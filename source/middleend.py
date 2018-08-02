# must be defined before imports to avoid circularity issues..
class Optimization:
	def __init__(self, c):
		self.contract = c
		self.changed = False

import utils
import expr
import hlir
import rewrites
import function
import vmcall
import dataflow
import elimination
import propagation
import functionid
import otheranalyses


class Optimizer:

	def sanity_checks(self, f):
		f_nodes = set(f.nodes())
		found_by_dfs = set(utils.dfs_ordering(f.header_node))
		assert (f_nodes == found_by_dfs)

		# for speedups
		preds = {node: node.get_predecessors() for node in f_nodes}
		succs = {node: node.get_successors() for node in f_nodes}


		seen_addrs = set()

		for node in f_nodes:

			# BB addresses should be unique
			assert (node.address not in seen_addrs)
			seen_addrs.add(node.address)

			# check preds/succs first
			for succ in succs[node]:
				assert (node in preds[succ])
				assert (succ in f_nodes)
				assert (succ.function == node.function)
			for pred in preds[node]:
				#assert (pred in f_nodes)
				#assert (pred.function == node.function)
				assert (node in pred.get_successors())
				
			assert (isinstance(node, hlir.BasicBlock))
			for ins in node.get_instructions():
				assert (None not in ins.results)
				assert (None not in ins.args)
				assert (ins.type in hlir.ins_types.__dict__)
				assert (ins.type != hlir.ins_types.jcond)
				assert (ins.type != hlir.ins_types.jump)
			assert (isinstance(node.sp_delta, int))
			assert (node.address is None or isinstance(node.address, int))

			# other checks on every node
			assert (node.function)
			assert (node.function == f)

			if utils.has_imprecise_successors(node):
				assert (len(node.get_successors()) > 0)


		# check that no expression object appears in more than one
		# instruction. Otherwise changing e.g. operand1 in (var123 + 0x55) may
		# affect more than one instruction, which leads to subtle bugs.
		seen = set()
		def mark_seen(e):
			if not isinstance(e, expr.Var):
				assert (id(e) not in seen)
				seen.add(id(e))
			return e

		for node in f_nodes:
			utils.visit_and_modify_expressions(node, mark_seen)

	def __init__(self, contract, hook=None):
		self.changed = False
		self.contract = contract

		if hook is None:
			hook = lambda c: True
		self.hook = hook

		self.optimizations = [

			## Speedups:
			otheranalyses.SuccessorReduction,
			otheranalyses.PredecessorReduction,

			## Elimination:
			elimination.LocalVariableElimination,
			elimination.IntraBBDCE,
			elimination.InterBBDCE,

			## Propagation:
			propagation.IntraBBPropagation,
			propagation.InterBBPropagation,
			propagation.InsPairUnification,

			## Readability:
			otheranalyses.Rewrites,
			otheranalyses.AssertReconstruction,
			otheranalyses.StackFlattening,

			functionid.FunctionIdentification,
		]

		# delay these as much as possible for better output
		self.delayed_analyses = [
			functionid.ExternalFunctionDiscovery,
		]

		self.more_delayed_analyses = [
			otheranalyses.BBMerging,
			elimination.UnusedVariableElimination,
		]

	def apply_opt(self, _opt, f):
		#print("running %s" % _opt)
		checksum = f.checksum()
		opt = _opt(self.contract)
		opt.hook = self.hook
		opt.optimize(f)

		if opt.changed:
			#print("YES: %s" % _opt)
			self.hook(self.contract)
		if not opt.changed:
			new_checksum = f.checksum()
			assert (new_checksum == checksum)
		
		self.changed |= opt.changed

	def optimize_until_fixed_point(self, f):
		cheap_opts = [opt for opt in self.optimizations if opt.is_cheap]
		expensive_opts = [opt for opt in self.optimizations if not opt.is_cheap]

		while True:
			self.changed = False

			for opt in cheap_opts:
				self.apply_opt(opt, f)
				self.sanity_checks(f)
			
			if self.changed:
				continue

			for opt in expensive_opts:
				self.apply_opt(opt, f)
				self.sanity_checks(f)

			if self.changed:
				continue

			for opt in self.delayed_analyses:
				self.apply_opt(opt, f)
				self.sanity_checks(f)

			if self.changed:
				continue

			for opt in self.more_delayed_analyses:
				self.apply_opt(opt, f)
				self.sanity_checks(f)

			if not self.changed:
				break
	
	def optimize(self):
		self.hook(self.contract)

		for f in self.contract.functions:
			self.optimize_until_fixed_point(f)


