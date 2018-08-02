from middleend import Optimization
import hlir
import expr
import dataflow
import utils
import vmcall

class UnusedVariableElimination(Optimization):
	is_cheap = True
	def optimize(self, f):
		for node in f.nodes():
			for ins in list(node.get_instructions()):
				if utils.is_unused(ins):
					node.remove_instruction(ins)
					self.changed = True
					

# this analysis is unnecessary; InterBBDCE will do the same work and more.
# However this analysis is quite cheap, so we can run this one initially to
# save work in the more expensive analyses.
# The idea is to find *all* usages of all expr.Var instances. If there's an
# assignment to a Var that's not ever used, we can eliminate it.
class LocalVariableElimination(Optimization):
	is_cheap = True
	def collect_vars(self, f):
		result = set()
		def collect(e):
			if isinstance(e, expr.Var):
				result.add(e)
			return e
		for node in f.nodes():
			utils.visit_and_modify_expressions(node, collect, True)

		return result

	def optimize(self, f):
		used_vars = self.collect_vars(f)

		for node in f.nodes():
			for ins in node.get_instructions() + [node.terminator]:
				if ins.type != hlir.ins_types.assign:
					continue
				if not isinstance(ins.results[0], expr.Var):
					continue
				if isinstance(ins.args[0], expr.UnusedValue):
					continue
				if ins.results[0] not in used_vars:
					node.remove_instruction(ins)
					self.changed = True


class DCE(Optimization):
	def safe_to_eliminate(self, var, def_point):
		self.result = True
		self.reached_redefinition = False
		self.terminated = False

		def lhs_redefined(_):
			self.reached_redefinition = True
			return dataflow.DefUseExplorer.STOP_EXPLORING_PATH

		def lhs_used(_):
			self.result = False
			return dataflow.DefUseExplorer.STOP_EXPLORING_ALTOGETHER

		def handle_term():
			self.terminated = True
		
		# we're handling a definition like this:
		# LHS := RHS
		inter_bb = self.is_inter_bb()
		explorer = dataflow.DefUseExplorer(def_point, inter_bb, uses_cache=self.uses_cache)

		# we want to know (1) if LHS is ever redefined, 
		explorer.subscribe_to_must_define(var, lhs_redefined)
		explorer.subscribe_to_unused(var, lhs_redefined)
		explorer.subscribe_to_termination(handle_term)

		# and (2) if LHS may be used
		explorer.subscribe_to_may_use(var, lhs_used)

		try:
			explorer.explore()
		except dataflow.ExplorationFailedException:
			return False

		if not inter_bb:
			if not self.reached_redefinition and not self.terminated:
				return False

		return self.result

	def attempt_to_eliminate(self, bb, ins):
		if ins.type == hlir.ins_types.assign:
			pass
		elif ins.type == hlir.ins_types.vmcall:
			if ins.loc not in vmcall.pure_vmcalls:
				return
		else:
			return

		assert (len(ins.results) == 1)
		var = ins.results[0]
		assert (isinstance(var, expr.Id))

		# TODO: re-enable eliminating pure vmcalls.
		# TODO: once again handle the case where this is an intra-BB analysis,
		# but there are no successors.

		def_point = dataflow.ProgramPoint(bb, ins)

		if not self.safe_to_eliminate(var, def_point):
			return

		# we go with the safe option and never eliminate stores to storage
		if (isinstance(var, expr.Storage) 
				or isinstance(var, expr.NamedStorageAccess)):
			return

		if isinstance(var, expr.Mem):
			if self.is_inter_bb() or not self.terminated:
				return

		bb.remove_instruction(ins)
		self.changed = True

	def eliminate_dead_code(self):
		for bb in self.function.bbs():
			for ins in bb.get_instructions():
				self.attempt_to_eliminate(bb, ins)
		
	def optimize(self, f):
		self.uses_cache = {}
		self.function = f
		self.eliminate_dead_code()

class InterBBDCE(DCE):
	is_cheap = False
	def is_inter_bb(self):
		return True

class IntraBBDCE(DCE):
	is_cheap = True
	def is_inter_bb(self):
		return False


