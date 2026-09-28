"""The boundary: `home/` is the private half, its own repo, and nothing under it is tracked here."""

import subprocess
from pathlib import Path

REPO = Path(__file__).parent.parent


def test_nothing_under_home_is_tracked():
    out = subprocess.run(
        ["git", "ls-files", "--", "home/"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout
    assert out == ""
