<script setup>
/* 实验功能控制台:iOS 模式(实验性)的启用/切换与状态展示。
 *
 * iOS 模式能力边界:
 *   ✅ 解包浏览 / 替换素材 / 最终重打包(产出未签名 IPA)
 *   ❌ 原包获取(需用户自备越狱 dump 的解密 IPA)
 *   ❌ 签名安装(需用户用 Sideloadly / 爱思助手等 Apple 签名链自行完成)
 */

import { computed, onMounted, ref } from 'vue'

import { api } from '../api'
import { scan, setPlatform, store } from '../store'
import { showToast } from '../toast'

const status = ref(null)       // /api/lab/status 快照
const statusErr = ref('')
const switching = ref(false)

const isIos = computed(() => store.platform === 'ios')

const iosOn = computed(() => status.value?.platform === 'ios')

const pkgFound = computed(() => !!status.value?.pkg_found)
const pkgSize = computed(() => status.value?.pkg_size_human || '')
const candidateCount = computed(() => {
  const c = status.value?.input_candidates || {}
  return (c.apk?.length || 0) + (c.ipa?.length || 0) + (c.zip?.length || 0)
})

async function loadStatus() {
  statusErr.value = ''
  try {
    status.value = await api('/api/lab/status')
  } catch (e) {
    statusErr.value = e.message
  }
}

async function toggle(p) {
  if (switching.value) return
  switching.value = true
  try {
    await setPlatform(p)
    showToast(p === 'ios'
      ? '已启用 iOS 模式,素材目录已刷新'
      : '已切回 Android 模式,素材目录已刷新')
  } catch (e) {
    showToast('切换失败: ' + e.message, 'err')
  } finally {
    await loadStatus()
  }
  switching.value = false
}

async function onRescan() {
  try {
    const r = await scan()
    showToast(`扫描完成:${r.total} 个素材`)
  } catch (e) {
    showToast('扫描失败: ' + e.message, 'err')
  }
}

/** 清空手动配置的原包路径,改回 input/ 目录自动识别。 */
async function onUseInput() {
  if (switching.value) return
  switching.value = true
  try {
    await api('/api/config', {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ apk_path: '' }),
    })
    await loadStatus()
    showToast('已清除手动配置,改用 input/ 目录自动识别')
  } catch (e) {
    showToast('操作失败: ' + e.message, 'err')
  }
  switching.value = false
}

onMounted(loadStatus)
</script>

