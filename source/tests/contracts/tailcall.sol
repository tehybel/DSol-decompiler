contract TailCall {
	function h(uint r) returns (uint) {
		return r+3;
	}
	function f (uint x) external returns (uint) {
		uint result = 1;
		result += x*2;
		return h(result);
	}
}
