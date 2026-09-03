"""Run flow5.

Two invocations, always: 2D polars first, then the plane analysis. A single script
containing both sections segfaults flow5 — verified reproducibly, with no output at
all to diagnose from. See ADR-0009.

That is also why the exit code is checked as well as stdout: on a crash there is
nothing to parse.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from ..errors import InternalError, SolverError
from .markers import Diagnosis, Outcome, diagnose, discarded_points, panel_count

DEFAULT_TIMEOUT = 900.0


@dataclass(slots=True)
class RunResult:
    returncode: int
    stdout: str
    elapsed: float
    script: Path
    diagnosis: Diagnosis

    @property
    def ok(self) -> bool:
        return self.diagnosis.outcome is Outcome.OK

    @property
    def panels(self) -> int | None:
        return panel_count(self.stdout)

    @property
    def discarded(self) -> int:
        return discarded_points(self.stdout)

    def raise_for_status(self) -> RunResult:
        if self.ok:
            return self
        d = self.diagnosis
        detail = f"{d.message}\n{d.hint}".strip()
        if d.internal:
            raise InternalError(detail)
        raise SolverError(detail)


def run_script(exe: Path, script: Path, *, timeout: float = DEFAULT_TIMEOUT,
               progress: bool = True, cwd: Path | None = None) -> RunResult:
    """Invoke `flow5 -s <script>` and classify the outcome."""
    script = Path(script)
    if not script.is_file():
        raise InternalError(f"script not written: {script}")

    cmd = [str(exe), *(["-p"] if progress else []), "-s", str(script)]
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              cwd=None if cwd is None else str(cwd))
        stdout, rc = proc.stdout + proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        raise SolverError(
            f"flow5 did not finish within {timeout:g} s. Reduce the panel count or the "
            f"number of operating points, or raise the timeout.\n"
            f"Last output:\n{stdout[-800:]}"
        ) from exc

    elapsed = time.monotonic() - started
    return RunResult(rc, stdout, elapsed, script, diagnose(stdout, rc))


# ------------------------------------------------------------------------ two passes

@dataclass(slots=True)
class Workspace:
    """The `build/` layout for one analysis. Everything here is regenerable."""

    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)

    @property
    def foils(self) -> Path:
        return self.root / "foils"

    @property
    def planes(self) -> Path:
        return self.root / "planes"

    @property
    def analyses(self) -> Path:
        return self.root / "analyses"

    @property
    def xfoil_polars(self) -> Path:
        return self.root / "xfoil_polars"

    @property
    def out(self) -> Path:
        return self.root / "out"

    def prepare(self, *, keep_polars: bool = True) -> Workspace:
        """Create the directories, clearing what is not worth keeping.

        2D polars are expensive (~15 s) and the 3D run that consumes them costs under
        2 s, so they are cached by default.
        """
        for d in (self.foils, self.planes, self.analyses, self.out):
            if d.exists():
                shutil.rmtree(d)
        for d in (self.foils, self.planes, self.analyses, self.out, self.xfoil_polars):
            d.mkdir(parents=True, exist_ok=True)
        if not keep_polars:
            shutil.rmtree(self.xfoil_polars, ignore_errors=True)
            self.xfoil_polars.mkdir(parents=True, exist_ok=True)
        return self

    def project_dir(self, project: str) -> Path:
        """Where flow5 writes, given `project_file_name`.

        Deterministic only because the script always sets `make_project_file` and
        `project_file_name`; otherwise flow5 uses a timestamped directory.
        """
        return self.out / project

    def stage_foil_polars(self, produced_root: Path) -> int:
        """Copy pass-1 polars into `xfoil_polars/` as `.txt` for pass 2.

        flow5 only scans that directory for `*.txt`, and names are flattened with the
        foil directory as a prefix so two foils cannot collide.
        """
        n = 0
        self.xfoil_polars.mkdir(parents=True, exist_ok=True)
        for src in sorted(Path(produced_root).rglob("*.txt")):
            dst = self.xfoil_polars / f"{src.parent.name}_{src.stem}.txt"
            shutil.copyfile(src, dst)
            n += 1
        return n

    def cached_polar_count(self) -> int:
        return len(list(self.xfoil_polars.glob("*.txt"))) if self.xfoil_polars.exists() else 0
