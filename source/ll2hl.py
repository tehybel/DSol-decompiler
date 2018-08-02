import llir
import hlir
import expr
import utils
import contract
import vmcall
import addressdispenser


bin_op_constructors = {
	llir.instructions.MUL: 	expr.Mul,
	llir.instructions.DIV: 	expr.Div,
	llir.instructions.SDIV:	expr.SDiv,
	llir.instructions.ADD:	expr.Add,
	llir.instructions.SUB:	expr.Sub,
	llir.instructions.AND:	expr.And,
	llir.instructions.MOD:	expr.Mod,
	llir.instructions.XOR:	expr.Xor,
	llir.instructions.OR:	expr.Or,
	llir.instructions.EQ:	expr.Eq,
	llir.instructions.GT:	expr.Gt,
	llir.instructions.SGT:	expr.SGt,
	llir.instructions.LT:	expr.Lt,
	llir.instructions.SLT:	expr.SLt,
	llir.instructions.EXP:	expr.Exp,
	llir.instructions.SIGNEXTEND: expr.SignExtend,
}

un_op_constructors = {
	llir.instructions.ISZERO: expr.Not,
	llir.instructions.NOT: expr.Neg, # yes, I didn't mix that with expr.Not.
}

gvars = {
	llir.instructions.COINBASE: "block.coinbase",
	llir.instructions.TIMESTAMP: "block.timestamp",
	llir.instructions.NUMBER: "block.number",
	llir.instructions.DIFFICULTY: "block.difficulty",
	llir.instructions.GASLIMIT: "block.gaslimit",

	llir.instructions.GAS: "msg.gas",
	llir.instructions.CALLER: "msg.sender",
	llir.instructions.CALLVALUE: "msg.value",
	llir.instructions.CALLDATASIZE: "msg.data.length",
	llir.instructions.ADDRESS: "this",

	llir.instructions.GASPRICE: "tx.gasprice",
	llir.instructions.ORIGIN: "tx.origin",
}

vmcalls = {
	# ins -> (name, num_params, num_retvals)
	llir.instructions.BLOCKHASH: (vmcall.vmcalls.blockhash, 1, 1),
	llir.instructions.SELFDESTRUCT: (vmcall.vmcalls.selfdestruct, 1, 0),

	llir.instructions.MSIZE: (vmcall.vmcalls.msize, 0, 1),
	
	llir.instructions.RETURNDATASIZE: (vmcall.vmcalls.returndatasize, 0, 1),

	llir.instructions.REVERT: (vmcall.vmcalls.revert, 2, 0),
	llir.instructions.STOP: (vmcall.vmcalls.stop, 0, 0),

	llir.instructions.BALANCE: (vmcall.vmcalls.balance, 1, 1),

	llir.instructions.CALLDATALOAD: (vmcall.vmcalls.calldataload, 1, 1),

	llir.instructions.BYTE: (vmcall.vmcalls.byte, 2, 1),

	llir.instructions.EXTCODESIZE: (vmcall.vmcalls.extcodesize, 1, 1),
	llir.instructions.CODESIZE: (vmcall.vmcalls.codesize, 0, 1),
}

