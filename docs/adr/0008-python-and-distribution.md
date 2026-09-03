# ADR-0008 — Python, and how it is distributed

**Status:** Accepted · 2026-09-03

## Context

The implementation needs: an MCP server, a CLI, schema validation, CSV parsing,
plotting, and geometry maths. It must install easily for people who are aerospace
engineers and students, not necessarily developers — and on macOS, Linux and Windows.

## Decision

**Python 3.11+**, with:

| Concern | Choice |
|---|---|
| MCP server | the official Python MCP SDK |
| Schema and validation | Pydantic v2 — the model *is* the JSON Schema the tools advertise |
| CLI | Typer or argparse; no heavy framework |
| Numerics | NumPy only. No SciPy in the core; `trim` uses a hand-written bracketed solver |
| Plotting | Matplotlib, imported lazily so the MCP server starts fast |
| Config | YAML (`design.yaml`), JSON for machine output |
| Tests | pytest, with golden files |

**Distribution:** PyPI, installed with `pipx install flow5ctl` or run with
`uvx flow5ctl`. A single Claude Desktop config line must be enough to get started.

## Rationale

- Pydantic models generate the MCP tool JSON Schemas directly, so the documented
  interface and the validated interface cannot diverge.
- The audience already has Python — XFLR5/flow5 users routinely post-process in it.
- The heavy numerics are inside flow5. Our side is bookkeeping, geometry, and I/O.
- `uvx` means a user can try the MCP server without installing anything permanently.

## Consequences

- Python startup time is on the critical path for every CLI call. Keep imports lazy;
  Matplotlib in particular must not be imported unless `plot` is called.
- Windows path handling and console encoding need explicit testing — flow5's output
  is UTF-8 with Unicode column headers.
- A future in-process API binding ([ADR-0001](0001-drive-flow5-via-the-xml-script-interface.md))
  would mean pybind11 and wheels per platform. Not v1.

## Alternatives considered

- **TypeScript/Node.** Better MCP ecosystem maturity, worse fit for numerics and for
  this audience.
- **Rust.** Excellent single-binary distribution, but slows contribution from the
  aerospace community we want contributing presets and airfoil data.
