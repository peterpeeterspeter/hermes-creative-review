/**
 * Creative Review — the desktop half of the Hermes plugin.
 *
 * An art director's desk: pick a board, compare a reference image against the
 * generated versions side by side, zoom and pan, click anywhere to drop a
 * numbered point annotation with a note, then "Request Revision" — which builds
 * a structured brief on the backend and hands it to the LIVE Hermes
 * conversation with host.composer.submit(), so the agent receives it as a real
 * user turn. Approve the final image and export it with its review history.
 *
 * Plain ESM, loaded uncompiled (no JSX — jsx()/jsxs() calls only). Only
 * '@hermes/plugin-sdk', 'react' and 'react/jsx-runtime' resolve. Styles live in
 * a <style> element this file injects on register and removes on dispose;
 * every colour resolves through the app's theme tokens, never a literal.
 *
 * All state comes from the sibling backend (dashboard/plugin_api.py) through
 * ctx.rest('/…') -> /api/plugins/creative-review/…. Image bytes are fetched as
 * data URLs on demand; nothing leaves the machine.
 */
import {
  Badge,
  Button,
  cn,
  EmptyState,
  ErrorState,
  GlyphSpinner,
  haptic,
  host,
  Input,
  PALETTE_AREA,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  STATUSBAR_AREAS,
  Textarea,
  Tip,
  useMutation,
  useQuery,
  useQueryClient,
  useValue
} from '@hermes/plugin-sdk'
import { useEffect, useRef, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

export const ID = 'creative-review'
export const PAGE_PATH = '/creative-review'
const STYLE_ID = 'creative-review-style'
const POLL_MS = 4000
const DBKEY = [ID]
// Badge accepts only: default | muted | success | warn | destructive | outline | solid.
const ROLE_BADGE = { reference: 'muted', generated: 'default', approved: 'success' }

// Bound in register(); ctx.rest is scoped to this plugin's namespace.
let rest = null

// ---------------------------------------------------------------------------
// small tree helpers (jsx/jsxs discipline: no JSX syntax, filter empties)
// ---------------------------------------------------------------------------
function present(child) {
  return child !== null && child !== undefined && child !== false && child !== ''
}
function el(type, props, children) {
  const list = (Array.isArray(children) ? children : [children]).filter(present)
  if (list.length === 0) return jsx(type, props || {})
  if (list.length === 1) return jsx(type, { ...(props || {}), children: list[0] })
  return jsxs(type, { ...(props || {}), children: list })
}
function box(className, children, key) {
  return el('div', { className, key }, children)
}
function txt(text) {
  return text === null || text === undefined ? '' : String(text)
}
function shortId(id) {
  return txt(id).replace(/^[a-z]+_/, '').slice(0, 6)
}
function pct(value) {
  return `${Math.round(Number(value) * 100)}%`
}

async function api(path, options) {
  if (!rest) throw new Error('creative-review: plugin context is not registered')
  return rest(path, options)
}

// ---------------------------------------------------------------------------
// data hooks
// ---------------------------------------------------------------------------
function useBoards() {
  const gateway = useValue(host.state.gateway)
  return useQuery({
    queryKey: [...DBKEY, 'boards'],
    queryFn: () => api('/boards'),
    refetchInterval: POLL_MS,
    enabled: gateway === 'open',
    placeholderData: (previous) => previous
  })
}

function useBoard(boardId) {
  const gateway = useValue(host.state.gateway)
  return useQuery({
    queryKey: [...DBKEY, 'board', boardId || ''],
    queryFn: () => api(`/board?board_id=${encodeURIComponent(boardId)}`),
    refetchInterval: boardId ? POLL_MS : false,
    enabled: gateway === 'open' && !!boardId,
    placeholderData: (previous) => previous
  })
}

function useImageData(imageId) {
  const q = useQuery({
    queryKey: [...DBKEY, 'image-data', imageId || ''],
    queryFn: () => api(`/image-data?image_id=${encodeURIComponent(imageId)}`),
    enabled: !!imageId,
    staleTime: 10 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    refetchOnWindowFocus: false
  })
  return q.data && q.data.ok ? q.data.data_url : null
}

// ---------------------------------------------------------------------------
// The image stage: zoom, pan, click-to-annotate
// ---------------------------------------------------------------------------
function ImageStage({ image, allowAnnotate, onAddMarker, fitKey }) {
  const dataUrl = useImageData(image ? image.id : null)
  const [view, setView] = useState({ scale: 1, tx: 0, ty: 0 })
  const containerRef = useRef(null)
  const dragRef = useRef({ panning: false, moved: false, sx: 0, sy: 0, ox: 0, oy: 0 })

  // Reset the view when the shown image changes.
  useEffect(() => { setView({ scale: 1, tx: 0, ty: 0 }) }, [image ? image.id : null, fitKey])

  // Wheel zoom needs a non-passive listener to preventDefault reliably.
  useEffect(() => {
    const node = containerRef.current
    if (!node) return undefined
    const onWheel = (event) => {
      event.preventDefault()
      const rect = node.getBoundingClientRect()
      const px = event.clientX - rect.left
      const py = event.clientY - rect.top
      setView((current) => {
        const factor = event.deltaY < 0 ? 1.15 : 1 / 1.15
        const scale = Math.min(8, Math.max(0.2, current.scale * factor))
        const k = scale / current.scale
        return { scale, tx: px - k * (px - current.tx), ty: py - k * (py - current.ty) }
      })
      haptic('tap')
    }
    node.addEventListener('wheel', onWheel, { passive: false })
    return () => node.removeEventListener('wheel', onWheel)
  }, [image ? image.id : null])

  if (!image) {
    return box('cr-stage cr-stage-empty', el('div', { className: 'cr-hint' }, 'Select an image'))
  }

  const onPointerDown = (event) => {
    const panning = event.button === 1 || (allowAnnotate === false)
    dragRef.current = {
      panning,
      moved: false,
      sx: event.clientX,
      sy: event.clientY,
      ox: view.tx,
      oy: view.ty
    }
    if (panning) event.currentTarget.setPointerCapture(event.pointerId)
  }
  const onPointerMove = (event) => {
    const drag = dragRef.current
    if (!drag.panning) return
    const dx = event.clientX - drag.sx
    const dy = event.clientY - drag.sy
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true
    setView((current) => ({ ...current, tx: drag.ox + dx, ty: drag.oy + dy }))
  }
  const onPointerUp = () => {
    dragRef.current.panning = false
  }
  const onClickImage = (event) => {
    if (!allowAnnotate || dragRef.current.moved) return
    const rect = event.currentTarget.getBoundingClientRect()
    const x = (event.clientX - rect.left) / rect.width
    const y = (event.clientY - rect.top) / rect.height
    if (x < 0 || x > 1 || y < 0 || y > 1) return
    onAddMarker(Math.round(x * 10000) / 10000, Math.round(y * 10000) / 10000)
  }

  const markers = image.annotations || []

  return box(
    'cr-stage',
    [
      el(
        'div',
        {
          className: 'cr-stage-inner',
          style: { transform: `translate(${view.tx}px, ${view.ty}px) scale(${view.scale})` },
          onPointerDown,
          onPointerMove,
          onPointerUp,
          onPointerLeave: onPointerUp
        },
        [
          el('div', { className: 'cr-frame' }, [
            dataUrl
              ? el(
                  'div',
                  { className: 'cr-canvas' },
                  [
                    el('img', {
                      className: cn('cr-image', allowAnnotate && 'cr-image-annotate'),
                      src: dataUrl,
                      alt: image.label || image.id,
                      draggable: false,
                      onClick: onClickImage
                    }),
                    el(
                      'div',
                      { className: 'cr-markers' },
                      markers.map((marker) =>
                        el(
                          'div',
                          {
                            key: marker.id,
                            className: 'cr-marker',
                            style: { left: pct(marker.x), top: pct(marker.y) }
                          },
                          [
                            el('span', { className: 'cr-marker-dot' }, txt(marker.number)),
                            marker.note
                              ? el('span', { className: 'cr-marker-label' }, txt(marker.note))
                              : null
                          ]
                        )
                      )
                    )
                  ]
                )
              : box(
                  'cr-image-placeholder',
                  image.exists === false
                    ? el(ErrorState, { title: 'File missing', description: `Not found on disk: ${image.path}` })
                    : jsx(GlyphSpinner, { ariaLabel: 'Loading image' })
                )
          ])
        ]
      ),
      box('cr-stage-tools', [
        el(Button, {
          variant: 'ghost',
          size: 'xs',
          onClick: () => setView({ scale: 1, tx: 0, ty: 0 }),
          children: 'Fit'
        }),
        el('span', { className: 'cr-zoom' }, `${Math.round(view.scale * 100)}%`)
      ])
    ]
  )
}

// ---------------------------------------------------------------------------
// Compare strip: two chosen images side by side, optional overlay slider
// ---------------------------------------------------------------------------
function CompareStrip({ images, leftId, rightId, setLeftId, setRightId }) {
  const [overlay, setOverlay] = useState(false)
  const [split, setSplit] = useState(50)
  const left = images.find((im) => im.id === leftId) || null
  const right = images.find((im) => im.id === rightId) || null

  const picker = (value, onChange, label) =>
    el(
      'label',
      { className: 'cr-picker' },
      [
        el('span', { className: 'cr-picker-label' }, label),
        el(
          'select',
          { className: 'cr-select', value: value || '', onChange: (e) => onChange(e.target.value) },
          [
            el('option', { value: '', key: 'none' }, '— none —'),
            ...images.map((im) =>
              el('option', { value: im.id, key: im.id },
                `${im.role}: ${im.label || shortId(im.id)}`)
            )
          ]
        )
      ]
    )

  if (overlay) {
    return box('cr-compare', [
      box('cr-compare-head', [
        box('cr-compare-pickers', [picker(leftId, setLeftId, 'Base'), picker(rightId, setRightId, 'Overlay')]),
        el(Button, { variant: 'ghost', size: 'xs', onClick: () => setOverlay(false), children: 'Side by side' })
      ]),
      el(OverlaySlider, { left, right, split, setSplit })
    ])
  }

  return box('cr-compare', [
    box('cr-compare-head', [
      box('cr-compare-pickers', [picker(leftId, setLeftId, 'Left'), picker(rightId, setRightId, 'Right')]),
      el(Button, { variant: 'ghost', size: 'xs', onClick: () => setOverlay(true), children: 'Overlay' })
    ]),
    box('cr-compare-body', [
      box('cr-compare-cell', [
        box('cr-compare-cell-head', txt(left ? left.label : 'Left')),
        el(StageThumb, { image: left })
      ]),
      box('cr-compare-cell', [
        box('cr-compare-cell-head', txt(right ? right.label : 'Right')),
        el(StageThumb, { image: right })
      ])
    ])
  ])
}

function StageThumb({ image }) {
  const dataUrl = useImageData(image ? image.id : null)
  if (!image) return box('cr-thumb cr-thumb-empty', '—')
  if (!dataUrl) return box('cr-thumb', jsx(GlyphSpinner, { ariaLabel: 'Loading' }))
  return box('cr-thumb', el('img', { className: 'cr-thumb-img', src: dataUrl, alt: image.label || image.id, draggable: false }))
}

function OverlaySlider({ left, right, split, setSplit }) {
  const leftUrl = useImageData(left ? left.id : null)
  const rightUrl = useImageData(right ? right.id : null)
  return box('cr-overlay', [
    box('cr-overlay-frame', [
      leftUrl ? el('img', { className: 'cr-overlay-img', src: leftUrl, alt: 'base', draggable: false }) : null,
      rightUrl
        ? el('img', {
            className: 'cr-overlay-img cr-overlay-top',
            src: rightUrl,
            alt: 'overlay',
            draggable: false,
            style: { clipPath: `inset(0 0 0 ${split}%)` }
          })
        : null
    ]),
    el('input', {
      className: 'cr-range',
      type: 'range',
      min: 0,
      max: 100,
      value: split,
      onChange: (e) => setSplit(Number(e.target.value)),
      'aria-label': 'Overlay split'
    })
  ])
}

// ---------------------------------------------------------------------------
// Annotation list
// ---------------------------------------------------------------------------
function AnnotationList({ image, onUpdate, onDelete, onSelect }) {
  const markers = (image && image.annotations) || []
  if (!markers.length) {
    return box('cr-ann-empty', 'Click the image to drop your first numbered marker.')
  }
  return box(
    'cr-ann-list',
    markers.map((marker) =>
      el(
        'div',
        { key: marker.id, className: 'cr-ann' },
        [
          el('span', { className: 'cr-ann-num' }, txt(marker.number)),
          el(Textarea, {
            className: 'cr-ann-note',
            rows: 1,
            defaultValue: marker.note,
            placeholder: 'Describe the change at this point…',
            onBlur: (e) => {
              if (e.target.value !== marker.note) onUpdate(marker.id, e.target.value)
            },
            onKeyDown: (e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                onUpdate(marker.id, e.target.value)
              }
            }
          }),
          el('span', { className: 'cr-ann-pos' }, `(${pct(marker.x)}, ${pct(marker.y)})`),
          el(Button, {
            variant: 'ghost',
            size: 'xs',
            onClick: () => onSelect(marker),
            children: 'Locate'
          }),
          el(Button, {
            variant: 'ghost',
            size: 'xs',
            onClick: () => onDelete(marker.id),
            children: '✕'
          })
        ]
      )
    )
  )
}

