"""
GDCE Calculator Service - Safe Formula Engine
===============================================
Evaluates arithmetic expressions stored in the database safely.
Uses Python's ast module — NO eval/exec of arbitrary code.

Supports:
  - Arithmetic: +, -, *, /, ()
  - Comparisons: >, <, >=, <=, ==, !=
  - Conditionals: "expr1 IF condition ELSE expr2"
  - Variables: referenced by name (must be whitelisted)
  - Constants: numeric literals
  - Rounding: apply rounding rules after evaluation

Security:
  - Only allows ast.Num, ast.BinOp, ast.UnaryOp, ast.Compare, ast.Name, ast.IfExp
  - Rejects function calls, imports, attribute access, subscripts

Version: 1.0
Created: 2026-05-04
"""

from __future__ import annotations

import ast
import logging
import re
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING
from typing import Dict, Optional, Union

from .rules_models import RoundingRule

logger = logging.getLogger(__name__)

# Allowed AST node types for safe evaluation
_ALLOWED_NODES = (
    ast.Expression,
    ast.Constant,       # Python 3.8+ numeric/string constants
    ast.Num,            # Python 3.7 compat
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.IfExp,          # ternary: x if cond else y
    ast.Name,
    ast.Load,
    # Operators
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd,
    # Comparison operators
    ast.Gt, ast.Lt, ast.GtE, ast.LtE, ast.Eq, ast.NotEq,
    # Boolean operators (for compound conditions)
    ast.BoolOp, ast.And, ast.Or, ast.Not,
)


class FormulaSecurityError(Exception):
    """Raised when a formula contains unsafe expressions."""
    pass


class FormulaEvaluationError(Exception):
    """Raised when a formula fails to evaluate."""
    pass


