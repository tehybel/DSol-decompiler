contract Loop {

	function foo () external returns (int) {
		int result = 0;
		int i = 0;
		while (i < 0x10) {
			result += i;
		}
		return result;
	}

}
