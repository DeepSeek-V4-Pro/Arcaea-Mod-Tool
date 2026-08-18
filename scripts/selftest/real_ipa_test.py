# -*- coding: utf-8 -*-
"""真实 940MB 暗改 IPA 全链路测试:外层 zip 解出 -> 扫描 -> 替换 -> 重打包。

运行: .venv\\Scripts\\python.exe scripts\\selftest\\real_ipa_test.py
产物: data/ipa_cache/*.ipa(缓存,供用户首次扫描即用)、data/output/*_mod.ipa
前置: 需通过环境变量指定真实包路径(脚本不内置机器路径):
  AMT_REAL_OUTER  暗改包外层 zip 的绝对路径
  AMT_REAL_HOME   官方素材文件绝对路径(如 APK 内 img/1080/home.png 的提取物)
"""
import os
import sys
import time
import zipfile

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

from core import builder, iosmode
from core.catalog import build_catalog
from core.patches import PatchStore
from core.zipio import read_central_directory

OUTER = os.environ.get("AMT_REAL_OUTER", "").strip()
OFFICIAL_HOME = os.environ.get("AMT_REAL_HOME", "").strip()
if not OUTER or not OFFICIAL_HOME:
    print("缺少环境变量,请先设置:")
    print("  set AMT_REAL_OUTER=外层 zip 绝对路径")
    print("  set AMT_REAL_HOME=官方素材文件绝对路径")
    sys.exit(2)

def fmt(n):
    return f"{n / (1 << 30):.2f} GB" if n >= 1 << 30 else f"{n / (1 << 20):.1f} MB"

t0 = time.time()
print("== 1. 外层 zip 解出内层 IPA(首次约 1GB,分块拷贝) ==")
ipa = iosmode.ensure_cached_ipa(OUTER)
print(f"  缓存 IPA: {ipa} ({fmt(os.path.getsize(ipa))})  用时 {time.time() - t0:.1f}s")

t0 = time.time()
print("== 2. 扫描目录(前缀剥离 + 分类) ==")
entries, _cd, _eocd = read_central_directory(ipa)
root = iosmode.detect_app_root(entries)
print(f"  应用根: {root}   条目总数: {len(entries)}")
cat = build_catalog(ipa, asset_root=root)
print(f"  图片素材: {cat['total']}   用时 {time.time() - t0:.1f}s")
print(f"  分类: {cat['sub_counts']}")
names = cat["char_names"]
if names:
    k = sorted(names)[0]
    print(f"  角色名示例: id={k} label={names[k]['label']}")

print("== 3. 替换(用官方 home.png 覆盖暗改 home.png) ==")
ps = PatchStore(os.path.join(BASE, "data", "selftest"))
with open(OFFICIAL_HOME, "rb") as f:
    patch_bytes = f.read()
target = root + "img/1080/home.png"
ps.put_bytes(target, patch_bytes, {"note": "selftest"})
print(f"  补丁: {target} ({fmt(len(patch_bytes))})")

print("== 4. iOS 构建(重打包 940MB) ==")
job = builder.BuildJob("real1")
outdir = os.path.join(BASE, "data", "output")
t0 = time.time()
builder.run_build(job, ipa, outdir, ps, platform="ios")
print(f"  状态: {job.state}  用时 {time.time() - t0:.1f}s")
if job.state != "done":
    print("  错误:", job.error)
    sys.exit(1)
out = job.result["output"]
print(f"  产物: {out} ({fmt(job.result['size'])})")

print("== 5. 产物校验 ==")
oentries, _cd2, _eocd2 = read_central_directory(out)
onames = {e.name for e in oentries}
ok1 = any(n.startswith(root + "_CodeSignature") for n in onames) is False
with zipfile.ZipFile(out) as z:
    data = z.read(target)
    ok2 = data == patch_bytes
    ok3 = z.read(root + "img/bg_light.jpg") == zipfile.ZipFile(ipa).read(root + "img/bg_light.jpg")
    n_app = sum(1 for n in onames if n.startswith(root))
print(f"  旧签名移除: {ok1}   替换生效: {ok2}   未替换条目保留: {ok3}")
print(f"  应用内条目: {n_app}")
assert ok1 and ok2 and ok3, "校验失败"
print("\n全部通过 ✓")
