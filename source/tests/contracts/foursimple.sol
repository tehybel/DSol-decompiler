contract FourSimple {
	
	function a (int x) internal returns (int) {
		if (x > 0)
			return 1;
		else
			return 0;
	}

	function b (int x) internal returns (int) {
		return 0x11*x;
	}

	function c () external returns (int, int) {
		int x = 0x22;
		x = b(x);
		int y = 0x33;
		if (x != 0) {
			y = a(x);
		}

		return (x, y);
	}

	function d (int x) external returns (int) {
		return a(b(x));
	}
}
