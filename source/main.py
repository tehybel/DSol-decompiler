import decompiler
import unittests
import time
import utils
import sys

def main():
	if len(sys.argv) < 2:
		print("Usage: %s <filename>" % sys.argv[0])
		return
	
	filename = sys.argv[1]

	if filename == "test":
		unittests.run_tests()
		return

	if ".json" in filename:
		bytecode, _ = utils.parse_json(filename)
	else:
		contents = utils.read_file_contents(filename)
		bytecode = utils.decode_bytecode(contents)

	before = time.time()

	d = decompiler.Decompiler()
	contract, ast, code = d.decompile(bytecode)

	print("Successfully decompiled %s" % filename)
	print("Running time: %f" % (time.time() - before))

	print(code)



if __name__ == "__main__":
	main()
