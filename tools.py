"""Tool handlers — the code that runs when the model calls a Creative Review tool.

Rules (from the Hermes plugin guide):
1. signature ``def handler(args: dict, **kwargs) -> str``
2. always return a JSON string, success and error alike
3. never raise — catch everything and return an error object
"""
from __future__ import annotations

import json
from typing import Any

from . import brief, export, store


def _ok(**payload: Any) -> str:
    return json.dumps({"ok": True, **payload})


def _err(message: Any, **extra: Any) -> str:
    return json.dumps({"ok": False, "error": str(message), **extra})


# --------------------------------------------------------------------------- #
def create_board(args: dict, **kwargs: Any) -> str:
    try:
        title = (args.get("title") or "").strip()
        if not title:
            return _err("title is required")
        board = store.create_board(title)
        return _ok(board_id=board["id"], board=board)
    except Exception as exc:  # noqa: BLE001
        return _err(f"could not create board: {exc}")


def list_boards(args: dict, **kwargs: Any) -> str:
    try:
        boards = store.list_boards()
        return _ok(count=len(boards), boards=boards)
    except Exception as exc:  # noqa: BLE001
        return _err(f"could not list boards: {exc}")


def add_image(args: dict, **kwargs: Any) -> str:
    try:
        board_id = (args.get("board_id") or "").strip()
        path = (args.get("path") or "").strip()
        role = (args.get("role") or store.ROLE_GENERATED).strip()
        label = (args.get("label") or "").strip()
        parent_id = (args.get("parent_id") or "").strip() or None
        if not board_id or not path:
            return _err("board_id and path are required")
        image = store.add_image(board_id, path, role=role, label=label, parent_id=parent_id)
        if parent_id:
            store.link_revision_child(board_id, parent_id, image["id"])
        return _ok(image=image)
    except FileNotFoundError as exc:
        return _err(str(exc), reason="file-not-found")
    except ValueError as exc:
        return _err(str(exc), reason="invalid")
    except Exception as exc:  # noqa: BLE001
        return _err(f"could not add image: {exc}")


def get_board(args: dict, **kwargs: Any) -> str:
    try:
        board_id = (args.get("board_id") or "").strip()
        if not board_id:
            return _err("board_id is required")
        board = store.get_board(board_id)
        if board is None:
            return _err(f"unknown board: {board_id}", reason="not-found")
        return _ok(board=board)
    except Exception as exc:  # noqa: BLE001
        return _err(f"could not read board: {exc}")


def revision_brief(args: dict, **kwargs: Any) -> str:
    try:
        board_id = (args.get("board_id") or "").strip()
        image_id = (args.get("image_id") or "").strip()
        overall_note = (args.get("overall_note") or "").strip()
        if not board_id or not image_id:
            return _err("board_id and image_id are required")
        board = store.get_board(board_id)
        if board is None:
            return _err(f"unknown board: {board_id}", reason="not-found")
        image = store.get_image(image_id)
        if image is None:
            return _err(f"unknown image: {image_id}", reason="not-found")
        store.require_board_image(board_id, image_id)
        reference = next((im for im in board.get("images", [])
                          if im.get("role") == store.ROLE_REFERENCE), None)
        data = brief.build_brief(board, image, reference=reference, overall_note=overall_note)
        store.create_revision(board_id, image_id, data["markdown"])
        return _ok(brief=data)
    except Exception as exc:  # noqa: BLE001
        return _err(f"could not build brief: {exc}")


def approve(args: dict, **kwargs: Any) -> str:
    try:
        board_id = (args.get("board_id") or "").strip()
        image_id = (args.get("image_id") or "").strip()
        decision = (args.get("decision") or "approved").strip()
        if not board_id or not image_id:
            return _err("board_id and image_id are required")
        if decision not in {"approved", "rejected"}:
            return _err("decision must be 'approved' or 'rejected'")
        if store.get_board(board_id) is None:
            return _err(f"unknown board: {board_id}", reason="not-found")
        approval = store.set_approval(board_id, image_id, decision)
        return _ok(approval=approval)
    except Exception as exc:  # noqa: BLE001
        return _err(f"could not record decision: {exc}")


def export_board(args: dict, **kwargs: Any) -> str:
    try:
        board_id = (args.get("board_id") or "").strip()
        fmt = (args.get("format") or "json").strip()
        out_dir = (args.get("out_dir") or "").strip() or None
        if not board_id:
            return _err("board_id is required")
        if fmt not in {"json", "markdown"}:
            return _err("format must be 'json' or 'markdown'")
        board = store.get_board(board_id)
        if board is None:
            return _err(f"unknown board: {board_id}", reason="not-found")
        result = export.export_board(board, fmt=fmt, out_dir=out_dir)
        return _ok(**result)
    except Exception as exc:  # noqa: BLE001
        return _err(f"could not export board: {exc}")