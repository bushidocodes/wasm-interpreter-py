"""
Tests for the WebAssembly spec comment syntax test suite (comments.wast).
"""

import os
import unittest

from wasm_interpreter import (
    SExprNode,
    WasmInterpreter,
    evaluate_assert_return,
    parse_wast_file,
)

WAST_FILE = os.path.join(os.path.dirname(__file__), "comments.wast")


class TestCommentsWast(unittest.TestCase):
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

        cls.assert_exprs = [
            expr
            for expr in expressions
            if (
                expr.children
                and isinstance(expr.children[0], SExprNode)
                and expr.children[0].value == "assert_return"
            )
        ]

    def test_all_assertions(self):
        failed = 0
        for expr in self.assert_exprs:
            if not evaluate_assert_return(self.interpreter, expr):
                failed += 1

        self.assertEqual(
            failed,
            0,
            f"{failed}/{len(self.assert_exprs)} assertions failed",
        )


if __name__ == "__main__":
    unittest.main()
