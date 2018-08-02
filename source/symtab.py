# maps from items to names
class SymbolTable:
	def __init__(self, base_name):
		self.counter = 0
		self.base_name = base_name
		self.entries = {}
	
	def contains(self, var):
		return id(var) in self.entries
	
	def insert(self, item, name=None):
		if name is None:
			name = self.base_name + str(self.counter)
			self.counter += 1
		self.entries[id(item)] = name
	
	def lookup(self, item):
		if id(item) not in self.entries:
			self.insert(item)

		return self.entries[id(item)]
