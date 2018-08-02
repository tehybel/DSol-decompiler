import hlir
import expr
import utils
import numbering
import draw

MAX_ITERATIONS = 20


class Loop:
	def __init__(self, h, f, nodes):
		assert (isinstance(h, hlir.BasicBlock))
		assert (f is None or isinstance(f, hlir.BasicBlock))
		for n in nodes:
			assert (isinstance(n, hlir.BasicBlock))

		self.header_node = h
		self.follow_node = f
		self.nodes = nodes

class Graph(draw.NodeContainer):
	def __init__(self):
		self.successors = {}
		self.predecessors = {}

		# initialized later
		self.header_node = None
		self.header_bb = None
	
	def nodes(self):
		return self.header_node.reachable_nodes()

	def is_reducible(self):
		return len(self.nodes()) != 1
	
	# collapse each interval into a single node
	def collapse_intervals(self, intervals):
		len_before = len(self.nodes())

		interval_nodes = {}
		containing_node = {}

		# make a node for each interval
		for interval in intervals:
			interval = tuple(interval) # make it hashable
			bbs = set()
			for node in interval:
				bbs |= node.bbs
			node = Node(self, interval[0].header_bb, bbs)
			interval_nodes[interval] = node
			for bb in bbs:
				containing_node[bb] = node

		# update header node
		self.header_node = containing_node[self.header_bb]

		# update succ/pred info
		new_succs = {}
		new_preds = {}
		for interval_node in interval_nodes.values():
			new_succs[interval_node] = set()
			new_preds[interval_node] = set()

		# the successors of an interval-node are all the nodes reachable from
		# the interval, but which aren't in the interval itself.
		for interval, interval_node in interval_nodes.items():
			reachable_bbs = set()
			for bb in interval_node.bbs:
				reachable_bbs |= bb.get_successors()
			reachable_bbs -= interval_node.bbs
			for succ_bb in reachable_bbs:
				assert (isinstance(succ_bb, hlir.BasicBlock))
				succ_node = containing_node[succ_bb]
				assert (isinstance(succ_node, Node))
				new_succs[interval_node].add(succ_node)

		# the predecessors of an interval-node are just the predecessors of
		# the header of the interval
		for interval, interval_node in interval_nodes.items():
			header_node = interval[0]
			reachable_bbs = set()
			for pred_node in self.predecessors[header_node]:
				reachable_bbs |= pred_node.bbs
			reachable_bbs -= interval_node.bbs
			for pred_bb in reachable_bbs:
				assert (isinstance(pred_bb, hlir.BasicBlock))
				pred_node = containing_node[pred_bb]
				assert (isinstance(pred_node, Node))
				new_preds[interval_node].add(pred_node)

		self.successors = new_succs
		self.predecessors = new_preds

		# sanity check: we should have made progress. (But it can't be a
		# strict less than; I found a counterexample where we did remove an
		# edge but no nodes.)
		assert (len(self.nodes()) <= len_before)

		

class Node(draw.Node):
	def __init__(self, graph, header_bb, bbs):
		assert (header_bb in bbs)
		for bb in bbs:
			assert (isinstance(bb, hlir.BasicBlock))

		self.graph = graph
		self.bbs = bbs
		self.successors = set()
		self.header_bb = header_bb
	def get_successors(self):
		return self.graph.successors[self]
	def get_predecessors(self):
		return self.graph.predecessors[self]
	
