"""构建路由:启动构建任务、轮询任务状态、下载构建产物。"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from .. import config as app_config
from ..deps import get_state, need_apk
from ..state import AppState

router = APIRouter(tags=["build"])


@router.post("/api/build")
def start_build(state: AppState = Depends(get_state)):
    apk = need_apk(state)
    job = state.start_build(apk)
    return {"job_id": job.id}


@router.get("/api/build/{job_id}")
def build_status(job_id: str, state: AppState = Depends(get_state)):
    job = state.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    return job.snapshot()


@router.get("/api/output/download")
def output_download(path: str, state: AppState = Depends(get_state)):
    """下载构建产物(限定在输出目录内,防止任意文件读取)。"""
    out_dir = os.path.abspath(state.settings.get("output_dir") or app_config.OUTPUT_DIR)
    p = os.path.abspath(path)
    try:
        inside = os.path.commonpath([p, out_dir]) == out_dir
    except ValueError:  # 不同盘符
        inside = False
    if not inside or not os.path.isfile(p):
        raise HTTPException(400, "路径不在输出目录内")
    return FileResponse(p, media_type="application/vnd.android.package-archive",
                        headers={"Content-Disposition":
                                 f'attachment; filename="{os.path.basename(p)}"'})
