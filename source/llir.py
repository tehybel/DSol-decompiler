

# The various LLIR instruction types are declared as constants here
# (taken from
# https://ethereum.stackexchange.com/questions/119/what-opcodes-are-available-for-the-ethereum-evm
# and parsed)

opcodes_table = [

(-1, "UNKNOWN"), # for e.g. inlined strings

# 0s: Stop and Arithmetic Operations
(0x00,    "STOP"),        # Halts execution
(0x01,    "ADD"),         # Addition operation
(0x02,    "MUL"),         # Multiplication operation
(0x03,    "SUB"),         # Subtraction operation
(0x04,    "DIV"),         # Integer division operation
(0x05,    "SDIV"),        # Signed integer
(0x06,    "MOD"),         # Modulo
(0x07,    "SMOD"),        # Signed modulo
(0x08,    "ADDMOD"),      # Modulo
(0x09,    "MULMOD"),      # Modulo
(0x0a,    "EXP"),         # Exponential operation
(0x0b,    "SIGNEXTEND"),  # Extend length of two's complement signed integer

# 10s: Comparison & Bitwise Logic Operations
(0x10,    "LT"),      # Lesser-than comparison
(0x11,    "GT"),      # Greater-than comparison
(0x12,    "SLT"),     # Signed less-than comparison
(0x13,    "SGT"),     # Signed greater-than comparison
(0x14,    "EQ"),      # Equality  comparison
(0x15,    "ISZERO"),  # Simple not operator
(0x16,    "AND"),     # Bitwise AND operation
(0x17,    "OR"),      # Bitwise OR operation
(0x18,    "XOR"),     # Bitwise XOR operation
(0x19,    "NOT"),     # Bitwise NOT operation
(0x1a,    "BYTE"),    # Retrieve single byte from word

# 20s: SHA3
(0x20,    "SHA3"),    # Compute Keccak-256 hash

# 30s: Environmental Information
(0x30,    "ADDRESS"),         # Get address of currently executing account
(0x31,    "BALANCE"),         # Get balance of the given account
(0x32,    "ORIGIN"),          # Get execution origination address
(0x33,    "CALLER"),          # Get caller address. 
(0x34,    "CALLVALUE"),       # Get deposited value by the ...
(0x35,    "CALLDATALOAD"),    # Get input data of current environment
(0x36,    "CALLDATASIZE"),    # Get size of input data in current environment
(0x37,    "CALLDATACOPY"),    # Copy input data in current environment ...
(0x38,    "CODESIZE"),        # Get size of code running in current environ
(0x39,    "CODECOPY"),        # Copy code running in current environment..
(0x3a,    "GASPRICE"),        # Get price of gas in current environment
(0x3b,    "EXTCODESIZE"),     # Get size of an account's code
(0x3c,    "EXTCODECOPY"),     # Copy an account's code to memory


# these are special; they're from EIP 211 and aren't in the yellowpaper
(0x3d,	  "RETURNDATASIZE"),
(0x3e,	  "RETURNDATACOPY"),

# 40s: Block Information

(0x40,    "BLOCKHASH"),   # Get the hash of one of the 256 most recent  ...
(0x41,    "COINBASE"),    # Get the block's beneficiary address
(0x42,    "TIMESTAMP"),   # Get the block's timestamp
(0x43,    "NUMBER"),      # Get the block's number
(0x44,    "DIFFICULTY"),  # Get the block's difficulty
(0x45,    "GASLIMIT"),    # Get the block's gas limit

# 50s Stack, Memory, Storage and Flow Operations

(0x50,    "POP"),         # Remove item from stack
(0x51,    "MLOAD"),       # Load word from memory
(0x52,    "MSTORE"),      # Save word to memory
(0x53,    "MSTORE8"),     # Save byte to memory
(0x54,    "SLOAD"),       # Load word from storage
(0x55,    "SSTORE"),      # Save word to storage
(0x56,    "JUMP"),        # Alter the program counter
(0x57,    "JUMPI"),       # Conditionally alter the program counter
(0x58,    "PC"),          # Get the value of the program counter prior ...
(0x59,    "MSIZE"),       # Get the size of active memory in bytes
(0x5a,    "GAS"),         # Get the amount of available gas, including ...
(0x5b,    "JUMPDEST"),    # Mark a valid destination for jumps

# 60s & 70s: Push Operations
# these are handled specially
# (0x60,    "PUSH1"),   # Place 1 byte item on stack
# (0x61,    "PUSH2"),   # Place 2-byte item on stack
# ...
# (0x7f,    "PUSH32"),  # Place 32-byte (full word) item on stack
(0x60,    "PUSH"),

# 80s: Duplication Operations
# these are handled specially
# (0x80,    "DUP1"),    # Duplicate 1st stack item
# (0x81,    "DUP2"),    # Duplicate 2nd stack item
# ...
# (0x8f,    "DUP16"),   # Duplicate 16th stack item
(0x80,    "DUP"),

# 90s: Exchange Operations
# these are handled specially
# (0x90,    "SWAP1"),   # Exchange 1st and 2nd stack items
# (0x91,    "SWAP2"),   # Exchange 1st and 3rd stack items
# ...
# (0x9f,    "SWAP16"),  # Exchange 1st and 17th stack items
(0x90,    "SWAP"),

# a0s: Logging Operations
# these are handled specially
# (0xa0,    "LOG0"),    # Append log record with no topics
# (0xa1,    "LOG1"),    # Append log record with one topic
# (0xa2,    "LOG2"),    # Append log record with two topic
# (0xa3,    "LOG3"),    # Append log record with three topic
# (0xa4,    "LOG4"),    # Append log record with four topics
(0xa0,    "LOG"),

# f0s: System operations

(0xf0,    "CREATE"),          # Create a new account with associated code

# NOTE: I modified this from "CALL" for less confusion
# Message-call into an account
# allegedly the parameters are: 
# (gasLimit, to, value, inputOffset, inputSize, outputOffset, outputSize)
(0xf1,    "MESSAGECALL"),     

(0xf2,    "CALLCODE"),        # Message-call into this account ...
# NOTE: I modified this from "RETURN" for less confusion
(0xf3,    "HALTRETURN"),          # Halt execution returning output data
(0xf4,    "DELEGATECALL"),    # Message-call into this account with ...

# special: from https://github.com/trailofbits/evm-opcodes
(0xfa,	  "STATICCALL"),
(0xfb,	  "CREATE2"),
(0xfc,	  "TXEXECGAS"),

(0xfd,    "REVERT"),
(0xfe,    "INVALID"),
(0xff,    "SELFDESTRUCT"),    # Halt execution and register account for ..

] # end opcodes_table


