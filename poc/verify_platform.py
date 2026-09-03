#!/usr/bin/env python3
"""Check whether flow5ctl's assumptions about flow5 hold on this platform.

Everything in docs/FLOW5-INTERFACE.md was verified on macOS with flow5 7.57. Linux and
Windows are unverified, and this script is how that gets fixed without us owning those
machines.

    python3 poc/verify_platform.py

It runs flow5 a handful of times, checks each documented behaviour, and prints a report
to paste into a platform report:
https://github.com/97kuek/flow5ctl/issues/new?template=platform_report.yml

Needs only the standard library and an installed flow5. Nothing is written outside a
temporary directory.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))
import f5
import gen

CANDIDATES = (
    "/Applications/flow5.app/Contents/MacOS/flow5",
    str(Path.home() / "Applications/flow5.app/Contents/MacOS/flow5"),
    "/usr/local/bin/flow5", "/usr/bin/flow5",
    "/opt/flow5/flow5", "/opt/flow5/bin/flow5",
    str(Path.home() / ".local/bin/flow5"), str(Path.home() / "flow5/flow5"),
    r"C:\Program Files\flow5\flow5.exe",
)


@dataclass
class Report:
    checks: list[tuple[str, str, str]] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.checks.append((name, status, detail))
        mark = {"pass": "  ok  ", "fail": " FAIL ", "info": " info ", "skip": " skip "}[status]
        print(f"[{mark}] {name}" + (f"\n           {detail}" if detail else ""))

    @property
    def failures(self) -> int:
        return sum(1 for _, s, _ in self.checks if s == "fail")


def find_flow5() -> Path | None:
    env = os.environ.get("FLOW5CTL_FLOW5")
    if env and Path(env).is_file():
        return Path(env)
    which = shutil.which("flow5")
    if which:
        return Path(which)
    return next((Path(c) for c in CANDIDATES if Path(c).is_file()), None)


def main() -> int:
    r = Report()
    print(f"\nflow5ctl platform verification\n{'=' * 62}")
    print(f"platform   {platform.platform()}")
    print(f"python     {sys.version.split()[0]}")
    print(f"{'=' * 62}\n")

    exe = find_flow5()
    if exe is None:
        r.add("flow5 found", "fail",
              "not on PATH and not at any known location. Set FLOW5CTL_FLOW5 and re-run.\n"
              "           Looked at:\n           " + "\n           ".join(CANDIDATES))
        return 1
    r.add("flow5 found", "pass", str(exe))
    f5.FLOW5 = str(exe)

    # --- version, and whether any packaging metadata disagrees with the program
    v = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=60)
    r.add("--version works", "pass" if v.returncode == 0 else "fail",
          (v.stdout + v.stderr).strip())

    # --- headless execution
    tmp = Path(tempfile.mkdtemp(prefix="flow5ctl-verify-"))
    try:
        root = tmp / "case"
        f5.clean(str(root))
        f5.write_foil(f"{root}/foils/NACA0012.dat", "NACA0012", f5.naca4("0012"))
        gen.plane_xml(f"{root}/planes/w.xml", "W", [{
            "name": "Main Wing", "type": "MAINWING", "symmetric": True, "sections": [
                {"y_position": 0.0, "Chord": 0.2, "y_number_of_panels": 20,
                 "y_panel_distribution": "UNIFORM", "x_number_of_panels": 13,
                 "Left_Side_FoilName": "NACA0012", "Right_Side_FoilName": "NACA0012"},
                {"y_position": 1.0, "Chord": 0.2, "y_number_of_panels": 1,
                 "x_number_of_panels": 13,
                 "Left_Side_FoilName": "NACA0012", "Right_Side_FoilName": "NACA0012"}]}],
            point_masses=[("m", 1.0, 0.05, 0, 0)])
        gen.polar_xml(f"{root}/analyses/t1.xml", "t1", "W", area=0.4, span=2.0, chord=0.2,
                      velocity=15.0, mass=1.0, cog=(0.05, 0, 0))
        gen.script_xml(f"{root}/script.xml", str(root), project="V",
                       foils=["NACA0012.dat"], ranges={"T12_Range": "0.0, 8.0, 2.0"},
                       outputs={"make_polars_text_file": "true", "make_oppoints": "true",
                                "make_oppoints_text_file": "true"})
        elapsed, out = f5.run(f"{root}/script.xml", timeout=600)
        verdict = f5.verdict(out)[0]
        r.add("runs headless and exits", "pass" if out else "fail",
              f"{elapsed:.1f} s, verdict {verdict}")

        polar = root / "out" / "V" / "W" / "t1.csv"
        r.add("writes the polar where documented", "pass" if polar.is_file() else "fail",
              str(polar.relative_to(root)) if polar.is_file()
              else "expected out/<project>/<plane>/<polar>.csv")

        if polar.is_file():
            text = polar.read_text(encoding="utf-8", errors="replace")
            lines = text.split("\n")
            hi = next((i for i, ln in enumerate(lines)
                       if "Ctrl" in ln and "CL" in ln and "CD" in ln), None)
            if hi is None:
                r.add("polar table header present", "fail", "no header row found")
            else:
                head, data = lines[hi], lines[hi + 1] if hi + 1 < len(lines) else ""
                ncol = len(data.split())
                r.add("polar 'csv' is whitespace-aligned, not comma separated",
                      "pass" if "," not in head else "fail",
                      f"{ncol} columns" if "," not in head else "commas found in the header")
                r.add("first data row is welded onto the header line",
                      "pass" if len(head) > len(data) > 0 else "info",
                      f"header {len(head)} chars, data row {len(data)} chars")
                claimed = next((ln.split("=")[1].strip() for ln in lines[:hi]
                                if "Nbr. of data points" in ln), None)
                rows = sum(1 for ln in lines[hi + 1:] if len(ln.split()) == ncol)
                r.add("declared point count matches the rows present",
                      "pass" if claimed and int(claimed) == rows + 1 else "fail",
                      f"declares {claimed}, found {rows} standalone + 1 embedded")
                sm = next((ln for ln in lines[:hi] if "Static margin" in ln), "")
                r.add("static margin is reported as a percentage", "info", sm.strip())

        # --- the crash: both script sections in one file
        crash_root = tmp / "crash"
        f5.clean(str(crash_root))
        f5.write_foil(f"{crash_root}/foils/NACA0012.dat", "NACA0012", f5.naca4("0012"))
        shutil.copytree(root / "planes", crash_root / "planes")
        shutil.copytree(root / "analyses", crash_root / "analyses")
        foil_section = """  <foil_analysis>
    <Foil_Files><Foil_File_Name>NACA0012.dat</Foil_File_Name></Foil_Files>
    <Batch_Analysis_Data><Polar_Type>FIXEDSPEEDPOLAR</Polar_Type>
      <Batch_Range><Reynolds>200000</Reynolds></Batch_Range></Batch_Analysis_Data>
    <OpPoint_Range><Alpha>-2.0, 4.0, 2.0</Alpha><Spec_Alpha>true</Spec_Alpha></OpPoint_Range>
    <Output><make_polars_text_file>true</make_polars_text_file></Output>
  </foil_analysis>
