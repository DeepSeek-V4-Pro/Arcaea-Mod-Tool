"""Build pipeline: apply patches -> rebuild APK -> sign -> verify.

Runs in a background thread; progress is polled via a job object.
"""

from __future__ import annotations

import os
import threading
import time

from . import signing
from .patches import PatchStore
from .zipio import build_apk

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
              keydir: str | None = None) -> None:
    try:
        job.update(state="running", log="开始构建…")

        # collect replacements
        items = patches.list()
        replace = {}
        for it in items:
            data = patches.get_bytes(it["path"])
            if data is None:
                continue
            replace[it["path"]] = data
        if not replace:
            raise RuntimeError("没有已保存的替换内容（补丁列表为空）")

        job.update(log=f"共 {len(replace)} 个替换条目")

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
        }
    except Exception as ex:
        job.error = str(ex)
        job.update(state="error", log=f"错误: {ex}")
