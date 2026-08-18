# -*- coding: utf-8 -*-
"""iOS 实验模式自测:合成 IPA 全链路(纯本地,秒级,无需真实 IPA)。

运行: .venv\\Scripts\\python.exe scripts\\selftest\\ios_selftest.py
"""
import io
import os
import sys
import zipfile

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

from PIL import Image

from core import builder, iosmode
from core.catalog import build_catalog
from core.patches import PatchStore
from core.zipio import read_central_directory

TMP = os.path.join(BASE, "data", "_selftest")
os.makedirs(TMP, exist_ok=True)

PASS = 0
FAIL = 0

def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name}  {detail}")

def png_bytes(color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGBA", (4, 4), color).save(buf, "PNG")
    return buf.getvalue()

def make_synthetic_ipa(path):
    root = "Payload/Arc-mobile.app/"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(root + "img/1080/bg_select_light.jpg", b"fakejpeg1")
        z.writestr(root + "char/0_icon.png", png_bytes((200, 30, 30)))
        z.writestr(root + "char/12_mp.png", png_bytes((30, 200, 30)))
        z.writestr(root + "char/characters.json",
                   '[{"character_id":0,"name":"Hikari","search_strings":["光","光"]}]')
        z.writestr(root + "startup/1080/title.png", png_bytes((30, 30, 200)))
        z.writestr(root + "_CodeSignature/CodeResources", b"old-signature")
        z.writestr(root + "Arc-mobile", b"MACHOFAKE")

print("== 1. 合成 IPA 基础 ==")
ipa = os.path.join(TMP, "syn.ipa")
make_synthetic_ipa(ipa)
entries, _cd, _eocd = read_central_directory(ipa)
root = iosmode.detect_app_root(entries)
check("detect_app_root", root == "Payload/Arc-mobile.app/", repr(root))

outer = os.path.join(TMP, "outer.zip")
with zipfile.ZipFile(outer, "w", zipfile.ZIP_STORED) as z:
    z.write(ipa, "inner/syn.ipa")
    z.writestr("说明.txt", "docs")
inner = iosmode.find_inner_ipa(outer)
check("find_inner_ipa", inner is not None and inner.filename.endswith(".ipa"))
c1 = iosmode.ensure_cached_ipa(outer)
check("ensure_cached_ipa", os.path.exists(c1) and os.path.getsize(c1) == os.path.getsize(ipa))
c2 = iosmode.ensure_cached_ipa(outer)
check("cache 复用", c1 == c2)

print("== 2. 目录构建(前缀剥离/分类/角色名) ==")
cat = build_catalog(ipa, asset_root=root)
check("total==4", cat["total"] == 4, str(cat["total"]))
subs = cat["sub_counts"]
check("char 分类", subs.get("char") == 2, str(subs))
check("startup 分类", subs.get("startup") == 1, str(subs))
check("ui_other 分类", subs.get("ui_other") == 1, str(subs))
a0 = next(a for a in cat["assets"] if a["path"].endswith("0_icon.png"))
check("icon 识别", a0["form"] == "icon" and a0["char_id"] == "0", str(a0))
check("rel 字段", a0["rel"] == "char/0_icon.png", a0["rel"])
check("char_names 解析", cat["char_names"].get("0", {}).get("label") == "光", str(cat["char_names"]))
# Android 根路径行为不变:根外条目按原名归类(与旧版一致,全部落入 misc)
cat_android = build_catalog(ipa, asset_root="assets/")
check("android 根全为 misc", cat_android["total"] == 4 and all(a["sub"] == "misc" for a in cat_android["assets"]),
      str(cat_android["sub_counts"]))

print("== 3. iOS 构建(重打包/去旧签名/校验) ==")
ps = PatchStore(os.path.join(TMP, "patches"))
new_img = png_bytes((9, 9, 9))
ps.put_bytes(root + "img/1080/bg_select_light.jpg", b"REPLACED-JPEG", {"note": "t"})
job = builder.BuildJob("t1")
outdir = os.path.join(TMP, "out")
builder.run_build(job, ipa, outdir, ps, platform="ios")
check("构建 done", job.state == "done", job.error)
out_ipa = job.result["output"] if job.result else None
check("产物路径", out_ipa and os.path.exists(out_ipa))
oentries, _cd2, _eocd2 = read_central_directory(out_ipa)
onames = {e.name for e in oentries}
check("旧签名已移除", not any(n.startswith(root + "_CodeSignature") for n in onames))
check("替换内容写入", os.path.exists(out_ipa))
with zipfile.ZipFile(out_ipa) as z:
    data = z.read(root + "img/1080/bg_select_light.jpg")
check("替换内容一致", data == b"REPLACED-JPEG", repr(data))
check("未替换条目保留", zipfile.ZipFile(out_ipa).read(root + "char/0_icon.png") == png_bytes((200, 30, 30)))
check("unsigned 标记", job.result and job.result["unsigned"] is True and job.result["platform"] == "ios")

print("== 4. 配置解析(外层 zip -> 缓存 ipa) ==")
from app import config as app_config
res = app_config.pick_pkg(outer, "ios")
check("pick zip->ipa", res["path"] == c1 and res["platform"] == "ios" and res["inner_ipa"] == "inner/syn.ipa", str(res))
res2 = app_config.pick_pkg(ipa, "ios")
check("pick ipa 直用", res2["platform"] == "ios" and res2["path"] == ipa, str(res2))
res3 = app_config.pick_pkg(ipa, "android")   # 配置 ipa + android 模式 -> 模式冲突,回退 input/ 识别
check("pick ipa+android -> 冲突回退", res3["platform"] == "android" and "不符" in res3["note"], str(res3))

print(f"\n结果: PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
