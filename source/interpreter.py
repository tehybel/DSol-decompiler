import expr
import hlir
import utils
import vmcall
import contract
import absyn
from numbers import Number

default_context = {
	"msg.sender": 0xdeadbeef,
	"msg.value": 0,
	"block.number": 1234,

}

STEP_LIMIT = 2000

class HaltReturnException(Exception):
	pass

class RevertException(Exception):
	pass

class RetException(Exception):
	def __init__(self, args):
		self.args = args

class BreakException(Exception):
	pass

class ContinueException(Exception):
	pass

class OutOfGasException(Exception):
	pass

class AssertionFailureException(Exception):
	pass

class InvalidJumpTargetException(Exception):
	pass


# the interpreter works on Values; a Value is a list of bytes. If a Value is
# 32 bytes long, it can be interpreted as an integer and have arithmetic
# performed upon it.
class Value:
	def __init__(self, v):
		if isinstance(v, list):
			self.__bytes = [item for item in v]
		else:
			assert (isinstance(v, Number))
			self.__bytes = utils.pack(v, 0x20)
	
	def num(self):
		assert (len(self.__bytes) == 0x20)
		return utils.unpack(self.__bytes)
	
	def bytes(self):
		return [b for b in self.__bytes]
	
	def __eq__(self, other):
		if isinstance(other, Number):
			return self.num() == other
		
		assert (False)

class UndefinedValue(Value):
	def __init__(self):
		self.__bytes = None

