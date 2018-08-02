import hlir
import function

def format_instruction(ins):

	if isinstance(ins.loc, function.Function):
		if ins.loc.address is not None:
			loc = hex(ins.loc.address)
		else:
			loc = "???"
	else:
		loc = str(ins.loc)

	if ins.results is None:
		results = "[]"
	else:
		results = ", ".join(str(r) for r in ins.results)
	if ins.args is None:
		args = "[]"
	else:
		args = ", ".join(str(a) for a in ins.args)

	if ins.type == hlir.ins_types.assign:
		return "%s := %s" % (results, args)
	
	if ins.type == hlir.ins_types.ret:
		return "return (%s) // dest: %s" % (args, loc)

	if ins.type == hlir.ins_types.jump:
		return "jump %s" % loc

	if ins.type == hlir.ins_types.jcond:
		return "jcond %s, %s" % (loc, args)
	
	if ins.type == hlir.ins_types.vmcall:
		return "%s := vmcall %s (%s)" % (results, loc, args)

	if ins.type == hlir.ins_types.call:
		return "%s := call %s (%s)" % (results, loc, args)
	
	if ins.type == hlir.ins_types.assertion:
		return "assert(%s)" % ins.args[0]

	# default behavior
	return str((ins.type, results, args, loc))


