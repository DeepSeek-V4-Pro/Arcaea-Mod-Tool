<script setup>
import { onBeforeUnmount, onMounted } from 'vue'

import { api } from './api'
import { loadCatalog, refreshPatches, setStatus, store } from './store'
import AppHeader from './components/AppHeader.vue'
import Sidebar from './components/Sidebar.vue'
import AssetGrid from './components/AssetGrid.vue'
import DetailPanel from './components/DetailPanel.vue'
import BuildPanel from './components/BuildPanel.vue'
import ConfigPanel from './components/ConfigPanel.vue'
import ToastHost from './components/ToastHost.vue'

async function init() {
  try {
    const cfg = await api('/api/config')
    store.cfgApk = cfg.apk_path || ''
    store.cfgOut = cfg.output_dir || ''
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
    <AppHeader />
    <main>
      <Sidebar />
      <section id="browser">
        <AssetGrid />
      </section>
      <section id="panel">
        <div class="tabs">
          <button :class="{ active: store.tab === 'detail' }" @click="store.tab = 'detail'">素材详情</button>
          <button :class="{ active: store.tab === 'build' }" @click="store.tab = 'build'">构建</button>
          <button :class="{ active: store.tab === 'config' }" @click="store.tab = 'config'">配置</button>
        </div>
        <div class="body">
          <DetailPanel v-if="store.tab === 'detail'" />
          <BuildPanel v-else-if="store.tab === 'build'" />
          <ConfigPanel v-else />
        </div>
      </section>
    </main>
    <ToastHost />
  </div>
</template>
