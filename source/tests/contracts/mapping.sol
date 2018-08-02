contract Mapping {
	
	mapping (uint => address) m;
	mapping (uint => address) n;
	
	function set(uint x, address v) external {
		n[x] = m[x] = v;
	}

	function get(uint x) external returns (address) {
		if (x < 100)
			return m[x];
		else
			return n[x];
	}
}
