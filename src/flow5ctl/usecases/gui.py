"""Hand the design back to the human, in the tool they already know.

This is small and matters out of proportion to its size. It is the point where a
designer stops trusting a summary and looks at the aircraft with their own eyes. A
design tool that cannot be checked will not be adopted — least of all by people whose
aircraft carries a pilot.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..errors import DesignError
from ..flow5 import probe as probe_mod
from ..project.store import Project
from .edit import export


def open_in_flow5(project: Project, *, polar: str | None = None,
                  flow5: str | None = None, launch: bool = True) -> dict[str, Any]:
    try:
        exported = export(project, "fl5", polar=polar)
    except DesignError as exc:
        # `export`'s wording is about exporting, and the user typed `open`. Naming
        # the wrong operation in a refusal sends them to look at the wrong thing.
        raise DesignError(
            f"there is no flow5 project to open yet: {exc}".replace(
                "there is nothing to export.", "there is nothing to open.")
            + (" flow5 writes the `.fl5` as a side effect of an analysis, so run "
               "`analyze` first and then open it.")
        ) from exc
    path = Path(exported["path"])
    install = probe_mod.probe(flow5)

    if not launch:
        return {**exported, "launched": False,
                "command": f"{install.path} {path}"}

    try:
        if sys.platform == "darwin" and shutil.which("open"):
            # `open -a` hands the file to the running instance rather than starting a
            # second copy, which is what a designer switching back and forth wants.
            app = install.path.parents[2] if install.path.parts[-3:-1] == ("Contents", "MacOS") \
                else install.path
            subprocess.Popen(["open", "-a", str(app), str(path)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen([str(install.path), str(path)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    except OSError as exc:
        raise DesignError(
            f"could not launch flow5 ({exc}). The project is at {path} — open it by hand."
        ) from exc

    return {**exported, "launched": True, "flow5_version": install.version,
            "notes": [f"opened {path.name} in flow5 {install.version}."]}
