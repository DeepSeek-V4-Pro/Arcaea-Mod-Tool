"""进程级运行时状态:素材目录缓存、构建任务表。

统一挂在 FastAPI 的 app.state.amt 上,路由通过 deps.get_state 访问,
避免模块级全局变量散落各处。
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field

from core import builder, iosmode
from core.catalog import build_catalog
from core.patches import PatchStore
from core.zipio import read_central_directory

from . import config


@dataclass
class AppState:
    settings: dict
    patches: PatchStore
    catalog: dict | None = None                     # 素材目录缓存
    jobs: dict[str, builder.BuildJob] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    # ------------------------------------------------------------ catalog

    def scan(self, pkg_path: str, platform: str) -> dict:
        """(重新)构建素材目录并缓存。iOS 模式先探测 Payload 应用根。"""
        asset_root = "assets/"
        if platform == "ios":
            entries, _cd, _eocd = read_central_directory(pkg_path)
            root = iosmode.detect_app_root(entries)
            if root is None:
                from core.zipio import ZipError
                raise ZipError("不是有效的 IPA:未找到 Payload/<App>.app/")
            asset_root = root
        with self.lock:
            self.catalog = build_catalog(pkg_path, asset_root=asset_root)
            self.catalog["platform"] = platform
            self.catalog["asset_root"] = asset_root
            return self.catalog

    def clear_catalog(self) -> None:
        """平台切换 / 原包变更后废弃旧目录缓存。"""
        with self.lock:
            self.catalog = None

    def get_catalog(self, pkg_path: str, platform: str) -> dict:
        if self.catalog is None:
            return self.scan(pkg_path, platform)
        return self.catalog

    # -------------------------------------------------------------- build

    def start_build(self, pkg_path: str, platform: str) -> builder.BuildJob:
        """创建构建任务并立即在后台线程执行,返回任务对象供轮询。"""
        job = builder.BuildJob(uuid.uuid4().hex[:12])
        out_dir = self.settings.get("output_dir") or config.OUTPUT_DIR
        with self.lock:
            self.jobs[job.id] = job
        t = threading.Thread(
            target=builder.run_build,
            args=(job, pkg_path, out_dir, self.patches),
            kwargs={"platform": platform},
            daemon=True,
        )
        t.start()
        return job
