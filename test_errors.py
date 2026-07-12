"""
Tests for strict error handling and parser edge cases.
"""

import unittest

from wasm_interpreter import (
    SExpressionParser,
    WasmInterpreter,
    WasmTrap,
    WasmValue,
)


def load(source: str) -> WasmInterpreter:
    interpreter = WasmInterpreter()
    for expr in SExpressionParser().parse(source):
        interpreter.load_module(expr)
    return interpreter


class TestStrictErrors(unittest.TestCase):
    def test_unsupported_instruction_raises(self):
        interp = load('(module (func (export "f") (result i32) (i32.frobnicate)))')
        with self.assertRaises(NotImplementedError):
            interp.invoke("f", [])

    def test_unknown_local_raises(self):
        interp = load('(module (func (export "f") (result i32) (local.get $missing)))')
        with self.assertRaises(ValueError):
            interp.invoke("f", [])

    def test_wrong_argument_count_raises(self):
        interp = load(
            '(module (func (export "f") (param $x i32) (result i32) (local.get $x)))'
        )
        with self.assertRaises(ValueError):
            interp.invoke("f", [])
        with self.assertRaises(ValueError):
            interp.invoke("f", [WasmValue("i32", 1), WasmValue("i32", 2)])

    def test_unknown_function_raises(self):
        interp = load("(module)")
        with self.assertRaises(ValueError):
            interp.invoke("nope", [])

    def test_out_of_range_constant_raises(self):
        interp = WasmInterpreter()
        with self.assertRaises(ValueError):
            interp.parse_i32_const("0x1FFFFFFFF")
        with self.assertRaises(ValueError):
            interp.parse_i32_const("4294967296")
        with self.assertRaises(ValueError):
            interp.parse_i32_const("-2147483649")

    def test_divide_by_zero_traps(self):
        interp = load(
            '(module (func (export "f") (param $x i32) (param $y i32) (result i32)'
            " (i32.div_s (local.get $x) (local.get $y))))"
        )
        with self.assertRaises(WasmTrap):
            interp.invoke("f", [WasmValue("i32", 1), WasmValue("i32", 0)])


class TestParserEdgeCases(unittest.TestCase):
    def test_unnamed_params_use_numeric_indices(self):
        interp = load(
            '(module (func (export "add") (param i32) (param i32) (result i32)'
            " (i32.add (local.get 0) (local.get 1))))"
        )
        result = interp.invoke("add", [WasmValue("i32", 3), WasmValue("i32", 4)])
        self.assertEqual(result, WasmValue("i32", 7))

    def test_multi_value_param_declaration(self):
        interp = load(
            '(module (func (export "add") (param i32 i32) (result i32)'
            " (i32.add (local.get 0) (local.get 1))))"
        )
        result = interp.invoke("add", [WasmValue("i32", 3), WasmValue("i32", 4)])
        self.assertEqual(result, WasmValue("i32", 7))

    def test_dollar_named_function(self):
        interp = load("(module (func $g (result i32) (i32.const 7)))")
        self.assertEqual(interp.invoke("$g", []), WasmValue("i32", 7))

    def test_folded_sequence_shares_stack(self):
        interp = load(
            '(module (func (export "f") (result i32)'
            " (i32.const 1) (i32.const 2) (i32.add)))"
        )
        self.assertEqual(interp.invoke("f", []), WasmValue("i32", 3))

    def test_comment_delimiters_inside_strings_are_preserved(self):
        parser = SExpressionParser()
        source = '(module (func (export "f") (result i32) (i32.const 1)) (data "(;"))'
        self.assertEqual(parser.strip_block_comments(source), source)
        interp = load(source)
        self.assertEqual(interp.invoke("f", []), WasmValue("i32", 1))

    def test_underscore_separators_and_signed_hex(self):
        interp = load(
            '(module (func (export "f") (result i32) (i32.const 1_000))'
            '        (func (export "g") (result i32) (i32.const +0x10)))'
        )
        self.assertEqual(interp.invoke("f", []), WasmValue("i32", 1000))
        self.assertEqual(interp.invoke("g", []), WasmValue("i32", 16))


if __name__ == "__main__":
    unittest.main()
