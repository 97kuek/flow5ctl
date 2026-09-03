# Tool surface

The same capabilities are exposed twice: as MCP tools (for Claude Desktop and other
MCP clients) and as CLI verbs (for Claude Code, Codex, humans, CI). This document
specifies them once.

## Principles

1. **Few tools, each a design action.** Not a CRUD API over XML. An agent should be
   able to hold the whole surface in mind.
2. **Every response is a summary plus a pointer.** Full data goes to a file; the
   response says where. See [ADR-0004](adr/0004-summarise-results-not-raw-data.md).
3. **Responses carry warnings.** Applied defaults, violated thresholds, and
   physically suspect results are named in the response, not buried in a log.
4. **The wrong thing is hard.** Asking for stability from a T1 polar is refused with
   the correct alternative, not silently obeyed.
5. **Prerequisites resolve themselves.** A viscous analysis with no 2D airfoil
   polars computes them and says so, rather than failing with a solver error.

## Where designs live

Claude Desktop has no filesystem access, so the server owns a workspace:

- default `~/flow5ctl/` — override with `FLOW5CTL_WORKSPACE`
- each design is a subdirectory (see [ARCHITECTURE.md](ARCHITECTURE.md))
- tools address designs by **name**, never by path
- the server refuses to read or write outside the workspace

For the CLI, the current working directory is the design if it contains
`design.yaml`; otherwise `--design <name>` resolves in the workspace.

---

## Tools

### `doctor`
Verify the environment. No arguments.

Returns: flow5 executable path, version, whether it is a **verified** version,
workspace path, writability, and the results of a 2-second self-test analysis.
Every other tool fails cheaply and clearly if `doctor` would fail.

> Agents should call this once at the start of a session. The MCP server also
> exposes the same content as the `flow5://status` resource so a client can read it
> without a tool call.

### `list_designs`
Returns each design's name, one-line description, preset, span, mass, and when it
was last analysed.

### `create_design`
`name`, `preset`, and either a `design` object or `from` (an existing design to copy).

Creates the project directory, writes `design.yaml`, computes geometry.
Returns the same payload as `get_design`.

