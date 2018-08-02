contract Storage {
	address last_sender;
	uint magic_value;

	function f(uint x) returns (uint) {
		if (x == magic_value) {
			magic_value += 1;
			return 0x1234;
		}

		last_sender = msg.sender;
		return x;
	}
}
