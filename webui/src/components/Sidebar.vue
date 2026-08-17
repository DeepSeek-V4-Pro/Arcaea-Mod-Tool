<script setup>
import { computed } from 'vue'

import { store } from '../store'

const search = computed({
  get: () => store.filter.search,
  set: (v) => { store.filter.search = v; store.gridPage = 1 },
})

const counts = computed(() => store.catalog?.sub_counts || {})

function pick(sub) {
  store.filter.sub = sub
  store.gridPage = 1
}
</script>

<template>
  <aside>
    <div class="filter"><input v-model="search" placeholder="搜索素材路径…"></div>
    <div class="cats">
      <div class="cat" :class="{ active: store.filter.sub === null }" @click="pick(null)">
        <span class="dot image"></span>全部图片
        <span class="cnt">{{ store.assets.length }}</span>
      </div>
      <div v-for="s in store.subs" :key="s.id"
           class="cat sub" :class="{ active: store.filter.sub === s.id }" @click="pick(s.id)">
        <span class="dot subdot"></span>{{ s.label }}
        <span class="cnt">{{ counts[s.id] || 0 }}</span>
      </div>
    </div>
  </aside>
</template>

