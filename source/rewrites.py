import hlir
import utils
import expr
import vmcall
import dataflow
import addressdispenser

###########################################################################

# HLIR REWRITES BELOW




# undo the compiler optimization which turns individual returns into jumps to
# a common return BB
def duplicate_terminating_successors(node):
	if len(node.get_successors()) == 0:
		pass
	elif utils.has_imprecise_successors(node):
		pass
	else:
		return False
	
	# it must have more than one predecessor
	if len(node.get_predecessors()) <= 1:
		return False
	
	changeable = [p for p in node.get_predecessors() 
				 	if not utils.has_imprecise_successors(p)]
	
	# sometimes changeable has a ridiculous size (200+) so avoid splitting in
	# those cases
	if len(changeable) > 5:
		return False
	
	changed = False
	for pred in changeable:
		# we should make sure that the copy doesn't share the old instruction,
		# nor its arguments, but uses copies instead, and the copy should have
		# the same sp-delta
		new_bb = node.copy()

		new_bb.address = addressdispenser.get_new_address()
		new_bb.next_bb = None

		# it should replace the original..
		pred.replace_successor(node, new_bb)
		if pred.terminator.loc == expr.Lit(node.address):
			pred.terminator.loc = expr.Lit(new_bb.address)
		if pred.next_bb == node:
			pred.next_bb = new_bb

		changed = True
	
	return changed

def revert_reconstruct(n):
	if (n.terminator.type == hlir.ins_types.jump and n.terminator.loc == expr.Lit(0x0)):
		n.terminator = hlir.make_vmcall(vmcall.vmcalls.revert, [], [])
		for s in n.get_successors():
			n.remove_successor(s)
		return True
	return False
	

def make_memseq_assignment(ins1, ins2):
	if ins1.type != hlir.ins_types.assign:
		return
	if ins2.type != hlir.ins_types.assign:
		return
	a = ins1.results[0]
	b = ins2.results[0]
	if not isinstance(a, expr.Mem):
		return
	if not isinstance(b, expr.Mem):
		return
	
	# ensure the lengths are OK
	if not isinstance(a.length, expr.Lit):
		return
	if not isinstance(b.length, expr.Lit):
		return
	
	# ensure that the memories are adjacent
	if isinstance(a.address, expr.Lit) and isinstance(b.address, expr.Lit):
		if b.address.literal != a.address.literal + a.length.literal:
			return
	elif isinstance(b.address, expr.Add):
		if (dataflow.exprs_must_be_equal(b.address.operand2, a.address, same_bb=True) and
			dataflow.exprs_must_be_equal(b.address.operand1, a.length, same_bb=True)):
			pass
		elif (dataflow.exprs_must_be_equal(b.address.operand1, a.address, same_bb=True) and 
			  dataflow.exprs_must_be_equal(b.address.operand2, a.length, same_bb=True)):
			pass
		else:
			return
	else:
		return
	
	return hlir.make_assign(
		expr.Mem(a.address, expr.Add(a.length, b.length)),
		expr.Sequence([ins1.args[0], ins2.args[0]])
	)

def generate_mem_seqs(node):
	for ins1, ins2 in utils.instruction_pairs(node):

		new_ins = make_memseq_assignment(ins1, ins2)
		if not new_ins:
			new_ins = make_memseq_assignment(ins2, ins1)
		if not new_ins:
			continue

		index = node.get_instructions().index(ins1)
		node.remove_instruction(ins1)
		node.remove_instruction(ins2)
		node.insert_instruction(new_ins, index)
		return True
	
	return False

def move_calldataloads_to_params(node):
	if node.function.address == 0x0:
		return False

	changed = False

	for ins in node.get_instructions() + [node.terminator]:
		if ins.type != hlir.ins_types.vmcall:
			continue
		if ins.loc != vmcall.vmcalls.calldataload:
			continue
		if not isinstance(ins.args[0], expr.Lit):
			continue
		offset = ins.args[0].literal
		if offset < 4:
			continue

		assert (offset % 0x20 == 4)
		pn = (offset - 4) / 0x20

		f = node.function
		while f.num_params < pn + 1:
			f.params.append(expr.Var())
			f.num_params += 1
			assert (len(f.params) == f.num_params)

		p = f.params[pn].copy()

		new_ins = hlir.make_assign(ins.results[0].copy(), p)
		node.replace_instruction(ins, new_ins)

		changed = True
	
	return changed

