# ADR-0003 — A design is a directory, not a session

**Status:** Accepted · 2026-09-03

## Context

Designing an aircraft is a long, iterative, multi-day activity. The state has to
survive a conversation ending, a client restarting, and a switch from one AI client
to another. It also has to be reviewable by a human who does not trust the agent yet.

An MCP server could hold designs in memory keyed by session. Many do.

## Decision

**All state lives on disk in a project directory**, with `design.yaml` as the single
source of truth. The server and CLI are stateless between calls apart from a lock file.

```
my-glider/
├── design.yaml       ← source of truth, hand- and LLM-editable, in git
├── airfoils/         ← .dat files and 2D polar requests
├── studies/          ← named, re-runnable questions
├── build/            ← .gitignore'd; generated XML and raw flow5 output
├── results/          ← normalised JSON, small and diffable
└── .flow5ctl/        ← flow5 version used, hashes, lock
```

Generated XML is a **build artifact**, never authored by hand, never committed.

## Consequences

- **Reproducible.** `design.yaml` plus a pinned flow5 version reproduces every number.
- **Reviewable.** `git diff` answers "what changed?". A human can open the directory,
  or `open_in_flow5` hands them the `.fl5` in the GUI they already know.
- **Portable across clients.** ADR-0002's two front-ends share designs for free.
- **Crash-safe.** Nothing is lost when a client disconnects.
- **Auditable.** For a human-carrying aircraft, an unversioned design that exists
  only inside a chat is not acceptable engineering practice.
- The server needs a workspace root for clients with no filesystem
  (default `~/flow5ctl/`, override `FLOW5CTL_WORKSPACE`) and must refuse to operate
  outside it.
- Concurrent runs against one project must be serialised — a lock file in `.flow5ctl/`.

## Alternatives considered

- **In-memory session state.** Rejected: loses work, invisible to humans, not
  reproducible, cannot be shared between clients.
- **A database.** Rejected: opaque to `git`, opaque to the user, solves a problem we
  do not have.
- **XML as the source of truth.** Rejected: unreadable in a diff, hostile to hand
  editing, and it encodes flow5's warts into the user's own data.
