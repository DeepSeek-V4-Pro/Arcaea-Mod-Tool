/* Arcaea Mod Tool — frontend logic (vanilla JS, no build step) */
"use strict";

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

const state = {
  catalog: null,
  assets: [],
  filter: { sub: null, search: "" },
  selected: null,           // asset path
  patches: {},              // path -> patch meta
  tab: "detail",
  buildJob: null,
  buildTimer: null,
  page: 1,
  perPage: 20,
  sort: "path",             // path | size_asc | size_desc
  subs: [],                 // [{id, label}]
  formLabels: {},
  formOrder: [],
};

const CAT_LABEL = { image: "图片 (2D)" };
const CAT_DOT = { image: "image" };

async function api(url, opts = {}) {
  const r = await fetch(url, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (e) { }
    throw new Error(msg);
  }
  const ct = r.headers.get("content-type") || "";
  return ct.includes("json") ? r.json() : r;
}

/* ------------------------------------------------------------- init */

async function init() {
  bindEvents();
  try {
    const cfg = await api("/api/config");
    $("#apk-label").textContent = "📦 " + (cfg.apk_path || "");
    await loadCatalog();
    setStatus(true, "已就绪");
  } catch (e) {
    $("#tb-info").textContent = "⚠ " + e.message;
    setStatus(false, "未就绪");
  }
  refreshPatches();
}

function setStatus(ok, text) {
  const s = $("#status");
  s.classList.toggle("ok", !!ok);
  $("#status-text").textContent = text;
}

async function loadCatalog() {
  const cat = await api("/api/catalog");
  state.catalog = cat;
  state.assets = cat.assets;
  state.subs = cat.subs || [];
  state.subLabels = {};
  state.subs.forEach((s) => { state.subLabels[s.id] = s.label; });
  state.formLabels = cat.form_labels || {};
  state.formOrder = cat.form_order || [];
  state.page = 1;
  renderCats();
  renderGrid();
}

