"""flow5ctl — AI-driven aircraft design with flow5.

The public surface is the use-case layer (`flow5ctl.usecases`) and the CLI. The
`flow5ctl.flow5` package is the only code that knows flow5 exists; nothing in
`flow5ctl.geometry` or `flow5ctl.model` may import it, so the aerodynamic model is
testable with flow5 absent. See docs/ARCHITECTURE.md.
"""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _installed_version


def _version() -> str:
    """The one place the version comes from is the packaging metadata.

    It used to be written here as well as in `pyproject.toml`, and the two drifted
    the moment one of them was bumped: the 0.1.0 wheel was built correctly while
    `flow5ctl --version`, `doctor` and the `flow5://status` resource all still said
    `0.1.0.dev0`. A user installing a release would have been told they had a
    pre-release. Reading it back from the installed distribution means there is
    nothing to keep in step.

    The fallback is for running out of a source tree with nothing installed at all,
    where the honest answer is that we do not know rather than a number that might
    be wrong.
    """
    try:
        return _installed_version("flow5ctl")
    except PackageNotFoundError:
        return "0+unknown"


__version__ = _version()
__all__ = ["__version__"]
