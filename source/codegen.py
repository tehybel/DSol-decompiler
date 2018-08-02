import symtab
import ll2hl
import vmcall
import hlir
import expr
import absyn
import utils

FUNC_PREFIX = "func"
VAR_PREFIX = "var"
LABEL_PREFIX = "L"

class CodeGenerator:
	def __init__(self, stats, contract):
		self.contract = contract
		self.goto_nodes = set()
		self.stats = stats
		self.reset()
		self.vars = {} # ast.Function -> symtab.SymbolTable
		self.labels = {} # ast.Function -> symtab.SymbolTable
		self.__funcs = self.make_func_symtab()
	
	def lookup_func(self, f):
		return self.__funcs.lookup(f)
	
	def reset(self):
		self.output = ""
		self.indent_level = 0
		self.seen = set()
		self.should_indent = False
		self.pending_bbs = []
		self.stats["num_gotos"] = 0
		self.stats["funcs_with_gotos"] = {}
	
	def lookup_var(self, v):
		vrs = self.vars[self.cur_func]
		if not vrs.contains(v) and id(v) in self.cur_func.var_names:
			name = self.cur_func.var_names[id(v)]
			vrs.insert(v, name)
		return vrs.lookup(v)
	
	def notify_new_func(self, f):
		self.cur_func = f

	def make_func_symtab(self):
		result = symtab.SymbolTable(FUNC_PREFIX)

		# recognize vmcall instructions
		# TODO is this needed?
		for name, _, _ in ll2hl.vmcalls.values():
			result.insert(name, name)

		for name in vmcall.get_vmcalls():
			result.insert(name, name)

		# collect, then name functions
		funcs = self.contract.functions

		func_num = 0
		for f in funcs:
			if f == self.contract.functions[0]:
				result.insert(f, "loader")

			elif f == self.contract.constructor:
				result.insert(f, "constructor")

			else:
				result.insert(f, "%s%d" % (FUNC_PREFIX, func_num))
				func_num += 1

		return result

	def write_char(self, c):
		assert (len(c) == 1)
		if self.should_indent:
			self.output += "\t"*self.indent_level
			self.should_indent = False

		self.output += c
		if c == "\n":
			self.should_indent = True
	
	def write(self, s):
		for c in s:
			self.write_char(c)

	def indent(self, delta):
		self.indent_level += delta
	
	def write_comma_separated_exprs(self, exprs):
		first = True
		for e in exprs:
			if first:
				first = False
			else:
				self.write(", ")
			e.gen_code(self)
	
	def compute_indirect_jump_targets(self, contract):
		self.indirect_jump_targets = set()
		for f in contract.functions:
			for n in f.header_node.reachable_nodes():
				if isinstance(n, absyn.IndirectJump):
					for s in n.successors:
						self.indirect_jump_targets.add(s)
	
	def generate_output(self):
		for f in self.contract.functions:
			self.vars[f] = symtab.SymbolTable(VAR_PREFIX)
			self.labels[f] = symtab.SymbolTable(LABEL_PREFIX)

		self.compute_indirect_jump_targets(self.contract)
		
		# first pass
		self.gen_code(self.contract)
		self.reset()

		# second pass
		self.gen_code(self.contract)

		return self.output.replace("\t", " "*4)

	def add_pending_bb(self, bb):
		self.pending_bbs.append(bb)
	
	def process_pending_bbs(self):
		while len(self.pending_bbs) != 0:
			bb = self.pending_bbs.pop()
			if id(bb) not in self.seen:
				self.gen_code(bb)

	def do_write_label(self, node):
		if isinstance(node, absyn.Sequence):
			self.write("0x%x" % node.address)
		else:
			self.write(self.labels[self.cur_func].lookup(node))

	def write_goto(self, node):
		# register stats
		self.stats["num_gotos"] += 1
		if self.cur_func not in self.stats["funcs_with_gotos"]:
			self.stats["funcs_with_gotos"][self.cur_func] = 0
		self.stats["funcs_with_gotos"][self.cur_func] += 1

		self.goto_nodes.add(node)
		self.write("goto ")
		self.do_write_label(node)
		self.write(";\n")
	
	def gen_code(self, node):
		if isinstance(node, absyn.Node):
			if id(node) in self.seen:
				self.write_goto(node)
				return
			self.seen.add(id(node))
			self.write_label(node)
		node.gen_code(self)

	def gen_code_for_call(self, ins):
		# write out results
		if len(ins.results) != 0:
			self.write_comma_separated_exprs(ins.results)
			self.write(" = ")

		# write out the function name
		self.write(self.__funcs.lookup(ins.loc))

		# write out the arguments
		self.write("(")
		if ins.loc.external:
			# TODO: put actuall calldataload instrs into the call at some
			# earlier point, so we don't have to special case here.
			self.write(", ".join("calldataload(0x%x)" % (4+i*0x20)
								 for i in range(ins.loc.num_params)))
		else:
			self.write_comma_separated_exprs(ins.args)
		self.write(");\n")

	def gen_code_for_vmcall(self, ins):
		# write out results
		if len(ins.results) != 0:
			self.write_comma_separated_exprs(ins.results)
			self.write(" = ")

		# write out the function name
		assert (isinstance(ins.loc, str))
		assert (ins.loc in self.__funcs.entries.values())
		self.write(self.__funcs.lookup(ins.loc))

		# write out the arguments
		self.write("(")
		self.write_comma_separated_exprs(ins.args)
		self.write(");\n")
	

	def gen_code_for_assign(self, ins):
		assert (len(ins.results) == 1)
		assert (len(ins.args) == 1)
		var = ins.results[0]
		exp = ins.args[0]
		# TODO re-enable this
		#if (isinstance(exp, expr.BinaryOp) and 
		#		exp.operand1 == var):
		#	self.gen_code(var)
		#	self.write(" %s= " % exp.symbol)
		#	self.gen_code(exp.operand2)
		#elif (isinstance(exp, expr.BinaryOp) 
		#		and exp.operand2 == var
		#		and exp.is_commutative):
		#	self.gen_code(var)
		#	self.write(" %s= " % exp.symbol)
		#	self.gen_code(exp.operand1)
		#else:
		self.gen_code(var)
		self.write(" = ")
		self.gen_code(exp)
		self.write(";\n")

	def gen_code_for_ins(self, ins):
		if ins.type == hlir.ins_types.assign:
			if not utils.is_unused(ins):
				self.gen_code_for_assign(ins)

		elif ins.type == hlir.ins_types.ret:
			self.write("return")
			if len(ins.args) != 0:
				self.write(" (")
				self.write_comma_separated_exprs(ins.args)
				self.write(")")
			self.write(";\n")
			
		elif ins.type == hlir.ins_types.jcond:
			assert (False)

		elif ins.type == hlir.ins_types.jump:
			assert (False)

		elif ins.type == hlir.ins_types.call:
			self.gen_code_for_call(ins)

		elif ins.type == hlir.ins_types.vmcall:
			self.gen_code_for_vmcall(ins)

		elif ins.type == hlir.ins_types.assertion:
			self.write("assert(")
			self.gen_code(ins.args[0])
			self.write(");\n")

		else:
			print(ins)
			assert (False)
	
	def write_label(self, node):
		should_write = False
		if node in self.goto_nodes:
			should_write = True
		if node in self.indirect_jump_targets:
			should_write = True

		if should_write:
			self.should_indent = False
			self.do_write_label(node)
			self.write(":\n")
	

def generate_code(stats, contract):
	c = CodeGenerator(stats, contract)
	return c.generate_output()
