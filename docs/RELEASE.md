# Releasing kept

The workflow in `.github/workflows/release.yml` does the publishing. Two steps
cannot be automated from here, because they need a browser and an account.

## One-time: tell PyPI to trust this repository

kept publishes with **trusted publishing**, so no API token is ever stored in this
repository. PyPI has to be told which workflow is allowed to publish, once.

1. Sign in at <https://pypi.org>.
2. Go to **Your account → Publishing → Add a new pending publisher**.
3. Fill in exactly:

   | Field | Value |
   |---|---|
   | PyPI project name | `kept-cli` |
   | Owner | `hicksonhaziel` |
   | Repository name | `kept` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

4. Save. The name `kept-cli` is claimed at this point, so nobody else can take it.
   (`kept` alone is already taken by an unrelated project, which is why the package
   is `kept-cli` and the command is `kept`.)
5. In this repository, **Settings → Environments → New environment**, named `pypi`.
   Nothing needs to go in it; the workflow references it so the publisher matches.

## Every release

1. Bump `version` in `pyproject.toml`. It is the source of truth, and the workflow
   refuses to publish if the tag disagrees with it.
2. Commit that bump on `main`.
3. Tag and push:

   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

4. Watch the run. It tests, verifies kept against its own ledger, builds, publishes.

A published version can never be replaced or reused. If `0.1.0` goes out wrong, the
only remedy is `0.1.1`.

## Rehearsing without spending the version number

TestPyPI is a separate index with separate accounts. Repeat the pending-publisher
step at <https://test.pypi.org>, then:

```bash
uv build
uv publish --index testpypi
```

and install it somewhere clean to confirm the console script works:

```bash
uv venv /tmp/kept-check && . /tmp/kept-check/bin/activate
uv pip install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ kept-cli
kept --version && kept parse --help
```

The `--extra-index-url` matters: TestPyPI does not carry `coverage` or `libcst`, so
without it the install fails for reasons that have nothing to do with kept.

## What publishing does not affect

The GitHub Action installs kept from its own checkout, not from an index, so
`uses: hicksonhaziel/kept@v0` works whether or not the package is on PyPI. Judges
cloning the repository are likewise unaffected.
