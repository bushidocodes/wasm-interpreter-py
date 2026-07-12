"""
WebAssembly Interpreter library — S-expression parser, runtime, and assertion helpers.
"""

import re
from typing import Union, List, Any, Dict, Optional, Tuple


def to_signed_i32(value: int) -> int:
    """Wrap an integer to the signed i32 range [-2^31, 2^31-1]."""
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value >= 0x80000000 else value


def to_unsigned_i32(value: int) -> int:
    """Reinterpret an integer as unsigned i32 in [0, 2^32-1]."""
    return value & 0xFFFFFFFF


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
        self,
        name: Optional[str],
        params: List[tuple],
        result: Optional[str],
        body: List[SExprNode],
    ):
        self.name = name
        self.params = params
        self.result = result
        self.body = body

    def __repr__(self):
        return f"WasmFunction({self.name}, {self.params} -> {self.result})"


class WasmTrap(RuntimeError):
    """A WebAssembly trap (e.g. integer divide by zero)."""


class _ReturnSignal(Exception):
    """Internal control-flow signal for the `return` instruction."""

    def __init__(self, value: Optional[WasmValue]):
        self.value = value


def _div_s(a: int, b: int) -> int:
    if b == 0:
        raise WasmTrap("integer divide by zero")
    if a == -0x80000000 and b == -1:
        raise WasmTrap("integer overflow")
    quotient = abs(a) // abs(b)
    return -quotient if (a < 0) != (b < 0) else quotient


def _rem_s(a: int, b: int) -> int:
    if b == 0:
        raise WasmTrap("integer divide by zero")
    remainder = abs(a) % abs(b)
    return -remainder if a < 0 else remainder


def _div_u(a: int, b: int) -> int:
    if b == 0:
        raise WasmTrap("integer divide by zero")
    return to_unsigned_i32(a) // to_unsigned_i32(b)


def _rem_u(a: int, b: int) -> int:
    if b == 0:
        raise WasmTrap("integer divide by zero")
    return to_unsigned_i32(a) % to_unsigned_i32(b)


def _shl(a: int, b: int) -> int:
    return to_unsigned_i32(a) << (to_unsigned_i32(b) % 32)


def _shr_s(a: int, b: int) -> int:
    return a >> (to_unsigned_i32(b) % 32)


def _shr_u(a: int, b: int) -> int:
    return to_unsigned_i32(a) >> (to_unsigned_i32(b) % 32)


def _rotl(a: int, b: int) -> int:
    ua = to_unsigned_i32(a)
    k = to_unsigned_i32(b) % 32
    return (ua << k) | (ua >> (32 - k)) if k else ua


def _rotr(a: int, b: int) -> int:
    ua = to_unsigned_i32(a)
    k = to_unsigned_i32(b) % 32
    return (ua >> k) | (ua << (32 - k)) if k else ua


def _clz(a: int) -> int:
    ua = to_unsigned_i32(a)
    return 32 - ua.bit_length()


def _ctz(a: int) -> int:
    ua = to_unsigned_i32(a)
    return 32 if ua == 0 else (ua & -ua).bit_length() - 1


def _extend8_s(a: int) -> int:
    v = a & 0xFF
    return v - 0x100 if v >= 0x80 else v


def _extend16_s(a: int) -> int:
    v = a & 0xFFFF
    return v - 0x10000 if v >= 0x8000 else v


# Each op takes/returns Python ints holding the signed i32 interpretation;
# results are re-wrapped with to_signed_i32 at the call site.
I32_BINOPS = {
    "i32.add": lambda a, b: a + b,
    "i32.sub": lambda a, b: a - b,
    "i32.mul": lambda a, b: a * b,
    "i32.div_s": _div_s,
    "i32.div_u": _div_u,
    "i32.rem_s": _rem_s,
    "i32.rem_u": _rem_u,
    "i32.and": lambda a, b: to_unsigned_i32(a) & to_unsigned_i32(b),
    "i32.or": lambda a, b: to_unsigned_i32(a) | to_unsigned_i32(b),
    "i32.xor": lambda a, b: to_unsigned_i32(a) ^ to_unsigned_i32(b),
    "i32.shl": _shl,
    "i32.shr_s": _shr_s,
    "i32.shr_u": _shr_u,
    "i32.rotl": _rotl,
    "i32.rotr": _rotr,
    "i32.eq": lambda a, b: int(a == b),
    "i32.ne": lambda a, b: int(a != b),
    "i32.lt_s": lambda a, b: int(a < b),
    "i32.lt_u": lambda a, b: int(to_unsigned_i32(a) < to_unsigned_i32(b)),
    "i32.le_s": lambda a, b: int(a <= b),
    "i32.le_u": lambda a, b: int(to_unsigned_i32(a) <= to_unsigned_i32(b)),
    "i32.gt_s": lambda a, b: int(a > b),
    "i32.gt_u": lambda a, b: int(to_unsigned_i32(a) > to_unsigned_i32(b)),
    "i32.ge_s": lambda a, b: int(a >= b),
    "i32.ge_u": lambda a, b: int(to_unsigned_i32(a) >= to_unsigned_i32(b)),
}

