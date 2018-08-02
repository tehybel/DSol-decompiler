import os
import sys
import utils
import decompiler
import traceback
import time
import json
import signal

TIMEOUT = 180

"""
decompilation {

	running_time: 123,
	
	success {
		num_funcs: 333,
		num_gotos: 123,
		num_funcs_with_gotos: 123,
		goto_func_complexities: [2,3,4],
		other_func_complexities: [3,1,2],
		output: "foooo",
		num_evm_instrs: 123,
	}

	OR:

	failure {
		error: "blabla",
	}

}

"""

filename = "../evaluation/contracts/"
filename += sys.argv[1]

out_filename = filename.replace("contracts", "raw_results") + ".json"
if os.path.isfile(out_filename):
	print("Already decompiled %s" % filename)
	exit(0)

#filename += "0xaec8162438b83646518f3bf3a70b048979f81fab" # works
#filename += "0x7d6d887c4078e6634102329f41725d21c0756aae" # breaks

contents = open(filename).read()
bytecode = utils.decode_bytecode(contents)


def handler(signum, frame):
	raise Exception("timeout")
signal.signal(signal.SIGALRM, handler)
signal.alarm(TIMEOUT)

################

print("Decompiling %s" % filename)

d = decompiler.Decompiler()

data = {}
begin = time.time()
try:
	contract, ast, code = d.decompile(bytecode)
	end = time.time()
	success = {}
	success["num_funcs"] = len(ast.functions)
	success["num_gotos"] = d.stats["num_gotos"]
	success["num_funcs_with_gotos"] = len(d.stats["funcs_with_gotos"])

	goto_func_complexities = []
	other_func_complexities = []
	for f in ast.functions:
		if f in d.stats["funcs_with_gotos"]:
			goto_func_complexities.append(f.num_statements())
		else:
			other_func_complexities.append(f.num_statements())

	success["goto_func_complexities"] = goto_func_complexities
	success["other_func_complexities"] = other_func_complexities

	success["num_evm_instrs"] = d.stats["num_evm_instrs"]

	print("Success:")
	print(success)
		
	success["output"] = code

	data["success"] = success

except Exception as e:
	err = traceback.format_exc(e)
	print("Failure:")
	print(err)

	end = time.time()
	data["failure"] = {
		"error": err
	}

data["running_time"] = (end - begin)


result = json.dumps(data)

f = open(out_filename, "w")
f.write(result)
f.close()

