# AGENTS.md

Instructions for AI agents working **on** this repository.

> If you are an agent **using** flow5ctl to design an aircraft, this is the wrong
> file. Read [docs/DESIGN-GUIDE.md](docs/DESIGN-GUIDE.md) instead.

## What this project is

`flow5ctl` lets AI agents design low-Reynolds-number aircraft by driving
[flow5](https://flow5.tech), a potential-flow solver, in its headless batch mode.
It ships as an MCP server and a CLI over one shared core.

The core, the CLI and the MCP server all work. See
[the roadmap](docs/ROADMAP.md) for what is left.

## Layout

```
src/flow5ctl/
  model/         design.yaml schema, presets
  geometry/      areas, span, MAC, mass properties       ← no flow5 knowledge
  advisor/       guardrails and thresholds               ← no flow5 knowledge
  viz/           chart rendering and the validated palette
  flow5/         probe, xmlgen, runner, results, summary ← the ONLY flow5-aware package
  usecases/      define, edit, analyze, trim, sweep, plot, gui  ← the only orchestrators
  presets/       *.yaml — data, so a new aircraft class needs no code
  cli.py         a thin adapter over the use cases
  mcp_server.py  the second thin adapter; no domain logic, no flow5 knowledge
poc/             the verification harness that produced the measured claims in docs/
examples/        worked designs and a study, used as documentation
tests/           golden values and real flow5 output; fixtures/ pins the parser traps
```

The dependency rule is one way: `cli / mcp_server → usecases → geometry/advisor/model`,
with `flow5/` reachable only from `usecases/`. Nothing in `geometry/`, `advisor/` or
`model/` may import `flow5/`, so the aerodynamic model stays testable with flow5
absent — and CI relies on that.

The two front-ends must stay in step. A capability added to one and not the other is
an incomplete change ([ADR-0002](docs/adr/0002-one-core-two-frontends.md)).

## Working on it

```bash
uv sync --group dev --extra plot    # the extra is what chart tests need
uv run pytest -q                    # everything, including the real flow5 runs
uv run pytest -q -m "not needs_flow5"   # what CI runs
uv run ruff check src tests tools poc
python3 tools/check_docs.py
```

The MCP server has two test layers, and they check different things:
`tests/test_mcp_server.py` runs it in process for the adapter's own contract, while
`tests/test_mcp_stdio.py` launches `flow5ctl mcp` as a subprocess and talks the
protocol — that is the only place a PNG surviving base64 transport, or a rejected
request coming back as an error result instead of killing the server, is actually
verified.

## Read before you change anything

In this order:

1. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — the layering and why it is that way
2. [docs/adr/](docs/adr/) — decisions already made, with their reasoning
3. [docs/FLOW5-INTERFACE.md](docs/FLOW5-INTERFACE.md) — verified facts about flow5
4. [docs/DOMAIN-MODEL.md](docs/DOMAIN-MODEL.md) — the vocabulary; use these words

## Rules

### Never invent facts about flow5

[docs/FLOW5-INTERFACE.md](docs/FLOW5-INTERFACE.md) marks every claim **[run]**
(verified by executing flow5) or **[src]** (read from a named upstream source file).
Anything not marked either way is not established.

If you need a fact that is not there:

- read it from the upstream source at [techwinder/flow5](https://github.com/techwinder/flow5), or
- verify it by running flow5, then
- add it to the reference with its marker and citation.

Do not guess an XML tag name. Unknown tags are silently ignored by flow5, so a
guess produces a subtly wrong analysis rather than an error.

### Never copy flow5 source code into this repository

flow5 is GPL-3.0; flow5ctl is Apache-2.0. Read the source to learn the interface and
describe it in your own words with a citation. See
[ADR-0006](docs/adr/0006-licensing-and-the-gpl-boundary.md).

### Physics correctness outranks everything

A crash is recoverable. A plausible wrong number that someone builds an aircraft
around is not. Specifically:

- Never let a code path produce stability results from a non-T7 polar. A T1 polar
  will happily return an eigenvalue of `5.995e+51`.
- Never emit `PLANFORM` or `PROJECTED` reference dimensions
  ([ADR-0005](docs/adr/0005-compute-reference-dimensions-ourselves.md)).
- Never report an L/D from an inviscid run without labelling it. Measured: an
  inviscid run omitted 93 % of the drag at α=0°.
- Never mix the two viscous methods inside one comparison; they disagree by 10–25 %.
- Never report Dutch-roll or short-period figures from flow5 7.57 — they are wrong.
- Never present a non-finite cell (`inf`, `nan`) as a result.
- Never treat `Static margin` from a flow5 file as a fraction; it is a percentage.
- Never attribute an operating-point file by its directory — flow5 duplicates those
  files across every polar's directory with the wrong contents.
- Never widen an α sweep past the airfoil's stall to "get more data".

If you are unsure whether something is physically sound, say so in the PR rather than
guessing.

### Check both flow5's exit code and its stdout

`0` means nothing — flow5 exits 0 for a rejected script and for a run that failed
every operating point. Non-zero means it **crashed** (exit 139, SIGSEGV, observed
reproducibly). Success needs the stdout markers in
[docs/FLOW5-INTERFACE.md §6](docs/FLOW5-INTERFACE.md); crash detection needs the exit
code. Use both.

Scope marker matches carefully: `Made 0 valid analysis pairs (boat, polar) to run`
is printed on **every** run, so matching on `analysis pairs` alone reports failure on
every success.

### Never emit both script sections in one file

A script containing both `<foil_analysis>` and `<Plane_analysis>` segfaults flow5.
Two invocations, always — [ADR-0009](docs/adr/0009-two-pass-solver-invocation.md).
The generator must make the single-file form impossible to express.

### Never write a new output parser

flow5's output has at least seven traps that produce plausible wrong numbers rather
than errors ([docs/FLOW5-INTERFACE.md §5](docs/FLOW5-INTERFACE.md)). Extend
[poc/lib/parse.py](poc/lib/parse.py), keep its self-checks — especially validating
the row count against the file's own `Nbr. of data points` — and do not "simplify"
its oddities away. Every one of them is load-bearing
([ADR-0010](docs/adr/0010-treat-solver-output-as-hostile.md)).

### Respect the layering

`front-ends → use cases → domain → flow5 adapter`, one way only. Nothing in
`domain/` may import the adapter; the aerodynamic model must be testable with flow5
absent. Do not add flow5-specific knowledge outside the adapter, and do not add
domain logic to a front-end — see [ADR-0002](docs/adr/0002-one-core-two-frontends.md).

### Keep the two front-ends in step

Every capability appears in both the MCP server and the CLI, and
`flow5ctl <verb> --json` emits exactly the MCP tool payload. A change to one without
the other is incomplete.

### Changing a decision means writing an ADR

The ADRs record *why*. If you conclude one is wrong, add a new ADR that supersedes
it, with the new reasoning. Do not silently contradict an accepted decision in code.

## Conventions

- Use the vocabulary in [docs/DOMAIN-MODEL.md](docs/DOMAIN-MODEL.md). Say *section*,
  *analysis*, *operating point*, *design*. Do not introduce synonyms.
- SI internally, always. Unit conversion happens at the edges only.
- Angles are degrees in `design.yaml` and in every user-facing value, radians inside
  geometry code. Name variables accordingly (`twist_deg`, `alpha_rad`).
- `design.yaml` is the source of truth; XML is a build artifact. Never hand-author
  XML in a fixture unless it is deliberately testing the parser.
- Prose in documentation is English. User-facing Japanese lives in `README.ja.md`
  and `docs/ja/`.

## Testing

- Geometry has golden tests against hand-computed values. Changing geometry code
  means changing them deliberately, never to make a failure go away.
- Solver-facing tests use recorded flow5 output where possible so the suite runs
  without flow5 installed. Tests that need the real binary are marked and skipped
  when it is absent.
- The spike design in [docs/log/2026-09-03-feasibility-spike.md](docs/log/2026-09-03-feasibility-spike.md)
  is the canonical end-to-end fixture.
- [`poc/`](poc/) holds the verification harness that produced every measured claim in
  the docs. If you change something the docs assert, re-run the relevant case and
  update both. `poc/work/` and `poc/ref/` are gitignored — never commit solver output,
  and never commit upstream flow5 source.

## When you finish

- Say what you verified by running versus what you reasoned about.
- If you changed anything in `docs/FLOW5-INTERFACE.md`, state which flow5 version you
  verified against.
- If a task turned out to be blocked, finish everything else and say plainly what you
  left and why.
