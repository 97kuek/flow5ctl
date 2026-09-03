# Contributing

flow5ctl exists so that everyone using flow5 can design with AI assistance — not
just people who write code. Contributions from designers, pilots and teams who have
actually built aircraft are as valuable as pull requests, and often more so.

## The project is in the design phase

There is no source code yet. Right now the most useful contributions are:

- **Review the design.** Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and the
  [ADRs](docs/adr/). If a decision is wrong, open an issue and say why. It is far
  cheaper to change now.
- **Tell us what you actually do.** How do you use flow5 or XFLR5 today? What is the
  loop you repeat twenty times? What do you always get wrong? That is the tool.
- **Contribute domain knowledge.** Reynolds ranges, static margin conventions,
  airfoil choices, panel counts that converge, sanity thresholds for your class of
  aircraft. See [docs/DESIGN-GUIDE.md](docs/DESIGN-GUIDE.md) — corrections welcome
  and wanted.
- **Verify flow5 on your platform.** Everything in
  [docs/FLOW5-INTERFACE.md](docs/FLOW5-INTERFACE.md) was verified on macOS with
  flow5 7.70. Linux and Windows are unverified. §8 lists what nobody has checked yet.

## Ground rules

### Do not copy flow5 source code into this repository

flow5 is GPL-3.0; flow5ctl is Apache-2.0. We read flow5's source to learn its file
formats and describe them in our own words, with citations. Never paste flow5 code,
comments or documentation text into a file here. See
[ADR-0006](docs/adr/0006-licensing-and-the-gpl-boundary.md).

### Every claim about flow5 needs evidence

[docs/FLOW5-INTERFACE.md](docs/FLOW5-INTERFACE.md) marks each fact **[run]** or
**[src]**. If you add one, mark it, cite the source file or paste the command output,
and say which flow5 version you used. Unmarked claims will be asked for evidence.

### Physics errors are the serious bugs

People build aircraft from this, and some of those aircraft carry a pilot a few
metres above water. A plausible wrong number is worse than a crash. If you find one,
it goes to the top of the queue — label the issue `physics` and say what the correct
result should be and how you know.

### Contributions must not require the reader to trust an agent

Every result must be traceable to a design file, a flow5 version and an analysis
setup. That is why designs live in git ([ADR-0003](docs/adr/0003-file-based-project-state.md)).

## What we would especially like

| | |
|---|---|
| **Presets** | `presets/*.yaml` for your class — F3B, F3F, F5J, DLG, HPA distance, HPA rally. Data, not code. Include the thresholds you use and why. |
| **Airfoil data** | Low-Re airfoils with **checked provenance and licensing**. Say where the coordinates came from and under what terms. |
| **Validation cases** | An aircraft you have flown, with the flow5 setup and what the real thing actually did. Nothing improves this tool more. |
| **Platform reports** | flow5 version, OS, what worked, what did not. |
| **Translation** | The Birdman Rally community is largely Japanese-speaking. `docs/ja/` and `README.ja.md`. |

## Once code exists

- Python 3.11+, Pydantic v2, pytest ([ADR-0008](docs/adr/0008-python-and-distribution.md)).
- Respect the layering: `front-ends → use cases → domain → flow5 adapter`, one way.
  Nothing in `domain/` may import the adapter.
- Every capability lands in **both** front-ends, with `--json` output identical to
  the MCP payload.
- Geometry changes need golden tests. Never edit a golden file to make a test pass
  without saying, in the PR, why the old value was wrong.
- Tests that need flow5 installed are marked and skipped when it is absent; the rest
  of the suite must run without it.

## Commits

We use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):

```
<type>(<optional scope>): <summary in the imperative, no trailing period>

<optional body: why, not what>
<optional footer: Refs #123 / Closes #123>
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `perf`, `build`, `ci`, `chore`.
Scopes we use: `geometry`, `xmlgen`, `runner`, `results`, `mcp`, `cli`, `presets`,
`poc`, `docs`.

```
feat(runner): run flow5 in two passes to avoid the 2D+3D segfault
fix(results): recover the operating point welded onto the header line
docs(adr): record why reference dimensions are computed locally
```

Keep the summary under ~72 characters. One logical change per commit — a commit that
touches the parser and the roadmap for unrelated reasons should be two.

**Commits and the contributor list name people, not tools.** Do not add
`Co-Authored-By` or `Generated-with` trailers for AI assistants, editors, or
generators, and do not credit them in `CHANGELOG.md`. If you used a tool to help
write a change, you are still the author and the one vouching for it — which matters
here, because these numbers end up in aircraft. Human co-authors do belong in
`Co-Authored-By`.

## Changing a decision

The [ADRs](docs/adr/) record why things are the way they are. If one is wrong, that
is worth knowing — open an issue, and if it is agreed, add a **new** ADR that
supersedes the old one and explains the change. Do not quietly contradict an
accepted decision in code.

## Reporting a problem

Include:

- flow5 version (`flow5 --version`) and OS
- your `design.yaml`, or the smallest version that reproduces it
- what you expected and what you got
- for a physics issue: why you believe the result is wrong

## Relationship to flow5

flow5 is a separate project by André Deperrois. flow5ctl is independent and not
affiliated with or endorsed by it. Bugs in flow5 itself belong
[upstream](https://github.com/techwinder/flow5) — but please tell us too, so we can
record it in the compatibility matrix
([ADR-0007](docs/adr/0007-flow5-version-compatibility.md)).

## Conduct

Be decent. Many contributors here are students on university teams, working in a
second language, on an aircraft they will fly themselves. Assume good faith and
explain your reasoning.
