#!/usr/bin/env python3
"""Fail when a test is skipped without an issue reference (#123) on the same line.

Usage: python scripts/check_test_skips.py [PATH ...]   (default: tests/ and frontend/)

Python files are checked for ``mark.skip`` (as in ``pytest.mark.skip``) and ``pytest.skip(``.
The check reads tokens, so a mention in a string or comment is not a skip. The reference
must be inside the skip itself, such as its ``reason``, or in a comment on a line the skip
spans, because ruff may wrap a long decorator over several lines.

Frontend test files (``*.test.*``, ``*.spec.*`` and files under ``__tests__/``) are checked
line by line for ``it.skip``, ``test.skip``, ``describe.skip`` and ``suite.skip``, including
chains such as ``it.concurrent.skip``, for the ``{ skip: true }`` option, and for ``skip()``
called inside a test.

A reference is ``#`` and 2 to 5 digits, as in ``#170`` or ``owner/repo#170``, or an issue
URL. Not checked: conditional skips (``skipif``, ``skipIf``), ``xfail``, ``it.todo``,
renamed imports and other aliases, and focused tests (``it.only``), which Vitest already
refuses when ``CI`` is set.
"""

import argparse
import io
import os
import re
import sys
import tokenize
from collections.abc import Callable, Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATHS = [REPO_ROOT / "tests", REPO_ROOT / "frontend"]
SKIPPED_DIRECTORIES = {".git", ".venv", "__pycache__", "node_modules"}
# Output directories are skipped only at the top of a checked path, so a feature folder
# that happens to be called "coverage" is still checked.
SKIPPED_OUTPUT_DIRECTORIES = {"coverage", "dist"}
JS_SUFFIXES = {".cjs", ".cts", ".js", ".jsx", ".mjs", ".mts", ".ts", ".tsx"}
FRONTEND_TEST_NAME = re.compile(r"\.(?:spec|test)\.")

ISSUE_REFERENCE = re.compile(r"(?<!&)#\d{2,5}\b|/issues/\d+\b")
JS_SKIPS = [
    re.compile(r"(?<![\w$.])(?:describe|it|suite|test)(?:\.\w+)*\.skip\b"),
    re.compile(r"\bskip\s*:\s*true\b"),
    re.compile(r"(?<![\w$])skip\(\s*\)"),
]
PYTHON_SKIPS = [("mark", ".", "skip"), ("pytest", ".", "skip", "(")]
LAYOUT_TOKENS = {tokenize.DEDENT, tokenize.ENCODING, tokenize.INDENT, tokenize.NL}


def python_statements(source: str) -> Iterator[list[tokenize.TokenInfo]]:
    """Yield the tokens of each statement, including its comments but not layout tokens.

    Raises:
        SyntaxError, tokenize.TokenError: If the source cannot be tokenized.
    """
    statement: list[tokenize.TokenInfo] = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in (tokenize.NEWLINE, tokenize.ENDMARKER):
            if statement:
                yield statement
            statement = []
        elif token.type == tokenize.COMMENT and not statement:
            continue  # A comment on its own line belongs to no statement.
        elif token.type not in LAYOUT_TOKENS:
            statement.append(token)


def skip_end(code: list[tokenize.TokenInfo], start: int, length: int) -> int:
    """Return the index of a skip's last token: the closing bracket of its call, if any."""
    end = start + length - 1
    opening = end if code[end].string == "(" else end + 1
    if opening == len(code) or code[opening].string != "(":
        return end
    depth = 0
    for index in range(opening, len(code)):
        depth += {"(": 1, ")": -1}.get(code[index].string, 0)
        if depth == 0:
            return index
    return len(code) - 1


def names_an_issue(
    statement: list[tokenize.TokenInfo], first: tokenize.TokenInfo, last: tokenize.TokenInfo
) -> bool:
    """Whether a token from ``first`` to ``last``, or a comment on their lines, names an issue."""
    lines = range(first.start[0], last.end[0] + 1)
    return any(
        ISSUE_REFERENCE.search(token.string)
        for token in statement
        if first.start <= token.start <= last.start
        or (token.type == tokenize.COMMENT and token.start[0] in lines)
    )


def unreferenced_python_skips(source: str) -> Iterator[int]:
    """Yield the line of each Python skip that names no issue."""
    for statement in python_statements(source):
        code = [token for token in statement if token.type in (tokenize.NAME, tokenize.OP)]
        words = [token.string for token in code]
        for start in range(len(code)):
            for skip in PYTHON_SKIPS:
                if tuple(words[start : start + len(skip)]) != skip:
                    continue
                last = code[skip_end(code, start, len(skip))]
                if not names_an_issue(statement, code[start], last):
                    yield code[start].start[0]


def unreferenced_js_skips(source: str) -> Iterator[int]:
    """Yield the line of each frontend test skip whose line names no issue."""
    for number, line in enumerate(source.split("\n"), start=1):
        if any(skip.search(line) for skip in JS_SKIPS) and not ISSUE_REFERENCE.search(line):
            yield number


def skip_finder(path: Path) -> Callable[[str], Iterator[int]] | None:
    """Return the check for ``path``, or None if it is neither Python nor a frontend test."""
    if path.suffix == ".py":
        return unreferenced_python_skips
    if path.suffix in JS_SUFFIXES and (
        FRONTEND_TEST_NAME.search(path.name) or "__tests__" in path.parts
    ):
        return unreferenced_js_skips
    return None


def files_under(root: Path) -> Iterator[Path]:
    """Yield ``root`` if it is a file, else every file below it, in a stable order."""
    if root.is_file():
        yield root
        return
    for directory, subdirectories, files in os.walk(root):
        skipped = SKIPPED_DIRECTORIES
        if Path(directory) == root:
            skipped = skipped | SKIPPED_OUTPUT_DIRECTORIES
        subdirectories[:] = sorted(set(subdirectories) - skipped)
        for name in sorted(files):
            yield Path(directory) / name


def main(argv: list[str] | None = None) -> int:
    """Check the given paths and print every unreferenced skip; return the exit status."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "paths", nargs="*", type=Path, default=DEFAULT_PATHS, help="files or directories"
    )
    paths = parser.parse_args(argv).paths
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        parser.error(f"no such file or directory: {', '.join(missing)}")

    checked = 0
    findings = []
    for root in paths:
        sources = [(path, find) for path in files_under(root) if (find := skip_finder(path))]
        if not sources:
            parser.error(f"no Python files or frontend test files under {root}")
        for path, find_skips in sources:
            source = path.read_text(encoding="utf-8-sig", errors="replace")
            shown = os.path.relpath(path)
            try:
                lines = list(find_skips(source))
            except (SyntaxError, tokenize.TokenError) as error:
                message = f"{shown}: cannot tokenize, so its skips cannot be checked: {error}"
                print(message, file=sys.stderr)
                return 1
            source_lines = source.split("\n")
            findings += [f"{shown}:{line}: {source_lines[line - 1].strip()}" for line in lines]
        checked += len(sources)

    if findings:
        print("\n".join(findings))
        print(
            f"\n{len(findings)} skipped test(s) without an issue reference. Put the issue number "
            "on the same line, e.g. `it.skip('...', () => {}); // #123` or "
            '`@pytest.mark.skip(reason="#123 ...")`, or remove the skip.'
        )
        return 1
    print(f"Checked {checked} files: every skipped test references an issue.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
