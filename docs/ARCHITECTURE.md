# Architecture

## The shape of the problem

Driving flow5 is easy. `flow5 -s script.xml` is one subprocess call and it returns in
half a second. If that were the whole job, no tool would be needed — Claude Code and
Codex already have a shell.

The actual work is everything around it:

1. **Authoring.** The plane and polar XML schemas are large, and several of their
   rules are lethal-if-wrong rather than merely wrong: a mistyped element is silently
   ignored, an unrecognised analysis method silently becomes VLM2, and `PLANFORM`
   reference dimensions silently produce zeros that kill the run
   ([FLOW5-INTERFACE.md §4](FLOW5-INTERFACE.md)).
2. **Geometry.** Reference area, span and MAC must be derived from the planform
   before flow5 sees it. So must the mass properties, if the user gave component masses.
3. **Interpretation.** flow5 answers with a wide CSV. A designer's question was
   "is this stable?" or "what does the CG do to sink rate?".
4. **Judgement.** An agent will happily ask for a T1 polar with `Compute_derivatives`
   and report the resulting `5.995e+51` eigenvalue as a finding. The tool has to make
   the wrong thing hard.

So `flow5ctl` is a **domain layer**, and the solver invocation is its smallest part.

## Layers

```
┌──────────────────────────────────────────────────────────────┐
│  Front-ends                                                  │
│  ┌────────────────────┐        ┌──────────────────────────┐  │
│  │ MCP server         │        │ CLI                      │  │
│  │ flow5ctl mcp       │        │ flow5ctl init/design/... │  │
│  │ → Claude Desktop   │        │ → Claude Code, Codex, CI │  │
│  └────────────────────┘        └──────────────────────────┘  │
│         both are thin adapters over the same use cases       │
├──────────────────────────────────────────────────────────────┤
│  Use cases            define · analyse · trim · sweep        │
│                       — the only layer that orchestrates     │
├──────────────────────────────────────────────────────────────┤
│  Domain                                                      │
│  model/      design.yaml schema, validation, presets         │
│  geometry/   area, span, MAC, AR, mass properties, CG        │
│  advisor/    guardrails: which polar type answers which      │
│              question; sanity thresholds; warnings           │
├──────────────────────────────────────────────────────────────┤
│  flow5 adapter  (the only code that knows flow5 exists)      │
│  xmlgen/     design → xflplane / xflPlanePolar / xflscript   │
│  runner/     subprocess, timeout, stdout state machine       │
│  results/    CSV → typed records; log → diagnosis            │
│  probe/      locate the binary, detect version, compat check │
├──────────────────────────────────────────────────────────────┤
│  Project store   a directory on disk, git-friendly           │
└──────────────────────────────────────────────────────────────┘
```

The dependency rule is one-way: front-ends → use cases → domain → adapter.
Nothing in `domain/` imports the adapter, so the aerodynamic model is testable
without flow5 installed.

## Source and artifact

The central decision ([ADR-0003](adr/0003-file-based-project-state.md)) is that a
design is **a directory, not a session**.

```
my-glider/
├── design.yaml              ← SOURCE OF TRUTH. Hand-editable, LLM-editable, in git.
├── airfoils/
│   ├── ag35.dat
│   └── ag35.polars.yaml     ← 2D polar requests, so they can be recomputed
├── studies/
│   └── cg-sweep.yaml        ← a named question, re-runnable
├── build/                   ← .gitignore'd. Everything here is regenerable.
│   ├── plane.xml
│   ├── polars/*.xml
│   ├── script.xml
│   └── out/…                ← flow5's raw output, kept for inspection
├── results/
│   └── cg-sweep.json        ← normalised, diffable, small
└── .flow5ctl/
    └── state.json           ← flow5 version used, hashes, timestamps
```

Consequences that make this the right call:

- **Reproducible.** `design.yaml` + a pinned flow5 version reproduces every number.
- **Reviewable.** A human opens the directory, or `flow5ctl open` hands the `.fl5`
  to the flow5 GUI and they look at it the way they always have.
- **Diffable.** "What changed between yesterday's design and today's?" is `git diff`.
- **Front-end agnostic.** Claude Desktop and Claude Code operate on the same
  directory; a design started in one continues in the other.
- **Crash-safe.** The MCP server holds no state worth losing.

XML is a *build artifact*, like object files. Users should never see it unless they
ask. Agents should never author it directly.

## Data flow for one analysis