function bindEvents() {
  $("#search").addEventListener("input", (e) => {
    state.filter.search = e.target.value.trim().toLowerCase();
    state.page = 1;
    renderGrid();
  });
  $("#btn-scan").addEventListener("click", async () => {
    $("#btn-scan").disabled = true;
    try {
      const r = await api("/api/scan", { method: "POST" });
      await loadCatalog();
      $("#tb-info").textContent = `扫描完成：${r.total} 个素材`;
      setStatus(true, `${r.total} 个素材`);
    } catch (e) { $("#tb-info").textContent = "⚠ " + e.message; setStatus(false, "扫描失败"); }
    $("#btn-scan").disabled = false;
  });
  $("#btn-export").addEventListener("click", exportPack);
  $("#btn-import").addEventListener("click", () => $("#import-file").click());
  $("#import-file").addEventListener("change", importPack);
  $("#btn-cfg").addEventListener("click", () => switchTab("config"));
  $$("#panel .tabs button").forEach((b) =>
    b.addEventListener("click", () => switchTab(b.dataset.tab)));
  // grid-level drag & drop (fallback: drop on cards)
  $("#grid").addEventListener("dragover", (e) => e.preventDefault());
  $("#grid").addEventListener("drop", (e) => e.preventDefault());
  // keyboard paging: ← / → flips pages
  document.addEventListener("keydown", (e) => {
    if (e.target && ["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) return;
    if (e.key === "ArrowRight") {
      const n = $("#pg-next");
      if (n && !n.disabled) n.click();
    } else if (e.key === "ArrowLeft") {
      const p = $("#pg-prev");
      if (p && !p.disabled) p.click();
    }
  });
}

/* ------------------------------------------------------------- catalog */

function renderCats() {
  const box = $("#cats");
  box.innerHTML = "";
  const counts = state.catalog.sub_counts || {};
  const all = document.createElement("div");
  all.className = "cat" + (state.filter.sub === null ? " active" : "");
  all.innerHTML = `<span class="dot image"></span>全部图片
    <span class="cnt">${state.assets.length}</span>`;
  all.addEventListener("click", () => {
    state.filter.sub = null;
    state.page = 1;
    renderCats();
    renderGrid();
  });
  box.appendChild(all);
  state.subs.forEach((s) => {
    const el = document.createElement("div");
    el.className = "cat sub" + (state.filter.sub === s.id ? " active" : "");
    el.innerHTML = `<span class="dot subdot"></span>${s.label}
      <span class="cnt">${counts[s.id] || 0}</span>`;
    el.addEventListener("click", () => {
      state.filter.sub = s.id;
      state.page = 1;
      renderCats();
      renderGrid();
    });
    box.appendChild(el);
  });
}

function filtered() {
  let list = state.assets;
  if (state.filter.sub) {
    list = list.filter((a) => a.sub === state.filter.sub);
  }
  if (state.filter.search) {
    list = list.filter((a) => a.path.toLowerCase().includes(state.filter.search));
  }
  if (state.sort === "size_asc") {
    list = [...list].sort((x, y) => x.size - y.size);
  } else if (state.sort === "size_desc") {
    list = [...list].sort((x, y) => y.size - x.size);
  }
  return list;
}

function makeCard(a) {
  const card = document.createElement("div");
  card.className = "card" + (state.patches[a.path] ? " patched" : "");
  card.dataset.path = a.path;
  const patched = state.patches[a.path];
  let inner = "";
  if (a.preview === "image") {
    inner = `<img class="thumb" loading="lazy" src="/api/asset/thumb?path=${enc(a.path)}&max=256">`;
  } else {
    inner = `<div class="icon">🖼️</div>`;
  }
  if (patched) inner += `<div class="badge">已替换</div>`;
  const short = a.path.startsWith("assets/songs/")
    ? a.path.slice("assets/songs/".length)
    : a.path.split("/").slice(-2).join("/");
  card.innerHTML = inner +
    `<div class="size">${a.human_size}</div><div class="name" title="${a.path}">${short}</div>`;
  card.addEventListener("click", () => selectAsset(a.path));
  card.addEventListener("dragover", (e) => {
    e.preventDefault();
    e.stopPropagation();
    card.classList.add("dragover");
  });
  card.addEventListener("dragleave", () => card.classList.remove("dragover"));
  card.addEventListener("drop", (e) => {
    e.preventDefault();
    e.stopPropagation();
    card.classList.remove("dragover");
    const f = e.dataTransfer.files[0];
    if (f) handleDropFile(a.path, f);
  });
  return card;
}

/* 角色分组渲染：char 分类下按 char_id 分组，组内按形态排序，全量展示 */
function renderCharGroups() {
  const grid = $("#grid");
  const list = filtered();
  const groups = {};
  list.forEach((a) => {
    const key = a.char_id || "?";
    (groups[key] = groups[key] || []).push(a);
  });
  const ids = Object.keys(groups).sort((x, y) => {
    const nx = parseInt(x, 10), ny = parseInt(y, 10);
    return (isNaN(nx) ? 99999 : nx) - (isNaN(ny) ? 99999 : ny);
  });
  grid.innerHTML = "";
  ids.forEach((id) => {
    const items = groups[id].sort((x, y) => {
      const fx = state.formOrder.indexOf(x.form);
      const fy = state.formOrder.indexOf(y.form);
      return (fx < 0 ? 99 : fx) - (fy < 0 ? 99 : fy) || x.path.localeCompare(y.path);
    });
    const head = document.createElement("div");
    head.className = "group-head";
    head.innerHTML = `角色 ${id}<span class="cnt">${items.length} 张</span>`;
    grid.appendChild(head);
    items.forEach((a) => grid.appendChild(makeCard(a)));
  });
}

function renderGrid() {
  const grid = $("#grid");
  const list = filtered();
  if (state.filter.sub === "char") {
    // 角色分类：按角色分组，全量展示（98 组 ≈ 420 张，DOM 可控）
    const groups = {};
    list.forEach((a) => { groups[a.char_id || "?"] = 1; });
    const ids = Object.keys(groups);
    const tb = $("#toolbar");
    tb.innerHTML = `
      <span class="info">角色立绘 · ${ids.length} 个角色 · ${list.length} 张</span>
      <span class="spacer" style="flex:1"></span>
      <span class="info">点卡片看详情，可跳转同角色的头像/觉醒形态</span>`;
    renderCharGroups();
    return;
  }
  const pages = Math.max(1, Math.ceil(list.length / state.perPage));
  if (state.page > pages) state.page = pages;
  const start = (state.page - 1) * state.perPage;
  const shown = list.slice(start, start + state.perPage);
  const subLabel = state.filter.sub
    ? (state.subLabels[state.filter.sub] || state.filter.sub) : "全部图片";

  // toolbar: paging + sort + info
  const tb = $("#toolbar");
  tb.innerHTML = `
    <span class="info">${subLabel} · 共 ${list.length} 张</span>
    <span class="spacer" style="flex:1"></span>
    <label style="font-size:12px;color:var(--dim)">排序
      <select id="sort-sel">
        <option value="path"${state.sort === "path" ? " selected" : ""}>路径</option>
        <option value="size_asc"${state.sort === "size_asc" ? " selected" : ""}>大小 ↑</option>
        <option value="size_desc"${state.sort === "size_desc" ? " selected" : ""}>大小 ↓</option>
      </select>
    </label>
    <label style="font-size:12px;color:var(--dim)">每页
      <select id="per-sel">
        <option value="20"${state.perPage === 20 ? " selected" : ""}>20</option>
        <option value="40"${state.perPage === 40 ? " selected" : ""}>40</option>
        <option value="60"${state.perPage === 60 ? " selected" : ""}>60</option>
        <option value="100"${state.perPage === 100 ? " selected" : ""}>100</option>
        <option value="200"${state.perPage === 200 ? " selected" : ""}>200</option>
      </select>
    </label>
    <button class="btn ghost" id="pg-prev" ${state.page <= 1 ? "disabled" : ""}>◀ 上一页</button>
    <span class="info" id="pg-info">${state.page} / ${pages}</span>
    <button class="btn ghost" id="pg-next" ${state.page >= pages ? "disabled" : ""}>下一页 ▶</button>
    <input type="text" id="pg-goto" style="width:52px" placeholder="页码" title="跳转到页码">
    <button class="btn ghost" id="pg-go">跳</button>`;
  $("#sort-sel").addEventListener("change", (e) => {
    state.sort = e.target.value;
    state.page = 1;
    renderGrid();
  });
  $("#per-sel").addEventListener("change", (e) => {
    state.perPage = +e.target.value;
    state.page = 1;
    renderGrid();
  });
  $("#pg-prev").addEventListener("click", () => {
    if (state.page > 1) { state.page--; renderGrid(); }
  });
  $("#pg-next").addEventListener("click", () => {
    if (state.page < pages) { state.page++; renderGrid(); }
  });
  $("#pg-go").addEventListener("click", () => {
    const v = parseInt($("#pg-goto").value, 10);
    if (v >= 1 && v <= pages) { state.page = v; renderGrid(); }
  });
  $("#pg-goto").addEventListener("keydown", (e) => {
    if (e.key === "Enter") $("#pg-go").click();
  });

  // grid
  grid.innerHTML = "";
  if (!shown.length) {
    grid.innerHTML = `<div class="empty">没有匹配的素材</div>`;
    return;
  }
  shown.forEach((a) => grid.appendChild(makeCard(a)));
}

function enc(s) { return encodeURIComponent(s); }

/* ------------------------------------------------------------- patches */

async function refreshPatches() {
  try {
    const list = await api("/api/patches");
    state.patches = {};
    list.forEach((p) => { state.patches[p.path] = p; });
    $$(".card").forEach((c) => {
      const p = c.dataset.path;
      c.classList.toggle("patched", !!state.patches[p]);
    });
    if (state.selected) renderDetail();
  } catch (e) { console.warn(e); }
}

async function handleDropFile(path, file) {
  const isImage = /\.(png|jpe?g|webp|gif|bmp)$/i.test(path);
  if (isImage && /\.(png|jpe?g|webp|gif|bmp)$/i.test(file.name)) {
    // show processing dialog with preview
    const reader = new FileReader();
    reader.onload = async () => {
      const preview = await imageProcessPreview(path, file.name, reader.result, {});
      openImageDialog(path, file.name, reader.result, preview);
    };
    reader.readAsDataURL(file);
  } else {
    await uploadPatch(path, file, "{}");
  }
}

async function uploadPatch(path, file, settingsJson) {
  const fd = new FormData();
  fd.append("path", path);
  fd.append("file", file);
  fd.append("settings_json", settingsJson);
  try {
    await api("/api/patch", { method: "PUT", body: fd });
    await refreshPatches();
    renderGrid();
    toast(`已替换: ${path.split("/").pop()}`);
  } catch (e) {
    toast("替换失败: " + e.message, true);
  }
}

async function imageProcessPreview(path, origName, dataUrl, settings) {
  const base64 = dataUrl.split(",")[1];
  const r = await api("/api/patch/process", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ path, orig_ext: ".png", data: base64, settings }),
  });
  return "data:image/png;base64," + r.data;
}

