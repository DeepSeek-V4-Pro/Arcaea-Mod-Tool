<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { exportAssetsZip, store, uploadPatch } from '../store'
import { showToast } from '../toast'
import { isImageName, readFileAsDataURL } from '../utils'
import AssetCard from './AssetCard.vue'

const isChar = computed(() => store.filter.sub === 'char')

/* ------------------------------------------------------------ filtering */

const filtered = computed(() => {
  let list = store.assets
  if (store.filter.sub) list = list.filter((a) => a.sub === store.filter.sub)
  if (store.filter.search) {
    const q = store.filter.search
    list = list.filter((a) => a.path.toLowerCase().includes(q))
  }
  if (store.sort === 'size_asc') list = [...list].sort((x, y) => x.size - y.size)
  else if (store.sort === 'size_desc') list = [...list].sort((x, y) => y.size - x.size)
  return list
})

const pages = computed(() => Math.max(1, Math.ceil(filtered.value.length / store.perPage)))

const shown = computed(() => {
  if (isChar.value) return []
  const start = (store.gridPage - 1) * store.perPage
  return filtered.value.slice(start, start + store.perPage)
})

/* 数据变化导致页数缩小时钳制页码 */
watch(pages, (p) => { if (store.gridPage > p) store.gridPage = p })

/* 角色分组视图:按 char_id 分组,组内按形态顺序,全量展示 */
const charGroups = computed(() => {
  const groups = {}
  filtered.value.forEach((a) => {
    const key = a.char_id || '?'
    ;(groups[key] = groups[key] || []).push(a)
  })
  return Object.keys(groups)
    .sort((x, y) => {
      const nx = parseInt(x, 10), ny = parseInt(y, 10)
      return (isNaN(nx) ? 99999 : nx) - (isNaN(ny) ? 99999 : ny)
    })
    .map((id) => ({
      id,
      label: store.charNames[id]?.label || '',
      fullName: store.charNames[id]
        ? (store.charNames[id].label + (store.charNames[id].name ? ' (' + store.charNames[id].name + ')' : ''))
        : '',
      items: groups[id].sort((x, y) => {
        const fx = store.formOrder.indexOf(x.form)
        const fy = store.formOrder.indexOf(y.form)
        return (fx < 0 ? 99 : fx) - (fy < 0 ? 99 : fy) || x.path.localeCompare(y.path)
      }),
    }))
})

const infoText = computed(() => {
  const subLabel = store.filter.sub
    ? (store.subLabels[store.filter.sub] || store.filter.sub) : '全部图片'
  return `${subLabel} · 共 ${filtered.value.length} 张`
})

/* ------------------------------------------------------------ paging */

const goto = ref('')

function jump() {
  const v = parseInt(goto.value, 10)
  if (v >= 1 && v <= pages.value) store.gridPage = v
  goto.value = ''
}

function onKey(e) {
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return
  if (e.key === 'ArrowRight' && store.gridPage < pages.value) store.gridPage++
  else if (e.key === 'ArrowLeft' && store.gridPage > 1) store.gridPage--
}

onMounted(() => document.addEventListener('keydown', onKey))
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))

/* ------------------------------------------------------------ export */

const exporting = ref(false)

async function onExportFiltered() {
  const paths = filtered.value.map((a) => a.path)
  if (!paths.length) {
    showToast('没有可导出的素材', 'warn')
    return
  }
  exporting.value = true
  try {
    await exportAssetsZip(paths)
    showToast(`已导出 ${paths.length} 个素材`)
  } catch (e) {
    showToast('导出失败: ' + e.message, 'err')
  }
  exporting.value = false
}

/* ------------------------------------------------------------ drop file */

async function onDropFile(asset, file) {
  if (!file) return
  if (asset.preview === 'image' && isImageName(file.name)) {
    try {
      const dataUrl = await readFileAsDataURL(file)
      store.incoming = { path: asset.path, name: file.name, dataUrl }
      store.selected = asset.path
    } catch (e) {
      showToast('读取文件失败: ' + e.message, 'err')
    }
  } else {
    try {
      await uploadPatch(asset.path, file, '{}')
      showToast(`已加入替换清单: ${asset.path.split('/').pop()}`)
    } catch (e) {
      showToast('替换失败: ' + e.message, 'err')
    }
  }
}
</script>

<template>
  <div id="toolbar">
    <span class="info">{{ infoText }}</span>
    <button class="btn ghost small" :disabled="exporting || !filtered.length" @click="onExportFiltered">
      {{ exporting ? '打包中…' : `导出 ${filtered.length} 个` }}
    </button>
    <span class="spacer" style="flex:1"></span>
    <template v-if="!isChar">
      <label class="ctl">排序
        <select v-model="store.sort" @change="store.gridPage = 1">
          <option value="path">路径</option>
          <option value="size_asc">大小 ↑</option>
          <option value="size_desc">大小 ↓</option>
        </select>
      </label>
      <label class="ctl">每页
        <select v-model.number="store.perPage" @change="store.gridPage = 1">
          <option v-for="n in [20, 40, 60, 100, 200]" :key="n" :value="n">{{ n }}</option>
        </select>
      </label>
      <button class="btn ghost" :disabled="store.gridPage <= 1" @click="store.gridPage--">◀ 上一页</button>
      <span class="info">{{ store.gridPage }} / {{ pages }}</span>
      <button class="btn ghost" :disabled="store.gridPage >= pages" @click="store.gridPage++">下一页 ▶</button>
      <input v-model="goto" type="text" class="goto" placeholder="页码" title="跳转到页码" @keydown.enter="jump">
      <button class="btn ghost" @click="jump">跳</button>
    </template>
  </div>

  <div id="grid">
    <template v-if="isChar">
      <template v-for="g in charGroups" :key="g.id">
        <div class="group-head" :title="g.fullName">
          角色 {{ g.id }}<template v-if="g.label"> · {{ g.label }}</template>
          <span class="cnt">{{ g.items.length }} 张</span>
        </div>
        <AssetCard v-for="a in g.items" :key="a.path" :asset="a" @drop-file="onDropFile" />
      </template>
    </template>
    <template v-else>
      <div v-if="!shown.length" class="empty">没有匹配的素材</div>
      <AssetCard v-for="a in shown" :key="a.path" :asset="a" @drop-file="onDropFile" />
    </template>
  </div>
</template>

