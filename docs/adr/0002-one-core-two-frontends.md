# ADR-0002 — One core, two front-ends

**Status:** Accepted · 2026-09-03

## Context

The goal is that *every* flow5 user can design with AI assistance. Those users reach
for different clients:

- **Claude Desktop** and other MCP clients — no shell, no filesystem. MCP is the only way in.
- **Claude Code, Codex** — already have a shell and files. An MCP server that only
  shells out adds a layer without adding capability, and costs tool-definition context.
- **CI, scripts, humans** — want a CLI and exit codes.

## Decision

Build **one Python package** containing the domain logic and the flow5 adapter, with
**two thin front-ends** over a shared use-case layer:

- `flow5ctl mcp` — MCP server on stdio
- `flow5ctl <verb>` — CLI

Neither front-end contains domain logic. Each is an adapter: parse input, call a use
case, format output. Target under ~200 lines each.

Every CLI command accepts `--json` and emits **exactly** the payload the
corresponding MCP tool returns.

## Consequences

- No capability can exist in one front-end and not the other, and they cannot drift.
- Agents with a shell get the same structured data as MCP clients, so documentation
  and examples are shared.
- A design started in Claude Desktop can be continued in Claude Code and vice versa,
  because both operate on the same project directory
  ([ADR-0003](0003-file-based-project-state.md)).
- Two packaging targets to test. Accepted.
- The MCP server must not assume a display, a terminal, or a working directory.

## Alternatives considered

- **MCP only.** Rejected: worse than a shell command for Claude Code and Codex, which
  are a large share of the audience.
- **CLI only.** Rejected: excludes Claude Desktop, which is the largest group of
  potential users and the reason this project is general rather than personal.
- **Two separate projects.** Rejected: guarantees drift, doubles maintenance.
