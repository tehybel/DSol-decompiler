import log
import expr
import hlir
import json
from sha3 import keccak_256

def remove_swarm_hash(bytecode):
	
	# new-type swarm hash (post 0.4.7, I think)
	index = bytecode.find("bzzr0")
	if index != -1:
		return bytecode[:index-2]

	# old-type swarm hash: bytecode ends in JUMP STOP, and then 32 bytes of hash
	if bytecode[-34] == "\x56" and bytecode[-33] == "\x00":
		return bytecode[:-32]

	#log.warn("Did not find a Swarm hash at the end of the bytecode")
	return bytecode


def read_file_contents(filename):
	try:
		f = open(filename)
	except IOError:
		log.critical("Could not open file '" + filename + "' for reading")
	s = f.read()
	f.close()
	return s

def decode_bytecode(s):
	s = s.replace("0x", "").strip()
	if len(s) % 2 != 0:
		log.critical("Invalid bytecode (Its length is odd.)")
	try:
		return s.decode("hex")
	except TypeError:
		log.critical("Non-hexadecimal characters in bytecode")

def big_endian_decode(ns):
	result = 0
	for n in ns:
		result <<= 8
		result |= n
	return result

def get_node_by_addr(nodes, addr):
	for node in nodes:
		if node.address == addr:
			return node
	raise KeyError() # we rely on this elsewhere

TAB = " "*2
def indent(text, times=1):
	result = ""
	new_line = True
	for c in text:
		if new_line:
			result += TAB*times
			new_line = False

		if c == "\n":
			new_line = True
		result += c
	
	return result

# sign-extend a value that is 'bits' wide
def extend(value, bits):
	sign_bit = 1 << (bits - 1)
	return (value & (sign_bit - 1)) - (value & sign_bit)

# bitwise negate a value that is 'bits' wide
def neg(value, bits):
	max_value = (1 << bits) - 1
	return max_value - value

def signed(value):
	if value >= (1 << 255):
		value -= (1 << 256)
	return value
	
def visit_and_modify(node, func, exclude=False):
	for attr in node.child_names:
		child_node = getattr(node, attr)
		assert (child_node != node)
		if isinstance(child_node, list):
			for i in range(len(child_node)):
				child_node[i] = visit_and_modify(child_node[i], func)
		else:
			new_child_node = visit_and_modify(child_node, func)
			setattr(node, attr, new_child_node)

	if not exclude:
		return func(node)


# NOTE: if two expressions compare equal but have different ids then this will
# only retrieve one of them!!!
def visit_expr(e, exclude=False):
	if exclude:
		result = []
	else:
		result = [e]
	
	for attr in e.child_names:
		child_node = getattr(e, attr)
		assert (child_node != e)
		if isinstance(child_node, list):
			for item in child_node:
				r = visit_expr(item)
				assert (e not in r)
				result += r
		else:
			r = visit_expr(child_node)
			assert (not any(id(e) == id(x) for x in r))
			result += r
	
	return {id(e): e for e in result}.values()

def visit_and_modify_instruction(ins, func, exclude_lhs=False):
	for i in range(len(ins.args)):
		ins.args[i] = visit_and_modify(ins.args[i], func)
	for i in range(len(ins.results)):
		if exclude_lhs:
			visit_and_modify(ins.results[i], func, True)
		else:
			ins.results[i] = visit_and_modify(ins.results[i], func)
	if isinstance(ins.loc, expr.Expression):
		ins.loc = visit_and_modify(ins.loc, func)

def pairs(l):
	i = 0
	while i < len(l) - 1:
		yield (l[i], l[i+1])
		i += 1

def is_unused(ins):
	if ins.type == hlir.ins_types.assign:
		if isinstance(ins.args[0], expr.UnusedValue):
			return True
	return False

def instruction_pairs(node):
	instrs = node.get_instructions() + [node.terminator]
	instrs = [ins for ins in instrs if not is_unused(ins)]
	return pairs(instrs)

def parse_json(filename):
	text = read_file_contents(filename)
	obj = json.loads(text)

	bytecode = decode_bytecode(obj["bytecode"])
	deployed_bytecode = decode_bytecode(obj["deployedBytecode"])
	
	return bytecode, deployed_bytecode

# NOTE: width is in bytes, not bits!
def pack(value, width):
	result = []
	for _ in range(width):
		result.append(value & 0xff)
		value >>= 8
	return result[::-1]

def unpack(values):
	result = 0
	for byte in values:
		assert (byte <= 255)
		assert (byte >= 0)
		result <<= 8
		result |= byte
	return result

def visit_and_modify_expressions(node, func, exclude_lhs=False):
	assert (isinstance(node, hlir.HLIRNode))
	result = [False]

	def modify(exp):
		new = func(exp)
		if new:
			result[0] = True
			return new
		return exp

	for ins in node.get_instructions() + [node.terminator]:
		visit_and_modify_instruction(ins, modify, exclude_lhs)

	return result[0]

def dfs_ordering(node):
	result = []
	seen = set()
	stack = [node]
	while len(stack) != 0:
		n = stack.pop()
		if n in seen:
			continue
		seen.add(n)
		for succ in n.get_successors():
			stack.append(succ)
		result.append(n)
	return result

def sha3(text):
	h = keccak_256()
	h.update(text)
	return int("0x" + h.hexdigest(), 16)

def compute_indirect_jump_successors(all_nodes, subset=None):
	if subset is None:
		subset = all_nodes

	valid_addresses = {}
	for node in all_nodes:
		# do not include the node with address 0, nor those with None
		if node.address:
			valid_addresses[node.address] = node

	result = set()
	for node in subset:
		for ins in node.get_instructions():
			if ins.type != hlir.ins_types.assign:
				continue
			for e in ins.args:
				if (isinstance(e, expr.Lit) and 
						e.literal in valid_addresses):
					result.add(valid_addresses[e.literal])
	assert (len(result) != 0)
	return result

def has_imprecise_successors(bb):
	ins = bb.terminator
	if (ins.type in [hlir.ins_types.jump, hlir.ins_types.jcond]
			and not isinstance(ins.loc, expr.Lit)):
		return True
	return False

def compute_preds(f):
	preds = {}
	for n in f.nodes():
		preds[n] = set()
	for n in f.nodes():
		for s in n.get_successors():
			preds[s].add(n)
	return preds
