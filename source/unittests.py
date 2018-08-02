import decompiler
import interpreter
import sys
import random
import utils
import struct
from contract import Contract
import absyn
import os

JSON_PATH = "./tests/build/contracts/"
BYTECODE_PATH = "./tests/bytecode/"

class UnitTestFailedException(Exception):
	pass

def feedback(status):
	if status:
		sys.stdout.write("\033[92m") # green
		sys.stdout.write("+")
		sys.stdout.write("\033[0m") # no color
	else:
		sys.stdout.write("\033[91m") # red
		sys.stdout.write("-")
		sys.stdout.write("\033[0m") # no color
	sys.stdout.flush()

class Tester:
	def __init__(self, filename, ctor_args, step_limit=None):
		if ".json" in filename:
			self.filename = JSON_PATH + filename
			self.bytecode, self.deployed_bytecode = (
				utils.parse_json(self.filename)
			)
			self.is_deployment_contract = True

		elif ".bc" in filename:
			self.filename = BYTECODE_PATH + filename
			contents = utils.read_file_contents(self.filename)
			self.deployed_bytecode = None
			self.bytecode = utils.decode_bytecode(contents)
			self.is_deployment_contract = False

		else:
			assert (False)

		self.ctor_args = ctor_args
		self.step_limit = step_limit
		self.deployment_contract = None
		self.deployment_ast = None

		self.tests = []
		self.except_tests = []

		self.previous_result_of_ctor_on_storage = None
	
	def add_test(self, args, results, raw=False):
		if raw:
			expected = results
		else:
			expected = []
			for er in results:
				expected += utils.pack(er, 0x20)

		args = self.prepare_args(args)
		self.tests.append((args, expected))
	
	def prepare_args(self, args):
		raw = []
		raw += utils.pack(args[0], 4)
		for a in args[1:]:
			raw += utils.pack(a, 32)
		return raw
	
	def add_except_test(self, args, exceptions):
		args = self.prepare_args(args)
		self.except_tests.append((args, exceptions))
	
	def ctor_sanity_checks(self, interp, result):
		# calling the constructor should yield the deployed bytecode
		assert (result.bytes() == [ord(c) for c in self.deployed_bytecode])
		feedback(True)

		# the constructor should have the same effect on storage every time
		stor = {k: v.bytes() for k, v in interp.storage.items()}
		if self.previous_result_of_ctor_on_storage is None:	
			self.previous_result_of_ctor_on_storage = stor
		else:
			assert (stor == self.previous_result_of_ctor_on_storage)
	
	def do_run_tests(self, contract):
		interp = interpreter.make_interpreter(contract)

		if self.is_deployment_contract:
			result = interp.call(self.ctor_args)
			self.ctor_sanity_checks(interp, result)
			return

		# initialize storage etc. by calling the constructor
		if isinstance(contract, Contract) and self.deployment_contract:
			interp.call_ctor(self.deployment_contract, self.ctor_args)
		if isinstance(contract, absyn.Contract) and self.deployment_ast:
			interp.call_ctor(self.deployment_ast, self.ctor_args)


		if self.step_limit:
			interp.step_limit = self.step_limit

		for args, expected in self.tests:
			value = interp.call(args)
			actual = value.bytes()

			if actual == expected:
				feedback(True)
			else:
				feedback(False)
				print("Expected: %s" % str(expected))
				print("Got: %s" % str(actual))
				raise UnitTestFailedException()

		for args, expected_exceptions in self.except_tests:
			try:
				interp.call(args)
			except Exception, e:
				if e.__class__ in expected_exceptions:
					feedback(True)
				else:
					feedback(False)
					print("Got a wrong exception type:")
					print(e.__class__)
					raise UnitTestFailedException()
	
	def run(self):
		sys.stdout.write(self.filename + ": ")
		sys.stdout.flush()

		d = decompiler.Decompiler()
		d.set_optimization_hook(self.do_run_tests)

		contract, ast, code = d.decompile_raw(self.bytecode)
		feedback(True) # it decompiled OK

		if self.is_deployment_contract:
			self.is_deployment_contract = False
			self.deployment_contract = contract
			self.deployment_ast = ast
			contract, ast, code = d.decompile_raw(self.deployed_bytecode)
			feedback(True) # it decompiled OK
			sys.stdout.write(" (%d functions)" % len(contract.functions))

		print("")

