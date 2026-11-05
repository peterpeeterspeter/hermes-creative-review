"""Structured revision brief — the contract between the review pane and the agent.

``build_brief`` turns a board + a selected image + its point annotations into
two things at once:

* a ``markdown`` string the user can read and that is sent into the live
  Hermes conversation (the pane's "Request Revision" action hands it to
  ``host.composer.submit``), and
* a machine-readable ``dict`` the agent tool and any exporter consume.

Both halves of the plugin import this module, so the wording the user sees and
the wording the agent receives can never drift apart.
"""
from __future__ import annotations

from typing import Any, Optional


def _pct(value: float) -> str:
    return f"{round(float(value) * 100, 1)}%"


def build_brief(board: dict[str, Any], image: dict[str, Any],
                reference: Optional[dict[str, Any]] = None,
                overall_note: str = "") -> dict[str, Any]:
    annotations = sorted(image.get("annotations", []), key=lambda a: a.get("number", 0))
    revisions = board.get("revisions", [])

    markers = [
        {
            "number": a.get("number"),
            "x": round(float(a.get("x", 0)), 4),
            "y": round(float(a.get("y", 0)), 4),
            "note": (a.get("note") or "").strip(),
        }
        for a in annotations
    ]

    lines: list[str] = []
    lines.append(f'Revision request — review board "{board.get("title", "Untitled")}"')
    lines.append(f'(board_id: {board.get("id")})')
    lines.append("")
    lines.append(f'Selected image: {image.get("label") or image.get("path")} '
                 f'(image_id: {image.get("id")}, role: {image.get("role")})')
    lines.append(f'File: {image.get("path")}')
    if reference:
        lines.append(f'Reference image: {reference.get("label") or reference.get("path")} '
                     f'(image_id: {reference.get("id")}) — treat it as the target style/composition.')
        lines.append(f'Reference file: {reference.get("path")}')
    if image.get("parent_id"):
        parent = next((im for im in board.get("images", [])
                       if im.get("id") == image.get("parent_id")), None)
        tag = parent.get("label") if parent else image.get("parent_id")
        lines.append(f'This image is a revision of: {tag} (parent_id: {image.get("parent_id")})')
    lines.append(f'Revision number: {sum(1 for r in revisions if r.get("child_image_id")) + 1}')
    lines.append("")

    if markers:
        lines.append("Feedback markers (coordinates are % of the image, origin top-left):")
        for m in markers:
            note = m["note"] or "(no note)"
            lines.append(f'  {m["number"]}. ({_pct(m["x"])}, {_pct(m["y"])}) — {note}')
    else:
        lines.append("Feedback markers: none — this revision is driven by the overall request below.")
    lines.append("")

    if overall_note.strip():
        lines.append(f'Overall request: {overall_note.strip()}')
        lines.append("")

    lines.append("Please produce a revised image that addresses every marker above, keeping")
    lines.append("everything not called out unchanged. Then register the new image against this")
    lines.append("board and link it to the image you revised:")
    lines.append("")
    lines.append("  creative_review_add_image(")
    lines.append(f'      board_id="{image.get("board_id") or board.get("id")}",')
    lines.append('      path="<absolute path to the new image>",')
    lines.append('      role="generated",')
    lines.append(f'      parent_id="{image.get("id")}")')
    lines.append("")
    lines.append("After registering it the user can review the new version in the Creative Review pane.")

    markdown = "\n".join(lines)

    return {
        "board_id": board.get("id"),
        "board_title": board.get("title"),
        "image_id": image.get("id"),
        "image_label": image.get("label"),
        "image_path": image.get("path"),
        "parent_image_id": image.get("parent_id"),
        "reference_image_id": reference.get("id") if reference else None,
        "reference_image_path": reference.get("path") if reference else None,
        "marker_count": len(markers),
        "markers": markers,
        "overall_note": overall_note.strip(),
        "markdown": markdown,
    }