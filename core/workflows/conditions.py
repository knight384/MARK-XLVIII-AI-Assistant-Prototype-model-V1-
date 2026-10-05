from typing import Any, Dict
import ast
import operator

class SafeExpressionError(Exception):
    pass

_ALLOWED_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.And: lambda a, b: a and b,
    ast.Or: lambda a, b: a or b,
    ast.Not: operator.not_,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

def evaluate_condition(expression: str, context: Dict[str, Any]) -> bool:
    """
    Safely evaluate a boolean expression string against a context dictionary.
    No function calls, attributes, or complex structures are allowed.
    Only basic comparisons and boolean logic.
    """
    if not expression:
        return True
        
    try:
        tree = ast.parse(expression, mode='eval')
    except SyntaxError as e:
        raise SafeExpressionError(f"Syntax error in expression: {e}")
        
    def _eval(node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Name):
            if node.id not in context:
                raise SafeExpressionError(f"Variable '{node.id}' not found in context")
            return context[node.id]
        elif isinstance(node, ast.Compare):
            left = _eval(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = _eval(comparator)
                op_func = _ALLOWED_OPS.get(type(op))
                if not op_func:
                    raise SafeExpressionError(f"Unsupported operator: {type(op)}")
                if not op_func(left, right):
                    return False
                left = right
            return True
        elif isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return all(_eval(val) for val in node.values)
            elif isinstance(node.op, ast.Or):
                return any(_eval(val) for val in node.values)
        elif isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return not _eval(node.operand)
        raise SafeExpressionError(f"Unsupported expression node: {type(node)}")
        
    try:
        result = _eval(tree.body)
        return bool(result)
    except Exception as e:
        if isinstance(e, SafeExpressionError):
            raise
        raise SafeExpressionError(f"Evaluation failed: {e}")