class Converter:
	def __init__(self):
		# the stack pointer variable
		self.virtual_sp = 0
		self.just_pushed = None

	def inc_sp(self):
		self.virtual_sp += 1

	def dec_sp(self):
		self.virtual_sp -= 1
	
	def tos(self):
		return expr.Stack(self.virtual_sp)
	
	def temp(self):
		return expr.Var()
	
	def push(self, value):
		self.inc_sp()
		self.out_instrs.append(hlir.make_assign(self.tos(), value))
	
	# the implementation of pop is *crucial*; it is extremely important that
	# we move the tos value into a temp, and then assign an UnusedValue to the
	# stack slot, because then *all* then places using pop will capture the
	# fact that after a pop, that stack slot can no longer be expected to be
	# valid. For example, after a JUMP then the pushed value will correctly be
	# marked as no longer needed and can be eliminated, resulting in a more
	# accurate CFG.
	def _pop(self):
		t = self.temp()
		self.out_instrs.append(hlir.make_assign(t, self.tos()))
		self.out_instrs.append(hlir.make_assign(self.tos(), expr.UnusedValue()))
		self.dec_sp()
		return t
	
	def convert_ins(self, ins):
		if ins.ins == llir.instructions.PUSH:
			self.just_pushed = ins.arg
			self.push(expr.Lit(ins.arg))

		elif ins.ins in [llir.instructions.MSTORE, llir.instructions.MSTORE8]:
			addr = self._pop()
			value = self._pop()
			if ins.ins == llir.instructions.MSTORE:
				length = 0x20
			else:
				length = 1
			dest = expr.Mem(addr, expr.Lit(length))
			self.out_instrs.append(hlir.make_assign(dest, value))

		elif ins.ins in [llir.instructions.MULMOD, llir.instructions.ADDMOD]:
			a = self._pop()
			b = self._pop()
			modulus = self._pop()
			if ins.ins == llir.instructions.MULMOD:
				self.push(expr.Mod(expr.Mul(a, b), modulus))
			elif ins.ins == llir.instructions.ADDMOD:
				self.push(expr.Mod(expr.Add(a, b), modulus))
			else:
				assert (False)

		elif ins.ins in gvars:
			self.push(expr.GlobalVar(gvars[ins.ins]))

		elif ins.ins in bin_op_constructors:
			op1 = self._pop()
			op2 = self._pop()
			constructor = bin_op_constructors[ins.ins] # e.g. expr.Mul
			self.push(constructor(op1, op2))

		elif ins.ins in vmcalls:
			name, num_params, num_retvals = vmcalls[ins.ins]
			inputs = [self._pop() for _ in range(num_params)]
			retvals = []
			for _ in range(num_retvals):
				self.inc_sp()
				retvals.append(self.tos())
			self.out_instrs.append(hlir.make_vmcall(name, inputs, retvals))

		elif ins.ins == llir.instructions.SWAP:
			t = self.temp()
			d = self.virtual_sp - ins.arg
			self.out_instrs.append(hlir.make_assign(t.copy(), self.tos()))
			self.out_instrs.append(hlir.make_assign(self.tos(), expr.Stack(d)))
			self.out_instrs.append(hlir.make_assign(expr.Stack(d), t.copy()))
			# note: it's much better not to declare the temp as unused after
			# this, because then the temp will be propagated along instead of
			# the stack variable, and that allows the eventual elimination of
			# the stack variable, getting rid of the swap.


		elif ins.ins == llir.instructions.DUP:
			self.push(expr.Stack(self.virtual_sp + 1 - ins.arg))

		elif ins.ins == llir.instructions.JUMPDEST:
			pass # no need to handle this

		elif ins.ins in un_op_constructors:
			operand = self._pop()
			constructor = un_op_constructors[ins.ins]
			self.push(constructor(operand))

		elif ins.ins == llir.instructions.POP:
			self._pop()

		elif ins.ins == llir.instructions.JUMP:
			if self.just_pushed is not None:
				dest = expr.Lit(self.just_pushed)
				self.out_instrs.pop() # undo the assignment from the push
				self.dec_sp()
			else:
				dest = self._pop()
			self.out_instrs.append(hlir.make_jump(dest))

		elif ins.ins == llir.instructions.JUMPI:
			if self.just_pushed is not None:
				dest = expr.Lit(self.just_pushed)
				self.out_instrs.pop() # undo the assignment from the push
				self.dec_sp()
			else:
				dest = self._pop()
			value = self._pop()
			self.out_instrs.append(hlir.make_jcond(dest, value))

		elif ins.ins == llir.instructions.MLOAD:
			addr = self._pop()
			self.push(expr.Mem(addr, expr.Lit(0x20)))

		elif ins.ins == llir.instructions.HALTRETURN:
			addr = self._pop()
			length = self._pop()
			args = [expr.Mem(addr, length)]
			self.out_instrs.append(
				hlir.make_vmcall(vmcall.vmcalls.haltreturn, args, []))

		elif ins.ins == llir.instructions.INVALID:
			self.out_instrs.append(
				hlir.make_vmcall(vmcall.vmcalls.revert, [], []))

		elif ins.ins == llir.instructions.LOG:
			inputs = [expr.Mem(self._pop(), self._pop())]
			inputs += [self._pop() for _ in range(ins.arg)]
			self.out_instrs.append(
				hlir.make_vmcall(vmcall.vmcalls.log, inputs, []))

		elif ins.ins == llir.instructions.SLOAD:
			self.push(expr.Storage(self._pop()))

		elif ins.ins == llir.instructions.SSTORE:
			addr = self._pop()
			value = self._pop()
			self.out_instrs.append(hlir.make_assign(expr.Storage(addr), value))

		elif ins.ins == llir.instructions.SHA3:
			addr = self._pop()
			length = self._pop()
			args = [expr.Mem(addr, length)]
			self.push(expr.PureFunctionCall(vmcall.vmcalls.sha3, args))

		elif ins.ins in [llir.instructions.MESSAGECALL, 
						 llir.instructions.DELEGATECALL,
						 llir.instructions.CALLCODE]:
			gaslimit = self._pop()
			to = self._pop()
			if ins.ins in [llir.instructions.MESSAGECALL,
						   llir.instructions.CALLCODE]:
				value = self._pop()
			input_addr = self._pop()
			input_length = self._pop()
			output_addr = self._pop()
			output_length = self._pop()

			if ins.ins in [llir.instructions.MESSAGECALL,
						   llir.instructions.CALLCODE]:
				args = [gaslimit, to, value, expr.Mem(input_addr, input_length)]
				cl = vmcall.vmcalls.messagecall
			else:
				args = [gaslimit, to, expr.Mem(input_addr, input_length)]
				cl = vmcall.vmcalls.delegatecall

			retval = self.temp()
			result = [retval, expr.Mem(output_addr, output_length)]
			self.out_instrs.append(hlir.make_vmcall(cl, args, result))
			self.push(retval)

		elif ins.ins in [llir.instructions.CODECOPY,
						 llir.instructions.CALLDATACOPY,
						 llir.instructions.RETURNDATACOPY]:
			out_addr = self._pop()
			in_addr = self._pop()
			args = [in_addr, self.tos()]
			result = [expr.Mem(out_addr, self.tos())]
			self.dec_sp()
			if ins.ins == llir.instructions.CODECOPY:
				cl = vmcall.vmcalls.coderead
			elif ins.ins == llir.instructions.CALLDATACOPY:
				cl = vmcall.vmcalls.calldataread
			else:
				cl = vmcall.vmcalls.returndataread
			self.out_instrs.append(hlir.make_vmcall(cl, args, result))

		elif ins.ins == llir.instructions.CREATE:
			value = self._pop()
			addr = self._pop()
			size = self._pop()
			result = self.temp()
			args = [expr.Mem(addr, size)]
			self.out_instrs.append(
				hlir.make_vmcall(vmcall.vmcalls.create, args, [result]))
			self.push(result)

		elif ins.ins == llir.instructions.UNKNOWN:
			# unknown instructions result in a revert
			self.out_instrs.append(
				hlir.make_vmcall(vmcall.vmcalls.revert, [], []))

		else:
			print(ins)
			assert (False)


		if ins.ins != llir.instructions.PUSH:
			self.just_pushed = None

		return self.out_instrs


	# convert a BB of LLIR into a BB of HLIR instructions
	def convert_bb(self, llir_bb):

		# first compute the virtual sp delta
		self.out_instrs = []
		self.virtual_sp = 0
		for ins in llir_bb.instructions:
			self.convert_ins(ins)

		delta = self.virtual_sp
		self.virtual_sp = -self.virtual_sp

		# then do the actual conversion
		self.out_instrs = []
		for ins in llir_bb.instructions:
			self.convert_ins(ins)

		return hlir.BasicBlock(
			llir_bb.address,
			self.out_instrs,
			delta
		)

	def finalize_prev_next(self, bbs):
		# fill out prev/next info
		for i in range(len(bbs)):
			if i == len(bbs)-1:
				next_bb = None
			else:
				next_bb = bbs[i+1]

			bb = bbs[i]
			bb.next_bb = next_bb

	def sanity_check(self, header_node):
		# by now, no BB should contain any jump/jcond instructions
		for node in header_node.reachable_nodes():
			for ins in node.get_instructions():
				assert (ins.type != hlir.ins_types.jump)
				assert (ins.type != hlir.ins_types.jcond)
				assert (not (ins.type == hlir.ins_types.vmcall 
							 and ins.loc in vmcall.terminating_vmcalls))

		for node in header_node.reachable_nodes():
			assert (node.get_successors() is not None)

	def init_terminators(self, bbs):
		addr = addressdispenser.get_new_address()
		revert_node = hlir.BasicBlock(addr, [], 0)
		revert_node.terminator = hlir.make_vmcall(vmcall.vmcalls.revert, [], [])

		bb_by_addr = {bb.address: bb for bb in bbs + [revert_node]}
		for bb in bbs:
			if len(bb.get_instructions()) == 0:
				last_ins = None
			else:
				last_ins = bb.get_instructions()[-1]

			if last_ins and last_ins.type == hlir.ins_types.jump:
				target = last_ins.loc
				if isinstance(target, expr.Lit):
					if target.literal not in bb_by_addr:
						target.literal = revert_node.address
					succ = bb_by_addr[target.literal]
					bb.add_successor(succ)
				else:
					for other in utils.compute_indirect_jump_successors(bbs):
						bb.add_successor(other)
				bb.remove_instruction(last_ins)
				bb.terminator = last_ins

			elif last_ins and last_ins.type == hlir.ins_types.jcond:
				bb.add_successor(bb.next_bb)

				target = last_ins.loc
				if isinstance(target, expr.Lit):
					if target.literal not in bb_by_addr:
						target.literal = revert_node.address
					succ = bb_by_addr[target.literal]
					bb.add_successor(succ)
				else:
					for other in utils.compute_indirect_jump_successors(bbs):
						bb.add_successor(other)

				bb.remove_instruction(last_ins)
				bb.terminator = last_ins

			elif (last_ins 
					and last_ins.type == hlir.ins_types.vmcall 
					and last_ins.loc in vmcall.terminating_vmcalls):
				assert (len(bb.get_successors()) == 0)
				bb.remove_instruction(last_ins)
				bb.terminator = last_ins

			else:
				if bb.next_bb is not None:
					bb.terminator = hlir.make_jump(expr.Lit(bb.next_bb.address))
					bb.add_successor(bb.next_bb)
				else:
					bb.terminator = hlir.make_vmcall(vmcall.vmcalls.revert, [], [])
				
	def convert(self, llir_bbs, bytecode):
		hlir_bbs = []
		for bb in llir_bbs:
			hlir_bb = self.convert_bb(bb)
			hlir_bbs.append(hlir_bb)

		self.finalize_prev_next(hlir_bbs)

		self.init_terminators(hlir_bbs)

		header_node = hlir_bbs[0]
		assert (header_node.address == 0)

		self.sanity_check(header_node)

		return contract.Contract(header_node, bytecode)

