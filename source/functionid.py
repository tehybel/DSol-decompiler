import hlir
import expr
import utils
import function
import dataflow
import vmcall
import middleend

class FunctionIdentification(middleend.Optimization):
	is_cheap = False

	def compute_reachable_rets(self, h):
		ret_deltas = {}
		reach = set()

		def is_ret(ins):
			return (ins.type == hlir.ins_types.jump 
					and not isinstance(ins.loc, expr.Lit))

		stack = []
		stack.append((h, 0))

		while True:
			try:
				node, delta = stack.pop()
			except IndexError:
				break

			if node in reach:
				# it's a cycle
				continue

			reach.add(node)

			delta += node.sp_delta

			if is_ret(node.terminator):
				if node not in ret_deltas:
					ret_deltas[node] = delta
				else:
					assert (delta == ret_deltas[node])
				continue
			
			for succ in node.get_successors():
				stack.append((succ, delta))

		return ret_deltas, reach
	
	def compute_deltas(self, node, delta, path):
		if self.failed:
			return

		delta += node.sp_delta

		if node in self.deltas:
			if delta != self.deltas[node]:
				self.failed = True
				return
		else:
			self.deltas[node] = delta

		if node in path:
			# it's a cycle, but we've just determined that the delta is OK, so
			# everything is fine
			return

		for succ in node.get_successors():
			self.compute_deltas(succ, delta, path + [node])
		
	def flatten(self, f):
		self.deltas = {}
		self.failed = False
		self.compute_deltas(f.header_node, 0, [])
		if self.failed:
			return None
		self.absolute_offsets = set()

		# adjust the sp-delta of each node to 0
		# we can't just use .adjust_sp_delta because we must do this for all
		# nodes, not just BBs.
		def fix(e, delta):
			if isinstance(e, expr.Stack) and id(e) not in adjusted:
				e.offset -= delta
				self.absolute_offsets.add(e.offset)
				adjusted.add(id(e))
			return e

		for node in f.nodes():
			adjusted = set()
			delta = -self.deltas[node]
			utils.visit_and_modify_expressions(node, lambda e: fix(e, delta))
			node.sp_delta = 0

		variables = {}

		def do_fix(e):
			if not isinstance(e, expr.Stack):
				return e
			offset = e.offset
			if offset not in variables:
				variables[offset] = expr.Var()
			return variables[offset]

		for node in f.nodes():
			utils.visit_and_modify_expressions(node, do_fix)

		for i in range(len(f.params)):
			f.params[i] = utils.visit_and_modify(f.params[i], do_fix)
	
		# now there should not be a single stack variable left.
		def check(e):
			assert (not isinstance(e, expr.Stack))
			return e
		for node in f.nodes():
			utils.visit_and_modify_expressions(node, check)

		return fix
		
	def compute_ret_delta(self, h, reachable_rets):
		self.result = 999
		
		stack = [(h, 0)]
		seen = set()
		while len(stack) != 0:
			n, offset = stack.pop()
			if n in seen:
				continue
			seen.add(n)

			offset += n.sp_delta
			
			def visit(n):
				if isinstance(n, expr.Stack):
					total_offset = n.offset + offset
					if total_offset < self.result:
						self.result = total_offset
				return n

			utils.visit_and_modify_expressions(n, visit)

			if n in reachable_rets:
				continue

			for s in n.get_successors():
				stack.append((s, offset))

		if self.result == 999:
			return None

		return [self.result]

	def attempt_function_creation(self, h):
		if len(h.get_predecessors()) < 2:
			return False

		# compute which indirect jumps are reachable from h and which sp-delta
		# they jump to
		reachable_rets, reach = self.compute_reachable_rets(h)
		if len(reachable_rets) == 0:
			return False

		# the reach should never include another function's header
		for f in self.contract.functions:
			if f.header_node in reach:
				return False

		# every predecessor of h which isn't in the reach must be a direct
		# jump
		for pred in h.get_predecessors():
			if pred in reach:
				continue
			if pred.terminator.type != hlir.ins_types.jump:
				return False
			if not isinstance(pred.terminator.loc, expr.Lit):
				return False
			if len(pred.get_successors()) != 1:
				return False

		# no other BB must jump into the middle of the function
		for r in reach:
			if r != h and any(p not in reach for p in r.get_predecessors()):
				return False

		# "calldataload" should never leave the external functions
		for bb in reach:
			for ins in bb.get_instructions():
				if (ins.type == hlir.ins_types.vmcall 
						and ins.loc == vmcall.vmcalls.calldataload):
					return False

		ret_deltas = self.compute_ret_delta(h, reachable_rets)
		if ret_deltas is None:
			# couldn't determine the delta
			return False

		ret_deltas = set(ret_deltas)
		if len(ret_deltas) > 1:
			# all rets should share the same delta (otherwise the function
			# we're trying to detect may have performed a jump to another
			# function)
			return False

		assert (len(ret_deltas)) == 1

		# now we know which sp-delta the return address is at.
		ret_delta = ret_deltas.pop()

		# it should be at most zero, anything else makes no sense.
		if ret_delta > 0:
			return False

		# for any BB that jumps to h but which is not reachable from h,
		# figure out which value it puts at the delta
		node_addrs = {node.address: node 
					  for node in self.function.nodes()}
		ret_addrs = {}
		preds = h.get_predecessors()
		stack_positions = set()
		for pred in preds:
			if pred in reach:
				continue

			# it must be a literal which corresponds to a valid BB address
			point = dataflow.resolve_stackvar(ret_delta, pred)
			if not point:
				return False

			value = point.ins.args[0]
			if not isinstance(value, expr.Lit):
				return False

			if value.literal not in node_addrs:
				return False

			ret_addrs[pred] = (value.literal, point)
			stack_positions.add(point.ins.results[0].offset)

		# if all the return addresses are defined in only a single program
		# point, then we should just propagate it with another analysis rather
		# than create a function.
		unique_defs = set([(p.node, p.ins) for _, p in ret_addrs.values()])
		if len(unique_defs) == 1:
			return False

		# these are all the items that lie above the return address at call
		# time
		num_params = -ret_delta

		# these are all the items that lie above the return address at ret
		# time
		bb_delta = reachable_rets.values()[0]
		num_retvals = num_params + bb_delta + 1 # +1 for ret addr

		f = function.Function(h, num_params, num_retvals, False)
		f.params = [expr.Stack(-i) for i in range(f.num_params)][::-1]

		# if we get this far then this is truly a function, so it's safe to
		# convert the jumps to calls
		self.changed = True

		self.contract.functions.append(f)

		# we must set this right away so h doesn't get eliminated when it
		# loses its predecessors
		h.function = f

		for pred in h.get_predecessors():
			if pred in reach:
				continue

			args = [expr.Stack(offset) 
					for offset in range(-f.num_params + 1, 1)]
			assert (len(args) == len(f.params))
			retvals = [expr.Stack(offset) 
					   for offset in range(-f.num_retvals + 1, 1)]

			# don't add the retvals yet; we must do so after adjusting the sp.
			new_ins = hlir.make_call(f, args, [])
			pred.append_instruction(new_ins)

			assert (pred.successor() == h)


			ret_addr, point = ret_addrs[pred]

			# make sure that a call always returns to the following
			# instruction
			succ = node_addrs[ret_addr]
			assert (succ.function == pred.function)
			pred.terminator = hlir.make_jump(expr.Lit(succ.address))
			pred.add_successor(succ)
			for s in pred.get_successors():
				if s != succ:
					pred.remove_successor(s)
			assert (pred.get_successors() == set([succ]))
			assert (h != succ)

			pred.adjust_sp_delta(f.num_retvals - (f.num_params + 1))

			new_ins.results = retvals


			# NOTE: we *CANNOT* eliminate the assignment to the return
			# address, because other BBs may still use that variable. It
			# simply isn't safe. Let another analysis do that.


		# convert the indirect jumps to rets
		for ret_bb in reachable_rets:
			retvals = [expr.Stack(offset) 
					   for offset in range(-f.num_retvals + 1, 1)]

			# we deliberately throw away the return address (jump.get_dest())
			# so that it goes away from the code.
			ret_bb.terminator = hlir.make_return(retvals, None)
			for s in ret_bb.get_successors():
				ret_bb.remove_successor(s)

		# flatten the stack variables in the function, so that the function
		# doesn't touch the stack at all, preventing side effects
		self.flatten(f)
		assert (not self.failed)

		# now, *after* we updated successors and preds, then f.nodes() is
		# well-defined and we can update each node's function to be f
		for n in f.nodes():
			n.function = f

		f.invalidate_cached_nodes()
		self.function.invalidate_cached_nodes()

		return True

	def optimize(self, f):
		
		if not f.external:
			return

		self.function = f

		while True:
			progress = False

			# we sort the nodes so that we'll prefer the latest BBs, because
			# otherwise we take most of the loader code and just move it to a
			# different function, which we then can't analyze.
			for node in (utils.dfs_ordering(f.header_node)):
				if node == f.header_node:
					continue

				if self.attempt_function_creation(node):
					progress = True
					break

			if not progress:
				break

