<script setup>
import { computed, ref } from 'vue'

import { exportPack, importPack, removePatch, setPatchEnabled, store } from '../store'
import { showToast } from '../toast'
import { fmtSize } from '../utils'

const importInput = ref(null)

const list = computed(() =>
  Object.values(store.patches).sort((a, b) => a.path.localeCompare(b.path)))
const enabledCount = computed(() => list.value.filter((p) => p.enabled !== false).length)

function short(path) {
  return path.split('/').slice(-2).join('/')
}

async function onToggle(p, ev) {
  try {
    await setPatchEnabled(p.path, ev.target.checked)
  } catch (e) {
    showToast('操作失败: ' + e.message, 'err')
  }
}

async function onRemove(p) {
  try {
    await removePatch(p.path)
    showToast('已移除: ' + p.path.split('/').pop())
  } catch (e) {
    showToast('移除失败: ' + e.message, 'err')
  }
}

async function onClear() {
  if (!list.value.length) return
  if (!confirm(`确认清空全部 ${list.value.length} 个补丁?`)) return
  for (const p of [...list.value]) {
    try { await removePatch(p.path) } catch (e) { showToast(e.message, 'err') }
  }
  showToast('已清空补丁列表')
}

function onExportPack() {
  exportPack().catch((e) => showToast('导出失败: ' + e.message, 'err'))
}

async function onImportPack(ev) {
  const f = ev.target.files[0]
  ev.target.value = ''
  if (!f) return
  try { await importPack(f) } catch (e) { showToast('导入失败: ' + e.message, 'err') }
}
</script>

<template>
  <div class="patch-head">
    <div class="patch-title">
      替换清单
      <span class="badge">{{ enabledCount }}/{{ list.length }} 启用</span>
    </div>
    <div class="patch-actions">
      <button class="btn ghost small" :disabled="!list.length" @click="onExportPack">导出包</button>
      <button class="btn ghost small" @click="importInput?.click()">导入</button>
      <input ref="importInput" type="file" accept=".zip" hidden @change="onImportPack">
      <button class="btn ghost small" :disabled="!list.length" @click="onClear">清空</button>
    </div>
  </div>
  <div class="patch-list">
    <div v-if="!list.length" class="empty">
      还没有替换项<br>
      <span style="font-size:12px">去「解包」页拖入新素材,或导入补丁包</span>
    </div>
    <div v-for="p in list" :key="p.path" class="patch-item"
         :class="{ active: store.selPatch === p.path, disabled: p.enabled === false }"
         @click="store.selPatch = p.path">
      <input type="checkbox" :checked="p.enabled !== false"
             :title="p.enabled === false ? '已停用,不参与构建' : '参与构建'"
             @click.stop @change="onToggle(p, $event)">
      <span class="p" :title="p.path">{{ short(p.path) }}</span>
      <span class="sz">{{ fmtSize(p.size) }}</span>
      <button class="x" title="移除补丁" @click.stop="onRemove(p)">✕</button>
    </div>
  </div>
  <div class="patch-hint">勾选 = 参与构建;停用的项不会被打进新包</div>
</template>