let dialogFile = null;
let dialogName = "";
let dialogDataUrl = "";
let dialogPreview = "";

function openImageDialog(path, name, dataUrl, preview) {
  dialogFile = null; dialogName = name; dialogDataUrl = dataUrl; dialogPreview = preview;
  switchTab("detail");
  state.selected = path;
  renderDetail(true);
}

/* ------------------------------------------------------------- detail */

function selectAsset(path) {
  state.selected = path;
  switchTab("detail");
  renderDetail(false);
}

function switchTab(tab) {
  state.tab = tab;
  $$("#panel .tabs button").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === tab));
  if (tab === "detail") renderDetail(false);
  else if (tab === "build") renderBuild();
  else renderConfig();
}

function currentAsset() {
  return state.assets.find((a) => a.path === state.selected) || null;
}

function renderDetail(forceImageDialog) {
  const body = $("#panel-body");
  const a = currentAsset();
  if (!a) {
    body.innerHTML = `<div class="empty">点击左侧素材查看详情</div>`;
    return;
  }
  const patch = state.patches[a.path];
  const subLabel = (state.subLabels && state.subLabels[a.sub]) || a.sub || "";
  let html = `<div class="pv-title">${a.path}</div>
    <div class="pv-meta">${a.human_size} · ${subLabel}${patch ? " · <span style='color:var(--accent)'>已替换</span>" : ""}</div>`;

  // 角色素材联动：显示同角色的头像/立绘/觉醒/高清跳转
  const charLinks = charLinkAssets(a.path);
  if (charLinks.length) {
    html += `<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px">` +
      charLinks.map((c) =>
        `<button class="btn ghost" style="padding:5px 10px;font-size:12px" data-goto="${enc(c.path)}">${c.label}</button>`
      ).join("") + `</div>`;
  }

  if (forceImageDialog && dialogDataUrl) {
    html += `<div class="pv-row">
        <div class="col"><div class="pv-meta">原素材</div><img class="pv-img" src="/api/asset/raw?path=${enc(a.path)}"></div>
        <div class="col"><div class="pv-meta">你的素材</div><img class="pv-img" src="${dialogDataUrl}"></div>
        <div class="col"><div class="pv-meta">处理后预览</div><img class="pv-img" src="${dialogPreview}"></div>
      </div>
      <label class="set"><input type="checkbox" id="opt-keep"> 保持原始尺寸（拉伸）</label>
      <label class="set">缩放 %<input type="number" id="opt-scale" value="100" min="1" max="400"></label>
      <label class="set">输出格式
        <select id="opt-fmt"><option value="png">PNG（保留透明）</option><option value="jpg">JPG（更小）</option></select></label>
      <label class="set" id="opt-q-wrap">JPG 质量<input type="number" id="opt-quality" value="90" min="1" max="100"></label>
      <button class="btn primary" id="btn-apply-img" style="width:100%">应用此图片替换</button>
      <div class="dropzone" id="dz-dialog"><input type="file" id="file-dialog">拖拽或点击更换素材文件</div>`;
  } else if (a.preview === "image") {
    html += `<div class="pv-row">
        <img class="pv-img" src="/api/asset/raw?path=${enc(a.path)}" style="max-width:100%"></div>
      <div class="dropzone" id="dz"><input type="file" id="file">拖拽图片/文件到这里替换，或点击选择</div>`;
  } else if (a.preview === "audio") {
    html += `<audio controls preload="metadata" src="/api/asset/raw?path=${enc(a.path)}"></audio>
      <div class="dropzone" id="dz"><input type="file" id="file">拖拽音频/文件到这里替换</div>`;
  } else if (a.preview === "text") {
    html += `<textarea class="txt" id="txt-edit" placeholder="加载中…"></textarea>
      <button class="btn primary" id="btn-save-txt" style="width:100%;margin-top:8px">保存文本补丁</button>
      <button class="btn ghost" id="btn-reset-txt" style="width:100%;margin-top:6px">恢复原文</button>
      <div class="pv-meta" style="margin-top:8px">提示：修改 songlist / characters.json 等数据需自行承担风险；纯本地显示类修改安全。</div>`;
  } else {
    html += `<div class="dropzone" id="dz"><input type="file" id="file">拖拽文件到这里替换</div>`;
  }

  if (patch) {
    html += `<div style="margin-top:12px;border-top:1px solid var(--line);padding-top:10px">
      <div class="pv-meta">当前补丁：${patch.orig_name || ""}（${fmtSize(patch.size)}）${patch.note ? "<br>" + patch.note : ""}</div>
      <button class="btn danger" id="btn-remove-patch" style="width:100%">移除补丁，恢复原素材</button>
    </div>`;
  }
  body.innerHTML = html;

  // char link buttons
  $$("[data-goto]").forEach((b) =>
    b.addEventListener("click", () => selectAsset(decodeURIComponent(b.dataset.goto))));
  // events
  const dz = $("#dz");
  if (dz) {
    const fi = $("#file");
    dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("dragover"); });
    dz.addEventListener("dragleave", () => dz.classList.remove("dragover"));
    dz.addEventListener("drop", (e) => {
      e.preventDefault(); dz.classList.remove("dragover");
      const f = e.dataTransfer.files[0];
      if (f) handleDetailDrop(a, f);
    });
    dz.addEventListener("click", () => fi.click());
    fi.addEventListener("change", () => {
      if (fi.files[0]) handleDetailDrop(a, fi.files[0]);
    });
  }
  const dz2 = $("#dz-dialog");
  if (dz2) {
    const fi = $("#file-dialog");
    dz2.addEventListener("dragover", (e) => { e.preventDefault(); dz2.classList.add("dragover"); });
    dz2.addEventListener("dragleave", () => dz2.classList.remove("dragover"));
    dz2.addEventListener("drop", (e) => {
      e.preventDefault(); dz2.classList.remove("dragover");
      const f = e.dataTransfer.files[0];
      if (f) readFileAsDataURL(f);
    });
    dz2.addEventListener("click", () => fi.click());
    fi.addEventListener("change", () => { if (fi.files[0]) readFileAsDataURL(fi.files[0]); });
  }
  const apply = $("#btn-apply-img");
  if (apply) {
    apply.addEventListener("click", async () => {
      const settings = {};
      if ($("#opt-keep") && $("#opt-keep").checked) settings.keep_size = true;
      if ($("#opt-scale") && +$("#opt-scale").value !== 100) settings.scale = +$("#opt-scale").value;
      const fmt = $("#opt-fmt") ? $("#opt-fmt").value : "png";
      if (fmt !== "png") settings.fmt = fmt;
      settings.quality = +($("#opt-quality").value || 90);
      const base64 = dialogDataUrl.split(",")[1];
      const blob = b64toBlob(base64, fmt === "jpg" ? "image/jpeg" : "image/png");
      const file = new File([blob], dialogName, { type: blob.type });
      await uploadPatch(a.path, file, JSON.stringify(settings));
      dialogDataUrl = ""; dialogPreview = "";
    });
  }
  const saveTxt = $("#btn-save-txt");
  if (saveTxt) {
    loadText(a.path);
    saveTxt.addEventListener("click", async () => {
      try {
        await api("/api/patch/text", {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ path: a.path, text: $("#txt-edit").value }),
        });
        await refreshPatches();
        toast("文本补丁已保存");
      } catch (e) { toast("保存失败: " + e.message, true); }
    });
    $("#btn-reset-txt").addEventListener("click", loadText.bind(null, a.path));
  }
  const rm = $("#btn-remove-patch");
  if (rm) {
    rm.addEventListener("click", async () => {
      await api("/api/patch?path=" + enc(a.path), { method: "DELETE" });
      await refreshPatches();
      renderGrid();
      renderDetail(false);
      toast("已恢复原素材");
    });
  }
}

