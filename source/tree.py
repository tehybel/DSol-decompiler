import utils
import log

class Node:
	def __str__(self):
		result = str(self.__class__)
		result += "(\n"
		for child_name in self.child_names:
			cn = getattr(self, child_name)

			if cn is None or isinstance(cn, Node):
				result += utils.indent(str(cn)) + "\n"
			elif isinstance(cn, list):
				for c in cn:
					result += utils.indent(str(c)) + "\n"
			else:
				log.critical("Unexpected child node type")
				
		result += ")\n"
		return result
