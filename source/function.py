import utils
import hlir
import draw

class Function(draw.NodeContainer):
	def __init__(self, header_node, num_params, num_retvals, external):
		draw.NodeContainer.__init__(self, header_node)

		self.address = self.header_node.address

		self.params = []
		self.num_params = num_params
		self.num_retvals = num_retvals
		self.external = external

		self.flattened = False
	
	def get_nodes_by_addr(self):
		return {node.address: node for node in self.nodes()}
	
	def checksum(self):
		c = 0
		c += hash(self.header_node)
		c += hash(self.address)
		c += hash(self.num_params)
		c += hash(self.num_retvals)
		for p in self.params:
			c += hash(p)
		for node in self.nodes():
			c += hash(node)
			for s in node.get_successors():
				c += hash(s)
			for p in node.get_predecessors():
				c += hash(p)
		return c

	def bbs(self):
		return [node for node in self.nodes() 
				if isinstance(node, hlir.BasicBlock)]
	
	def __str__(self):
		out = "Function (addr=0x%x" % self.address
		out += ", params: [%s]" % ",".join(str(p) for p in self.params)
		out += ", retvals: %d" % self.num_retvals
		out += ") {\n"
		for node in sorted(self.nodes(), key=lambda n: id(n)):
			out += utils.indent(str(node) + "\n")
		#out += utils.indent(str(self.header_node))
		out += "}\n"
		return out
	