// ---------------------------------------------------------------------------
// Version history / lineage
// ---------------------------------------------------------------------------
function VersionHistory({ board, currentId, onSelect }) {
  const images = (board && board.images) || []
  const byParent = new Map()
  for (const im of images) {
    const key = im.parent_id || '__root__'
    if (!byParent.has(key)) byParent.set(key, [])
    byParent.get(key).push(im)
  }
  const rows = []
  const walk = (parentId, depth) => {
    for (const im of byParent.get(parentId) || []) {
      rows.push({ im, depth })
      walk(im.id, depth + 1)
    }
  }
  walk('__root__', 0)
  for (const im of images) if (!rows.some((r) => r.im.id === im.id)) rows.push({ im, depth: 0 })

  return box(
    'cr-versions',
    rows.map(({ im, depth }) =>
      el(
        'button',
        {
          type: 'button',
          key: im.id,
          className: cn('cr-version', im.id === currentId && 'cr-version-active'),
          style: { paddingLeft: `${8 + depth * 14}px` },
          onClick: () => onSelect(im.id)
        },
        [
          el(Badge, { variant: ROLE_BADGE[im.role] || 'muted', size: 'xs' }, txt(im.role)),
          el('span', { className: 'cr-version-label' }, txt(im.label || shortId(im.id))),
          (im.annotations || []).length
            ? el('span', { className: 'cr-version-count' }, `${im.annotations.length} note${im.annotations.length === 1 ? '' : 's'}`)
            : null
        ]
      )
    )
  )
}

