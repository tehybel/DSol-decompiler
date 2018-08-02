import utils
import tree
import vmcall
from interpreter import Value, UndefinedValue
from numbers import Number
import settings

# TODO: all arithmetic in evaluate() should be done modulo 2**256.

class Expression(tree.Node):
	def __str__(self):
		print(self.__class__)
		raise NotImplementedError()
	def gen_code(self, o):
		print(self)
		raise NotImplementedError()
	def evaluate(self, interp):
		print(self)
		raise NotImplementedError()

class UnusedValue(Expression):
	child_names = []
	def __str__(self):
		return "unused"
	def evaluate(self, interp):
		return UndefinedValue()
	def gen_code(self, o):
		o.write("unused")
	def copy(self):
		return UnusedValue()

### identifiers ###

class Id(Expression):
	pass

class Stack(Id):
	child_names = []
	def __init__(self, offset):
		self.offset = offset
		self.bb = None
	
	def copy(self):
		result = Stack(self.offset)
		result.bb = self.bb
		return result
	
	def __str__(self):
		if self.offset == 0:
			return "stack[sp]"
		elif self.offset > 0:
			return "stack[sp+%d]" % self.offset
		else:
			return "stack[sp%d]" % self.offset
	
	def gen_code(self, o):
		o.write(str(self))
	
	def __eq__(self, other):
		if not isinstance(other, Stack):
			return False
		# we really have to be careful when comparing stack variables, because
		# if they're in different BBs then we can't just compare their
		# offsets. So __eq__ should never be called; we should instead reason
		# about whether they're in the same BB, and if so, compare offsets.
		assert (False)
	def __hash__(self):
		return 0x1111
	
	def evaluate(self, interp):
		return interp.access_stack(self.offset)

class Mem(Id):
	child_names = ["address", "length"]
	def __init__(self, addr, length):
		assert (isinstance(addr, Expression))
		assert (isinstance(length, Expression))
		self.address = addr
		self.length = length
	def copy(self):
		return Mem(self.address.copy(), self.length.copy())
	def __str__(self):
		return "mem(%s, %s)" % (str(self.address), str(self.length))
	def is_free_mem_ptr(self):
		if not isinstance(self.address, Lit) or not isinstance(self.length, Lit):
			return False
		return self.address.literal == 0x40 and self.length.literal == 0x20
	def gen_code(self, o):
		if self.is_free_mem_ptr():
			if settings.simplify_free_mem_ptr:
				return o.write("free_mem_ptr")
		o.write("mem[")
		self.address.gen_code(o)
		o.write(":+")
		self.length.gen_code(o)
		o.write("]")
	def __eq__(self, other):
		if not isinstance(other, Mem):
			return False

		# if this doesn't hold then we simple cannot answer yes/no to whether
		# they are equal, and in that case __eq__ should not have been used,
		# or it'll lead to subtle bugs.
		assert (isinstance(self.address, Lit))
		assert (isinstance(self.length, Lit))
		assert (isinstance(other.address, Lit))
		assert (isinstance(other.length, Lit))

		return self.address == other.address and self.length == other.length
	def __hash__(self):
		return 0x2222
	def evaluate(self, interp):
		addr = self.address.evaluate(interp).num()
		length = self.length.evaluate(interp).num()
		return interp.access_mem(addr, length)

class PureFunctionCall(Expression):
	child_names = ["args"]
	def __init__(self, name, args):
		self.name = name
		self.args = args
	def __str__(self):
		return "%s(%s)" % (self.name, ", ".join(str(a) for a in self.args))
	def gen_code(self, o):
		o.write(self.name)
		o.write("(")
		o.write_comma_separated_exprs(self.args)
		o.write(")")
	def copy(self):
		args = [a.copy() for a in self.args]
		return PureFunctionCall(self.name, args)
	def evaluate(self, interp):
		results = interp.interpret_vmcall(self.name, self.args)
		assert (len(results) == 1)
		return results[0]

class Sequence(Expression):
	child_names = ["expressions"]
	def __init__(self, exprs):
		self.expressions = exprs
	def __str__(self):
		out = "("
		first = True
		for exp in self.expressions:
			if first:
				first = False
			else:
				out += ", "
			out += str(exp)
		out += ")"
		return out
		
	def gen_code(self, o):
		o.write("(")
		first = True
		# TODO: use o.write_comma_separated_exprs here, also other places
		for exp in self.expressions:
			if first:
				first = False
			else:
				o.write(", ")
			exp.gen_code(o)
		o.write(")")
	def evaluate(self, interp):
		out_bytes = []
		for e in self.expressions:
			out_bytes += e.evaluate(interp).bytes()
		return Value(out_bytes)
	
	def copy(self):
		return Sequence([e.copy() for e in self.expressions])

