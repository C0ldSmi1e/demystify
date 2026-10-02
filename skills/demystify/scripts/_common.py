"""Shared helpers for the demystify scripts.

Standard library only. Runs on Python 3.8 and later, so that the system
`python3` of any current macOS or Linux can run it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = SKILL_DIR / "assets"

# Pinned versions. The video pipeline is tested with exactly these.
MANIM = "manim==0.21.0"
MANIM_MATH = "manim[typst]==0.21.0"
KOKORO = "kokoro-onnx==0.6.1"
SOUNDFILE = "soundfile"

# Interpreters that Manim 0.21 and kokoro-onnx 0.6 both support, in order of preference.
PYTHONS = ("3.12", "3.11", "3.13")

UV_INSTALL_HINT = {
    "macos": "brew install uv    (or: curl -LsSf https://astral.sh/uv/install.sh | sh)",
    "linux": "curl -LsSf https://astral.sh/uv/install.sh | sh",
    "windows": 'powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"',
}
CAIRO_INSTALL_HINT = {
    "macos": "brew install cairo pkg-config",
    "linux": "sudo apt install build-essential python3-dev pkg-config libcairo2-dev libpango1.0-dev"
    "    (Fedora: sudo dnf install gcc python3-devel pkgconf cairo-devel pango-devel)",
    "windows": "no action: Manim ships prebuilt wheels for Windows",
}


def eprint(*args) -> None:
    print(*args, file=sys.stderr)


def system() -> str:
    if sys.platform == "darwin":
        return "macos"
    if os.name == "nt":
        return "windows"
    return "linux"


def cache_dir() -> Path:
    """Where large downloads live (the voice model). Override with DEMYSTIFY_CACHE."""
    env = os.environ.get("DEMYSTIFY_CACHE")
    if env:
        return Path(env).expanduser()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "demystify"
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "demystify"


def run(cmd, timeout=None, env=None, cwd=None) -> subprocess.CompletedProcess:
    """Run a command and capture its output as text. Never raises on a non-zero exit."""
    try:
        return subprocess.run(
            [str(c) for c in cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=str(cwd) if cwd else None,
        )
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(cmd, 127, "", str(exc))
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout if isinstance(exc.stdout, str) else ""
        return subprocess.CompletedProcess(cmd, 124, out, "timed out after %s s" % timeout)


def find_uv():
    """Path of the `uv` program, or None."""
    found = shutil.which("uv")
    if found:
        return found
    home = Path.home()
    for candidate in (
        home / ".local" / "bin" / "uv",
        home / ".cargo" / "bin" / "uv",
        Path("/opt/homebrew/bin/uv"),
        Path("/usr/local/bin/uv"),
    ):
        if candidate.is_file() and os.access(str(candidate), os.X_OK):
            return str(candidate)
    return None


def uv_version(uv) -> str:
    proc = run([uv, "--version"], timeout=20)
    return proc.stdout.strip().replace("uv ", "", 1) if proc.returncode == 0 else ""


def find_python(uv):
    """Return (version, found_locally).

    Prefers an interpreter that is already on the machine, so that uv does not
    download one. If none is found, uv downloads Python 3.12 on first use.
    """
    for version in PYTHONS:
        proc = run([uv, "python", "find", version], timeout=30)
        if proc.returncode == 0 and proc.stdout.strip():
            return version, True
    return PYTHONS[0], False


def uv_run(uv, python, packages, args):
    """Command line for a temporary environment: nothing is installed permanently."""
    cmd = [uv, "run", "--no-project", "--python", python]
    for package in packages:
        cmd += ["--with", package]
    return cmd + [str(a) for a in args]


def pkg_config(name):
    """Return (present, detail). detail is the version, or the reason it is missing."""
    if not shutil.which("pkg-config"):
        return False, "pkg-config is not installed"
    if run(["pkg-config", "--exists", name], timeout=15).returncode != 0:
        return False, "%s is not installed" % name
    version = run(["pkg-config", "--modversion", name], timeout=15).stdout.strip()
    return True, version


def find_browser():
    """Path of a Chrome-family browser that can run headless, or None.

    Set DEMYSTIFY_BROWSER to use a specific one.
    """
    env = os.environ.get("DEMYSTIFY_BROWSER")
    if env:
        return env if Path(env).exists() or shutil.which(env) else None
    which = system()
    if which == "macos":
        apps = (
            "Google Chrome.app/Contents/MacOS/Google Chrome",
            "Chromium.app/Contents/MacOS/Chromium",
            "Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "Brave Browser.app/Contents/MacOS/Brave Browser",
            "Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
        )
        for root in (Path("/Applications"), Path.home() / "Applications"):
            for app in apps:
                path = root / app
                if path.exists():
                    return str(path)
    elif which == "windows":
        roots = [os.environ.get(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        tails = (
            "Google/Chrome/Application/chrome.exe",
            "Microsoft/Edge/Application/msedge.exe",
            "BraveSoftware/Brave-Browser/Application/brave.exe",
            "Chromium/Application/chrome.exe",
        )
        for root in roots:
            if not root:
                continue
            for tail in tails:
                path = Path(root) / tail
                if path.exists():
                    return str(path)
    for name in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "microsoft-edge",
        "brave-browser",
        "chrome",
    ):
        found = shutil.which(name)
        if found:
            return found
    return None


def kokoro_files():
    """The two files of the Kokoro voice model, with what is needed to fetch and verify them."""
    base = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/"
    folder = cache_dir() / "kokoro"
    return [
        {
            "path": folder / "kokoro-v1.0.onnx",
            "url": base + "kokoro-v1.0.onnx",
            "size": 325505369,
            "sha256": "beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a",
        },
        {
            "path": folder / "voices-v1.0.bin",
            "url": base + "voices-v1.0.bin",
            "size": 28214398,
            "sha256": "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
        },
    ]


def kokoro_cached() -> bool:
    return all(f["path"].is_file() and f["path"].stat().st_size == f["size"] for f in kokoro_files())
