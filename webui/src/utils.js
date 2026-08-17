/* 通用工具函数 */

/* 缩略图缓存版本:与后端 thumb 缓存 key 的 vN 前缀同步。
   规则变化时 bump 此值,URL 随之变化,浏览器旧缓存(黑底图等)立即失效。 */
export const THUMB_VERSION = 3

export function enc(s) {
  return encodeURIComponent(s)
}

export function fmtSize(n) {
  if (n >= 1 << 20) return (n / (1 << 20)).toFixed(1) + ' MB'
  if (n >= 1 << 10) return (n / (1 << 10)).toFixed(0) + ' KB'
  return n + ' B'
}

export function b64toBlob(b64, type) {
  const bin = atob(b64)
  const arr = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i)
  return new Blob([arr], { type })
}

export function debounce(fn, ms) {
  let timer = null
  return (...args) => {
    clearTimeout(timer)
    timer = setTimeout(() => fn(...args), ms)
  }
}

export function readFileAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

/* 判断文件扩展名是否为可处理的图片 */
export function isImageName(name) {
  return /\.(png|jpe?g|webp|gif|bmp)$/i.test(name)
}

/* 触发浏览器下载 blob */
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
