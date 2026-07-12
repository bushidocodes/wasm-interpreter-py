#!/usr/bin/env python3
"""
WebAssembly Interpreter CLI — runs assertions from a .wast file.
"""

import os
import sys

from wasm_interpreter import (
    SExprNode,
    WasmInterpreter,
    evaluate_assert_return,
    evaluate_assert_trap,
    parse_wast_file,
)


def main():
    if len(sys.argv) > 1:
        wast_file = sys.argv[1]
    else:
        wast_file = os.path.join(os.path.dirname(__file__), "i32.wast")

    print("Parsing WebAssembly S-expressions...")
    print("=" * 50)

    try:
        expressions, content = parse_wast_file(wast_file)
    except (OSError, ValueError) as e:
        print(f"Error reading file '{wast_file}': {e}")
        sys.exit(1)

    if not expressions:
        print("No expressions found.")
        sys.exit(1)

    print(f"Successfully parsed {len(expressions)} top-level expressions")
    print(f"File size: {len(content)} characters")

    interpreter = WasmInterpreter()

    module_exprs = [
        expr
        for expr in expressions
        if (
            expr.children
            and isinstance(expr.children[0], SExprNode)
            and expr.children[0].value == "module"
        )
    ]

    if not module_exprs:
        print("No module found in the file")
        sys.exit(1)

    print(f"\nLoading {len(module_exprs)} WebAssembly module(s)...")
    for module_expr in module_exprs:
        interpreter.load_module(module_expr)

    print(f"Loaded {len(interpreter.functions)} functions:")
    for name, func in interpreter.functions.items():
        params_str = ", ".join(f"{pname}: {ptype}" for pname, ptype in func.params)
        result_str = f" -> {func.result}" if func.result else ""
        print(f"  - {name}({params_str}){result_str}")

    print("\nExecuting assert_return and assert_trap tests...")
    print("-" * 40)

    passed = 0
    failed = 0

    for expr in expressions:
        if not (
            expr.children
            and isinstance(expr.children[0], SExprNode)
        ):
            continue
        directive = expr.children[0].value
        if directive == "assert_return":
            success = evaluate_assert_return(interpreter, expr)
        elif directive == "assert_trap":
            success = evaluate_assert_trap(interpreter, expr)
        else:
            continue
        if success:
            passed += 1
        else:
            failed += 1

    print(f"\nTest Results:")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print(f"  Total:  {passed + failed}")

    if failed == 0 and passed > 0:
        print("All tests passed!")
    elif passed > 0:
        print(f"{passed}/{passed + failed} tests passed")
        sys.exit(1)
    else:
        print("No tests passed")
        sys.exit(1)


if __name__ == "__main__":
    main()
