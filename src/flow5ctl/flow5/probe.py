"""Find flow5 and work out whether we trust this version.

The version must come from the program, never from the macOS application bundle: on
the verification machine `Info.plist` reported 7.70 while flow5 and Homebrew both
reported 7.57, and trusting the bundle put the wrong version in our own first log.
See docs/adr/0007-flow5-version-compatibility.md.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ..errors import SolverNotFound

VERIFIED = {"7.57"}
"""Versions flow5ctl has been checked against end to end."""

EXPECTED_OK = {"7.5", "7.6", "7.7"}
"""Minor series expected to work. Used only to soften the warning."""

KNOWN_BAD: dict[str, str] = {}
"""version -> reason. Empty so far."""

def _candidates() -> tuple[str, ...]:
    """Where flow5 usually lands, per platform.

    PATH is checked first, so this list only matters for a GUI install that never
    added itself to PATH — which is the normal case on macOS and Windows. Only the
    macOS entries are verified; the others are best guesses and a wrong guess here
    just means the user has to set FLOW5CTL_FLOW5. Reports welcome:
    https://github.com/97kuek/flow5ctl/issues
    """
    home = Path.home()
    if sys.platform == "darwin":
        return (
            "/Applications/flow5.app/Contents/MacOS/flow5",
            str(home / "Applications/flow5.app/Contents/MacOS/flow5"),
            "/usr/local/bin/flow5",
            "/opt/homebrew/bin/flow5",
        )
    if sys.platform == "win32":
        program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        program_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", str(home / "AppData/Local"))
        return tuple(
            str(Path(base) / sub / "flow5.exe")
            for base in (program_files, program_files_x86, local)
            for sub in ("flow5", "flow5/bin")
        )
    # Linux and other Unix
    return (
        "/usr/local/bin/flow5",
        "/usr/bin/flow5",
        "/opt/flow5/flow5",
        "/opt/flow5/bin/flow5",
        str(home / ".local/bin/flow5"),
        str(home / "flow5/flow5"),
        str(home / "Applications/flow5/flow5"),
    )

_VERSION_RE = re.compile(r"v?(\d+)\.(\d+)")


@dataclass(frozen=True, slots=True)
class Flow5Install:
    path: Path
    version: str
    verified: bool
    note: str = ""


def find_executable(explicit: str | os.PathLike[str] | None = None) -> Path:
    if explicit:
        p = Path(explicit)
        if p.is_file() and os.access(p, os.X_OK):
            return p
        raise SolverNotFound(f"{p} is not an executable file")

    env = os.environ.get("FLOW5CTL_FLOW5")
    if env:
        return find_executable(env)

    which = shutil.which("flow5")
    if which:
        return Path(which)

    candidates = _candidates()
    for cand in candidates:
        p = Path(cand)
        if p.is_file() and (sys.platform == "win32" or os.access(p, os.X_OK)):
            return p

    raise SolverNotFound(
        "flow5 was not found. Install it from https://flow5.tech, or set "
        "FLOW5CTL_FLOW5 to the executable. Looked on PATH and at:\n  "
        + "\n  ".join(candidates)
    )


def read_version(exe: Path, timeout: float = 20.0) -> str:
    """Ask flow5 for its version.

    The output repeats the application name (`flow5 flow5 v7.57`), so the
    `v<major>.<minor>` token is extracted rather than the whole string.
    """
    try:
        r = subprocess.run([str(exe), "--version"], capture_output=True, text=True,
                           timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SolverNotFound(f"could not run {exe}: {exc}") from exc
    m = _VERSION_RE.search(r.stdout + r.stderr)
    if not m:
        raise SolverNotFound(f"could not read a version from {exe}: {r.stdout.strip()!r}")
    return f"{m.group(1)}.{m.group(2)}"


def probe(explicit: str | os.PathLike[str] | None = None) -> Flow5Install:
    exe = find_executable(explicit)
    version = read_version(exe)

    if version in KNOWN_BAD:
        return Flow5Install(exe, version, verified=False, note=KNOWN_BAD[version])
    if version in VERIFIED:
        return Flow5Install(exe, version, verified=True)

    series = ".".join(version.split(".")[:2])[:3]
    close = series in EXPECTED_OK or version[:3] in EXPECTED_OK
    note = (
        f"flow5 {version} has not been verified with flow5ctl "
        f"(verified: {', '.join(sorted(VERIFIED))}). "
        + ("It is close enough that it will probably work, but results are unconfirmed. "
           if close else
           "Results may be wrong in ways flow5ctl cannot detect. ")
        + "Please report what you find: https://github.com/97kuek/flow5ctl/issues"
    )
    return Flow5Install(exe, version, verified=False, note=note)
