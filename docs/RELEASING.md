# Releasing

A release is a decision, not a side effect of merging, so nothing publishes on a
push to `main`. Pushing a tag that starts with `v` is what publishes.

## One-time setup

Both steps are done by the repository owner and only need doing once.

### 1. Register the trusted publisher on PyPI

Trusted publishing lets GitHub Actions upload without an API token existing
anywhere — no secret to leak, rotate or accidentally print.

On [pypi.org](https://pypi.org) → *Your projects* → *Publishing* → *Add a new
pending publisher*:

| Field | Value |
|---|---|
| PyPI project name | `flow5ctl` |
| Owner | `97kuek` |
| Repository name | `flow5ctl` |
| Workflow name | `release.yaml` |
| Environment name | `pypi` |

"Pending publisher" is the right form before the first upload: the project does not
exist on PyPI yet, and the first successful run creates it.

### 2. Create the `pypi` environment on GitHub

*Settings* → *Environments* → *New environment* → `pypi`. Adding yourself as a
required reviewer there is worth it: it turns a mistaken tag into a prompt rather
than into a version that can never be reused.

## Cutting a release

```bash
# 1. The changelog leads. Move [Unreleased] to the new version with today's date.
$EDITOR CHANGELOG.md

# 2. The version in pyproject.toml must match the tag exactly — the workflow
#    refuses the release otherwise, because PyPI will not let a filename be reused.
$EDITOR pyproject.toml

# 3. uv.lock records the project's own version, so it lags a release unless it is
#    refreshed here. Left out, it becomes a follow-up commit every time.
uv lock

# 4. Everything green locally, including the tests CI cannot run.
uv run ruff check src tests tools poc
uv run pytest -q                    # includes the real flow5 runs
python3 tools/check_docs.py

# 5. Commit, tag, push.
git commit -am "chore: release 0.1.0"
git tag -a v0.1.0 -m "0.1.0"
git push && git push origin v0.1.0    # the one tag, not every local v*
```

The workflow then checks the tag against the packaged version, lints, runs the
suite, builds, runs `twine check`, publishes to PyPI, and creates the GitHub
release with the artifacts attached.

## Before the first release, run the package the way a user will

Building and importing is not the same as installing. Presets are `.yaml` files
inside the package and a data file that fails to ship makes the wheel useless while
every test still passes, because the tests read them from the source tree.

```bash
uv build --out-dir /tmp/dist
uv venv /tmp/relcheck
uv pip install --python /tmp/relcheck/bin/python "/tmp/dist/flow5ctl-<version>-py3-none-any.whl[plot]"

export FLOW5CTL_WORKSPACE=/tmp/relcheck-ws
/tmp/relcheck/bin/flow5ctl doctor            # finds flow5, lists 4 presets
/tmp/relcheck/bin/flow5ctl init g --file examples/rc-glider.yaml
/tmp/relcheck/bin/flow5ctl analyze g --name check
```

The last command must produce a polar, not just exit zero. This project's failure
mode is confident wrong numbers, and a release is the worst place for one.

## Version numbers

[Semantic versioning](https://semver.org/) from 0.1.0 onward, with the pre-1.0
convention that the minor number carries breaking changes.

`design.yaml` is a published interface. Adding a field is a minor release; changing
what an existing field means, or removing one, is the kind of change that needs a
minor bump and a note in the changelog saying what to edit. The schema resource
`flow5://schema/design` is generated from the model, so it follows automatically.

## If the publish job fails with `invalid-publisher`

This happened on the first attempt at 0.1.0, and it is the likely failure, so it is
worth knowing what it does and does not mean.

```
* `invalid-publisher`: valid token, but no corresponding publisher
  (Publisher with matching claims was not found)
```

**Nothing was published and no version was consumed.** PyPI reserves a filename only
on a successful upload, so the same tag can be published again once the publisher is
fixed — there is no need to bump the version or delete the tag.

The action prints the claims GitHub actually sent. Every one of them has to match
the registration exactly:

| claim | what it will say | what to register |
|---|---|---|
| `repository` | `<owner>/<repo>` | Owner and Repository name, separately |
| `workflow_ref` | `…/.github/workflows/release.yaml@refs/tags/v0.1.0` | **`release.yaml`** — the *filename*, and it must match character for character. `release.yml` and `release.yaml` are different publishers to PyPI; this is what failed on the first attempt at 0.1.0 |
| `environment` | `pypi` | `pypi` |

The workflow-name field is the one that catches people twice over: the tab in
GitHub says "Release" and the field wants the filename, and `.yml` against `.yaml`
is a mismatch like any other. The workflow here is deliberately named
`release.yaml` — with the `a` — because that is what the registration says.

Check the *Pending publishers* list on
[pypi.org/manage/account/publishing](https://pypi.org/manage/account/publishing/) —
if the row is not there at all, the form did not save. Delete and re-add a row that
does not match rather than editing around it.

Then re-run only the failed job; the build, the tests and `twine check` have already
passed and do not need repeating:

```bash
gh run rerun <run-id> --failed
```

## If the upload fails halfway

PyPI filenames are permanent: a version that uploaded even partially cannot be
re-uploaded, and the fix is always a new version number, never a force. Delete the
tag, bump to the next patch, and start again.