class Storage(Id):
	def __init__(self, addr):
		assert (isinstance(addr, Expression))
		self.address = addr
	def copy(self):
		return Storage(self.address.copy())
	def __str__(self):
		return "storage(%s)" % str(self.address)
	def __eq__(self, other):
		if not isinstance(other, Storage):
			return False

		# if this doesn't hold then we cannot compare the addresses; e.g. they
		# might both be stack[sp+1], but we can't tell if they're the same
		# value.
		assert (isinstance(self.address, Lit))
		assert (isinstance(other.address, Lit))
		return self.address == other.address

	def __hash__(self):
		return 0x3333

	def gen_code(self, o):
		# TODO: this should use a table lookup.
		o.write("storage(")
		self.address.gen_code(o)
		o.write(")")
	def evaluate(self, interp):
		return interp.access_storage(self.address.evaluate(interp).num())
	child_names = ["address"]

class NamedStorageAccess(Id):
	child_names = ["offset"]
	def __init__(self, num, offset):
		assert (isinstance(num, int))
		assert (isinstance(offset, Expression))
		self.num = num
		self.offset = offset
	def copy(self):
		return self.__class__(self.num, self.offset.copy())
	def __eq__(self, other):
		if not isinstance(other, NamedStorageAccess):
			return False
		assert (isinstance(self.offset, Lit))
		assert (isinstance(other.offset, Lit))
		return self.num == other.num and self.offset == other.offset
	def __hash__(self):
		return hash(self.num)
	def __str__(self):
		return "%s%d[%s]" % (self.access_type, self.num, self.offset)
	def gen_code(self, o):
		o.write(self.access_type) # e.g. "mapping" or "array"
		o.write("%d[" % self.num)
		self.offset.gen_code(o)
		o.write("]")

	def evaluate(self, interp):
		return interp.access_storage(self.compute_address(interp))
	
	def compute_address(self, interp):
		raise NotImplementedError()

class MappingAccess(NamedStorageAccess):
	access_type = "mapping"
	def compute_address(self, interp):
		seq = Sequence([self.offset, Lit(self.num)])
		loc = vmcall.vmcalls.sha3
		results = interp.interpret_vmcall(loc, [seq])
		assert (len(results) == 1)
		return results[0].num()
	
class ArrayAccess(NamedStorageAccess):
	access_type = "array"
	def compute_address(self, interp):
		seq = Sequence([Lit(self.num)])
		loc = vmcall.vmcalls.sha3
		results = interp.interpret_vmcall(loc, [seq])
		assert (len(results) == 1)
		return results[0].num() + self.offset.evaluate(interp).num()

# a local variable
class Var(Id):
	def __init__(self):
		self.name = None # assigned later
	def copy(self):
		return self
	def __str__(self):
		if self.name is None:
			# just something unique for now; this is the object's address.
			return "var(%s)" % id(self) 
		else:
			return self.name
	
	def gen_code(self, o):
		o.write(o.lookup_var(self))

	def evaluate(self, interp):
		return interp.lookup_var(self)
	
	child_names = []

class GlobalVar(Id):
	def __init__(self, name):
		assert (isinstance(name, str))
		self.name = name
	
	def __str__(self):
		return self.name
	
	def gen_code(self, o):
		o.write(self.name)
	
	def evaluate(self, interp):
		return interp.lookup_global(self.name)
	
	def copy(self):
		return GlobalVar(self.name)

	child_names = []



### literal ###

class Lit(Expression):
	def __init__(self, n):
		assert (isinstance(n, Number))
		self.literal = n
	def __str__(self):
		return "0x%x" % self.literal
	def gen_code(self, o):
		o.write(str(self))
	def evaluate(self, interp):
		return Value(self.literal)
	child_names = []
	def __eq__(self, other):
		if not isinstance(other, Lit):
			return False
		return self.literal == other.literal
	def __hash__(self):
		return self.literal
	def copy(self):
		return Lit(self.literal)

### binary ops ###

class BinaryOp(Expression):
	symbol = "?" # set in subclasses
	def __init__(self, op1, op2):
		self.operand1 = op1
		self.operand2 = op2

	def copy(self):
		return self.__class__(self.operand1.copy(), self.operand2.copy())
	
	def __str__(self):
		return "(%s %s %s)" % (self.operand1, self.symbol, self.operand2)
	
	def gen_code(self, o):
		o.write("(")
		self.operand1.gen_code(o)
		o.write(" ")
		o.write(self.symbol)
		o.write(" ")
		self.operand2.gen_code(o)
		o.write(")")
	
	child_names = ["operand1", "operand2"]

# this is not a good example of a binary op, but it's convenient to treat it
# as such.
class SignExtend(BinaryOp):
	is_commutative = False
	symbol = "extend"
	def evaluate(self, interp):
		value = self.operand2.evaluate(interp).num()
		nbytes = self.operand1.evaluate(interp).num()
		nbits = 8*(nbytes+1) # +1 since it starts at 0
		return Value(utils.extend(value, nbits))
	
class SGt(BinaryOp):
	is_commutative = False
	symbol = ">"
	def evaluate(self, interp):
		return Value(utils.signed(self.operand1.evaluate(interp).num()) >
					 utils.signed(self.operand2.evaluate(interp).num()))

