<script setup>
import { computed, ref } from 'vue'

import { api } from '../api'
import { startBuildPolling, store } from '../store'
import { showToast } from '../toast'

const starting = ref(false)
const patchCount = computed(() => Object.keys(store.patches).length)
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
    showToast('构建启动失败: ' + e.message, true)
  }
  starting.value = false
}
</script>

<template>
  <div>
    <div class="pv-title">构建改包</div>
    <div class="pv-meta">
      当前 {{ patchCount }} 个替换条目。构建流程：重打包（原始字节级拷贝）→ v2 签名 → 校验。
    </div>
    <button class="btn primary" style="width:100%"
            :disabled="!patchCount || store.polling || starting" @click="start">
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
        输出：{{ job.result.output }}<br>
        大小：{{ job.result.size_human }}（{{ job.result.entries }} 个替换）
      </div>
      <div v-else-if="failed" class="err">❌ {{ job.error || '构建失败' }}</div>
    </template>
  </div>
</template>
