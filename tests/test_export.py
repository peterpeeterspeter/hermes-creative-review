"""Unit tests for export.py — JSON/Markdown export and the approved-image copy."""
from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from _helpers import load, make_png

store = load("store")
export = load("export")


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="cr-export-"))
        self.img = make_png(self.tmp / "hero.png")
        self.board_id = store.create_board("Export me")["id"]
        self.image = store.add_image(self.board_id, str(self.img), role="generated", label="v1")
        store.add_annotation(self.image["id"], 0.3, 0.4, note="fix the strap")
        store.set_approval(self.board_id, self.image["id"], "approved")

    def test_export_json_bundle_and_image_copy(self):
        board = store.get_board(self.board_id)
        out = self.tmp / "out"
        result = export.export_board(board, fmt="json", out_dir=str(out))
        self.assertTrue(result["ok"])
        written = pathlib.Path(result["written"][0])
        self.assertTrue(written.is_file())
        bundle = json.loads(written.read_text())
        self.assertEqual(bundle["schema"], "creative-review/export/v1")
        self.assertEqual(bundle["approved_image_id"], self.image["id"])
        self.assertTrue(pathlib.Path(result["approved_image_export"]).is_file())

    def test_export_markdown_report(self):
        board = store.get_board(self.board_id)
        out = self.tmp / "out"
        result = export.export_board(board, fmt="markdown", out_dir=str(out))
        text = pathlib.Path(result["written"][0]).read_text()
        self.assertIn("# Creative Review — Export me", text)
        self.assertIn("fix the strap", text)
        self.assertIn("approved", text.lower())

    def test_missing_image_is_skipped_not_fatal(self):
        loose = store.add_image(self.board_id, str(self.img), role="reference", label="ref")
        pathlib.Path(loose["path"]).unlink()
        board = store.get_board(self.board_id)
        result = export.export_board(board, fmt="json", out_dir=str(self.tmp / "out2"))
        self.assertTrue(result["ok"])  # export still succeeds; approved copy still made


if __name__ == "__main__":
    unittest.main()