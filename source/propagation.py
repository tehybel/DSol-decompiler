import middleend
import hlir
import expr
import dataflow
import utils
import vmcall

class Propagation(middleend.Optimization):
	def safe_to_propagate(self, use_point, definition, paths):
		# first we must check the instruction type
		def_ins = definition.point.ins
		if def_ins.type != hlir.ins_types.assign:
			# calls and impure vmcalls cannot be propagated
			return False

		assert (len(def_ins.results) == 1)
		lhs_var = def_ins.results[0]

		# special case if the RHS of the definition is in the LHS of the
		# definition
		for arg in def_ins.args:
			for r in utils.visit_expr(arg):
				if not isinstance(r, expr.Id):
					continue
				if dataflow.ids_may_be_equal(lhs_var, r, same_bb=True):
					return False

		# then check if the RHS of the definition is ever redefined along any
		# path from def to use.

		self.result = True

		def lhs_used(point):
			if point.ins == use_point.ins and point.node == use_point.node:
				# we hit the use point -- but is this the last time we'll hit
				# it?
				self.reached_use_point = True
				if self.index == 0:
					return dataflow.DefUseExplorer.STOP_EXPLORING_PATH

		def r_redefined(point):
			self.result = False
			return dataflow.DefUseExplorer.STOP_EXPLORING_ALTOGETHER

		# we're handling a definition like this:
		#
		# 	def_ins: LHS := RHS
		#
		# and a later use:
		#
		# 	use_ins: FOO := LHS
		#

		for path in paths:
			self.reached_use_point = False
			explorer = dataflow.DefUseExplorer(definition.point, True)

			# we want to know (1) if LHS is used 
			explorer.subscribe_to_may_use(lhs_var, lhs_used)

			# and (2) if any R in RHS is ever redefined.
			for arg in definition.point.ins.args:
				for r in utils.visit_expr(arg):
					if isinstance(r, expr.Id):
						explorer.subscribe_to_may_define(r, r_redefined)

						# note: this *is* necessary; if we delete it, we allow
						# propagation past "v := unused", but if we allow that
						# then we can no longer eliminate variables when we
						# see ":= unused"... so instead, wait for the end and
						# then remove all UnusedValue assignments.
						explorer.subscribe_to_unused(r, r_redefined)

			self.index = len(path) - 1
			def next_nodes(_):
				self.index -= 1
				if self.index < 0:
					return set()
				result = set([path[self.index]])
				return result

			explorer.next_nodes = next_nodes
			explorer.explore()

			if not self.result:
				return False
			assert (self.reached_use_point)

		return True
	
	
	def propagate_id(self, ident, use_point):
		if not isinstance(ident, expr.Id):
			return ident

		# for now only handle propagation of some types
		if isinstance(ident, expr.Var):
			pass
		elif isinstance(ident, expr.Mem):
			pass
		elif isinstance(ident, expr.Stack):
			pass
		else:
			# could be e.g. gvar, storage, arrayaccess
			return ident

		# we can't propagate parameters; we return early in this case because
		# possible_definitions can't find the implicit definition of the param
		if ident in self.function.params:
			return ident

		res = dataflow.get_certain_definitions(ident, use_point)
		if res is None:
			return ident
		paths, defs = res
		defining_nodes = set([path[-1] for path in paths])
		if len(defining_nodes) != 1:
			return ident

		definition, sp_offset = next(iter(defs.items()))

		if not self.safe_to_propagate(use_point, definition, paths):
			return ident

		# it's safe to propagate; do so.

		# vmcalls must be propagated specially
		def_ins = definition.point.ins
		if def_ins.type == hlir.ins_types.vmcall:
			assert (def_ins.results == use_point.ins.args)
			args = [a.copy() for a in def_ins.args]
			results = [r.copy() for r in use_point.ins.results]
			new_ins = hlir.make_vmcall(def_ins.loc, args, results)
			self.pending_replacements.append((use_point, new_ins))
			self.changed = True
			return ident

		assert (def_ins.type == hlir.ins_types.assign)
		value = definition.point.ins.args[0]
		self.changed = True

		# if we're propagating a stack variable, we need to adjust its offset
		def fix(e):
			if isinstance(e, expr.Stack):
				e.offset += sp_offset
			return e
		
		# these should never be propagated
		assert (not isinstance(value, expr.UnusedValue)) 

		return utils.visit_and_modify(value.copy(), fix)

	def propagate_in_node(self, node):
		instrs = node.get_instructions() + [node.terminator]
		for ins in instrs:
			#print("before: %s (function 0x%x)" % (ins, node.function.address))
			use_point = dataflow.ProgramPoint(node, ins)
			fix = lambda v: self.propagate_id(v, use_point)
			utils.visit_and_modify_instruction(ins, fix, exclude_lhs=True)
			#print("after: %s" % ins)
			#self.hook(self.contract)
			#print("done")

class InterBBPropagation(Propagation):
	is_cheap = False
	def optimize(self, f):
		self.function = f

		self.pending_replacements = []

		for node in f.nodes():
			self.propagate_in_node(node)

		for use_point, new_ins in self.pending_replacements:
			use_point.node.replace_instruction(use_point.ins, new_ins)

	def is_inter_bb(self):
		return True

# This optimization is unnecessary, because InterBBPropagation does the same
# work and more. However this one is super cheap since it doesn't require
# global analysis, so we can run this first to save work in the global
# analyses
class IntraBBPropagation(Propagation):
	is_cheap = True
	def optimize(self, f):
		self.function = f

		self.pending_replacements = []

		for node in f.nodes():
			self.propagate_in_node(node)

		for use_point, new_ins in self.pending_replacements:
			use_point.node.replace_instruction(use_point.ins, new_ins)
	
	def is_inter_bb(self):
		return False


"""
Sometimes we have a pair like this:
1:        var0 = (var0 / 0x3);
2:        var0 = (0x5 + var0);
We can't propagate because (1) interferes. But if we eliminated (1) then it
would be okay to propagate. So we handle this case here.
"""
class InsPairUnification(middleend.Optimization):
	is_cheap = True
	def optimize(self, f):
		for node in f.nodes():
			for ins1, ins2 in utils.instruction_pairs(node):
				if ins1.type != hlir.ins_types.assign:
					continue

				if ins2.type == hlir.ins_types.assign:
					id1, id2 = ins1.results[0], ins2.results[0]
					if not dataflow.ids_must_be_equal(id1, id2, True):
						continue
				elif (ins2.type == hlir.ins_types.vmcall 
						and ins2.loc in vmcall.terminating_vmcalls):

					# if ins2 is a terminating vmcall then we must ensure that
					# id1 doesn't appear in its arguments, otherwise
					# eliminating ins1 isn't safe.
					id1 = ins1.results[0]
					bad = False
					for arg in ins2.args:
						for e in utils.visit_expr(arg):
							if isinstance(e, expr.Id):
								if (dataflow.ids_may_be_equal(id1, e, True) and not 
										(dataflow.ids_must_be_equal(id1, e, True))):
									bad = True
					if bad:
						continue
				else:
					continue

				def fix(e):
					if not isinstance(e, expr.Id):
						return e
					if dataflow.ids_must_be_equal(e, id1, True):
						self.changed = True
						return ins1.args[0].copy()
					return e

				utils.visit_and_modify_instruction(ins2, fix, True)
				if self.changed:
					node.remove_instruction(ins1)
					break

