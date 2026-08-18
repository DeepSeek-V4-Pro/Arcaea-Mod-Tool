"""Build pipeline: apply patches -> rebuild package -> sign/verify.

Android: rebuild APK -> APK v2 sign -> verify.
iOS(实验): rebuild IPA -> 结构校验(不签名,签名交给 Sideloadly/爱思助手)。

Runs in a background thread; progress is polled via a job object.
"""

from __future__ import annotations

import os
import threading
import time

from . import iosmode, signing
from .patches import PatchStore
from .zipio import build_apk, read_central_directory

SIGNATURE_DROPS = {
    "META-INF/MANIFEST.MF", "META-INF/CERT.SF", "META-INF/CERT.RSA",
    "META-INF/CERT.DSA", "META-INF/CERT.EC",
}


class BuildJob:
    def __init__(self, job_id: str):
        self.id = job_id
        self.state = "pending"      # pending | running | done | error
        self.step = ""
        self.progress = 0.0         # 0..1
        self.log: list[str] = []
        self.error = ""
        self.result = None
        self._lock = threading.Lock()
        self._started = time.time()

    def update(self, state=None, step=None, progress=None, log=None):
        with self._lock:
            if state:
                self.state = state
            if step:
                self.step = step
            if progress is not None:
                self.progress = progress
            if log:
                self.log.append(log)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "id": self.id, "state": self.state, "step": self.step,
                "progress": self.progress, "log": list(self.log),
                "error": self.error, "result": self.result,
                "elapsed": round(time.time() - self._started, 1),
            }


def run_build(job: BuildJob, apk_path: str, output_dir: str, patches: PatchStore,
              keydir: str | None = None, platform: str = "android") -> None:
    if platform == "ios":
        _run_build_ios(job, apk_path, output_dir, patches)
    else:
        _run_build_android(job, apk_path, output_dir, patches, keydir)


def _collect_replacements(job: BuildJob, patches: PatchStore) -> dict[str, bytes]:
    """收集启用状态的补丁内容;为空则抛错。"""
    items = [it for it in patches.list() if it.get("enabled", True)]
    replace = {}
    for it in items:
        data = patches.get_bytes(it["path"])
        if data is None:
            continue
        replace[it["path"]] = data
    if not replace:
        raise RuntimeError("没有已启用(勾选)的替换内容")
    job.update(log=f"共 {len(replace)} 个替换条目")
    return replace


def _run_build_android(job: BuildJob, apk_path: str, output_dir: str,
                       patches: PatchStore, keydir: str | None) -> None:
    try:
        job.update(state="running", log="开始构建…")

        replace = _collect_replacements(job, patches)

        out_unsigned = os.path.join(output_dir, "mod_unsigned.apk")
        os.makedirs(output_dir, exist_ok=True)

        # 1. rebuild (fast raw-copy)
        def on_progress(done, total, name):
            job.update(progress=0.05 + 0.45 * done / total,
                       step=f"重打包 {done}/{total}: {name}")

        job.update(step="重打包…", log="重打包（原始字节级拷贝，未改动条目不重新压缩）")
        build_apk(apk_path, out_unsigned, replace=replace,
                  drop=SIGNATURE_DROPS, on_progress=on_progress)
        job.update(progress=0.5, log="重打包完成")

        # 2. sign
        base = os.path.splitext(os.path.basename(apk_path))[0]
        out_signed = os.path.join(output_dir, f"{base}_mod.apk")

        def on_sign(done, total, name):
            job.update(progress=0.5 + 0.35 * done / total, step=f"签名: {name}")

        job.update(step="签名…", log="APK v2 签名（AOSP apksig 算法，纯 Python）")
        signing.sign_apk(out_unsigned, keydir=keydir, out_path=out_signed,
                         on_progress=on_sign)
        job.update(progress=0.85, log="签名完成")

        # 3. verify
        job.update(step="校验…", log="校验签名与内容摘要")
        vr = signing.verify_apk(out_signed)
        if not vr["ok"]:
            raise RuntimeError("签名自校验失败: " + str(vr.get("checks", [])))
        sp = signing.structural_parse(out_signed)
        if not sp.get("ok"):
            raise RuntimeError("签名结构解析失败: " + str(sp.get("error")))
        job.update(progress=0.95, log="校验通过")

        # 4. cleanup
        if os.path.exists(out_unsigned):
            os.remove(out_unsigned)
        size = os.path.getsize(out_signed)
        job.update(state="done", progress=1.0, log="构建完成")
        job.result = {
            "output": out_signed,
            "size": size,
            "size_human": f"{size / (1 << 30):.2f} GB",
            "entries": len(replace),
            "platform": "android",
            "unsigned": False,
        }
    except Exception as ex:
        job.error = str(ex)
        job.update(state="error", log=f"错误: {ex}")


