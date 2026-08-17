<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import { api } from '../api'
import { downloadAsset, refreshPatches, removePatch, store, uploadPatch } from '../store'
import { showToast } from '../toast'
import { b64toBlob, debounce, enc, fmtSize, isImageName, readFileAsDataURL } from '../utils'
import Dropzone from './Dropzone.vue'

const asset = computed(() => store.assets.find((a) => a.path === store.selected) || null)

const patch = computed(() => (store.selected ? store.patches[store.selected] : null))
const subLabel = computed(() => asset.value ? (store.subLabels[asset.value.sub] || asset.value.sub) : '')
/* 角色名:char_id -> {name, label} */
const charInfo = computed(() => {
  if (!asset.value?.char_id) return null
  return store.charNames[asset.value.char_id] || null
})

/* ------------------------------------------------ 素材导出 */

const exporting = ref(false)

async function onDownload() {
  if (!asset.value) return
  exporting.value = true
  try {
    await downloadAsset(asset.value.path)
    showToast('已开始下载')
  } catch (e) {
    showToast('导出失败: ' + e.message, 'err')
  }
  exporting.value = false
}

/* ------------------------------------------------ 图片替换对话框(组件内局部状态) */

const img = reactive({ name: '', dataUrl: '', preview: '', hasImage: false })
const opts = reactive({ keepSize: false, scale: 100, fmt: 'png', quality: 90 })

function settingsPayload() {
  const s = {}
  if (opts.keepSize) s.keep_size = true
  if (opts.scale !== 100) s.scale = opts.scale
  if (opts.fmt !== 'png') s.fmt = opts.fmt
  s.quality = opts.quality
  return s
}

async function refreshPreview() {
  if (!img.hasImage || !asset.value) return
  try {
    const r = await api('/api/patch/process', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        path: asset.value.path,
        orig_ext: '.png',
        data: img.dataUrl.split(',')[1],
        settings: settingsPayload(),
      }),
    })
    img.preview = 'data:image/png;base64,' + r.data
  } catch (e) {
    img.preview = img.dataUrl
  }
}
const refreshPreviewDebounced = debounce(refreshPreview, 350)

/* 选项变化时防抖重新预览 */
watch(opts, refreshPreviewDebounced)

function openImageDialog(name, dataUrl) {
  img.name = name
  img.dataUrl = dataUrl
  img.hasImage = true
  refreshPreview()
}

function closeImageDialog() {
  img.hasImage = false
  img.name = ''
  img.dataUrl = ''
  img.preview = ''
}

async function applyImage() {
  if (!img.hasImage || !asset.value) return
  const settings = settingsPayload()
  const mime = opts.fmt === 'jpg' ? 'image/jpeg' : 'image/png'
  const blob = b64toBlob(img.dataUrl.split(',')[1], mime)
  const file = new File([blob], img.name || asset.value.path.split('/').pop(), { type: mime })
  try {
    await uploadPatch(asset.value.path, file, JSON.stringify(settings))
    closeImageDialog()
    showToast(`已加入替换清单: ${asset.value.path.split('/').pop()}`)
  } catch (e) {
    showToast('替换失败: ' + e.message, 'err')
  }
}

/* ------------------------------------------------ 文件拖入 / 选择 */

async function handleFile(file) {
  if (!file || !asset.value) return
  if (asset.value.preview === 'image' && isImageName(file.name)) {
    try {
      const dataUrl = await readFileAsDataURL(file)
      openImageDialog(file.name, dataUrl)
    } catch (e) {
      showToast('读取文件失败: ' + e.message, 'err')
    }
  } else {
    try {
      await uploadPatch(asset.value.path, file, '{}')
      showToast(`已加入替换清单: ${asset.value.path.split('/').pop()}`)
    } catch (e) {
      showToast('替换失败: ' + e.message, 'err')
    }
  }
}

/* 卡片上拖入的图片经 store.incoming 转交到这里 */
function consumeIncoming() {
  const inc = store.incoming
  if (!inc || !asset.value) return
  if (inc.path === store.selected) openImageDialog(inc.name, inc.dataUrl)
  store.incoming = null
}

/* ------------------------------------------------ 文本编辑 */

const text = ref('')
const textLoading = ref(false)
const textTruncated = ref(false)
const textSize = ref(0)

async function loadText() {
  if (!asset.value || asset.value.preview !== 'text') return
  textLoading.value = true
  try {
    const r = await api(`/api/asset/text?path=${enc(asset.value.path)}&limit=500000`)
    text.value = r.text
    textSize.value = r.size
    textTruncated.value = r.truncated
  } catch (e) {
    text.value = ''
    textTruncated.value = false
  }
  textLoading.value = false
}

async function saveText() {
  if (!asset.value) return
  try {
    await api('/api/patch/text', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ path: asset.value.path, text: text.value }),
    })
    await refreshPatches()
    showToast('文本补丁已保存')
  } catch (e) {
    showToast('保存失败: ' + e.message, 'err')
  }
}

/* ------------------------------------------------ 补丁移除 */

const removing = ref(false)

async function onRemovePatch() {
  if (!asset.value) return
  removing.value = true
  try {
    await removePatch(asset.value.path)
    showToast('已恢复原素材')
  } catch (e) {
    showToast('移除失败: ' + e.message, 'err')
  }
  removing.value = false
}

/* 跳转替换页并选中当前补丁 */
function gotoReplace() {
  if (!asset.value) return
  store.selPatch = asset.value.path
  store.page = 'replace'
}

