# DSol
A practical Ethereum smart contract decompiler


## What does DSol do?

DSol translates the raw EVM bytecode of a smart contract into a high-level language that resembles Solidity.

## Get DSol

`$ git clone https://github.com/tehybel/DSol-decompiler.git`

## Usage

```
# Navigate to the source directory
$ cd DSol-decompiler/source/

# Ensure the pysha3 module is installed
$ sudo pip2 install pysha3

# Run the software with python 2.7
$ python2 main.py 

# Supply a file containing hex-encoded bytecode or a .json file.
$ python2 main.py tests/bytecode/foursimple.bc 
$ python2 main.py tests/build/contracts/Minimal.json

# Run unit tests (optional)
$ python2 main.py test
```

## What is DSol useful for?

You can use DSol to:
- validate the output of the Solidity compiler
- understand how Solidity language features are implemented at the EVM level
- understand and audit contracts without public source code
- help recover lost source code
- discover backdoors and compiler bugs (if any)

## About the project

DSol is the result of half a year's full-time work on my master's thesis. For technical details and documentation, see my [thesis](https://github.com/tehybel/DSol-decompiler/raw/master/thesis/DSol-thesis-Thomas-Hybel.pdf).


## Licensing

All files in this project use the MIT license.