I32_UNOPS = {
    "i32.clz": _clz,
    "i32.ctz": _ctz,
    "i32.popcnt": lambda a: bin(to_unsigned_i32(a)).count("1"),
    "i32.eqz": lambda a: int(a == 0),
    "i32.extend8_s": _extend8_s,
    "i32.extend16_s": _extend16_s,
}


class WasmInterpreter:
    """Simple WebAssembly interpreter for i32 operations"""

    def __init__(self):
        self.functions: Dict[str, WasmFunction] = {}

    def parse_i32_const(self, value_str: str) -> int:
        """Parse an i32 constant literal (decimal or hex, optional sign and
        underscore separators) into its signed i32 value.

        Raises ValueError for literals outside [-2^31, 2^32-1], which the
        spec treats as malformed.
        """
        s = value_str.replace("_", "")
        base = 16 if s.lstrip("+-").lower().startswith("0x") else 10
        val = int(s, base)
        if val > 0xFFFFFFFF or val < -0x80000000:
            raise ValueError(f"i32 constant out of range: {value_str}")
        return to_signed_i32(val)

    def load_module(self, module_expr: SExprNode):
        """Load a WebAssembly module"""
        if not module_expr.children or not isinstance(
            module_expr.children[0], SExprNode
        ):
            return

        if module_expr.children[0].value != "module":
            return

        # Handle (module quote "..." "..." ...) — concatenate WAT string literals and re-parse.
        if (
            len(module_expr.children) > 1
            and isinstance(module_expr.children[1], SExprNode)
            and module_expr.children[1].value == "quote"
        ):
            parts = []
            for child in module_expr.children[2:]:
                if isinstance(child, SExprNode) and child.value is not None:
                    parts.append(_process_wat_string(child.value))
            wat_content = "".join(parts)
            parser = SExpressionParser()
            exprs = parser.parse(f"(module {wat_content})")
            if exprs:
                self.load_module(exprs[0])
            return

        for child in module_expr.children[1:]:
            if (
                isinstance(child, SExprNode)
                and child.children
                and isinstance(child.children[0], SExprNode)
                and child.children[0].value == "func"
            ):
                self._parse_function(child)

    def _parse_function(self, func_expr: SExprNode):
        """Parse a function definition"""
        export_name = None
        dollar_name = None
        params: List[Tuple[Optional[str], str]] = []
        result = None
        body: List[SExprNode] = []

        for child in func_expr.children[1:]:
            if not isinstance(child, SExprNode):
                continue

            if child.value is not None:
                # A bare token before any body instruction is the function's $label.
                if (
                    isinstance(child.value, str)
                    and child.value.startswith("$")
                    and dollar_name is None
                    and not body
                ):
                    dollar_name = child.value
                    continue
                raise NotImplementedError(
                    f"unsupported token in function definition: {child.value!r} "
                    "(flat instruction syntax is not supported)"
                )

            if child.children and isinstance(child.children[0], SExprNode):
                directive = child.children[0].value

                if directive == "export" and len(child.children) > 1:
                    export_name = child.children[1].value.strip('"')
                    continue
                if directive == "param":
                    fields = [c.value for c in child.children[1:]]
                    if fields and isinstance(fields[0], str) and fields[0].startswith("$"):
                        if len(fields) < 2:
                            raise ValueError(f"param {fields[0]} is missing a type")
                        params.append((fields[0], fields[1]))
                    else:
                        params.extend((None, field) for field in fields)
                    continue
                if directive == "result" and len(child.children) > 1:
                    result = child.children[1].value
                    continue

            body.append(child)

        func = WasmFunction(export_name or dollar_name, params, result, body)
        if export_name:
            self.functions[export_name] = func
        if dollar_name:
            self.functions[dollar_name] = func

    def invoke(self, func_name: str, args: List[WasmValue]) -> Optional[WasmValue]:
        """Invoke a function with given arguments"""
        if func_name not in self.functions:
            raise ValueError(f"Function '{func_name}' not found")

        func = self.functions[func_name]
        if len(args) != len(func.params):
            raise ValueError(
                f"'{func_name}' expects {len(func.params)} argument(s), got {len(args)}"
            )

        # Locals are addressable both by numeric index and by $name.
        local_vars: Dict[str, WasmValue] = {}
        for i, ((param_name, _param_type), arg) in enumerate(zip(func.params, args)):
            local_vars[str(i)] = arg
            if param_name is not None:
                local_vars[param_name] = arg

        stack: List[WasmValue] = []
        try:
            for instr in func.body:
                self._exec(instr, stack, local_vars)
        except _ReturnSignal as ret:
            return ret.value

        return stack[-1] if stack else None

    def _exec(
        self,
        expr: SExprNode,
        stack: List[WasmValue],
        local_vars: Dict[str, WasmValue],
    ):
        """Execute one (possibly folded) instruction against the operand stack."""
        if not isinstance(expr, SExprNode):
            raise ValueError(f"malformed instruction: {expr!r}")
        if expr.value is not None:
            raise NotImplementedError(
                f"flat instruction syntax is not supported: {expr.value!r}"
            )
        if (
            not expr.children
            or not isinstance(expr.children[0], SExprNode)
            or not isinstance(expr.children[0].value, str)
        ):
            raise ValueError(f"malformed instruction: {expr!r}")

        op = expr.children[0].value
        operands = expr.children[1:]

        if op == "local.get":
            if not operands:
                raise ValueError("local.get is missing its local index")
            name = operands[0].value
            if name not in local_vars:
                raise ValueError(f"unknown local: {name}")
            stack.append(local_vars[name])
            return

        if op == "i32.const":
            if not operands:
                raise ValueError("i32.const is missing its value")
            stack.append(WasmValue("i32", self.parse_i32_const(operands[0].value)))
            return

        # Folded operands execute first, pushing their results onto the stack.
        for operand in operands:
            self._exec(operand, stack, local_vars)

        if op == "return":
            raise _ReturnSignal(stack[-1] if stack else None)

        if op in I32_BINOPS:
            if len(stack) < 2:
                raise ValueError(f"stack underflow executing {op}")
            right = stack.pop()
            left = stack.pop()
            stack.append(
                WasmValue("i32", to_signed_i32(I32_BINOPS[op](left.value, right.value)))
            )
            return

        if op in I32_UNOPS:
            if not stack:
                raise ValueError(f"stack underflow executing {op}")
            operand = stack.pop()
            stack.append(WasmValue("i32", to_signed_i32(I32_UNOPS[op](operand.value))))
            return

        raise NotImplementedError(f"unsupported instruction: {op}")