class Interpreter:
	def __init__(self, contract):
		self.contract = contract
		self.storage = {}
		self.reset()
		self.step_limit = None
	
	def reset(self):
		self.sp = 0
		self.steps = 0
		self.cur_func = self.contract.functions[0]
		self.cur_node = self.cur_func.header_node
		self.loops = [] # a stack containing the nesting of loops we're inside
		self.result = None
		self.mem = []
		self.local_vars = {}
		self.stack = {}
	
	def lookup_global(self, g):
		if g in default_context:
			return Value(default_context[g])

		if g == "msg.data.length":
			return Value(len(self.calldata))

		else:
			print(g)
			assert (False)
	
	def lookup_var(self, v):
		try:
			result = self.local_vars[v]
			return result
		except KeyError:
			# this happens sometimes, and it's actually not a problem; it
			# could look like: "x = stack[sp+3]" where stack[sp+3] isn't yet
			# defined, but then later there'll be "x = y" so the former
			# assignment would have been eliminated with more optimizations.
			# It's never used either way.
			return UndefinedValue()

	def access_storage(self, addr):
		assert (isinstance(addr, Number))
		if addr not in self.storage:
			self.storage[addr] = Value(0)
		return self.storage[addr]
	
	def access_stack(self, offset):
		assert (self.sp >= 0)
		try:
			return self.stack[self.sp + offset]
		except KeyError:
			return UndefinedValue()
	
	def ensure_mem_size(self, size):
		assert (size <= 0x100000) # just so my machine doesn't blow up
		assert (isinstance(size, int))
		while len(self.mem) <= size:
			self.mem.append(0)
	
	def access_mem(self, addr, length):
		# int, not Number, because otherwise it's unrealistically big
		assert (isinstance(addr, int))
		assert (isinstance(length, int)) 

		self.ensure_mem_size(addr + length)
		return Value(self.mem[addr:addr + length])
	
	def assign(self, var, result):
		assert (isinstance(result, Value))

		if isinstance(var, expr.Mem):
			addr = var.address.evaluate(self).num()
			length = var.length.evaluate(self).num()

			vs = result.bytes()
			assert (len(vs) == length)
			self.ensure_mem_size(addr + length)
			for i in range(length):
				self.mem[addr+i] = vs[i]

		elif isinstance(var, expr.Var):
			self.local_vars[var] = result

		elif isinstance(var, expr.Stack):
			offset = self.sp + var.offset
			assert (offset >= 0)
			self.stack[offset] = result

		elif isinstance(var, expr.Storage):
			self.storage[var.address.evaluate(self).num()] = result

		elif isinstance(var, expr.NamedStorageAccess):
			addr = var.compute_address(self)
			self.storage[addr] = result

		else:
			assert(False)

	def load_calldata(self, offset):
		while len(self.calldata) <= offset + 0x20:
			self.calldata.append(0)
		return Value(self.calldata[offset:offset+0x20])
	
	def interpret_vmcall(self, loc, args):
		if loc == vmcall.vmcalls.calldataload:
			assert (len(args) == 1)
			offset = args[0].evaluate(self).num()
			return [self.load_calldata(offset)]

		elif loc == vmcall.vmcalls.revert:
			raise RevertException()

		elif loc == vmcall.vmcalls.haltreturn:
			assert (len(args) == 1)
			self.result = args[0].evaluate(self)
			assert (isinstance(self.result, Value))
			raise HaltReturnException()
		
		elif loc == vmcall.vmcalls.stop:
			self.result = Value([])
			raise HaltReturnException()

		elif loc == vmcall.vmcalls.log:
			# TODO: implement logging.
			return []

		elif loc == vmcall.vmcalls.sha3:
			assert (len(args) == 1)
			text = args[0].evaluate(self).bytes()
			text = "".join(chr(c) for c in text)
			result = [Value(utils.sha3(text))]
			return result

		elif loc == vmcall.vmcalls.coderead:
			assert (len(args) == 2)
			offset = args[0].evaluate(self).num()
			length = args[1].evaluate(self).num()

			# when creating a contract, the bytes used for creation are
			# appended to the bytecode..
			code  = [ord(c) for c in self.contract.bytecode]
			code += self.calldata

			assert (len(code) >= offset + length)
			return [Value(code[offset:offset+length])]

		elif loc == vmcall.vmcalls.calldataread:
			offset = args[0].evaluate(self).num()
			length = args[1].evaluate(self).num()
			assert (len(self.calldata) >= offset + length)
			return [Value(self.calldata[offset:offset+length])]

		# "Get the size of active memory in bytes."
		elif loc == vmcall.vmcalls.msize:
			return [Value(len(self.mem))]

		else:
			print(loc)
			assert (False)
	
	def step(self):
		self.steps += 1
		# TODO move this 'or' to constructor
		limit = self.step_limit or STEP_LIMIT
		if self.steps >= limit:
			raise OutOfGasException()
	
	def interpret_instruction(self, ins):
		#print("-----------------")
		#print(ins)
		#print(self.stack)
		#print(self.sp)
		assert (self.sp >= 0)

		if ins.type == hlir.ins_types.assign:
			self.assign(ins.results[0], ins.args[0].evaluate(self))
		
		elif ins.type == hlir.ins_types.vmcall:
			values = self.interpret_vmcall(ins.loc, ins.args)
			assert (len(ins.results) == len(values))
			for r, v in zip(ins.results, values):
				self.assign(r, v)

		elif ins.type == hlir.ins_types.call:
			# grab args
			f = ins.loc
			args = [arg.evaluate(self) for arg in ins.args]

			# these get trashed; restore them after the call
			old_vars = self.local_vars
			old_func = self.cur_func
			old_node = self.cur_node
			old_loops = self.loops

			self.loops = []
			self.local_vars = {}
			self.cur_func = f
			self.cur_node = self.cur_func.header_node

			# init params
			if f.external:
				for i, param in enumerate(f.params):
					offset = 4 + i*0x20
					value = self.load_calldata(offset)
					self.assign(param, value)
			else:
				assert (len(args) == len(f.params))
				for arg, param in zip(args, f.params):
					self.assign(param, arg)
			
			try:
				self.interpret()
				assert (False)
			except RetException, exc:
				results = exc.args

			self.loops = old_loops
			self.local_vars = old_vars
			self.cur_func = old_func
			self.cur_node = old_node

			# define return values
			assert (len(results) == len(ins.results))
			for v, e in zip(ins.results, results):
				self.assign(v, e)

		elif ins.type == hlir.ins_types.ret:
			args = [a.evaluate(self) for a in ins.args]
			raise RetException(args)

		elif ins.type == hlir.ins_types.assertion:
			result = ins.args[0].evaluate(self).num()
			if result == 0:
				raise AssertionFailureException(ins)

		elif ins.type == hlir.ins_types.jcond:
			cond = ins.args[0]
			if cond.evaluate(self) == 0:
				dest = self.cur_node.next_bb
			else:
				addr = ins.loc.evaluate(self).num()
				dest = self.get_node_by_addr(addr)
			self.jump(self.cur_node, dest)

		elif ins.type == hlir.ins_types.jump:
			addr = ins.loc.evaluate(self).num()
			dest = self.get_node_by_addr(addr)
			self.jump(self.cur_node, dest)

		else:
			print(ins)
			assert(False)
	
	def jump(self, from_node, to_node):
		if to_node is None:
			self.cur_node = None
			return

		if isinstance(from_node, hlir.HLIRNode):
			assert (isinstance(to_node, hlir.HLIRNode))
		else:
			assert (isinstance(to_node, absyn.Node))
		assert (isinstance(from_node, (hlir.HLIRNode, absyn.Node)))
		assert (isinstance(to_node, (hlir.HLIRNode, absyn.Node)))
		assert (to_node in from_node.get_successors())
		assert (self.cur_node == from_node)
		self.cur_node = to_node

	def call_ctor(self, deployment_contract, args):
		assert (self.contract.__class__ == deployment_contract.__class__)
		old_contract = self.contract
		self.contract = deployment_contract
		self.call(args)
		self.contract = old_contract

	def call(self, args):
		assert (isinstance(args, list))
		self.calldata = args
		self.reset()
		try:
			self.interpret()
		except HaltReturnException:
			pass
		return self.result