<template>
  <section id="lab">
    <div class="lab-head">
      <div>
        <div class="pv-title">实验功能控制台</div>
        <div class="pv-meta">
          实验性功能与正式功能相互独立,按需启用;切换平台后「解包 / 替换 / 构建」页面
          会立即针对当前平台工作。
        </div>
      </div>
      <span class="lab-chip" :class="{ on: iosOn }">
        {{ iosOn ? 'iOS 模式已启用' : 'Android 模式' }}
      </span>
    </div>

    <!-- iOS 模式卡片 -->
    <div class="lab-card">
      <div class="lab-card-title">
        🍎 iOS 模式（实验性）
        <span class="lab-tag">解包 · 替换 · 重打包</span>
      </div>

      <div class="pv-meta" style="margin-top:8px">
        IPA 本质就是 zip,素材树位于 <b>Payload/&lt;App&gt;.app/</b> 下,与 Android
        <code>assets/</code> 逐字节同构 —— 扫描 / 分类 / 替换 / 重打包全部复用现有引擎。
        <br>
        与 Android 流程的两处不同,均需自行处理:
      </div>

      <div class="lab-grid">
        <div class="lab-step">
          <div class="lab-step-no">1</div>
          <div>
            <b>原包自备</b>
            <div class="pv-meta">
              官方 App Store 包是 FairPlay 加密的,无法直接改。需先在越狱设备上
              dump 出解密版 IPA(TrollStore → Dopamine → AppsDump 流程),放入项目
              <code>input/</code> 目录,或在「配置」中填写路径。
              <template v-if="status?.inner_ipa">
                <br>已识别外层 zip 内的 IPA:{{ status.inner_ipa.name }}（{{ status.inner_ipa.size_human }}）
              </template>
            </div>
          </div>
        </div>
        <div class="lab-step">
          <div class="lab-step-no">2</div>
          <div>
            <b>签名自做</b>
            <div class="pv-meta">
              工具产出的是<b>未签名 IPA</b>(并自动移除失效的旧代码签名)。安装请用
              Sideloadly / 爱思助手等工具以 Apple ID 签名(免费签名 7 天有效,到期重签)。
            </div>
          </div>
        </div>
      </div>

      <!-- 状态区 -->
      <div class="lab-status">
        <div class="row"><span>生效模式</span><b>{{ iosOn ? 'iOS' : 'Android' }}</b></div>
        <div class="row"><span>原包来源</span>
          <b>{{ status?.pkg_source === 'input' ? 'input/ 自动识别' : status?.pkg_source === 'configured' ? '手动配置' : '—' }}</b>
        </div>
        <div class="row"><span>原包路径</span><code :class="{ miss: !pkgFound }">{{ status?.apk_path || '未找到' }}</code></div>
        <div class="row"><span>包大小</span><b>{{ pkgSize || '—' }}</b></div>
        <div class="row"><span>素材根目录</span><code>{{ status?.app_root || '—' }}</code></div>
        <div class="row"><span>目录缓存</span><b>{{ status?.catalog_ready ? '已就绪' : '未扫描' }}</b></div>
      </div>
      <div v-if="status?.pkg_note" class="lab-warn">ℹ {{ status.pkg_note }}</div>
      <div v-if="status?.resolve_error" class="lab-warn">⚠ 原包解析失败:{{ status.resolve_error }}</div>
      <div v-if="statusErr" class="lab-warn">⚠ 状态查询失败:{{ statusErr }}</div>

      <!-- input/ 候选清单 -->
      <div v-if="candidateCount" class="lab-cands">
        <div class="pv-meta" style="margin-bottom:6px">
          📂 <b>input/</b> 目录已识别 {{ candidateCount }} 个候选,自动取当前平台最大的一个
        </div>
        <div v-for="(items, kind) in status?.input_candidates" :key="kind">
          <template v-if="items.length">
            <div class="lab-cand-kind">
              {{ kind === 'apk' ? 'APK' : kind === 'ipa' ? 'IPA' : '外层 zip' }}
              <span class="cnt">{{ items.length }}</span>
            </div>
            <div v-for="c in items" :key="c.name" class="lab-cand">
              <span class="dot" :class="kind"></span>{{ c.name }}
              <span class="sz">{{ c.size_human }}</span>
            </div>
          </template>
        </div>
      </div>

      <div class="lab-actions">
        <button class="btn primary" :disabled="switching || iosOn" @click="toggle('ios')">
          {{ switching ? '切换中…' : '启用 iOS 模式' }}
        </button>
        <button class="btn ghost" :disabled="switching || !iosOn" @click="toggle('android')">
          切回 Android 模式
        </button>
        <button v-if="status?.pkg_source === 'configured'" class="btn ghost"
                :disabled="switching" @click="onUseInput">改用 input/ 自动识别</button>
        <button class="btn ghost" :disabled="!pkgFound" @click="onRescan">重新扫描素材</button>
      </div>

      <details class="fold" style="margin-top:14px">
        <summary>使用步骤</summary>
        <div class="fold-body">
          1. 准备解密 IPA:越狱设备上安装官方 Arcaea 后用 AppsDump 导出(或使用暗改包分发 zip,工具会自动解出内层 IPA)。<br>
          2. 将原包放入项目 <b>input/</b> 目录:APK / IPA / 外层 zip 均可自动识别,无需配置路径
             (也支持在「配置」中手动填写路径,按文件类型自动判定平台)。<br>
          3. 确认「生效模式」符合预期(仅放了一种包时会自动跟随),点「解包」扫描浏览素材;
             「替换」页替换素材(与 Android 完全一致的操作)。<br>
          4. 「替换」页构建,产物为 <b>未签名 IPA</b>(已移除旧代码签名)。<br>
          5. 用 Sideloadly / 爱思助手签名安装;免费 Apple ID 签名 7 天有效,到期需重签。
        </div>
      </details>

      <details class="fold">
        <summary>注意事项</summary>
        <div class="fold-body">
          1. iOS 包内<b>没有歌曲内容</b>(音频 / 谱面 / 曲目背景均不打包,运行时下载),能改的只有 UI / 角色 / 剧情等静态素材。<br>
          2. 谱面背景替换需通过「文件共享」把素材注入 App 沙盒下载目录,不属于改包流程。<br>
          3. 改包登录官方服务器有风控(24h 内两台设备登录会触发封禁);推分后建议同步回官方版。<br>
          4. 请先阅读 <a href="/docs/iOS实验模式.md" target="_blank">iOS 实验模式文档</a> 与
          <a href="/docs/免责声明与注意事项.md" target="_blank">免责声明</a>。
        </div>
      </details>
    </div>
  </section>
</template>