class FormulaEngine:
    """
    Safe expression evaluator for database-stored formulas.
    
    Usage:
        engine = FormulaEngine()
        result = engine.evaluate(
            "customs_value * duty_rate",
            {"customs_value": Decimal("4022000"), "duty_rate": Decimal("0.35")}
        )
    
    Conditional:
        result = engine.evaluate(
            "(customs_value + cop_amount + sop_amount) * vat_rate "
            "if sop_amount > 0 else "
            "(customs_value + cop_amount) * vat_rate",
            variables
        )
    """

    def __init__(self):
        self._expression_cache: Dict[str, ast.Expression] = {}

    def evaluate(
        self,
        expression: str,
        variables: Dict[str, Decimal],
    ) -> Decimal:
        """
        Safely evaluate a formula expression.
        
        Args:
            expression: Arithmetic expression (e.g. "customs_value * duty_rate")
            variables: Dict mapping variable names to Decimal values
            
        Returns:
            Result as Decimal
            
        Raises:
            FormulaSecurityError: If expression contains unsafe constructs
            FormulaEvaluationError: If evaluation fails
        """
        # Preprocess: convert "X IF cond ELSE Y" to Python ternary "X if cond else Y"
        processed = self._preprocess_expression(expression)

        # Parse and validate
        tree = self._parse_and_validate(processed)

        # Evaluate
        try:
            result = self._eval_node(tree.body, variables)
            return Decimal(str(result))
        except FormulaSecurityError:
            raise
        except Exception as e:
            raise FormulaEvaluationError(
                f"Failed to evaluate '{expression}': {e}"
            ) from e

    def apply_rounding(
        self,
        amount: Decimal,
        rule: Optional[RoundingRule] = None,
        method: Optional[str] = None,
    ) -> Decimal:
        """
        Apply a rounding rule to an amount.
        
        Args:
            amount: Value to round
            rule: RoundingRule object (takes precedence)
            method: Rounding method string if no rule object
            
        Returns:
            Rounded Decimal value
        """
        if rule:
            method = rule.rounding_method

        if not method or method == "NONE":
            return amount

        if method == "CEILING_100":
            return self._ceiling_to(amount, 100)
        elif method == "ROUND_WHOLE":
            return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        elif method.startswith("CEILING_"):
            precision = int(method.split("_")[1])
            return self._ceiling_to(amount, precision)
        else:
            logger.warning(f"Unknown rounding method '{method}', returning as-is")
            return amount

    def validate_expression(self, expression: str) -> bool:
        """
        Check if an expression is safe without evaluating it.
        
        Returns True if safe, raises FormulaSecurityError if not.
        """
        processed = self._preprocess_expression(expression)
        self._parse_and_validate(processed)
        return True

    def get_required_variables(self, expression: str) -> list[str]:
        """Extract variable names from an expression."""
        processed = self._preprocess_expression(expression)
        tree = self._parse_and_validate(processed)
        names: set[str] = set()
        self._collect_names(tree.body, names)
        return sorted(names)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _preprocess_expression(expr: str) -> str:
        """Convert uppercase IF/ELSE to Python ternary syntax."""
        # Replace " IF " with " if " and " ELSE " with " else " (case-insensitive)
        result = re.sub(r'\bIF\b', 'if', expr)
        result = re.sub(r'\bELSE\b', 'else', result)
        result = re.sub(r'\bAND\b', 'and', result)
        result = re.sub(r'\bOR\b', 'or', result)
        result = re.sub(r'\bNOT\b', 'not', result)
        return result.strip()

    def _parse_and_validate(self, expression: str) -> ast.Expression:
        """Parse expression string and validate all nodes are safe."""
        if expression in self._expression_cache:
            return self._expression_cache[expression]

        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as e:
            raise FormulaSecurityError(f"Invalid expression syntax: {e}") from e

        # Walk tree and check every node
        for node in ast.walk(tree):
            if not isinstance(node, _ALLOWED_NODES):
                raise FormulaSecurityError(
                    f"Unsafe expression: node type '{type(node).__name__}' not allowed. "
                    f"Only arithmetic, comparisons, and conditionals are permitted."
                )

        self._expression_cache[expression] = tree
        return tree

    def _eval_node(self, node: ast.AST, variables: Dict[str, Decimal]) -> Decimal:
        """Recursively evaluate an AST node."""
        # Numeric constant
        if isinstance(node, ast.Constant):
            return Decimal(str(node.value))
        if isinstance(node, ast.Num):  # Python 3.7 compat
            return Decimal(str(node.n))

        # Variable reference
        if isinstance(node, ast.Name):
            name = node.id
            if name not in variables:
                raise FormulaEvaluationError(
                    f"Variable '{name}' not provided. Available: {list(variables.keys())}"
                )
            return Decimal(str(variables[name]))

        # Binary operation
        if isinstance(node, ast.BinOp):
            left = self._eval_node(node.left, variables)
            right = self._eval_node(node.right, variables)
            return self._apply_binop(node.op, left, right)

        # Unary operation
        if isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand, variables)
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return operand
            raise FormulaSecurityError(f"Unsupported unary op: {type(node.op).__name__}")

        # Comparison (returns 1 or 0 as Decimal for boolean)
        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left, variables)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator, variables)
                if not self._apply_compare(op, left, right):
                    return Decimal("0")
                left = right
            return Decimal("1")

        # Ternary / conditional: value_if_true if condition else value_if_false
        if isinstance(node, ast.IfExp):
            condition = self._eval_node(node.test, variables)
            if condition != Decimal("0"):
                return self._eval_node(node.body, variables)
            else:
                return self._eval_node(node.orelse, variables)

        # Boolean operators
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                for value in node.values:
                    if self._eval_node(value, variables) == Decimal("0"):
                        return Decimal("0")
                return Decimal("1")
            if isinstance(node.op, ast.Or):
                for value in node.values:
                    if self._eval_node(value, variables) != Decimal("0"):
                        return Decimal("1")
                return Decimal("0")

        raise FormulaSecurityError(f"Cannot evaluate node type: {type(node).__name__}")

    @staticmethod
    def _apply_binop(op: ast.operator, left: Decimal, right: Decimal) -> Decimal:
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, ast.Div):
            if right == 0:
                raise FormulaEvaluationError("Division by zero")
            return left / right
        if isinstance(op, ast.FloorDiv):
            if right == 0:
                raise FormulaEvaluationError("Division by zero")
            return left // right
        if isinstance(op, ast.Mod):
            return left % right
        if isinstance(op, ast.Pow):
            return left ** right
        raise FormulaSecurityError(f"Unsupported binary op: {type(op).__name__}")

    @staticmethod
    def _apply_compare(op: ast.cmpop, left: Decimal, right: Decimal) -> bool:
        if isinstance(op, ast.Gt):
            return left > right
        if isinstance(op, ast.Lt):
            return left < right
        if isinstance(op, ast.GtE):
            return left >= right
        if isinstance(op, ast.LtE):
            return left <= right
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
        raise FormulaSecurityError(f"Unsupported comparison: {type(op).__name__}")

    @staticmethod
    def _ceiling_to(amount: Decimal, precision: int) -> Decimal:
        p = Decimal(str(precision))
        return (amount / p).quantize(Decimal("1"), rounding=ROUND_CEILING) * p

    def _collect_names(self, node: ast.AST, names: set[str]) -> None:
        if isinstance(node, ast.Name):
            names.add(node.id)
        for child in ast.iter_child_nodes(node):
            self._collect_names(child, names)