def jcond_not_not(node):
	if node.terminator.type != hlir.ins_types.jcond:
		return False
	
	exp = node.terminator.args[0]
	if not isinstance(exp, expr.Not):
		return False
	if not isinstance(exp.operand, expr.Not):
		return False
	
	node.terminator.args[0] = exp.operand.operand
	return True

# if(0){x}else{y} -----> y, if(1){x}else{y} -----> x
def simplify_if_lit(node):
	if node.terminator.type != hlir.ins_types.jcond:
		return False
	
	exp = node.terminator.args[0]
	if not isinstance(exp, expr.Lit):
		return False

	if exp.literal == 0:
		target = node.next_bb
	else:
		target = [n for n in node.get_successors()
				  if n != node.next_bb][0]
	node.terminator = hlir.make_jump(expr.Lit(target.address))
	for s in node.get_successors():
		node.remove_successor(s)
	node.add_successor(target)
	return True

def remove_useless_assignments(node):
	changed = False
	for ins in list(node.get_instructions()):
		if ins.type == hlir.ins_types.assign:
			if (isinstance(ins.args[0], expr.Id) 
					and isinstance(ins.results[0], expr.Id)):
				if dataflow.ids_must_be_equal(ins.args[0], ins.results[0], True):
					node.remove_instruction(ins)
					changed = True
				
	return changed
	

def assert_lit(node):
	for ins in node.get_instructions():
		if (ins.type == hlir.ins_types.assertion 
				and isinstance(ins.args[0], expr.Lit)
				and ins.args[0].literal != 0):
			node.remove_instruction(ins)
			return True

	return False


############################################################################

# EXPRESSION REWRITES BELOW

# turn this:
#	storage(sha3((param0, 0x0)))
# into this:
# 	mapping0[param0]
def detect_mapping_access(node):
	if not isinstance(node, expr.Storage):
		return
	addr = node.address
	if not isinstance(addr, expr.PureFunctionCall):
		return
	if addr.name != vmcall.vmcalls.sha3:
		return
	if not isinstance(addr.args[0], expr.Sequence):
		return
	offset, mapping_num = addr.args[0].expressions
	if not isinstance(mapping_num, expr.Lit):
		return
	return expr.MappingAccess(mapping_num.literal, offset)

def do_detect_array_access(op1, op2):
	if not isinstance(op1, expr.PureFunctionCall):
		return
	if op1.name != vmcall.vmcalls.sha3:
		return
	if not isinstance(op1.args[0], expr.Lit):
		return
	num = op1.args[0].literal
	offset = op2
	result = expr.ArrayAccess(num, offset)
	return result

# turn this:
#	storage(var0 + sha3(0x0))
# into this:
# 	array0[var0]
def detect_array_access(node):
	if not isinstance(node, expr.Storage):
		return
	addr = node.address
	if not isinstance(addr, expr.Add):
		return
	fixed = do_detect_array_access(addr.operand1, addr.operand2)
	if fixed:
		return fixed
	return do_detect_array_access(addr.operand2, addr.operand1)

def simplify_eq(node):
	if (isinstance(node, expr.Eq) 
			and dataflow.exprs_must_be_equal(node.operand1, node.operand2, True)):
		return expr.Lit(1)

def fold_constants(node):
	if (isinstance(node, expr.BinaryOp) 
			and isinstance(node.operand1, expr.Lit) 
			and isinstance(node.operand2, expr.Lit)):
		result = expr.Lit(node.evaluate(None).num())
		return result
	
	if (isinstance(node, expr.UnaryOp) 
			and isinstance(node.operand, expr.Lit)):
		result = expr.Lit(node.evaluate(None).num())
		return result

def fold_commutative_constants(node):
	if not isinstance(node, expr.BinaryOp) or not node.is_commutative:
		return
	typ = node.__class__
	if isinstance(node.operand1, typ):
		n = fold_constants(typ(node.operand2, node.operand1.operand1))
		if n: return typ(n, node.operand1.operand2)
		n = fold_constants(typ(node.operand2, node.operand1.operand2))
		if n: return typ(n, node.operand1.operand1)
	if isinstance(node.operand2, typ):
		n = fold_constants(typ(node.operand1, node.operand2.operand1))
		if n: return typ(n, node.operand2.operand2)
		n = fold_constants(typ(node.operand1, node.operand2.operand2))
		if n: return typ(n, node.operand2.operand1)

