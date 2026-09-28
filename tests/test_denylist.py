"""The publish gate at `pytest` time: no tracked file may match `home/denylist.txt`.

The denylist lives in the private `home/` repo, because a denylist in the public tree would
publish the list. So this skips wherever `home/` is absent — CI, a stranger's clone — and runs
on the one machine that holds the record. The pre-push hook in `home/hooks/` is the same scan
over commit messages too; this catches a hit before it is committed at all.
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
DENYLIST = REPO / "home" / "denylist.txt"


def _patterns() -> list[re.Pattern[bytes]]:
    lines = DENYLIST.read_text().splitlines()
    return [re.compile(ln.strip().encode(), re.IGNORECASE) for ln in lines
            if ln.strip() and not ln.lstrip().startswith("#")]


@pytest.mark.skipif(not DENYLIST.exists(), reason="no home/denylist.txt on this machine")
def test_no_tracked_file_matches_the_denylist():
    files = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True,
                           check=True).stdout.split(b"\0")
    pats = _patterns()
    hits = []
    for name in filter(None, files):
        path = REPO / name.decode()
        if not path.is_file():
            continue
        data = path.read_bytes()
        hits += [f"{name.decode()}: {p.pattern.decode()}" for p in pats if p.search(data)]
    assert not hits, "denylisted strings in tracked files:\n" + "\n".join(hits)