class SExpressionParser:
    """Parser for S-expressions in WebAssembly format"""

    ATOM_TOKENS = ("IDENTIFIER", "STRING", "NUMBER", "HEX")

    def __init__(self):
        # Token patterns - ORDER MATTERS: HEX must come before NUMBER
        self.token_patterns = [
            (r"\(", "LPAREN"),
            (r"\)", "RPAREN"),
            (r'"(?:[^"\\]|\\.)*"', "STRING"),
            (r"[+-]?0x[0-9a-fA-F][0-9a-fA-F_]*", "HEX"),
            (r"[+-]?\d[\d_]*(?:\.[\d_]*)?", "NUMBER"),
            (r"[a-zA-Z_$][a-zA-Z0-9_$.-]*", "IDENTIFIER"),
            (r";;[^\r\n]*", "COMMENT"),
            (r"\s+", "WHITESPACE"),
        ]
        self.compiled_patterns = [
            (re.compile(pattern), token_type)
            for pattern, token_type in self.token_patterns
        ]

    def strip_block_comments(self, text: str) -> str:
        """Remove WAT block comments of the form (; ... ;), including nested ones.

        Block comments may be nested, e.g. (; outer (; inner ;) still outer ;).
        String literals are copied verbatim so that comment delimiters inside
        strings (e.g. "(;") do not start a comment. Per the WAT grammar, the
        reverse is not true: strings inside comments are not special.
        Each matched comment is replaced with a single space so that token
        positions (line/column) are not wildly distorted.
        """
        result = []
        pos = 0
        length = len(text)
        while pos < length:
            # Line comment: copy verbatim until end of line so ;; takes priority over (;
            if text[pos : pos + 2] == ";;":
                while pos < length and text[pos] not in ("\n", "\r"):
                    result.append(text[pos])
                    pos += 1
            # Opening block comment delimiter
            elif text[pos : pos + 2] == "(;":
                depth = 1
                pos += 2
                while pos < length and depth > 0:
                    if text[pos : pos + 2] == "(;":
                        depth += 1
                        pos += 2
                    elif text[pos : pos + 2] == ";)":
                        depth -= 1
                        pos += 2
                    else:
                        pos += 1
                result.append(" ")
            # String literal: copy verbatim, honoring backslash escapes
            elif text[pos] == '"':
                result.append(text[pos])
                pos += 1
                while pos < length:
                    char = text[pos]
                    result.append(char)
                    pos += 1
                    if char == "\\" and pos < length:
                        result.append(text[pos])
                        pos += 1
                    elif char == '"':
                        break
            else:
                result.append(text[pos])
                pos += 1
        return "".join(result)

    def tokenize(self, text: str) -> List[tuple]:
        """Tokenize the input text"""
        text = self.strip_block_comments(text)
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
                raise ValueError(
                    f"unexpected character {text[pos]!r} at position {pos}"
                )

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

            elif token_type in self.ATOM_TOKENS:
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


