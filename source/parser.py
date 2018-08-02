import llir
import utils

def is_push(b):
	return b >= 0x60 and b <= 0x7f

def is_dup(b):
	return b >= 0x80 and b <= 0x8f

def is_swap(b):
	return b >= 0x90 and b <= 0x9f

def is_log(b):
	return b >= 0xa0 and b <= 0xa4

def parse(bytecode):
	result = []
	bytecode = [ord(b) for b in bytecode]
	index = 0
	while index < len(bytecode):
		
		addr = index
		byte = bytecode[index]
		index += 1

		if is_push(byte):
			length = byte - 0x60 + 1
			arg = utils.big_endian_decode(bytecode[index:index+length])
			index += length
			ins = llir.instructions.PUSH

		elif is_dup(byte):
			arg = byte - 0x80 + 1
			ins = llir.instructions.DUP

		elif is_swap(byte):
			arg = byte - 0x90 + 1
			ins = llir.instructions.SWAP

		elif is_log(byte):
			arg = byte - 0xa0 # no +1
			ins = llir.instructions.LOG

		elif byte in llir.opcodes_map:
			ins = llir.opcodes_map[byte]
			arg = None

		else:
			#log.warn("Unknown opcode: " + hex(byte))
			ins = llir.instructions.UNKNOWN
			arg = byte

		bc = bytecode[addr:index]
		result.append(llir.Instruction(ins, arg, addr, bc))
	
	return result

