contract SmallTypes2 {

	function f (int x) internal returns (int8) {
		int8 result = 0;
		for(int i = 0; i < x; i++) {
			result += 3;
		}
		return result;
	}

	function g(int x) external returns (int) {
		int8 r = f(x);

		if (r == 3)
			return 0x11;

		return r;
	}

}
