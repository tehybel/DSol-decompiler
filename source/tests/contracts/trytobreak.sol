// I'll try to cover as many weird edge cases here as possible
contract TryToBreak {
	
	function g (uint x) external returns (int) {
		int result = 22;
		do {
			if (x == 1) {
				return 12;
			}
			else if (x == 2) {
				return 34;
			}
			else if (x == 3) {
				result = 111;
				break;
			}
			else {
				while (true) {
					result += 1;
					break;
				}
				result += 2;
				break;
			}
			result += 1;
		} while (x == 42);

		result -= 33;
		return result;
	}

	function h (uint x) external returns (uint) {
		uint result = 0;
		while (result != x) {
			result++;
			++result;
			if (result == 2)
				continue;
			result += 2;
		}
		return result;
	}

	function i (uint x) external returns (uint) {
		uint result = 0;
		while (true) {
			if (result > 10)
				break;

			if (x == 3) {
				result += 5;
				continue;
			}
			result += 2;
			if (x == 4) {
				continue;
			}

			break;
		}
		return result;
	}

	function j () external {
		while (true) {
			if (true)
				break;
			else
				break;
			break;
			break;
			break;
		}
	}

	function k(uint x) external returns (uint) {
		while (true) {
			if (x == 42) {
				return 1;
			} else {
				return 2;
			}
		}
	}

	function l (uint x) external returns (uint) {
		uint result = 0;
		while (true) {
			while (true) {
				result += 1;
				break;
			}

			if (x == 1) {
				result += 2;
				break;
			}
			if (x == 2) {
				result += 3;
				break;
			}
			if (x == 3) {
				result += 5;
				break;
			}
			if (x == 4) {
				result += 7;
				break;
			}
			result += 11;
			break;
		}
		return result;
	}

}
