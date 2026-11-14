"""The repo root stays small so anyone reading it cold finds things. See AGENTS.md, "Where things go"."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ALLOWED_AT_ROOT = {
    ".agents",
    ".claude",
    ".env.example",
    ".github",
    ".gitattributes",
    ".gitignore",
    ".python-version",
    "AGENTS.md",
    "CLAUDE.md",
    "GLOSSARY.md",
    "LICENSE",
    "README.md",
    "app",
    "data",
    "docs",
    "notebooks",
    "pyproject.toml",
    "scripts",
    "src",
    "tests",
    "uv.lock",
}

FORBIDDEN_MODULE_NAMES = {"utils.py", "helpers.py", "misc.py", "common.py"}


def tracked_files() -> list[str]:
    out = subprocess.run(
        # -z: without it git quotes non-ASCII paths ("docs/...") and the root check misreads them
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [path for path in out.stdout.split("\0") if path]


def test_nothing_unexpected_at_repo_root():
    at_root = {path.split("/")[0] for path in tracked_files()}
    unexpected = sorted(at_root - ALLOWED_AT_ROOT)
    assert not unexpected, f"move these to their home (see AGENTS.md): {unexpected}"


def test_no_catch_all_modules():
    catch_all = sorted(
        path
        for path in tracked_files()
        if path.startswith("src/") and Path(path).name in FORBIDDEN_MODULE_NAMES
    )
    assert not catch_all, f"name modules by what they do: {catch_all}"