class Gt(BinaryOp):
	is_commutative = False
	symbol = ">"
	def evaluate(self, interp):
		return Value(self.operand1.evaluate(interp).num() >
					 self.operand2.evaluate(interp).num())

class Lt(BinaryOp):
	is_commutative = False
	symbol = "<"
	def evaluate(self, interp):
		return Value(self.operand1.evaluate(interp).num() <
					 self.operand2.evaluate(interp).num())

class SLt(BinaryOp):
	is_commutative = False
	symbol = "<"
	def evaluate(self, interp):
		return Value(utils.signed(self.operand1.evaluate(interp).num()) <
					 utils.signed(self.operand2.evaluate(interp).num()))

class Div(BinaryOp):
	is_commutative = False
	symbol = "/"
	def evaluate(self, interp):
		return Value(self.operand1.evaluate(interp).num() /
					 self.operand2.evaluate(interp).num())

	def gen_code(self, o):

		return BinaryOp.gen_code(self, o)


class SDiv(BinaryOp):
	is_commutative = False
	symbol = "/"
	def evaluate(self, interp):
		# TODO: account for this in the yellowpaper:
		# "Note the overflow semantic when -2^255 is negated."
		return Value(utils.signed(self.operand1.evaluate(interp).num()) /
					 utils.signed(self.operand2.evaluate(interp).num()))

class And(BinaryOp):
	is_commutative = False
	symbol = "&"
	def evaluate(self, interp):
		return Value(self.operand1.evaluate(interp).num() &
					 self.operand2.evaluate(interp).num())
	
	casts = {
		0xffffffffffffffffffffffffffffffffffffffff: "address",
		0xffffffffffffffffffffffff0000000000000000000000000000000000000000: "remaddrbits",
		0xff: "byte",
	}
	
	def gen_code(self, o):
		# TODO: we put casts here for now, but we should handle this in a
		# better place by detecting types.
		for value, text in self.casts.items():

			if self.operand1 == Lit(value):
				o.write(text)
				o.write("(")
				self.operand2.gen_code(o)
				o.write(")")
				return

			if self.operand2 == Lit(value):
				o.write(text)
				o.write("(")
				self.operand1.gen_code(o)
				o.write(")")
				return

		return BinaryOp.gen_code(self, o)

class Or(BinaryOp):
	is_commutative = True
	symbol = "|"
	def evaluate(self, interp):
		return Value(self.operand1.evaluate(interp).num() |
					 self.operand2.evaluate(interp).num())

class Sub(BinaryOp):
	is_commutative = False
	symbol = "-"
	def evaluate(self, interp):
		return Value(self.operand1.evaluate(interp).num() -
					 self.operand2.evaluate(interp).num())

class Mul(BinaryOp):
	is_commutative = True
	symbol = "*"
	def evaluate(self, interp):
		return Value(self.operand1.evaluate(interp).num() *
					 self.operand2.evaluate(interp).num())

class Add(BinaryOp):
	is_commutative = True
	symbol = "+"
	def evaluate(self, interp):
		return Value(self.operand1.evaluate(interp).num() +
					 self.operand2.evaluate(interp).num())
	
class Xor(BinaryOp):
	is_commutative = True
	symbol = "^"
	def evaluate(self, interp):
		return Value(self.operand1.evaluate(interp).num() ^
					 self.operand2.evaluate(interp).num())

class Eq(BinaryOp):
	is_commutative = True
	symbol = "=="
	def evaluate(self, interp):
		a = self.operand1.evaluate(interp).num()
		b = self.operand2.evaluate(interp).num()
		return Value(a == b)

class Exp(BinaryOp):
	is_commutative = False
	symbol = "**"
	def evaluate(self, interp):
		return Value(self.operand1.evaluate(interp).num() **
					 self.operand2.evaluate(interp).num())

class Mod(BinaryOp):
	is_commutative = False
	symbol = "%"
	def evaluate(self, interp):
		return Value(self.operand1.evaluate(interp).num() %
					 self.operand2.evaluate(interp).num())

### unary ops ###

class UnaryOp(Expression):
	symbol = "?" # set properly in subclasses
	def __init__(self, op):
		self.operand = op
	
	def copy(self):
		return self.__class__(self.operand.copy())
	
	def __str__(self):
		return "%s(%s)" % (self.symbol, self.operand)
	
	def gen_code(self, o):
		o.write(self.symbol)
		o.write("(")
		self.operand.gen_code(o)
		o.write(")")
	
	child_names = ["operand"]

# logical negation
class Not(UnaryOp):
	symbol = "!"
	def evaluate(self, interp):
		result = self.operand.evaluate(interp).num()
		if result == 0:
			return Value(1)
		else:
			return Value(0)
	
	def gen_code(self, o):
		if not isinstance(self.operand, Eq):
			return UnaryOp.gen_code(self, o)
		self.operand.operand1.gen_code(o)
		o.write(" != ")
		self.operand.operand2.gen_code(o)
		
			

# bitwise negation
class Neg(UnaryOp):
	symbol = "~"
	def evaluate(self, interp):
		return Value(utils.neg(self.operand.evaluate(interp).num(), 256))
