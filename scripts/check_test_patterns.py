"""Structural tripwires for vacuous tests, supplemented by behavioral proofs."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import sys


@dataclass(frozen=True)
class Finding:
    path: str
    test: str
    kind: str
    line: int


def positive_census(expression: ast.expr, collectors: set[str]) -> bool:
    """Recognize direct nonempty collections and explicit positive numeric floors."""
    if isinstance(expression, ast.Name):
        return expression.id in collectors
    if not isinstance(expression, ast.Compare) or len(expression.ops) != 1:
        return False
    left = expression.left
    if (
        isinstance(left, ast.Call)
        and isinstance(left.func, ast.Name)
        and left.func.id == "len"
        and len(left.args) == 1
    ):
        left = left.args[0]
    if not isinstance(left, ast.Name) or left.id not in collectors:
        return False
    right = expression.comparators[0]
    if (
        not isinstance(right, ast.Constant)
        or not isinstance(right.value, (int, float))
        or isinstance(right.value, bool)
    ):
        return False
    op = expression.ops[0]
    return (
        (isinstance(op, ast.Gt) and right.value >= 0)
        or (isinstance(op, (ast.GtE, ast.Eq)) and right.value > 0)
        or (isinstance(op, ast.NotEq) and right.value == 0)
    )


TestFunction = ast.FunctionDef | ast.AsyncFunctionDef


def is_platform_test(test: TestFunction) -> bool:
    return any(
        isinstance(d, ast.Call)
        and isinstance(d.func, ast.Attribute)
        and d.func.attr in {"skip", "skipif"}
        and "platform" in ast.unparse(d).lower()
        for d in test.decorator_list
    )


def has_asserting_call(call: ast.Call, helpers: dict[str, TestFunction]) -> bool:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr == "raises" or call.func.attr.startswith("assert_")
    if isinstance(call.func, ast.Name) and call.func.id in helpers:
        return any(isinstance(n, ast.Assert) for n in ast.walk(helpers[call.func.id]))
    return False


def has_behavior_assertion(test: TestFunction, helpers: dict[str, TestFunction]) -> bool:
    if any("pytest.mark.behavior_no_raise" in ast.unparse(d) for d in test.decorator_list):
        return True
    for node in ast.walk(test):
        if isinstance(node, ast.Assert):
            return True
        if isinstance(node, ast.Call) and has_asserting_call(node, helpers):
            return True
    return False


def guard_body(guard: ast.If) -> list[ast.AST]:
    return [node for statement in guard.body for node in ast.walk(statement)]


def has_status_early_return(guard: ast.If) -> bool:
    condition = list(ast.walk(guard.test))
    if "status_code" not in ast.unparse(guard.test):
        return False
    if not any(isinstance(n, ast.Constant) and n.value in (404, 405) for n in condition):
        return False
    if any(isinstance(n, (ast.NotEq, ast.NotIn)) for n in condition):
        return False
    body = guard_body(guard)
    return any(isinstance(n, ast.Return) and n.value is None for n in body) and not any(
        isinstance(n, ast.Assert) for n in body
    )


def census_collectors(body: list[ast.AST]) -> set[str]:
    collectors = set()
    for node in body:
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.attr in {"append", "add"}
        ):
            collectors.add(node.func.value.id)
        if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            collectors.add(node.target.id)
    return collectors


def has_nullable_census(guard: ast.If, assertions: list[ast.Assert]) -> bool:
    body = guard_body(guard)
    guarded = {id(n) for n in body}
    collectors = census_collectors(body)
    targets = [
        ast.unparse(node.left)
        for node in ast.walk(guard.test)
        if isinstance(node, ast.Compare) and any(isinstance(op, ast.IsNot) for op in node.ops)
    ]
    for assertion in assertions:
        if id(assertion) in guarded:
            continue
        text = ast.unparse(assertion.test)
        if "is not None" in text and any(target in text for target in targets):
            return True
        if positive_census(assertion.test, collectors):
            return True
    return False


def analyze(source: str, path: str) -> list[Finding]:
    tree = ast.parse(source)
    helpers = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    findings = []
    for test in ast.walk(tree):
        if not isinstance(
            test, (ast.FunctionDef, ast.AsyncFunctionDef)
        ) or not test.name.startswith("test_"):
            continue
        if is_platform_test(test):
            continue
        if not has_behavior_assertion(test, helpers):
            findings.append(Finding(path, test.name, "no-behavior-assertion", test.lineno))
        assertions = [node for node in ast.walk(test) if isinstance(node, ast.Assert)]
        for guard in (node for node in ast.walk(test) if isinstance(node, ast.If)):
            if has_status_early_return(guard):
                findings.append(Finding(path, test.name, "status-early-return", guard.lineno))
            if (
                path.startswith("tests/property/")
                and "is not None" in ast.unparse(guard.test)
                and not has_nullable_census(guard, assertions)
            ):
                findings.append(
                    Finding(path, test.name, "nullable-invariant-without-census", guard.lineno)
                )
    return findings


def check(root: Path) -> list[str]:
    failures = []
    for path in sorted((root / "tests").rglob("test_*.py")):
        rel = str(path.relative_to(root))
        for finding in analyze(path.read_text(), rel):
            failures.append(f"{rel}:{finding.line}: {finding.kind} in {finding.test}")
    # Contract examples must retain both successful execution and meaningful assertion.
    contracts = {
        "DATA-01": (
            "tests/integration/test_nondefault_profile_scoping.py",
            "test_boundary_put_as_nondefault_profile_lands_on_p_only",
            (".put(", "status_code == 200", "assert"),
        ),
        "PRIV-02": (
            "tests/integration/test_08_privacy.py",
            "test_query_never_in_logs",
            (
                "capfd.readouterr",
                "configure_logging",
                ".get(",
                "status_code == 200",
                "PROBE_TERM not in emitted",
            ),
        ),
        "SEG-08": (
            "tests/integration/test_segment_api.py",
            "test_get_segments_returns_derived_data",
            (".get(", "status_code == 200", "segments"),
        ),
    }
    for requirement, (filename, name, required) in contracts.items():
        tree = ast.parse((root / filename).read_text())
        test = next(
            (
                n
                for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
            ),
            None,
        )
        text = ast.unparse(test) if test is not None else ""
        if any(token not in text for token in required):
            failures.append(
                f"{filename}: {requirement} lost its executed behavior/emission contract"
            )
    return failures


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    failures = check(root)
    for message in failures:
        print(message, file=sys.stderr)
    if failures:
        sys.exit(1)
    print(
        "Static test pattern gate passed: behavior contracts, status paths and nullable census checks"
    )


if __name__ == "__main__":
    main()
