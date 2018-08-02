contract SmallTypes {

	function f (int x) external returns (int8) {
		int8 result = 0;
		for(int i = 0; i < x; i++) {
			result += 3;
		}
		return result;
	}

}
