"""Unit tests for tools.py — the JSON contract every handler must honour."""
from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from _helpers import load, make_png

tools = load("tools")


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="cr-tools-"))
        self.img = make_png(self.tmp / "gen.png")

    def test_create_board_returns_json(self):
        out = json.loads(tools.create_board({"title": "Board A"}))
        self.assertTrue(out["ok"])
        self.assertTrue(out["board_id"].startswith("board_"))

    def test_create_board_requires_title(self):
        out = json.loads(tools.create_board({"title": "  "}))
        self.assertFalse(out["ok"])

    def test_add_image_and_get_board_roundtrip(self):
        board_id = json.loads(tools.create_board({"title": "B"}))["board_id"]
        added = json.loads(tools.add_image({"board_id": board_id, "path": str(self.img)}))
        self.assertTrue(added["ok"])
        board = json.loads(tools.get_board({"board_id": board_id}))["board"]
        self.assertEqual(len(board["images"]), 1)

    def test_add_image_missing_file_returns_error_not_raise(self):
        board_id = json.loads(tools.create_board({"title": "B"}))["board_id"]
        out = json.loads(tools.add_image({"board_id": board_id, "path": str(self.tmp / "x.png")}))
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "file-not-found")

    def test_revision_brief_creates_revision_record(self):
        board_id = json.loads(tools.create_board({"title": "B"}))["board_id"]
        img = json.loads(tools.add_image({"board_id": board_id, "path": str(self.img)}))["image"]
        out = json.loads(tools.revision_brief({"board_id": board_id, "image_id": img["id"]}))
        self.assertTrue(out["ok"])
        self.assertIn("Revision request", out["brief"]["markdown"])
        board = json.loads(tools.get_board({"board_id": board_id}))["board"]
        self.assertEqual(len(board["revisions"]), 1)

    def test_approve_and_export(self):
        board_id = json.loads(tools.create_board({"title": "B"}))["board_id"]
        img = json.loads(tools.add_image({"board_id": board_id, "path": str(self.img)}))["image"]
        approved = json.loads(tools.approve({"board_id": board_id, "image_id": img["id"]}))
        self.assertTrue(approved["ok"])
        exported = json.loads(tools.export_board(
            {"board_id": board_id, "format": "markdown", "out_dir": str(self.tmp / "out")}))
        self.assertTrue(exported["ok"])

    def test_unknown_ids_return_errors(self):
        self.assertFalse(json.loads(tools.get_board({"board_id": "nope"}))["ok"])
        self.assertFalse(json.loads(tools.approve(
            {"board_id": "nope", "image_id": "nope"}))["ok"])

    def test_every_handler_returns_a_json_string(self):
        for fn, args in (
            (tools.list_boards, {}),
            (tools.create_board, {"title": "Z"}),
            (tools.get_board, {"board_id": "nope"}),
        ):
            payload = fn(args)
            self.assertIsInstance(payload, str)
            json.loads(payload)  # must not raise


if __name__ == "__main__":
    unittest.main()