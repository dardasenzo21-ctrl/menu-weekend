"""Client du moteur Blender : lance ``engine.py`` dans un sous-processus et dialogue en JSON.

Deux backends :

* ``module`` : l'interpréteur courant possède ``bpy`` (``pip install bpy``) → ``python -m blender_buildings.engine``.
* ``binary`` : un exécutable Blender (``BLENDER_BIN`` ou détection automatique) → ``blender -b --python engine.py``.

``backend="auto"`` choisit le module s'il est importable, sinon le binaire.
"""

from __future__ import annotations

import collections
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import threading
import time
from typing import Any

from . import engine as _engine_module

ENGINE_PATH = os.path.abspath(_engine_module.__file__)
_CANDIDATE_BINARIES = (
    "/opt/blender/blender",
    "/usr/local/bin/blender",
    "/usr/bin/blender",
    "/Applications/Blender.app/Contents/MacOS/Blender",
    "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe",
)


class EngineError(RuntimeError):
    def __init__(self, message: str, traceback_text: str | None = None):
        super().__init__(message)
        self.traceback_text = traceback_text


class EngineCrashed(EngineError):
    pass


def find_blender_binary() -> str | None:
    env = os.environ.get("BLENDER_BIN")
    if env and os.path.exists(env):
        return env
    # <racine du projet blender/>/vendor/blender/blender (installé par scripts/setup.sh)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(ENGINE_PATH)))
    repo_local = os.path.join(project_root, "vendor", "blender", "blender")
    if os.path.exists(repo_local):
        return repo_local
    for c in _CANDIDATE_BINARIES:
        if os.path.exists(c):
            return c
    return shutil.which("blender")


def module_backend_available(python: str | None = None) -> bool:
    python = python or sys.executable
    try:
        r = subprocess.run([python, "-c", "import bpy"], capture_output=True, timeout=120)
        return r.returncode == 0
    except Exception:
        return False


