"""
WebAssembly Interpreter library — S-expression parser, runtime, and assertion helpers.
"""

import re
from typing import Union, List, Any, Dict, Optional


class SExprNode:
    """Represents a node in the S-expression tree"""

    def __init__(self, value: Union[str, List[Any]]):
        self.value = value
        self.children = []

        if isinstance(value, list):
            self.children = value
            self.value = None

    def __repr__(self):
        if self.value is not None:
            return f"SExprNode({repr(self.value)})"
        else:
            return f"SExprNode({self.children})"

    def pretty_print(self, indent=0):
        """Pretty print the S-expression tree"""
        spaces = "  " * indent
        if self.value is not None:
            return f"{spaces}{self.value}"
        else:
            result = f"{spaces}(\n"
            for child in self.children:
                if isinstance(child, SExprNode):
                    result += child.pretty_print(indent + 1) + "\n"
                else:
                    result += f"{spaces}  {child}\n"
            result += f"{spaces})"
            return result


class WasmValue:
    """Represents a WebAssembly value"""

    def __init__(self, value_type: str, value: int):
        self.type = value_type
        self.value = value

    def __repr__(self):
        return f"WasmValue({self.type}, {self.value})"

    def __eq__(self, other):
        if not isinstance(other, WasmValue):
            return False
        return self.type == other.type and self.value == other.value


class WasmFunction:
    """Represents a WebAssembly function"""

    def __init__(
        self, name: str, params: List[tuple], result: Optional[str], body: SExprNode
    ):
        self.name = name
        self.params = params
        self.result = result
        self.body = body

    def __repr__(self):
        return f"WasmFunction({self.name}, {self.params} -> {self.result})"


