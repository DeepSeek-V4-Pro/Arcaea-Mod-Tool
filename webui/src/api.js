/* 与后端交互的 fetch 封装:非 2xx 抛错(优先取 FastAPI 的 detail 信息) */

export async function api(url, opts = {}) {
  const r = await fetch(url, opts)
  if (!r.ok) {
    let msg = r.statusText
    try { msg = (await r.json()).detail || msg } catch (e) { /* 保留 statusText */ }
    throw new Error(msg)
  }
  const ct = r.headers.get('content-type') || ''
  return ct.includes('json') ? r.json() : r
}
