contract NonCom {
	function f(uint x) external returns (uint) {
		return x / 3;
	}
	
	function g(uint x) external returns (uint) {
		return x & 0xee;
	}

	function h(uint x) external returns (uint) {
		return x % 3;
	}

	function i(uint x) external returns (uint) {
		return x & 2;
	}

	function j(uint x) external returns (uint) {
		return x**2;
	}

}
