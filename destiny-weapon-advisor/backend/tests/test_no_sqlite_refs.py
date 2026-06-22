"""Regression guard: no .py file under app/ may import sqlite3 or app.storage."""
from pathlib import Path


def test_no_sqlite_imports_in_app():
    app_root = Path(__file__).parent.parent / "app"
    violations = []
    for py_file in sorted(app_root.rglob("*.py")):
        text = py_file.read_text()
        if "import sqlite3" in text or "from app.storage" in text:
            violations.append(str(py_file))
    assert violations == [], (
        "SQLite references found in app/ (must be removed):\n"
        + "\n".join(violations)
    )
