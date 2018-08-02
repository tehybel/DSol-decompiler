contract Log {
    function f() public payable {
        bytes32 _id = 0x420042;
        log3(
            bytes32(msg.value),
            bytes32(0x50cb9fe53daa9737b786ab3646f04d0150dc50ef4e75f59509d83667ad5adb20),
            bytes32(msg.sender),
            _id
        );
    }
}
