"""进程级运行时状态:素材目录缓存、构建任务表。

统一挂在 FastAPI 的 app.state.amt 上,路由通过 deps.get_state 访问,
避免模块级全局变量散落各处。
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field

from core import builder
from core.catalog import build_catalog
from core.patches import PatchStore

from . import config


@dataclass
class AppState:
    settings: dict
    patches: PatchStore
    catalog: dict | None = None                     # 素材目录缓存
    jobs: dict[str, builder.BuildJob] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    # ------------------------------------------------------------ catalog

    def scan(self, apk_path: str) -> dict:
        """(重新)构建素材目录并缓存。"""
        with self.lock:
            self.catalog = build_catalog(apk_path)
            return self.catalog

    def get_catalog(self, apk_path: str) -> dict:
        if self.catalog is None:
            return self.scan(apk_path)
        return self.catalog

    # -------------------------------------------------------------- build

    def start_build(self, apk_path: str) -> builder.BuildJob:
        """创建构建任务并立即在后台线程执行,返回任务对象供轮询。"""
        job = builder.BuildJob(uuid.uuid4().hex[:12])
        out_dir = self.settings.get("output_dir") or config.OUTPUT_DIR
        with self.lock:
            self.jobs[job.id] = job
        t = threading.Thread(
            target=builder.run_build,
            args=(job, apk_path, out_dir, self.patches),
            daemon=True,
        )
        t.start()
        return job
