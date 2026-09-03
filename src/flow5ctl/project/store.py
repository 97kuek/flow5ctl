"""A design is a directory, not a session.

`design.yaml` is the source of truth; `build/` holds regenerable XML and raw solver
output; `results/` holds normalised JSON small enough to diff. Everything survives a
client restart, is reviewable by a human, and is shared between the CLI and the MCP
server. See ADR-0003.
"""
from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..errors import DesignError, Flow5ctlError
from ..model.design import Design

DESIGN_FILE = "design.yaml"
STATE_DIR = ".flow5ctl"
GITIGNORE = """# flow5ctl: everything here is regenerable from design.yaml
build/
.flow5ctl/lock
"""


def workspace_root() -> Path:
    """Where designs live for clients that have no filesystem of their own."""
    return Path(os.environ.get("FLOW5CTL_WORKSPACE", Path.home() / "flow5ctl")).expanduser()


@dataclass(slots=True)
class Project:
    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root).expanduser().resolve()

    # ---- layout ----
    @property
    def design_path(self) -> Path:
        return self.root / DESIGN_FILE

    @property
    def airfoils(self) -> Path:
        return self.root / "airfoils"

    @property
    def studies(self) -> Path:
        return self.root / "studies"

    @property
    def build(self) -> Path:
        return self.root / "build"

    @property
    def results(self) -> Path:
        return self.root / "results"

    @property
    def state_path(self) -> Path:
        return self.root / STATE_DIR / "state.json"

    @property
    def name(self) -> str:
        return self.root.name

    # ---- lifecycle ----
    @classmethod
    def create(cls, root: Path, design: Design, *, exist_ok: bool = False) -> Project:
        p = cls(root)
        if p.design_path.exists() and not exist_ok:
            raise DesignError(f"a design already exists at {p.root}")
        for d in (p.root, p.airfoils, p.studies, p.results, p.root / STATE_DIR):
            d.mkdir(parents=True, exist_ok=True)
        (p.root / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
        p.save(design)
        return p

    @classmethod
    def open(cls, root: Path) -> Project:
        p = cls(root)
        if not p.design_path.exists():
            raise DesignError(f"no {DESIGN_FILE} in {p.root}")
        return p

    @classmethod
    def resolve(cls, name_or_path: str | os.PathLike[str] | None) -> Project:
        """Accept a design name in the workspace, a path, or the current directory."""
        if name_or_path is None:
            cwd = Path.cwd()
            if (cwd / DESIGN_FILE).exists():
                return cls.open(cwd)
            raise DesignError(
                f"no {DESIGN_FILE} in the current directory. Give a design name "
                f"(they live in {workspace_root()}) or a path."
            )
        candidate = Path(name_or_path)
        if (candidate / DESIGN_FILE).exists():
            return cls.open(candidate)
        in_ws = workspace_root() / str(name_or_path)
        if (in_ws / DESIGN_FILE).exists():
            return cls.open(in_ws)
        raise DesignError(
            f"no design called {name_or_path!r}. Known: "
            f"{', '.join(n for n, _ in list_designs()) or 'none'}"
        )

    # ---- design ----
    def load(self) -> Design:
        raw = yaml.safe_load(self.design_path.read_text(encoding="utf-8")) or {}
        return Design.model_validate(raw)

    def save(self, design: Design) -> None:
        data = design.model_dump(mode="json", by_alias=True, exclude_none=True)
        self.design_path.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100),
            encoding="utf-8",
        )

    # ---- state ----
    def state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def update_state(self, **fields: Any) -> dict[str, Any]:
        s = self.state()
        s.update(fields)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(s, indent=2, sort_keys=True), encoding="utf-8")
        return s

    def write_result(self, name: str, payload: dict[str, Any]) -> Path:
        self.results.mkdir(parents=True, exist_ok=True)
        path = self.results / f"{name}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
        return path

    # ---- lock ----
    @contextmanager
    def lock(self, timeout: float = 300.0) -> Iterator[None]:
        """Serialise solver runs against one project — they share `build/`."""
        path = self.root / STATE_DIR / "lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + timeout
        while True:
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                break
            except FileExistsError:
                if time.monotonic() > deadline:
                    raise Flow5ctlError(
                        f"another flow5ctl run is using {self.root} "
                        f"(lock: {path}). Remove it if that is stale."
                    ) from None
                time.sleep(0.2)
        try:
            yield
        finally:
            path.unlink(missing_ok=True)


def list_designs(root: Path | None = None) -> list[tuple[str, Path]]:
    ws = Path(root) if root else workspace_root()
    if not ws.is_dir():
        return []
    return sorted(
        (p.name, p) for p in ws.iterdir() if (p / DESIGN_FILE).exists()
    )
