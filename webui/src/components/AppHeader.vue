<script setup>
import { ref } from 'vue'

import { exportPack, importPack, scan, setStatus, store } from '../store'
import { showToast } from '../toast'

const scanning = ref(false)
const importInput = ref(null)

async function onScan() {
  scanning.value = true
  try {
    const r = await scan()
    setStatus(true, `${r.total} 个素材`)
    showToast(`扫描完成:${r.total} 个素材`)
  } catch (e) {
    setStatus(false, '扫描失败')
    showToast('扫描失败: ' + e.message, true)
  }
  scanning.value = false
}

async function onExport() {
  try {
    await exportPack()
  } catch (e) {
    showToast('导出失败: ' + e.message, true)
  }
}

function triggerImport() {
  importInput.value?.click()
}

async function onImport(e) {
  const f = e.target.files[0]
  e.target.value = ''
  if (!f) return
  try {
    await importPack(f)
  } catch (err) {
    showToast('导入失败: ' + err.message, true)
  }
}
</script>

<template>
  <header>
    <div class="logo">♪</div>
    <div class="title-wrap">
      <h1>Arcaea <span>Mod Tool</span></h1>
      <p id="apk-label">📦 {{ store.cfgApk || '未配置 APK 路径' }}</p>
    </div>
    <div class="status" :class="{ ok: store.statusOk }">
      <span class="dot"></span><span id="status-text">{{ store.statusText }}</span>
    </div>
    <button class="btn ghost" :disabled="scanning" @click="onScan">扫描</button>
    <button class="btn ghost" @click="onExport">导出补丁包</button>
    <button class="btn ghost" @click="triggerImport">导入</button>
    <input ref="importInput" id="import-file" type="file" accept=".zip" hidden @change="onImport">
    <button class="btn ghost" @click="store.tab = 'config'">配置</button>
  </header>
</template>