# this is an enumeration of all the different *types* of instructions, e.g.
# ADD, MUL etc.
class instructions:
	pass # initialized below

opcodes_map = {}

# NOTE: this magic sets instructions.ADD = "ADD" etc.
for opcode, name in opcodes_table:
	instructions.__dict__[name] = name
	opcodes_map[opcode] = name


# this class is for concrete instances of an instruction in a contract, so
# that it has an address.
class Instruction:
	def __init__(self, ins, arg, addr, bytecode):
		self.ins = ins
		self.arg = arg
		self.address = addr
		self.bytecode = bytecode
	
	def __str__(self):
		result = ""#"0x%02x: " % self.address
		if self.arg is None:
			result += self.ins
		else:
			result += "%s %s" % (self.ins, hex(self.arg).rstrip("L"))
		return result

class BasicBlock:
	def __init__(self, instructions, address):
		self.instructions = instructions
		self.address = address
	
	def __str__(self):
		out  = "0x%x:\n" % self.instructions[0].address
		for ins in self.instructions:
			out += str(ins) + "\n"
		return out


# instructions which end a BB
ending_instructions = [
	instructions.JUMP,
	instructions.JUMPI,
	instructions.MESSAGECALL,
	instructions.HALTRETURN,
	instructions.DELEGATECALL,
	instructions.SELFDESTRUCT,
	instructions.STOP,
	instructions.REVERT,
	instructions.UNKNOWN, # because it results in a revert
]

def split(llir):
	instrs = []
	result = []

	for ins in llir:
		if ins.ins == instructions.JUMPDEST:
			if len(instrs) == 0:
				instrs.append(ins)
			else:
				result.append(BasicBlock(instrs, instrs[0].address))
				instrs = [ins]

		else:
			instrs.append(ins)
			if ins.ins in ending_instructions:
				result.append(BasicBlock(instrs, instrs[0].address))
				instrs = []

	if len(instrs) != 0:
		result.append(BasicBlock(instrs, instrs[0].address))

	return result


