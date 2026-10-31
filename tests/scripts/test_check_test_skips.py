"""scripts/check_test_skips.py fails on a skipped test unless the same line references an issue.

Each test writes test files into a temporary directory and runs the real script on it.
"""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_test_skips.py"


def check(
    directory: Path, files: dict[str, str], paths: tuple[str, ...] = (".",)
) -> subprocess.CompletedProcess[str]:
    """Write ``files`` (relative path -> content) under ``directory`` and check ``paths``."""
    for name, content in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *paths],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=30,
    )


# Python


@pytest.mark.parametrize(
    "source",
    [
        "@pytest.mark.skip\ndef test_it():\n    pass\n",
        '@pytest.mark.skip(reason="flaky")\ndef test_it():\n    pass\n',
        "pytestmark = pytest.mark.skip\n",
        "def test_it():\n    pytest.skip('not ready')\n",
        "@pytest.mark.parametrize('n', [pytest.param(1, marks=pytest.mark.skip)])\n"
        "def test_it(n):\n    pass\n",
        "from pytest import mark\n\n@mark.skip\ndef test_it():\n    pass\n",
    ],
    ids=[
        "decorator",
        "decorator-with-reason",
        "module-mark",
        "imperative",
        "param-mark",
        "imported-mark",
    ],
)
def test_python_skip_without_an_issue_fails(tmp_path: Path, source: str) -> None:
    assert check(tmp_path, {"test_sample.py": source}).returncode == 1


@pytest.mark.parametrize(
    "source",
    [
        '@pytest.mark.skip(reason="#170 flaky")\ndef test_it():\n    pass\n',
        "@pytest.mark.skip  # #170\ndef test_it():\n    pass\n",
        "def test_it():\n    pytest.skip(f'waiting on #170 for {reason}')\n",
        '@pytest.mark.skip(\n    reason="the delta loop drops frames, see #170"\n)\n'
        "def test_it():\n    pass\n",
        '@pytest.mark.skip(reason="tcole333/plane-game-v4#170")\ndef test_it():\n    pass\n',
        '@pytest.mark.skip(reason="https://github.com/tcole333/plane-game-v4/issues/9")\n'
        "def test_it():\n    pass\n",
    ],
    ids=["in-reason", "in-comment", "in-f-string", "wrapped-call", "cross-repo", "issue-url"],
)
def test_python_skip_that_names_an_issue_passes(tmp_path: Path, source: str) -> None:
    assert check(tmp_path, {"test_sample.py": source}).returncode == 0


@pytest.mark.parametrize(
    "source",
    [
        "# Flaky, see #170\n@pytest.mark.skip\ndef test_it():\n    pass\n",
        "@pytest.mark.parametrize(\n    'player',\n    [\n"
        "        pytest.param('host', id='issue #170 host'),\n"
        "        pytest.param('guest', marks=pytest.mark.skip(reason='flaky')),\n"
        "    ],\n)\ndef test_it(player):\n    pass\n",
        "@pytest.mark.parametrize(\n    'n',\n    [\n"
        "        pytest.param(1, marks=pytest.mark.skip(reason='#170 flaky')),\n"
        "        pytest.param(2, marks=pytest.mark.skip(reason='broken')),\n"
        "    ],\n)\ndef test_it(n):\n    pass\n",
        '@pytest.mark.skip(reason="flaky when round #2 starts early")\ndef test_it():\n    pass\n',
        "@pytest.mark.skip(reason='paints #111827')\ndef test_it():\n    pass\n",
    ],
    ids=["line-above", "sibling-param", "sibling-skip", "single-digit", "hex-colour"],
)
def test_python_reference_elsewhere_or_not_an_issue_does_not_count(
    tmp_path: Path, source: str
) -> None:
    assert check(tmp_path, {"test_sample.py": source}).returncode == 1


@pytest.mark.parametrize(
    "source",
    [
        "@pytest.mark.skipif(sys.platform == 'win32', reason='posix only')\n"
        "def test_it():\n    pass\n",
        '"""Never use pytest.mark.skip or pytest.skip( here."""\n',
        "# pytest.mark.skip is not allowed without an issue\n",
        "def test_it(rows):\n    rows.skip(2)\n",
    ],
    ids=["skipif", "docstring", "comment", "other-skip-method"],
)
def test_python_file_without_an_unconditional_skip_passes(tmp_path: Path, source: str) -> None:
    assert check(tmp_path, {"test_sample.py": source}).returncode == 0


def test_python_report_names_the_line_and_code_of_each_skip(tmp_path: Path) -> None:
    source = "pytestmark = [\n    pytest.mark.integration,\n    pytest.mark.skip,\n]\n"

    result = check(tmp_path, {"test_sample.py": source})

    assert result.stdout.splitlines()[0] == "test_sample.py:3: pytest.mark.skip,"


