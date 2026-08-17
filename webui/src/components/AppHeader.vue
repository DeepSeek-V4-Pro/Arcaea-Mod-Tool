<script setup>
import { computed, ref } from 'vue'

import { scan, setStatus, store } from '../store'
import { showToast } from '../toast'

const emit = defineEmits(['open-config'])

const scanning = ref(false)
const patchCount = computed(() => Object.keys(store.patches).length)

async function onScan() {
  scanning.value = true
  try {
    const r = await scan()
    setStatus(true, `${r.total} 个素材`)
    showToast(`扫描完成:${r.total} 个素材`)
  } catch (e) {
    setStatus(false, '扫描失败')
    showToast('扫描失败: ' + e.message, 'err')
  }
  scanning.value = false
}
</script>

<template>
  <header>
    <div class="logo">♪</div>
    <div class="title-wrap">
      <h1>Arcaea <span>Mod Tool</span></h1>
      <p id="apk-label">📦 {{ store.cfgApk || '未配置 APK 路径' }}</p>
    </div>

    <!-- 页面导航 -->
    <nav class="nav">
      <button :class="{ active: store.page === 'extract' }" @click="store.page = 'extract'">解包</button>
      <button :class="{ active: store.page === 'replace' }" @click="store.page = 'replace'">
        替换<span v-if="patchCount" class="nav-badge">{{ patchCount }}</span>
      </button>
    </nav>

    <div class="status" :class="{ ok: store.statusOk }">
      <span class="dot"></span><span id="status-text">{{ store.statusText }}</span>
    </div>
    <button class="btn ghost" :disabled="scanning" @click="onScan">扫描</button>
    <button class="btn ghost" @click="emit('open-config')">配置</button>
  </header>
</template>
