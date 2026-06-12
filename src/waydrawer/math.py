# ----------- Math Eval for Search Bar -----------------------------------------
"""
  Using AST to recursively see fi what we're looking at is a possible math
  operation and then evaluating it.
"""
from __future__ import annotations

import ast
import operator

_OPS = {
  ast.Add: operator.add,
  ast.Sub: operator.sub,
  ast.Mult: operator.mul,
  ast.Div: operator.truediv,
  ast.FloorDiv: operator.floordiv,
  ast.Mod: operator.mod,
  ast.Pow: operator.pow,
  ast.USub: operator.neg,
  ast.UAdd: operator.pos,
}


def try_math(expr: str):
  """Evaluate expr if it looks like arithmetic. Return result string or None."""
  expr = expr.strip()

  # require at least one operator so bare numbers/words pass through to search
  if not any(c in expr for c in "+-*/%^"):
    return None

  expr = expr.replace("^", "**")  # convenience: ^ for power

  try:
    tree = ast.parse(expr, mode="eval")

  except SyntaxError:
    return None

  def _eval(node):
    if isinstance(node, ast.Expression):
      return _eval(node.body)

    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
      return node.value

    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
      return _OPS[type(node.op)](_eval(node.left), _eval(node.right))

    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
      return _OPS[type(node.op)](_eval(node.operand))

    raise ValueError("unsupported")

  try:
    result = _eval(tree)

  except (ValueError, ZeroDivisionError, OverflowError, TypeError):
    return None

  if isinstance(result, float):
    if result.is_integer():
      result = int(result)

    else:
      result = round(result, 10)

  return str(result)
