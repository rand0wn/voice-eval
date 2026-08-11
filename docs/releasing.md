# Releasing Voice Eval

Voice Eval publishes to PyPI through GitHub Actions trusted publishing. No
long-lived PyPI token belongs in the repository or GitHub secrets.

## One-time PyPI setup

1. Create the `voice-agent-eval-lab` project on PyPI, or make its first manual
   upload from a trusted maintainer account.
2. In the PyPI project settings, add a trusted publisher for:
   - owner: `rand0wn`
   - repository: `voice-eval`
   - workflow: `publish.yml`
   - environment: `pypi`
3. In the GitHub repository settings, create an environment named `pypi`.

## Release checklist

1. Update the version in `pyproject.toml` and confirm the README reflects the
   public installation path.
2. Run:

   ```bash
   pytest -q
   python -m build
   python -m pip install --force-reinstall dist/*.whl
   voice-eval suite --adapter cascade --min-score 1 --min-tool-recall 1 --max-p95-ms 900
   ```

3. Merge the release pull request only after CI passes.
4. Create a GitHub release whose tag matches the package version, for example
   `v0.3.0`. Publishing the release triggers `publish.yml`.
5. Confirm the workflow succeeds and install the released package in a clean
   environment before announcing it.

If publishing fails, do not reuse the same version number after any artifact
has reached PyPI. Fix the issue, increment the patch version, and release again.