/* 同角色跳转：同 char_id 的其他形态（立绘/头像/觉醒立绘/觉醒头像/高清） */
function charLinkAssets(path) {
  const a = currentAsset();
  if (!a || !a.char_id) return [];
  const outs = [];
  state.assets.forEach((b) => {
    if (b.path === path || b.char_id !== a.char_id) return;
    const label = state.formLabels[b.form] || b.form;
    outs.push({ path: b.path, label });
  });
  return outs.slice(0, 8);
}

function handleDetailDrop(a, file) {
  const isImage = a.preview === "image" && /\.(png|jpe?g|webp|gif|bmp)$/i.test(file.name);
  if (isImage) {
    readFileAsDataURL(file);
  } else {
    uploadPatch(a.path, file, "{}");
  }
}

function readFileAsDataURL(file) {
  const reader = new FileReader();
  reader.onload = async () => {
    dialogName = file.name;
    dialogDataUrl = reader.result;
    try {
      dialogPreview = await imageProcessPreview(state.selected, file.name, reader.result, {});
    } catch (e) { dialogPreview = reader.result; }
    renderDetail(true);
  };
  reader.readAsDataURL(file);
}

async function loadText(path) {
  try {
    const r = await api(`/api/asset/text?path=${enc(path)}&limit=500000`);
    const ta = $("#txt-edit");
    if (!ta) return;
    ta.value = r.text;
    ta.placeholder = r.truncated ? `（文件 ${fmtSize(r.size)}，仅显示前 500KB）` : "";
  } catch (e) {
    const ta = $("#txt-edit");
    if (ta) ta.placeholder = "加载失败: " + e.message;
  }
}