```
design.yaml
    │  model.load + validate                        → schema errors, early
    ▼
Design (typed)
    │  geometry.solve                               → area, span, MAC, CG, AR, Re
    ▼
Design + DerivedGeometry
    │  advisor.check(question, design)              → "use T7 for stability", warnings
    ▼
AnalysisRequest
    │  xmlgen  (PASS 1: foil script — 2D polars, cached)
    │  runner.run → stage .txt polars into xfoil_polars_dir
    │  xmlgen  (PASS 2: plane script)               → build/plane.xml, polar.xml, script.xml
    ▼
    │  runner.run(flow5 -s …, timeout)              → stdout stream + exit code
    ▼
RunLog
    │  results.diagnose(stdout)                     → success? which failure mode?
    │  results.parse(out/**.csv)                    → typed OperatingPoint records
    ▼
AnalysisResult
    │  advisor.summarise                            → CL_α, (L/D)_max & its α, Cm_α,
    ▼                                                  static margin, X_NP, warnings
Summary  →  agent          |  full records → results/*.json → agent reads if needed
```

The agent receives the **Summary**. It never receives the CSV
([ADR-0004](adr/0004-summarise-results-not-raw-data.md)).

## Why one core with two front-ends

Claude Desktop cannot run shell commands, so an MCP server is required to reach it —
and reaching every flow5 user, not just the ones in a terminal, is the point of this
project.

But an MCP tool call is a poor fit for CI, for scripted parameter studies, and for
agents that already have a shell and would rather pipe. Those want a CLI.

Duplicating the domain logic across two front-ends would guarantee they drift.
So both are adapters ~200 lines deep over a shared use-case layer
([ADR-0002](adr/0002-one-core-two-frontends.md)). Every capability appears in both,
automatically.

## Failure handling

flow5's exit code is not a success signal ([FLOW5-INTERFACE.md §1](FLOW5-INTERFACE.md)),
so the runner implements a small state machine over stdout markers, combines it with
the exit code, and classifies failures into causes the agent can act on:

| Detected | Reported to the agent as |
|---|---|
| exit 139 / signal 11, no stdout | internal error — flow5 crashed; almost certainly both script sections in one file ([ADR-0009](adr/0009-two-pass-solver-invocation.md)). Our bug, please report |
| `Error reading script...aborting` | internal error — flow5ctl generated invalid XML; our bug, please report |
| `foils not found ...discarding this plane` | airfoil `X` is referenced but not loaded; add it with `add_airfoil` |
| `Made 0 valid analysis pairs (plane, polar)` | plane name / polar `Plane_Name` mismatch — internal error |
| `reference … is 0m` | internal error — reference dimensions were not computed |
| `Viscous interpolation failures` | the 2D polar mesh does not cover the local Re; flow5ctl widens it and retries once, then reports the range needed |
| `OTF failures:` | on-the-fly XFoil did not converge at a strip; switch to the interpolated method |
| `Error generating the operating point... discarding` | that point failed; reported per point, with how many survived |
| row count ≠ header's `Nbr. of data points` | internal error — parse dropped points ([ADR-0010](adr/0010-treat-solver-output-as-hostile.md)) |
| timeout | mesh too large for the time budget; reduce panel count or α points |

Note that flow5's exit code is `0` for a rejected script and for a run that failed
every point, so it can never be the success test — but a **non-zero** code means a
crash and must be surfaced. Both are checked.

Distinguishing *our* bugs from *user* problems in the message is deliberate: an agent
told "this is a flow5ctl bug" stops trying to fix the design and reports it instead.

## Two passes, always

flow5 **segfaults** if one script contains both a `<foil_analysis>` and a
`<Plane_analysis>` section — reproducibly, with no output at all
([FLOW5-INTERFACE.md §7](FLOW5-INTERFACE.md)). So every analysis is two invocations:
2D polars first, staged as `.txt` into `xfoil_polars_dir`, then the 3D run.
[ADR-0009](adr/0009-two-pass-solver-invocation.md) covers the consequences, the most
useful of which is that 2D polar meshes are naturally cached — they cost ~15 s and
the 3D run that consumes them costs under 2 s.

The `xmlgen` layer must make emitting both sections *impossible*, not merely
discouraged.

## Concurrency

flow5 runs its own multithreaded analysis. flow5ctl serialises subprocess launches
per project directory (a lock file in `.flow5ctl/`) because they share `build/` and
`out/`. Parameter sweeps run sequentially by default; parallelism across separate
build directories is a Phase 4 optimisation, not a v1 requirement — a 34 m
high-aspect-ratio aircraft takes 0.5 s per viscous polar
([FLOW5-INTERFACE.md §10](FLOW5-INTERFACE.md)), so patience is cheap.

## Platform support

macOS is the verified platform. Linux and Windows are Phase 1 targets and are
explicitly listed as unverified in [FLOW5-INTERFACE.md §8](FLOW5-INTERFACE.md).
The `probe/` module isolates every platform assumption: binary discovery, path
conventions, and whether a display connection is required.
