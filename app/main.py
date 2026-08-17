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
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from core.patches import PatchStore

from . import config
from .routes import assets, build, config as config_route, packs, patches
from .state import AppState


def _web_root() -> str:
    """返回前端静态目录:优先 Vite 构建产物 dist/,未构建时返回空串。"""
    dist = os.path.join(config.WEBUI_DIR, "dist")
    if os.path.exists(os.path.join(dist, "index.html")):
        return dist
    return ""


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

    web_root = _web_root()
    if web_root:
        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(os.path.join(web_root, "index.html"))

        app.mount("/static", StaticFiles(directory=web_root), name="static")
    else:
        @app.get("/", include_in_schema=False)
        def index():
            hint = (
                "<h3>Arcaea Mod Tool</h3>"
                "<p>前端尚未构建。请先执行:</p>"
                "<pre>cd webui &amp;&amp; npm install &amp;&amp; npm run build</pre>"
                "<p>或直接运行 start.bat(检测到 Node 时会自动构建)。</p>"
            )
            return HTMLResponse(hint)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    port = int(os.environ.get("AMT_PORT", "8000"))
    print(f"Arcaea Mod Tool → http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