class LoopStructuring:

	# based on "Interval Algorithm" from reverse compilation techniques
	def find_intervals(self, g):
		intervals = []
		header_nodes = []

		remaining_nodes = set([n for n in g.nodes()])

		assert (g.header_node in remaining_nodes)
		remaining_nodes.remove(g.header_node)
		header_nodes.append(g.header_node)

		for h in header_nodes:
			# compute the interval with h as a header node
			interval_nodes = [h]

			# add nodes to the interval while possible
			while True:
				progress = False
				for m in list(remaining_nodes):
					assert (m not in interval_nodes)
					assert (len(g.predecessors[m]) != 0)
					if all(p in interval_nodes for p in g.predecessors[m]):
						remaining_nodes.remove(m)
						interval_nodes.append(m)
						progress = True

				if not progress:
					break

			# add it to the intervals set
			intervals.append(interval_nodes)

			# compute more header nodes to process
			for m in list(remaining_nodes):
				assert (m not in header_nodes)
				assert (m not in interval_nodes)
				if any(p in interval_nodes for p in g.predecessors[m]):
					remaining_nodes.remove(m)
					header_nodes.append(m)

					# every predecessor should not be in the interval,
					# otherwise this node should have been included in the
					# interval too
					assert (not all(p in interval_nodes 
									for p in g.predecessors[m]))

		return intervals
	
	def find_latching_nodes(self, interval):
		header = interval[0]
		return [n for n in interval if header in n.get_successors()]

	def make_loop(self, header_node, follow_node, loop_nodes):
		header_bb = header_node.header_bb
		follow_bb = None
		if follow_node:
			follow_bb = follow_node.header_bb
		loop_bbs = set()
		for node in loop_nodes:
			loop_bbs |= node.bbs

		loop = Loop(
			header_bb,
			follow_bb,
			loop_bbs
		)

		self.sanity_check_loop(loop)
		self.found_loops.add(loop)
	
	# check a condition: there must exist 
	def satisfies_condition(self, node, latching_nodes):
		reachable = node.reachable_nodes()
		return any(l in reachable for l in latching_nodes)
	
	# attempts to create a loop, though it may fail.
	def make_loop_from_interval(self, interval):
		
		latching_nodes = self.find_latching_nodes(interval)

		if len(latching_nodes) == 0:
			# this is no loop
			return

		# make sure the nodes have numbers
		number = numbering.initialize_node_numbers(interval)

		# figure out which nodes it contains.
		header_node = interval[0]
		max_latching_node = max(latching_nodes, key=lambda n: number[n])
		assert (number[header_node] <= number[max_latching_node])

		loop_nodes = [n for n in interval if number[n] >= number[header_node]
						and number[n] <= number[max_latching_node]
						and self.satisfies_condition(n, latching_nodes)]

		# don't make loops with indirect jumps in them
		for node in loop_nodes:
			for bb in node.bbs:
				if utils.has_imprecise_successors(bb):
					return

		while True:
			out_reachable = set()
			for node in loop_nodes:
				for s in node.get_successors():
					if s not in loop_nodes:
						out_reachable.add(s)

			if len(out_reachable) == 0:
				follow_node = None
				break # endless loop

			if len(out_reachable) == 1:
				follow_node = next(iter(out_reachable))
				break # everything is fine!

			# if there are indirect jumps in the out_reachable, then we're
			# better off not turning this set of nodes into a loop yet; if we
			# wait, the indirect jump may be resolved and then we'll get
			# better results.
			# Also if out_reachable consists purely of indirect jumps, and
			# there's more than one, then we wouldn't know which, if any, to
			# pull into the loop. By returning early we avoid this case.
			# TODO: revisit this.
			for node in out_reachable:
				for bb in node.bbs:
					if utils.has_imprecise_successors(bb):
						return

			for node in out_reachable:
				if all(p in loop_nodes for p in node.get_predecessors()):
					if node in interval:
						# we can pull it in
						loop_nodes.append(node)
						break
			else:
				# found no node to pull in.
				# TODO: we should still make a loop but generate gotos.
				return

		# sanity checks:
		for node in loop_nodes:
			# no imprecise jumps in the loop
			for bb in node.bbs:
				assert (not utils.has_imprecise_successors(bb))

			# can't escape the loop except via follow
			for s in node.get_successors():
				assert (s in loop_nodes or s in [header_node, follow_node])

			# all loop nodes are in this interval
			assert (node in interval)
			
		self.make_loop(header_node, follow_node, loop_nodes)

	# an interval for a header node is the maximal subgraph for which it holds
	# that every cycle goes through the interval header
	def sanity_check_intervals(self, intervals, g):
		# none of the intervals should overlap
		for interval in intervals:
			i = set(interval)
			for other in intervals:
				o = set(other)
				if i == o:
					continue

				assert (len(i & o) == 0)

		# every node in the graph should be in some interval
		covered_nodes = set()
		for interval in intervals:
			for node in interval:
				covered_nodes.add(node)
		for node in g.nodes():
			assert (node in covered_nodes)

		# every node in the original function should be in some interval
		covered_bbs = set()
		for node in covered_nodes:
			for bb in node.bbs:
				covered_bbs.add(bb)
		for bb in self.function.nodes():
			assert (bb in covered_bbs)

		# more checks
		for interval in intervals:
			# all nodes are unique
			assert (len(set(interval)) == len(interval))

			# any cycles should go through the header node
			# (this isn't quite what we're checking, but what we check is close
			# and cheaper.)
			header = interval[0]
			for node in interval:
				reach = node.reachable_nodes(exclude_self=True)
				if node in reach:
					assert (header in reach)

			# the subgraph should be maximal
			for node in self.function.nodes():
				if all(pred in interval for pred in node.get_predecessors()):
					assert (node in interval or node == i[0] for i in intervals)

	def sanity_check_loop(self, loop):
		assert (loop.header_node != loop.follow_node)

		for node in loop.nodes:
			assert (not utils.has_imprecise_successors(node))
			for s in node.get_successors():
				assert (s in loop.nodes or s == loop.follow_node)

		# also no node from the function should reach inside the loop, except
		# to the loop node itself.
		for node in self.function.nodes():
			if node not in loop.nodes:
				for s in node.get_successors():
					if s != loop.header_node:
						assert (s not in loop.nodes)

	def make_initial_graph(self):
		g = Graph()

		# set up translation
		bb_to_node = {}
		node_to_bb = {}
		for bb in self.function.nodes():
			node = Node(g, bb, set([bb]))
			bb_to_node[bb] = node
			node_to_bb[node] = bb

		# set header node
		g.header_bb = self.function.header_node
		g.header_node = bb_to_node[g.header_bb]

		# init succ/pred info
		for bb in self.function.nodes():
			node = bb_to_node[bb]
			g.successors[node] = set()
			g.predecessors[node] = set()
			for s in bb.get_successors():
				s = bb_to_node[s]
				g.successors[node].add(s)
			for p in bb.get_predecessors():
				p = bb_to_node[p]
				g.predecessors[node].add(p)

		return g
	
	def sanity_check_graph(self, g):
		assert (isinstance(g.header_node, Node))

		for node, successors in g.successors.items():
			assert (isinstance(node, Node))
			for s in successors:
				assert (isinstance(s, Node))

		for node, preds in g.predecessors.items():
			assert (isinstance(node, Node))
			for p in preds:
				assert (isinstance(p, Node))

		for node in g.nodes():
			assert (len(node.bbs) > 0)

		bb_to_node = {}
		for node in g.nodes():
			for bb in node.bbs:
				bb_to_node[bb] = node

		# each original BB's successors should be either part of that BB's
		# collapsed node, or it should be in one of the successor nodes.
		for bb in self.function.nodes():
			bb_node = bb_to_node[bb]
			for succ in bb.get_successors():
				succ_node = bb_to_node[succ]
				assert (succ_node == bb_node or
						succ_node in bb_node.get_successors())
			# likewise for preds
			for pred in bb.get_predecessors():
				pred_node = bb_to_node[pred]
				assert (pred_node == bb_node or
						pred_node in bb_node.get_predecessors())
				
	
	def find_loops(self):
		g = self.make_initial_graph()
		iterations = 0
		while g.is_reducible():
			self.sanity_check_graph(g)
			intervals = self.find_intervals(g)
			self.sanity_check_intervals(intervals, g)
			for interval in intervals:
				# may fail silently.
				self.make_loop_from_interval(interval)

			g.collapse_intervals(intervals)

			# sometimes the graphs *do* contain the canonical irreducible
			# subgraph because of indirect jumps.. So we have a way out here.
			iterations += 1
			if iterations > MAX_ITERATIONS:
				break

		return self.found_loops
	
	def __init__(self, f):
		self.function = f
		self.found_loops = set()

