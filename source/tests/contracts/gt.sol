contract GT {
	function f (uint x) external returns (uint) {
		if (x > 0x11)
			return 0x44;
		return x;
	}
}
