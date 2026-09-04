#!/usr/bin/env python3
"""Repository checks that do not need flow5 installed.

  1. Every relative Markdown link resolves.
  2. No upstream flow5 source is committed (ADR-0006).
  3. No solver output or generated artifacts are committed.
  4. FLOW5-INTERFACE.md keeps its evidence markers.

Run: python3 tools/check_docs.py
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FAIL: list[str] = []


def tracked() -> list[pathlib.Path]:
    """Everything git would ship, plus anything staged for it that is not yet.

    `git ls-files` alone lists only what is already tracked, so a brand-new document
    was never link-checked until after it had been committed — which is exactly how
    a broken link reached CI: it passed here while the file was untracked, and
    failed on the next push. `--others` with the standard exclusions adds files git
    can see and would add, and keeps ignored ones (scratch output, gitignored
    aircraft material) out.
    """
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / p for p in dict.fromkeys(out.split("\0")) if p]


#: README.md carries absolute URLs because PyPI renders it on the project page and
#: does not rewrite relative ones — 34 links pointed at nowhere for anyone arriving
#: from there. They still have to resolve, so links back at this repository are
#: mapped to paths and checked like any other.
REPO = "https://github.com/97kuek/flow5ctl"
RAW = "https://raw.githubusercontent.com/97kuek/flow5ctl/main"
_SELF = (f"{REPO}/blob/main/", f"{REPO}/tree/main/", f"{RAW}/")


def check_links(files: list[pathlib.Path]) -> None:
    link = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
    n = 0
    for f in files:
        if f.suffix != ".md":
            continue
        for m in link.finditer(f.read_text(encoding="utf-8")):
            href = m.group(1)
            base = f.parent
            for prefix in _SELF:
                if href.startswith(prefix):
                    href, base = href[len(prefix):], ROOT
                    break
            else:
                if href.startswith(("http://", "https://", "#", "mailto:")):
                    continue
            target = href.split("#")[0]
            if not target:
                continue
            n += 1
            if not (base / target).resolve().exists():
                FAIL.append(f"broken link  {f.relative_to(ROOT)} -> {m.group(1)}")
    print(f"  checked {n} links, relative and back into this repo")


def check_no_upstream_source(files: list[pathlib.Path]) -> None:
    """flow5 is GPL-3.0; its source must never live here. See ADR-0006."""
    fingerprints = ("This file is part of flow5", "XflScriptReader",
                    "XmlPlanePolarReader", "Copyright (C) 2025 André Deperrois")
    bad = 0
    for f in files:
        if f.suffix in (".cpp", ".h", ".hpp", ".pro", ".pri"):
            FAIL.append(f"upstream source file committed  {f.relative_to(ROOT)}")
            bad += 1
            continue
        if f.suffix not in (".md", ".py", ".txt", ".yml", ".yaml"):
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        for fp in fingerprints:
            # a quoted identifier in prose is fine; a block of source is not
            if text.count(fp) > 0 and f.suffix not in (".md", ".py"):
                FAIL.append(f"possible upstream source in  {f.relative_to(ROOT)} ({fp!r})")
                bad += 1
    print(f"  licence hygiene: {bad} problem(s)")


def check_no_artifacts(files: list[pathlib.Path]) -> None:
    forbidden_dirs = ("poc/work/", "poc/ref/", "build/", "results/", ".flow5ctl/")
    forbidden_ext = (".fl5", ".stl", ".plr")
    bad = 0
    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        if any(rel.startswith(d) or f"/{d}" in rel for d in forbidden_dirs):
            FAIL.append(f"generated artifact committed  {rel}")
            bad += 1
        if f.suffix in forbidden_ext:
            FAIL.append(f"solver artifact committed  {rel}")
            bad += 1
    print(f"  artifact hygiene: {bad} problem(s)")


def check_evidence_markers() -> None:
    """Facts about flow5 must be attributed. See AGENTS.md."""
    f = ROOT / "docs" / "FLOW5-INTERFACE.md"
    text = f.read_text(encoding="utf-8")
    run, src = text.count("**[run]**"), text.count("**[src]**")
    print(f"  evidence markers: {run} [run], {src} [src]")
    if run < 20 or src < 5:
        FAIL.append(f"FLOW5-INTERFACE.md lost evidence markers ([run]={run}, [src]={src})")
    if "flow5 7.70" in text:
        FAIL.append("FLOW5-INTERFACE.md claims flow5 7.70; the verified version is 7.57")


def check_python_compiles(files: list[pathlib.Path]) -> None:
    py = [f for f in files if f.suffix == ".py"]
    r = subprocess.run([sys.executable, "-m", "py_compile", *map(str, py)],
                       capture_output=True, text=True)
    if r.returncode:
        FAIL.append("python does not compile:\n" + r.stderr)
    print(f"  compiled {len(py)} python file(s)")


def main() -> int:
    files = tracked()
    print(f"checking {len(files)} tracked files")
    check_links(files)
    check_no_upstream_source(files)
    check_no_artifacts(files)
    check_evidence_markers()
    check_python_compiles(files)
    if FAIL:
        print("\nFAILED:")
        for m in FAIL:
            print("  -", m)
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
