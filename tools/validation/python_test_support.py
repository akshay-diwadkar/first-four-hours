"""Execute actual Python entrypoints in-process when process isolation is not the claim."""
from __future__ import annotations
import contextlib
import io
import os
import runpy
import subprocess
import sys
from pathlib import Path

_NATIVE_RUN = subprocess.run
_SKILLS = str(Path(__file__).resolve().parents[2] / "skills")


def run_python(argv, **kwargs):
    if (len(argv) < 2 or str(argv[0]) != sys.executable or not str(argv[1]).endswith(".py")
        or not kwargs.get("capture_output") or not kwargs.get("text")
        or "fake-gh" in str(kwargs.get("env", {}).get("PYTHONPATH", ""))):
        return _NATIVE_RUN(argv, **kwargs)
    script = Path(argv[1]).resolve()
    if not script.is_file():
        return _NATIVE_RUN(argv, **kwargs)
    # Only the selected entrypoint's own Python steps may share this interpreter.
    # Authored verification commands and native Git/GitHub commands remain real processes.
    allowed = script.parent
    old_run = subprocess.run
    def child(command, **options):
        if (len(command) > 1 and str(command[0]) == sys.executable
            and str(command[1]).endswith(".py") and Path(command[1]).resolve().is_relative_to(allowed)):
            return run_python(command, **options)
        return _NATIVE_RUN(command, **options)
    before = dict(sys.modules)
    old_path, old_args, old_env, old_cwd = sys.path[:], sys.argv[:], os.environ.copy(), Path.cwd()
    out, err = io.StringIO(), io.StringIO()
    owned = {name for name, module in before.items()
             if str(getattr(module, "__file__", "")).startswith(_SKILLS)}
    try:
        for name in owned:
            sys.modules.pop(name, None)
        if kwargs.get("env", {}).get("PYTHONPATH") == "":
            checkout = str(Path(__file__).resolve().parents[2])
            sys.path[:] = [entry for entry in sys.path if entry and not str(entry).startswith(checkout)]
        sys.path.insert(0, str(script.parent))
        sys.argv = list(map(str, argv[1:]))
        if kwargs.get("env") is not None:
            os.environ.clear()
            os.environ.update(kwargs["env"])
        if kwargs.get("cwd") is not None:
            os.chdir(kwargs["cwd"])
        subprocess.run = child
        code = 0
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                runpy.run_path(str(script), run_name="__main__")
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else int(exc.code is not None)
        result = subprocess.CompletedProcess(argv, code, out.getvalue(), err.getvalue())
        if kwargs.get("check") and code:
            raise subprocess.CalledProcessError(code, argv, result.stdout, result.stderr)
        return result
    finally:
        subprocess.run = old_run
        os.chdir(old_cwd)
        os.environ.clear()
        os.environ.update(old_env)
        sys.argv, sys.path = old_args, old_path
        for name in list(sys.modules):
            module = sys.modules[name]
            file = str(getattr(module, "__file__", ""))
            if file.startswith(_SKILLS) or file.startswith(str(allowed)):
                sys.modules.pop(name, None)
        sys.modules.update({name: module for name, module in before.items() if name in owned or name not in sys.modules})
