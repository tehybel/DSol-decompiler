contract Bytes {
	bytes data;

	function set_data(uint index, byte value) {
		data[index] = value;
	}

	function get_data(uint index) returns (byte) {
		return data[index];
	}

}
