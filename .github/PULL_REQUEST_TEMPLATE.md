## What and why

<!-- What does this change, and what problem does it solve? Link the issue if there is one. -->

## Evidence

<!-- Required for any claim about flow5's behaviour or about a physical result. -->

- [ ] I verified this by **running** it (say which flow5 version and OS)
- [ ] I verified this by **reading upstream source** (cite the file)
- [ ] Not applicable — this change makes no claim about flow5 or about physics

flow5 version used: <!-- `flow5 --version` output -->
OS: <!-- -->

## Checklist

- [ ] No flow5 source code is copied into this repository
      ([ADR-0006](../docs/adr/0006-licensing-and-the-gpl-boundary.md))
- [ ] No solver output or generated artifacts are committed (`poc/work/`, `build/`)
- [ ] Any new fact in `docs/FLOW5-INTERFACE.md` is marked **[run]** or **[src]** and cited
- [ ] If this changes an accepted decision, a new ADR supersedes the old one
- [ ] If this touches geometry or the result parser, golden tests were updated
      deliberately — and the PR says why the old values were wrong
- [ ] Both front-ends are in step (MCP and CLI), with `--json` matching the MCP payload

## Physics

<!-- Delete if this change cannot affect a number a user might act on. -->

- [ ] I have stated the limits that apply to any result this produces
- [ ] This does not let a stability figure come from a non-T7 polar
- [ ] This does not present a non-finite value as a result
