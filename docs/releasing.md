# Publishing to python.wattka.dev

`.github/workflows/wheels.yml` runs on pushed `v*` tags and manual Actions runs.
First it reads `project.name` and `project.version` from `pyproject.toml`, validates
release tags, and checks the public HTML Simple index. If **any wheel** of that
exact version already exists, the entire build/publication is skipped. An sdist
alone does not cause a skip. Network, authentication and server failures stop the
workflow rather than being interpreted as a missing release.

## Credentials (one-time GitHub setup)

1. Open the repository's **Settings → Environments → New environment**.
2. Name it **private-index**.
3. Under **Environment secrets**, add:
   - `PRIVATE_INDEX_USERNAME`: the pypiserver upload username.
   - `PRIVATE_INDEX_PASSWORD`: its password.
4. Configure required reviewers and allowed deployment tags/branches if desired.
   Manual runs publish too, so allow only trusted release refs.

Alternatively, repository secrets with the same names can be added under
**Settings → Secrets and variables → Actions → New repository secret**.
Environment secrets are preferred for restricting access to the publishing job.
Never commit credentials or embed them in URLs. They are passed to uv only
through environment variables, without shell interpolation or printing.

The server must accept authenticated legacy PyPI uploads at
`https://python.wattka.dev/` (the pypiserver default). `/simple/` is the **read**
index, not the upload URL. No upload is performed during local validation.

## Coverage

- CPython 3.12 and 3.13.
- Linux glibc x86_64 and ARM64 (`manylinux_2_28`).
- Windows x64.
- macOS Intel and Apple Silicon.

The workflow builds 10 wheels and an sdist, then uploads when all builds pass.
Tests remain in the separate CI workflow and do not gate this publication job.
It does not publish to PyPI.org. Alpine/musllinux, Windows ARM64, Python 3.14+
and free-threaded Python are not covered. GitHub-hosted ARM Linux runner
availability depends on repository visibility/plan; use an eligible ARM64 runner
if unavailable.

## Release

Update the project version (and keep `Cargo.toml` consistent), commit, then push
the matching tag, for example `v0.2.1`. Or choose **Actions → Build and publish
wheels → Run workflow** on a trusted ref.

Version 0.2.0 already has a Windows wheel on this index and will be skipped.
Partial uploads also cause the next run to skip: the check deliberately means
"any wheel exists", not "every platform is complete". If an upload fails midway,
inspect the index and finish the missing uploads manually with the retained
Actions artifacts, or remove the incomplete version on the server before retrying.
Never silently overwrite published wheels. Uploads are not atomic.

Install without falling back to PyPI:

```sh
python -m pip install bson --index-url https://python.wattka.dev/simple/ --only-binary=:all:
```