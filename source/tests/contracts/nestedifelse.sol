contract NestedIfElse {
	
	function f (uint x, uint y) returns (uint) {
		
		uint result = 1;
		
		if (x == 1) {
			if (y == 1) {
				result = 2;
			}
			else {
				result = 3;
			}
		}
		else {
			if (y == 1) {
				result = 4;
			}
			else {
				result = 5;
			}
		}
		return result;
	}

}
