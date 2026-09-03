# ADR-0001 — Drive flow5 via its XML script interface

**Status:** Accepted · 2026-09-03

## Context

flow5 offers three ways in:

1. **XML script batch mode** — `flow5 -s script.xml`, headless, verified working.
2. **The C++ API** — `flow5-lib` / `flow5-io-lib`, with eight examples in the
   upstream repository. The shared libraries already ship inside the macOS app bundle.
3. **GUI automation** — driving the Qt interface. Not seriously considered.

Option 2 is more powerful: in-process optimisation loops with no serialisation, no
subprocess, direct access to meshes and results.

## Decision

**Use the XML script interface (option 1) for v1.** Isolate every flow5 assumption
in an adapter module so that option 2 remains reachable later.

## Rationale

- **It is proven.** A full plane analysis was run end to end on 2026-09-03; see
  [the spike log](../log/2026-09-03-feasibility-spike.md).
- **Speed is a non-issue.** 0.5 s wall clock for an 11-point VLM2 sweep, including
  process start. The performance argument for the API does not bite at this scale.
- **The API is explicitly unstable.** Upstream states it is "in an experimental state
  and subject to change", with stabilisation targeted for end of 2026. Building v1 on
  it means rewriting v1.
- **No build toolchain.** Option 2 requires compiling against Qt, OpenCASCADE and
  gmsh on three platforms. Option 1 requires Python and an installed flow5, which
  users already have.
- **Licensing.** Invoking a binary keeps us outside GPL-3.0 derivation; linking the
  library does not. See [ADR-0006](0006-licensing-and-the-gpl-boundary.md).
- **Portability.** The same script XML works on every platform flow5 ships for.

## Consequences

- We accept the script format's warts and document them
  ([FLOW5-INTERFACE.md](../FLOW5-INTERFACE.md)): flat range elements, silent skipping
  of unknown tags, an exit code that is always 0, and reference dimensions that must
  be computed by us.
- Optimisation loops pay a process launch per evaluation. At 0.5 s this is
  acceptable for hundreds of evaluations, not tens of thousands.
- The script format may change between flow5 versions.
  See [ADR-0007](0007-flow5-version-compatibility.md).

## Revisit when

The upstream API is declared stable (targeted end of 2026), **and** a real workload
appears where process launch dominates — a gradient-based or population optimiser
running thousands of evaluations. Then add an API-backed runner behind the same
adapter interface and choose at runtime.
