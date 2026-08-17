"""Arcaea Mod Tool — FastAPI 应用入口。

API 一览:
  GET  /                         webui
  GET  /api/config               settings (apk path, output dir)
  PUT  /api/config               update settings
  POST /api/scan                 (re)build asset catalog
  GET  /api/catalog              cached catalog
  GET  /api/asset/raw?path=      original bytes (Range supported)
  GET  /api/asset/thumb?path=    image thumbnail (cached)
  GET  /api/asset/text?path=     text preview
  GET  /api/patches              patch list
  PUT  /api/patch                upload replacement (+image settings)
  POST /api/patch/text           save text patch
  DELETE /api/patch?path=        remove patch
  GET  /api/patch/bytes?path=    replacement bytes (preview)
  POST /api/patch/process        image processing preview (base64 in/out)
  POST /api/build                start build job
  GET  /api/build/{id}           job snapshot
  POST /api/pack/export          export mod pack zip
  POST /api/pack/import          import mod pack zip

启动方式:  python -m app   (端口可用环境变量 AMT_PORT 覆盖,默认 8000)
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from core.patches import PatchStore

from . import config
from .routes import assets, build, config as config_route, packs, patches
from .state import AppState


def create_app() -> FastAPI:
    config.ensure_dirs()
    app = FastAPI(title="Arcaea Mod Tool")
    app.state.amt = AppState(
        settings=config.load_settings(),
        patches=PatchStore(config.PATCH_DIR),
    )

    app.include_router(config_route.router)
    app.include_router(assets.router)
    app.include_router(patches.router)
    app.include_router(build.router)
    app.include_router(packs.router)

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(os.path.join(config.WEBUI_DIR, "index.html"))

    app.mount("/static", StaticFiles(directory=config.WEBUI_DIR), name="static")
    return app


app = create_app()


def main() -> None:
    import uvicorn

    port = int(os.environ.get("AMT_PORT", "8000"))
    print(f"Arcaea Mod Tool → http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
