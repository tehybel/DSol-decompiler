/*
def g(x):
    return x*2

# 0xb3de648b
def f(i):
    result = 0
    result += g(i+1)
    result += g(i+2)
    result += g(i+3)
    result += g(i+4)
    result += g(i+5)
    return result

# 0xcb97492a
def h(j):
    result = 1
    result += g(j) + g(j) + g(j)
    result += g(g(g(j)))
    return result

*/
contract Multicall {
	
	function g (uint x) internal returns (uint) {
		return x*2;
	}
	
	function f (uint i) external returns (uint result) {
		result += g(i+1);
		result += g(i+2);
		result += g(i+3);
		result += g(i+4);
		result += g(i+5);
	}

	function h (uint j) external returns (uint) {
		uint result = 1;
		result += g(j) + g(j) + g(j);
		result += g(g(g(j)));
		return result;
	}


}
