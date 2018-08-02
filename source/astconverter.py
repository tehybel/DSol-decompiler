import utils
import absyn
import expr
import hlir

class Converter:
	def __init__(self, contract, loops, follows, constructor_ast):
		self.contract = contract
		self.loops = loops
		self.follows = follows
		self.constructor_ast = constructor_ast
		self.cur_func = None
		self.used_loops = set()
	
	def convert_bb(self, bb):
		if bb in self.bb_to_ast:
			return self.bb_to_ast[bb]
		ast = absyn.Sequence(
			bb.address, 
			bb.get_instructions(), 
			bb.terminator,
			bb.sp_delta
		)
		self.bb_to_ast[bb] = ast
		self.ast_to_bb[ast] = bb
		for s in bb.get_successors():
			ast.successors.add(self.convert_bb(s))
		return ast
	
	def convert_function(self, f):
		self.bb_to_ast = {}
		self.ast_to_bb = {}
		header = self.convert_bb(f.header_node)
		return absyn.Function(header, f.params, f.num_retvals, f.external)
	
	def visit_nodes(self, f, func):
		for node in f.nodes():
			func(node)
			self.sanity_checks(f)
	
	def remove_direct_jumps(self, node):
		if not isinstance(node, absyn.Sequence):
			return
		ins = node.terminator
		if ins and ins.type == hlir.ins_types.jump:
			if isinstance(ins.loc, expr.Lit):
				assert (len(node.successors) == 1)
				assert (next(iter(node.successors)).address == ins.loc.literal)
				node.terminator = None

	def move_terminators(self, node):
		if (isinstance(node, absyn.Sequence) 
				and node.terminator is not None 
				and node.terminator.type in [hlir.ins_types.vmcall,
											 hlir.ins_types.ret,
											 hlir.ins_types.call]):
			node.instructions.append(node.terminator)
			node.terminator = None

	def remove_indirect_jumps(self, node):
		ins = node.terminator
		if ins and ins.type == hlir.ins_types.jump:
			if not isinstance(ins.loc, expr.Lit):
				indirectjump_node = absyn.IndirectJump(ins.loc, node.successors)
				node.successors = set([indirectjump_node])
				node.terminator = None

	def remove_jconds(self, node):
		if not isinstance(node, absyn.Sequence):
			return

		ins = node.terminator
		if ins and ins.type == hlir.ins_types.jcond:
			# TODO: we don't yet handle indirect jconds
			assert (len(node.successors) == 2)
			jump_taken_node, fallthrough_node = list(node.successors)
			if fallthrough_node.address == ins.loc.literal:
				jump_taken_node, fallthrough_node = fallthrough_node, jump_taken_node

			assert (jump_taken_node.address == ins.loc.literal)
			
			assert (jump_taken_node is not None)
			assert (fallthrough_node is not None)

			ifelse_node = absyn.IfElse(
				ins.args[0],
				jump_taken_node,
				fallthrough_node,
			)

			assert (not (ifelse_node.true_node == ifelse_node.false_node))

			node.terminator = None
			node.successors = set([ifelse_node])

	
	def remove_follow_edges(self, node):
		if not isinstance(node, absyn.IfElse):
			return
		follow = node.follow
		if follow is None:
			return

		assert (not (follow == node.true_node and follow == node.false_node))

		if node.true_node == follow:
			node.true_node = None
		else:
			self.do_remove_follow_edges(node, node.true_node, follow)

		if node.false_node == follow:
			node.false_node = None
		else:
			self.do_remove_follow_edges(node, node.false_node, follow)

	def do_remove_follow_edges(self, orig, start_node, follow):
		assert (start_node != follow)

		def remove_follow(n, s):
			if isinstance(n, absyn.Sequence):
				assert (n.successors == set([s]))
				n.successors = set()
			elif isinstance(n, absyn.Loop):
				assert (follow == n.follow_node)
				n.follow_node = None
			else:
				assert (isinstance(n, absyn.IfElse))
				if n.follow == follow:
					n.follow = None
				assert (n.false_node != follow or n.true_node != follow)
				if n.true_node == follow:
					assert (n.false_node is not None)
					n.true_node = None
				if n.false_node == follow:
					assert (n.true_node is not None)
					n.false_node = None

		seen = set()
		stack = [start_node]
		while len(stack) != 0:
			n = stack.pop()

			if n in seen:
				continue
			seen.add(n)

			if isinstance(n, absyn.IndirectJump):
				continue

			# this can happen if we failed to structure a loop
			if n == orig:
				continue

			for s in n.get_successors():
				if s == follow:
					remove_follow(n, s)
				else:
					stack.append(s)
	
	def sanity_checks(self, f):
		
		remaining_addrs = set()
		for n in f.nodes():
			if isinstance(n, absyn.Sequence):
				remaining_addrs.add(n.address)

			if isinstance(n, absyn.IfElse):
				# if both are None, then where does the IfElse go???
				assert (n.true_node is not None or
						n.false_node is not None)

		# AST conversion should only ever result in more nodes; otherwise
		# we've lost some nodes.
		assert (len(f.nodes()) >= len(self.old_f.nodes()))

		# no nodes should have disappeared
		for bb in self.bb_to_ast:
			assert (bb.address in remaining_addrs)

	
	def replace_loop_edges(self, loop_node, cur):
		assert (cur != loop_node.follow_node)

		# avoid cycles
		if cur in self.tmp_seen:
			return
		self.tmp_seen.add(cur)

		# replace edges
		for s in cur.get_successors():
			if s == loop_node.header_node:
				# don't follow it
				cur.replace_successor(s, absyn.Continue())
			elif s == loop_node.follow_node:
				# don't follow it
				cur.replace_successor(s, absyn.Break())
			else:
				assert (s != loop_node.header_node)
				assert (s != loop_node.follow_node)
				# do follow it
				self.replace_loop_edges(loop_node, s)

	
	def fix_loops(self, f):
		loops = set()

		# first enumerate valid loops
		for loop in self.loops:
			if loop.header_node not in self.bb_to_ast:
				# must belong to another function..
				continue

			# convert loop info to our new AST nodes
			header_node = self.bb_to_ast[loop.header_node]
			if loop.follow_node:
				follow_node = self.bb_to_ast[loop.follow_node]
			else:
				follow_node = None

			self.used_loops.add(loop)
			loop_node = absyn.Loop(header_node, follow_node)
			loops.add(loop_node)

		for loop_node in loops:
			header_node = loop_node.header_node
			follow_node = loop_node.follow_node
			preds = utils.compute_preds(f)

			self.tmp_seen = set()
			self.replace_loop_edges(loop_node, header_node)

			# insert the loop node before its header
			for pred in preds[header_node]:
				if pred not in self.tmp_seen:
					pred.replace_successor(header_node, loop_node)
			if header_node == f.header_node:
				f.header_node = loop_node

			# if this loop was the follow of another loop, update that follow
			# to reflect our change
			for other_loop in loops:
				if other_loop == loop_node:
					continue
				if other_loop.follow_node == loop_node.header_node:
					other_loop.follow_node = loop_node

			# if this loop was the follow of a conditional, update that follow
			for node in f.nodes():
				if isinstance(node, absyn.IfElse) and node.follow == header_node:
					node.follow = loop_node

			# check that there's no way "out" of the loop except through the
			# follow node
			assert (loop_node not in loop_node.header_node.reachable_nodes())
			assert (follow_node not in loop_node.header_node.reachable_nodes())

	def fix_locations(self, f, conv):
		for node in f.nodes():
			if isinstance(node, absyn.Sequence):
				for ins in node.instructions:
					if ins.loc in conv:
						ins.loc = conv[ins.loc]

	def set_conditional_follows(self, node):
		if not isinstance(node, absyn.Sequence):
			return
		if len(node.successors) != 1:
			return
		succ = next(iter(node.successors))
		if not isinstance(succ, absyn.IfElse):
			return

		orig = self.ast_to_bb[node]
		if orig not in self.follows:
			return

		follow_bb = self.follows[orig]
		succ.follow = self.bb_to_ast[follow_bb]

	def convert(self):
		funcs = []
		conv = {}
		# TODO: what about mappings and such?
		for old_f in self.contract.functions:
			self.old_f = old_f
			f = self.convert_function(old_f)
			funcs.append(f)
			conv[old_f] = f

			# then get rid of indirect jumps
			# note that this must happen before removing follow edges,
			# otherwise we can't refrain from following indirect jumps as
			# easily
			self.visit_nodes(f, self.remove_indirect_jumps)
	
			# then get rid of jconds
			self.visit_nodes(f, self.remove_jconds)

			# then get rid of direct jumps
			self.visit_nodes(f, self.remove_direct_jumps)

			# then move vmcalls from terminator to being part of the instructions
			self.visit_nodes(f, self.move_terminators)

			self.visit_nodes(f, self.set_conditional_follows)
			self.fix_loops(f)
			self.visit_nodes(f, self.remove_follow_edges)

			self.sanity_checks(f)

		for f in funcs:
			self.fix_locations(f, conv)

		# sanity check
		assert (self.used_loops == self.loops)

		constructor = None
		if self.constructor_ast:
			constructor = self.constructor_ast.functions[0]
			funcs += self.constructor_ast.functions

		return absyn.Contract(funcs, constructor, self.contract.bytecode)

def convert(contract, loops, follows, constructor_ast):
	c = Converter(contract, loops, follows, constructor_ast)
	return c.convert()
