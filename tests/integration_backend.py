"""Backend integration test — drives the real ASGI app the gateway mounts.

Run with Hermes' own venv python:

    PYTHONPATH=~/.hermes/hermes-agent \\
    ~/.hermes/hermes-agent/venv/bin/python tests/integration_backend.py

It loads ``dashboard/plugin_api.py`` exactly the way Hermes does (by path,
standalone), mounts its router under ``/api/plugins/creative-review`` and
exercises every route end to end against the real plugin DB.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

REPO = pathlib.Path.home() / ".hermes" / "hermes-agent"
if REPO.is_dir() and str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PLUGIN_DIR = pathlib.Path(__file__).resolve().parent.parent
API_PATH = PLUGIN_DIR / "dashboard" / "plugin_api.py"

# Load exactly as the gateway does: standalone, by path.
spec = importlib.util.spec_from_file_location(
    "hermes_dashboard_plugin_creative_review", API_PATH)
assert spec is not None and spec.loader is not None
api = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = api
spec.loader.exec_module(api)

app = FastAPI()
app.include_router(api.router, prefix="/api/plugins/creative-review")
client = TestClient(app)

PASS, FAIL = 0, 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label} {detail}")


def main() -> int:
    print("Creative Review — backend integration\n")

    r = client.get("/api/plugins/creative-review/health")
    check("health", r.status_code == 200 and r.json()["plugin"] == "creative-review")

    # Cross-process persistence: the board the live agent created earlier.
    boards = client.get("/api/plugins/creative-review/boards").json()["boards"]
    live = [b for b in boards if b["title"] == "Live E2E review"]
    check("persistence: live-agent board survives in a new process", len(live) >= 1,
          f"(boards={[b['title'] for b in boards]})")

    board = client.post("/api/plugins/creative-review/boards",
                        json={"title": "Backend E2E"}).json()["board"]
    bid = board["id"]
    check("create board", bid.startswith("board_"))

    ref = client.post("/api/plugins/creative-review/image", json={
        "board_id": bid, "path": "/tmp/cr-e2e/reference.png", "role": "reference"}).json()
    check("register reference image", ref.get("ok") and ref["image"]["role"] == "reference")

    v1 = client.post("/api/plugins/creative-review/image", json={
        "board_id": bid, "path": "/tmp/cr-e2e/v1.png", "role": "generated",
        "label": "v1"}).json()["image"]

    missing = client.post("/api/plugins/creative-review/image", json={
        "board_id": bid, "path": "/tmp/cr-e2e/does-not-exist.png"}).json()
    check("missing file → clean error", missing.get("ok") is False
          and missing.get("reason") == "file-not-found")

    a1 = client.post("/api/plugins/creative-review/annotation", json={
        "image_id": v1["id"], "x": 0.25, "y": 0.5, "note": "make this gold"}).json()["annotation"]
    a2 = client.post("/api/plugins/creative-review/annotation", json={
        "image_id": v1["id"], "x": 0.7, "y": 0.1, "note": "remove the logo"}).json()["annotation"]
    check("annotation numbering", a1["number"] == 1 and a2["number"] == 2)
    check("annotation coordinates accurate", abs(a1["x"] - 0.25) < 1e-9 and abs(a1["y"] - 0.5) < 1e-9)

    board = client.get(f"/api/plugins/creative-review/board?board_id={bid}").json()["board"]
    v1b = next(im for im in board["images"] if im["id"] == v1["id"])
    check("board carries annotations", len(v1b["annotations"]) == 2)
    check("images exist on disk", all(im["exists"] for im in board["images"]))

    data = client.get(f"/api/plugins/creative-review/image-data?image_id={v1['id']}").json()
    check("image served as data URL", data.get("ok")
          and data["data_url"].startswith("data:image/png;base64,"))

    brief = client.post("/api/plugins/creative-review/revision", json={
        "board_id": bid, "image_id": v1["id"], "overall_note": "warmer light"}).json()
    md = brief["brief"]["markdown"]
    check("structured brief built", brief.get("ok") and brief["brief"]["marker_count"] == 2)
    check("brief names the coordinates", "(25.0%, 50.0%)" in md)
    check("brief carries the notes", "make this gold" in md and "remove the logo" in md)
    check("brief instructs parent-linked registration", 'parent_id="%s"' % v1["id"] in md)

    v2 = client.post("/api/plugins/creative-review/image", json={
        "board_id": bid, "path": "/tmp/cr-e2e/v2.png", "role": "generated",
        "label": "v2", "parent_id": v1["id"]}).json()["image"]
    board = client.get(f"/api/plugins/creative-review/board?board_id={bid}").json()["board"]
    rev = board["revisions"][0]
    check("revision lineage linked to child", rev["child_image_id"] == v2["id"])
    check("child records its parent", v2["parent_id"] == v1["id"])

    appr = client.post("/api/plugins/creative-review/approve", json={
        "board_id": bid, "image_id": v2["id"], "decision": "approved"}).json()
    check("approval recorded", appr.get("ok") and appr["approval"]["decision"] == "approved")

    exp = client.get(f"/api/plugins/creative-review/export?board_id={bid}&format=markdown").json()
    exported = pathlib.Path(exp["written"][0])
    check("export wrote a file", exp.get("ok") and exported.is_file())
    check("export copied the approved image",
          exp.get("approved_image_export") and pathlib.Path(exp["approved_image_export"]).is_file())
    check("export report has the feedback", "make this gold" in exported.read_text())

    bad = client.post("/api/plugins/creative-review/approve", json={
        "board_id": bid, "image_id": v2["id"], "decision": "maybe"}).json()
    check("invalid decision rejected", bad.get("ok") is False)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())