/* ------------------------------------------------ 同角色跳转 */

const charLinks = computed(() => {
  const a = asset.value
  if (!a || !a.char_id) return []
  const outs = []
  store.assets.forEach((b) => {
    if (b.path === a.path || b.char_id !== a.char_id) return
    outs.push({ path: b.path, label: store.formLabels[b.form] || b.form })
  })
  return outs.slice(0, 8)
})

/* ------------------------------------------------ 生命周期 */

onMounted(() => {
  consumeIncoming()
  if (asset.value?.preview === 'text') loadText()
})
onBeforeUnmount(closeImageDialog)

watch(() => store.selected, () => {
  closeImageDialog()
  if (asset.value?.preview === 'text') loadText()
})
watch(() => store.incoming, consumeIncoming)
</script>

<template>
  <div>
    <div v-if="!asset" class="empty">点击左侧素材查看详情</div>

    <template v-else>
      <div class="pv-title">{{ asset.path }}</div>
      <div class="pv-meta">
        {{ asset.human_size }} · {{ subLabel }}
        <template v-if="charInfo">
          · 角色 {{ asset.char_id }} {{ charInfo.label }}
          <span v-if="charInfo.name">({{ charInfo.name }})</span>
        </template>
        <span v-if="patch" style="color:var(--accent)"> · 已替换</span>
      </div>

      <div class="pv-actions">
        <button class="btn ghost small" :disabled="exporting" @click="onDownload">
          {{ exporting ? '导出中…' : '导出此素材' }}
        </button>
        <button v-if="patch" class="btn ghost small" @click="gotoReplace">前往「替换」页管理</button>
      </div>

      <!-- 同角色素材联动 -->
      <div v-if="charLinks.length" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px">
        <button v-for="c in charLinks" :key="c.path" class="btn ghost"
                style="padding:5px 10px;font-size:12px" @click="store.selected = c.path">{{ c.label }}</button>
      </div>

      <!-- 图片:处理对话框 / 普通预览 -->
      <template v-if="asset.preview === 'image'">
        <template v-if="img.hasImage">
          <div class="pv-row">
            <div class="col">
              <div class="pv-meta">原素材</div>
              <img class="pv-img" :src="`/api/asset/raw?path=${enc(asset.path)}`">
            </div>
            <div class="col">
              <div class="pv-meta">你的素材</div>
              <img class="pv-img" :src="img.dataUrl">
            </div>
            <div class="col">
              <div class="pv-meta">处理后预览</div>
              <img class="pv-img" :src="img.preview">
            </div>
          </div>
          <label class="set"><input v-model="opts.keepSize" type="checkbox"> 保持原始尺寸（拉伸）</label>
          <label class="set">缩放 %<input v-model.number="opts.scale" type="number" min="1" max="400"></label>
          <label class="set">输出格式
            <select v-model="opts.fmt">
              <option value="png">PNG（保留透明）</option>
              <option value="jpg">JPG（更小）</option>
            </select>
          </label>
          <label v-if="opts.fmt === 'jpg'" class="set">JPG 质量<input v-model.number="opts.quality" type="number" min="1" max="100"></label>
          <button class="btn primary" style="width:100%" @click="applyImage">应用此图片替换</button>
          <Dropzone text="拖拽或点击更换素材文件" @file="handleFile" />
        </template>
        <template v-else>
          <div class="pv-row">
            <img class="pv-img" :src="`/api/asset/raw?path=${enc(asset.path)}`" style="max-width:100%">
          </div>
          <Dropzone text="拖拽图片/文件到这里替换，或点击选择" @file="handleFile" />
        </template>
      </template>

      <!-- 音频 -->
      <template v-else-if="asset.preview === 'audio'">
        <audio controls preload="metadata" :src="`/api/asset/raw?path=${enc(asset.path)}`"></audio>
        <Dropzone text="拖拽音频/文件到这里替换" @file="handleFile" />
      </template>

      <!-- 文本 -->
      <template v-else-if="asset.preview === 'text'">
        <textarea v-model="text" class="txt" :placeholder="textLoading ? '加载中…' : ''"></textarea>
        <div v-if="textTruncated" class="pv-meta" style="margin-top:6px">
          （文件 {{ fmtSize(textSize) }}，仅显示前 500KB）
        </div>
        <button class="btn primary" style="width:100%;margin-top:8px" @click="saveText">保存文本补丁</button>
        <button class="btn ghost" style="width:100%;margin-top:6px" @click="loadText">恢复原文</button>
        <div class="pv-meta" style="margin-top:8px">
          提示：修改 songlist / characters.json 等数据需自行承担风险；纯本地显示类修改安全。
        </div>
      </template>

      <!-- 其他类型 -->
      <template v-else>
        <Dropzone text="拖拽文件到这里替换" @file="handleFile" />
      </template>

      <!-- 当前补丁 -->
      <div v-if="patch" style="margin-top:12px;border-top:1px solid var(--line);padding-top:10px">
        <div class="pv-meta">
          当前补丁：{{ patch.orig_name || '' }}（{{ fmtSize(patch.size) }}）<br v-if="patch.note">{{ patch.note }}
        </div>
        <button class="btn danger" style="width:100%" :disabled="removing" @click="onRemovePatch">
          移除补丁，恢复原素材
        </button>
      </div>
    </template>
  </div>
</template>
