/* 全局 toast:多态(ok/err/warn)堆叠展示,最多保留 4 条 */

import { reactive } from 'vue'

export const toasts = reactive([])  // [{id, msg, kind}]

let _seq = 0

export function showToast(msg, kind = 'ok') {
  const id = ++_seq
  toasts.push({ id, msg, kind })
  if (toasts.length > 4) toasts.shift()
  setTimeout(() => {
    const i = toasts.findIndex((t) => t.id === id)
    if (i >= 0) toasts.splice(i, 1)
  }, 4000)
}
