import expr
import hlir
import utils
import vmcall

class ProgramPoint:
	def __init__(self, node, ins):
		self.node = node
		self.ins = ins
	
class Def:
	def __init__(self, bb, ins, var):
		self.var = var
		self.point = ProgramPoint(bb, ins)
	
	def __eq__(self, o):
		# this is really necessary, because we need to put Defs into a set to
		# deduplicate them.
		return self.point.ins == o.point.ins and self.point.node == o.point.node
	
	def __hash__(self):
		return hash(self.point.node)
	
	def __str__(self):
		return "def of %s: %s" % (str(self.var), str(self.point))

def exprs_must_be_equal(e1, e2, same_bb=False):
	if (e1.__class__ != e2.__class__):
		return False
	if isinstance(e1, expr.Lit):
		return e1 == e2
	if isinstance(e1, expr.Id):
		return ids_must_be_equal(e1, e2, same_bb)
	# TODO make more precise
	return False

def exprs_may_be_equal(e1, e2, same_bb=False):
	if (e1.__class__ != e2.__class__):
		return False
	if isinstance(e1, expr.Lit):
		return e1 == e2
	if isinstance(e1, expr.Id):
		return ids_may_be_equal(e1, e2, same_bb)
	# TODO make more precise
	return False

# this only returns true when the IDs are definitely the same
def ids_must_be_equal(id1, id2, same_bb=False):
	assert (isinstance(id1, expr.Id))
	assert (isinstance(id2, expr.Id))
	if id1.__class__ != id2.__class__:
		return False

	if isinstance(id1, expr.Lit):
		return id1 == id2
	
	if not ids_may_be_equal(id1, id2, same_bb):
		return False

	elif isinstance(id1, expr.Var):
		return id1 == id2
	
	elif isinstance(id1, expr.Mem):
		if (isinstance(id1.address, expr.Lit) and
				isinstance(id2.address, expr.Lit) and
				isinstance(id1.length, expr.Lit) and
				isinstance(id2.length, expr.Lit)):
			return id1 == id2
		elif (isinstance(id1.address, expr.Id) and
				isinstance(id2.address, expr.Id) and
				isinstance(id1.length, expr.Id) and
				isinstance(id2.length, expr.Id)):
			return (
				ids_must_be_equal(id1.address, id2.address) and
				ids_must_be_equal(id1.length, id2.length)
			)
		else:
			return False

	elif isinstance(id1, expr.Stack):
		if same_bb:
			return id1.offset == id2.offset
		else:
			return False # we don't know.
	
	elif isinstance(id1, expr.Storage):
		if (isinstance(id1.address, expr.Lit) 
				and isinstance(id2.address, expr.Lit)):
			return id1.address == id2.address

		if (isinstance(id1.address, expr.Id) 
				and isinstance(id2.address, expr.Id)):
			return ids_must_be_equal(id1.address, id2.address)

		return False
	
	elif isinstance(id1, expr.GlobalVar):
		return id1.name == id2.name

	elif isinstance(id1, expr.NamedStorageAccess):
		if id1.num != id2.num:
			return False
		return exprs_must_be_equal(id1.offset, id2.offset)
	
	else:
		print(id1)
		assert (False)

def ids_may_be_equal(id1, id2, same_bb=False):
	assert (isinstance(id1, expr.Id))
	assert (isinstance(id2, expr.Id))
	if id1.__class__ != id2.__class__:
		return False
	
	if isinstance(id1, expr.Var):
		return id1 == id2

	elif isinstance(id1, expr.Mem):
		# special case: mem(0x40, 0x20) ?= mem(mem(0x40, 0x20), 0x20)
		# we assume that this is false, because the free mem ptr would be
		# pointing at itself otherwise, which is nonsense.
		if (id1.is_free_mem_ptr() 
				and isinstance(id2.address, expr.Mem) 
				and id2.address.is_free_mem_ptr()):
			return False

		if all(isinstance(e, expr.Lit) 
			   for e in [id1.address, id1.length, id2.address, id2.length]):
			r1 = range(id1.address.literal, id1.address.literal + id1.length.literal)
			r2 = range(id2.address.literal, id2.address.literal + id2.length.literal)
			intersection = set(r1) & set(r2)
			return len(intersection) != 0

		return True
	
	elif isinstance(id1, expr.NamedStorageAccess):
		if id1.num != id2.num:
			return False
		return exprs_may_be_equal(id1.offset, id2.offset)
	
	elif isinstance(id1, expr.Stack):
		if same_bb:
			return id1.offset == id2.offset
		else:
			return True

	elif isinstance(id1, expr.Storage):
		if (isinstance(id1.address, expr.Lit) 
				and isinstance(id2.address, expr.Lit)):
			return id1.address == id2.address

		if (isinstance(id1.address, expr.Id) 
				and isinstance(id2.address, expr.Id)):
			return ids_may_be_equal(id1.address, id2.address)

		return True

	elif isinstance(id1, expr.GlobalVar):
		return id1.name == id2.name

	else:
		print(id1)
		print(id2)
		assert (False)

