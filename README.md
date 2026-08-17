# Arcaea Mod Tool

本地改包工具:直接从 APK 中浏览、替换 **Arcaea** 的 2D 素材(立绘、曲绘、界面、背景、音符皮肤、音频、文本),并重新打包、签名生成可安装的 mod APK。

- **不触碰** dex / lib / 资源表,只替换素材文件,风险低
- **快**:重打包采用原始字节级拷贝(解析 zip 中央目录,只重压缩被替换的条目),1.8 GB 的 APK 无需全量解压
- **纯本地**:所有数据保存在 `data/` 目录,不联网、不上传
- **自签名**:内置纯 Python 的 APK v2 签名实现,自动生成/复用本地密钥

## 快速开始

```bat
:: 一键安装(创建 .venv 并安装依赖,然后自动启动)
scripts\install.bat

:: 或手动
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
start.bat
```

启动后浏览器访问 <http://127.0.0.1:8000>(端口可用环境变量 `AMT_PORT` 覆盖)。

> 首次使用请在「配置」页填写 APK 文件路径,然后点「扫描」建立素材目录。

## 使用流程

1. **扫描**:读取 APK 中央目录,建立素材索引(仅 2D 图片 + 可读文本/音频,数秒完成)
2. **替换**:在素材网格中点选条目,拖入新文件即可;图片支持缩放 / 拉伸保持原尺寸 / 转 JPG 等处理预览;文本类文件可在线编辑
3. **构建**:自动执行「重打包 → v2 签名 → 自校验」,输出到 `data/output/`
4. **补丁包**:可导出 / 导入 mod pack zip,便于分享与备份

## 目录结构

```
arcaea-mod-tool/
├── app/                  # FastAPI 应用层
│   ├── main.py           # 应用工厂 + 入口(python -m app)
│   ├── config.py         # 路径布局 + settings.json 读写
│   ├── state.py          # 进程内状态(目录缓存、构建任务表)
│   ├── deps.py           # 路由共享依赖
│   ├── mime.py           # Content-Type 猜测
│   └── routes/           # 按业务域拆分的路由
│       ├── assets.py     # 扫描 / 目录 / 资源读取
│       ├── patches.py    # 补丁 CRUD / 图片处理 / 文本编辑
│       ├── build.py      # 构建任务
│       ├── packs.py      # 补丁包导入导出
│       └── config.py     # 配置读写
├── core/                 # 引擎层(与 Web 无关,可独立测试)
│   ├── zipio.py          # zip 解析 / 原始字节级重打包
│   ├── catalog.py        # 素材目录与分类规则
│   ├── patches.py        # 补丁存储(sha1 命名 blob + 元数据)
│   ├── builder.py        # 构建流水线(后台线程 + 进度)
│   └── signing.py        # APK v2 签名 / 校验(纯 Python)
├── webui/                # 前端(无构建步骤:HTML/CSS/JS)
├── scripts/install.bat   # 一键安装(venv + 依赖 + 启动)
├── start.bat             # 启动脚本
├── data/                 # 运行时数据(不入库,见 .gitignore)
│   ├── settings.json     # 用户配置(APK 路径、输出目录)
│   ├── patches/          # 补丁内容与元数据
│   ├── thumbs/           # 缩略图缓存
│   ├── keystore/         # 签名密钥(自动生成)
│   ├── output/           # 构建产物
│   └── packs/            # 补丁包
└── requirements.txt
```

## 开发

```bat
.venv\Scripts\python -m app          :: 启动服务(等价于 start.bat)
.venv\Scripts\python -m py_compile app core -q   :: 语法检查
```

约定:

- 应用层(`app/`)负责 HTTP 与进程状态,引擎层(`core/`)负责纯逻辑,`core/` 不依赖 FastAPI
- 所有路径基于项目根目录推导,不依赖当前工作目录
- API 变更请同步更新 `app/main.py` 顶部注释与 README

## 说明

- 生成的 mod APK 使用本地自签名证书,与官方包签名不同;安装前需卸载原版
- 修改素材为纯本地行为;修改 songlist / characters.json 等数据类文件请自行承担风险