def pack_string_ref(s):
	vs = []
	vs += interpreter.Value(0x20).bytes() # mem ref: next word.
	vs += interpreter.Value(len(s)).bytes() # string length
	for c in s:
		vs.append(ord(c))
	while len(vs) % 0x20 != 0:
		vs.append(0)
	return vs

# for printing our unit tests so we can use it in our report..
#total_num_tests = 0
#class Tester:
#	def __init__(self, contract_name, _, step_limit=None):
#		self.cn = contract_name
#		self.num_tests = 0
#	def new_test(self):
#		global total_num_tests
#		total_num_tests += 1
#		self.num_tests += 1
#	def add_test(self, _, __, raw=None):
#		self.new_test()
#	def add_except_test(self, _, __):
#		self.new_test()
#	def run(self):
#		if self.num_tests != 0:
#			print("%s & %d & description \\\\" % (self.cn, self.num_tests))
		

def run_all_tests():

	tester = Tester("Minimal.json", [])
	tester.add_test([0xc2985578], [0x123])
	tester.add_except_test([0xdeadc0de], 
						   [interpreter.RevertException,
						    interpreter.AssertionFailureException])
	tester.run()

	Tester("eval1.bc", []).run()
	Tester("eval2.bc", []).run()
	Tester("eval3.bc", []).run()

	tester = Tester("ArgOrder.json", [])
	tester.add_test([0x13d1aa2e, 1, 2], [2, 6])
	tester.run()

	tester = Tester("Multicall.json", [])
	tester.add_test([0xb3de648b, 0], [30])
	tester.add_test([0xb3de648b, 1], [40])
	tester.add_test([0xb3de648b, 2], [50])
	tester.add_test([0xb3de648b, 3], [60])
	tester.add_test([0xcb97492a, 0], [1])
	tester.add_test([0xcb97492a, 1], [15])
	tester.add_test([0xcb97492a, 2], [29])
	tester.add_test([0xcb97492a, 3], [43])
	tester.run()

	# TODO re-enable (and update to new values)
	#tester = Tester("SmallExample.json", [])
	#tester.add_test([0x8a9d0e05, 0], [0])
	#tester.add_test([0x8a9d0e05, 1], [2])
	#tester.add_test([0x8a9d0e05, 2], [4])
	#tester.run()

	tester = Tester("Multiargs.json", [])
	tester.add_test([0xbf06dbf1, 0x1, 0x2, 0x3], [0x1*0x2*0x3*0x11])
	tester.run()
	
	tester = Tester("Multiret.json", [])
	tester.add_test([0xb3de648b, 0x1], [0x1*0x11, 0x1*0x22])
	tester.add_test([0xb3de648b, 0x2], [0x2*0x11, 0x2*0x22])
	tester.add_test([0xb3de648b, 0x0], [0, 0])
	tester.run()

	tester = Tester("FourSimple.json", [])
	tester.add_test([0x6482e626, 0], [0]) # d
	tester.add_test([0x6482e626, 1], [1]) # d
	tester.add_test([0xc3da42b8], [0x11*0x22, 1])
	tester.run()

	tester = Tester("Mapping.json", [])
	tester.add_test([0x9507d39a, 0], [0])
	tester.add_test([0x2f30c6f6, 0, 0xc0ffee], []) # set m[0]=n[0]=0xc0ffee
	tester.add_test([0x9507d39a, 0], [0xc0ffee])
	tester.add_test([0x9507d39a, 1], [0])
	tester.add_test([0x2f30c6f6, 0, 0xdedede], [])
	tester.add_test([0x9507d39a, 0], [0xdedede])
	tester.add_test([0x2f30c6f6, 101, 0xfff], [])
	tester.add_test([0x9507d39a, 101], [0xfff])
	tester.run()

	# 0x76febb7e is the getter, 0xcf0d6774 is the setter
	tester = Tester("Array.json", [])
	tester.add_test([0x76febb7e, 9], [0])
	tester.add_test([0x76febb7e, 0], [0])
	tester.add_except_test([0x76febb7e, 10], 
						   [interpreter.RevertException,
						    interpreter.AssertionFailureException])
	tester.add_test([0x76febb7e, 1], [0])
	tester.add_test([0xcf0d6774, 123], [])
	tester.add_test([0x76febb7e, 0], [123])
	tester.add_test([0xcf0d6774, 321], [])
	tester.add_test([0x76febb7e, 0], [123])
	tester.add_test([0x76febb7e, 1], [321])
	tester.run() 

	tester = Tester("String.json", [])
	tester.add_test([0x1c008df9, 1], pack_string_ref("one"), raw=True)
	tester.add_test([0x1c008df9, 2], pack_string_ref("two"), raw=True)
	tester.add_test([0x1c008df9, 3], pack_string_ref("foo"), raw=True)
	tester.add_test(
		[
			0xbe161a2a, 
			1,  # x
			0x60,  # memref: s. Why not 0x64? No clue.
			0xa0,  # memref: r

			# s:
			1, # length
			0x41 << (256-8), # "A"

			# r:
			1, # length
			0x42 << (256-8), # "B"
		], 
		pack_string_ref("A"), 
		raw=True
	)
	tester.add_test(
		[
			0xbe161a2a, 
			1,  # x
			0x60,  # memref: s. Why not 0x64? No clue.
			0xa0,  # memref: r

			# s:
			1, # length
			0x42 << (256-8), # "A"

			# r:
			1, # length
			0x42 << (256-8), # "B"
		], 
		pack_string_ref("[::]URL:;._.=//**-+thisisAstringThatContaINsManyInvalidOPC0des!![]/\\()##%&/(-<-,"), 
		raw=True
	)
	tester.run()

	tester = Tester("Endless.json", [])
	tester.add_test([0x4c970b2f, 0x11], [368])
	tester.add_test([0x4c970b2f, 0x33], [464])
	tester.add_test([0x4c970b2f, 0x66], [63240])
	tester.add_test([0x4c970b2f, 0x77], [589])
	tester.add_except_test([0x4c970b2f, 0], [interpreter.OutOfGasException])
	tester.run()

	tester = Tester("Loop.json", [])
	tester.add_except_test([0xc2985578], [interpreter.OutOfGasException])
	tester.run()

	tester = Tester("NestedLoops.json", [])
	tester.add_test([0xc2985578], [1920])
	tester.run()

	tester = Tester("PostTestedLoop.json", [])
	tester.add_test([0x4c970b2f, 1], [307])
	tester.add_test([0x4c970b2f, 2], [308])
	tester.add_test([0x4c970b2f, 0x23], [307])
	tester.add_test([0x4c970b2f, 0x24], [291])
	tester.run()

	tester = Tester("SmallTypes.json", [])
	tester.add_test([0x1c008df9, 0], [0])
	tester.add_test([0x1c008df9, 3], [9])
	tester.add_test([0x1c008df9, -1], [0])
	tester.add_test([0x1c008df9, 50], [-106])
	tester.run()

	tester = Tester("SmallTypes2.json", [])
	tester.add_test([0x7877b803, 1], [0x11])
	tester.add_test([0x7877b803, 50], [-106])
	tester.run()

	tester = Tester("GT.json", [])
	tester.add_test([0xb3de648b, 0x12], [0x44])
	tester.add_test([0xb3de648b, 0x11], [0x11])
	tester.run()

	tester = Tester("Log.json", [])
	tester.add_test([0x26121ff0], [])
	tester.run()

	tester = Tester("Neg.json", [])
	tester.add_test([0xb3de648b, (2**256)-1], [0])
	tester.add_test([0xb3de648b, 0], [-1])
	tester.add_test([0xb3de648b, 1], [-2])
	tester.run()

	tester = Tester("Storage.json", [])
	tester.add_test([0xb3de648b, 0x123], [0x123])
	tester.add_test([0xb3de648b, 1], [1])
	tester.add_test([0xb3de648b, 0], [0x1234]) # note: this changes storage
	tester.add_test([0xb3de648b, 0], [0])
	tester.add_test([0xb3de648b, 1], [0x1234])
	tester.run()

	tester = Tester("NonCom.json", [])
	tester.add_test([0x29688a80, 2], [2]) # &2
	tester.add_test([0x29688a80, 1], [0]) # &2
	tester.add_test([0x29688a80, 0], [0]) # &2
	tester.add_test([0x29688a80, 3], [2]) # &2
	tester.add_test([0x7ece3246, 3], [9]) # **2
	tester.add_test([0x7ece3246, 2], [4]) # **2
	tester.add_test([0xb3de648b, 2], [0]) # /3
	tester.add_test([0xb3de648b, 3], [1]) # /3
	tester.add_test([0xb3de648b, 5], [1]) # /3
	tester.add_test([0xb3de648b, 6], [2]) # /3
	tester.add_test([0xcb97492a, 0], [0]) # %3
	tester.add_test([0xcb97492a, 1], [1]) # %3
	tester.add_test([0xcb97492a, 2], [2]) # %3
	tester.add_test([0xcb97492a, 3], [0]) # %3
	tester.add_test([0xe420264a, 0xff], [0xee]) # &0xee
	tester.add_test([0xe420264a, 0x12], [0x02]) # &0xee
	tester.add_test([0xe420264a, 0x32], [0x22]) # &0xee
	tester.run()

	tester = Tester("TailCall.json", [])
	tester.add_test([0xb3de648b, 0], [4])
	tester.add_test([0xb3de648b, 1], [6])
	tester.add_test([0xb3de648b, 2], [8])
	tester.add_test([0xcb97492a, 0], [3])
	tester.add_test([0xcb97492a, 1], [4])
	tester.run()

	tester = Tester("NestedIfElse.json", [])
	tester.add_test([0x13d1aa2e, 1, 1], [2])
	tester.add_test([0x13d1aa2e, 1, 2], [3])
	tester.add_test([0x13d1aa2e, 2, 1], [4])
	tester.add_test([0x13d1aa2e, 2, 2], [5])
	tester.run()

	tester = Tester("IfElseSame.json", [])
	tester.add_test([0xb3de648b, 0], [2])
	tester.add_test([0xb3de648b, 1], [1])
	tester.add_test([0xb3de648b, 2], [2])
	tester.run()

	tester = Tester("TryToBreak.json", [], step_limit=300)
	tester.add_test([0x29688a80, 3], [15])
	tester.add_test([0x29688a80, 0], [2])
	tester.add_test([0x29688a80, 4], [12])
	tester.add_test([0x443ddba2, 42], [1])
	tester.add_test([0x443ddba2, 43], [2])
	tester.add_test([0x54bb1361, 0], [12])
	tester.add_test([0x54bb1361, 1], [3])
	tester.add_test([0x54bb1361, 2], [4])
	tester.add_test([0x54bb1361, 3], [6])
	tester.add_test([0x54bb1361, 4], [8])
	tester.add_test([0x54bb1361, 5], [12])
	tester.add_test([0xb582ec5f], [])
	tester.add_test([0xcb97492a, 0], [0])
	tester.add_test([0xcb97492a, 2], [2])
	tester.add_test([0xcb97492a, 6], [6])
	tester.add_except_test([0xcb97492a, 1], [interpreter.OutOfGasException])
	tester.add_except_test([0xcb97492a, 4], [interpreter.OutOfGasException])
	tester.add_except_test([0xcb97492a, 8], [interpreter.OutOfGasException])
	tester.add_test([0xe420264a, 0], [-8])
	tester.add_test([0xe420264a, 1], [12])
	tester.add_test([0xe420264a, 2], [34])
	tester.add_test([0xe420264a, 3], [78])
	tester.add_test([0xe420264a, 4], [-8])
	tester.run()

	tester = Tester("BlackjackTipJar.json", [])
	# TODO add tests.
	tester.run()

	Tester("mystery.bc", []).run()
	Tester("Bytes.json", []).run()
	Tester("Struct.json", []).run()

	#Tester("etherscan1.bc", []).run()
	Tester("etherscan2.bc", []).run()
	Tester("misc.bc", []).run()

	#tester = Tester("Exchange.json", 
	#	utils.pack(0x34767f3c519f361c5ecf46ebfc08981c629d381, 32))
	#tester.run()


	######### Slow tests below #######

	#Tester("Oraclize.json", []).run()
	#Tester("Wallet.json", []).run()
	#Tester("contracts/kittycore.bc").run() # takes ~5 minutes...
	#Tester("contracts/dice5.bc").run() # takes ~5 minutes...

	
def run_tests():

	print("Running unit tests")
	run_all_tests()

	print("All unit tests pass!\n")


if __name__ == "__main__":
	run_all_tests()
	print("Total & %d & " % total_num_tests)
