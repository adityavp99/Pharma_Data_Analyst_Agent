from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GuardrailResult:
    allowed: bool
    reason: str = ""
    category: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "category": self.category,
        }


USER_REFUSAL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "medical_advice",
        re.compile(
            r"\b(diagnose|diagnosis|treat|treatment|prescribe|which drug should|medical advice|clinical recommendation)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "credential_or_secret_request",
        re.compile(r"\b(api key|password|secret|token|credential|private key)\b", re.IGNORECASE),
    ),
    (
        "system_or_prompt_extraction",
        re.compile(r"\b(system prompt|developer prompt|hidden instruction|ignore previous instructions)\b", re.IGNORECASE),
    ),
    (
        "unsafe_data_exfiltration",
        re.compile(
            r"\b(export all|dump all|extract all|show all rows|full dataset|all patient|all customer|all employee)\b",
            re.IGNORECASE,
        ),
    ),
]


DISALLOWED_AST_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.Global,
    ast.Nonlocal,
    ast.Lambda,
    ast.ClassDef,
    ast.AsyncFunctionDef,
    ast.FunctionDef,
    ast.With,
    ast.AsyncWith,
    ast.Delete,
)

DISALLOWED_CALL_NAMES = {
    "__import__",
    "breakpoint",
    "compile",
    "eval",
    "exec",
    "exit",
    "getattr",
    "globals",
    "input",
    "locals",
    "open",
    "quit",
    "setattr",
    "vars",
}

DISALLOWED_ATTRIBUTE_NAMES = {
    "read_csv",
    "read_excel",
    "read_feather",
    "read_json",
    "read_parquet",
    "read_pickle",
    "read_sql",
    "read_sql_query",
    "read_table",
    "read_xml",
    "to_csv",
    "to_excel",
    "to_feather",
    "to_hdf",
    "to_json",
    "to_parquet",
    "to_pickle",
    "to_sql",
}


def check_user_request(question: str) -> GuardrailResult:
    normalized = question.strip()
    if not normalized:
        return GuardrailResult(False, "The question is empty.", "empty_question")
    for category, pattern in USER_REFUSAL_PATTERNS:
        if pattern.search(normalized):
            return GuardrailResult(
                False,
                (
                    "I cannot perform that request in this prototype. Ask for an aggregate, "
                    "privacy-preserving data analysis question instead."
                ),
                category,
            )
    return GuardrailResult(True)


def validate_python_analysis_code(code: str, max_chars: int = 4000, max_nodes: int = 250) -> GuardrailResult:
    if not code.strip():
        return GuardrailResult(False, "Python analysis code is empty.", "empty_python")
    if len(code) > max_chars:
        return GuardrailResult(False, f"Python analysis code is too long. Max characters: {max_chars}.", "python_too_long")

    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        return GuardrailResult(False, f"Python syntax error: {exc}.", "python_syntax_error")

    nodes = list(ast.walk(tree))
    if len(nodes) > max_nodes:
        return GuardrailResult(False, f"Python analysis code is too complex. Max AST nodes: {max_nodes}.", "python_too_complex")

    for node in nodes:
        if isinstance(node, DISALLOWED_AST_NODES):
            return GuardrailResult(
                False,
                f"Python analysis code uses a disallowed construct: {node.__class__.__name__}.",
                "python_disallowed_syntax",
            )
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            return GuardrailResult(False, f"Python analysis code references disallowed name `{node.id}`.", "python_dunder")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__"):
                return GuardrailResult(False, f"Python analysis code references disallowed attribute `{node.attr}`.", "python_dunder")
            if node.attr in DISALLOWED_ATTRIBUTE_NAMES:
                return GuardrailResult(
                    False,
                    f"Python analysis code uses disallowed file/database method `{node.attr}`.",
                    "python_file_or_db_access",
                )
        if isinstance(node, ast.Call):
            call_name = ""
            if isinstance(node.func, ast.Name):
                call_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                call_name = node.func.attr
            if call_name in DISALLOWED_CALL_NAMES:
                return GuardrailResult(
                    False,
                    f"Python analysis code calls disallowed function `{call_name}`.",
                    "python_disallowed_call",
                )

    return GuardrailResult(True)
