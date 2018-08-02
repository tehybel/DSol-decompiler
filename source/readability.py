import expr
import absyn
import utils
import hlir
import vmcall
from collections import OrderedDict

def improve_not_ifelse(n):
	if n.false_node is None:
		return False
	result = False
	while isinstance(n.exp, expr.Not):
		n.exp = n.exp.operand
		n.true_node, n.false_node = n.false_node, n.true_node
		result = True
	return result

def improve_double_not_if(n):
	if isinstance(n.exp, expr.Not) and isinstance(n.exp.operand, expr.Not):
		n.exp = n.exp.operand.operand
		return True
	return False

def improve_empty_if(n):
	if n.true_node is None:
		n.exp = expr.Not(n.exp)
		n.true_node, n.false_node = n.false_node, n.true_node
		return True
	else:
		return False

def remove_empty_nodes(f):
	changed = False
	preds = utils.compute_preds(f)

	# remove useless nodes
	for n in f.nodes():
		if not isinstance(n, absyn.Sequence):
			continue
		if len(n.instructions) != 0:
			continue
		if n.sp_delta != 0:
			continue
		succs = n.get_successors()
		if len(succs) != 1:
			continue
		succ = next(iter(succs))
		ps = preds[n]
		if len(ps) != 1:
			continue
		
		pred = next(iter(ps))
		if isinstance(pred, absyn.IfElse):
			if pred.true_node == n:
				pred.true_node = succ
				changed = True
			if pred.false_node == n:
				pred.false_node = succ
				changed = True
			if pred.follow == n:
				pred.follow = succ
				changed = True
		elif isinstance(pred, absyn.Loop):
			if pred.header_node == n:
				pred.header_node = succ
				changed = True
		else:
			pass # unhandled for now
	
	return changed

def improve_loop(loop):
	if not isinstance(loop.header_node, absyn.IfElse):
		return False
	ifelse = loop.header_node
	if not (loop.exp == expr.Lit(1)):
		return False
	if ifelse.follow is not None:
		return False
	if isinstance(ifelse.false_node, absyn.Break):
		loop.exp = ifelse.exp
		loop.header_node = ifelse.true_node
		return True

	return False

def name_vars(f):
	# name results
	# (we used OrderedDict to avoid duplicates but retain order)
	returned_vars = OrderedDict()
	for node in f.nodes():
		if isinstance(node, absyn.Sequence):
			for ins in node.instructions:
				if ((ins.type == hlir.ins_types.ret) or 
						(ins.type == hlir.ins_types.vmcall and
						 ins.loc == vmcall.vmcalls.haltreturn)):
					for arg in ins.args:
						if isinstance(arg, expr.Var):
							returned_vars[id(arg)] = arg
						elif isinstance(arg, expr.Sequence):
							for v in arg.expressions:
								returned_vars[id(v)] = v

	if len(returned_vars) == 1:
		v = next(iter(returned_vars.values()))
		f.var_names[id(v)] = "result"
	else:
		for i, v in enumerate(returned_vars.values()):
			f.var_names[id(v)] = "result%d" % i

	# name params; do this after, so they get priority over results
	for i, p in enumerate(f.params):
		f.var_names[id(p)] = "param%d" % i
	
	# name loop induction variables
	indvar_names = ["i", "j", "ii", "jj"]
	indvar_index = 0
	for node in f.nodes():
		if isinstance(node, absyn.Loop):
			if isinstance(node.exp, (expr.Lt, expr.SLt)):
				try:
					name = indvar_names[indvar_index]
					indvar_index += 1
					f.var_names[id(node.exp.operand1)] = name
				except IndexError:
					pass

def improve(contract):
	for f in contract.functions:
		while True:
			changed = False

			changed |= remove_empty_nodes(f)

			for n in f.header_node.reachable_nodes():
				if isinstance(n, absyn.Sequence):
					pass

				elif isinstance(n, absyn.IfElse):
					changed |= improve_empty_if(n)
					changed |= improve_double_not_if(n)
					changed |= improve_not_ifelse(n)

				elif isinstance(n, absyn.Loop):
					changed |= improve_loop(n)
		
			if not changed:
				break

		name_vars(f)
			
	return contract
