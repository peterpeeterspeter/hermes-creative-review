# Creative Review — Phase A research & architecture (Hermes v0.22.7)

## Deliverable
One **unified Hermes plugin** (`creative-review`) = agent half + desktop half +
backend, installable as a single folder / repo, that gives Hermes Desktop an art
director's desk: import images, compare two side by side, zoom/pan, drop
numbered point annotations, request a revision, and approve + export.

## Verified SDK facts (from `website/docs/developer-guide/desktop-plugin-sdk.md` + repo source)

### Unified package layout (one folder, one install)
```
~/.hermes/plugins/<id>/
├── plugin.yaml                 # agent half manifest (tools/hooks)
├── __init__.py                 # register(ctx): tools, skills
├── dashboard/
│   ├── manifest.json           # {"name":"<id>","api":"plugin_api.py"}
│   └── plugin_api.py           # APIRouter → /api/plugins/<id>/*
└── desktop/
    └── plugin.js               # desktop half: panes, ctx.rest, host.composer
```
Electron main copies `desktop/` → `desktop-plugins/<id>/` beside a
`.hermes-package.json` marker. The desktop half is **opt-in** (off until the user
toggles it in Capabilities ▸ Plugins). A `ln -s` of the package into `plugins/`
makes the copy hot-reload on every save (content-hashed, not mtime).

### Desktop plugin contract
- Plain ESM, loaded **uncompiled** → `jsx()`/`jsxs()` only, **no JSX syntax**.
- Only `@hermes/plugin-sdk`, `react`, `react/jsx-runtime` resolve.
- Persistence: `ctx.storage` (JSON, `hermes.plugin.<id>.*`) and `ctx.files` ('data' folder).
- Backend: `ctx.rest('/path', {method, body})` → `/api/plugins/<id>/path`; `ctx.socket` for live.
- UI kit + theme vars; never hardcode colors; canvas panes need a `ResizeObserver`.
- Admission lint (`plugin_validate_desktop.py`) **forbids**: eval/new Function,
  dynamic import outside SDK, remote import, `<script>`, `document.querySelector`
  on `[data-slot|tour|sidebar|testid]`, webview reach. Warns on
  `window.hermesDesktop` + app markup selectors.

### THE revision-handoff door (mission §4, step 7-8) — SUPPORTED API
`host.composer` (Composer draft API):
```ts
host.composer.submit(sessionId, text): boolean   // send as if typed + Enter
host.composer.setDraft(sessionId, text): Promise<boolean>
host.composer.insertText(sessionId, text, {mode}): Promise<boolean>
host.composer.getDraft(sessionId): Promise<string|null>
host.composer.focus(sessionId): void
```
`sessionId` = `host.state.focusedSessionId.get()` (runtime id) — the focused
chat's composer. Fail-closed: `false` when no mounted surface answers.
→ **"Request Revision" builds the structured brief and calls
`host.composer.submit(focusedSessionId, brief)`**, which lands as a real user
turn in the live Hermes conversation. Fallback: `setDraft` + toast if submit
returns false. This is a documented, first-class API — not a fake interaction.

### Host state atoms used
`host.state.focusedSessionId`, `host.state.busyBySession`,
`host.state.gateway`, `host.state.focusedStoredSessionId`.

## OMH status (mission §1)
- `omh` CLI **is** installed and healthy: `omh 4.0.6`, `omh doctor` 63/63.
- The OMH **agent tools** (`omh_document_plan`, `omh_todo`, `omh_status`, …) are
  declared in `plugins/omh/plugin.yaml` but are **not exposed to this agent
  session** (tool_search finds none; the gateway is running pre-update OMH code).
- Per the brief ("If OMH core or an optional feature is unavailable, continue
  using available tools. Do not claim delegation or tests occurred unless
  confirmed"), planning/tracking is done with the available `omh` CLI where it
  supports the task and Hermes-native tools otherwise. **No delegation is
  claimed.**

## Storage (mission §3)
- Local-first, persistent across sessions: SQLite via `plugin_db("creative-review")`
  → `<HERMES_HOME>/plugin-data/creative-review/`. Survives `plugins update/remove`,
  follows the profile.
- Images stay on disk; the backend reads bytes and returns a **data URL** to the
  pane (`GET /image-data`). No upload, no cloud, no account. No secrets in files.

## Data model
- `boards(id, title, status, created_at, updated_at, meta)`
- `images(id, board_id, path, role, label, parent_id, created_at, meta)`
  roles: `reference | generated | approved`
- `annotations(id, image_id, number, x, y, w, h, note, author, created_at)`
  x/y normalized 0..1 (origin top-left) → resolution-independent markers.
- `revisions(id, board_id, parent_image_id, child_image_id, brief, delivered, created_at)`
- `approvals(board_id, image_id, decision, created_at)`

## Agent tools
`creative_review_create_board`, `creative_review_list_boards`,
`creative_review_add_image`, `creative_review_get_board`,
`creative_review_revision_brief`, `creative_review_approve`,
`creative_review_export`.

## Workflow loop
1. Hermes generates an image → `creative_review_create_board` +
   `creative_review_add_image(role='generated')` (reference optionally added too).
2. User opens the pane → sees the board.
3. Compares reference vs generated; zoom/pan; clicks to drop numbered markers + notes.
4. "Request Revision" → backend builds the structured brief → pane calls
   `host.composer.submit(focusedSessionId, brief)`.
5. Hermes receives the real turn, invokes an image tool.
6. Agent calls `creative_review_add_image(parent_id=<old>)` → lineage recorded.
7. User approves → `creative_review_approve`.
8. `creative_review_export` → image + review history (JSON/Markdown).

## Quality gates
`hermes plugins validate ./ --install-deps` and `hermes plugins doctor ./` must pass.
Desktop half must clear `desktop surface`.