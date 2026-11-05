// Mount the shipped plugin in real React + jsdom. Only the host SDK boundary is mocked.
import fs from 'node:fs'
import path from 'node:path'
import os from 'node:os'
import { createRequire } from 'node:module'
const repo = process.env.HERMES_AGENT_REPO || path.join(os.homedir(), '.hermes/hermes-agent')
const require = createRequire(path.join(repo, 'package.json'))
const { JSDOM } = require('jsdom')
const dom = new JSDOM('<!doctype html><html><head></head><body><div id="root"></div></body></html>', { url: 'http://localhost' })
Object.assign(globalThis, { window: dom.window, document: dom.window.document, HTMLElement: dom.window.HTMLElement, Event: dom.window.Event, IS_REACT_ACT_ENVIRONMENT: true })
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true })
globalThis.ResizeObserver = class { observe() {} disconnect() {} }
const React = require('react'), { createRoot } = require('react-dom/client'), { act } = React
const tmp = fs.mkdtempSync(path.join(process.env.TMPDIR || os.tmpdir(), 'cr-mounted-'))
const nm = path.join(tmp, 'node_modules'); fs.mkdirSync(nm)
for (const name of ['react', '@tanstack']) fs.symlinkSync(path.join(repo, 'node_modules', name), path.join(nm, name))
const sdk = path.join(nm, '@hermes/plugin-sdk'); fs.mkdirSync(sdk, { recursive: true })
fs.writeFileSync(path.join(sdk, 'package.json'), JSON.stringify({ type: 'module', exports: './index.mjs' }))
fs.writeFileSync(path.join(sdk, 'index.mjs'), `
import React from 'react'; export { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
const atom = v => ({get:()=>v});
export const host = { state:{gateway:atom('open'),profile:atom('default'),connectionId:atom('local'),focusedSessionId:atom('session-a'),focusedSessionProfile:atom('default')}, composer:{submit:(sid,text)=>{globalThis.calls.push(['submit',sid,text]);return globalThis.sendOK},insertText:async(sid,text)=>{globalThis.calls.push(['insert',sid,text]);return true}},navigate:()=>{} };
export const useValue = a => a?.get(); export const cn=(...a)=>a.filter(Boolean).join(' ');export const haptic=()=>{};
const plain=tag=>({children,...p})=>React.createElement(tag,p,children);
export const Button=({variant,size,loading,...p})=>React.createElement('button',p);
export const Input=plain('input'),Textarea=plain('textarea'),Badge=plain('span'),Tip=plain('div');
export const ErrorState=({title,description})=>React.createElement('div',{role:'alert'},title+' '+description);
export const EmptyState=ErrorState,GlyphSpinner=()=>React.createElement('span',null,'loading');
export const ROUTES_AREA='routes',SIDEBAR_NAV_AREA='sidebar.nav',PALETTE_AREA='palette',STATUSBAR_AREAS={right:'statusBar.right'};
`)
fs.copyFileSync(new URL('../desktop/plugin.js', import.meta.url), path.join(tmp, 'plugin.mjs'))
const { QueryClient, QueryClientProvider } = await import(path.join(repo, 'node_modules/@tanstack/react-query/build/modern/index.js'))
const plugin = (await import(path.join(tmp, 'plugin.mjs'))).default
const host = (await import(path.join(sdk, 'index.mjs'))).host
const contributions=[],saved=new Map(); let note='',holdRevision=null,holdSave=null
const image={id:'img-a',label:'Image',role:'generated',exists:true,annotations:[{id:'ann-a',number:1,x:.254,y:.375,note:''}]}
const board={id:'board-a',title:'Test',images:[image]}
globalThis.calls=[];globalThis.sendOK=true
plugin.register({storage:{get:(k,d)=>saved.get(k)??d,set:(k,v)=>saved.set(k,v)},onDispose:()=>{},registerMany:c=>contributions.push(...c),rest:async(p,o)=>{
 calls.push([p,o]);
 if(p==='/boards')return {ok:true,count:1,boards:[{...board,image_count:1}]}
 if(p.startsWith('/board?'))return {ok:true,board}
 if(p.startsWith('/image-data?'))return {ok:true,data_url:'data:image/png;base64,iVBORw0KGgo='}
 if(p==='/annotation'&&o.method==='PATCH'){if(holdSave)await holdSave;note=o.body.note;return {ok:true}}
 if(p==='/revision'){if(holdRevision)await holdRevision;return {ok:true,brief:{markdown:'brief:'+note},revision_id:'rev-a'}}
 return {ok:true}
}})
let count=0
function check(label,condition){if(!condition)throw new Error(label); count++;console.log('ok',label)}
const root=createRoot(document.getElementById('root')),query=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0},mutations:{retry:false,gcTime:0}}})
const tick=()=>new Promise(r=>setTimeout(r,30))
const button=t=>[...document.querySelectorAll('button')].find(x=>x.textContent===t)
try{
 await act(async()=>{root.render(React.createElement(QueryClientProvider,{client:query},contributions.find(c=>c.area==='routes').render()));await tick()})
 for (let n=0;n<8&&!document.querySelector('.cr-stage');n++) await act(async()=>{await tick()})
 check('actual image stage mounts',!!document.querySelector('.cr-stage'))
 check('native desk contribution registered',contributions.some(c=>c.area==='panes'))
 for (let n=0;n<8&&!document.querySelector('.cr-marker');n++) await act(async()=>{await tick()})
 check('marker preserves fractional percentage',document.querySelector('.cr-marker').style.left==='25.4%')
 check('board selection persisted', [...saved.values()].includes('board-a'))
 await act(async()=>{document.querySelector('.cr-stage').dispatchEvent(new dom.window.WheelEvent('wheel',{deltaY:-100,clientX:50,clientY:50,bubbles:true,cancelable:true}))})
 check('wheel zoom changes view',document.querySelector('.cr-zoom').textContent==='115%')
 await act(async()=>{button('Locate').click()})
 // Set intrinsic dimensions so locate has an actual image to center.
 const img=document.querySelector('.cr-image');Object.defineProperties(img,{naturalWidth:{value:1000},naturalHeight:{value:800}})
 await act(async()=>{img.dispatchEvent(new Event('load'));button('Locate').click()})
 check('Locate centers/zooms view',document.querySelector('.cr-zoom').textContent==='200%')
 check('image import is rendered',!!button('Import image'))
 // Simulate blur/save -> click revision. Delayed annotation must settle first.
 let releaseSave;holdSave=new Promise(r=>releaseSave=r)
 const ta=document.querySelector('.cr-ann-note')
 await act(async()=>{const setter=Object.getOwnPropertyDescriptor(dom.window.HTMLTextAreaElement.prototype,'value').set;setter.call(ta,'precise note');ta.dispatchEvent(new Event('input',{bubbles:true}))})
 await act(async()=>{button('Request Revision').click();await tick()})
 check('revision waits for feedback save',!calls.some(c=>c[0]==='/revision'))
 await act(async()=>{releaseSave();await tick();await tick()})
 check('handoff includes freshly saved feedback',calls.some(c=>c[0]==='submit'&&c[2]==='brief:precise note'))
 // Target is captured before the backend awaits. Switching focus must not retarget.
 let releaseRevision;holdRevision=new Promise(r=>releaseRevision=r)
 await act(async()=>{button('Request Revision').click();await tick()})
 host.state.focusedSessionId.get=()=> 'session-b'
 await act(async()=>{releaseRevision();await tick();await tick()})
 check('handoff pins original session',calls.filter(c=>c[0]==='submit').at(-1)[1]==='session-a')
 holdRevision=null;sendOK=false
 await act(async()=>{button('Request Revision').click();await tick();await tick()})
 check('fallback appends rather than overwrites draft',calls.some(c=>c[0]==='insert'))
 // Scope changes cancel the response instead of sending it into another backend.
 sendOK=true
 let releaseScope;holdRevision=new Promise(r=>releaseScope=r)
 const before=calls.filter(c=>c[0]==='submit').length
 await act(async()=>{button('Request Revision').click();await tick()})
 host.state.connectionId.get=()=> 'remote'
 await act(async()=>{releaseScope();await tick();await tick()})
 check('backend switch cancels in-flight handoff',calls.filter(c=>c[0]==='submit').length===before)
 check('cache keys include backend scope',query.getQueryCache().getAll().every(q=>typeof q.queryKey[1]==='string'&&JSON.parse(q.queryKey[1]).length===2))
 host.state.connectionId.get=()=> 'local';holdRevision=null
 // Direct coordinate extraction from the actual mounted handler.
 await act(async()=>{root.render(React.createElement(QueryClientProvider,{client:query},contributions.find(c=>c.area==='routes').render()));await tick()})
 for(let n=0;n<8&&!document.querySelector('.cr-image');n++)await act(async()=>{await tick()})
 const activeImg=document.querySelector('.cr-image')
 activeImg.getBoundingClientRect=()=>({left:100,top:50,width:400,height:200})
 await act(async()=>{activeImg.dispatchEvent(new dom.window.MouseEvent('click',{bubbles:true,clientX:201.6,clientY:125})) ;await tick()})
 check('actual click handler preserves image coordinates',calls.some(c=>c[0]==='/annotation'&&c[1]?.method==='POST'&&c[1].body.x===.254&&c[1].body.y===.375))
 // Import action reaches the actual backend namespace.
 const input=document.querySelector('[aria-label="Image path"]')
 await act(async()=>{Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype,'value').set.call(input,'/local/image.png');input.dispatchEvent(new Event('input',{bubbles:true}))})
 await act(async()=>{button('Import image').click();await tick()})
 check('image import posts path and role',calls.some(c=>c[0]==='/image'&&c[1].body.path==='/local/image.png'&&c[1].body.role==='generated'))
 const submitted=calls.filter(c=>c[0]==='submit').length
 host.state.focusedSessionProfile.get=()=> 'other-profile'
 await act(async()=>{button('Request Revision').click();await tick()})
 check('wrong-profile chat cannot receive revision',calls.filter(c=>c[0]==='submit').length===submitted)
 host.state.focusedSessionProfile.get=()=> 'default'
 const revisionsBefore=calls.filter(c=>c[0]==='/revision').length
 let releaseDouble;holdRevision=new Promise(r=>releaseDouble=r)
 await act(async()=>{button('Request Revision').click();button('Request Revision').click();await tick()})
 check('double-click creates one revision',calls.filter(c=>c[0]==='/revision').length===revisionsBefore+1)
 await act(async()=>{releaseDouble();await tick();await tick()});holdRevision=null

 console.log(count+' mounted React interaction checks passed')
}finally{await act(async()=>root.unmount());query.clear();dom.window.close();fs.rmSync(tmp,{recursive:true,force:true})}
