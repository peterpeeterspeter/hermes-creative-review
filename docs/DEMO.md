# 90-second demo script

Record for real — every step below runs against the shipped plugin. Nothing is
mocked.

## Before you hit record
- Hermes Desktop open, **Creative Review** enabled (Capabilities → Plugins) and
  the `review` chip visible in the status bar.
- A chat open. `/tmp/cr-demo/` holds: `reference.png` (the target aesthetic) and
  `v1.png` (a first attempt). Have an image-generation tool available.
- Plugin installed (`hermes plugins install <owner>/hermes-creative-review`).

## The script (≈90s)

**0:00 — The ask (chat)**
> "Generate a hero image of a leather satchel on a stone plinth, and put it in
> Creative Review against `/tmp/cr-demo/reference.png`."

The agent calls `creative_review_create_board` then `creative_review_add_image`
(reference + generated). *Say:* "The agent registers the files locally — nothing
is uploaded."

**0:12 — Open the desk**
Click the **review** chip (or sidebar → Creative Review). The board opens with
the version tree on the left, the generated image on the stage, and the
reference thumbnail.

**0:20 — Compare**
In the compare strip, set Left = reference, Right = v1. Click **Overlay**, drag
the slider. *Say:* "Reference against result, side by side or blended."

**0:36 — Annotate**
Scroll to zoom into the buckle. Click it → marker **1** appears. Type
*"make the buckle brass, not steel."* Zoom out, click the top corner → marker
**2**, *"remove the logo watermark."* *Say:* "Coordinates are stored as a
fraction of the image, so they survive any zoom or resize."

**0:56 — Request Revision (the money shot)**
Add an overall note: *"warmer, golden-hour light."* Press **Request Revision**.
Cut to the **chat window**: the structured brief has landed as a real user turn —
markers, coordinates, notes, the reference, and the `creative_review_add_image`
call for the new version.

**1:08 — The agent revises**
The agent generates v2 and registers it with `parent_id`. In the pane, the
version tree now shows **v2 under v1**, with the revision linked. Switch the
stage to v2.

**1:20 — Approve & export**
Click **Approve**. The board status flips to approved and v2's role becomes
`approved`. Click **Export JSON** — the toast names the written file. Show it:
the bundle + a copy of the approved image, under the plugin's own data folder.

**1:30 — Close**
*"Local-first, no account, no uploads. The agent got a real, precise brief — not
a screenshot and a vibe."*

## Verification for the submission
```
hermes plugins validate . --install-deps     # all green
hermes plugins doctor .                      # 7 tools, registration passed
python -m unittest discover -s tests         # unit + tool contract tests
python tests/integration_backend.py          # 21 backend route checks
node tests/desktop_harness.mjs               # 15 desktop registration checks
```