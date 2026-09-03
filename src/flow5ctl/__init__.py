"""flow5ctl — AI-driven aircraft design with flow5.

The public surface is the use-case layer (`flow5ctl.usecases`) and the CLI. The
`flow5ctl.flow5` package is the only code that knows flow5 exists; nothing in
`flow5ctl.geometry` or `flow5ctl.model` may import it, so the aerodynamic model is
testable with flow5 absent. See docs/ARCHITECTURE.md.
"""
from __future__ import annotations

__version__ = "0.1.0.dev0"
__all__ = ["__version__"]
