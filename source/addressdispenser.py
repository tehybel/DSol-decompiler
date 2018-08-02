
address = 0x111000
def get_new_address():
	global address
	result = address
	address += 0x1000
	return result