### `get_design`
`name`. Returns the design, **all derived geometry**
([DOMAIN-MODEL.md](DOMAIN-MODEL.md#derived-geometry)), applied preset defaults, and
validation warnings.

```jsonc
{
  "name": "Albatross-2026",
  "preset": "hpa",
  "geometry": {
    "planform_area": 27.03, "projected_area": 27.01,
    "span": 34.0, "projected_span": 33.98,
    "mac": 0.826, "mac_y": 7.31, "aspect_ratio": 42.8, "taper_ratio": 0.45,
    "total_mass": 95.0, "cg": [0.351, 0.0, -0.221],
    "wing_loading": 3.51,
    "reynolds_at_mac": 4.4e5,
    "tail_volume_h": 0.52, "tail_volume_v": 0.021
  },
  "defaults_applied": [
    "wing.panels.span_distribution = COSINE (preset: hpa)",
    "atmosphere.density = 1.225 (standard sea level)"
  ],
  "warnings": [
    "Aspect ratio 42.8 is high even for an HPA; check that the structural mass budget is realistic.",
    "Vertical tail volume 0.021 is below the 0.03 typically used at this span."
  ]
}
```

### `update_design`
`name` plus a **partial** design object, deep-merged. Returns the new `get_design`
payload and a diff summary of what changed.

Partial updates matter: an agent adjusting washout should not have to restate the
whole aircraft, and a restated aircraft is a chance to lose a field.

### `add_airfoil`
`design`, `name`, `source` (`file:` / `naca:NNNN` / `url:` / inline coordinates),
optional `polars` specification.

Validates the coordinates (closed trailing edge, ordering, point count), stores the
`.dat`, and registers it. Does **not** compute polars — `analyze` does that on demand.

### `analyze`
The main tool.

```jsonc
{
  "design": "Albatross-2026",
  "type": "T1",                    // T1|T2|T3|T4|T5|T6|T7 — plain flow5 names
  "speed": 8.0,
  "alpha": [-2, 10, 0.5],
  "viscous": true,                 // default true
  "ground_effect": true,           // preset default for hpa
  "method": "VLM2",
  "cg_x": 0.351,                   // overrides the design CG for this run
  "mass": 95.0,
  "name": "cruise"                 // for later reference
}
```

Returns a summary, never the table:

```jsonc
{
  "status": "ok",
  "polar": "cruise",
  "points": 25,
  "runtime_s": 3.2,
  "summary": {
    "cl_alpha_per_deg": 0.0912,
    "alpha_zero_lift": -3.4,
    "best_LD": {"value": 38.2, "alpha": 3.5, "cl": 0.82, "cd": 0.0215},
    "min_sink": {"rate": 0.41, "alpha": 5.0, "speed": 7.4},
    "cm_alpha_per_deg": -0.0121,
    "neutral_point_x": 0.462,
    "static_margin": 0.134,
    "trim_alpha": 3.1
  },
  "warnings": [
    "Static margin 0.134 is inside the target band [0.05, 0.15].",
    "2D polars for DAE-31 were computed automatically (Re 3e5–1e6, 4 points, 11 s)."
  ],
  "data": "results/cruise.json",
  "flow5_project": "build/out/Albatross-2026.fl5"
}
```

Guardrails enforced here:
- `type: "T1"` with a stability question → refused, pointing at `T7`
- `viscous: true` with no 2D polars → computes them, reports the cost
- panel count above the preset ceiling → refused with the count and a suggestion
- estimated runtime above the budget → asks for confirmation instead of hanging

### `trim`
Solve rather than sweep. `design`, plus a target:

- `target: "level_flight"` with `speed` → finds α and required elevator incidence
- `target: "static_margin"`, `value: 0.10` → finds the CG that achieves it
- `target: "cl"`, `value: 0.9` → finds α

Returns the solved quantity, the operating point at that condition, and the
iterations used. This is the question designers actually ask, and doing it inside
the tool avoids an agent burning ten tool calls on a bisection.

### `sweep`
Runs a [study](DOMAIN-MODEL.md#studies): `design`, `parameter` (dotted path into
`design.yaml`), `values`, `analysis`, `metrics`.

Returns a comparison table — one row per value, one column per metric — plus the
best row by the design's `objective`, plus the path to full results. A CG sweep, a
taper study, and a washout study are all this one tool.

### `plot`
`design`, `polar` (one or more), `kind` (`polar` | `cl_alpha` | `cm_alpha` |
`drag_breakdown` | `spanwise_lift`).

Returns a **PNG as MCP image content**. This exists for Claude Desktop, where the
user cannot open a file and where a curve communicates in one glance what twenty
numbers do not. The CLI writes the file instead.

### `export`
`design`, `format` (`fl5` | `stl` | `csv` | `xml`), optional `polar`.
Returns the path, and for `fl5` a reminder that `open_in_flow5` exists.

### `open_in_flow5`
Launches the flow5 GUI on the design's `.fl5` project. Available only to the CLI and
to MCP clients running on the user's own machine.

**This tool is important out of proportion to its size.** It is the handoff back to
the human — the point where a designer stops trusting the agent's summary and looks
at the aircraft with their own eyes, in the tool they already know. A design tool
that cannot be checked will not be adopted.

---

## Resources (MCP)

| URI | Content |
|---|---|
| `flow5://status` | Same as `doctor`, readable without a tool call |
| `flow5://presets/{name}` | Preset defaults and thresholds |
| `flow5://design/{name}` | The current `design.yaml` |
| `flow5://results/{design}/{polar}` | Full operating-point data |
| `flow5://guide/design` | [DESIGN-GUIDE.md](DESIGN-GUIDE.md) — the aerodynamic guardrails |
| `flow5://airfoils` | Catalogue of bundled low-Re airfoils |

`flow5://guide/design` is deliberately a resource: a client that reads it before
designing makes far fewer physically wrong requests, and it can be updated without
shipping a new server.

## Prompts (MCP)

| Prompt | Walks the user through |
|---|---|
| `new-aircraft` | Preset → requirements → first planform → first analysis |
| `improve-glide` | Diagnose the drag breakdown, propose and test changes |
| `check-stability` | T7 polar, modes, CG band, control authority |
| `compare-designs` | Two or more designs on the same metrics |

## CLI mapping

```
flow5ctl doctor
flow5ctl init <name> --preset hpa
flow5ctl list
flow5ctl show [<name>]
flow5ctl set wing.planform.washout=-2.5      # → update_design
flow5ctl airfoil add DAE-31 --file dae31.dat
flow5ctl analyze --type T1 --speed 8 --alpha -2,10,0.5 --name cruise
flow5ctl trim --target static-margin --value 0.10
flow5ctl sweep studies/cg-sweep.yaml
flow5ctl plot cruise --kind polar -o cruise.png
flow5ctl export --format stl
flow5ctl open
flow5ctl mcp                                  # run the MCP server on stdio
```

Every CLI command takes `--json` for machine-readable output identical to the MCP
response, so an agent with a shell gets exactly what an MCP client gets.
