---
name: creative-review
description: "Use when reviewing, annotating or art-directing AI-generated images with the user — open a Creative Review board, add reference/generated images, read the user's numbered point feedback, and hand a precise revision brief back."
---

# Creative Review

Creative Review gives you an art director's desk: a local board where the user
compares a **reference** image against your **generated** images, drops numbered
point annotations, and asks for a precise revision. You drive the board through
seven tools; the user drives the visual review in the Desktop pane.

## The loop

1. **Generate**, then register. After you produce an image file (with any image
   tool), open or reuse a board and register the file:
   - `creative_review_create_board(title)` → `board_id`
   - `creative_review_add_image(board_id, path, role="generated")`
   - If the user gave a reference image, add it first with `role="reference"`.
2. **Tell the user** to open **Creative Review** (sidebar, ⌘K → "Open Creative
   Review", or the `review N` status-bar chip).
3. **The user annotates** in the pane and clicks **Request Revision**. That sends
   you a real user turn containing the structured brief (markers + notes + the
   selected image's path and id).
4. **Revise.** When you receive a revision brief, generate a new image that
   addresses every numbered marker, then register it **with the parent** so the
   lineage is recorded:
   `creative_review_add_image(board_id=…, path="<new file>", role="generated", parent_id="<the image_id you revised>")`
5. **Repeat** until the user clicks **Approve** (or tells you to). Approval is
   recorded on the board; the approved image's role becomes `approved`.
6. **Export** on request: `creative_review_export(board_id, format="json"|"markdown")`
   writes the approved image plus the full review history into the plugin's own
   data folder.

## Rules that matter

- **Never invent feedback.** Read the markers from the brief (or
  `creative_review_get_board`) — each has a coordinate (x/y as a fraction of the
  image, origin top-left) and a note. Address every one.
- **Always pass `parent_id`** when registering a revision. Without it the version
  lineage breaks and the user cannot compare versions in the pane.
- **Paths are absolute and local.** The board stores the path; it does not copy
  or upload the image. If the user's file is missing, `add_image` returns
  `file-not-found` — ask for the correct path.
- **Approval is the user's call.** Only record `creative_review_approve` on an
  explicit decision; never self-approve.
- **No image generation here.** This plugin reviews and directs; the actual image
  comes from whatever image tool is available in the session.

## Tool reference

- `creative_review_create_board(title)` — new board → board_id
- `creative_review_list_boards()` — all boards + counts
- `creative_review_add_image(board_id, path, role?, label?, parent_id?)` — register a local image
- `creative_review_get_board(board_id)` — full board state (images, annotations, lineage, approval)
- `creative_review_revision_brief(board_id, image_id, overall_note?)` — the structured brief (markdown + markers)
- `creative_review_approve(board_id, image_id, decision="approved"|"rejected")`
- `creative_review_export(board_id, format="json"|"markdown", out_dir?)`