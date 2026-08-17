/* 全局 toast 状态 */

import { reactive } from 'vue'

export const toast = reactive({
  msg: '',
  isErr: false,
  visible: false,
  _timer: null,
})

export function showToast(msg, isErr = false) {
  toast.msg = msg
  toast.isErr = isErr
  toast.visible = true
  clearTimeout(toast._timer)
  toast._timer = setTimeout(() => { toast.visible = false }, 4000)
}
