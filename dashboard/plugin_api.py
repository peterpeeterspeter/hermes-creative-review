"""Backend half of the Creative Review Hermes plugin.

Hermes' web server imports this file by path as the module
``hermes_dashboard_plugin_creative_review`` and mounts ``router`` under
``/api/plugins/creative-review`` -- only while ``creative-review`` is in the
host's ``plugins.enabled`` allow-list. That import is standalone (no package,
nothing of ours on ``sys.path``), so the bundle's own modules are loaded here by
path as well, under a private module prefix, and every route reaches them
through that.

Routes are thin: they validate a little, delegate to ``store`` / ``brief`` /
``export`` and answer JSON. The only route that touches image bytes is
``GET /image-data``, which reads one user file from disk and returns it as a
data URL for the Desktop pane; nothing is uploaded and no network call is made.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import Response

PLUGIN_ID = "creative-review"
PACKAGE = "creative_review_cache"

_BUNDLE_ROOT = Path(__file__).resolve().parent.parent


def _load(module_name: str):
    """Load a sibling module of this bundle by path, cached under PACKAGE."""
    full = f"{PACKAGE}.{module_name}"
    if full in sys.modules:
        return sys.modules[full]
    if PACKAGE not in sys.modules:
        import types
        pkg = types.ModuleType(PACKAGE)
        pkg.__path__ = [str(_BUNDLE_ROOT)]  # type: ignore[attr-defined]
        sys.modules[PACKAGE] = pkg
    path = _BUNDLE_ROOT / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(full, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


store = _load("store")
brief = _load("brief")
export = _load("export")

router = APIRouter()


def _bad(exc: Exception, default: str = "request failed") -> dict:
    return {"ok": False, "error": str(exc) or default}


@router.get("/health")
async def health() -> dict:
    return {"ok": True, "plugin": PLUGIN_ID, "schema": "creative-review/1"}


@router.get("/boards")
async def list_boards() -> dict:
    try:
        boards = store.list_boards()
        return {"ok": True, "count": len(boards), "boards": boards}
    except Exception as exc:  # noqa: BLE001
        return _bad(exc)


@router.post("/boards")
async def create_board(body: dict) -> dict:
    try:
        title = str(body.get("title") or "").strip()
        if not title:
            return {"ok": False, "error": "title is required"}
        board = store.create_board(title)
        return {"ok": True, "board": board}
    except Exception as exc:  # noqa: BLE001
        return _bad(exc)


@router.get("/board")
async def get_board(board_id: str) -> dict:
    try:
        board = store.get_board(board_id)
        if board is None:
            return {"ok": False, "error": "unknown board", "reason": "not-found"}
        return {"ok": True, "board": board}
    except Exception as exc:  # noqa: BLE001
        return _bad(exc)


@router.post("/image")
async def add_image(body: dict) -> dict:
    try:
        board_id = str(body.get("board_id") or "").strip()
        path = str(body.get("path") or "").strip()
        role = str(body.get("role") or store.ROLE_GENERATED).strip()
        label = str(body.get("label") or "").strip()
        parent_id = str(body.get("parent_id") or "").strip() or None
        if not board_id or not path:
            return {"ok": False, "error": "board_id and path are required"}
        image = store.add_image(board_id, path, role=role, label=label, parent_id=parent_id)
        if parent_id:
            store.link_revision_child(board_id, parent_id, image["id"])
        return {"ok": True, "image": image}
    except FileNotFoundError as exc:
        return {"ok": False, "error": str(exc), "reason": "file-not-found"}
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "reason": "invalid"}
    except Exception as exc:  # noqa: BLE001
        return _bad(exc)


@router.get("/image-data")
async def image_data(image_id: str) -> dict:
    try:
        return store.read_image_data_url(image_id)
    except Exception as exc:  # noqa: BLE001
        return _bad(exc)


@router.get("/file")
async def raw_file(image_id: str):
    try:
        data = store.read_image_bytes(image_id)
        if not data.get("ok"):
            payload = {k: v for k, v in data.items() if k != "data_url"}
            import json
            return Response(content=json.dumps(payload), media_type="application/json",
                            status_code=404)
        mime = data["mime"]
        raw = data["bytes"]
        return Response(content=raw, media_type=mime, headers={
            "Content-Disposition": f'inline; filename="{image_id}"'})
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@router.post("/annotation")
async def add_annotation(body: dict) -> dict:
    try:
        image_id = str(body.get("image_id") or "").strip()
        if not image_id:
            return {"ok": False, "error": "image_id is required"}
        annotation = store.add_annotation(
            image_id,
            float(body.get("x", 0.0)),
            float(body.get("y", 0.0)),
            note=str(body.get("note") or ""),
            author=str(body.get("author") or "user"),
            w=body.get("w"),
            h=body.get("h"),
        )
        return {"ok": True, "annotation": annotation}
    except Exception as exc:  # noqa: BLE001
        return _bad(exc)


@router.patch("/annotation")
async def update_annotation(body: dict) -> dict:
    try:
        ann_id = str(body.get("id") or "").strip()
        if not ann_id:
            return {"ok": False, "error": "id is required"}
        note = body.get("note")
        x = body.get("x")
        y = body.get("y")
        annotation = store.update_annotation(
            ann_id,
            note=None if note is None else str(note),
            x=None if x is None else float(x),
            y=None if y is None else float(y),
        )
        if annotation is None:
            return {"ok": False, "error": "unknown annotation", "reason": "not-found"}
        return {"ok": True, "annotation": annotation}
    except Exception as exc:  # noqa: BLE001
        return _bad(exc)


@router.delete("/annotation")
async def delete_annotation(id: str) -> dict:
    try:
        return {"ok": store.delete_annotation(id)}
    except Exception as exc:  # noqa: BLE001
        return _bad(exc)


@router.post("/revision")
async def build_revision(body: dict) -> dict:
    try:
        board_id = str(body.get("board_id") or "").strip()
        image_id = str(body.get("image_id") or "").strip()
        overall_note = str(body.get("overall_note") or "").strip()
        if not board_id or not image_id:
            return {"ok": False, "error": "board_id and image_id are required"}
        board = store.get_board(board_id)
        if board is None:
            return {"ok": False, "error": "unknown board", "reason": "not-found"}
        image = store.get_image(image_id)
        if image is None:
            return {"ok": False, "error": "unknown image", "reason": "not-found"}
        store.require_board_image(board_id, image_id)
        reference = next((im for im in board.get("images", [])
                          if im.get("role") == store.ROLE_REFERENCE), None)
        data = brief.build_brief(board, image, reference=reference, overall_note=overall_note)
        record = store.create_revision(board_id, image_id, data["markdown"])
        return {"ok": True, "brief": data, "revision_id": record["id"]}
    except Exception as exc:  # noqa: BLE001
        return _bad(exc)


@router.post("/revision-delivered")
async def revision_delivered(body: dict) -> dict:
    try:
        rev_id = str(body.get("revision_id") or "").strip()
        if not rev_id:
            return {"ok": False, "error": "revision_id is required"}
        store.mark_revision_delivered(rev_id)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return _bad(exc)


@router.post("/approve")
async def approve(body: dict) -> dict:
    try:
        board_id = str(body.get("board_id") or "").strip()
        image_id = str(body.get("image_id") or "").strip()
        decision = str(body.get("decision") or "approved").strip()
        if not board_id or not image_id:
            return {"ok": False, "error": "board_id and image_id are required"}
        if decision not in {"approved", "rejected"}:
            return {"ok": False, "error": "decision must be 'approved' or 'rejected'"}
        if store.get_board(board_id) is None:
            return {"ok": False, "error": "unknown board", "reason": "not-found"}
        approval = store.set_approval(board_id, image_id, decision)
        return {"ok": True, "approval": approval}
    except Exception as exc:  # noqa: BLE001
        return _bad(exc)


@router.get("/export")
async def export_board(board_id: str, format: str = "json") -> dict:  # noqa: A002
    try:
        board = store.get_board(board_id)
        if board is None:
            return {"ok": False, "error": "unknown board", "reason": "not-found"}
        if format not in {"json", "markdown"}:
            return {"ok": False, "error": "format must be json or markdown"}
        fmt = format
        return export.export_board(board, fmt=fmt)
    except Exception as exc:  # noqa: BLE001
        return _bad(exc)