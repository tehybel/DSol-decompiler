
class CriticalError(Exception):
	pass

def critical(text):
	print("/!\\ critical error: " + text + " /!\\\n")
	raise CriticalError()

def warn(text):
	print("Warning: %s" % text)
