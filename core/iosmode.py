"""iOS 实验模式:IPA 识别、Payload 应用根目录探测、外层 zip 内 IPA 解出。

IPA 本质就是 zip:素材树位于 Payload/<App>.app/ 下,与 Android 的 assets/
同构(实测 4417 个共有路径与官方 APK 逐字节一致)。本模块只负责"定位
与取用原包",不改包逻辑;真正的扫描/替换/重打包全部复用现有引擎。

⚠️ 官方 App Store 分发的 IPA 主程序带 FairPlay DRM(加密),无法直接修改;
实验模式要求用户自备「已解密」的 IPA(越狱设备 AppsDump 类工具的产物)。
"""

from __future__ import annotations

import hashlib
import os
import re
import zipfile

IPA_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "ipa_cache",
)

# Payload/<App>.app/ 前缀:命中即认为该条目属于应用素材树
_APP_RE = re.compile(r"^Payload/[^/]+\.app/")


def detect_app_root(entries) -> str | None:
    """从中央目录条目中探测 Payload/<App>.app/ 前缀(取第一个命中)。"""
    for e in entries:
        m = _APP_RE.match(e.name)
        if m:
            return m.group(0)
    return None


def find_inner_ipa(zip_path: str) -> zipfile.ZipInfo | None:
    """外层 zip 里最大的 *.ipa 成员(暗改包分发 zip 即此形态)。"""
    with zipfile.ZipFile(zip_path) as z:
        best = None
        for e in z.infolist():
            if e.filename.lower().endswith(".ipa") and not e.is_dir():
                if best is None or e.file_size > best.file_size:
                    best = e
        return best


def ensure_cached_ipa(zip_path: str) -> str:
    """把外层 zip 内的 IPA 解出到 data/ipa_cache/(按 路径+mtime+大小 缓存)。

    暗改包分发格式是「外层 zip 包着 940MB 的 IPA」;这里做一次性解出并缓存,
    之后扫描/构建都直接读缓存文件。分块拷贝,不整包载入内存。
    """
    os.makedirs(IPA_CACHE_DIR, exist_ok=True)
    st = os.stat(zip_path)
    key = hashlib.sha1(
        f"{os.path.abspath(zip_path)}|{st.st_mtime_ns}|{st.st_size}".encode("utf-8")
    ).hexdigest()[:16]
    out = os.path.join(IPA_CACHE_DIR, key + ".ipa")
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return out
    info = find_inner_ipa(zip_path)
    if info is None:
        raise ValueError("压缩包内未找到 .ipa 文件")
    tmp = out + ".tmp"
    with zipfile.ZipFile(zip_path) as z, open(tmp, "wb") as f:
        with z.open(info) as src:
            while True:
                chunk = src.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
    os.replace(tmp, out)
    return out


def resolve_ipa(configured: str) -> str:
    """iOS 生效原包路径:.ipa 直接用;外层 .zip 则解出缓存的内部 IPA。"""
    low = configured.lower()
    if low.endswith(".ipa"):
        return configured
    if low.endswith(".zip"):
        return ensure_cached_ipa(configured)
    return configured
