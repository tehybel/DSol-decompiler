contract IfElseSame {
    function f(uint x) external returns (uint) {
        uint result = 0;
        if (x == 1) {
            result += 1;
        } else {
            result += 1;
        }

        if (x == 2) {
        } else {
        }

        if ((x % 2) == 0) {
            result += 1;
        }

        return result;
    }
}
