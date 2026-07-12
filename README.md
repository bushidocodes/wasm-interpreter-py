# wasm-interpreter-py

A WebAssembly interpreter written in Python. Parses and executes WebAssembly Text Format (WAT/WAST) using S-expressions.

## Status

Currently implements the **i32 numeric instructions**:

| Group | Instructions |
|---|---|
| Arithmetic | `i32.add`, `i32.sub`, `i32.mul`, `i32.div_s`, `i32.div_u`, `i32.rem_s`, `i32.rem_u` |
| Bitwise | `i32.and`, `i32.or`, `i32.xor` |
| Shifts / rotates | `i32.shl`, `i32.shr_s`, `i32.shr_u`, `i32.rotl`, `i32.rotr` |
| Bit counting | `i32.clz`, `i32.ctz`, `i32.popcnt` |
| Comparisons | `i32.eqz`, `i32.eq`, `i32.ne`, `i32.lt_s`, `i32.lt_u`, `i32.le_s`, `i32.le_u`, `i32.gt_s`, `i32.gt_u`, `i32.ge_s`, `i32.ge_u` |
| Sign extension | `i32.extend8_s`, `i32.extend16_s` |

Trap semantics are implemented for divide-by-zero and signed overflow (`INT_MIN / -1`).
Unsupported instructions, unknown locals, and malformed constants raise errors rather
than silently producing wrong results.

## Usage

```
python main.py [file.wast]
```

This loads `i32.wast` (or the given `.wast` file) and runs all the test assertions in it,
printing pass/fail for each and a summary at the end. The exit code is non-zero if any
assertion fails.

## Tests

Tests are written in the [WebAssembly spec test format](https://github.com/WebAssembly/spec/tree/main/test/core) using `assert_return` and `assert_trap`:

```wat
(assert_return (invoke "add" (i32.const 1) (i32.const 2)) (i32.const 3))
(assert_trap  (invoke "div_s" (i32.const 1) (i32.const 0)) "integer divide by zero")
```

`i32.wast` contains 372 test cases covering all supported operations, including edge cases
like overflow wrapping, signed/unsigned interpretation, shift counts ≥ 32, and trap
conditions. Every expected value has been cross-validated against
[wasmtime](https://wasmtime.dev/).

## Architecture

Core logic lives in `wasm_interpreter.py`; `main.py` is the CLI entry point.

**`wasm_interpreter.py`**

- **`SExpressionParser`** — tokenizes and parses S-expression text into a tree
- **`WasmInterpreter`** — loads a module and evaluates function calls against it
- **`evaluate_assert_return` / `evaluate_assert_trap`** — test harness that runs spec assertions

**`main.py`**

- **`main()`** — CLI entry point; loads a `.wast` file, runs all assertions, and prints a summary

## Requirements

Python 3. No external dependencies.
