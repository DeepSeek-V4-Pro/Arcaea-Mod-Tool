"""Patch store: replacements for APK entries, image processing options.

A patch = original asset path -> replacement file + metadata.
Replacement bytes live in data/patches/<sha1-of-path>.bin, metadata in
patches.json. Text patches store the full new content as the replacement.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import time
import zipfile

from PIL import Image

PATCHES_JSON = "patches.json"


def _key(path: str) -> str:
    return hashlib.sha1(path.encode("utf-8")).hexdigest()[:20]


class PatchStore:
    def __init__(self, root: str):
        self.root = root
        os.makedirs(root, exist_ok=True)
        self.json_path = os.path.join(root, PATCHES_JSON)
        self._meta: dict = {}
        if os.path.exists(self.json_path):
            try:
                self._meta = json.load(open(self.json_path, "r", encoding="utf-8"))
            except Exception:
                self._meta = {}

    def _save(self):
        tmp = self.json_path + ".tmp"
        json.dump(self._meta, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        os.replace(tmp, self.json_path)

    def _blob(self, path: str) -> str:
        return os.path.join(self.root, _key(path) + ".bin")

    # ------------------------------------------------------------- queries

    def list(self) -> list[dict]:
        out = []
        for path, meta in self._meta.items():
            blob = self._blob(path)
            item = dict(meta)
            item["path"] = path
            item["exists"] = os.path.exists(blob)
            item["size"] = os.path.getsize(blob) if os.path.exists(blob) else 0
            out.append(item)
        return sorted(out, key=lambda x: x["path"])

    def get(self, path: str) -> dict | None:
        if path not in self._meta:
            return None
        return {**self._meta[path], "path": path}

    def get_bytes(self, path: str) -> bytes | None:
        blob = self._blob(path)
        if not os.path.exists(blob):
            return None
        with open(blob, "rb") as f:
            return f.read()

    # -------------------------------------------------------------- writes

    def put_bytes(self, path: str, data: bytes, meta: dict | None = None) -> dict:
        with open(self._blob(path), "wb") as f:
            f.write(data)
        entry = {
            "source": meta.get("source", "upload") if meta else "upload",
            "orig_name": meta.get("orig_name", os.path.basename(path)) if meta else os.path.basename(path),
            "orig_ext": meta.get("orig_ext", os.path.splitext(path)[1].lower()) if meta else os.path.splitext(path)[1].lower(),
            "note": (meta or {}).get("note", ""),
            "ts": time.time(),
            "settings": (meta or {}).get("settings", {}),
            "enabled": True,
        }
        self._meta[path] = entry
        self._save()
        return {**entry, "path": path, "size": len(data)}

    def set_enabled(self, path: str, enabled: bool) -> bool:
        """启用/停用补丁(停用的不参与构建)。"""
        if path not in self._meta:
            return False
        self._meta[path]["enabled"] = bool(enabled)
        self._save()
        return True

    def put_text(self, path: str, text: str) -> dict:
        return self.put_bytes(path, text.encode("utf-8"), {
            "source": "text_edit", "orig_name": os.path.basename(path),
            "orig_ext": os.path.splitext(path)[1].lower(),
            "note": "文本编辑", "settings": {"kind": "text"},
        })

    def remove(self, path: str) -> bool:
        if path not in self._meta:
            return False
        blob = self._blob(path)
        if os.path.exists(blob):
            os.remove(blob)
        del self._meta[path]
        self._save()
        return True

    def clear(self):
        for path in list(self._meta):
            self.remove(path)

    # -------------------------------------------------------------- image processing

    @staticmethod
    def _apply_bottom_fade(img: Image.Image, fade: float = 0.25) -> Image.Image:
        """底部渐变透明(垂直均匀淡出),模拟官方联机立绘的人物截断效果。

        实测官方 *_mp.png:内容至约 70% 高度处开始半透明,线性淡出到 88%
        处全透明,以下全空。这里对画布底部 fade 比例做 1->0 线性 alpha 渐变。
        输入为 RGB(用户拖入的 JPG / 无 alpha PNG)时先补全透明通道,否则
        渐变无处施加,半身效果会静默失效。
        """
        w, h = img.size
        if h <= 1:
            return img
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        fade = max(0.05, min(0.9, fade))
        start = int(h * (1 - fade))
        if start >= h - 1:
            return img
        col = Image.new("L", (1, h), 255)
        for y in range(start, h):
            t = (h - 1 - y) / (h - 1 - start)  # 1 -> 0
            col.putpixel((0, y), max(0, min(255, int(round(255 * t)))))
        mask = col.resize((w, h), Image.Resampling.BILINEAR)
        _, _, _, alpha = img.split()
        out = img.copy()
        out.putalpha(Image.composite(alpha, Image.new("L", (w, h), 0), mask))
        return out

    @staticmethod
    def _apply_diamond_mask(img: Image.Image) -> Image.Image:
        """套用内切菱形 alpha 蒙版(顶点在四边中点,与 Arcaea 官方头像一致)。

        官方头像素材本身就是"正方形画布 + 菱形镂空"的 RGBA 图(四角全透明),
        直接替换成实心方块图会在游戏里穿帮;此蒙版把替换图裁成同样的菱形。
        仅对带 alpha 的图生效,RGB 图先建一个菱形 alpha 通道。
        """
        w, h = img.size
        if w <= 0 or h <= 0:
            return img
        mask = Image.new("L", (w, h), 0)
        px = mask.load()
        # 逐像素解析判定内切菱形(避免多边形光栅化把顶点像素裁掉):
        #   |2x-(w-1)|/w + |2y-(h-1)|/h <= 1  (整数交叉相乘)
        den = w * h
        for y in range(h):
            dy = abs(2 * y - (h - 1)) * w
            for x in range(w):
                if abs(2 * x - (w - 1)) * h + dy <= den:
                    px[x, y] = 255
        if img.mode == "RGBA":
            _, _, _, alpha = img.split()
            new_alpha = Image.composite(alpha, Image.new("L", (w, h), 0), mask)
            out = img.copy()
            out.putalpha(new_alpha)
            return out
        if img.mode == "RGB":
            out = img.convert("RGBA")
            out.putalpha(mask)
            return out
        return img

    @staticmethod
    def _crop_to_aspect(img: Image.Image, tw: int, th: int, align: str = "center") -> Image.Image:
        """裁切到目标宽高比 tw/th,不拉伸变形。

        align: 'center' 居中裁切 | 'top' 保留顶部 | 'bottom' 保留底部。
        若比例已一致或目标尺寸未知则原样返回。
        """
        w, h = img.size
        if tw <= 0 or th <= 0 or w <= 0 or h <= 0:
            return img
        target = tw / th
        cur = w / h
        if abs(cur - target) < 1e-4:
            return img
        if cur > target:
            # 太宽:裁掉左右
            nw = max(1, min(w, int(round(h * target))))
            if align == "top":
                x = 0
            elif align == "bottom":
                x = w - nw
            else:
                x = (w - nw) // 2
            return img.crop((x, 0, x + nw, h))
        # 太高:裁掉上下
        nh = max(1, min(h, int(round(w / target))))
        if align == "top":
            y = 0
        elif align == "bottom":
            y = h - nh
        else:
            y = (h - nh) // 2
        return img.crop((0, y, w, y + nh))

    @staticmethod
    def process_image(data: bytes, orig_ext: str, settings: dict) -> bytes:
        """Resize / crop / convert before storing. settings keys:
        keep_size (bool), scale (float), quality (int 1-100), fmt ('png'|'jpg'),
        fit ('crop'), fit_align ('center'|'top'|'bottom'),
        fit_zone (0<z<1: 联机立绘半身裁切,先保留源图顶部 z 再适配并底部淡出),
        shape ('diamond'|'none'|'auto' — 路由层按素材路径解析,菱形头像自动识别),
        orig_w / orig_h (原素材像素尺寸,由路由层提供)。

        处理优先级: fit 裁切校准 > keep_size 拉伸 > scale 缩放。
        fit='crop' 时先按原素材宽高比裁切(align 控制保留区域),再缩放到
        原素材精确尺寸 —— 铺满不变形;keep_size 为无比例校正的纯拉伸。
        shape='diamond' 时最后套内切菱形蒙版(匹配官方头像镂空形状)。
        """
        img = Image.open(io.BytesIO(data))
        img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P", "PA") else "RGB")
        fmt = (settings.get("fmt") or "png").lower()
        if fmt not in ("png", "jpg", "jpeg"):
            fmt = "png"
        if fmt in ("jpg", "jpeg"):
            fmt = "jpg"

        ow = settings.get("orig_w")
        oh = settings.get("orig_h")
        if settings.get("fit") == "crop" and ow and oh:
            # 联机立绘(半身)裁切:先保留源图顶部 fit_zone 比例(头部+胸肩),
            # 再裁到原素材比例 -> 缩放到原素材精确尺寸 -> 底部渐变淡出
            zone = settings.get("fit_zone")
            is_bust = bool(zone) and 0 < zone < 1
            if is_bust:
                h = max(1, int(round(img.height * zone)))
                img = img.crop((0, 0, img.width, h))
            img = PatchStore._crop_to_aspect(img, ow, oh, settings.get("fit_align") or "center")
            img = img.resize((ow, oh), Image.LANCZOS)
            if is_bust and fmt == "png":
                img = PatchStore._apply_bottom_fade(img)
        elif settings.get("keep_size"):
            # stretch to original dimensions if known
            if ow and oh:
                img = img.resize((ow, oh), Image.LANCZOS)
        elif settings.get("scale") and settings["scale"] not in (1, 100):
            s = settings["scale"] / 100.0
            img = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)

        if settings.get("shape") == "diamond" and fmt == "png":
            # 头像菱形蒙版(JPG 无 alpha,跳过)
            img = PatchStore._apply_diamond_mask(img)

        buf = io.BytesIO()
        if fmt == "png":
            img.save(buf, "PNG", optimize=True)
        else:
            # JPG 无透明通道:合成到白色底(黑底在浅色界面里太突兀)
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                bg.paste(img, mask=img.split()[3])
            else:
                bg.paste(img)
            bg.save(buf, "JPEG", quality=int(settings.get("quality", 90)))
        return buf.getvalue()


# ------------------------------------------------------------------ pack export/import

def export_pack(store: PatchStore, out_zip: str) -> str:
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        meta = {}
        for item in store.list():
            blob = store._blob(item["path"])
            z.write(blob, "blobs/" + _key(item["path"]) + ".bin")
            meta[item["path"]] = {k: v for k, v in item.items() if k not in ("path", "exists", "size")}
        z.writestr("patches.json", json.dumps(meta, ensure_ascii=False, indent=2))
    return out_zip


def import_pack(store: PatchStore, zip_path: str) -> int:
    count = 0
    with zipfile.ZipFile(zip_path) as z:
        meta = json.loads(z.read("patches.json").decode("utf-8"))
        for path, m in meta.items():
            blob_name = "blobs/" + _key(path) + ".bin"
            if blob_name not in z.namelist():
                continue
            data = z.read(blob_name)
            store.put_bytes(path, data, m)
            count += 1
    return count