function b64toBlob(b64, type) {
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return new Blob([arr], { type });
}

function fmtSize(n) {
  if (n >= 1 << 20) return (n / (1 << 20)).toFixed(1) + " MB";
  if (n >= 1 << 10) return (n / (1 << 10)).toFixed(0) + " KB";
  return n + " B";
}

/* ------------------------------------------------------------- build */

function renderBuild() {
  const body = $("#panel-body");
  const n = Object.keys(state.patches).length;
  body.innerHTML = `
    <div class="pv-title">构建改包</div>
    <div class="pv-meta">当前 ${n} 个替换条目。构建流程：重打包（原始字节级拷贝）→ v2 签名 → 校验。</div>
    <button class="btn primary" id="btn-build" style="width:100%" ${n ? "" : "disabled"}>开始构建</button>
    <div class="progress" id="prog-wrap" style="display:none">
      <div class="bar" id="prog-bar"></div><span class="pct" id="prog-pct">0%</span>
    </div>
    <div class="pv-meta" id="prog-step" style="margin-top:6px"></div>
    <div class="log" id="build-log" style="margin-top:10px"></div>
    <div id="build-result"></div>`;
  $("#btn-build").addEventListener("click", startBuild);
}

async function startBuild() {
  const btn = $("#btn-build");
  btn.disabled = true;
  $("#prog-wrap").style.display = "";
  $("#build-log").textContent = "";
  $("#build-result").innerHTML = "";
  try {
    const r = await api("/api/build", { method: "POST" });
    state.buildJob = r.job_id;
    pollBuild();
  } catch (e) {
    showBuildError(e.message);
    btn.disabled = false;
  }
}

