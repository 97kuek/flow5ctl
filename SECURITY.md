# Security policy

## Scope

`flow5ctl` runs a local solver, reads and writes files in a workspace, and can be
driven by an AI agent over MCP. The security-relevant surface is therefore:

- **Path handling.** The MCP server must never read or write outside its workspace.
  A path-escape is a vulnerability, not a bug.
- **Subprocess invocation.** Arguments passed to the flow5 binary, and the contents
  of generated XML, come partly from model output.
- **Untrusted input files.** Airfoil `.dat` files, `design.yaml`, and `.fl5` projects
  may come from anywhere.
- **Agent-supplied instructions.** Content inside a design file or an airfoil comment
  is data, never instructions.

Out of scope: vulnerabilities in flow5 itself (report those
[upstream](https://github.com/techwinder/flow5)), and the consequences of an
aerodynamically wrong result, which is a correctness issue — open a normal issue
labelled `physics`.

## Reporting a vulnerability

Please use GitHub's **private vulnerability reporting** on this repository
(Security → Report a vulnerability). If that is unavailable, open an issue saying
only that you have a security report and asking for a contact — do not include
details in a public issue.

Include what you can: affected version, a reproduction, and the impact you see.

We aim to acknowledge within a week. This is a small volunteer project, so please
allow reasonable time before public disclosure; we will credit you unless you prefer
otherwise.

## Supported versions

Pre-1.0. Only the latest commit on `main` is supported.

## Solver versions

flow5ctl depends on undocumented behaviour of the flow5 binary and pins a verified
version range — see
[ADR-0007](docs/adr/0007-flow5-version-compatibility.md). Running an unverified flow5
is a correctness risk, not a security one, and flow5ctl warns rather than refuses.
