__vmcalls = [
	"balance",
	"blockhash",
	"byte",
	"calldataload",
	"calldataread",
	"coderead",
	"returndataread",
	"haltreturn",
	"log",
	"messagecall",
	"delegatecall",
	"msize",
	"returndatasize",
	"revert",
	"selfdestruct",
	"sha3",
	"stop",
	"extcodesize",
	"codesize",
	"create",
]

def get_vmcalls():
	return __vmcalls

class vmcalls:
	# initialized below
	pass

# NOTE: this magic sets instructions.ADD = "ADD" etc.
for name in __vmcalls:
	vmcalls.__dict__[name] = name

pure_vmcalls = [
	vmcalls.calldataload,
	vmcalls.sha3,
]

terminating_vmcalls = [
	vmcalls.haltreturn,
	vmcalls.stop,
	vmcalls.revert,
	vmcalls.selfdestruct,
]

