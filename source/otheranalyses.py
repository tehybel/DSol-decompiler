import hlir
import expr
import utils
import function
import dataflow
import vmcall
import middleend
import functionid
import rewrites

class BBMerging(middleend.Optimization):
	is_cheap = True

	def optimize(self, f):
		unprocessed = set(f.bbs())
		while len(unprocessed) != 0:
			bb = unprocessed.pop()

			if bb.terminator.type != hlir.ins_types.jump:
				continue
			if not isinstance(bb.terminator.loc, expr.Lit):
				continue

			if len(bb.get_successors()) != 1:
				continue

			succ = bb.successor()
			if len(succ.get_predecessors()) != 1:
				continue
			assert (bb in succ.get_predecessors())

			if succ == f.header_node:
				continue

			# sanity check: no other BB should be able to reach the successor
			for node in f.nodes():
				if node == bb:
					continue
				assert (succ not in node.get_successors())

			# now it's safe to merge them
			self.changed = True

			if succ in unprocessed:
				unprocessed.remove(succ)
			assert (succ not in unprocessed)

			bb.merge(succ)
			unprocessed.add(bb) # maybe we can merge again

			assert (succ not in f.nodes())



class PredecessorReduction(middleend.Optimization):
	is_cheap = True

	def optimize(self, f):
		self.function = f
		f_nodes = f.nodes()
		for n in f_nodes:
			for p in n.get_predecessors():
				if p not in f_nodes:
					p.remove_successor(n)
					self.changed = True

class SuccessorReduction(middleend.Optimization):
	is_cheap = True

	def compute_indirect_jump_successors(self):
		return utils.compute_indirect_jump_successors(list(self.function.nodes()))
	
	# use the backwards reach for this.
	def compute_succs_for_node(self, n):
		backwards_reach = n._reachable_nodes(lambda x: x.get_predecessors())
		return utils.compute_indirect_jump_successors(
			list(self.function.nodes()),
			list(backwards_reach)
		)

	def optimize(self, f):
		self.function = f

		# use two rounds; 
		# in the first round, compute the new successors for all nodes. 
		# In the second round, update the successors.
		# (If we did both at once, some of the nodes we would be working on
		# might have turned unreachable when we get to them.)

		# round one
		updates = {}
		for node in f.nodes():
			if node.terminator.type in [hlir.ins_types.jump,
										hlir.ins_types.jcond]:
				if isinstance(node.terminator.loc, expr.Lit):
					addr = node.terminator.loc.literal
					try:
						succs = set([utils.get_node_by_addr(f.nodes(), addr)])
					except KeyError:
						succs = set()
				elif isinstance(node.terminator.loc, expr.Id):
					succs = self.compute_succs_for_node(node)
				else:
					# otherwise it may be improved via constant folding
					continue

				if node.terminator.type == hlir.ins_types.jcond:
					succs.add(node.next_bb)

				updates[node] = succs

		# round two
		for node, succs in updates.items():
			old_succs = node.get_successors()
			if len(succs) < len(old_succs):
				for s in old_succs:
					node.remove_successor(s)
				for s in succs:
					node.add_successor(s)
				self.changed = True


class Rewrites(middleend.Optimization):
	is_cheap = False

	def optimize(self, f):
		while True:
			progress = False
			for node in list(f.nodes()):
				result = rewrites.rewrite_node(node)
				progress |= result
				self.changed |= result

			if not progress:
				break

# in the loader code, we often see this pattern:
# jcond (!x, R); R: revert(0, 0);
# by turning this into a single assert call, we gain precision, because then
# we can merge and get fewer BBs.
class AssertReconstruction(middleend.Optimization):
	is_cheap = True

	def optimize(self, f):
		for bb in f.nodes():
			if bb.terminator.type != hlir.ins_types.jcond:
				continue
			if not isinstance(bb.terminator.loc, expr.Lit):
				continue

			disc = functionid.ExternalFunctionDiscovery(self.contract)
			if disc.matches_pattern(bb.terminator):
				continue

			def is_revert(n):
				# this is a compiler optimization; jumping back to address 0x0
				# will always result in an OutOfGas exception eventually, thus
				# causing a revert.
				if n.address == 0x0:
					return True

				if len(n.get_instructions()) == 0:
					if (n.terminator.type == hlir.ins_types.vmcall and
						n.terminator.loc == vmcall.vmcalls.revert):
						return True

				return False

			taken = utils.get_node_by_addr(f.nodes(), bb.terminator.loc.literal)
			fallthrough = bb.next_bb

			if is_revert(taken):
				other_bb = fallthrough
				ins = hlir.make_assertion(expr.Not(bb.terminator.args[0]))
			elif is_revert(fallthrough):
				other_bb = taken
				ins = hlir.make_assertion(bb.terminator.args[0])
			else:
				continue

			bb.append_instruction(ins)
			bb.terminator = hlir.make_jump(expr.Lit(other_bb.address))
			for s in bb.get_successors():
				bb.remove_successor(s)
			bb.add_successor(other_bb)
			self.changed = True


class StackFlattening(middleend.Optimization):
	is_cheap = True
	def optimize(self, f):
		if f.flattened:
			return

		for n in f.nodes():
			if utils.has_imprecise_successors(n):
				return

		fid = functionid.FunctionIdentification(self.contract)
		if fid.flatten(f) is not None:
			f.flattened = True
			self.changed = True

