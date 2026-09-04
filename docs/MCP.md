# Using flow5ctl from Claude Desktop

flow5ctl speaks the Model Context Protocol over stdio, so any MCP client can drive it.
Claude Desktop is the one this was built for: it has no shell and no filesystem, which
is exactly why the MCP server exists ([ADR-0002](adr/0002-one-core-two-frontends.md)).

## Install

You need **flow5 itself** first, from [flow5.tech](https://flow5.tech). flow5ctl runs
it; it does not include it.

Then add one entry to Claude Desktop's config file:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "flow5": {
      "command": "uvx",
      "args": ["--from", "flow5ctl[plot]", "flow5ctl", "mcp"]
    }
  }
}
```

`uvx` (part of [uv](https://docs.astral.sh/uv/)) fetches and runs flow5ctl without
installing anything permanently. The `[plot]` extra pulls in matplotlib, which only
`plot` needs — everything else works without it, and `plot` says so clearly if it is
missing.

That is all it takes — flow5ctl is on
[PyPI](https://pypi.org/project/flow5ctl/) and `uvx` fetches it. To run a checkout
instead, for development or to try an unreleased change, point `--from` at the
directory:

```json
{
  "mcpServers": {
    "flow5": {
      "command": "uvx",
      "args": ["--from", "/path/to/flow5ctl[plot]", "flow5ctl", "mcp"]
    }
  }
}
```

Restart Claude Desktop. Ask it to run `doctor`; it should report your flow5 version.

### If flow5 is somewhere unusual

flow5ctl looks on `PATH` and then in the usual per-platform locations. If it cannot
find flow5, tell it where:

```json
"env": { "FLOW5CTL_FLOW5": "/opt/flow5/flow5" }
```

## Where designs live

Claude Desktop cannot browse your filesystem, so the server owns a workspace —
`~/flow5ctl` by default, or `FLOW5CTL_WORKSPACE` if you set it. Designs are addressed
**by name**; a name containing a path separator or a traversal is rejected rather than
resolved, and the server never reads or writes outside that directory.

Each design is an ordinary directory with a `design.yaml` you can read, edit and put
in git ([ADR-0003](adr/0003-file-based-project-state.md)). Nothing is hidden in a
database, and a design started in Claude Desktop can be continued from the CLI.

## What to ask for

The server ships four prompts, which are the fastest way in:

| Prompt | What it walks through |
|---|---|
| `new-aircraft` | preset → requirements → first planform → first analysis |
| `improve-glide` | diagnose the drag breakdown, propose and test a change |
| `check-stability` | T1 static margin, CG placement, then a T7 polar and its modes |
| `compare-designs` | several designs on identical settings, in one table |

Or just ask. *"Design a 3 m F5J glider for minimum sink, then show me what moving the
CG from 30 % to 40 % MAC does"* is a reasonable opening.

## Reading what comes back

Every tool returns `warnings` and `notes` alongside its numbers, and they are the
part worth reading. They are where the tool tells you which of its own results you
should not trust — that a run was inviscid and therefore understates drag, that the
mass model has no spanwise content so the lateral modes are meaningless, that the
metric you asked to compare does not respond to the parameter you varied.

The server points Claude at `flow5://guide/design` in its instructions. That guide is
short and it is the difference between a number and an answer: this is a
potential-flow solver with no separation model, so it returns confident values past
stall; its absolute drag is optimistic; and comparisons between designs run
identically are far more reliable than any single absolute figure.

**No aircraft that carries a person should be committed to build on a potential-flow
analysis alone.**

## The surface

13 tools: `doctor`, `list_workspace`, `create_design`, `get_design`, `update_design`,
`add_airfoil`, `expand_planform`, `analyze`, `trim`, `sweep`, `plot`, `export`,
`open_in_flow5`. See [MCP-TOOLS.md](MCP-TOOLS.md) for what each one is for.

Six resources: `flow5://status`, `flow5://guide/design`, `flow5://schema/design`,
`flow5://presets/{name}`, `flow5://design/{name}`, `flow5://results/{name}/{polar}`.

`flow5://schema/design` is generated from the actual model, so the fields it
advertises and the fields `create_design` accepts cannot drift apart.

## Charts

`plot` returns a PNG: the drag polar, the lift curve, the pitching moment with the
trim point, the drag breakdown, or the spanwise lift distribution against elliptic.
Pass `theme: "dark"` if you read Claude Desktop in dark mode — both themes are
separately chosen rather than one inverted, and the palette is validated for
colour-vision deficiency in each.

## Handing back to a human

`open_in_flow5` exports the analysis as a `.fl5` project and opens it in the flow5
GUI. It is a small tool that matters out of proportion to its size: it is where a
designer stops trusting a summary and looks at the aircraft themselves, in the
program they already know. It only works when Claude Desktop and flow5 are on the
same machine, which for a stdio server they are.

## Troubleshooting

**"flow5 was not found."** Install flow5, or set `FLOW5CTL_FLOW5` in the `env` block.

**"flow5 7.xx has not been verified."** flow5ctl is verified against flow5 7.57. A
different version will probably work, and every result carries the warning until
someone confirms it. Please
[report what you find](https://github.com/97kuek/flow5ctl/issues).

**"charts need matplotlib."** Use `--from "flow5ctl[plot]"` as shown above.

**The server does not appear.** Claude Desktop logs MCP server output; check that
`uvx` is on the PATH Claude Desktop sees. `uvx --from flow5ctl flow5ctl doctor` in a
terminal proves the package side works.
