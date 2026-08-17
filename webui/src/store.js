/* 全局状态仓库:页面导航、素材目录、补丁、构建任务 */

import { reactive } from 'vue'

import { api } from './api'
import { downloadBlob } from './utils'
import { showToast } from './toast'

export const store = reactive({
  // 页面导航:extract(解包页) | replace(替换页)
  page: 'extract',

  // 素材目录
  catalog: null,
  assets: [],
  subs: [],                 // [{id, label}]
  subLabels: {},
  formLabels: {},
  formOrder: [],
  charNames: {},            // char_id -> {name, label, search}

  // 解包页视图状态
  filter: { sub: null, search: '' },
  selected: null,           // 当前选中的素材路径
  sort: 'path',             // path | size_asc | size_desc
  perPage: 20,
  gridPage: 1,              // 素材网格分页页码
  exportSel: [],            // 勾选待导出的素材路径列表

  // 替换页视图状态
  selPatch: null,           // 当前选中的补丁路径

  // 补丁
  patches: {},              // path -> patch meta(含 enabled)

  // 配置
  cfgApk: '',
  cfgOut: '',

  // 状态栏
  statusOk: false,
  statusText: '就绪',

  // 构建任务(轮询快照)与轮询标记
  buildJob: null,           // {id, state, step, progress, log[], error, result}
  polling: false,

  // 图片替换流:卡片拖入图片后转交详情面板的数据
  incoming: null,           // {path, name, dataUrl}
})

export function setStatus(ok, text) {
  store.statusOk = ok
  store.statusText = text
}

/* ---------------------------------------------------------------- catalog */

export async function loadCatalog() {
  const cat = await api('/api/catalog')
  store.catalog = cat
  store.assets = cat.assets
  store.subs = cat.subs || []
  store.subLabels = {}
  store.subs.forEach((s) => { store.subLabels[s.id] = s.label })
  store.formLabels = cat.form_labels || {}
  store.formOrder = cat.form_order || []
  store.charNames = cat.char_names || {}
  store.gridPage = 1
}

export async function scan() {
  const r = await api('/api/scan', { method: 'POST' })
  await loadCatalog()
  return r
}

/* ---------------------------------------------------------------- patches */

export async function refreshPatches() {
  const list = await api('/api/patches')
  store.patches = {}
  list.forEach((p) => { store.patches[p.path] = p })
  if (store.selPatch && !store.patches[store.selPatch]) store.selPatch = null
}

export async function uploadPatch(path, file, settingsJson) {
  const fd = new FormData()
  fd.append('path', path)
  fd.append('file', file)
  fd.append('settings_json', settingsJson)
  await api('/api/patch', { method: 'PUT', body: fd })
  await refreshPatches()
}

export async function removePatch(path) {
  await api('/api/patch?path=' + encodeURIComponent(path), { method: 'DELETE' })
  await refreshPatches()
}

export async function setPatchEnabled(path, enabled) {
  await api('/api/patch/enabled', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ path, enabled }),
  })
  if (store.patches[path]) store.patches[path].enabled = enabled
}

/* ---------------------------------------------------------------- export */

/** 批量导出素材 zip(当前筛选结果等)。 */
export async function exportAssetsZip(paths) {
  const r = await fetch('/api/assets/export', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ paths }),
  })
  if (!r.ok) {
    let msg = r.statusText
    try { msg = (await r.json()).detail || msg } catch (e) { /* keep */ }
    throw new Error(msg)
  }
  downloadBlob(await r.blob(), 'arcaea_assets.zip')
}

/** 下载单个素材。 */
export async function downloadAsset(path) {
  const r = await fetch('/api/asset/download?path=' + encodeURIComponent(path))
  if (!r.ok) {
    let msg = r.statusText
    try { msg = (await r.json()).detail || msg } catch (e) { /* keep */ }
    throw new Error(msg)
  }
  downloadBlob(await r.blob(), path.split('/').pop() || 'asset.bin')
}

/** 下载构建产物 mod APK。 */
export async function downloadBuildOutput(path) {
  const r = await fetch('/api/output/download?path=' + encodeURIComponent(path))
  if (!r.ok) {
    let msg = r.statusText
    try { msg = (await r.json()).detail || msg } catch (e) { /* keep */ }
    throw new Error(msg)
  }
  downloadBlob(await r.blob(), path.split('/').pop() || 'mod.apk')
}

/* ---------------------------------------------------------------- build */

let _buildTimer = null

export function startBuildPolling(jobId) {
  stopBuildPolling()
  store.buildJob = {
    id: jobId, state: 'running', step: '启动中…', progress: 0,
    log: [], error: '', result: null,
  }
  store.polling = true
  _buildTimer = setInterval(async () => {
    try {
      const j = await api(`/api/build/${jobId}`)
      store.buildJob = { ...store.buildJob, ...j }
      if (j.state === 'done' || j.state === 'error') stopBuildPolling()
    } catch (e) {
      store.buildJob = { ...store.buildJob, state: 'error', error: e.message }
      stopBuildPolling()
    }
  }, 700)
}

export function stopBuildPolling() {
  if (_buildTimer) { clearInterval(_buildTimer); _buildTimer = null }
  store.polling = false
}

/* ---------------------------------------------------------------- packs */

export async function exportPack() {
  const r = await api('/api/pack/export', { method: 'POST' })
  showToast(`已导出: ${r.file}`)
}

export async function importPack(file) {
  const fd = new FormData()
  fd.append('file', file)
  const r = await api('/api/pack/import', { method: 'POST', body: fd })
  await refreshPatches()
  showToast(`导入 ${r.imported} 个补丁`)
}

