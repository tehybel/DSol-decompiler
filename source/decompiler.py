import middleend
import parser
import utils
import llir
import ll2hl
import hlir
import codegen
import vmcall
import expr
import dataflow
import cfa
import astconverter
import log
import readability

class Decompiler:

	def __init__(self):
		self.__unit_test_hook = None
		self.orig_bytecode = None
		self.constructor_ast = None

		self.stats = {}
	
	def set_optimization_hook(self, hook):
		self.__unit_test_hook = hook

	def extract_contract_bytecode(self, contract, bytecode):

		for f in contract.functions:

			codereads = []
			nodes = f.nodes()
			for node in nodes:
				for ins in node.get_instructions() + [node.terminator]:
					if (ins.type == hlir.ins_types.vmcall 
							and ins.loc == vmcall.vmcalls.coderead):
						codereads.append(ins)

			if len(codereads) == 0:
				continue

			# detect this pattern:
			# mem(0x0, 0x1c9d) := vmcall coderead (0x6f, 0x1c9d)
			# vmcall haltreturn (mem(0x0, 0x1c9d))
			final_ins = []
			for coderead in codereads:
				mem = coderead.results[0]
				for node in nodes:
					for ins in node.get_instructions() + [node.terminator]:
						if (ins.type == hlir.ins_types.vmcall 
								and ins.loc == vmcall.vmcalls.haltreturn):
							if dataflow.ids_must_be_equal(ins.args[0], mem):
								final_ins.append(coderead)

			if len(final_ins) == 0:
				continue

			addr_len_pairs = set()
			for ins in final_ins:
				assert (isinstance(ins.args[0], expr.Lit))
				assert (isinstance(ins.args[1], expr.Lit))
				addr, length = ins.args[0].literal, ins.args[1].literal
				assert (addr + length <= len(bytecode))
				addr_len_pairs.add((addr, length))

			assert (len(addr_len_pairs) == 1)
			addr, length = next(iter(addr_len_pairs))

			return bytecode[addr:addr+length]

	def front_end(self, bytecode):
		llir_instructions = parser.parse(bytecode)
		self.stats["num_evm_instrs"] = len(llir_instructions)

		llir_bbs = llir.split(llir_instructions)

		contract = ll2hl.Converter().convert(llir_bbs, self.orig_bytecode)

		return contract
	
	def middle_end(self, contract, hook=None):
		optimizer = middleend.Optimizer(contract, hook)
		optimizer.optimize()

		loops = cfa.discover_loops(contract)
		cond_follows = cfa.discover_cond_follows(contract, loops)

		return contract, loops, cond_follows

	def decompile_raw(self, bytecode):
		self.orig_bytecode = bytecode
		bytecode = utils.remove_swarm_hash(bytecode)

		contract = self.front_end(bytecode)

		if self.__unit_test_hook:
			self.__unit_test_hook(contract)

		contract, loops, cond_follows = self.middle_end(
				contract, hook=self.__unit_test_hook)

		ast = astconverter.convert(
				contract, loops, cond_follows, self.constructor_ast)

		if self.__unit_test_hook:
			self.__unit_test_hook(ast)

		ast = readability.improve(ast)

		if self.__unit_test_hook:
			self.__unit_test_hook(ast)

		code = codegen.generate_code(self.stats, ast)

		return contract, ast, code
	
	def decompile(self, bytecode):
		
		# decompile the deployment contract
		constructor_contract, self.constructor_ast, code = self.decompile_raw(bytecode)

		# extract the deployed bytecode
		bytecode = self.extract_contract_bytecode(
			constructor_contract, bytecode)

		if bytecode is None:
			log.warn("Failed to extract the bytecode for the deployed contract")
			return constructor_contract, self.constructor_ast, code

		# decompile the deployed contract
		contract, ast, code = self.decompile_raw(bytecode)

		return contract, ast, code
	
