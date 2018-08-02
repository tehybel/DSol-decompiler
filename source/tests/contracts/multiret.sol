contract Multiret {
	function f (uint x) external returns (uint, uint) {
		return (x*0x11, x*0x22);
	}

}
