"""Arcaea Mod Tool — FastAPI 应用层。

分层约定:
  app/       Web 应用层(路由、配置、进程内状态)
  core/      引擎层(zip 解析、素材目录、补丁存储、构建、签名)
  webui/     前端(无构建步骤的静态页面)
  data/      运行时数据(APK 路径设置、补丁、缩略图、签名密钥等,不入库)
"""
