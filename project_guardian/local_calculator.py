"""Existing bounded calculator; exact function from PR168.
Source: 4eea564b0de97c124aea7475527e7ab542249ffc:elysia_offline.py.
Extracted unchanged to avoid importing the unrelated restricted pilot launcher.
"""

def calculate_local(expression: str) -> str:
    """Bounded arithmetic only: no names, calls, attributes, powers or eval."""
    import ast
    from decimal import Decimal, DecimalException, localcontext
    if not expression.strip() or len(expression) > 120:
        raise ValueError("Use an arithmetic expression of 1 to 120 characters.")
    try:
        source = expression.strip()
        tree = ast.parse(source, mode="eval")
        if sum(1 for _ in ast.walk(tree)) > 40:
            raise ValueError("Expression is too complex.")
        def number(node):
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                result = Decimal(ast.get_source_segment(source, node))
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                value = number(node.operand)
                result = value if isinstance(node.op, ast.UAdd) else -value
            elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
                left, right = number(node.left), number(node.right)
                if isinstance(node.op, ast.Add): result = left + right
                elif isinstance(node.op, ast.Sub): result = left - right
                elif isinstance(node.op, ast.Mult): result = left * right
                else: result = left / right
            else:
                raise ValueError("Only numbers, parentheses and + - * / are allowed.")
            if not result.is_finite() or abs(result) > Decimal("1e12"):
                raise ValueError("Each value must be finite and no larger than 1 trillion.")
            if result and result.adjusted() < -12:
                raise ValueError("Nonzero values must be at least 0.000000000001 in magnitude.")
            return result
        with localcontext() as context:
            context.prec = 28
            return format(number(tree.body).normalize(), "f")
    except (SyntaxError, DecimalException, OverflowError) as exc:
        raise ValueError("Invalid arithmetic or division by zero.") from exc
