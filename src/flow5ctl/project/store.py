"""A design is a directory, not a session.

`design.yaml` is the source of truth; `build/` holds regenerable XML and raw solver
output; `results/` holds normalised JSON small enough to diff. Everything survives a
client restart, is reviewable by a human, and is shared between the CLI and the MCP
server. See ADR-0003.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ..errors import DesignError, Flow5ctlError
from ..model.design import Design

DESIGN_FILE = "design.yaml"
STATE_DIR = ".flow5ctl"
GITIGNORE = """# flow5ctl: everything here is regenerable from design.yaml
build/
.flow5ctl/lock
# Half-written files from an atomic write whose process was killed outright.
.*.tmp
"""


def _write_atomic(path: Path, text: str) -> None:
    """Replace `path` with `text` so that no failure can leave a partial file.

    `Path.write_text` opens with O_TRUNC, so a process killed between the truncate
    and the write leaves an empty or half-written file. For `build/` output that
    only costs a re-run, but `design.yaml` is the one file in a project that is not
    regenerable — it is what the person (or the agent) authored. Writing a sibling
    temporary file and renaming it means the old contents stay intact until the new
    ones are complete, because rename within a directory is atomic.

    What each step is for, since the recipe is easy to copy without the parts that
    make it work:

    - `fsync` on the file, before the rename, so the bytes are on the disk and not
      only in the page cache. Without it the rename can be recorded while the data
      it points at is not, which is how a crash produces a file of the right name
      full of zeroes. Renaming is atomic with respect to *other processes*, which is
      a different guarantee from surviving a power cut.
    - `fsync` on the directory, after the rename, so the new directory entry itself
      is durable.
    - The destination's mode is carried over. A fresh temporary file gets
      `0666 & ~umask`, so without this a `0600` design would silently become
      readable by everyone the first time it was edited under a permissive umask.
    - The pid is in the temporary name so two processes cannot collide on it. Two
      *threads* of one process still can, which is why nothing here is a substitute
      for `Project.lock`.
    - Cleanup cannot mask the real error: if removing the temporary file fails too,
      the original exception is the one that propagates.

    A process killed with SIGKILL still leaves the temporary file behind. That is
    why `.*.tmp` is in the project `.gitignore` — it is litter, not lost data.
    """
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        mode = path.stat().st_mode & 0o777
    except FileNotFoundError:
        mode = None
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        # Never let cleanup replace the error the caller needs to see.
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        raise
    _fsync_dir(path.parent)


def _fsync_dir(directory: Path) -> None:
    """Make a rename durable. Not every platform lets us, and that is not fatal."""
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        # Windows and some network filesystems refuse; the rename still happened.
        with contextlib.suppress(OSError):
            os.fsync(fd)
    finally:
        os.close(fd)


def workspace_root() -> Path:
    """Where designs live for clients that have no filesystem of their own."""
    return Path(os.environ.get("FLOW5CTL_WORKSPACE", Path.home() / "flow5ctl")).expanduser()


def explain_validation(exc: ValidationError, path: Path, lead: str = "") -> str:
    """Turn a Pydantic error into the sentence a person needs to fix the file."""
    lines: list[str] = []
    for err in exc.errors()[:6]:
        where = ".".join(str(p) for p in err["loc"]) or "(top level)"
        kind, msg = err["type"], err["msg"]
        if kind == "missing":
            lines.append(f"  {where} is required but missing")
        elif kind == "extra_forbidden":
            lines.append(f"  {where} is not a field flow5ctl knows — check the spelling")
        else:
            lines.append(f"  {where}: {msg}")
    more = len(exc.errors()) - len(lines)
    if more > 0:
        lines.append(f"  … and {more} more")
    head = lead or f"{path} does not describe a valid design:"
    return head + "\n" + "\n".join(lines)


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
        """Read `design.yaml`, or say what is wrong with it in one line.

        Design files are meant to be hand-edited, so a validation failure is a normal
        event and has to read like a message rather than a stack trace. Pydantic's own
        `ValidationError` renders as a wall of dotted paths and a docs URL.
        """
        text = self.design_path.read_text(encoding="utf-8")
        try:
            raw = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            where = f" at line {mark.line + 1}" if mark is not None else ""
            raise DesignError(
                f"{self.design_path} is not valid YAML{where}: "
                f"{getattr(exc, 'problem', exc)}"
            ) from exc
        if not isinstance(raw, dict):
            raise DesignError(
                f"{self.design_path} should hold a mapping of fields, "
                f"not {type(raw).__name__}."
            )
        try:
            return Design.model_validate(raw)
        except ValidationError as exc:
            raise DesignError(explain_validation(exc, self.design_path)) from exc

    def save(self, design: Design) -> None:
        data = design.model_dump(mode="json", by_alias=True, exclude_none=True)
        _write_atomic(
            self.design_path,
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100),
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
        _write_atomic(self.state_path, json.dumps(s, indent=2, sort_keys=True))
        return s

    def write_result(self, name: str, payload: dict[str, Any]) -> Path:
        self.results.mkdir(parents=True, exist_ok=True)
        path = self.results / f"{name}.json"
        _write_atomic(path, json.dumps(payload, indent=2, sort_keys=False))
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
                        f"(lock: {path}). {_lock_holder(path)}"
                    ) from None
                time.sleep(0.2)
        try:
            yield
        finally:
            path.unlink(missing_ok=True)


_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$")


def safe_name(name: str) -> str:
    """Validate a design name that came from outside.

    The MCP server addresses designs by name only and must never read or write
    outside its workspace, so a name containing a path separator, a traversal, or a
    null byte is rejected here rather than resolved.
    """
    if not isinstance(name, str) or not _SAFE_NAME.match(name):
        raise DesignError(
            f"{name!r} is not a valid design name. Use letters, digits, spaces, "
            "dots, hyphens and underscores only — a name is not a path."
        )
    if name.strip(". ") != name.strip():
        raise DesignError(f"{name!r} is not a valid design name")
    return name


def _lock_holder(path: Path) -> str:
    """Say enough about the lock's owner that a person can decide to remove it.

    The lock is never broken automatically. A stale lock is indistinguishable from a
    live one except through the pid, and a pid can be reused by an unrelated process
    between the check and the removal — deleting a live run's lock would let two
    flow5 invocations write the same `build/`, which is the thing the lock exists to
    prevent. So the choice stays with the person, and this supplies what the old
    message asked them to judge without any way of judging it.
    """
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return "Remove it if that is stale."
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return f"Process {pid} no longer exists, so the lock is stale — remove it."
    except PermissionError:
        pass  # alive, owned by someone else
    return f"Held by pid {pid}, which is still running."


def resolve_in_workspace(name: str) -> Project:
    """Open a design by name, strictly inside the workspace.

    Unlike `Project.resolve`, this never accepts a path and never falls back to the
    current directory. It is what the MCP server uses.
    """
    ws = workspace_root().resolve()
    root = (ws / safe_name(name)).resolve()
    if root != ws and ws not in root.parents:
        raise DesignError(f"{name!r} resolves outside the workspace")
    if not (root / DESIGN_FILE).exists():
        raise DesignError(
            f"no design called {name!r}. Known: "
            f"{', '.join(n for n, _ in list_designs()) or 'none'}"
        )
    return Project(root)


def list_designs(root: Path | None = None) -> list[tuple[str, Path]]:
    ws = Path(root) if root else workspace_root()
    if not ws.is_dir():
        return []
    return sorted(
        (p.name, p) for p in ws.iterdir() if (p / DESIGN_FILE).exists()
    )