class ExternalFunctionDiscovery(middleend.Optimization):
	is_cheap = False

	def matches_pattern(self, t):
		if t.type != hlir.ins_types.jcond:
			return False

		if not isinstance(t.loc, expr.Lit):
			return False

		if not isinstance(t.args[0], expr.Eq):
			return False

		if isinstance(t.args[0].operand1, expr.Lit):
			lit = t.args[0].operand1.literal
			if lit <= 0x100000000 and lit != 0x0:
				return True

		if isinstance(t.args[0].operand2, expr.Lit):
			lit = t.args[0].operand2.literal
			if lit <= 0x100000000 and lit != 0x0:
				return True

		return False
	
	def has_calldataload(self, bb):
		for ins in bb.get_instructions():
			if ins.type == hlir.ins_types.vmcall:
				if ins.loc == vmcall.vmcalls.calldataload:
					if not (ins.args[0] == expr.Lit(0)):
						return True
		return False
	
	def has_call(self, bb):
		for ins in bb.get_instructions():
			if ins.type == hlir.ins_types.call:
				return True
		return False
	
	def make_function_at(self, calling_bb, h):
		# make a copy of every node reachable from 'h'
		translate = {}
		for n in h.reachable_nodes():
			new = n.copy()
			translate[n] = new

		old_h = h
		h = translate[old_h]
		f = function.Function(h, 0, 0, True)

		# mark new nodes as belonging to the new function,
		# and initialize their successor information
		for n, new in translate.items():
			new.function = f
			for s in new.get_successors():
				new.remove_successor(s)
			assert (len(new.get_successors()) == 0)
			for s in n.get_successors():
				new.add_successor(translate[s])

			if n.next_bb:
				if n.next_bb in translate:
					new.next_bb = translate[n.next_bb]
				else:
					new.next_bb = None

		# sanity check
		old_func_nodes = calling_bb.function.nodes()
		for n in f.nodes():
			assert (n not in old_func_nodes)
			assert (n.function == f)
			for s in n.get_successors():
				assert (s.function == f)
				assert (s in f.nodes())
			for p in n.get_predecessors():
				assert (p.function == f)
				assert (p in f.nodes())

		old_h.terminator = hlir.make_call(f, [], [])
		for ins in old_h.get_instructions():
			old_h.remove_instruction(ins)
		for s in old_h.get_successors():
			old_h.remove_successor(s)

		self.contract.functions.append(f)
		self.changed = True

	def optimize(self, f):
		if f.address != 0x0:
			return

		cur_func_addrs = set([func.address 
							  for func in self.contract.functions])
		seen = set()
		stack = [f.header_node]
		while len(stack) != 0:
			cur = stack.pop()
			if cur in seen:
				continue
			seen.add(cur)

			if (self.has_calldataload(cur) or self.has_call(cur)):
				# we're likely inside a function now, so don't proceed.
				continue

			if self.matches_pattern(cur.terminator):
				addr = cur.terminator.loc.literal
				if addr not in cur_func_addrs:
					target = f.get_nodes_by_addr()[addr]
					self.make_function_at(cur, target)
				stack.append(cur.next_bb)
				continue
			
			if not utils.has_imprecise_successors(cur):
				for s in cur.get_successors():
					stack.append(s)

