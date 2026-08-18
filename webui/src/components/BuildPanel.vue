<script setup>
import { computed, ref } from 'vue'

import { api } from '../api'
import { downloadBuildOutput, startBuildPolling, store } from '../store'
import { showToast } from '../toast'

const starting = ref(false)
const isIos = computed(() => store.platform === 'ios')
const enabledCount = computed(() =>
  Object.values(store.patches).filter((p) => p.enabled !== false).length)
const job = computed(() => store.buildJob)
const done = computed(() => job.value?.state === 'done')
const failed = computed(() => job.value?.state === 'error')
const pct = computed(() => Math.round((job.value?.progress || 0) * 100))

async function start() {
  starting.value = true
  try {
    const r = await api('/api/build', { method: 'POST' })
    startBuildPolling(r.job_id)
  } catch (e) {
    showToast('构建启动失败: ' + e.message, 'err')
  }
  starting.value = false
}

function download() {
  if (!done.value || !job.value?.result?.output) return
  downloadBuildOutput(job.value.result.output)
    .catch((e) => showToast('下载失败: ' + e.message, 'err'))
}
</script>

<template>
  <div>
    <div class="pv-title">导出新包</div>
    <div class="pv-meta">
      <template v-if="isIos">
        当前启用 {{ enabledCount }} 个替换条目。构建流程:重打包(原始字节级拷贝)→ 结构校验。
        产物为<b>未签名 IPA</b>,需自行用 Sideloadly / 爱思助手签名安装。
      </template>
      <template v-else>
        当前启用 {{ enabledCount }} 个替换条目。构建流程:重打包(原始字节级拷贝)→ v2 签名 → 校验。
      </template>
    </div>
    <button class="btn primary" style="width:100%"
            :disabled="!enabledCount || store.polling || starting" @click="start">
      {{ store.polling ? '构建中…' : '开始构建' }}
    </button>

    <template v-if="job">
      <div class="progress">
        <div class="bar"><div class="bar-inner" :style="{ width: pct + '%' }"></div></div>
        <span class="pct">{{ pct }}%</span>
      </div>
      <div class="pv-meta" style="margin-top:6px">{{ job.step }}（{{ pct }}%）</div>
      <div class="log">{{ job.log.join('\n') }}</div>

      <div v-if="done" class="result">
        ✅ 构建完成<br>
        输出:{{ job.result.output }}<br>
        大小:{{ job.result.size_human }}（{{ job.result.entries }} 个替换）
        <div v-if="isIos" class="pv-meta" style="margin-top:6px">
          ⚠️ 产物未签名:请用 Sideloadly / 爱思助手签名后安装（免费 Apple ID 签名 7 天有效）。
        </div>
        <button class="btn primary" style="width:100%;margin-top:10px" @click="download">
          {{ isIos ? '下载 IPA' : '下载 APK' }}
        </button>
      </div>
      <div v-else-if="failed" class="err">❌ {{ job.error || '构建失败' }}</div>
    </template>

    <details class="fold" style="margin-top:14px">
      <summary>构建说明</summary>
      <div class="fold-body">
        <template v-if="isIos">
          1. 重打包:仅重新压缩被替换的条目,其余素材原始字节拷贝,速度很快。<br>
          2. 自动移除失效的旧代码签名 _CodeSignature/（越狱 dump 残留,与改动内容不匹配）。<br>
          3. 产物是<b>未签名 IPA</b>:必须用 Sideloadly / 爱思助手以 Apple ID 签名后才能安装（7 天有效）。<br>
          4. iOS 包内没有歌曲音频/谱面/曲目背景,只能改 UI / 角色 / 剧情等静态素材。
        </template>
        <template v-else>
          1. 重打包:仅重新压缩被替换的条目,其余素材原始字节拷贝,速度很快。<br>
          2. 签名:使用本地生成的密钥做 APK v2 签名,不联网。<br>
          3. 产物是重新签名的 APK,与官方签名不同;安装前需卸载原版。<br>
          4. 本工具不触碰 dex / lib / 资源表,只替换素材。
        </template>
      </div>
    </details>
  </div>
</template>