"""
        gen.script_xml(f"{crash_root}/script.xml", str(crash_root), project="C",
                       foils=["NACA0012.dat"], foil_section=foil_section,
                       ranges={"T12_Range": "0.0, 4.0, 2.0"})
        proc = subprocess.run([str(exe), "-s", f"{crash_root}/script.xml"],
                              capture_output=True, text=True, timeout=600)
        crashed = proc.returncode != 0
        r.add("foil_analysis + Plane_analysis in one script crashes flow5",
              "pass" if crashed else "info",
              f"exit {proc.returncode}" + ("" if crashed else
                                           " — this platform does NOT crash. Please report: "
                                           "flow5ctl's two-pass design may be unnecessary here."))

        # --- exit code on a rejected script
        bad = tmp / "bad.xml"
        bad.write_text("<?xml version=\"1.0\"?><nonsense/>", encoding="utf-8")
        proc = subprocess.run([str(exe), "-s", str(bad)], capture_output=True,
                              text=True, timeout=120)
        r.add("a rejected script still exits 0",
              "pass" if proc.returncode == 0 else "info", f"exit {proc.returncode}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{'=' * 62}")
    if r.failures:
        print(f"{r.failures} check(s) FAILED — flow5ctl's assumptions do not all hold here.")
        print("Please open a platform report with this output:")
    else:
        print("All checks passed. flow5ctl's documented assumptions hold on this platform.")
        print("Please still report it, so the compatibility matrix can say so:")
    print("https://github.com/97kuek/flow5ctl/issues/new?template=platform_report.yml")
    return 1 if r.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