def _process_wat_string(token_value: str) -> str:
    """Strip outer quotes and decode WAT string escapes (e.g. \\0a → LF, \\" → ")."""
    s = token_value
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1]

    def _replace(m):
        esc = m.group(1)
        if len(esc) == 2:
            return chr(int(esc, 16))
        return {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}.get(esc, m.group(0))

    return re.sub(r'\\([0-9a-fA-F]{2}|[nrt"\\])', _replace, s)


def parse_wast_file(filename: str):
    """Parse a WAST file and return (expressions, raw_content).

    Raises OSError (e.g. FileNotFoundError) if the file cannot be read and
    ValueError if the contents cannot be tokenized.
    """
    with open(filename, "r", encoding="utf-8") as f:
        content = f.read()
    parser = SExpressionParser()
    return parser.parse(content), content


def _parse_invoke(
    interpreter: WasmInterpreter, invoke_expr: SExprNode
) -> Optional[Tuple[str, List[WasmValue]]]:
    """Extract (func_name, args) from an (invoke "name" (i32.const ...) ...) expression."""
    if (
        not isinstance(invoke_expr, SExprNode)
        or not invoke_expr.children
        or len(invoke_expr.children) < 2
        or not isinstance(invoke_expr.children[0], SExprNode)
        or invoke_expr.children[0].value != "invoke"
    ):
        return None

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

    return func_name, args


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

    invoke = _parse_invoke(interpreter, assert_expr.children[1])
    if invoke is None:
        return False
    func_name, args = invoke

    expected_expr = assert_expr.children[2]
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

    args_str = ", ".join(str(arg.value) for arg in args)
    try:
        actual_result = interpreter.invoke(func_name, args)
        success = actual_result == expected_value
        actual_str = actual_result.value if actual_result is not None else "<nothing>"
        print(
            f"  {func_name}({args_str}) = {actual_str} "
            f"{'PASS' if success else 'FAIL'} (expected {expected_value.value})"
        )
        return success
    except Exception as e:
        print(f"  {func_name}({args_str}) = ERROR: {e}")
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

    invoke = _parse_invoke(interpreter, assert_expr.children[1])
    if invoke is None:
        return False
    func_name, args = invoke

    expected_message = assert_expr.children[2].value.strip('"')

    args_str = ", ".join(str(arg.value) for arg in args)
    try:
        result = interpreter.invoke(func_name, args)
        result_str = result.value if result is not None else "<nothing>"
        print(
            f"  {func_name}({args_str}) = {result_str} "
            f"FAIL (expected trap: {expected_message})"
        )
        return False
    except WasmTrap as e:
        success = expected_message.lower() in str(e).lower()
        print(
            f"  {func_name}({args_str}) = TRAP: {e} "
            f"{'PASS' if success else 'FAIL'} (expected trap: {expected_message})"
        )
        return success
    except Exception as e:
        print(
            f"  {func_name}({args_str}) = ERROR: {e} "
            f"FAIL (expected trap: {expected_message})"
        )
        return False
