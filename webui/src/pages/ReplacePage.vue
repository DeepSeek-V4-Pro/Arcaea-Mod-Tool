<script setup>
import PatchList from '../components/PatchList.vue'
import PatchDetail from '../components/PatchDetail.vue'
import BuildPanel from '../components/BuildPanel.vue'
</script>

<template>
  <!-- 替换页:补丁清单(确认要替换的部分) + 详情预览 + 构建导出新包 -->
  <aside id="patch-side">
    <PatchList />
  </aside>
  <section id="browser" class="replace-main">
    <div class="replace-detail">
      <PatchDetail />
    </div>
    <div class="replace-build">
      <BuildPanel />
    </div>
  </section>
</template>
