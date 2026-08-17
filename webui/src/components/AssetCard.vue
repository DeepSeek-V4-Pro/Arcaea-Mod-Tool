<script setup>
import { computed, ref } from 'vue'

import { store } from '../store'
import { enc, THUMB_VERSION } from '../utils'

const props = defineProps({
  asset: { type: Object, required: true },
})
const emit = defineEmits(['drop-file'])

const broken = ref(false)
const dragOver = ref(false)
const patched = computed(() => !!store.patches[props.asset.path])
const checked = computed(() => store.exportSel.includes(props.asset.path))

function shortName(path) {
  return path.startsWith('assets/songs/')
    ? path.slice('assets/songs/'.length)
    : path.split('/').slice(-2).join('/')
}

function onDrop(e) {
  dragOver.value = false
  emit('drop-file', props.asset, e.dataTransfer.files[0])
}

function select() {
  store.selected = props.asset.path
}

function onToggleCheck() {
  const i = store.exportSel.indexOf(props.asset.path)
  if (i >= 0) store.exportSel.splice(i, 1)
  else store.exportSel.push(props.asset.path)
}
</script>

<template>
  <div class="card" :class="{ patched, selected: checked, 'has-sel': store.exportSel.length, dragover: dragOver }" :data-path="asset.path"
       @click="select"
       @dragover.prevent="dragOver = true"
       @dragleave="dragOver = false"
       @drop.prevent.stop="onDrop">
    <input type="checkbox" class="check" :checked="checked" title="勾选后导出"
           @click.stop @change="onToggleCheck">
    <img v-if="!broken && asset.preview === 'image'" class="thumb" loading="lazy"
         :src="`/api/asset/thumb?path=${enc(asset.path)}&max=256&v=${THUMB_VERSION}`"
         :alt="asset.path" @error="broken = true">
    <div v-else class="icon">🖼️</div>
    <div v-if="patched" class="badge">已替换</div>
    <div class="size">{{ asset.human_size }}</div>
    <div class="name" :title="asset.path">{{ shortName(asset.path) }}</div>
  </div>
</template>
