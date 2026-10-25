# Contributing

- Work on a branch (`feature/…`, `fix/…`) and open a pull request into `main`.
- `main` is protected: a pull request and green checks (hassfest, HACS, tests) are required.
- Releases are tags on `main`. Pre-releases (`v0.2.0b1`) reach only HACS users who enable beta versions; the same version without the suffix is the stable release.
- Bump `version` in `custom_components/kronan/manifest.json` to match the tag in the same pull request.

Run the tests locally:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest -q
```
