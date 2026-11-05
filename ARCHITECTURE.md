# Architecture

Creative Review is **one unified Hermes plugin**: a single installable folder
that ships an agent half, a Desktop half and a backend, wired together by the
plugin SDK and the plugin backend namespace.

```
~/.hermes/plugins/creative-review/     (one install)
├── plugin.yaml            agent half manifest: 7 tools, requires_hermes>=0.22.0
├── __init__.py            register(ctx): registers tools + bundled skill
├── schemas.py             tool schemas (model-facing descriptions)
├── tools.py               tool handlers (never raise; always JSON)
├── store.py               local-first persistence (SQLite via plugin_db)
├── brief.py               structured revision brief (shared by both halves)
├── export.py              JSON/Markdown export + approved-image copy
├── dashboard/
│   ├── manifest.json      {"name":"creative-review","api":"plugin_api.py"}
│   └── plugin_api.py      APIRouter mounted at /api/plugins/creative-review/
├── desktop/
│   └── plugin.js          Desktop pane (loaded uncompiled; jsx() calls only)
└── skills/creative-review/SKILL.md
```

## Three halves, one folder

| Half | Runs in | Talks to |
|---|---|---|
| Agent (`__init__.py`, `tools.py`) | the agent process | `store.py` directly |
| Backend (`dashboard/plugin_api.py`) | the gateway process | `store.py` / `brief.py` / `export.py` (loaded by path) |
| Desktop (`desktop/plugin.js`) | the Electron renderer | the backend via `ctx.rest('/…')` → `/api/plugins/creative-review/…` |

The Electron main process copies `desktop/` into `$HERMES_HOME/desktop-plugins/creative-review/`
beside a `.hermes-package.json` marker and loads it through the disk-plugin door.
The Desktop half is **opt-in** (off until the user toggles it), matching the
Python half's `plugins.enabled` gate. Both halves are gated; both default off.

`store.py` is deliberately dependency-free (stdlib + a lazy `plugins.plugin_storage`
import), so it can be imported by any loader without a package on `sys.path`.

## Data model (SQLite, `<HERMES_HOME>/plugin-data/creative-review/data.db`)

```
boards(id, title, status, created_at, updated_at, meta)
images(id, board_id, path, role, label, parent_id, created_at, meta)
annotations(id, image_id, number, x, y, w, h, note, author, created_at)
revisions(id, board_id, parent_image_id, child_image_id, brief, delivered, created_at)
approvals(board_id, image_id, decision, created_at)
```

- `images.path` is an **absolute local path**; bytes are never copied into the DB.
- `annotations.x` / `.y` are **normalized (0..1, origin top-left)**, so markers
  are resolution-independent and survive a resize or a different display scale.
- `images.parent_id` encodes the **revision lineage**; the pane renders it as an
  indented version tree.

## The revision handoff (the core requirement)

The user's "Request Revision" must reach a **real Hermes conversation** — not a
mock. The plugin uses a documented, first-class SDK door:

```js
// desktop/plugin.js
const brief = await api('/revision', { method: 'POST', body: { board_id, image_id, overall_note } })
const target = host.state.focusedSessionId.get()          // the focused chat
const sent = host.composer.submit(target, brief.brief.markdown)  // a real user turn
if (!sent) await host.composer.setDraft(target, brief.brief.markdown)  // fallback: leave a draft
```

`host.composer.submit` is the SDK's supported "send as if the user typed and
pressed Enter" verb. It is **fail-closed**: it returns `false` when no mounted
composer answers the address, in which case the plugin places the brief in the
composer as a draft and tells the user to press Enter. No DOM reach-in, no
synthetic events, no patched internals.

The agent then receives the brief as an ordinary user turn, generates a new
image and calls `creative_review_add_image(..., parent_id=<revised image>)`,
which records the lineage and shows up in the pane on the next poll.

## Backend routes (`/api/plugins/creative-review/`)

```
GET    /health
GET    /boards                     POST /boards
GET    /board?board_id=            POST /image
GET    /image-data?image_id=       GET  /file?image_id=
POST   /annotation                 PATCH /annotation      DELETE /annotation?id=
POST   /revision                   POST /revision-delivered
POST   /approve
GET    /export?board_id=&format=
```

`GET /image-data` is the only route that touches image bytes: it reads one
registered file from disk and returns a `data:` URL. Nothing is uploaded.

## Polling

The pane polls `/boards` and `/board` every 4 s via React Query (the same client
the app uses). That is how a revision the **agent** registers shows up while the
user is looking at the board. No socket is used (sockets are a no-op on OAuth
remotes, so polling is the reliable floor).