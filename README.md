# flow5ctl

**AI-driven aircraft design with [flow5](https://flow5.tech).**

`flow5ctl` lets an AI agent — Claude Desktop, Claude Code, Codex, or any MCP client —
design and analyse low-Reynolds-number aircraft by driving flow5's headless batch engine.

It ships as one Python package with two front-ends:

| Front-end | Command | For |
|---|---|---|
| **MCP server** | `flow5ctl mcp` | Claude Desktop, and any MCP-capable client |
| **CLI** | `flow5ctl <verb>` | Claude Code, Codex, humans, CI |

> **Status: design phase — verified, not yet implemented.**
> There is no library code yet. What exists is a design record and a **reproducible
> proof that the approach works**: eleven verification cases run against
> **flow5 7.57** on macOS, covering 2D polar generation, viscous analysis, five
> polar types, ground effect, fuselages, 34 m HPA meshes and stability polars.
> Read [the verification log](docs/log/2026-09-03-poc-verification.md) for what was
> found — including a reproducible flow5 crash and seven ways its output misleads a
> naive reader. Re-run any of it from [`poc/`](poc). Implementation follows the
> [roadmap](docs/ROADMAP.md).

日本語版 README: [README.ja.md](README.ja.md)

---

## Why

flow5 is an excellent potential-flow solver, but designing an aircraft with it is a
long loop of manual GUI work: draw a planform, pick airfoils, set up a polar, run,
read graphs, adjust, repeat. That loop is exactly what an AI agent is good at —
*if* it can drive the solver reliably.

It can. flow5 has a headless batch mode (`flow5 -s script.xml`) that runs a full
plane analysis in well under a second. What it lacks is a surface an agent can
actually use: the XML schemas are large, some required fields are silently fatal if
omitted, and the results come back as wide Unicode-headed CSVs.

`flow5ctl` is that missing surface. It is **not** a thin wrapper around the flow5
binary — that would add nothing over a shell command. It is a domain layer that:

- accepts a **high-level design description** (span, taper, airfoil, mass, CG) instead of raw XML
- computes the geometry flow5 needs but does not derive in batch mode (reference area, span, MAC)
- generates and validates every XML artifact
- runs the solver, diagnoses failures in plain language
- returns **summaries an agent can reason about** (CL slope, best L/D and where, Cm_α, static margin, neutral point) rather than raw data dumps
- keeps the whole design in a **git-friendly project directory** so humans can inspect, diff and review it

How much of that is real work rather than plumbing: flow5 **segfaults** if one script
asks for both 2D and 3D work, its polar `.csv` files contain no commas, the first row
of data is welded onto the header line, `Static margin` is a percentage that looks
like a fraction, operating-point files are duplicated into every polar's directory
carrying *another* polar's contents, and a stability request on the wrong polar type
returns eigenvalues of `5.995e+51` with a straight face. Each of those is verified,
documented, and handled.

## Who it is for

`flow5ctl` targets the whole low-Re community that already uses flow5 / XFLR5:

- **Human-powered aircraft** (鳥人間コンテスト, Daedalus-class): 30 m+ span, AR ≈ 30, Re ≈ 5×10⁵–1×10⁶, ground effect, spanwise loading, structural mass budget
- **RC gliders** (F3B / F3F / F5J, DLG): 1.5–4 m span, Re ≈ 5×10⁴–3×10⁵, camber-changing flaps, ballast, wide speed range
- **Small UAVs and model aircraft** in the same regime

Presets encode the defaults each of these needs; the underlying model is general.

## Quickstart (planned)

```bash
pipx install flow5ctl
flow5ctl doctor                 # verify the flow5 installation
flow5ctl init my-glider --preset rc-glider
```

Claude Desktop — add to your MCP config:

```json
{
  "mcpServers": {
    "flow5": { "command": "flow5ctl", "args": ["mcp"] }
  }
}
```

Then ask: *"Design a 3 m F5J glider for minimum sink, and show me the effect of
moving the CG from 30% to 40% MAC."*

## How it works

```
                design.yaml  ← source of truth, human- and LLM-readable, in git
                     │
        flow5ctl     │  geometry solve → XML generation → validation
                     ▼
            plane.xml + polar.xml + script.xml   ← build artifacts, disposable
                     │
                     ▼
            flow5 -s script.xml                  ← headless, ~0.5 s per sweep
                     │
                     ▼
            polars.csv + oppoints/ + project.fl5
                     │
        flow5ctl     │  parse → normalise → summarise
                     ▼
            structured result + warnings  → agent
                                          → `flow5ctl open` hands the .fl5 to the GUI for a human
```

The YAML is the source; the XML is a build artifact. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Documentation

| Document | What it covers |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layers, data flow, why one core with two front-ends |
| [docs/DOMAIN-MODEL.md](docs/DOMAIN-MODEL.md) | Vocabulary and the `design.yaml` schema |
| [docs/MCP-TOOLS.md](docs/MCP-TOOLS.md) | The tool surface exposed to agents |
| [docs/FLOW5-INTERFACE.md](docs/FLOW5-INTERFACE.md) | Verified reference for flow5's batch/XML interface |
| [docs/DESIGN-GUIDE.md](docs/DESIGN-GUIDE.md) | Aerodynamic guardrails agents must respect |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Phases and milestones |
| [docs/adr/](docs/adr/) | Architecture decision records |
| [docs/log/](docs/log/) | Investigation and verification log |
| [poc/](poc/) | The verification harness — reproduce every measured claim |

Contributing: [CONTRIBUTING.md](CONTRIBUTING.md) · Working with AI agents in this repo: [AGENTS.md](AGENTS.md)

## Known limitations

- **Flaps and control surfaces are not supported, and cannot be.** flow5 has no flap
  or hinge elements in its plane XML — a flap belongs to flow5's Foil object, which a
  `.dat` file cannot carry, and planes loaded from a GUI-made project cannot be paired
  with new analyses. So T6 control polars are out of reach through this interface.
  This matters if you fly camber-changing RC gliders; see
  [the verification log](docs/log/2026-09-03-poc-verification.md), findings 9 and 10.
- **Verified on macOS only.** Linux and Windows are expected to work and are
  untested — reports very welcome.
- **flow5's own defects are inherited.** Dutch-roll and short-period frequencies are
  unreliable in 7.57 and are deliberately not reported.

## Relationship to flow5

flow5 is a separate project by André Deperrois, released under GPL-3.0 at
[techwinder/flow5](https://github.com/techwinder/flow5). `flow5ctl` is an
independent tool that invokes the flow5 executable as a subprocess. It does not
link flow5 code and does not redistribute it — you install flow5 yourself.
See [ADR-0006](docs/adr/0006-licensing-and-the-gpl-boundary.md).

`flow5ctl` is not affiliated with or endorsed by the flow5 project.

## License

Apache-2.0 (proposed — see [ADR-0006](docs/adr/0006-licensing-and-the-gpl-boundary.md)).
