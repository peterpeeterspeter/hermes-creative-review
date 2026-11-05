"""Unit tests for brief.py — the structured revision brief."""
from __future__ import annotations

import unittest

from _helpers import load

brief = load("brief")


def _board():
    return {
        "id": "board_x",
        "title": "Hero shot",
        "images": [
            {"id": "img_ref", "role": "reference", "label": "reference", "path": "/r.png"},
            {"id": "img_p", "role": "generated", "label": "v1", "path": "/p.png"},
            {"id": "img_c", "role": "generated", "label": "v2", "path": "/c.png",
             "parent_id": "img_p",
             "annotations": [
                 {"number": 2, "x": 0.7, "y": 0.12, "note": "remove the logo"},
                 {"number": 1, "x": 0.32, "y": 0.41, "note": "make the buckle gold"},
             ]},
        ],
        "revisions": [{"child_image_id": "img_c"}],
    }


class BriefTests(unittest.TestCase):
    def test_markers_sorted_and_formatted(self):
        board = _board()
        image = board["images"][2]
        reference = board["images"][0]
        data = brief.build_brief(board, image, reference=reference, overall_note="warmer light")
        self.assertEqual(data["marker_count"], 2)
        self.assertEqual([m["number"] for m in data["markers"]], [1, 2])
        self.assertIn("(32.0%, 41.0%)", data["markdown"])
        self.assertIn("make the buckle gold", data["markdown"])
        self.assertIn("warmer light", data["markdown"])

    def test_brief_names_lineage_and_reference(self):
        board = _board()
        image = board["images"][2]
        data = brief.build_brief(board, image, reference=board["images"][0])
        self.assertEqual(data["parent_image_id"], "img_p")
        self.assertIn("v1", data["markdown"])
        self.assertIn("reference", data["markdown"])

    def test_brief_instructs_parent_linked_registration(self):
        board = _board()
        image = board["images"][2]
        data = brief.build_brief(board, image)
        self.assertIn("creative_review_add_image", data["markdown"])
        self.assertIn('parent_id="img_c"', data["markdown"])
        self.assertIn('board_id="board_x"', data["markdown"])

    def test_no_markers_says_so(self):
        board = _board()
        image = {"id": "img_solo", "board_id": "board_x", "role": "generated",
                 "label": "solo", "path": "/s.png", "annotations": []}
        data = brief.build_brief(board, image, overall_note="start over")
        self.assertEqual(data["marker_count"], 0)
        self.assertIn("none", data["markdown"].lower())


if __name__ == "__main__":
    unittest.main()