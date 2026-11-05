"""Creative Review — local-first persistence.

Every board, image reference, annotation, revision and approval lives in one
SQLite database under the profile's plugin-data root
(``<HERMES_HOME>/plugin-data/creative-review/``), provided by
``plugins.plugin_storage.plugin_db``. That home survives ``hermes plugins
update`` and ``remove`` and follows the active profile, so nothing the user
creates is lost and nothing is written into the install tree.

Image *bytes* are never copied into the database: a row stores the absolute
path the user (or the agent) registered. The backend reads those bytes on
demand and hands them to the Desktop pane as a data URL, so images stay on the
user's own disk and no network call is ever made.
"""
from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

PLUGIN_ID = "creative-review"

# Largest image we will read into memory (also the data-URL ceiling).
MAX_IMAGE_BYTES = 40 * 1024 * 1024

# Roles an image row can carry.
ROLE_REFERENCE = "reference"
ROLE_GENERATED = "generated"
ROLE_APPROVED = "approved"
VALID_ROLES = {ROLE_REFERENCE, ROLE_GENERATED, ROLE_APPROVED}

# Extensions we accept and can serve back as a data URL.
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".avif"}
_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".avif": "image/avif",
}

# One connection per (thread, database path) — see `_connect`.
_local = threading.local()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS boards (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    meta        TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS images (
    id          TEXT PRIMARY KEY,
    board_id    TEXT NOT NULL,
    path        TEXT NOT NULL,
    role        TEXT NOT NULL,
    label       TEXT NOT NULL DEFAULT '',
    parent_id   TEXT,
    created_at  REAL NOT NULL,
    meta        TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS annotations (
    id          TEXT PRIMARY KEY,
    image_id    TEXT NOT NULL,
    number      INTEGER NOT NULL,
    x           REAL NOT NULL,
    y           REAL NOT NULL,
    w           REAL,
    h           REAL,
    note        TEXT NOT NULL DEFAULT '',
    author      TEXT NOT NULL DEFAULT 'user',
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS revisions (
    id              TEXT PRIMARY KEY,
    board_id        TEXT NOT NULL,
    parent_image_id TEXT,
    child_image_id  TEXT,
    brief           TEXT NOT NULL,
    delivered       INTEGER NOT NULL DEFAULT 0,
    created_at      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    board_id    TEXT PRIMARY KEY,
    image_id    TEXT NOT NULL,
    decision    TEXT NOT NULL,
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_images_board ON images(board_id);
CREATE INDEX IF NOT EXISTS idx_images_parent ON images(parent_id);
CREATE INDEX IF NOT EXISTS idx_annotations_image ON annotations(image_id);
CREATE INDEX IF NOT EXISTS idx_revisions_board ON revisions(board_id);
"""


def _now() -> float:
    return time.time()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _connect() -> sqlite3.Connection:
    """Open this thread's connection to the active profile's DB, schema once.

    One connection per (thread, database path): threads must not share a SQLite
    connection while the FastAPI thread pool writes concurrently, and keying on
    the resolved path (not just the plugin) keeps a multiplexed gateway honest —
    a profile switch opens the new profile's file instead of reusing the old one.
    """
    from plugins.plugin_storage import plugin_data_dir, plugin_db

    path = str(plugin_data_dir(PLUGIN_ID) / "data.db")
    cache = getattr(_local, "conns", None)
    if cache is None:
        cache = {}
        _local.conns = cache
    conn = cache.get(path)
    if conn is None:
        conn = plugin_db(PLUGIN_ID)
        conn.row_factory = sqlite3.Row
        # Wait rather than raise when the agent half and the backend half write at
        # the same moment (separate processes, one WAL database).
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.executescript(_SCHEMA)
        cache[path] = conn
    return conn


def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    data = dict(row)
    for key in ("meta",):
        if key in data and isinstance(data[key], str):
            try:
                data[key] = json.loads(data[key])
            except (TypeError, ValueError):
                data[key] = {}
    return data


# --------------------------------------------------------------------------- #
# Boards
# --------------------------------------------------------------------------- #
def create_board(title: str, meta: Optional[dict] = None) -> dict[str, Any]:
    board_id = _new_id("board")
    now = _now()
    conn = _connect()
    with conn:
        conn.execute(
            "INSERT INTO boards(id, title, status, created_at, updated_at, meta)"
            " VALUES(?,?,?,?,?,?)",
            (board_id, title.strip() or "Untitled review", "open", now, now,
             json.dumps(meta or {})),
        )
    return get_board(board_id)  # type: ignore[return-value]


def list_boards() -> list[dict[str, Any]]:
    conn = _connect()
    rows = conn.execute(
        "SELECT b.*, "
        " (SELECT COUNT(*) FROM images i WHERE i.board_id = b.id) AS image_count,"
        " (SELECT COUNT(*) FROM annotations a JOIN images i ON a.image_id = i.id"
        "   WHERE i.board_id = b.id) AS annotation_count,"
        " ap.image_id AS approved_image_id"
        " FROM boards b LEFT JOIN approvals ap ON ap.board_id = b.id"
        " ORDER BY b.updated_at DESC"
    ).fetchall()
    return [d for d in (_row_to_dict(r) for r in rows) if d is not None]


def get_board(board_id: str) -> Optional[dict[str, Any]]:
    conn = _connect()
    board = _row_to_dict(conn.execute(
        "SELECT * FROM boards WHERE id = ?", (board_id,)).fetchone())
    if board is None:
        return None
    images = [d for d in
              (_row_to_dict(r) for r in conn.execute(
                  "SELECT * FROM images WHERE board_id = ? ORDER BY created_at",
                  (board_id,)).fetchall()) if d is not None]
    annotations: dict[str, list] = {}
    for r in conn.execute(
            "SELECT a.* FROM annotations a JOIN images i ON a.image_id = i.id"
            " WHERE i.board_id = ? ORDER BY a.number", (board_id,)).fetchall():
        annotations.setdefault(r["image_id"], []).append(_row_to_dict(r))
    for img in images:
        img["annotations"] = annotations.get(img["id"], [])
        img["exists"] = Path(img["path"]).is_file()
    board["images"] = images
    board["revisions"] = [
        _row_to_dict(r) for r in conn.execute(
            "SELECT * FROM revisions WHERE board_id = ? ORDER BY created_at",
            (board_id,)).fetchall()]
    board["approval"] = _row_to_dict(conn.execute(
        "SELECT * FROM approvals WHERE board_id = ?", (board_id,)).fetchone())
    return board


def touch_board(board_id: str) -> None:
    conn = _connect()
    with conn:
        conn.execute("UPDATE boards SET updated_at = ? WHERE id = ?", (_now(), board_id))


def set_board_status(board_id: str, status: str) -> None:
    conn = _connect()
    with conn:
        conn.execute("UPDATE boards SET status = ?, updated_at = ? WHERE id = ?",
                     (status, _now(), board_id))


# --------------------------------------------------------------------------- #
# Images
# --------------------------------------------------------------------------- #
def describe_path(path: str) -> dict[str, Any]:
    """Validate and describe a local image path without copying it."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        raise ValueError("image path must be absolute")
    p = p.resolve()
    exists = p.is_file()
    ext = p.suffix.lower()
    return {
        "path": str(p),
        "exists": exists,
        "extension": ext,
        "supported": ext in IMAGE_EXTENSIONS,
        "size": p.stat().st_size if exists else None,
    }


def add_image(board_id: str, path: str, role: str = ROLE_GENERATED,
              label: str = "", parent_id: Optional[str] = None,
              meta: Optional[dict] = None) -> dict[str, Any]:
    if role not in {ROLE_REFERENCE, ROLE_GENERATED}:
        raise ValueError("import role must be reference or generated; approve separately")
    if get_board(board_id) is None:
        raise ValueError(f"unknown board: {board_id}")
    if parent_id:
        parent = get_image(parent_id)
        if parent is None:
            raise ValueError(f"unknown parent image: {parent_id}")
        if parent["board_id"] != board_id:
            raise ValueError(f"parent image {parent_id} belongs to another board")
    info = describe_path(path)
    if not info["exists"]:
        raise FileNotFoundError(f"image file not found: {info['path']}")
    if not info["supported"]:
        raise ValueError(f"unsupported image extension: {info['extension'] or '(none)'}")
    _validated_bytes(Path(info["path"]), MAX_IMAGE_BYTES)
    image_id = _new_id("img")
    conn = _connect()
    with conn:
        conn.execute(
            "INSERT INTO images(id, board_id, path, role, label, parent_id,"
            " created_at, meta) VALUES(?,?,?,?,?,?,?,?)",
            (image_id, board_id, info["path"], role, label or Path(info["path"]).name,
             parent_id, _now(), json.dumps(meta or {})),
        )
    touch_board(board_id)
    return _row_to_dict(conn.execute(
        "SELECT * FROM images WHERE id = ?", (image_id,)).fetchone())  # type: ignore[return-value]


def get_image(image_id: str) -> Optional[dict[str, Any]]:
    conn = _connect()
    img = _row_to_dict(conn.execute(
        "SELECT * FROM images WHERE id = ?", (image_id,)).fetchone())
    if img:
        img["annotations"] = [_row_to_dict(r) for r in conn.execute(
            "SELECT * FROM annotations WHERE image_id = ? ORDER BY number",
            (image_id,)).fetchall()]
        img["exists"] = Path(img["path"]).is_file()
    return img


def lineage(board_id: str) -> list[dict[str, Any]]:
    """Return the board's images ordered oldest→newest with parent links."""
    conn = _connect()
    return [_row_to_dict(r) for r in conn.execute(
        "SELECT id, parent_id, role, label, path, created_at FROM images"
        " WHERE board_id = ? ORDER BY created_at", (board_id,)).fetchall()]


# --------------------------------------------------------------------------- #
# Annotations
# --------------------------------------------------------------------------- #
def _next_annotation_number(conn: sqlite3.Connection, image_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(number), 0) AS n FROM annotations WHERE image_id = ?",
        (image_id,)).fetchone()
    return int(row["n"]) + 1


def add_annotation(image_id: str, x: float, y: float, note: str = "",
                   author: str = "user", w: Optional[float] = None,
                   h: Optional[float] = None) -> dict[str, Any]:
    image = get_image(image_id)
    if image is None:
        raise ValueError(f"unknown image: {image_id}")
    x = _coordinate(x)
    y = _coordinate(y)
    conn = _connect()
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        number = _next_annotation_number(conn, image_id)
        ann_id = _new_id("ann")
        conn.execute(
            "INSERT INTO annotations(id, image_id, number, x, y, w, h, note,"
            " author, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (ann_id, image_id, number, x, y, w, h, note, author, _now()),
        )
    touch_board(image["board_id"])
    return _row_to_dict(conn.execute(
        "SELECT * FROM annotations WHERE id = ?", (ann_id,)).fetchone())  # type: ignore[return-value]


def update_annotation(ann_id: str, note: Optional[str] = None,
                      x: Optional[float] = None, y: Optional[float] = None) -> Optional[dict]:
    conn = _connect()
    fields, params = [], []
    if note is not None:
        fields.append("note = ?")
        params.append(note)
    if x is not None:
        fields.append("x = ?")
        params.append(_coordinate(x))
    if y is not None:
        fields.append("y = ?")
        params.append(_coordinate(y))
    if not fields:
        return _row_to_dict(conn.execute(
            "SELECT * FROM annotations WHERE id = ?", (ann_id,)).fetchone())
    params.append(ann_id)
    with conn:
        conn.execute(f"UPDATE annotations SET {', '.join(fields)} WHERE id = ?", params)
    return _row_to_dict(conn.execute(
        "SELECT * FROM annotations WHERE id = ?", (ann_id,)).fetchone())


def delete_annotation(ann_id: str) -> bool:
    conn = _connect()
    with conn:
        cur = conn.execute("DELETE FROM annotations WHERE id = ?", (ann_id,))
    return cur.rowcount > 0


# --------------------------------------------------------------------------- #
# Revisions
# --------------------------------------------------------------------------- #
def create_revision(board_id: str, parent_image_id: Optional[str], brief: str,
                    child_image_id: Optional[str] = None) -> dict[str, Any]:
    require_board_image(board_id, parent_image_id)
    if child_image_id:
        require_board_image(board_id, child_image_id)
    rev_id = _new_id("rev")
    conn = _connect()
    with conn:
        conn.execute(
            "INSERT INTO revisions(id, board_id, parent_image_id, child_image_id,"
            " brief, delivered, created_at) VALUES(?,?,?,?,?,?,?)",
            (rev_id, board_id, parent_image_id, child_image_id, brief, 0, _now()),
        )
    touch_board(board_id)
    return _row_to_dict(conn.execute(
        "SELECT * FROM revisions WHERE id = ?", (rev_id,)).fetchone())  # type: ignore[return-value]


def mark_revision_delivered(rev_id: str) -> None:
    conn = _connect()
    with conn:
        cursor = conn.execute("UPDATE revisions SET delivered = 1 WHERE id = ?", (rev_id,))
        if not cursor.rowcount:
            raise ValueError(f"unknown revision: {rev_id}")


def link_revision_child(board_id: str, parent_image_id: str, child_image_id: str) -> None:
    """Attach a newly registered child image to the newest open revision."""
    require_board_image(board_id, parent_image_id)
    child = require_board_image(board_id, child_image_id)
    if child["parent_id"] != parent_image_id:
        raise ValueError("revision child does not descend from this parent")
    conn = _connect()
    with conn:
        conn.execute(
            "UPDATE revisions SET child_image_id = ?, delivered = 1"
            " WHERE id = (SELECT id FROM revisions WHERE board_id = ?"
            "   AND parent_image_id = ? AND child_image_id IS NULL"
            "   ORDER BY created_at DESC LIMIT 1)",
            (child_image_id, board_id, parent_image_id),
        )


# --------------------------------------------------------------------------- #
# Approvals
# --------------------------------------------------------------------------- #
def set_approval(board_id: str, image_id: str, decision: str) -> dict[str, Any]:
    if decision not in {"approved", "rejected"}:
        raise ValueError("decision must be approved or rejected")
    require_board_image(board_id, image_id)
    conn = _connect()
    with conn:
        conn.execute(
            "INSERT INTO approvals(board_id, image_id, decision, created_at)"
            " VALUES(?,?,?,?) ON CONFLICT(board_id) DO UPDATE SET"
            " image_id = excluded.image_id, decision = excluded.decision,"
            " created_at = excluded.created_at",
            (board_id, image_id, decision, _now()),
        )
        conn.execute("UPDATE boards SET status = ?, updated_at = ? WHERE id = ?",
                     ("approved" if decision == "approved" else "rejected",
                      _now(), board_id))
        # Exactly one image on a board is 'approved': promote the chosen one and
        # demote any earlier pick, so re-approving a different version never
        # leaves two rows claiming to be the final image.
        conn.execute("UPDATE images SET role = ? WHERE board_id = ? AND role = ?",
                     (ROLE_GENERATED, board_id, ROLE_APPROVED))
        if decision == "approved":
            conn.execute("UPDATE images SET role = ? WHERE id = ?",
                         (ROLE_APPROVED, image_id))
    return _row_to_dict(conn.execute(
        "SELECT * FROM approvals WHERE board_id = ?", (board_id,)).fetchone())  # type: ignore[return-value]


def get_approval(board_id: str) -> Optional[dict[str, Any]]:
    conn = _connect()
    return _row_to_dict(conn.execute(
        "SELECT * FROM approvals WHERE board_id = ?", (board_id,)).fetchone())


# --------------------------------------------------------------------------- #
# Image bytes (on-demand, local only)
# --------------------------------------------------------------------------- #
def require_board_image(board_id: str, image_id: Optional[str]) -> dict[str, Any]:
    if get_board(board_id) is None:
        raise ValueError(f"unknown board: {board_id}")
    image = get_image(image_id or "")
    if image is None:
        raise ValueError(f"unknown image: {image_id}")
    if image["board_id"] != board_id:
        raise ValueError("image belongs to another board")
    return image


def _coordinate(value: float) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("coordinate must be finite")
    return min(max(value, 0.0), 1.0)


def _validated_bytes(path: Path, limit: int) -> bytes:
    # Read at most limit+1, not stat then an unbounded read (file may grow).
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("image exceeds size limit")
    ext = path.suffix.lower()
    signatures = {
        ".png": raw.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": raw.startswith(b"\xff\xd8\xff"),
        ".jpeg": raw.startswith(b"\xff\xd8\xff"),
        ".gif": raw[:6] in {b"GIF87a", b"GIF89a"},
        ".bmp": raw.startswith(b"BM"),
        ".webp": raw[:4] == b"RIFF" and raw[8:12] == b"WEBP",
        ".avif": raw[4:8] == b"ftyp" and any(raw[n:n+4] in {b"avif", b"avis"} for n in range(8, min(len(raw), 64), 4)),
    }
    if not signatures.get(ext, False):
        raise ValueError("file signature does not match a supported image format")
    return raw


def read_image_bytes(image_id: str, max_bytes: int = MAX_IMAGE_BYTES) -> dict[str, Any]:
    """Read one registered image's bytes from disk. Local only, never network."""
    image = get_image(image_id)
    if image is None:
        return {"ok": False, "error": "unknown image"}
    path = Path(image["path"])
    if not path.is_file():
        return {"ok": False, "error": "missing-file",
                "message": f"file no longer exists: {path}"}
    size = path.stat().st_size
    if size > max_bytes:
        return {"ok": False, "error": "too-large",
                "message": f"image is {size} bytes (limit {max_bytes})"}
    mime = _MIME.get(path.suffix.lower())
    if mime is None:
        return {"ok": False, "error": "unsupported",
                "message": f"unsupported extension {path.suffix}"}
    try:
        raw = _validated_bytes(path, max_bytes)
    except ValueError as exc:
        return {"ok": False, "error": "invalid-image", "message": str(exc)}
    return {"ok": True, "mime": mime, "size": len(raw), "bytes": raw}


def read_image_data_url(image_id: str, max_bytes: int = MAX_IMAGE_BYTES) -> dict[str, Any]:
    import base64

    data = read_image_bytes(image_id, max_bytes=max_bytes)
    if not data.get("ok"):
        return data
    b64 = base64.b64encode(data["bytes"]).decode("ascii")
    return {"ok": True, "mime": data["mime"], "size": data["size"],
            "data_url": f"data:{data['mime']};base64,{b64}"}