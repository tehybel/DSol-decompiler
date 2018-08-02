contract PostTestedLoop {

	function f() internal returns (int) {
		return 0x11;
	}

	function foo (int ii) external returns (int) {
		int i = ii;
		do {
			if (ii > 0x22)
				i += f();
			else
				i += 0x33;
		} while (i < 0x123);
		return i;
	}

}