def get_certain_definitions(ident, use_point):
	paths = []
	defs = {}

	explorer = DefUseExplorer(use_point, inter_bb=True, forward=False)

	def ident_must_redefined(point):
		offset = explorer.sp_offset
		paths.append([use_point.node] + explorer.path)
		d = Def(point.node, point.ins, ident)
		if d in defs:
			if defs[d] != offset:
				while len(paths) != 0:
					paths.pop()
				return DefUseExplorer.STOP_EXPLORING_ALTOGETHER
		else:
			defs[d] = offset
		return DefUseExplorer.STOP_EXPLORING_PATH

	def ident_may_redefined(point):
		while len(paths) != 0:
			paths.pop()
		return DefUseExplorer.STOP_EXPLORING_ALTOGETHER

	explorer.subscribe_to_may_define(ident, ident_may_redefined)
	explorer.subscribe_to_must_define(ident, ident_must_redefined)

	try:
		explorer.explore()
	except ExplorationFailedException:
		return None

	return paths, defs

# this keeps on walking backwards and looking for the given stack variable,
# taking sp-deltas into account. It will stop the moment there's more than one
# predecessor.
def resolve_stackvar(offset, node, max_index=None):
	while True:
		instrs = node.get_instructions()
		if max_index is not None:
			instrs = instrs[:max_index]
			max_index = None
			
		for ins in reversed(instrs):
			if (ins.type == hlir.ins_types.assign and
				isinstance(ins.results[0], expr.Stack) and
				ins.results[0].offset == offset):
				return ProgramPoint(node, ins)

			else:
				for defined in ins.results:
					if (isinstance(defined, expr.Stack) 
							and defined.offset == offset):
						return None

		offset += node.sp_delta

		if len(node.get_predecessors()) != 1:
			return None

		node = next(iter(node.get_predecessors()))



# sometimes there's too much indirection, and then the all-paths analysis
# becomes too expensive -- in that case we'd rather return early (and use the
# safe answer) than to hang for a long time
MAX_STEPS = 35
class ExplorationFailedException(Exception):
	pass

