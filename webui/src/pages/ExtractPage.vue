<script setup>
import Sidebar from '../components/Sidebar.vue'
import AssetGrid from '../components/AssetGrid.vue'
import DetailPanel from '../components/DetailPanel.vue'
</script>

<template>
  <!-- 解包页:素材浏览 / 预览 / 导出 -->
  <Sidebar />
  <section id="browser">
    <AssetGrid />
  </section>
  <section id="panel">
    <div class="panel-title">素材预览</div>
    <div class="body">
      <DetailPanel />
    </div>
  </section>
</template>
