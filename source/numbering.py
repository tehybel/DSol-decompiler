class NumberComputer:
	
	def reachable_nodes(self, n):
		result = set()
		stack = [n]
		while len(stack) != 0:
			node = stack.pop()
			assert (node in self.interval)
			if node in result:
				continue
			result.add(node)
			for succ in self.succ_func(node):
				if succ in self.interval:
					stack.append(succ)

		# sanity check
		for n in result:
			assert (n in self.interval)

		return result
	
	def path_exists(self, a, b):
		return b in self.reachable_nodes(a)

	def __init__(self, interval, succ_func=None):
		self.interval = set([n for n in interval])
		self.interval_header = interval[0]
		self.numbering = {}

		if succ_func is None:
			self.succ_func = lambda n: n.get_successors()
		else:
			self.succ_func = succ_func

		self.init_dfs_numbers()
	
	def dfs(self, n, seen):
		if n in seen:
			return
		seen.add(n)
		for succ in self.succ_func(n):
			if succ in self.interval:
				self.dfs(succ, seen)
		self.dfs_number[n] = self.cur_dfs_num
		self.cur_dfs_num -= 1
	
	def init_dfs_numbers(self):
		self.dfs_number = {}
		self.cur_dfs_num = len(self.interval)
		self.dfs(self.interval_header, set())
	
	def break_ties(self, a, b):
		if a in self.dfs_number and b in self.dfs_number:
			return self.dfs_number[b] - self.dfs_number[a]
		else:
			# TODO fix this.
			return 0

	def compare_nodes(self, a, b):
		path_from_a_to_b = self.path_exists(a, b)
		path_from_b_to_a = self.path_exists(b, a)

		if path_from_a_to_b and path_from_b_to_a:
			# it's a tie, so use their address to determine which is first
			return self.break_ties(a, b)
		
		if path_from_a_to_b:
			return 1
		
		if path_from_b_to_a:
			return -1
		
		return self.break_ties(a, b)

	def compute_bb_numbering(self):
		nodes = list(self.interval)
		sorted_nodes = sorted(nodes, cmp=self.compare_nodes)
		for i, node in enumerate(reversed(sorted_nodes)):
			self.numbering[node] = i+1

	def sanity_check_numbers(self):
		assert (self.numbering[self.interval_header] == 1)

def initialize_node_numbers(interval):
	assert (isinstance(interval, list))
	nc = NumberComputer(interval)
	nc.compute_bb_numbering()
	nc.sanity_check_numbers()
	return nc.numbering
