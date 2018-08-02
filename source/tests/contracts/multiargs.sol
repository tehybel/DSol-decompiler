contract Multiargs {
	function f(uint x, uint y, uint z) external returns (uint) {
		return x*y*z*0x11;
	}
}