// ---------------------------------------------------------------------------
// The page
// ---------------------------------------------------------------------------
function ReviewPage() {
  const queryClient = useQueryClient()
  const boardsQuery = useBoards()
  const [boardId, setBoardId] = useState(null)
  const [currentId, setCurrentId] = useState(null)
  const [leftId, setLeftId] = useState(null)
  const [rightId, setRightId] = useState(null)
  const [overallNote, setOverallNote] = useState('')
  const [status, setStatus] = useState(null)
  const [newBoardOpen, setNewBoardOpen] = useState(false)
  const [draftTitle, setDraftTitle] = useState('')
  const [revisionBusy, setRevisionBusy] = useState(false)
  const [fitKey, setFitKey] = useState(0)
  const boardQuery = useBoard(boardId)

  const boards = (boardsQuery.data && boardsQuery.data.boards) || []
  const board = boardQuery.data && boardQuery.data.ok ? boardQuery.data.board : null
  const images = (board && board.images) || []

  // Auto-select a board and a current image when the data arrives.
  useEffect(() => {
    if (!boardId && boards.length) setBoardId(boards[0].id)
  }, [boards, boardId])
  useEffect(() => {
    if (!images.length) { setCurrentId(null); setLeftId(null); setRightId(null); return }
    const reference = images.find((im) => im.role === 'reference')
    const newest = [...images].reverse().find((im) => im.role !== 'reference') || images[images.length - 1]
    setCurrentId((current) => (images.some((im) => im.id === current) ? current : (newest && newest.id)))
    setLeftId((current) => (images.some((im) => im.id === current) ? current : (reference ? reference.id : (images[0] && images[0].id))))
    setRightId((current) => (images.some((im) => im.id === current) ? current : (newest && newest.id)))
  }, [board ? board.id : null, images.length])

  const current = images.find((im) => im.id === currentId) || null

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: [...DBKEY, 'board'] })
    queryClient.invalidateQueries({ queryKey: [...DBKEY, 'boards'] })
  }

  const addMarker = useMutation({
    mutationFn: ({ x, y }) => api('/annotation', { method: 'POST', body: { image_id: currentId, x, y } }),
    onSuccess: invalidate
  })
  const updateMarker = useMutation({
    mutationFn: ({ id, note }) => api('/annotation', { method: 'PATCH', body: { id, note } }),
    onSuccess: invalidate
  })
  const deleteMarker = useMutation({
    mutationFn: ({ id }) => api(`/annotation?id=${encodeURIComponent(id)}`, { method: 'DELETE' }),
    onSuccess: invalidate
  })
  const newBoard = useMutation({
    mutationFn: (title) => api('/boards', { method: 'POST', body: { title } }),
    onSuccess: (data) => {
      invalidate()
      setNewBoardOpen(false)
      setDraftTitle('')
      if (data && data.ok && data.board) setBoardId(data.board.id)
    }
  })
  const approve = useMutation({
    mutationFn: ({ decision }) => api('/approve', { method: 'POST', body: { board_id: boardId, image_id: currentId, decision } }),
    onSuccess: (data) => {
      invalidate()
      setStatus(data && data.ok ? `Recorded: ${data.approval.decision}` : `Failed: ${(data && data.error) || 'unknown'}`)
      haptic('tap')
    }
  })
  const doExport = useMutation({
    mutationFn: (format) => api(`/export?board_id=${encodeURIComponent(boardId)}&format=${format}`),
    onSuccess: (data) => {
      if (data && data.ok) {
        setStatus(`Exported to ${(data.written || []).join(', ')}`)
        haptic('tap')
      } else {
        setStatus(`Export failed: ${(data && data.error) || 'unknown'}`)
      }
    }
  })

  // The revision handoff — the mission's core requirement, through real APIs.
  const requestRevision = async () => {
    if (!boardId || !currentId) return
    setRevisionBusy(true)
    try {
      let data
      try {
        data = await api('/revision', {
          method: 'POST',
          body: { board_id: boardId, image_id: currentId, overall_note: overallNote }
        })
      } catch (error) {
        setStatus(`Could not build brief: ${error.message || error}`)
        return
      }
      if (!data || !data.ok) {
        setStatus(`Could not build brief: ${(data && data.error) || 'unknown'}`)
        return
      }
      const briefText = data.brief.markdown
      const target = host.state.focusedSessionId.get() || null
      let sent = false
      try {
        sent = host.composer.submit(target, briefText)
      } catch (error) {
        sent = false
      }
      if (sent) {
        setStatus('Revision brief sent to Hermes — the agent has it now.')
        haptic('tap')
        api('/revision-delivered', { method: 'POST', body: { revision_id: data.revision_id } }).catch(() => {})
        return
      }
      // Fail-closed: no mounted composer answered, so leave the brief as a draft.
      const placed = await host.composer.setDraft(target, briefText).catch(() => false)
      setStatus(
        placed
          ? 'Brief placed in the composer — press Enter to send it to Hermes.'
          : 'Could not reach a conversation composer. Open a chat and retry.'
      )
    } finally {
      setRevisionBusy(false)
      invalidate()
    }
  }

  // Electron implements no window.prompt, so the title is an inline field.
  const createBoard = () => {
    const title = draftTitle.trim()
    if (title) newBoard.mutate(title)
  }

  const removeMarker = (id) => deleteMarker.mutate({ id })

  const gateway = useValue(host.state.gateway)

  // Keyboard shortcuts (ignored while a field has focus).
  const onKey = (event) => {
    const tag = event.target && event.target.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
    const index = images.findIndex((im) => im.id === currentId)
    if (event.key === 'ArrowDown' || event.key === ']') {
      const next = images[Math.min(images.length - 1, index + 1)]
      if (next) { setCurrentId(next.id); event.preventDefault() }
    } else if (event.key === 'ArrowUp' || event.key === '[') {
      const prev = images[Math.max(0, index - 1)]
      if (prev) { setCurrentId(prev.id); event.preventDefault() }
    } else if (event.key === 'f') {
      setFitKey((k) => k + 1)
    } else if (event.key === 'a' && currentId) {
      approve.mutate({ decision: 'approved' })
    } else if (event.key === 'r' && currentId) {
      requestRevision()
    }
  }

  return el('div', { className: 'cr-page', tabIndex: 0, onKeyDown: onKey }, [
    box('cr-toolbar', [
      el(Badge, { variant: 'muted', size: 'xs' }, 'Creative Review'),
      el(
        'select',
        {
          className: 'cr-select',
          value: boardId || '',
          onChange: (e) => setBoardId(e.target.value || null)
        },
        boards.length
          ? boards.map((b) => el('option', { value: b.id, key: b.id }, `${b.title} (${b.image_count})`))
          : [el('option', { value: '', key: 'empty' }, 'No boards yet')]
      ),
      newBoardOpen
        ? [
            el(Input, {
              key: 'title',
              className: 'cr-newboard',
              autoFocus: true,
              placeholder: 'Board title',
              value: draftTitle,
              onChange: (e) => setDraftTitle(e.target.value),
              onKeyDown: (e) => {
                if (e.key === 'Enter') createBoard()
                else if (e.key === 'Escape') setNewBoardOpen(false)
              }
            }),
            el(Button, { key: 'create', variant: 'default', size: 'sm', onClick: createBoard, disabled: !draftTitle.trim(), children: 'Create' }),
            el(Button, { key: 'cancel', variant: 'ghost', size: 'sm', onClick: () => setNewBoardOpen(false), children: 'Cancel' })
          ]
        : el(Button, { variant: 'secondary', size: 'sm', onClick: () => setNewBoardOpen(true), children: 'New board' }),
      el(Button, {
        variant: 'ghost',
        size: 'sm',
        onClick: () => api('/boards').then(invalidate),
        children: 'Refresh'
      }),
      status ? el('span', { className: 'cr-status' }, status) : null
    ]),

    gateway !== 'open'
      ? el(ErrorState, { title: 'Gateway offline', description: 'Creative Review needs the running gateway for its local backend.' })
      : !board
        ? box('cr-body-single', [
            boardsQuery.error
              ? el(ErrorState, {
                  title: 'Backend unavailable',
                  description: 'The Creative Review backend is not answering. Enable the plugin (hermes plugins enable creative-review) and restart the gateway.'
                })
              : boardsQuery.isLoading
                ? jsx(GlyphSpinner, { ariaLabel: 'Loading' })
                : el(EmptyState, {
                    title: 'No review board yet',
                    description: 'Ask Hermes to generate an image, then it will open a board here — or create one with the field above.'
                  }),
            el(Button, { variant: 'secondary', size: 'sm', onClick: () => setNewBoardOpen(true), children: 'New board' })
          ])
        : box('cr-body', [
            box('cr-col cr-col-side', [
              box('cr-section', [
                box('cr-section-title', 'Versions'),
                el(VersionHistory, { board, currentId, onSelect: setCurrentId })
              ]),
              box('cr-section', [
                box('cr-section-title', 'Reference'),
                el(StageThumb, { image: images.find((im) => im.role === 'reference') || null })
              ])
            ]),
            box('cr-col cr-col-main', [
              el(ImageStage, {
                image: current,
                allowAnnotate: true,
                onAddMarker: (x, y) => addMarker.mutate({ x, y }),
                fitKey
              }),
              box('cr-actions', [
                el(Button, { variant: 'default', size: 'sm', onClick: requestRevision, disabled: !currentId || revisionBusy, loading: revisionBusy, children: 'Request Revision' }),
                el(Button, { variant: 'secondary', size: 'sm', onClick: () => approve.mutate({ decision: 'approved' }), disabled: !currentId, children: 'Approve' }),
                el(Button, { variant: 'ghost', size: 'sm', onClick: () => approve.mutate({ decision: 'rejected' }), disabled: !currentId, children: 'Reject' }),
                el(Button, { variant: 'ghost', size: 'sm', onClick: () => doExport.mutate('json'), disabled: !boardId, children: 'Export JSON' }),
                el(Button, { variant: 'ghost', size: 'sm', onClick: () => doExport.mutate('markdown'), disabled: !boardId, children: 'Export MD' })
              ]),
              el(CompareStrip, { images, leftId, rightId, setLeftId, setRightId })
            ]),
            box('cr-col cr-col-ann', [
              box('cr-section', [
                box('cr-section-title', `Feedback on “${txt(current ? current.label : '')}”`),
                el(AnnotationList, {
                  image: current,
                  onUpdate: (id, note) => updateMarker.mutate({ id, note }),
                  onDelete: removeMarker,
                  onSelect: () => {}
                })
              ]),
              box('cr-section', [
                box('cr-section-title', 'Overall request'),
                el(Textarea, {
                  className: 'cr-overall',
                  rows: 3,
                  placeholder: 'Optional free-text instruction sent with the markers…',
                  value: overallNote,
                  onChange: (e) => setOverallNote(e.target.value)
                })
              ])
            ])
          ])
  ])
}

