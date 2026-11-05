"""Tool schemas — what the model reads to decide when to call Creative Review."""

TOOLSET = "creative_review"

CREATE_BOARD = {
    "name": "creative_review_create_board",
    "description": (
        "Create a local Creative Review board: a visual workspace where a user "
        "compares a reference image against generated images, drops numbered "
        "point annotations, requests a precise revision, and approves the final "
        "image. Call this once when the user asks to review / art-direct an "
        "image, or before adding the first image to a new review."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string",
                      "description": "Short human title for the review, e.g. 'Hero shot — autumn campaign'."},
        },
        "required": ["title"],
    },
}

LIST_BOARDS = {
    "name": "creative_review_list_boards",
    "description": (
        "List every Creative Review board with its image, annotation and "
        "approval counts. Use this to find an existing board before adding to it."
    ),
    "parameters": {"type": "object", "properties": {}},
}

ADD_IMAGE = {
    "name": "creative_review_add_image",
    "description": (
        "Register a local image file on a Creative Review board. Use role "
        "'reference' for the target image the user wants to match, 'generated' "
        "for an image you just produced. When the image is a revision of an "
        "earlier one, pass that earlier image's id as parent_id so the version "
        "lineage is recorded. The file is read from disk in place; nothing is "
        "uploaded or copied."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "board_id": {"type": "string", "description": "Board id returned by creative_review_create_board."},
            "path": {"type": "string",
                     "description": "Absolute path to the image file on this machine (png/jpg/webp/gif/bmp/avif)."},
            "role": {"type": "string", "enum": ["reference", "generated", "approved"],
                     "description": "'reference' = the target to match; 'generated' = an image you produced. Default 'generated'."},
            "label": {"type": "string", "description": "Optional display label, e.g. 'v2 — warmer light'."},
            "parent_id": {"type": "string",
                          "description": "image_id this image revises, to record lineage. Omit for a fresh image."},
        },
        "required": ["board_id", "path"],
    },
}

GET_BOARD = {
    "name": "creative_review_get_board",
    "description": (
        "Read one Creative Review board in full: its images (with on-disk "
        "existence), every annotation, the revision lineage and the approval "
        "state. Use this to see the user's feedback before acting on it."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "board_id": {"type": "string", "description": "The board id to read."},
        },
        "required": ["board_id"],
    },
}

REVISION_BRIEF = {
    "name": "creative_review_revision_brief",
    "description": (
        "Produce the structured revision brief for one image on a board: the "
        "selected image, its numbered point annotations with coordinates and "
        "notes, the reference image, and the revision lineage. Use this when the "
        "user says 'revise this', or when you receive a revision brief in the "
        "conversation and want the machine-readable version. Pass overall_note "
        "for a free-text instruction that isn't tied to a marker."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "board_id": {"type": "string", "description": "The board id."},
            "image_id": {"type": "string", "description": "The image to revise."},
            "overall_note": {"type": "string",
                             "description": "Optional global instruction for the revision."},
        },
        "required": ["board_id", "image_id"],
    },
}

APPROVE = {
    "name": "creative_review_approve",
    "description": (
        "Record an approval decision for a Creative Review board. 'approved' "
        "marks the chosen image as final (and promotes its role to 'approved'); "
        "'rejected' closes the board as rejected. Use this only on the user's "
        "explicit decision."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "board_id": {"type": "string", "description": "The board id."},
            "image_id": {"type": "string", "description": "The image being approved or rejected."},
            "decision": {"type": "string", "enum": ["approved", "rejected"],
                         "description": "The decision. Default 'approved'."},
        },
        "required": ["board_id", "image_id"],
    },
}

EXPORT = {
    "name": "creative_review_export",
    "description": (
        "Export a Creative Review board's approved image and its full review "
        "history. Format 'json' writes a machine-readable bundle; 'markdown' "
        "writes a human-readable report. Returns the written file paths. Nothing "
        "leaves the machine — the export is written to the plugin's own data "
        "folder unless out_dir is given."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "board_id": {"type": "string", "description": "The board id to export."},
            "format": {"type": "string", "enum": ["json", "markdown"],
                       "description": "Export format. Default 'json'."},
            "out_dir": {"type": "string",
                        "description": "Optional absolute directory to write into. Defaults to the plugin's own data folder."},
        },
        "required": ["board_id"],
    },
}

ALL = [CREATE_BOARD, LIST_BOARDS, ADD_IMAGE, GET_BOARD, REVISION_BRIEF, APPROVE, EXPORT]