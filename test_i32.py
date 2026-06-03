"""
Tests for the i32 WebAssembly spec test suite (i32.wast).
"""

import os
import unittest

from wasm_interpreter import (
    SExprNode,
    WasmInterpreter,
    evaluate_assert_return,
    evaluate_assert_trap,
    parse_wast_file,
)

WAST_FILE = os.path.join(os.path.dirname(__file__), "i32.wast")


class TestI32Wast(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        expressions, _ = parse_wast_file(WAST_FILE)

        cls.interpreter = WasmInterpreter()
        for expr in expressions:
            if (
                expr.children
                and isinstance(expr.children[0], SExprNode)
                and expr.children[0].value == "module"
            ):
                cls.interpreter.load_module(expr)
                break

        cls.assert_exprs = [
            expr
            for expr in expressions
            if (
                expr.children
                and isinstance(expr.children[0], SExprNode)
                and expr.children[0].value in ("assert_return", "assert_trap")
            )
        ]

    def test_all_assertions(self):
        failed = 0
        for expr in self.assert_exprs:
            directive = expr.children[0].value
            if directive == "assert_return":
                if not evaluate_assert_return(self.interpreter, expr):
                    failed += 1
            else:
                if not evaluate_assert_trap(self.interpreter, expr):
                    failed += 1

        self.assertEqual(
            failed,
            0,
            f"{failed}/{len(self.assert_exprs)} assertions failed",
        )


if __name__ == "__main__":
    unittest.main()