async function pollBuild() {
  if (!state.buildJob) return;
  try {
    const j = await api(`/api/build/${state.buildJob}`);
    $("#prog-bar").style.width = (j.progress * 100).toFixed(1) + "%";
    $("#prog-pct").textContent = (j.progress * 100).toFixed(0) + "%";
    $("#prog-step").textContent = `${j.step}（${(j.progress * 100).toFixed(0)}%）`;
    const log = $("#build-log");
    if (log) log.textContent = j.log.join("\n");
    if (j.state === "done") {
      $("#prog-bar").style.width = "100%";
      $("#prog-pct").textContent = "100%";
      $("#build-result").innerHTML =
        `<div class="result">✅ 构建完成<br>输出：${j.result.output}<br>大小：${j.result.size_human}（${j.result.entries} 个替换）</div>`;
      $("#btn-build").disabled = false;
      state.buildJob = null;
    } else if (j.state === "error") {
      showBuildError(j.error || "构建失败");
      $("#btn-build").disabled = false;
      state.buildJob = null;
    } else {
      setTimeout(pollBuild, 700);
    }
  } catch (e) {
    showBuildError(e.message);
    $("#btn-build").disabled = false;
    state.buildJob = null;
  }
}

function showBuildError(msg) {
  const box = $("#build-result");
  if (box) box.innerHTML = `<div class="err">❌ ${msg}</div>`;
}

