# Releasing

The version lives in one place: `agent_status/__init__.py` → `__version__`. `pyproject.toml` reads it dynamically, and
`agent-status --version` prints it. A release tag must match it exactly.

## One-time PyPI setup (repository owner)

The [release workflow](../.github/workflows/release.yml) publishes with PyPI trusted publishing (OIDC), so there is no
API token in GitHub secrets.

1. Create the `agent-status` project on PyPI, or add a **pending trusted publisher** for it.
2. Configure the trusted publisher with:
   - owner: `prateekjaindev`
   - repository: `agent-status`
   - workflow: `release.yml`
   - environment: `pypi`
3. Optionally add protection rules to the `pypi` environment in the GitHub repository settings.

Until this is done, a `v*` tag will build and pass the version check, then fail at the publish step.

## Cut a release

1. Bump `__version__` in `agent_status/__init__.py`.
2. Add the matching entry to [`CHANGELOG.md`](../CHANGELOG.md).
3. Commit, then tag and push:

   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

4. The workflow checks `v$version == $GITHUB_REF_NAME`, builds the sdist and wheel, and publishes them.
5. Verify the install, then switch the README install line to the PyPI command:

   ```bash
   uv tool install agent-status
   # or: pipx install agent-status
   ```
