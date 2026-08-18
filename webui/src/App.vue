<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { api } from './api'
import { loadCatalog, refreshConfig, refreshPatches, setStatus, store } from './store'
import AppHeader from './components/AppHeader.vue'
import ExtractPage from './pages/ExtractPage.vue'
import ReplacePage from './pages/ReplacePage.vue'
import LabPage from './pages/LabPage.vue'
import ConfigDialog from './components/ConfigDialog.vue'
import ToastHost from './components/ToastHost.vue'

const showConfig = ref(false)

async function init() {
  try {
    await refreshConfig()
    await loadCatalog()
    setStatus(true, '已就绪')
  } catch (e) {
    setStatus(false, '未就绪')
  }
  refreshPatches().catch(() => {})
}

onMounted(init)
onBeforeUnmount(() => { store.incoming = null })
</script>

<template>
  <!-- 根容器拦截拖放,防止文件误落到空白处触发浏览器跳转 -->
  <div id="app" @dragover.prevent @drop.prevent>
    <AppHeader @open-config="showConfig = true" />
    <main>
      <ExtractPage v-if="store.page === 'extract'" />
      <ReplacePage v-else-if="store.page === 'replace'" />
      <LabPage v-else />
    </main>
    <ConfigDialog v-if="showConfig" @close="showConfig = false" />
    <ToastHost />
  </div>
</template>
