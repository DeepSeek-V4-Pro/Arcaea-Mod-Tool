<script setup>
import { ref } from 'vue'

defineProps({
  text: { type: String, default: '拖拽文件到这里' },
})
const emit = defineEmits(['file'])

const dragOver = ref(false)
const inputEl = ref(null)

function pick() { inputEl.value?.click() }

function onInput(e) {
  const f = e.target.files[0]
  e.target.value = ''
  if (f) emit('file', f)
}

function onDrop(e) {
  dragOver.value = false
  const f = e.dataTransfer.files[0]
  if (f) emit('file', f)
}
</script>

<template>
  <div class="dropzone" :class="{ dragover: dragOver }"
       @click="pick"
       @dragover.prevent="dragOver = true"
       @dragleave="dragOver = false"
       @drop.prevent.stop="onDrop">
    <input ref="inputEl" type="file" hidden @change="onInput">
    {{ text }}
  </div>
</template>
