"""构建路由:启动构建任务与轮询任务状态。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

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
