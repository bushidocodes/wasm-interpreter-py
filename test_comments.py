"""
Tests ported from the WebAssembly spec comments.wast test suite.

Covers block-comment stripping (including nesting and ;; inside block comments),
the module-quote mechanism, and line-comment termination by LF, CR, and CRLF.
"""

import os
import unittest

from wasm_interpreter import (
    SExprNode,
    SExpressionParser,
    WasmInterpreter,
    evaluate_assert_return,
)

WAST_FILE = os.path.join(os.path.dirname(__file__), "comments.wast")


class TestBlockCommentStripping(unittest.TestCase):
    """Unit tests for SExpressionParser.strip_block_comments."""

    def setUp(self):
        self.parser = SExpressionParser()

    def strip(self, text):
        return self.parser.strip_block_comments(text)

    def test_simple_block_comment(self):
        self.assertEqual(self.strip("(;hello;)"), " ")

    def test_nested_block_comment(self):
        self.assertEqual(self.strip("(;outer(;inner;)outer;)"), " ")

    def test_deeply_nested_block_comment(self):
        self.assertEqual(self.strip("(;a(;b(;c;)b;)a;)"), " ")

    def test_line_comment_inside_block_comment(self):
        self.assertEqual(self.strip("(;foo;;bar;)"), " ")

    def test_line_comment_newline_inside_block_comment(self):
        # ;; does not close the block comment; ;) on next line does
        self.assertEqual(self.strip("(;foo;;bar\n;)"), " ")

    def test_block_comment_adjacent_to_code(self):
        self.assertEqual(self.strip("(module(;comment;))"), "(module )")

    def test_multiple_block_comments(self):
        self.assertEqual(self.strip("(;a;)x(;b;)"), " x ")

    def test_no_comments_unchanged(self):
        self.assertEqual(self.strip("(module)"), "(module)")

    def test_unterminated_block_comment_consumed(self):
        # Unterminated comment is silently consumed as a single space
        self.assertEqual(self.strip("(;never closed"), " ")


class TestCommentsParsing(unittest.TestCase):
    """Verify that every comment form in comments.wast parses without error."""

    def test_file_parses_without_error(self):
        with open(WAST_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        parser = SExpressionParser()
        expressions = parser.parse(content)
        # File contains several module declarations plus 3 assert_return forms
        self.assertGreater(len(expressions), 0)


class TestCommentsExecution(unittest.TestCase):
    """Run the assert_return assertions from comments.wast (newline-recognition section)."""

    @classmethod
    def setUpClass(cls):
        with open(WAST_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        parser = SExpressionParser()
        expressions = parser.parse(content)

        cls.interpreter = WasmInterpreter()
        cls.assert_exprs = {}

        for expr in expressions:
            if not (expr.children and isinstance(expr.children[0], SExprNode)):
                continue
            tag = expr.children[0].value
            if tag == "module":
                cls.interpreter.load_module(expr)
            elif tag == "assert_return":
                invoke = expr.children[1]
                if (
                    invoke.children
                    and len(invoke.children) > 1
                    and isinstance(invoke.children[0], SExprNode)
                    and invoke.children[0].value == "invoke"
                ):
                    name = invoke.children[1].value.strip('"')
                    cls.assert_exprs[name] = expr

    def test_f1_lf_terminated_line_comment(self):
        """Line comment ended by LF (\\0a) — (return (i32.const 2)) must execute."""
        self.assertIn("f1", self.assert_exprs)
        self.assertTrue(evaluate_assert_return(self.interpreter, self.assert_exprs["f1"]))

    def test_f2_cr_terminated_line_comment(self):
        """Line comment ended by bare CR (\\0d) — (return (i32.const 2)) must execute."""
        self.assertIn("f2", self.assert_exprs)
        self.assertTrue(evaluate_assert_return(self.interpreter, self.assert_exprs["f2"]))

    def test_f3_crlf_terminated_line_comment(self):
        """Line comment ended by CRLF (\\0d\\0a) — (return (i32.const 2)) must execute."""
        self.assertIn("f3", self.assert_exprs)
        self.assertTrue(evaluate_assert_return(self.interpreter, self.assert_exprs["f3"]))
