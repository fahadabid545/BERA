"""The platform's name and support address are settings (General). A test fails if either is
written into the code again: a message or email that names the platform must read the setting."""

import ast
import re
from pathlib import Path

SERVER = Path(__file__).resolve().parents[2]
SKIPPED_PARTS = {".venv", "tests", "migrations", "node_modules", "__pycache__", "management"}
# Sample values for development and tests are examples, not what people are sent.
# definitions.py holds the defaults of the two settings themselves.
SKIPPED_FILES = {"samples.py", "definitions.py"}
# A hyphenated name such as the X-Bera-Template header is technical, not text people read.
NAME = re.compile(r"(?<![-\w])Bera(?![-\w])")
ADDRESS = re.compile(r"support@", re.IGNORECASE)


def code_files():
    for path in SERVER.rglob("*.py"):
        parts = set(path.relative_to(SERVER).parts)
        if not parts & SKIPPED_PARTS and path.name not in SKIPPED_FILES:
            yield path


def texts_in(path):
    """Every string in a file's code, except docstrings and comments (which are for developers)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                yield node.lineno, node.value


def test_no_code_writes_the_platform_name_or_support_address_into_a_message():
    found = [
        f"{path.relative_to(SERVER)}:{line}"
        for path in code_files()
        for line, text in texts_in(path)
        if NAME.search(text) or ADDRESS.search(text)
    ]
    assert not found, f"Read general.app_name / general.support_email instead: {found}"


def test_the_email_layouts_do_not_write_the_name_or_address_either():
    for layout in (SERVER / "emailing" / "templates" / "emailing").iterdir():
        text = layout.read_text(encoding="utf-8")
        assert not NAME.search(text) and not ADDRESS.search(text), layout.name
