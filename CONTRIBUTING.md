# Contributing

Contributions should include a clear description, relevant tests and confirmation that you have the right to submit the material under Apache-2.0. Do not include credentials, private captures or third-party source without documented permission. Review of issues and pull requests is at the maintainer's discretion; no support commitment is implied.

From a source checkout, install development tools and run the same checks as CI:

```sh
python -m pip install -e . pytest build 'tomli; python_version < "3.11"'
python -m pytest -q
python scripts/render_evidence.py --check
python scripts/check_docs.py
python -m build
python scripts/check_public_release.py . dist/*.whl dist/*.tar.gz
python scripts/check_boundary.py . dist/*.whl dist/*.tar.gz
python scripts/check_installed.py dist/*.whl
```

CI covers Python 3.10 and 3.13. Tests use temporary databases and temporary Git repositories, so `git` must be on PATH. Private experiment integrations and historical corpus tests are excluded from this distribution; they are not hidden behind missing-data skips.
