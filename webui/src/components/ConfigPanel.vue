<script setup>
import { ref } from 'vue'

import { api } from '../api'
import { scan, setStatus, store } from '../store'
import { showToast } from '../toast'

const apk = ref(store.cfgApk)
const out = ref(store.cfgOut)
const saving = ref(false)

async function save() {
  const cfg = { apk_path: apk.value.trim(), output_dir: out.value.trim() }
  saving.value = true
  try {
    await api('/api/config', {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(cfg),
    })
    store.cfgApk = cfg.apk_path
    store.cfgOut = cfg.output_dir
    const r = await scan()
    setStatus(true, `${r.total} 个素材`)
    showToast('配置已保存，已重新扫描')
  } catch (e) {
    showToast('保存失败: ' + e.message, true)
  }
  saving.value = false
}
</script>

<template>
  <div>
    <div class="pv-title">配置</div>
    <div class="cfg-row">
      <label>APK 文件路径</label>
      <input v-model="apk" type="text">
    </div>
    <div class="cfg-row">
      <label>输出目录</label>
      <input v-model="out" type="text">
    </div>
    <button class="btn primary" style="width:100%" :disabled="saving" @click="save">
      保存并重新扫描
    </button>
    <div class="pv-meta" style="margin-top:12px">
      提示：<br>
      1. 修改 2D 素材/音频/文本为纯本地行为，不触发服务器检测。<br>
      2. 构建会生成一个重新签名（v2）的 APK，卸载原版后安装即可。<br>
      3. 本工具不触碰 dex / lib / 资源表，只替换素材。
    </div>
  </div>
</template>
