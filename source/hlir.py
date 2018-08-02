import expr
import outputformat
import function
import utils
import draw
import settings

######### HLIR node types #########

class HLIRNode(draw.Node):
	def __init__(self):
		self.__successors = set()
		self.__predecessors = set()
		self.address = None
		self.function = None

	def replace_successor(self, old, new):
		self.add_successor(new)
		self.remove_successor(old)

	def add_successor(self, succ):
		self.__successors.add(succ)
		succ.__predecessors.add(self)
		if self.function:
			self.function.invalidate_cached_nodes()
	
	def successor(self):
		assert (len(self.__successors) == 1)
		return next(iter(self.__successors))
	
	def remove_successor(self, succ):
		self.__successors.remove(succ)
		succ.__predecessors.remove(self)
		if self.function:
			self.function.invalidate_cached_nodes()
	
	def get_successors(self):
		return set(self.__successors)
	
	def get_predecessors(self):
		return set(self.__predecessors)

class BasicBlock(HLIRNode):
	def __init__(self, addr, instrs, sp_delta):
		HLIRNode.__init__(self)
		self.__instructions = instrs
		self.address = addr
		self.sp_delta = sp_delta

		# variables below are filled out later
		self.next_bb = None # block with physically next higher address
		self.function = None
		self.terminator = None

	def remove_instruction(self, ins):
		self.__instructions.remove(ins)
	
	def insert_instruction(self, ins, offset=0):
		self.__instructions.insert(offset, ins)
	
	def replace_instruction(self, old, new):
		index = self.__instructions.index(old)
		self.remove_instruction(old)
		self.insert_instruction(new, index)
	
	def copy(self):
		instrs = [ins.copy() for ins in self.__instructions]
		result = BasicBlock(self.address, instrs, self.sp_delta)
		result.function = self.function
		result.terminator = self.terminator.copy()
		for s in self.get_successors():
			result.add_successor(s)
		return result
	
	def get_instructions(self):
		return list(self.__instructions)
	
	def gen_code(self, o):
		for ins in self.get_instructions() + [self.terminator]:
			o.gen_code_for_instruction(ins)

	def __str__(self):	
		if settings.simplify_bbs:
			return "0x%x" % self.address

		out = "Node 0x%x: BasicBlock " % id(self)
		if self.address is not None:
			out += "addr: 0x%x " % self.address
		else:
			out += "addr: None "
		out += "{\n"
		out += "\tsp += %d\n" % self.sp_delta
		for ins in self.get_instructions() + [self.terminator]:
			if not settings.show_unusedvalue_assignments:
				if utils.is_unused(ins):
					continue
			out += "\t" + str(ins) + "\n"
		out += "}\n"
		out += "succs = [%s]\n" % (
			",".join(hex(id(s)) for s in self.get_successors()),
		)
		out += "preds = [%s]\n" % (
			",".join(hex(id(s)) for s in self.get_predecessors()),
		)
		return out
	
	def append_instruction(self, ins):
		self.__instructions.append(ins)
	
	def adjust_sp_delta(self, delta):
		self.sp_delta += delta
		adjusted = set()
		def fix(e):
			if isinstance(e, expr.Stack) and id(e) not in adjusted:
				# this should go in the other direction
				e.offset -= delta

				# we use id(e) because if we just used e then two different
				# stack variables with the same offset would compare equal
				# and so only one would get adjusted.
				adjusted.add(id(e))
			return e

		for ins in self.get_instructions():
			utils.visit_and_modify_instruction(ins, fix)
	
	def merge(self, succ):
		assert (self.terminator.type == ins_types.jump)
		assert (self.terminator.loc.literal == succ.address)
		self.terminator = None
		self.adjust_sp_delta(succ.sp_delta)
		for ins in succ.get_instructions():
			self.append_instruction(ins)
		self.terminator = succ.terminator

		self.next_bb = succ.next_bb

		for ss in list(succ.get_successors()):
			self.add_successor(ss)
			succ.remove_successor(ss)
		self.remove_successor(succ)

		assert (len(succ.get_successors()) == 0)
		assert (len(succ.get_predecessors()) == 0)


###################################

# the types of HLIR instructions
class ins_types:
	assign = "assign"
	jcond = "jcond"
	jump = "jump"
	call = "call"
	vmcall = "vmcall"
	ret = "ret"
	assertion = "assertion"

class Instruction:
	def __init__(self, type, results, args, location):
		assert (isinstance(results, list))
		assert (isinstance(args, list))
		for exp in results + args:
			assert (isinstance(exp, expr.Expression))
		if location is not None:
			assert (isinstance(location, expr.Expression) or
					isinstance(location, str) or # TODO: get rid of this 'str'..
					isinstance(location, function.Function)) 

		self.type = type
		self.results = results
		self.args = args
		self.loc = location
	
	def __str__(self):
		return outputformat.format_instruction(self)
	
	def copy(self):
		if isinstance(self.loc, expr.Expression):
			loc = self.loc.copy()
		else:
			loc = self.loc
		
		results = [r.copy() for r in self.results]
		args = [a.copy() for a in self.args]
		return Instruction(self.type, results, args, loc)

### convenience functions to create instructions ###

def make_assign(var, exp):
	return Instruction(ins_types.assign, [var], [exp], None)

def make_jcond(dest, value):
	return Instruction(ins_types.jcond, [], [value], dest)

def make_jump(dest):
	return Instruction(ins_types.jump, [], [], dest)

def make_call(loc, args, results):
	return Instruction(ins_types.call, results, args, loc)

def make_vmcall(funcname, args, results):
	return Instruction(ins_types.vmcall, results, args, funcname)

def make_return(values, loc):
	return Instruction(ins_types.ret, [], values, loc)

def make_assertion(exp):
	return Instruction(ins_types.assertion, [], [exp], None)

