<script setup>
import { toast } from '../toast'
</script>

<template>
  <div id="toast" :class="{ err: toast.isErr }"
       :style="{ display: toast.visible ? 'block' : 'none' }">
    {{ toast.msg }}
  </div>
</template>
