<script setup>
/* 自定义下拉组件:视觉参考 GPT-SoVITS-API 的 dselect。
 * 原生 select 隐藏保留语义(仅作数据源),自绘弹层接管交互:
 * 悬停高亮 / ✓ 选中标记 / 禁用项 / 方向键+回车 / Esc / 点击外部关闭。
 * 弹层用 position:fixed 定位,避免被滚动容器裁剪。
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  options: { type: Array, default: () => [] },   // [{value,label,disabled?}] 或裸值
  placeholder: { type: String, default: '请选择' },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'change'])

const opts = computed(() =>
  props.options.map((o) =>
    (typeof o === 'object' && o !== null ? o : { value: o, label: String(o) })))

const current = computed(() => opts.value.find((o) => o.value === props.modelValue))
const label = computed(() => (current.value ? current.value.label : props.placeholder))

const open = ref(false)
const root = ref(null)
const popRef = ref(null)
const hoverIdx = ref(-1)

function toggle() {
  if (props.disabled) return
  open.value ? close() : openPopup()
}

/* 触发点击:忽略 label 重派发给隐藏原生 select 的合成点击,
 * 否则「打开→label 默认行为重派发→再次 toggle→立刻关闭」。 */
function onTrigger(e) {
  if (props.disabled) return
  if (e.target && e.target.classList && e.target.classList.contains('dselect-native')) return
  toggle()
}

function openPopup() {
  open.value = true
  hoverIdx.value = opts.value.findIndex((o) => o.value === props.modelValue)
  nextTick(position)
}

function close() {
  open.value = false
  hoverIdx.value = -1
}

function pick(o) {
  if (o.disabled) return
  if (o.value !== props.modelValue) {
    emit('update:modelValue', o.value)
    emit('change', o.value)
  }
  close()
}

/* 弹层视口内定位:优先向下开,放不下则向上;超宽靠右收敛 */
function position() {
  const el = root.value
  const pop = popRef.value
  if (!el || !pop || !open.value) return
  const r = el.getBoundingClientRect()
  const ph = Math.min(248, Math.max(84, opts.value.length * 34 + 14))
  let top = r.bottom + 6
  let left = r.left
  if (top + ph > window.innerHeight - 8) top = Math.max(8, r.top - ph - 6)
  if (left + Math.max(r.width, 150) > window.innerWidth - 8) {
    left = Math.max(8, window.innerWidth - Math.max(r.width, 150) - 8)
  }
  pop.style.top = top + 'px'
  pop.style.left = left + 'px'
  pop.style.width = Math.max(r.width, 150) + 'px'
}

/* 键盘导航 */
function onKeySelf(e) {
  if (props.disabled) return
  if (['Enter', ' ', 'ArrowDown', 'ArrowUp'].includes(e.key)) {
    e.preventDefault()
    if (!open.value) openPopup()
  }
}

function onDocKey(e) {
  if (!open.value) return
  const enabled = opts.value.map((o, i) => (o.disabled ? -1 : i)).filter((i) => i >= 0)
  if (e.key === 'Escape') close()
  else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault()
    let idx = enabled.indexOf(hoverIdx.value)
    idx = e.key === 'ArrowDown'
      ? Math.min(enabled.length - 1, idx + 1)
      : Math.max(0, idx - 1)
    if (idx >= 0) {
      hoverIdx.value = enabled[idx]
      nextTick(() => {
        const el = popRef.value && popRef.value.querySelector('.dselect-opt.hover')
        el && el.scrollIntoView({ block: 'nearest' })
      })
    }
  } else if (e.key === 'Enter' && hoverIdx.value >= 0) {
    e.preventDefault()
    pick(opts.value[hoverIdx.value])
  }
}

function onDocClick(e) {
  if (!open.value) return
  /* 弹层已 Teleport 到 body:root 之外的点击要区分弹层内部与外部 */
  const inRoot = root.value && root.value.contains(e.target)
  const inPop = popRef.value && popRef.value.contains(e.target)
  if (!inRoot && !inPop) close()
}

watch(open, (v) => {
  if (v) {
    document.addEventListener('click', onDocClick)
    document.addEventListener('keydown', onDocKey)
  } else {
    document.removeEventListener('click', onDocClick)
    document.removeEventListener('keydown', onDocKey)
  }
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onDocKey)
})
</script>

<template>
  <div ref="root" class="dselect" :class="{ open, disabled }" :tabindex="disabled ? -1 : 0"
       role="combobox" :aria-expanded="open ? 'true' : 'false'"
       @click="onTrigger" @keydown="onKeySelf">
    <span class="dselect-label" :class="{ ph: !current }">{{ label }}</span>
    <span class="dselect-arrow"></span>
    <!-- 原生 select 仅作数据源/语义保留 -->
    <select class="dselect-native" :value="modelValue" tabindex="-1" aria-hidden="true">
      <option v-for="o in opts" :key="o.value" :value="o.value">{{ o.label }}</option>
    </select>
    <!-- Teleport 到 body:面板上的 backdrop-filter 会把 fixed 的包含块变成面板,
         导致弹层位置叠加面板偏移;传送到 body 后包含块才是视口 -->
    <Teleport to="body">
      <div v-if="open" ref="popRef" class="dselect-pop">
        <div v-for="(o, i) in opts" :key="o.value" class="dselect-opt"
             :class="{ selected: o.value === modelValue, disabled: o.disabled, hover: hoverIdx === i }"
             @click="pick(o)">{{ o.label }}</div>
      </div>
    </Teleport>
  </div>
</template>
