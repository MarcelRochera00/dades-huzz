"""Copy the skills in .agents/skills to the folders other agents read.

Usage:
    uv run python scripts/sync_skills.py          # copy
    uv run python scripts/sync_skills.py --check  # fail if the copies differ
"""

import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / ".agents" / "skills"
TARGETS = [ROOT / ".claude" / "skills", ROOT / ".github" / "skills"]


def same_tree(a: Path, b: Path) -> bool:
    if not b.is_dir():
        return False
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.funny_files:
        return False
    _, mismatch, errors = filecmp.cmpfiles(a, b, cmp.common_files, shallow=False)
    if mismatch or errors:
        return False
    return all(same_tree(a / d, b / d) for d in cmp.common_dirs)


def main() -> int:
    check = "--check" in sys.argv
    stale = [t for t in TARGETS if not same_tree(SOURCE, t)]
    if check:
        for target in stale:
            print(f"out of sync: {target.relative_to(ROOT)}")
        if stale:
            print("run: uv run python scripts/sync_skills.py")
        return 1 if stale else 0
    for target in stale:
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(SOURCE, target)
        print(f"synced: {target.relative_to(ROOT)}")
    if not stale:
        print("skills already in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
