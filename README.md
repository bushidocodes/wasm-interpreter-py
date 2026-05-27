# wasm-interpreter-py

A WebAssembly interpreter written in Python. Parses and executes WebAssembly Text Format (WAT/WAST) using S-expressions.

## Status

Currently implements **i32 arithmetic operations**:

| Instruction | Description |
|---|---|
| `i32.add` | Addition with 32-bit overflow wrapping |
| `i32.sub` | Subtraction with 32-bit underflow wrapping |
| `i32.mul` | Multiplication with 32-bit overflow wrapping |
| `i32.div_s` | Signed division, truncates toward zero |
| `i32.div_u` | Unsigned division |
| `i32.rem_s` | Signed remainder (sign follows dividend) |
| `i32.rem_u` | Unsigned remainder |

Trap semantics are implemented for divide-by-zero and signed overflow (`INT_MIN / -1`).

## Usage

```
python main.py
```

This loads `i32.wast` and runs all the test assertions in it, printing pass/fail for each and a summary at the end.

## Tests

Tests are written in the [WebAssembly spec test format](https://github.com/WebAssembly/spec/tree/main/test/core) using `assert_return` and `assert_trap`:

```wat
(assert_return (invoke "add" (i32.const 1) (i32.const 2)) (i32.const 3))
(assert_trap  (invoke "div_s" (i32.const 1) (i32.const 0)) "integer divide by zero")
```

`i32.wast` contains ~100 test cases covering all supported operations, including edge cases like overflow wrapping, signed/unsigned interpretation, and trap conditions.

## Architecture

Everything lives in `main.py`:

- **`SExpressionParser`** — tokenizes and parses S-expression text into a tree
- **`WasmInterpreter`** — loads a module and evaluates function calls against it
- **`evaluate_assert_return` / `evaluate_assert_trap`** — test harness that runs spec assertions

## Requirements

Python 3. No external dependencies.