class HLIRInterpreter(Interpreter):
	def __init__(self, contract):
		Interpreter.__init__(self, contract)

	def interpret(self):
		while True:
			node = self.cur_node
			assert (isinstance(node, hlir.HLIRNode))
			self.step()

			self.sp += node.sp_delta
			for ins in node.get_instructions():
				self.interpret_instruction(ins)

			self.interpret_instruction(node.terminator)

	def get_node_by_addr(self, addr):
		for node in self.cur_func.header_node.reachable_nodes():
			if isinstance(node, hlir.BasicBlock) and node.address == addr:
				return node
		raise InvalidJumpTargetException()
	

class ASTInterpreter(Interpreter):
	def __init__(self, contract):
		Interpreter.__init__(self, contract)
	
	def interpret(self):
		while True:
			node = self.cur_node
			if not node:
				return
			assert (isinstance(node, absyn.Node))
			self.step()

			if isinstance(node, absyn.Sequence):
				self.sp += node.sp_delta
				for ins in node.instructions:
					self.interpret_instruction(ins)
				assert (node.terminator is None)
				if len(node.get_successors()) == 1:
					self.cur_node = next(iter(node.get_successors()))
				else:
					assert (len(node.get_successors()) == 0)
					return

			elif isinstance(node, absyn.IfElse):
				if node.exp.evaluate(self).num() != 0:
					self.jump(node, node.true_node)
					self.interpret()
				else:
					self.jump(node, node.false_node)
					self.interpret()

				self.cur_node = node.follow

			elif isinstance(node, absyn.IndirectJump):
				addr = node.dest.evaluate(self).num()
				dest = self.get_node_by_addr(addr)
				self.jump(node, dest)

			elif isinstance(node, absyn.Loop):
				while True:
					if node.exp.evaluate(self).num() == 0:
						break
					try:
						self.cur_node = node.header_node
						self.interpret()
					except ContinueException:
						continue
					except BreakException:
						break
				self.cur_node = node.follow_node

			elif isinstance(node, absyn.Continue):
				raise ContinueException()

			elif isinstance(node, absyn.Break):
				raise BreakException()

			else:
				print("Unhandled node type in interpret: %s" % node.__class__)
				assert (False)

	def get_node_by_addr(self, addr):
		for node in self.cur_func.nodes():
			if isinstance(node, absyn.Sequence) and node.address == addr:
				return node
		raise InvalidJumpTargetException()

def make_interpreter(node):
	if isinstance(node, contract.Contract):
		return HLIRInterpreter(node)
	
	elif isinstance(node, absyn.Contract):
		return ASTInterpreter(node)
	
	else:
		assert (False)
