"""Export a board's approved image and its whole review history.

Two shapes, both written to disk locally:

* ``json`` — a machine-readable bundle (board, images, annotations, revisions,
  approval) plus a copy of the approved image beside it.
* ``markdown`` — a human-readable report of the same, plus the image copy.

Nothing is uploaded. The default destination is the plugin's own data folder
(``<HERMES_HOME>/plugin-data/creative-review/exports/``), which survives plugin
updates and follows the active profile.
"""
from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Optional


def _export_dir(out_dir: Optional[str]) -> Path:
    if out_dir:
        target = Path(out_dir).expanduser()
    else:
        from plugins.plugin_storage import plugin_data_dir
        target = plugin_data_dir("creative-review") / "exports"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _approved_image(board: dict[str, Any]) -> Optional[dict[str, Any]]:
    approval = board.get("approval")
    if approval and approval.get("decision") == "approved":
        for img in board.get("images", []):
            if img.get("id") == approval.get("image_id"):
                return img
    # History-only export is allowed, but never invent an approval.
    return None


def _copy_approved(image: Optional[dict[str, Any]], dest_dir: Path) -> Optional[str]:
    if not image:
        return None
    src = Path(image["path"])
    if not src.is_file():
        return None
    dest = dest_dir / f"approved_{src.name}"
    shutil.copy2(src, dest)
    return str(dest)


def _stamp(board: dict) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in (board.get("title") or "board"))
    return f"{safe.strip('-')[:48] or 'board'}-{int(time.time())}"


def build_bundle(board: dict[str, Any], approved_path: Optional[str]) -> dict[str, Any]:
    return {
        "schema": "creative-review/export/v1",
        "exported_at": time.time(),
        "board": {
            "id": board.get("id"),
            "title": board.get("title"),
            "status": board.get("status"),
            "created_at": board.get("created_at"),
        },
        "approved_image_id": ((board.get("approval") or {}).get("image_id")
                              if (board.get("approval") or {}).get("decision") == "approved" else None),
        "approved_export_path": approved_path,
        "images": [
            {
                "id": im.get("id"),
                "role": im.get("role"),
                "label": im.get("label"),
                "path": im.get("path"),
                "parent_id": im.get("parent_id"),
                "created_at": im.get("created_at"),
                "exists": im.get("exists"),
                "annotations": [
                    {"number": a.get("number"), "x": a.get("x"), "y": a.get("y"),
                     "note": a.get("note"), "author": a.get("author")}
                    for a in im.get("annotations", [])
                ],
            }
            for im in board.get("images", [])
        ],
        "revisions": board.get("revisions", []),
        "approval": board.get("approval"),
    }


def _render_markdown(board: dict[str, Any], bundle: dict[str, Any]) -> str:
    out: list[str] = []
    out.append(f'# Creative Review — {board.get("title", "Untitled")}')
    out.append("")
    out.append(f'- Board id: `{board.get("id")}`')
    out.append(f'- Status: **{board.get("status")}**')
    if bundle.get("approved_export_path"):
        out.append(f'- Approved image: `{bundle["approved_export_path"]}`')
    out.append("")
    out.append("## Version history")
    out.append("")
    out.append("| # | id | role | label | parent | annotations |")
    out.append("|---|---|---|---|---|---|")
    for i, im in enumerate(board.get("images", []), 1):
        out.append("| {} | `{}` | {} | {} | {} | {} |".format(
            i, im.get("id"), im.get("role"), im.get("label") or "",
            im.get("parent_id") or "—", len(im.get("annotations", []))))
    out.append("")
    out.append("## Feedback markers")
    out.append("")
    for im in board.get("images", []):
        anns = im.get("annotations", [])
        if not anns:
            continue
        out.append(f'### {im.get("label") or im.get("id")}')
        for a in anns:
            out.append(f'- **{a.get("number")}.** ({round(float(a.get("x", 0)) * 100, 1)}%, '
                       f'{round(float(a.get("y", 0)) * 100, 1)}%) — {a.get("note") or ""}')
        out.append("")
    approval = board.get("approval")
    if approval:
        out.append("## Decision")
        out.append("")
        out.append(f'- **{approval.get("decision")}** on image `{approval.get("image_id")}`')
        out.append("")
    return "\n".join(out)


def export_board(board: dict[str, Any], fmt: str = "json",
                 out_dir: Optional[str] = None) -> dict[str, Any]:
    dest = _export_dir(out_dir) / f"{_stamp(board)}-{uuid.uuid4().hex[:12]}"
    dest.mkdir()
    approved = _approved_image(board)
    approved_path = _copy_approved(approved, dest)
    stamp = _stamp(board)
    written: list[str] = []

    if fmt == "markdown":
        bundle = build_bundle(board, approved_path)
        path = dest / f"{stamp}.md"
        path.write_text(_render_markdown(board, bundle), encoding="utf-8")
        written.append(str(path))
    else:
        bundle = build_bundle(board, approved_path)
        path = dest / f"{stamp}.json"
        path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
        written.append(str(path))

    return {
        "ok": True,
        "format": fmt,
        "written": written,
        "approved_image_export": approved_path,
        "export_dir": str(dest),
    }