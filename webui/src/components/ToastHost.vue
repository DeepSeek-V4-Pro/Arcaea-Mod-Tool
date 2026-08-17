<script setup>
import { toasts } from '../toast'
</script>

<template>
  <div id="toasts">
    <div v-for="t in toasts" :key="t.id" class="toast" :class="t.kind">{{ t.msg }}</div>
  </div>
</template>