class WasmInterpreter:
    """Simple WebAssembly interpreter for i32 operations"""

    def __init__(self):
        self.functions: Dict[str, WasmFunction] = {}
        self.local_vars: Dict[str, WasmValue] = {}

    def parse_i32_const(self, value_str: str) -> int:
        """Parse i32 constant from string"""
        if value_str.startswith("0x"):
            val = int(value_str, 16)
            if val >= 0x80000000:
                val -= 0x100000000
            return val
        elif value_str.startswith("-0x"):
            val = -int(value_str[3:], 16)
            val = val & 0xFFFFFFFF
            if val >= 0x80000000:
                val -= 0x100000000
            return val
        else:
            val = int(value_str)
            val = val & 0xFFFFFFFF
            if val >= 0x80000000:
                val -= 0x100000000
            return val

    def load_module(self, module_expr: SExprNode):
        """Load a WebAssembly module"""
        if not module_expr.children or not isinstance(
            module_expr.children[0], SExprNode
        ):
            return

        if module_expr.children[0].value != "module":
            return

        for child in module_expr.children[1:]:
            if (
                isinstance(child, SExprNode)
                and child.children
                and len(child.children) > 0
                and isinstance(child.children[0], SExprNode)
                and child.children[0].value == "func"
            ):
                self._parse_function(child)

    def _parse_function(self, func_expr: SExprNode):
        """Parse a function definition"""
        export_name = None
        params = []
        result = None
        body = None

        for child in func_expr.children[1:]:
            if not isinstance(child, SExprNode) or not child.children:
                continue

            if len(child.children) > 0 and isinstance(child.children[0], SExprNode):
                directive = child.children[0].value

                if directive == "export" and len(child.children) > 1:
                    export_name = child.children[1].value.strip('"')
                elif directive == "param" and len(child.children) >= 3:
                    param_name = child.children[1].value
                    param_type = child.children[2].value
                    params.append((param_name, param_type))
                elif directive == "result" and len(child.children) > 1:
                    result = child.children[1].value
                elif isinstance(directive, str) and directive.startswith("i32."):
                    body = child

        if export_name and body:
            func = WasmFunction(export_name, params, result, body)
            self.functions[export_name] = func

    def invoke(self, func_name: str, args: List[WasmValue]) -> WasmValue:
        """Invoke a function with given arguments"""
        if func_name not in self.functions:
            raise ValueError(f"Function '{func_name}' not found")

        func = self.functions[func_name]
        old_locals = self.local_vars.copy()

        try:
            for i, (param_name, param_type) in enumerate(func.params):
                if i < len(args):
                    self.local_vars[param_name] = args[i]
                else:
                    self.local_vars[param_name] = WasmValue(param_type, 0)

            return self._evaluate_expression(func.body)

        finally:
            self.local_vars = old_locals

    def _evaluate_expression(self, expr: SExprNode) -> WasmValue:
        """Evaluate a WebAssembly expression"""
        if not isinstance(expr, SExprNode):
            return WasmValue("i32", 0)

        if expr.value is not None:
            if isinstance(expr.value, str):
                if expr.value in self.local_vars:
                    return self.local_vars[expr.value]
                try:
                    return WasmValue("i32", self.parse_i32_const(expr.value))
                except ValueError:
                    return WasmValue("i32", 0)
            return WasmValue("i32", 0)

        if not expr.children or len(expr.children) == 0:
            return WasmValue("i32", 0)

        if not isinstance(expr.children[0], SExprNode):
            return WasmValue("i32", 0)

        instruction = expr.children[0].value

        if instruction == "local.get" and len(expr.children) > 1:
            param_name = expr.children[1].value
            if param_name in self.local_vars:
                return self.local_vars[param_name]
            return WasmValue("i32", 0)

        elif instruction == "i32.const" and len(expr.children) > 1:
            value_str = expr.children[1].value
            return WasmValue("i32", self.parse_i32_const(value_str))

        elif instruction == "i32.add" and len(expr.children) >= 3:
            left = self._evaluate_expression(expr.children[1])
            right = self._evaluate_expression(expr.children[2])
            result = (left.value + right.value) & 0xFFFFFFFF
            if result >= 0x80000000:
                result -= 0x100000000
            return WasmValue("i32", result)

        elif instruction == "i32.sub" and len(expr.children) >= 3:
            left = self._evaluate_expression(expr.children[1])
            right = self._evaluate_expression(expr.children[2])
            result = (left.value - right.value) & 0xFFFFFFFF
            if result >= 0x80000000:
                result -= 0x100000000
            return WasmValue("i32", result)

        elif instruction == "i32.mul" and len(expr.children) >= 3:
            left = self._evaluate_expression(expr.children[1])
            right = self._evaluate_expression(expr.children[2])
            result = (left.value * right.value) & 0xFFFFFFFF
            if result >= 0x80000000:
                result -= 0x100000000
            return WasmValue("i32", result)

        elif instruction == "i32.div_s" and len(expr.children) >= 3:
            left = self._evaluate_expression(expr.children[1])
            right = self._evaluate_expression(expr.children[2])
            if right.value == 0:
                raise RuntimeError("integer divide by zero")
            if left.value == -2147483648 and right.value == -1:
                raise RuntimeError("integer overflow")
            result = int(left.value / right.value)
            return WasmValue("i32", result)

        elif instruction == "i32.div_u" and len(expr.children) >= 3:
            left = self._evaluate_expression(expr.children[1])
            right = self._evaluate_expression(expr.children[2])
            if right.value == 0:
                raise RuntimeError("integer divide by zero")
            left_unsigned = left.value & 0xFFFFFFFF
            right_unsigned = right.value & 0xFFFFFFFF
            result = left_unsigned // right_unsigned
            return WasmValue("i32", result)

        elif instruction == "i32.rem_s" and len(expr.children) >= 3:
            left = self._evaluate_expression(expr.children[1])
            right = self._evaluate_expression(expr.children[2])
            if right.value == 0:
                raise RuntimeError("integer divide by zero")
            quotient = int(left.value / right.value)
            result = left.value - (quotient * right.value)
            return WasmValue("i32", result)

        elif instruction == "i32.rem_u" and len(expr.children) >= 3:
            left = self._evaluate_expression(expr.children[1])
            right = self._evaluate_expression(expr.children[2])
            if right.value == 0:
                raise RuntimeError("integer divide by zero")
            left_unsigned = left.value & 0xFFFFFFFF
            right_unsigned = right.value & 0xFFFFFFFF
            result = left_unsigned % right_unsigned
            if result >= 0x80000000:
                result -= 0x100000000
            return WasmValue("i32", result)

        return WasmValue("i32", 0)


class SExpressionParser:
    """Parser for S-expressions in WebAssembly format"""

    def __init__(self):
        # Token patterns - ORDER MATTERS: HEX must come before NUMBER
        self.token_patterns = [
            (r"\(", "LPAREN"),
            (r"\)", "RPAREN"),
            (r'"[^"]*"', "STRING"),
            (r"0x[0-9a-fA-F]+", "HEX"),
            (r"[+-]?\d+\.?\d*", "NUMBER"),
            (r"[a-zA-Z_$][a-zA-Z0-9_$.-]*", "IDENTIFIER"),
            (r";;.*", "COMMENT"),
            (r"\s+", "WHITESPACE"),
        ]
        self.compiled_patterns = [
            (re.compile(pattern), token_type)
            for pattern, token_type in self.token_patterns
        ]

    def tokenize(self, text: str) -> List[tuple]:
        """Tokenize the input text"""
        tokens = []
        pos = 0

        while pos < len(text):
            matched = False

            for pattern, token_type in self.compiled_patterns:
                match = pattern.match(text, pos)
                if match:
                    value = match.group(0)
                    if token_type not in ["WHITESPACE", "COMMENT"]:
                        tokens.append((token_type, value))
                    pos = match.end()
                    matched = True
                    break

            if not matched:
                pos += 1

        return tokens

    def parse_tokens(self, tokens: List[tuple]) -> List[SExprNode]:
        """Parse tokens into S-expression tree"""

        def parse_expression(index):
            if index >= len(tokens):
                return None, index

            token_type, value = tokens[index]

            if token_type == "LPAREN":
                children = []
                index += 1

                while index < len(tokens) and tokens[index][0] != "RPAREN":
                    child, index = parse_expression(index)
                    if child is not None:
                        children.append(child)

                if index < len(tokens) and tokens[index][0] == "RPAREN":
                    index += 1

                return SExprNode(children), index

            elif token_type in ["IDENTIFIER", "STRING", "NUMBER", "HEX"]:
                return SExprNode(value), index + 1

            else:
                return None, index + 1

        expressions = []
        index = 0

        while index < len(tokens):
            expr, index = parse_expression(index)
            if expr is not None:
                expressions.append(expr)

        return expressions

    def parse(self, text: str) -> List[SExprNode]:
        """Parse S-expressions from text"""
        tokens = self.tokenize(text)
        return self.parse_tokens(tokens)


