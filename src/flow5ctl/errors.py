"""Error types.

The distinction that matters to an agent is *whose problem it is*: a design that
cannot work, a solver that could not converge, or a bug in flow5ctl. An agent told
"this is a flow5ctl bug" stops trying to fix the aircraft and reports it instead.
"""
from __future__ import annotations


class Flow5ctlError(Exception):
    """Base class. Every raised error carries a message meant for a human or agent."""


class DesignError(Flow5ctlError):
    """The design is invalid or physically impossible. The user can fix this."""


class SolverError(Flow5ctlError):
    """flow5 ran and failed. Often fixable by changing the analysis request."""


class SolverCrashed(SolverError):
    """flow5 terminated on a signal. Always a flow5ctl bug or a flow5 bug."""


class SolverNotFound(Flow5ctlError):
    """flow5 is not installed, or not where we looked."""


class UnsupportedByFlow5(Flow5ctlError):
    """Something flow5 genuinely cannot do through its script interface.

    Raised for flaps and T6 control polars: flow5 has no hinge elements in its plane
    XML, and planes loaded from a project file cannot be paired with new analyses.
    See docs/FLOW5-INTERFACE.md section 3.3.
    """


class ParseError(Flow5ctlError):
    """flow5's output could not be read, or read incompletely.

    Never downgrade this to a warning. flow5's output has several traps that silently
    drop operating points; an incomplete parse must be loud.
    See docs/adr/0010-treat-solver-output-as-hostile.md.
    """


class InternalError(Flow5ctlError):
    """flow5ctl generated something invalid. Our bug — ask the user to report it."""

    def __init__(self, message: str) -> None:
        super().__init__(
            f"{message}\n\nThis is a bug in flow5ctl, not in your design. "
            "Please report it: https://github.com/97kuek/flow5ctl/issues"
        )
