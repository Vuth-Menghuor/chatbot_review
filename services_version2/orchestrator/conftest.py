"""
conftest.py — project-root fixture for pytest.

Adds the orchestrator root to sys.path so that `import app.*` works when
pytest is invoked from `e:/GDCE-Intern/Local/orchestrator` without the
package being pip-installed.  This is the standard pattern for pytest
projects that do not use an editable install or pyproject.toml.
"""
import sys
import os

# Insert the project root (the directory containing this file) at the
# front of sys.path so `app` and `prompts` are importable.
sys.path.insert(0, os.path.dirname(__file__))
