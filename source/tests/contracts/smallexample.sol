contract SmallExample {

	function myfunc (uint x) external returns (uint) {
		uint result = 0;

		if ((x % 2) == 1) {
			result += 1;
		}
		else {
			result += 2;
		}

		for (uint i = 0; i < x; i++) {
			result += 2;
		}

		return result/3 + 5;
	}

}
