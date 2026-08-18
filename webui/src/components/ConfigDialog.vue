<script setup>
import { computed, ref } from 'vue'

import { api } from '../api'
import { scan, setStatus, store } from '../store'
import { showToast } from '../toast'

const emit = defineEmits(['close'])

const isIos = computed(() => store.platform === 'ios')
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
    showToast('配置已保存,已重新扫描')
    emit('close')
  } catch (e) {
    showToast('保存失败: ' + e.message, 'err')
  }
  saving.value = false
}
</script>

<template>
  <div class="modal-mask" @click.self="emit('close')">
    <div class="modal">
      <div class="modal-title">配置</div>
      <div class="cfg-row">
        <label>{{ isIos ? 'IPA 文件路径' : 'APK 文件路径' }}</label>
        <input v-model="apk" type="text"
               :placeholder="isIos ? '留空时自动识别 input/(支持 .ipa / 外层 .zip);填路径按文件类型判定' : '留空时自动识别项目 input/ 目录中的原包'">
      </div>
      <div class="cfg-row">
        <label>输出目录</label>
        <input v-model="out" type="text">
      </div>
      <button class="btn primary" style="width:100%" :disabled="saving" @click="save">
        保存并重新扫描
      </button>
      <div class="pv-meta" style="margin-top:12px">
        1. 把 APK / IPA / 外层 zip 放进项目 <b>input/</b> 目录即自动识别,无需手填路径;<br>
        2. 手动填路径时按文件类型自动判定平台(.apk→Android,.ipa/.zip→iOS),无需先切换模式;<br>
        <template v-if="isIos">
          3. iOS 原包需为<b>越狱 dump 的解密 IPA</b>(官方 App Store 包是 FairPlay 加密,无法直接改)。<br>
          4. 构建产出<b>未签名 IPA</b>,需用 Sideloadly / 爱思助手签名安装(7 天有效)。<br>
          5. 平台模式可在「实验」页查看与切换。
        </template>
        <template v-else>
          3. 修改 2D 素材/音频/文本为纯本地行为,不触发服务器检测。<br>
          4. 构建会生成重新签名(v2)的 APK,卸载原版后安装即可。
        </template>
      </div>
    </div>
  </div>
</template>
