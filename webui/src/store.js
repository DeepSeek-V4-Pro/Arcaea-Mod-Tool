/* 全局状态仓库:目录、补丁、视图状态、构建任务 */

import { reactive } from 'vue'

import { api } from './api'
import { showToast } from './toast'

export const store = reactive({
  // 素材目录
  catalog: null,
  assets: [],
  subs: [],                 // [{id, label}]
  subLabels: {},
  formLabels: {},
  formOrder: [],
  charNames: {},            // char_id -> {name, label, search}

  // 视图状态
  filter: { sub: null, search: '' },
  selected: null,           // 当前选中的素材路径
  sort: 'path',             // path | size_asc | size_desc
  perPage: 20,
  page: 1,
  tab: 'detail',            // detail | build | config

  // 补丁
  patches: {},              // path -> patch meta

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
  store.page = 1
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