// ---------------------------------------------------------------------------
// Status-bar chip
// ---------------------------------------------------------------------------
function ReviewChip() {
  const boardsQuery = useBoards()
  const count = boardsQuery.data && boardsQuery.data.ok ? boardsQuery.data.count : 0
  return el(
    Tip,
    {
      label: 'Creative Review — image review boards',
      children: el(
        'button',
        {
          type: 'button',
          className: 'cr-chip',
          onClick: () => {
            haptic('tap')
            host.navigate(PAGE_PATH)
          }
        },
        [
          el('span', { className: 'cr-chip-dot' }),
          el('span', null, count ? `review ${count}` : 'review')
        ]
      )
    }
  )
}

// ---------------------------------------------------------------------------
// styles — prefixed classes, theme tokens only
// ---------------------------------------------------------------------------
const CSS = `
.cr-page{display:flex;flex-direction:column;height:100%;min-height:0;font-family:var(--font-sans,sans-serif);color:var(--ui-text-primary);font-size:12.5px}
.cr-toolbar{display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid var(--ui-stroke-secondary);flex-wrap:wrap}
.cr-toolbar .cr-select{max-width:280px}
.cr-newboard{width:180px}
.cr-page:focus{outline:none}
.cr-select{appearance:none;height:26px;padding:0 8px;border-radius:6px;border:1px solid var(--ui-stroke-secondary);background:var(--ui-bg-control,var(--background));color:var(--ui-text-primary);font:inherit}
.cr-status{margin-left:auto;color:var(--ui-text-secondary);font-size:11.5px;max-width:44%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cr-body{display:grid;grid-template-columns:200px minmax(0,1fr) 300px;gap:0;flex:1;min-height:0}
.cr-body-single{flex:1;display:grid;place-items:center}
.cr-col{min-width:0;min-height:0;display:flex;flex-direction:column;overflow:auto}
.cr-col-side,.cr-col-ann{border-right:1px solid var(--ui-stroke-secondary);background:var(--ui-bg-card,transparent)}
.cr-col-ann{border-right:0;border-left:1px solid var(--ui-stroke-secondary)}
.cr-section{padding:10px 12px;border-bottom:1px solid var(--ui-stroke-secondary)}
.cr-section-title{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.07em;color:var(--ui-text-tertiary);margin-bottom:8px}
.cr-col-main{padding:12px;gap:12px}
.cr-stage{position:relative;overflow:hidden;flex:1;min-height:280px;border:1px solid var(--ui-stroke-secondary);border-radius:10px;background:var(--ui-bg-editor,transparent);cursor:crosshair}
.cr-stage-empty{display:grid;place-items:center;cursor:default}
.cr-stage-inner{position:absolute;inset:0;transform-origin:0 0;will-change:transform}
.cr-frame{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;min-width:0;min-height:0}
.cr-canvas{position:relative;display:flex;max-width:100%;max-height:100%;min-width:0;min-height:0}
.cr-image{display:block;max-width:100%;max-height:100%;width:auto;height:auto;user-select:none}
.cr-image-annotate{cursor:crosshair}
.cr-image-placeholder{position:absolute;inset:0;display:grid;place-items:center;padding:16px;text-align:center}
.cr-markers{position:absolute;inset:0;pointer-events:none}
.cr-marker{position:absolute;transform:translate(-50%,-50%);display:flex;align-items:center;gap:5px}
.cr-marker-dot{display:grid;place-items:center;min-width:20px;height:20px;padding:0 5px;border-radius:10px;background:var(--ui-accent);color:var(--ui-accent-fg,#fff);font-size:11px;font-weight:700;box-shadow:0 0 0 2px var(--background)}
.cr-marker-label{max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px;padding:2px 6px;border-radius:5px;background:var(--ui-bg-card,var(--background));border:1px solid var(--ui-stroke-secondary);color:var(--ui-text-secondary)}
.cr-stage-tools{position:absolute;right:8px;bottom:8px;display:flex;align-items:center;gap:6px;background:var(--ui-bg-card,var(--background));border:1px solid var(--ui-stroke-secondary);border-radius:8px;padding:3px 6px}
.cr-zoom{font-variant-numeric:tabular-nums;color:var(--ui-text-tertiary);font-size:11px;min-width:34px;text-align:right}
.cr-hint{color:var(--ui-text-tertiary)}
.cr-actions{display:flex;flex-wrap:wrap;gap:8px}
.cr-compare{border:1px solid var(--ui-stroke-secondary);border-radius:10px;padding:10px;display:flex;flex-direction:column;gap:8px}
.cr-compare-head{display:flex;align-items:center;gap:12px}
.cr-compare-pickers{display:flex;gap:14px;flex:1;min-width:0}
.cr-picker{display:flex;align-items:center;gap:6px;min-width:0}
.cr-picker-label{color:var(--ui-text-tertiary);font-size:11px}
.cr-compare-body{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.cr-compare-cell{display:flex;flex-direction:column;gap:4px;min-width:0}
.cr-compare-cell-head{font-size:11px;color:var(--ui-text-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cr-thumb{position:relative;aspect-ratio:4/3;border:1px solid var(--ui-stroke-secondary);border-radius:8px;overflow:hidden;display:grid;place-items:center;background:var(--ui-bg-editor,transparent)}
.cr-thumb-empty{color:var(--ui-text-quaternary)}
.cr-thumb-img{width:100%;height:100%;object-fit:contain}
.cr-overlay{display:flex;flex-direction:column;gap:8px}
.cr-overlay-frame{position:relative;aspect-ratio:16/10;border:1px solid var(--ui-stroke-secondary);border-radius:8px;overflow:hidden;background:var(--ui-bg-editor,transparent)}
.cr-overlay-img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}
.cr-range{width:100%;accent-color:var(--ui-accent)}
.cr-versions{display:flex;flex-direction:column;gap:2px}
.cr-version{display:flex;align-items:center;gap:6px;width:100%;text-align:left;background:transparent;border:0;border-radius:6px;padding:5px 8px;color:var(--ui-text-primary);cursor:pointer}
.cr-version:hover{background:var(--chrome-action-hover)}
.cr-version-active{background:var(--chrome-action-hover)}
.cr-version-label{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cr-version-count{color:var(--ui-text-tertiary);font-size:10.5px}
.cr-ann-empty{color:var(--ui-text-tertiary);font-size:11.5px;line-height:1.5}
.cr-ann-list{display:flex;flex-direction:column;gap:8px}
.cr-ann{display:grid;grid-template-columns:22px minmax(0,1fr) auto;grid-auto-rows:min-content;align-items:center;gap:4px 6px;border:1px solid var(--ui-stroke-secondary);border-radius:8px;padding:6px}
.cr-ann-num{display:grid;place-items:center;width:20px;height:20px;border-radius:10px;background:var(--ui-accent);color:var(--ui-accent-fg,#fff);font-size:11px;font-weight:700}
.cr-ann-note{grid-column:2/-1}
.cr-ann-pos{grid-column:2;color:var(--ui-text-tertiary);font-size:10.5px}
.cr-overall{width:100%}
.cr-chip{display:inline-flex;height:100%;align-items:center;gap:4px;padding:0 6px;font-size:.6875rem;color:var(--ui-text-tertiary)}
.cr-chip:hover{color:var(--ui-text-primary);background:var(--chrome-action-hover)}
.cr-chip-dot{width:6px;height:6px;border-radius:3px;background:var(--ui-accent)}
`

