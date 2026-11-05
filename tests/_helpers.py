"""Shared test helpers: point Hermes at a throwaway home and load the bundle.

Hermes' own ``plugins.plugin_storage`` resolves ``<HERMES_HOME>/plugin-data`` via
``hermes_constants``, so the tests set ``HERMES_HOME`` to a temp dir and put the
Hermes checkout on ``sys.path`` before importing anything from the plugin.
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
import tempfile
import types

if "HERMES_HOME" not in os.environ:
    os.environ["HERMES_HOME"] = tempfile.mkdtemp(prefix="cr-test-home-", dir=os.environ.get("TMPDIR"))

_REPO = pathlib.Path(
    os.environ.get("HERMES_AGENT_REPO")
    or (pathlib.Path.home() / ".hermes" / "hermes-agent")
)
if _REPO.is_dir() and str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

PLUGIN_DIR = pathlib.Path(__file__).resolve().parent.parent
_PKG = "cr_plugin_pkg"


def _ensure_package():
    if _PKG not in sys.modules:
        pkg = types.ModuleType(_PKG)
        pkg.__path__ = [str(PLUGIN_DIR)]  # type: ignore[attr-defined]
        sys.modules[_PKG] = pkg
    return _PKG


def load(name: str):
    """Import a module of the plugin bundle so intra-bundle relative imports work."""
    _ensure_package()
    full = f"{_PKG}.{name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, PLUGIN_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


def make_png(path: pathlib.Path, size: int = 8) -> pathlib.Path:
    """Write a tiny valid PNG so image helpers have a real file to read."""
    import struct
    import zlib

    path.parent.mkdir(parents=True, exist_ok=True)
    raw = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    raw += struct.pack(">I", 13) + b"IHDR" + ihdr + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))
    row = b"\x00" + b"\x10\x20\x30" * size
    idat = zlib.compress(row * size)
    raw += struct.pack(">I", len(idat)) + b"IDAT" + idat + struct.pack(">I", zlib.crc32(b"IDAT" + idat))
    raw += struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND"))
    path.write_bytes(raw)
    return path