contract Endless {

	function foo (int ii) external returns (int) {
		int i = ii;
		while (true) {
			i = i*3 + 5;
			i /= 2;
			if (ii == 0x11) {
				i += 0x22;
				break;
			}

			if (ii == 0x33) {
				i += 0x44;
				i += 0x55;
				return i + i;
			}

			if (ii == 0x66) {
				return i*4*ii;
			}

			if (ii == 0x77) {
				break;
			}
		}

		i += 0x88;
		return i + ii + 0x99;
	}

}
