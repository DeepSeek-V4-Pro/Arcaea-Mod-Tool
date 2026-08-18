# -*- coding: utf-8 -*-
"""input/ 自动识别(pick_pkg)组合用例自测。

运行: .venv\\Scripts\\python.exe scripts\\selftest\\pick_test.py
"""
import io
import os
import shutil
import sys
import zipfile

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

from app import config as app_config

TMP = os.path.join(BASE, "data", "selftest_pick")      # 充当 input/ 的测试目录
CFG = os.path.join(BASE, "data", "selftest_pick_cfg")  # 配置文件目录(与 input/ 隔离)
os.makedirs(TMP, exist_ok=True)
os.makedirs(CFG, exist_ok=True)
app_config.INPUT_DIR = TMP  # 重定向到测试目录

PASS = 0
FAIL = 0

def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok {name}")
    else:
        FAIL += 1
        print(f"  XX {name}  {detail}")

def make_zip(path, with_ipa=True):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        if with_ipa:
            z.writestr("inner/syn.ipa", b"fake-ipa-content")
        z.writestr("readme.txt", "docs")

def reset(*names):
    for n in os.listdir(TMP):
        os.remove(os.path.join(TMP, n))
    for n in names:
        with open(os.path.join(TMP, n), "wb") as f:
            f.write(os.urandom(32))

print("== 配置路径优先 ==")
for n in os.listdir(CFG):
    os.remove(os.path.join(CFG, n))
cfg_apk = os.path.join(CFG, "game.apk")
cfg_ipa = os.path.join(CFG, "game.ipa")
cfg_zip = os.path.join(CFG, "outer.zip")
with open(cfg_apk, "wb") as f: f.write(b"a" * 100)
with open(cfg_ipa, "wb") as f: f.write(b"b" * 100)
make_zip(cfg_zip)
weird = os.path.join(CFG, "weird.bin")
with open(weird, "wb") as f: f.write(b"w" * 50)
reset()  # input/ 保持干净,冲突用例才能验证「回退为空」

p = app_config.pick_pkg(cfg_apk, "ios")   # 配置 APK 但设置 ios -> 模式冲突,忽略配置
check("配置 .apk + ios模式 -> 忽略回退", p["platform"] == "ios" and p["source"] == "" and "不符" in p["note"], str(p))
p = app_config.pick_pkg(cfg_ipa, "android")  # 配置 IPA 但设置 android -> 模式冲突,忽略
check("配置 .ipa + android模式 -> 忽略回退", p["platform"] == "android" and p["source"] == "" and "不符" in p["note"], str(p))
p = app_config.pick_pkg(cfg_ipa, "ios")
check("配置 .ipa + ios模式 -> 使用", p["platform"] == "ios" and p["source"] == "configured", str(p))
p = app_config.pick_pkg(cfg_zip, "ios")  # zip 总是 ios
check("配置 .zip + ios -> 内层", p["platform"] == "ios" and p["inner_ipa"] == "inner/syn.ipa" and p["path"].endswith(".ipa"), str(p))
p = app_config.pick_pkg(cfg_zip, "android")  # zip + android -> 冲突,忽略回退
check("配置 .zip + android -> 忽略回退", p["platform"] == "android" and p["source"] == "", str(p))
p = app_config.pick_pkg(cfg_zip, "ios")
check("配置 .zip 缓存复用", p["path"] == app_config.iosmode.ensure_cached_ipa(cfg_zip), str(p))
p = app_config.pick_pkg(weird, "android")
check("其他扩展名按设置平台", p["platform"] == "android" and p["path"].endswith("weird.bin"), str(p))

print("== 模式冲突时 input/ 有对应包:回退识别 ==")
reset("only.apk")
p = app_config.pick_pkg(cfg_zip, "android")   # zip 配置冲突,但 input/ 有 apk -> 自动识别 android
check("zip冲突+input有apk -> android", p["platform"] == "android" and p["source"] == "input" and p["display"] == "only.apk", str(p))
reset("only.ipa")
p = app_config.pick_pkg(cfg_apk, "ios")       # apk 配置冲突,但 input/ 有 ipa -> 自动识别 ios
check("apk冲突+input有ipa -> ios", p["platform"] == "ios" and p["source"] == "input" and p["display"] == "only.ipa", str(p))

print("== input/ 自动识别 ==")
# 只有 APK
reset("only.apk")
p = app_config.pick_pkg("", "android")
check("android+只有apk", p["platform"] == "android" and p["source"] == "input" and p["display"] == "only.apk", str(p))
p = app_config.pick_pkg("", "ios")
check("ios+只有apk -> 自动android", p["platform"] == "android" and "自动" in p["note"], str(p))
# 只有 IPA
reset("only.ipa")
p = app_config.pick_pkg("", "ios")
check("ios+只有ipa", p["platform"] == "ios" and p["display"] == "only.ipa", str(p))
p = app_config.pick_pkg("", "android")
check("android+只有ipa -> 自动ios", p["platform"] == "ios" and "自动" in p["note"], str(p))
# 只有外层 zip
reset("outer.zip")
make_zip(os.path.join(TMP, "outer.zip"))
p = app_config.pick_pkg("", "ios")
check("ios+只有zip -> 解出", p["platform"] == "ios" and p["inner_ipa"] == "inner/syn.ipa" and p["source"] == "input", str(p))
p = app_config.pick_pkg("", "android")
check("android+只有zip -> 自动ios", p["platform"] == "ios", str(p))
# APK + IPA 同时存在:按当前平台
reset("big.apk", "big.ipa")
with open(os.path.join(TMP, "big.apk"), "wb") as f: f.write(b"a" * 200)
p = app_config.pick_pkg("", "android")
check("apk+ipa -> android 取apk", p["platform"] == "android" and p["display"] == "big.apk", str(p))
p = app_config.pick_pkg("", "ios")
check("apk+ipa -> ios 取ipa", p["platform"] == "ios" and p["display"] == "big.ipa", str(p))
# 空目录
reset()
p = app_config.pick_pkg("", "android")
check("空目录 -> 未找到", p["path"] == "" and p["source"] == "", str(p))

print("== 候选展示 ==")
reset("a.apk", "b.ipa", "c.zip")
c = app_config.input_candidates()
check("candidates 三类齐全", len(c["apk"]) == 1 and len(c["ipa"]) == 1 and len(c["zip"]) == 1, str(c))

print(f"\n结果: PASS={PASS} FAIL={FAIL}")
shutil.rmtree(TMP, ignore_errors=True)
shutil.rmtree(CFG, ignore_errors=True)
sys.exit(1 if FAIL else 0)
