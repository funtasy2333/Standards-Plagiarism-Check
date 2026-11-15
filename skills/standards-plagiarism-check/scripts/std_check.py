#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "httpx>=0.27.0",
#   "pydantic>=2.7.0",
#   "python-dotenv>=1.0.1",
#   "typer>=0.12.3",
#   "rich>=13.7.1",
#   "mcp>=1.2.0",
#   "python-docx>=1.1.2",
#   "openpyxl>=3.1.2",
#   "jinja2>=3.1.4",
# ]
# ///
"""Self-contained skill entrypoint for Standards Plagiarism Check.

Can be executed directly via `uv run scripts/std_check.py ...` or `python3 scripts/std_check.py ...`
even when the skill directory is installed outside the original repository.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from std_plagiarism_check.cli import app  # noqa: E402

if __name__ == "__main__":
    app()