class DefUseExplorer:
	STOP_EXPLORING_PATH = 1
	STOP_EXPLORING_ALTOGETHER = 2

	def __init__(self, bp, inter_bb, forward=True, uses_cache=None):
		self.begin_point = bp
		self.function = bp.node.function
		self.unused_subs = []
		self.may_define_subs = []
		self.must_define_subs = []
		self.may_use_subs = []
		self.term_sub = None
		self.inter_bb = inter_bb
		self.forward = forward
		self.steps = 0
		self.next_nodes = None

		if uses_cache:
			self.uses_cache = uses_cache
		else:
			self.uses_cache = {}
	
	def step(self):
		self.steps += 1
		if self.steps > MAX_STEPS:
			raise ExplorationFailedException()

	def subscribe_to_unused(self, var, func):
		self.unused_subs.append((var, func))
	
	def subscribe_to_may_define(self, var, func):
		self.may_define_subs.append((var, func))

	def subscribe_to_must_define(self, var, func):
		self.must_define_subs.append((var, func))

	def subscribe_to_may_use(self, var, func):
		self.may_use_subs.append((var, func))
	
	def subscribe_to_termination(self, func):
		self.term_sub = func
	
	def handle_uses(self, used_ids, point):
		for e in used_ids:
			assert (isinstance(e, expr.Id))
			for ident, handler in self.may_use_subs:
				if self.maybe_eq(ident, e):
					self.action = handler(point)
					if self.action: return self.action

	def must_eq(self, saught_id, other_id):
		if (isinstance(saught_id, expr.Stack) 
				and isinstance(other_id, expr.Stack)
				and self.sp_offset is not None):
			return saught_id.offset == other_id.offset + self.sp_offset

		return ids_must_be_equal(saught_id, other_id)
	
	def maybe_eq(self, saught_id, other_id):
		if (isinstance(saught_id, expr.Stack) 
				and isinstance(other_id, expr.Stack)
				and self.sp_offset is not None):
			return saught_id.offset == other_id.offset + self.sp_offset

		return ids_may_be_equal(saught_id, other_id)
	
	def get_uses(self, ins):
		if id(ins) not in self.uses_cache:
			# collect the uses
			used_ids = []
			def collect(e):
				if isinstance(e, expr.Id):
					used_ids.append(e)
				return e
			utils.visit_and_modify_instruction(ins, collect, exclude_lhs=True)
			self.uses_cache[id(ins)] = used_ids

		return self.uses_cache[id(ins)]
	
	def handle_ins(self, ins, point):
		# handle the uses
		used_ids = self.get_uses(ins)
		self.action = self.handle_uses(used_ids, point)
		if self.action: return

		if (ins.type == hlir.ins_types.vmcall 
				and ins.loc in vmcall.terminating_vmcalls):
			if self.term_sub:
				self.term_sub()

		if ins.type == hlir.ins_types.call:
			# if this is a call instruction, it may have had side effects,
			# which means that it could define any mem or storage.
			for ident, handler in self.may_define_subs:
				if (isinstance(ident, expr.Mem) 
						or isinstance(ident, expr.Storage)):
					self.action = handler(point)
					if self.action: return

		# handle the defs
		for res in ins.results:
			if not isinstance(res, expr.Id):
				continue

			if utils.is_unused(ins):
				# these are not true definitions, they're just extra
				# information.
				for ident, handler in self.unused_subs:
					if self.must_eq(ident, res):
						self.action = handler(point)
						if self.action: return
				continue

			# handle must-defines
			for ident, handler in self.must_define_subs:
				if self.must_eq(ident, res):
					self.action = handler(point)
					if self.action: return

			# handle may-defines
			for ident, handler in self.may_define_subs:
				if self.maybe_eq(ident, res):
					self.action = handler(point)
					if self.action: return

	def explore(self):
		self.sp_offset = 0
		first_node = True

		instrs = self.begin_point.node.get_instructions() + [self.begin_point.node.terminator]
		self.ins_offset = instrs.index(self.begin_point.ins)

		# then we must explore outward, keeping track of the state (on the
		# stack).
		stack = [(self.begin_point.node, [], 0)]

		def get_instrs(node):
			instrs = node.get_instructions() + [node.terminator]

			if self.ins_offset is not None:
				if self.forward:
					instrs = instrs[self.ins_offset+1:]
				else:
					instrs = instrs[:self.ins_offset]
				self.ins_offset = None

			if not self.forward:
				instrs = reversed(instrs)

			return instrs

		def adjust_sp_offset(node, next_node, sp_offset):
			if self.forward:
				n = next_node
			else:
				n = node

			if sp_offset is not None:
				if self.forward:
					sp_offset += n.sp_delta
				else:
					sp_offset -= n.sp_delta

			if self.forward:
				n = node
			else:
				n = next_node

			if utils.has_imprecise_successors(n):
				# we lose precision on indirect jumps.
				sp_offset = None

			return sp_offset

		if self.next_nodes:
			next_nodes = self.next_nodes
		elif self.forward:
			next_nodes = lambda n: n.get_successors()
		else:
			next_nodes = lambda n: n.get_predecessors()

		func_nodes = self.function.nodes()

		while len(stack) != 0:
			node, seen, sp_offset = stack.pop()
			self.sp_offset = sp_offset

			# check against cycles
			if node in seen:
				continue

			# this can happen sometimes while we're walking backwards and
			# predecessors haven't been updated yet
			if node not in func_nodes:
				continue
			
			assert (node.function == self.function)

			self.step()

			# mark node as seen
			if first_node:
				# we can't initially mark the first node as seen, because we
				# may only have seen *some* of its instructions.
				first_node = False
			else:
				seen = seen + [node]
			self.path = seen

			# handle the uses and defs in the node
			stop_exploring_path = False

			for ins in get_instrs(node):
				point = ProgramPoint(node, ins)
				self.handle_ins(ins, point)
				if self.action == self.STOP_EXPLORING_ALTOGETHER:
					return
				if self.action == self.STOP_EXPLORING_PATH:
					stop_exploring_path = True
					break

			if stop_exploring_path:
				continue

			nnodes = next_nodes(node)
			if len(nnodes) > 1 and not self.inter_bb:
				return

			# make sure to visit its successors
			for next_node in nnodes:
				new_sp_offset = adjust_sp_offset(node, next_node, sp_offset)
				args = (next_node, seen, new_sp_offset)
				stack.append(args)

