/**
 * Desktop-half registration harness.
 *
 * Loads desktop/plugin.js exactly as the Electron renderer would (plain ESM,
 * uncompiled) with stubbed '@hermes/plugin-sdk', 'react' and
 * 'react/jsx-runtime' modules, then drives `register(ctx)` with a recording
 * context and asserts the contributions the pane declares.
 *
 * Run:  node tests/desktop_harness.mjs
 */
import { mkdtempSync, mkdirSync, writeFileSync, copyFileSync, rmSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const PLUGIN_JS = join(HERE, '..', 'desktop', 'plugin.js')

const SDK_STUB = `
export const host = {
  state: {
    gateway: { get: () => 'open' },
    profile: { get: () => 'default' }, connectionId: { get: () => 'local' },
    focusedSessionId: { get: () => 'sess-test' },
    busyBySession: { get: () => ({}) }
  },
  notify: () => 1,
  navigate: () => {},
  composer: {
    submit: () => false,
    setDraft: async () => false,
    insertText: async () => false,
    getDraft: async () => null,
    focus: () => {}
  }
}
export const haptic = () => {}
export const cn = (...a) => a.filter(Boolean).join(' ')
export const useValue = (atom) => (atom && atom.get ? atom.get() : undefined)
export const useQuery = () => ({ data: undefined, error: undefined, isLoading: false })
export const useMutation = () => ({ mutate: () => {}, mutateAsync: async () => ({}) })
export const useQueryClient = () => ({ invalidateQueries: () => {} })
export const queryClient = { invalidateQueries: () => {} }
export const atom = (v) => ({ get: () => v, set: () => {}, subscribe: () => () => {} })
export const computed = (fn) => ({ get: fn })
const noop = () => null
export const Badge = noop, Button = noop, Input = noop, Textarea = noop, Tip = noop
export const EmptyState = noop, ErrorState = noop, GlyphSpinner = noop, StatusDot = noop
export const Separator = noop, Switch = noop, Codicon = noop
export const icons = {}
export const PANES_AREA = 'panes'
export const ROUTES_AREA = 'routes'
export const SIDEBAR_NAV_AREA = 'sidebar.nav'
export const STATUSBAR_AREAS = { left: 'statusBar.left', right: 'statusBar.right' }
export const PALETTE_AREA = 'palette'
export const KEYBINDS_AREA = 'keybinds'
export const THEMES_AREA = 'themes'
`

const REACT_STUB = `
export const useEffect = () => {}
export const useMemo = (fn) => fn()
export const useRef = (v) => ({ current: v })
export const useState = (v) => [typeof v === 'function' ? v() : v, () => {}]
export const useCallback = (fn) => fn
export default { createElement: () => null }
`

const JSXRUNTIME_STUB = `
export const jsx = (type, props) => ({ type, props })
export const jsxs = (type, props) => ({ type, props })
export const Fragment = Symbol('Fragment')
`

const tmp = mkdtempSync(join(tmpdir(), 'cr-desktop-'))
let pass = 0
let fail = 0
const check = (label, cond, detail = '') => {
  if (cond) { pass++; console.log(`  ok   ${label}`) }
  else { fail++; console.log(`  FAIL ${label} ${detail}`) }
}

try {
  const nm = join(tmp, 'node_modules')
  const write = (spec, body, fname = 'index.mjs') => {
    const dir = join(nm, spec)
    mkdirSync(dir, { recursive: true })
    writeFileSync(join(dir, fname), body)
    return dir
  }
  write('@hermes/plugin-sdk', SDK_STUB)
  writeFileSync(join(nm, '@hermes', 'plugin-sdk', 'package.json'),
    JSON.stringify({ name: '@hermes/plugin-sdk', type: 'module', exports: { '.': './index.mjs' } }))
  const reactDir = write('react', REACT_STUB)
  write('react', JSXRUNTIME_STUB, 'jsx-runtime.mjs')
  writeFileSync(join(reactDir, 'package.json'), JSON.stringify({
    name: 'react',
    type: 'module',
    exports: { '.': './index.mjs', './jsx-runtime': './jsx-runtime.mjs' }
  }))

  const pluginCopy = join(tmp, 'plugin.mjs')
  copyFileSync(PLUGIN_JS, pluginCopy)

  const mod = await import(pluginCopy)
  const plugin = mod.default
  console.log('Creative Review — desktop registration harness\n')

  check('default export has id creative-review', plugin.id === 'creative-review', `(id=${plugin.id})`)
  check('exports the page path', mod.PAGE_PATH === '/creative-review', `(path=${mod.PAGE_PATH})`)
  check('register is a function', typeof plugin.register === 'function')

  const contributions = []
  const disposers = []
  const ctx = {
    rest: async () => ({ ok: true }),
    register: (c) => { contributions.push(c); return () => {} },
    registerMany: (cs) => { cs.forEach((c) => contributions.push(c)); return () => {} },
    onDispose: (fn) => { disposers.push(fn); return () => {} },
    onEvent: () => () => {},
    registerSettingsPage: () => () => {},
    i18n: { register: () => {}, t: (k) => k }
  }

  plugin.register(ctx)

  const byArea = Object.fromEntries(contributions.map((c) => [c.area, c]))
  check('registers a full page route', !!byArea['routes'])
  check('route path is /creative-review', byArea['routes'] && byArea['routes'].data.path === '/creative-review')
  check('route renders a component', byArea['routes'] && typeof byArea['routes'].render === 'function')
  check('registers a sidebar nav row', !!byArea['sidebar.nav'])
  check('nav points at the page', byArea['sidebar.nav'] && byArea['sidebar.nav'].data.path === '/creative-review')
  check('registers a palette command', !!byArea['palette'])
  check('palette command runs without throwing', (() => {
    try { byArea['palette'].data.run(); return true } catch { return false }
  })())
  check('registers a status-bar chip', !!byArea['statusBar.right'])
  check('chip returns a React descriptor (not mounted)', (() => {
    try { return !!byArea['statusBar.right'].render() } catch { return false }
  })())
  check('page returns a React descriptor (not mounted)', (() => {
    try { return !!byArea['routes'].render() } catch { return false }
  })())
  check('registers a dispose hook (style teardown)', disposers.length >= 1)
  check('registered five contributions', contributions.length === 5, `(got ${contributions.length})`)

  // Regression guards for bugs found in review: these must never come back.
  const source = readFileSync(PLUGIN_JS, 'utf8')
  check('no window.prompt (Electron does not implement it)',
    !/window\.prompt\s*\(/.test(source))
  check('no invalid Button variant (primary/accent/good are not in the kit)',
    !/variant:\s*'(primary|accent|good)'/.test(source))
  check('no invalid Badge variant (accent/good are not in the kit)',
    !/Badge[^)]*variant:\s*'(accent|good)'/.test(source))
  check('revision handoff uses host.composer.submit',
    /host\.composer\.submit\(/.test(source))
  check('no raw DOM reach into app markup',
    !/document\.querySelector/.test(source))

  console.log(`\n${pass} passed, ${fail} failed`)
} catch (error) {
  console.error('harness error:', error && error.stack ? error.stack : error)
  fail++
} finally {
  rmSync(tmp, { recursive: true, force: true })
}

process.exit(fail ? 1 : 0)