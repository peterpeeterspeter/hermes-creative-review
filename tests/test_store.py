"""Unit tests for store.py — persistence, annotation numbering, lineage, approval."""
from __future__ import annotations

import unittest

from _helpers import load, make_png

store = load("store")

import pathlib
import tempfile


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="cr-store-"))
        self.img = make_png(self.tmp / "hero.png")
        self.ref = make_png(self.tmp / "ref.png")
        self.board = store.create_board("Test board")
        self.board_id = self.board["id"]

    def test_create_and_list_board(self):
        self.assertTrue(self.board_id.startswith("board_"))
        boards = [b for b in store.list_boards() if b["id"] == self.board_id]
        self.assertEqual(len(boards), 1)
        self.assertEqual(boards[0]["title"], "Test board")
        self.assertEqual(boards[0]["image_count"], 0)

    def test_add_reference_and_generated_with_lineage(self):
        ref = store.add_image(self.board_id, str(self.ref), role="reference", label="ref")
        v1 = store.add_image(self.board_id, str(self.img), role="generated", label="v1")
        v2 = store.add_image(self.board_id, str(self.img), role="generated",
                             label="v2", parent_id=v1["id"])
        board = store.get_board(self.board_id)
        self.assertEqual(len(board["images"]), 3)
        self.assertEqual(ref["role"], "reference")
        self.assertEqual(v2["parent_id"], v1["id"])
        self.assertTrue(all(im["exists"] for im in board["images"]))

    def test_add_image_missing_file_is_rejected(self):
        with self.assertRaises(FileNotFoundError):
            store.add_image(self.board_id, str(self.tmp / "nope.png"))

    def test_add_image_unsupported_extension(self):
        bad = self.tmp / "notes.txt"
        bad.write_text("hi")
        with self.assertRaises(ValueError):
            store.add_image(self.board_id, str(bad))

    def test_annotation_numbering_and_coordinate_clamp(self):
        img = store.add_image(self.board_id, str(self.img))
        a1 = store.add_annotation(img["id"], 0.25, 0.5, note="first")
        a2 = store.add_annotation(img["id"], 1.5, -0.3, note="clamped")
        self.assertEqual(a1["number"], 1)
        self.assertEqual(a2["number"], 2)
        self.assertEqual(a2["x"], 1.0)
        self.assertEqual(a2["y"], 0.0)

    def test_update_and_delete_annotation(self):
        img = store.add_image(self.board_id, str(self.img))
        a = store.add_annotation(img["id"], 0.1, 0.1, note="old")
        updated = store.update_annotation(a["id"], note="new")
        self.assertEqual(updated["note"], "new")
        self.assertTrue(store.delete_annotation(a["id"]))
        self.assertFalse(store.delete_annotation(a["id"]))

    def test_revision_lineage_link(self):
        v1 = store.add_image(self.board_id, str(self.img), role="generated")
        store.create_revision(self.board_id, v1["id"], "brief text")
        v2 = store.add_image(self.board_id, str(self.img), role="generated", parent_id=v1["id"])
        store.link_revision_child(self.board_id, v1["id"], v2["id"])
        board = store.get_board(self.board_id)
        self.assertEqual(board["revisions"][0]["child_image_id"], v2["id"])
        self.assertEqual(board["revisions"][0]["delivered"], 1)

    def test_approval_promotes_role_and_closes_board(self):
        img = store.add_image(self.board_id, str(self.img), role="generated")
        approval = store.set_approval(self.board_id, img["id"], "approved")
        self.assertEqual(approval["decision"], "approved")
        board = store.get_board(self.board_id)
        self.assertEqual(board["status"], "approved")
        promoted = next(im for im in board["images"] if im["id"] == img["id"])
        self.assertEqual(promoted["role"], "approved")

    def test_read_image_data_url(self):
        img = store.add_image(self.board_id, str(self.img))
        data = store.read_image_data_url(img["id"])
        self.assertTrue(data["ok"])
        self.assertTrue(data["data_url"].startswith("data:image/png;base64,"))

    def test_unknown_board_raises(self):
        with self.assertRaises(ValueError):
            store.add_image("board_missing", str(self.img))

    def test_foreign_parent_is_rejected(self):
        other = store.create_board("Other")["id"]
        foreign = store.add_image(other, str(self.img), role="generated")
        with self.assertRaises(ValueError):
            store.add_image(self.board_id, str(self.img), parent_id=foreign["id"])

    def test_reapproving_demotes_the_earlier_pick(self):
        v1 = store.add_image(self.board_id, str(self.img), role="generated", label="v1")
        v2 = store.add_image(self.board_id, str(self.img), role="generated", label="v2")
        store.set_approval(self.board_id, v1["id"], "approved")
        store.set_approval(self.board_id, v2["id"], "approved")
        roles = {im["id"]: im["role"] for im in store.get_board(self.board_id)["images"]}
        self.assertEqual(roles[v2["id"]], "approved")
        self.assertNotEqual(roles[v1["id"]], "approved")

    def test_rejection_clears_any_approved_role(self):
        v1 = store.add_image(self.board_id, str(self.img), role="generated")
        store.set_approval(self.board_id, v1["id"], "approved")
        store.set_approval(self.board_id, v1["id"], "rejected")
        board = store.get_board(self.board_id)
        self.assertEqual(board["status"], "rejected")
        self.assertNotEqual(
            next(im for im in board["images"] if im["id"] == v1["id"])["role"], "approved")

    def test_read_image_bytes_returns_raw_bytes(self):
        img = store.add_image(self.board_id, str(self.img))
        data = store.read_image_bytes(img["id"])
        self.assertTrue(data["ok"])
        self.assertEqual(data["mime"], "image/png")
        self.assertEqual(data["bytes"][:8], b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()