def _run_build_ios(job: BuildJob, ipa_path: str, output_dir: str,
                   patches: PatchStore) -> None:
    """iOS 实验模式:重打包 -> 结构校验。不做签名(产物未签名,由用户自行
    用 Sideloadly / 爱思助手等 Apple 签名链签名安装)。"""
    try:
        job.update(state="running", log="开始构建（iOS 实验模式）…")

        replace = _collect_replacements(job, patches)

        entries, _cd, _eocd = read_central_directory(ipa_path)
        app_root = iosmode.detect_app_root(entries)
        if not app_root:
            raise RuntimeError("不是有效的 IPA:未找到 Payload/<App>.app/ 目录")
        job.update(log=f"应用根目录: {app_root}")

        # 旧代码签名清单(越狱 dump 残留)已与修改后的内容不匹配,
        # 直接移除——签名工具(如 Sideloadly)安装时会重新生成。
        drop_prefixes = [app_root + "_CodeSignature/"]
        job.update(log="将移除旧代码签名 _CodeSignature/（重签时由签名工具重新生成）")

        out_unsigned = os.path.join(output_dir, "mod_unsigned.ipa")
        os.makedirs(output_dir, exist_ok=True)

        # 1. rebuild (fast raw-copy)
        def on_progress(done, total, name):
            job.update(progress=0.05 + 0.75 * done / total,
                       step=f"重打包 {done}/{total}: {name}")

        job.update(step="重打包…", log="重打包（原始字节级拷贝，未改动条目不重新压缩）")
        build_apk(ipa_path, out_unsigned, replace=replace,
                  drop_prefixes=drop_prefixes, on_progress=on_progress)
        job.update(progress=0.8, log="重打包完成")

        # 2. verify (zip 结构 + 每个替换条目存在且大小一致;不涉及签名)
        job.update(step="校验…", log="校验产物结构（iOS 不签名,签名由用户自行完成）")
        out_entries, _cd2, _eocd2 = read_central_directory(out_unsigned)
        by_name = {e.name: e for e in out_entries}
        for path, data in replace.items():
            e = by_name.get(path)
            if e is None:
                raise RuntimeError(f"校验失败:替换条目缺失 {path}")
            if e.usize != len(data):
                raise RuntimeError(
                    f"校验失败:大小不符 {path}（{e.usize} != {len(data)}）")
        if not any(e.name.startswith(app_root) for e in out_entries):
            raise RuntimeError("校验失败:产物中未找到应用目录")
        job.update(progress=0.95, log="校验通过")

        # 3. finalize
        base = os.path.splitext(os.path.basename(ipa_path))[0]
        out_signed = os.path.join(output_dir, f"{base}_mod.ipa")
        if os.path.exists(out_unsigned):
            if os.path.exists(out_signed):
                os.remove(out_signed)
            os.replace(out_unsigned, out_signed)
        size = os.path.getsize(out_signed)
        job.update(state="done", progress=1.0,
                   log="构建完成（未签名,请用 Sideloadly/爱思助手签名后安装）")
        job.result = {
            "output": out_signed,
            "size": size,
            "size_human": f"{size / (1 << 30):.2f} GB",
            "entries": len(replace),
            "platform": "ios",
            "unsigned": True,
        }
    except Exception as ex:
        job.error = str(ex)
        job.update(state="error", log=f"错误: {ex}")
