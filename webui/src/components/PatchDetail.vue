<script setup>
import { computed } from 'vue'

import { removePatch, store } from '../store'
import { showToast } from '../toast'
import { enc, fmtSize, isImageName } from '../utils'

const patch = computed(() => (store.selPatch ? store.patches[store.selPatch] : null))
const isImage = computed(() => patch.value && isImageName(patch.value.path))
const origUrl = computed(() => (patch.value ? `/api/asset/raw?path=${enc(patch.value.path)}` : ''))
const replUrl = computed(() => (patch.value ? `/api/patch/bytes?path=${enc(patch.value.path)}` : ''))

function gotoExtract() {
  store.selected = patch.value.path
  store.page = 'extract'
}

async function onRemove() {
  if (!patch.value) return
  try {
    await removePatch(patch.value.path)
    showToast('已恢复原素材')
  } catch (e) {
    showToast('移除失败: ' + e.message, 'err')
  }
}
</script>

<template>
  <div v-if="!patch" class="empty">从左侧选择补丁查看详情</div>
  <template v-else>
    <div class="pv-title">{{ patch.path }}</div>
    <div class="pv-meta">
      {{ patch.orig_name || '' }} · {{ fmtSize(patch.size) }}
      <span v-if="patch.enabled === false" style="color:var(--warn)"> · 已停用</span>
      <br v-if="patch.note">{{ patch.note }}
    </div>

    <!-- 图片类补丁:原素材 vs 替换内容对比 -->
    <template v-if="isImage">
      <div class="pv-row">
        <div class="col">
          <div class="pv-meta">原素材</div>
          <img class="pv-img" :src="origUrl">
        </div>
        <div class="col">
          <div class="pv-meta">替换内容</div>
          <img class="pv-img" :src="replUrl">
        </div>
      </div>
    </template>

    <div style="display:flex;gap:8px;margin-top:12px">
      <button class="btn ghost" style="flex:1" @click="gotoExtract">在解包页查看</button>
      <button class="btn danger" style="flex:1" @click="onRemove">移除补丁</button>
    </div>
  </template>
</template>