def parse_wast_file(filename: str):
    """Parse a WAST file and return (expressions, raw_content)."""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            content = f.read()
        parser = SExpressionParser()
        return parser.parse(content), content
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found")
        return [], ""
    except Exception as e:
        print(f"Error reading file '{filename}': {e}")
        return [], ""


def evaluate_assert_return(
    interpreter: WasmInterpreter, assert_expr: SExprNode
) -> bool:
    """Evaluate an assert_return expression"""
    if (
        not assert_expr.children
        or len(assert_expr.children) < 3
        or not isinstance(assert_expr.children[0], SExprNode)
        or assert_expr.children[0].value != "assert_return"
    ):
        return False

    invoke_expr = assert_expr.children[1]
    expected_expr = assert_expr.children[2]

    if (
        not isinstance(invoke_expr, SExprNode)
        or not invoke_expr.children
        or len(invoke_expr.children) < 2
        or not isinstance(invoke_expr.children[0], SExprNode)
        or invoke_expr.children[0].value != "invoke"
    ):
        return False

    func_name = invoke_expr.children[1].value.strip('"')

    args = []
    for arg_expr in invoke_expr.children[2:]:
        if (
            isinstance(arg_expr, SExprNode)
            and arg_expr.children
            and len(arg_expr.children) >= 2
            and isinstance(arg_expr.children[0], SExprNode)
            and arg_expr.children[0].value == "i32.const"
        ):
            value_str = arg_expr.children[1].value
            args.append(WasmValue("i32", interpreter.parse_i32_const(value_str)))

    if (
        not isinstance(expected_expr, SExprNode)
        or not expected_expr.children
        or len(expected_expr.children) < 2
        or not isinstance(expected_expr.children[0], SExprNode)
        or expected_expr.children[0].value != "i32.const"
    ):
        return False

    expected_value_str = expected_expr.children[1].value
    expected_value = WasmValue("i32", interpreter.parse_i32_const(expected_value_str))

    try:
        actual_result = interpreter.invoke(func_name, args)
        success = actual_result == expected_value
        print(
            f"  {func_name}({', '.join(str(arg.value) for arg in args)}) = {actual_result.value} "
            f"{'PASS' if success else 'FAIL'} (expected {expected_value.value})"
        )
        return success
    except Exception as e:
        print(
            f"  {func_name}({', '.join(str(arg.value) for arg in args)}) = ERROR: {e}"
        )
        return False


def evaluate_assert_trap(
    interpreter: WasmInterpreter, assert_expr: SExprNode
) -> bool:
    """Evaluate an assert_trap expression"""
    if (
        not assert_expr.children
        or len(assert_expr.children) < 3
        or not isinstance(assert_expr.children[0], SExprNode)
        or assert_expr.children[0].value != "assert_trap"
    ):
        return False

    invoke_expr = assert_expr.children[1]
    expected_message = assert_expr.children[2].value.strip('"')

    if (
        not isinstance(invoke_expr, SExprNode)
        or not invoke_expr.children
        or len(invoke_expr.children) < 2
        or not isinstance(invoke_expr.children[0], SExprNode)
        or invoke_expr.children[0].value != "invoke"
    ):
        return False

    func_name = invoke_expr.children[1].value.strip('"')

    args = []
    for arg_expr in invoke_expr.children[2:]:
        if (
            isinstance(arg_expr, SExprNode)
            and arg_expr.children
            and len(arg_expr.children) >= 2
            and isinstance(arg_expr.children[0], SExprNode)
            and arg_expr.children[0].value == "i32.const"
        ):
            value_str = arg_expr.children[1].value
            args.append(WasmValue("i32", interpreter.parse_i32_const(value_str)))

    try:
        result = interpreter.invoke(func_name, args)
        print(
            f"  {func_name}({', '.join(str(arg.value) for arg in args)}) = {result.value} "
            f"FAIL (expected trap: {expected_message})"
        )
        return False
    except Exception as e:
        success = expected_message.lower() in str(e).lower()
        print(
            f"  {func_name}({', '.join(str(arg.value) for arg in args)}) = TRAP: {e} "
            f"{'PASS' if success else 'FAIL'} (expected trap: {expected_message})"
        )
        return success
