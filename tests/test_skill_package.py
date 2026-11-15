"""Verify the self-contained Skill directory conforms to the Agent Skills specification."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT_DIR / "skills" / "standards-plagiarism-check"


def test_skill_directory_structure() -> None:
    skill_md = SKILL_DIR / "SKILL.md"
    assert skill_md.exists()
    content = skill_md.read_text(encoding="utf-8")
    assert content.startswith("---\nname: standards-plagiarism-check\n")
    assert "description:" in content

    assert (SKILL_DIR / "scripts" / "std_check.py").exists()
    assert (SKILL_DIR / "scripts" / "std_plagiarism_check" / "cli.py").exists()
    assert (SKILL_DIR / "references" / "appendix_b_rules.md").exists()
    assert (SKILL_DIR / "references" / "assessment_schema.json").exists()
    assert (SKILL_DIR / "assets" / "env.example").exists()


def test_skill_bundled_runner_cli_executes() -> None:
    runner = SKILL_DIR / "scripts" / "std_check.py"
    proc = subprocess.run(
        [sys.executable, "-B", str(runner), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "prepare" in proc.stdout
    assert "report" in proc.stdout