# e.g. ((0x60 + free_mem_ptr) - free_mem_ptr) -----> 0x60
def simplify_plus_minus(node):
	if not isinstance(node, expr.Sub):
		return
	a, b = node.operand1, node.operand2
	if not isinstance(a, expr.Add):
		return
	if dataflow.exprs_must_be_equal(a.operand2, b, True):
		return a.operand1
	if dataflow.exprs_must_be_equal(a.operand1, b, True):
		return a.operand2
	
	if isinstance(a.operand1, expr.Lit) and isinstance(b, expr.Lit):
		return expr.Add(a.operand2, expr.Lit(a.operand1.literal - b.literal))
	if isinstance(a.operand2, expr.Lit) and isinstance(b, expr.Lit):
		return expr.Add(a.operand1, expr.Lit(a.operand2.literal - b.literal))

def simplify_duplicate_and(node):
	if not isinstance(node, expr.And):
		return
	a, b = node.operand1, node.operand2
	if isinstance(b, expr.And):
		if dataflow.exprs_must_be_equal(a, b.operand1, True):
			return b
		if dataflow.exprs_must_be_equal(a, b.operand2, True):
			return b
	if isinstance(a, expr.And):
		if dataflow.exprs_must_be_equal(b, a.operand1, True):
			return a
		if dataflow.exprs_must_be_equal(b, a.operand2, True):
			return a

def simplify_add(node):
	if not isinstance(node, expr.Add):
		return
	if node.operand1 == expr.Lit(0):
		return node.operand2
	if node.operand2 == expr.Lit(0):
		return node.operand1

def simplify_div(node):
	if not isinstance(node, expr.Div):
		return
	if node.operand2 == expr.Lit(1):
		return node.operand1

def simplify_mul(node):
	if not isinstance(node, expr.Mul):
		return
	if node.operand1 == expr.Lit(1):
		return node.operand2
	if node.operand2 == expr.Lit(1):
		return node.operand1

def simplify_and(node):
	if not isinstance(node, expr.And):
		return
	if node.operand1 == expr.Lit((2**256)-1):
		return node.operand2
	if node.operand2 == expr.Lit((2**256)-1):
		return node.operand1

def simplify_minus(node):
	if isinstance(node, expr.Sub):
		if dataflow.exprs_must_be_equal(node.operand1, node.operand2, same_bb=True):
			return expr.Lit(0)

def simplify_minus_minus(node):
	if not isinstance(node, expr.Sub):
		return
	a, b = node.operand1, node.operand2
	if not isinstance(a, expr.Sub):
		return
	a1, a2 = a.operand1, a.operand2
	if not isinstance(a2, expr.Lit) or not isinstance(b, expr.Lit):
		return
	return expr.Sub(a1, expr.Lit(a2.literal + b.literal))

def simplify_expr_seqs(node):
	if not isinstance(node, expr.Sequence):
		return
	
	if not any(isinstance(e, expr.Sequence) for e in node.expressions):
		return

	new_expressions = []
	for e in node.expressions:
		if isinstance(e, expr.Sequence):
			new_expressions += e.expressions
		else:
			new_expressions.append(e)
	node.expressions = new_expressions
	return node


############################################################################

# these rewrites work on HLIR node
hlir_node_rewrites = [
	simplify_if_lit,
	generate_mem_seqs,
	assert_lit,
	remove_useless_assignments,

	revert_reconstruct,

	# TODO: this really belongs near CFA..?
	duplicate_terminating_successors,

	# TODO: move these to readability module
	move_calldataloads_to_params,

	jcond_not_not,
]

expr_rewrites = [
	fold_constants,
	fold_commutative_constants,
	simplify_plus_minus,
	simplify_duplicate_and,
	simplify_eq,
	simplify_and,
	simplify_mul,
	simplify_div,
	simplify_add,
	simplify_minus,
	simplify_minus_minus,
	simplify_expr_seqs,

	# TODO: move this to readability.. maybe?
	detect_mapping_access,
	detect_array_access,
]

def rewrite_node(node):
	assert (isinstance(node, hlir.HLIRNode))

	result = False

	# first rewrite the node itself
	for rewrite in hlir_node_rewrites:
		r = rewrite(node)
		#if r: print(rewrite)
		result |= r
	
	# then rewrite any of its expressions
	for rewrite in expr_rewrites:
		r = utils.visit_and_modify_expressions(node, rewrite)
		#if r: print(rewrite)
		result |= r
	
	return result
	
