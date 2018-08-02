contract String {

	function stringsEqual(string memory _a, string memory _b) internal returns (bool) {
		bytes memory a = bytes(_a);
		bytes memory b = bytes(_b);
		if (a.length != b.length)
			return false;
		for (uint i = 0; i < a.length; i ++)
			if (a[i] != b[i])
				return false;
		return true;
	}

	function g(int x, string s, string r) returns (string) {
		if (stringsEqual(s, r))
			return "[::]URL:;._.=//**-+thisisAstringThatContaINsManyInvalidOPC0des!![]/\\()##%&/(-<-,";
		return s;
	}

	function f(int x) external returns (string) {
		if (x == 1)
			return "one";
		else if (x == 2)
			return "two";


		return g(x, "foo", "baz");
	}

}

