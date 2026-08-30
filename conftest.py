"""
TEMPORARY collection guard for the repo reorganization safety net.

The repo root still has legacy `test_*.py` scripts left over from before the
reorg (test_400s.py, test_400s2.py, test_diag.py, test_diag2.py,
test_dashboard_review.py, test_dashboard_e2e.py, test_search.py,
test_semantic_encoder.py). Several of them run unguarded Playwright code at
*module import time* (a bare `with sync_playwright(): p.chromium.launch(...)`
at top level), which launches a real headless Chromium against the live
server the instant the file is imported — including for `--collect-only`.

`[tool.pytest.ini_options] testpaths = ["tests"]` in pyproject.toml stops a
bare `pytest` invocation from ever looking at these files, but testpaths is
only a *default* used when no paths are given on the command line — it does
NOT stop `pytest test_400s.py`, a glob, or an IDE's "run this file", all of
which name the file explicitly on the command line.

A plain `collect_ignore_glob` is not enough for that case: pytest never even
consults the `pytest_ignore_collect` hook for a path that was named
explicitly on the command line (see `Session._collect_path` /
`Dir.collect()` in `_pytest/main.py`, which only checks
`pytest_ignore_collect` for paths that are *not* `session.isinitpath(...)`).
So instead this hooks the one call in the chain that unconditionally decides
whether a `.py` file becomes an importable test module —
`pytest_pycollect_makemodule`, which the docs mark "stops at first non-None
result" — and substitutes a do-nothing collector for any root-level
`test_*.py` path before pytest's own implementation (which would import the
file) ever runs.

DELETE THIS FILE once the legacy root-level test_*.py scripts are removed
(Tasks 4 and 12 of the reorganization) — it exists only to protect against
them in the meantime and serves no purpose once they are gone.
"""

import fnmatch
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.resolve()
_LEGACY_TEST_GLOB = "test_*.py"

# Belt: stops these files being auto-discovered at all (already effective for
# every root-level test_*.py that is NOT named explicitly on the command
# line).
collect_ignore_glob = [_LEGACY_TEST_GLOB]


class _BlockedLegacyModule(pytest.File):
    """Stands in for a legacy root-level test_*.py file so pytest never
    imports it — and so never executes its unguarded top-level Playwright
    code — no matter how the file was named on the pytest command line."""

    def collect(self):
        return []

    def reportinfo(self):
        return self.path, 0, "collection blocked: legacy root-level test script (see conftest.py)"


# Braces: stops the same files being imported even when passed explicitly,
# e.g. `pytest test_400s.py`, which bypasses collect_ignore_glob entirely.
@pytest.hookimpl(tryfirst=True)
def pytest_pycollect_makemodule(module_path: Path, parent):
    if module_path.parent == _ROOT and fnmatch.fnmatch(module_path.name, _LEGACY_TEST_GLOB):
        return _BlockedLegacyModule.from_parent(parent, path=module_path)
    return None
