contract Array {
	uint[] nums;
	uint offset;

	function Array() {
		nums = new uint[](10);
	}

	function add_num(uint num) {
		nums[offset++] = num;
	}

	function get_num(uint offset) external returns (uint) {
		return nums[offset];
	}

}