/* ------------------------------------------------------------- config */

function renderConfig() {
  const body = $("#panel-body");
  body.innerHTML = `
    <div class="pv-title">配置</div>
    <div class="cfg-row"><label>APK 文件路径</label>
      <input type="text" id="cfg-apk" value="${esc(state.cfgApk || "")}"></div>
    <div class="cfg-row"><label>输出目录</label>
      <input type="text" id="cfg-out" value="${esc(state.cfgOut || "")}"></div>
    <button class="btn primary" id="btn-save-cfg" style="width:100%">保存并重新扫描</button>
    <div class="pv-meta" style="margin-top:12px">
      提示：<br>
      1. 修改 2D 素材/音频/文本为纯本地行为，不触发服务器检测。<br>
      2. 构建会生成一个重新签名（v2）的 APK，卸载原版后安装即可。<br>
      3. 本工具不触碰 dex / lib / 资源表，只替换素材。</div>`;
  $("#btn-save-cfg").addEventListener("click", async () => {
    const cfg = {
      apk_path: $("#cfg-apk").value.trim(),
      output_dir: $("#cfg-out").value.trim(),
    };
    try {
      await api("/api/config", {
        method: "PUT", headers: { "content-type": "application/json" },
        body: JSON.stringify(cfg),
      });
      state.cfgApk = cfg.apk_path;
      state.cfgOut = cfg.output_dir;
      $("#apk-label").textContent = "📦 " + cfg.apk_path;
      $("#btn-scan").click();
      toast("配置已保存");
    } catch (e) { toast("保存失败: " + e.message, true); }
  });
}

function esc(s) {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/* ------------------------------------------------------------- packs */

async function exportPack() {
  try {
    const r = await api("/api/pack/export", { method: "POST" });
    toast(`已导出: ${r.file}`);
  } catch (e) { toast("导出失败: " + e.message, true); }
}

async function importPack(ev) {
  const f = ev.target.files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append("file", f);
  try {
    const r = await api("/api/pack/import", { method: "POST", body: fd });
    await refreshPatches();
    renderGrid();
    toast(`导入 ${r.imported} 个补丁`);
  } catch (e) { toast("导入失败: " + e.message, true); }
  ev.target.value = "";
}

/* ------------------------------------------------------------- toast */

function toast(msg, isErr) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.toggle("err", !!isErr);
  el.style.display = "block";
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.style.display = "none"; }, 4000);
}

async function boot() {
  const cfg = await api("/api/config");
  state.cfgApk = cfg.apk_path;
  state.cfgOut = cfg.output_dir;
  await init();
}
boot().catch((e) => {
  $("#tb-info").textContent = "⚠ 初始化失败: " + e.message;
});
