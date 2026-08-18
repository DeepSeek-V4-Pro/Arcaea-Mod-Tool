"""Fast APK zip engine.

APK is a zip archive. Instead of extracting 1.8GB and recompressing everything,
we parse the central directory and rebuild the archive by copying raw local
records byte-for-byte; only replaced / added entries are (re)compressed.

Output is always a "clean" zip32 archive:
  * data descriptors (flag bit 3) are eliminated by rewriting local headers
  * stored entries are 4-byte aligned (zipalign style, extra padding)
  * EOCD / central directory are rebuilt with correct offsets
"""

from __future__ import annotations

import os
import struct
import threading
import time
import zlib
from dataclasses import dataclass, field

EOCD_SIG = b"PK\x05\x06"
ZIP64_EOCD_SIG = b"PK\x06\x06"
ZIP64_LOC_SIG = b"PK\x06\x07"
LOCAL_SIG = b"PK\x03\x04"
CENTRAL_SIG = b"PK\x01\x02"

ZIP64_EXTRA_ID = 0x0001
FLAG_UTF8 = 0x0800
FLAG_DATA_DESCRIPTOR = 0x0008

# extensions that are already compressed: store them as-is (fast, no size gain from deflate)
STORE_EXTS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ogg", ".wav", ".mp3",
    ".m4a", ".otf", ".ttf", ".zip", ".gz", ".7z", ".rar", ".mp4", ".webm",
}


class ZipError(Exception):
    pass


@dataclass
class Entry:
    name: str
    method: int
    flags: int
    crc: int
    csize: int
    usize: int
    header_offset: int
    local_fn_len: int
    local_extra_len: int
    central_extra: bytes
    comment: bytes
    dos_date: int
    dos_time: int
    version_made: int
    version_needed: int
    internal_attr: int
    external_attr: int

    @property
    def local_record_size(self) -> int:
        """Bytes the entry occupies in the original file (header + data, no descriptor)."""
        return 30 + self.local_fn_len + self.local_extra_len + self.csize

    @property
    def is_dir(self) -> bool:
        return self.name.endswith("/") and self.usize == 0


def _parse_extra(extra: bytes) -> dict:
    out = {}
    i = 0
    while i + 4 <= len(extra):
        eid, size = struct.unpack_from("<HH", extra, i)
        i += 4
        if i + size > len(extra):
            break
        out[eid] = extra[i:i + size]
        i += size
    return out


def read_central_directory(apk_path: str) -> tuple[list[Entry], bytes, bytes]:
    """Parse the central directory. Returns (entries, central_dir_bytes, eocd_bytes).

    Results are cached in memory keyed by (path, mtime, size):素材浏览会产生大量
    逐条读取请求(缩略图等),每次全量解析 7k+ 条目录会拖垮服务,缓存后接近零开销。
    """
    st = os.stat(apk_path)
    key = (st.st_mtime_ns, st.st_size)
    cached = _cd_state["cache"]
    if cached is not None and cached["path"] == apk_path and cached["key"] == key:
        return cached["entries"], cached["cd"], cached["eocd"]
    entries, cd_raw, eocd_bytes = _parse_central_directory(apk_path)
    with _cd_lock:
        _cd_state["cache"] = {
            "path": apk_path, "key": key,
            "entries": entries, "cd": cd_raw, "eocd": eocd_bytes,
        }
    return entries, cd_raw, eocd_bytes


_cd_state: dict = {"cache": None}
_cd_lock = threading.Lock()


def _parse_central_directory(apk_path: str) -> tuple[list[Entry], bytes, bytes]:
    with open(apk_path, "rb") as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()

        # locate EOCD: scan backwards for PK\x05\x06 (max 65557 bytes back)
        back = min(file_size, 65557)
        f.seek(file_size - back)
        tail = f.read(back)
        pos = tail.rfind(EOCD_SIG)
        if pos < 0:
            raise ZipError("EOCD not found; not a zip archive")
        eocd = tail[pos:]
        if len(eocd) < 22:
            raise ZipError("truncated EOCD")
        disk_no, cd_disk, n_this, n_total, cd_size, cd_off, comment_len = struct.unpack_from(
            "<HHHHIIH", eocd, 4)
        eocd_bytes = eocd[:22 + comment_len]

        zip64 = False
        if cd_off == 0xFFFFFFFF or cd_size == 0xFFFFFFFF or n_total == 0xFFFF:
            zip64 = True
        if zip64:
            # locate zip64 EOCD via locator right before EOCD
            loc_pos = file_size - back + pos - 20
            if loc_pos >= 0:
                f.seek(loc_pos)
                loc = f.read(20)
                if loc[:4] == ZIP64_LOC_SIG:
                    z64_off = struct.unpack_from("<Q", loc, 8)[0]
                    f.seek(z64_off)
                    z64 = f.read(56)
                    if z64[:4] == ZIP64_EOCD_SIG:
                        _, _, _, _, n_total, cd_size, cd_off = struct.unpack_from(
                            "<QIIQQQQ", z64, 4)
                        # note: n_total read twice (disk counts then totals); fix layout:
                        n_total = struct.unpack_from("<Q", z64, 32)[0]
                        cd_size = struct.unpack_from("<Q", z64, 40)[0]
                        cd_off = struct.unpack_from("<Q", z64, 48)[0]

        f.seek(cd_off)
        cd_raw = f.read(cd_size)

        entries: list[Entry] = []
        i = 0
        while i + 46 <= len(cd_raw):
            if cd_raw[i:i + 4] != CENTRAL_SIG:
                break
            (ver_made, ver_need, flags, method, dos_t, dos_d, crc,
             csize, usize, fn_len, extra_len, comment_len, disk_start,
             int_attr, ext_attr, hdr_off) = struct.unpack_from(
                "<HHHHHHIIIHHHHHII", cd_raw, i + 4)
            name = cd_raw[i + 46:i + 46 + fn_len].decode("utf-8", errors="replace")
            extra = cd_raw[i + 46 + fn_len:i + 46 + fn_len + extra_len]
            comment = cd_raw[i + 46 + fn_len + extra_len:i + 46 + fn_len + extra_len + comment_len]
            # zip64 fields in extra override
            if csize == 0xFFFFFFFF or usize == 0xFFFFFFFF or hdr_off == 0xFFFFFFFF:
                z64 = _parse_extra(extra).get(ZIP64_EXTRA_ID, b"")
                off = 0
                if usize == 0xFFFFFFFF:
                    usize = struct.unpack_from("<Q", z64, off)[0]
                    off += 8
                if csize == 0xFFFFFFFF:
                    csize = struct.unpack_from("<Q", z64, off)[0]
                    off += 8
                if hdr_off == 0xFFFFFFFF:
                    hdr_off = struct.unpack_from("<Q", z64, off)[0]
            # read local header to get its own fn/extra lengths
            f.seek(hdr_off)
            lh = f.read(30)
            if len(lh) == 30 and lh[:4] == LOCAL_SIG:
                l_fn, l_extra = struct.unpack_from("<HH", lh, 26)
            else:
                l_fn, l_extra = fn_len, extra_len
            entries.append(Entry(
                name=name, method=method, flags=flags, crc=crc,
                csize=csize, usize=usize, header_offset=hdr_off,
                local_fn_len=l_fn, local_extra_len=l_extra,
                central_extra=extra, comment=comment,
                dos_date=dos_d, dos_time=dos_t,
                version_made=ver_made, version_needed=ver_need,
                internal_attr=int_attr, external_attr=ext_attr,
            ))
            i += 46 + fn_len + extra_len + comment_len

    return entries, cd_raw, eocd_bytes


def _now_dos() -> tuple[int, int]:
    t = time.localtime()
    dos_time = (t.tm_hour << 11) | (t.tm_min << 5) | (t.tm_sec // 2)
    dos_date = ((t.tm_year - 1980) << 9) | (t.tm_mon << 5) | t.tm_mday
    return dos_time, dos_date


def _compress(data: bytes, name: str, level: int = 6) -> tuple[int, bytes]:
    ext = os.path.splitext(name)[1].lower()
    if ext in STORE_EXTS or len(data) < 64:
        return 0, data
    co = zlib.compressobj(level, zlib.DEFLATED, -15)
    out = co.compress(data) + co.flush()
    if len(out) >= len(data):
        return 0, data
    return 8, out


def build_apk(
    src: str,
    dst: str,
    replace: dict[str, bytes] | None = None,
    add: dict[str, bytes] | None = None,
    drop: set[str] | None = None,
    drop_prefixes: list[str] | None = None,
    on_progress=None,
    deflate_level: int = 6,
) -> list[Entry]:
    """Clean reimplementation of build_apk (no leftover placeholder logic)."""
    replace = replace or {}
    add = add or {}
    drop = drop or set()
    drop_prefixes = drop_prefixes or []

    entries, _cd, _eocd = read_central_directory(src)
    existing_names = {e.name for e in entries}
    for k in replace:
        if k in add:
            raise ZipError(f"path '{k}' in both replace and add")
    wanted = [
        e for e in entries
        if e.name not in drop and not any(e.name.startswith(p) for p in drop_prefixes)
    ]
    additions = [(k, v) for k, v in add.items() if k not in existing_names]

    plan: list[tuple[Entry | None, bytes | None, str]] = []
    for e in wanted:
        plan.append((e, replace.get(e.name), e.name))
    for name, data in additions:
        plan.append((None, data, name))

    total = len(plan)
    done = 0
    out_entries: list[Entry] = []

    with open(src, "rb") as fin, open(dst, "wb") as fout:
        offset = 0
        for orig, new_data, name in plan:
            if orig is None:
                method, compressed = _compress(new_data, name, deflate_level)
                crc = zlib.crc32(new_data) & 0xFFFFFFFF
                csize = len(compressed)
                usize = len(new_data)
                flags = FLAG_UTF8 | (0x0001 if method == 8 else 0)
                dos_t, dos_d = _now_dos()
                ver_need = 20
                ver_made = 20
                int_attr = 0
                ext_attr = 0
                comment = b""
                central_extra_orig = b""
            else:
                method = orig.method
                crc = orig.crc
                csize = orig.csize
                usize = orig.usize
                flags = orig.flags & ~FLAG_DATA_DESCRIPTOR
                dos_t, dos_d = orig.dos_time, orig.dos_date
                ver_need = orig.version_needed
                ver_made = orig.version_made
                int_attr = orig.internal_attr
                ext_attr = orig.external_attr
                comment = orig.comment
                central_extra_orig = orig.central_extra
                if new_data is not None:
                    method, compressed = _compress(new_data, name, deflate_level)
                    crc = zlib.crc32(new_data) & 0xFFFFFFFF
                    csize = len(compressed)
                    usize = len(new_data)
                    flags = FLAG_UTF8 | (0x0001 if method == 8 else 0)
                    dos_t, dos_d = _now_dos()
                    ver_need = 20

            # data bytes
            if new_data is not None:
                data = compressed
                extra_bytes = b""
            else:
                fin.seek(orig.header_offset + 30 + orig.local_fn_len + orig.local_extra_len)
                data = fin.read(orig.csize)
                extra_bytes = central_extra_orig

            fn = name.encode("utf-8")

            # stored entries: pad extra so data starts at a 4-byte boundary
            if method == 0:
                header_end = offset + 30 + len(fn)
                pad = (4 - (header_end % 4)) % 4
                if pad:
                    extra_bytes = extra_bytes + b"\x00" * pad
                elif new_data is None and orig.local_extra_len != len(extra_bytes):
                    # keep byte-exact local extra size for raw entries
                    extra_bytes = b""

            local = struct.pack(
                "<IHHHHHIIIHH",
                int.from_bytes(LOCAL_SIG, "little"),
                ver_need,
                flags,
                method,
                dos_t, dos_d,
                crc, csize, usize,
                len(fn), len(extra_bytes),
            )
            fout.write(local)
            fout.write(fn)
            fout.write(extra_bytes)
            fout.write(data)

            header_offset = offset
            offset += 30 + len(fn) + len(extra_bytes) + csize

            out_entries.append(Entry(
                name=name, method=method, flags=flags,
                crc=crc, csize=csize, usize=usize, header_offset=header_offset,
                local_fn_len=len(fn), local_extra_len=len(extra_bytes),
                central_extra=extra_bytes, comment=comment,
                dos_date=dos_d, dos_time=dos_t,
                version_made=ver_made, version_needed=ver_need,
                internal_attr=int_attr, external_attr=ext_attr,
            ))

            done += 1
            if on_progress:
                on_progress(done, total, name)

        cd_offset = offset
        cd = bytearray()
        for e in out_entries:
            fn = e.name.encode("utf-8")
            cd += struct.pack(
                "<IHHHHHHIIIHHHHHII",
                int.from_bytes(CENTRAL_SIG, "little"),
                e.version_made, e.version_needed, e.flags, e.method,
                e.dos_time, e.dos_date, e.crc, e.csize, e.usize,
                len(fn), len(e.central_extra), len(e.comment),
                0, e.internal_attr, e.external_attr, e.header_offset,
            )
            cd += fn
            cd += e.central_extra
            cd += e.comment
        cd_size = len(cd)
        fout.write(cd)

        eocd = struct.pack(
            "<IHHHHIIH",
            int.from_bytes(EOCD_SIG, "little"),
            0, 0, len(out_entries), len(out_entries),
            cd_size, cd_offset, 0,
        )
        fout.write(eocd)

    return out_entries


def read_entry_data(apk_path: str, entry: Entry) -> bytes:
    """Read one entry's raw (decompressed) data on demand."""
    with open(apk_path, "rb") as f:
        f.seek(entry.header_offset + 30 + entry.local_fn_len + entry.local_extra_len)
        raw = f.read(entry.csize)
    if entry.method == 0:
        return raw
    if entry.method == 8:
        return zlib.decompress(raw, -15)
    raise ZipError(f"unsupported compression method {entry.method} for {entry.name}")
