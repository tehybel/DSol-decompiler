
class NodeContainer:
	def __init__(self, h):
		self.__cached_nodes = None
		self.header_node = h
	
	def invalidate_cached_nodes(self):
		self.__cached_nodes = None
	
	def nodes(self):
		if not self.__cached_nodes:
			self.__cached_nodes = self.header_node.reachable_nodes()
		return self.__cached_nodes

	def to_dot_file(self):
		out  = "subgraph G {\n"
		for node in sorted(self.nodes(), key=_key):
			out += node.to_dot_file()
		out += "}\n"
		return out

	def display(self):
		import tempfile
		dot = self.to_dot_file().replace("subgraph", "digraph")
		f = tempfile.NamedTemporaryFile(delete=False)
		f.write(dot)
		f.close()
		import os
		#os.system("killall xdot")
		os.system("xdot %s & " % f.name)
	

def _key(n):
	try:
		return n.address
	except AttributeError:
		return id(n)

class Node:
	def to_dot_file(self):
		out = ""
		label = str(self).replace("\n", "\\l")
		out += '"0x%x" [shape=box, label="%s"];\n' % (id(self), label )
		for succ in sorted(self.get_successors(), key=_key):
			out += '"0x%x" -> "0x%x";\n' % (id(self), id(succ))
		return out

	def _reachable_nodes(self, follow_func, exclude_self=False):
		result = set()

		# using id(node) and this separate set may seem strange, but it
		# results in an almost 50% speedup of the decompiler.
		seen = set()

		if exclude_self:
			stack = [s for s in self.get_successors()]
		else:
			stack = [self]

		while len(stack) != 0:
			node = stack.pop()
			if id(node) in seen:
				continue

			result.add(node)
			seen.add(id(node))
			for o in follow_func(node):
				stack.append(o)

		return result

	def reachable_nodes(self, exclude_self=False):
		assert (isinstance(exclude_self, bool))
		return self._reachable_nodes(lambda n: n.get_successors(), exclude_self)