def discover_loops(contract):
	result = set()
	for f in contract.functions:
		ls = LoopStructuring(f)
		found_loops = ls.find_loops()
		for loop in found_loops:
			result.add(loop)

	return result




##############################################################################
######################## conditional structuring #############################
##############################################################################


"""

Constraints:
- if the header is inside a loop, we may never leave that loop
- if we find a loop that is not the one we're initially inside, then that
  loop's nodes (including its header) may not be reached
- we may never follow continues
- if the true-node or false-node terminates, we can choose that as the follow
	- but we must still obey the constraints; e.g., the true-node can't break
	  out of the loop.
- we should never follow an edge to the cond header. (This should not happen,
  but it still might if all loops were not detected.)
- we should never follow imprecise successors
- we currently use node.next_bb as the next false node. Is that accurate??
- the numbering computation should use the above rules, too.

We should use a special "successor" function that only returns valid edges.
Then we can use that to compute the reach.
We can also use that to check if we can make the true- or false-node a follow.
We should keep the cond header as a self-property so we don't have to pass it
around so much.

And we should remember to check that the constraints hold via assertions.

"""

class ConditionalFollowDiscoverer:
	def __init__(self, contract, loops):
		self.contract = contract
		self.loops = loops

		# compute breaks/continues so we don't follow those
		self.compute_loop_edges()
	
	def compute_loop_edges(self):
		self.continues = set()
		self.breaks = set()
		self.containing_loop = {}
		self.loop_headers = {}

		for loop in self.loops:
			self.loop_headers[loop.header_node] = loop
			for bb in loop.nodes:
				self.containing_loop[bb] = loop
				for s in bb.get_successors():
					if s == loop.header_node:
						self.continues.add((bb, s))
					if s == loop.follow_node:
						self.breaks.add((bb, s))
	
	def successors(self, n):
		result = set()
		if utils.has_imprecise_successors(n):
			return result

		for s in n.get_successors():
			if utils.has_imprecise_successors(s):
				continue
			if (n, s) in self.continues:
				continue
			if (n, s) in self.breaks:
				continue
			if s == self.current_header:	
				continue

			if s in self.loop_headers:
				loop = self.loop_headers[s]
				if loop.follow_node:
					result.add(loop.follow_node)
				continue

			result.add(s)

		return result
	
	def is_end_point(self, node):
		if len(node.get_successors()) != 0:
			return False

		if len(node.get_predecessors()) != 1:
			return False

		return True

	def sanity_check(self, node, true_node, false_node, follow):
		# we can at least check that some very basic cases are handled
		# properly...
		if len(false_node.get_successors()) == 1:
			if false_node.successor() == true_node:
				assert (follow == true_node)

		if len(true_node.get_successors()) == 1:
			if true_node.successor() == false_node:
				assert (follow == false_node)

		true_succs = self.successors(true_node)
		false_succs = self.successors(false_node)
		if len(true_succs) == 1 and len(false_succs) == 1:
			ts = next(iter(true_succs))
			fs = next(iter(false_succs))
			if ts == fs:
				assert (follow == ts)

		# this would make no sense
		assert (node != follow)
	
	def discover_follow_in_func(self, function):
		follows = {}
		bbs_by_addr = {bb.address: bb for bb in function.nodes()}
		for node in reversed(utils.dfs_ordering(function.header_node)):
			ins = node.terminator
			if ins.type != hlir.ins_types.jcond:
				continue

			if not isinstance(ins.loc, expr.Lit):
				# can't structure indirect jconds
				continue

			assert (len(node.get_successors()) == 2)

			self.current_header = node
			succs = self.successors(node)

			if len(succs) != 2:
				continue
			if succs != node.get_successors():
				continue

			true_node, false_node = succs
			if true_node != bbs_by_addr[ins.loc.literal]:
				true_node, false_node = false_node, true_node
			assert (true_node == bbs_by_addr[ins.loc.literal])

			true_reach = true_node._reachable_nodes(self.successors)
			false_reach = false_node._reachable_nodes(self.successors)

			if node in true_reach or node in false_reach:
				continue

			intersection = true_reach & false_reach
			if len(intersection) == 0:
				# we can't find a traditional follow -- but if one of the
				# sides returns early then we can still make the conditional
				# look better
				# however we should ensure that the follow node doesn't have other
				# predecessors, otherwise the generated code may actually get
				# worse from this.
				if self.is_end_point(true_node):
					follow = false_node

				elif self.is_end_point(false_node):
					follow = true_node

				else:
					follow = None

			else:
				nc = numbering.NumberComputer(list(intersection), self.successors)
				nc.compute_bb_numbering()
				follow = min(intersection, key=lambda n: nc.numbering[n])

			self.sanity_check(node, true_node, false_node, follow)
			if follow:
				assert (node not in follows)
				follows[node] = follow
		
		return follows

	def discover(self):
		follows = {}

		# compute the follows for each function
		for f in self.contract.functions:
			fls = self.discover_follow_in_func(f)
			for cond in fls:
				assert (cond not in follows)
				follows[cond] = fls[cond]

			# sanity check
			for follow_node in fls.values():
				assert (follow_node in f.nodes())

		return follows

def discover_cond_follows(contract, loops):
	discoverer = ConditionalFollowDiscoverer(contract, loops)
	return discoverer.discover()


