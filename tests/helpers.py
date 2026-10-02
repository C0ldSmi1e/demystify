"""Shared paths and loaders for the tests. Standard library only."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # the tests import the scripts: do not leave __pycache__ in the skill folder

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / "skills" / "demystify"
SCRIPTS = SKILL / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load(name: str):
    """Import one of the skill's scripts as a module."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_script(name: str, *args, stdin: str = None, env=None, timeout: int = 120):
    """Run a script the way an agent does: `python3 <path> args`."""
    return subprocess.run(
        [sys.executable, str(SCRIPTS / (name + ".py"))] + [str(a) for a in args],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )
