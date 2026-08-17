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
    def process_image(data: bytes, orig_ext: str, settings: dict) -> bytes:
        """Resize / convert before storing. settings keys:
        keep_size (bool), scale (float), quality (int 1-100), fmt ('png'|'jpg')"""
        img = Image.open(io.BytesIO(data))
        img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P", "PA") else "RGB")
        fmt = (settings.get("fmt") or "png").lower()
        if fmt not in ("png", "jpg", "jpeg"):
            fmt = "png"
        if fmt in ("jpg", "jpeg"):
            fmt = "jpg"

        if settings.get("keep_size"):
            # stretch to original dimensions if known
            ow = settings.get("orig_w")
            oh = settings.get("orig_h")
            if ow and oh:
                img = img.resize((ow, oh), Image.LANCZOS)
        elif settings.get("scale") and settings["scale"] not in (1, 100):
            s = settings["scale"] / 100.0
            img = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)

        buf = io.BytesIO()
        if fmt == "png":
            img.save(buf, "PNG", optimize=True)
        else:
            bg = Image.new("RGB", img.size, (0, 0, 0))
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