class BlenderEngine:
    """Sous-processus Blender persistant. Thread-safe (une commande à la fois)."""

    def __init__(self, backend: str = "auto", blender_bin: str | None = None, python: str | None = None, timeout: float = 900.0, log_lines: int = 200, env: dict[str, str] | None = None):
        self.backend = backend
        self.blender_bin = blender_bin
        self.python = python or sys.executable
        self.timeout = timeout
        self.env = env or {}
        self._proc: subprocess.Popen[bytes] | None = None
        self._lock = threading.RLock()
        self._next_id = 1
        self._stderr: collections.deque[str] = collections.deque(maxlen=log_lines)
        self._stderr_thread: threading.Thread | None = None
        self.info: dict[str, Any] = {}

    # ---- cycle de vie --------------------------------------------------------------------------
    def _command(self) -> list[str]:
        backend = self.backend
        if backend == "auto":
            backend = "module" if module_backend_available(self.python) else "binary"
        self.resolved_backend = backend
        if backend == "module":
            return [self.python, "-u", "-m", "blender_buildings.engine"]
        if backend == "binary":
            binary = self.blender_bin or find_blender_binary()
            if not binary:
                raise EngineError("Aucun binaire Blender trouvé (définir BLENDER_BIN) et le module bpy est absent.")
            sites = [sysconfig.get_paths()["purelib"]]
            cmd = [binary, "-b", "--factory-startup", "--python-exit-code", "1", "--python", ENGINE_PATH, "--"]
            for s in sites:
                cmd += ["--site", s]
            return cmd
        raise EngineError(f"Backend inconnu : {backend!r}")

    def start(self) -> "BlenderEngine":
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return self
            env = dict(os.environ)
            env.update(self.env)
            src_dir = os.path.dirname(os.path.dirname(ENGINE_PATH))
            env["PYTHONPATH"] = src_dir + os.pathsep + env.get("PYTHONPATH", "")
            env.setdefault("PYTHONIOENCODING", "utf-8")
            cmd = self._command()
            self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=src_dir)
            self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
            self._stderr_thread.start()
            ready = self._read_response(expect_id=None, timeout=self.timeout)
            self.info = ready.get("result", {})
            return self

    def _drain_stderr(self) -> None:
        proc = self._proc
        assert proc is not None and proc.stderr is not None
        for raw in iter(proc.stderr.readline, b""):
            self._stderr.append(raw.decode("utf-8", "replace").rstrip())

    def stop(self) -> None:
        with self._lock:
            proc = self._proc
            if proc is None:
                return
            try:
                if proc.poll() is None and proc.stdin:
                    proc.stdin.write(b'{"id": 0, "op": "quit"}\n')
                    proc.stdin.flush()
                    proc.wait(timeout=10)
            except Exception:
                pass
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=10)
                self._proc = None

    def restart(self) -> "BlenderEngine":
        self.stop()
        return self.start()

    def __enter__(self) -> "BlenderEngine":
        return self.start()

    def __exit__(self, *exc: Any) -> None:
        self.stop()

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def log(self) -> str:
        return "\n".join(self._stderr)

    # ---- appels ---------------------------------------------------------------------------------
    def _read_response(self, expect_id: int | None, timeout: float) -> dict[str, Any]:
        proc = self._proc
        assert proc is not None and proc.stdout is not None
        deadline = time.monotonic() + timeout
        result: dict[str, Any] = {}

        def reader() -> None:
            nonlocal result
            while True:
                raw = proc.stdout.readline()
                if not raw:
                    return
                try:
                    msg = json.loads(raw.decode("utf-8", "replace"))
                except json.JSONDecodeError:
                    continue
                if expect_id is None or msg.get("id") == expect_id:
                    result = msg
                    return

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        t.join(max(0.0, deadline - time.monotonic()))
        if t.is_alive():
            proc.kill()
            self._proc = None
            raise EngineCrashed(f"Délai dépassé ({timeout}s) ; moteur arrêté.\n{self.log}")
        if not result:
            code = proc.poll()
            self._proc = None
            raise EngineCrashed(f"Le moteur Blender s'est arrêté (code {code}).\n{self.log}")
        return result

    def call(self, op: str, timeout: float | None = None, **args: Any) -> Any:
        with self._lock:
            if not self.alive:
                self.start()
            proc = self._proc
            assert proc is not None and proc.stdin is not None
            mid = self._next_id
            self._next_id += 1
            payload = json.dumps({"id": mid, "op": op, "args": args}, ensure_ascii=False) + "\n"
            try:
                proc.stdin.write(payload.encode("utf-8"))
                proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self._proc = None
                raise EngineCrashed(f"Impossible d'écrire vers le moteur : {exc}\n{self.log}") from exc
            msg = self._read_response(mid, timeout or self.timeout)
            if not msg.get("ok"):
                raise EngineError(msg.get("error", "erreur inconnue"), msg.get("traceback"))
            return msg.get("result")

    # ---- raccourcis -----------------------------------------------------------------------------
    def ping(self) -> dict[str, Any]:
        return self.call("ping")

    def reset(self) -> dict[str, Any]:
        return self.call("reset")

    def build_building(self, spec: dict[str, Any] | None = None, preset: str | None = None, overrides: dict[str, Any] | None = None, reset: bool = False) -> dict[str, Any]:
        return self.call("build_building", spec=spec, preset=preset, overrides=overrides, reset=reset)

    def render(self, path: str, **kw: Any) -> dict[str, Any]:
        return self.call("render", path=path, **kw)

    def export(self, path: str, format: str | None = None, objects: list[str] | None = None) -> dict[str, Any]:
        return self.call("export", path=path, format=format, objects=objects)


_shared: BlenderEngine | None = None
_shared_lock = threading.Lock()


def shared_engine(**kwargs: Any) -> BlenderEngine:
    """Moteur partagé (un seul processus Blender par application)."""
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = BlenderEngine(**kwargs)
        return _shared
