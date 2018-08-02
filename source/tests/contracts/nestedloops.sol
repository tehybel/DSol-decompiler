contract NestedLoops {

	function foo () external returns (int) {
		int result = 0;
		int i = 0;
		while (i < 0x10) {
			int j = 0;

			while (j < 0x20) {
				j += 2;
				result += i;
			}

			i += 1;
		}
		return result;
	}

}
