import function
import utils

class Contract:
	def __init__(self, header_node, bytecode):
		assert (header_node.address == 0)
		f0 = function.Function(header_node, 0, 0, True)
		for n in f0.nodes():
			n.function = f0

		self.functions = [f0]

		# original, raw bytecode (used for interpreting coderead vmcalls)
		self.bytecode = bytecode
	
	def __str__(self):
		result = "contract {\n"
		for f in self.functions:
			result += utils.indent(str(f))
		result += "}\n"
		return result
	
