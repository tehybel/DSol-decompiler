contract Struct {
	struct winner {
		uint age;
		address addr;
		bool did_win;
		bool is_old;
	}

	winner w;

	function set_age(uint a) external {
		w.age = a;
	}

	function set_addr(address addr) external {
		w.addr = addr;
	}

	function set_win() external {
		w.did_win = true;
	}

	function get_winner() external returns (winner) {
		return w;
	}

}
