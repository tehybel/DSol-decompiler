import utils
import draw
import settings
import expr

class Node:
	pass

class Contract(Node):
	def __init__(self, fs, constructor, bc):
		self.functions = sorted(fs, key=lambda f: f.address)
		self.constructor = constructor
		self.bytecode = bc

	def __str__(self):
		out = "contract {\n"
		for f in self.functions:
			out += utils.indent(str(f) + "\n")
		out += "}\n"
		return out
	def gen_code(self, o):
		o.write("contract Decompiled {\n")
		o.indent(+1)

		for f in self.functions:
			o.gen_code(f)

		o.indent(-1)
		o.write("}\n")

class Function(Node, draw.NodeContainer):
	def __init__(self, h, params, num_retvals, ext):
		# this sets self.header_node
		draw.NodeContainer.__init__(self, h)
		self.address = h.address
		self.params = params
		self.num_params = len(params)
		self.num_retvals = num_retvals
		self.external = ext
		self.var_names = {}
	
	def nodes(self):
		return self.header_node.reachable_nodes()

	def __str__(self):
		out = "function {\n"
		out += utils.indent("header: 0x%x\n" % self.header_node.address)
		out += "}\n"
		return out
	
	def num_statements(self):
		result = 0
		for node in self.nodes():
			if isinstance(node, Sequence):
				result += len(node.instructions)
			else:
				result += 1
		return result
	
	def gen_code(self, o):
		o.notify_new_func(self)

		# write the header
		o.write("function ")
		o.write(o.lookup_func(self))
		o.write(" (")

		o.write_comma_separated_exprs(self.params)

		o.write(") ")
		if self.num_retvals != 0:
			o.write("returns (%s) " % 
				", ".join("int" for _ in range(self.num_retvals)))

		o.write("{\n")

		# write the body
		o.indent(+1)
		o.add_pending_bb(self.header_node)
		o.process_pending_bbs()

		# write the trailer
		o.indent(-1)
		o.write("}\n\n")

class Sequence(Node, draw.Node):
	def __init__(self, addr, instrs, t, spd):
		self.address = addr
		self.instructions = instrs
		self.terminator = t
		self.sp_delta = spd
		self.successors = set()
	def get_successors(self):
		return self.successors
	
	def replace_successor(self, old, new):
		self.successors.remove(old)
		self.successors.add(new)
	
	def __str__(self):
		if settings.pretty_ast:
			return "Sequence (0x%x)\n" % self.address

		out = ""
		out += "%x:\n" % id(self)
		out += "Sequence (0x%x):\n" % self.address
		if self.sp_delta != 0:
			out += "sp += %d\n" % self.sp_delta
		for ins in self.instructions:
			if not settings.show_unusedvalue_assignments:
				if utils.is_unused(ins):
					continue
			out += str(ins) + "\n"
		if self.terminator:
			out += str(self.terminator) + "\n"
			
		return out
	
	def gen_code(self, o):
		if self.sp_delta != 0:
			o.write("sp += %d\n" % self.sp_delta)
		for ins in self.instructions:
			o.gen_code_for_ins(ins)
		assert (self.terminator is None)
		assert (len(self.successors) <= 1)
		for s in self.successors:
			o.gen_code(s)

class IndirectJump(Node, draw.Node):
	def __init__(self, dest, succs):
		self.dest = dest
		self.successors = succs
	def __str__(self):
		return "IndirectJump (%s)\n" % (self.dest)
	def get_successors(self):
		return self.successors
	def gen_code(self, o):
		o.write("goto ")
		o.gen_code(self.dest)
		o.write(";\n")
		# TODO: this sorting should be done in codegen module
		for s in sorted(self.successors, key=lambda x: x.address):
			o.add_pending_bb(s)

class IfElse(Node, draw.Node):
	def __init__(self, exp, t, f):
		self.true_node = t
		self.false_node = f
		self.follow = None
		self.exp = exp
		self.terminator = None
	
	def replace_successor(self, old, new):
		if old == self.true_node:
			self.true_node = new
		elif old == self.false_node:
			self.false_node = new
		else:
			assert (old == self.follow)
			self.follow = new
	
	def __str__(self):
		out = ""
		if settings.pretty_ast:
			return "IfElse\n"
		out += "%x\n" % id(self)
		out += "IfElse:\n"
		out += "%s\n" % (self.exp)

		if settings.pretty_ast:
			return out

		if self.true_node is not None:
			out += "t: %x\n" % id(self.true_node)
		else:
			out += "t: None\n"
		if self.false_node is not None:
			out += "f: %x\n" % id(self.false_node)
		else:
			out += "f: None\n"
		if self.follow is not None:
			out += "fol: %x\n" % id(self.follow)
		else:
			out += "fol: None\n"
		return out
	
	def gen_code(self, o):
		o.write("if (")
		o.gen_code(self.exp)
		o.write(") {\n")
		o.indent(+1)
		if self.true_node:
			o.gen_code(self.true_node)
		o.indent(-1)
		o.write("}\n")
		if self.false_node:
			if isinstance(self.false_node, IfElse):
				o.write("else ")
				o.gen_code(self.false_node)
			else:
				o.write("else {\n")
				o.indent(+1)
				o.gen_code(self.false_node)
				o.indent(-1)
				o.write("}\n")
		if self.follow:
			o.gen_code(self.follow)
	
	def get_successors(self):
		result = []
		if self.true_node:
			result.append(self.true_node)
		if self.false_node:
			result.append(self.false_node)
		if self.follow:
			result.append(self.follow)
		return result

class Loop(Node, draw.Node):
	def __init__(self, h, f):
		self.header_node = h
		self.follow_node = f
		self.exp = expr.Lit(1)

	def __str__(self):
		return "Loop"
	def gen_code(self, o):
		o.write("while (")
		self.exp.gen_code(o)
		o.write(") {\n")
		o.indent(+1)
		o.gen_code(self.header_node)
		o.indent(-1)
		o.write("}\n")
		if self.follow_node:
			o.gen_code(self.follow_node)
	def replace_successor(self, old, new):
		assert (old == self.follow_node)
		self.follow_node = new
	def get_successors(self):
		result = [self.header_node]
		if self.follow_node:
			result.append(self.follow_node)
		return result

class Break(Node, draw.Node):
	def __str__(self):
		if not settings.pretty_ast:
			return ("%x:\n" % id(self)) + "Break"
		return "Break"
	def gen_code(self, o):
		o.write("break;\n")
	def get_successors(self):
		return set()

class Continue(Node, draw.Node):
	def __str__(self):
		if not settings.pretty_ast:
			return ("%x:\n" % id(self)) + "Continue"
		return "Continue"
	def gen_code(self, o):
		o.write("continue;\n")
	def get_successors(self):
		return set()