function injectStyle() {
  if (typeof document === 'undefined') return function () {}
  const existing = document.getElementById(STYLE_ID)
  if (existing) existing.remove()
  const style = document.createElement('style')
  style.id = STYLE_ID
  style.textContent = CSS
  document.head.append(style)
  return function () { style.remove() }
}

// ---------------------------------------------------------------------------
// registration
// ---------------------------------------------------------------------------
export default {
  id: ID,
  name: 'Creative Review',
  register(ctx) {
    rest = (path, options) => ctx.rest(path, options)
    ctx.onDispose(injectStyle())

    ctx.registerMany([
      {
        id: 'page',
        area: ROUTES_AREA,
        data: { path: PAGE_PATH },
        render: () => jsx(ReviewPage, {})
      },
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        data: { path: PAGE_PATH, label: 'Creative Review', codicon: 'paintcan' }
      },
      {
        id: 'open',
        area: PALETTE_AREA,
        data: {
          id: 'creative-review.open',
          label: 'Open Creative Review',
          keywords: ['image', 'review', 'annotate', 'art', 'design'],
          run: () => host.navigate(PAGE_PATH)
        }
      },
      {
        id: 'chip',
        area: STATUSBAR_AREAS.right,
        order: 140,
        render: () => jsx(ReviewChip, {})
      }
    ])
  }
}