def test_python_file_that_cannot_be_tokenized_fails(tmp_path: Path) -> None:
    result = check(tmp_path, {"test_sample.py": "x = '''unclosed\n"})

    assert (result.returncode, "test_sample.py" in result.stderr) == (1, True)


# Frontend


@pytest.mark.parametrize(
    "source",
    [
        "it.skip('renders', () => {});\n",
        "test.skip('renders', () => {});\n",
        "describe.skip('Map', () => {});\n",
        "suite.skip('Map', () => {});\n",
        "it.concurrent.skip('renders', async () => {});\n",
        "test.skip.each([1, 2])('renders %i', () => {});\n",
        "it('renders', { skip: true }, () => {});\n",
        "it('renders', (ctx) => {\n  ctx.skip();\n});\n",
    ],
    ids=["it", "test", "describe", "suite", "chained", "each", "option", "in-test"],
)
def test_frontend_skip_without_an_issue_fails(tmp_path: Path, source: str) -> None:
    assert check(tmp_path, {"src/Map.test.tsx": source}).returncode == 1


@pytest.mark.parametrize(
    "name",
    ["Map.test.ts", "Map.test.js", "Map.test.jsx", "Map.spec.ts", "Map.test.mts", "__tests__/a.ts"],
)
def test_every_kind_of_frontend_test_file_is_checked(tmp_path: Path, name: str) -> None:
    assert check(tmp_path, {f"src/{name}": "it.skip('renders', () => {});\n"}).returncode == 1


def test_frontend_skip_with_an_issue_on_the_same_line_passes(tmp_path: Path) -> None:
    source = "it.skip('renders', () => {}); // #170\n"

    assert check(tmp_path, {"src/Map.test.tsx": source}).returncode == 0


def test_issue_named_on_the_line_above_a_frontend_skip_does_not_count(tmp_path: Path) -> None:
    source = "// #170\nit.skip('renders', () => {});\n"

    assert check(tmp_path, {"src/Map.test.tsx": source}).returncode == 1


@pytest.mark.parametrize(
    "source",
    [
        "it.skipIf(process.env.CI)('renders', () => {});\n",
        "it('renders', () => { expect(result.test.skip).toBe(true); });\n",
        "it('sends skipRound', () => { send({ type: 'skipRound' }); });\n",
    ],
    ids=["skipIf", "property-named-skip", "skip-round-message"],
)
def test_frontend_file_without_an_unconditional_skip_passes(tmp_path: Path, source: str) -> None:
    assert check(tmp_path, {"src/Map.test.tsx": source}).returncode == 0


def test_frontend_source_that_is_not_a_test_is_not_checked(tmp_path: Path) -> None:
    files = {
        "src/Map.test.tsx": "it('renders', () => {});\n",
        "src/options.ts": "export const replay = { skip: true };\n",
    }

    assert check(tmp_path, files).returncode == 0


# Directories


@pytest.mark.parametrize("directory", ["node_modules", "coverage", "dist"])
def test_generated_and_installed_directories_are_not_checked(
    tmp_path: Path, directory: str
) -> None:
    files = {
        "src/Map.test.tsx": "it('renders', () => {});\n",
        f"{directory}/vendor.test.js": "it.skip('renders', () => {});\n",
    }

    assert check(tmp_path, files).returncode == 0


def test_feature_folder_named_like_an_output_directory_is_checked(tmp_path: Path) -> None:
    files = {"src/coverage/__tests__/CoverageMap.test.ts": "it.skip('draws', () => {});\n"}

    assert check(tmp_path, files).returncode == 1


# Reporting


def test_report_names_the_file_and_line_of_each_skip(tmp_path: Path) -> None:
    source = "import { it } from 'vitest';\nit.skip('renders', () => {});\n"

    result = check(tmp_path, {"src/Map.test.tsx": source})

    assert "src/Map.test.tsx:2: it.skip('renders', () => {});" in result.stdout


def test_report_counts_lines_as_editors_do(tmp_path: Path) -> None:
    source = "const sep = 'a b';\nit.skip('renders', () => {});\n"

    result = check(tmp_path, {"src/Map.test.tsx": source})

    assert "src/Map.test.tsx:2:" in result.stdout


def test_directory_without_test_sources_is_an_error(tmp_path: Path) -> None:
    result = check(tmp_path, {"README.md": "it.skip\n"})

    assert result.returncode == 2


def test_each_path_must_hold_test_sources(tmp_path: Path) -> None:
    files = {"tests/test_sample.py": "def test_it():\n    pass\n", "docs/README.md": "notes\n"}

    assert check(tmp_path, files, paths=("tests", "docs")).returncode == 2
