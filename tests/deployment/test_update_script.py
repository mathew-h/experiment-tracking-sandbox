"""Invariants of the lab-PC deploy script, `update.ps1`.

These are static assertions on the script text, not an execution of it. `update.ps1`
drives `nssm` and a live Windows service, so it cannot be run under pytest; the first
run of any change to it must be an attended, manual one on the lab PC.

What they DO buy: every property asserted here is one whose loss produced, or would
produce, a silently broken deploy. Each was learned from a real 2026-07-30 incident in
which the lab PC sat 22 commits behind for ten days while the nightly job logged
`FAILED` to a file nobody read:

  * a dirty working tree blocks `git pull` forever, so the script must clear it;
  * clearing it with `reset --hard origin/main` moves HEAD itself, which makes the
    script's own `git pull` a no-op, so `$headBefore -eq $headAfter` fires the
    "no new commits" early exit and the frontend is NEVER rebuilt — a deploy that
    logs SUCCESS while shipping a stale `frontend/dist`;
  * `git clean -fdx` would delete `.venv`, `.env` and `node_modules`, all of which
    are gitignored and none of which are recoverable from the repo;
  * the service must be stopped before git rewrites files (open file handles are the
    most likely cause of the partial pull that started the incident) — but stopping
    it first means any later failure leaves the lab app OFFLINE rather than merely
    stale, so every exit path has to bring it back up.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "update.ps1"


@pytest.fixture(scope="module")
def script_text() -> str:
    assert SCRIPT.is_file(), f"{SCRIPT} is missing"
    return SCRIPT.read_text(encoding="utf-8-sig")


def _blank_block_comments(lines: list[str]) -> list[str]:
    """Blank out `<# ... #>` bodies, preserving line count so indices stay comparable.

    The script's own .NOTES block quotes the forbidden commands in order to explain why
    they are forbidden, so the "never do X" assertions have to read code, not prose.
    """
    out: list[str] = []
    in_block = False
    for line in lines:
        stripped = line.strip()
        if not in_block and stripped.startswith("<#"):
            in_block = not stripped.endswith("#>") or stripped == "<#"
            out.append("")
            continue
        if in_block:
            if "#>" in line:
                in_block = False
            out.append("")
            continue
        out.append(line)
    return out


@pytest.fixture(scope="module")
def script_lines(script_text: str) -> list[str]:
    """Executable lines only — block comments blanked, line numbering preserved."""
    return _blank_block_comments(script_text.splitlines())


def _first_line_matching(lines: list[str], pattern: str) -> int:
    """0-indexed line number of the first line matching `pattern`, ignoring comments."""
    rx = re.compile(pattern)
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        if rx.search(line):
            return i
    raise AssertionError(f"no non-comment line matches {pattern!r}")


# A git *invocation*, anchored at the start of the line, so that a progress message
# such as Write-Step "Step 1: git pull" is not mistaken for the command itself.
GIT_PULL = r"^\s*git\b[^\"']*\bpull\b"


# ---------------------------------------------------------------------------
# The reset target — the trap that produces a SUCCESS-logging no-op deploy
# ---------------------------------------------------------------------------

def test_dirty_tree_is_reset_to_head_not_to_origin_main(script_lines):
    """`reset --hard HEAD` leaves the version move to the script's own `git pull`,
    which is what makes the frontend-rebuild detection fire."""
    _first_line_matching(script_lines, r"reset\s+--hard\s+HEAD\b")


def test_reset_never_targets_origin_main(script_lines):
    """`reset --hard origin/main` advances HEAD itself, so the subsequent pull finds
    nothing, `$headBefore -eq $headAfter`, and Step 5 never rebuilds the frontend."""
    for line in script_lines:
        if line.lstrip().startswith("#"):
            continue
        assert not re.search(r"reset\s+--hard\s+origin/", line), (
            f"reset --hard must target HEAD, never a remote ref: {line.strip()!r}"
        )


def test_clean_never_uses_x_flag(script_lines):
    """-x removes ignored files: .venv (which this script's own pip/alembic live in),
    .env, frontend/.env.local, node_modules, frontend/dist."""
    for line in script_lines:
        if line.lstrip().startswith("#"):
            continue
        match = re.search(r"\bclean\s+(-[a-zA-Z]+)", line)
        if match:
            assert "x" not in match.group(1), (
                f"git clean must not use -x: {line.strip()!r}"
            )


def test_untracked_files_are_cleaned_so_the_pull_is_not_blocked(script_lines):
    _first_line_matching(script_lines, r"\bclean\s+-[a-zA-Z]*f[a-zA-Z]*d")


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------

def test_service_is_stopped_before_git_rewrites_files(script_lines):
    """Open handles held by the running service are the leading suspect for the
    partial pull that left the tree dirty in the first place."""
    stop = _first_line_matching(script_lines, r"nssm\s+stop")
    pull = _first_line_matching(script_lines, GIT_PULL)
    assert stop < pull, f"nssm stop (line {stop + 1}) must precede git pull (line {pull + 1})"


def test_tree_is_cleaned_before_the_pull(script_lines):
    reset = _first_line_matching(script_lines, r"reset\s+--hard\s+HEAD\b")
    pull = _first_line_matching(script_lines, GIT_PULL)
    assert reset < pull


def test_head_before_is_captured_after_cleaning_and_before_pulling(script_lines):
    """Cleaning does not move HEAD, but capturing $headBefore after the pull would
    make the change-detection compare a commit against itself."""
    head_before = _first_line_matching(script_lines, r"\$headBefore\s*=")
    pull = _first_line_matching(script_lines, GIT_PULL)
    assert head_before < pull


# ---------------------------------------------------------------------------
# The pull actually applied
# ---------------------------------------------------------------------------

def test_head_is_verified_against_origin_main_after_the_pull(script_lines):
    """A partial pull must not be able to report SUCCESS."""
    verify = _first_line_matching(script_lines, r"rev-parse\s+origin/main")
    pull = _first_line_matching(script_lines, GIT_PULL)
    assert verify > pull, "the origin/main comparison must happen after the pull"


# ---------------------------------------------------------------------------
# The service always comes back up
# ---------------------------------------------------------------------------

def test_abort_starts_the_service_again(script_text):
    """Stopping the service up front means a mid-script failure would otherwise
    leave the lab PC's app offline until someone noticed."""
    body = re.search(r"function\s+Abort\s*\{(.*?)\n\}", script_text, re.S)
    assert body, "Abort function not found"
    assert "Start-TrackerService" in body.group(1), (
        "Abort must bring the service back up before exiting"
    )


def test_no_new_commits_path_starts_the_service(script_text):
    """The early-exit branch runs when the tree was merely dirty and there was
    nothing to pull; it must not leave the service stopped."""
    branch = re.search(
        r"if\s*\(\s*\$headBefore\s+-eq\s+\$headAfter\s*\)\s*\{(.*?)\n\}", script_text, re.S
    )
    assert branch, "the '$headBefore -eq $headAfter' early-exit branch was not found"
    assert "Start-TrackerService" in branch.group(1)


def test_success_path_starts_the_service(script_text):
    assert "Start-TrackerService" in script_text
    # A bare `nssm restart` on a service we deliberately stopped is not equivalent:
    # it must be a start, routed through the helper that clears the stopped flag.
    assert re.search(r"nssm\s+start", script_text), "no 'nssm start' found"


# ---------------------------------------------------------------------------
# It is valid PowerShell
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    shutil.which("powershell.exe") is None and shutil.which("pwsh") is None,
    reason="no PowerShell host available to parse the script",
)
def test_script_parses_as_powershell():
    host = shutil.which("pwsh") or shutil.which("powershell.exe")
    checker = (
        "$errors = $null; "
        "[void][System.Management.Automation.Language.Parser]::ParseFile("
        f"'{SCRIPT.as_posix()}', [ref]$null, [ref]$errors); "
        "if ($errors) { $errors | ForEach-Object { $_.ToString() }; exit 1 } "
        "else { 'OK'; exit 0 }"
    )
    result = subprocess.run(
        [host, "-NoProfile", "-NonInteractive", "-Command", checker],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"PowerShell parse errors:\n{result.stdout}\n{result.stderr}"
