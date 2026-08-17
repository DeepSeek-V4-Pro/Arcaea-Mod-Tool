"""APK v2 signing (pure Python).

Follows AOSP apksig:
  * content digest = chunked digest (0xa5-prefixed 1MiB chunks, 0x5a top level)
    over [zip prefix][central dir][EOCD with cd_offset rewritten to sb_offset]
  * signer block: signed data (digests|certs|attrs) + signatures + public key
  * algorithm 0x0101: RSASSA-PKCS1-v1_5 with SHA-256 (max device compat)

The original Arcaea APK carries a v2 block only (no v3), so we sign v2 only.
Verification re-implements the digest + signature checks locally (apksigtool's
HASHERS table mislabels 0x0103, so we cannot rely on its verify for 0x0101).
"""

from __future__ import annotations

import hashlib
import os
import struct
from datetime import datetime, timedelta

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.x509.oid import NameOID

from .zipio import read_central_directory, EOCD_SIG

V2_BLOCK_ID = 0x7109871A
BLOCK_MAGIC = b"APK Sig Block 42"
ALG_RSA_PKCS1_SHA256 = 0x0101
CHUNK_SIZE = 1 << 20
PREFIX_CHUNK = b"\xa5"
PREFIX_TOP = b"\x5a"


class SignError(Exception):
    pass


# ---------------------------------------------------------------- key store

def _default_keydir() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "keystore")


def load_or_create_key(keydir: str | None = None) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    keydir = keydir or _default_keydir()
    os.makedirs(keydir, exist_ok=True)
    key_path = os.path.join(keydir, "modkey.pem")
    cert_path = os.path.join(keydir, "modcert.pem")
    if os.path.exists(key_path) and os.path.exists(cert_path):
        with open(key_path, "rb") as f:
            key = serialization.load_pem_private_key(f.read(), password=None)
        with open(cert_path, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
        return key, cert

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Arcaea Mod Tool")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365 * 30))
        .sign(key, hashes.SHA256())
    )
    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    return key, cert


# ------------------------------------------------------------- digest math

def chunked_digest(buf: bytes) -> bytes:
    """AOSP chunked digest: 0xa5-prefixed chunk hashes, 0x5a top level."""
    h = hashlib.sha256()
    for i in range(0, len(buf), CHUNK_SIZE):
        chunk = buf[i:i + CHUNK_SIZE]
        h.update(hashlib.sha256(PREFIX_CHUNK + struct.pack("<I", len(chunk)) + chunk).digest())
    top = h.digest()
    return hashlib.sha256(PREFIX_TOP + struct.pack("<I", 1) + top).digest()


def compute_content_digest(apk_path: str, prefix_end: int, cd_start: int,
                           eocd_offset: int, eocd_size: int) -> bytes:
    """digest over [0..prefix_end) + [cd_start..eocd_offset) + EOCD(cd→prefix_end).

    Signing (no block yet): prefix_end == cd_start == cd_offset.
    Verifying (block present): prefix_end = block start, cd_start = EOCD's
    cd_offset (block lies between them and is excluded from the digest)."""
    h = hashlib.sha256()
    with open(apk_path, "rb") as f:
        for start, end in ((0, prefix_end), (cd_start, eocd_offset)):
            f.seek(start)
            remaining = end - start
            while remaining > 0:
                chunk = f.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                h.update(hashlib.sha256(PREFIX_CHUNK + struct.pack("<I", len(chunk)) + chunk).digest())
        f.seek(eocd_offset)
        eocd = f.read(eocd_size)
    eocd_patched = eocd[:16] + struct.pack("<I", prefix_end) + eocd[20:]
    h.update(hashlib.sha256(PREFIX_CHUNK + struct.pack("<I", len(eocd_patched)) + eocd_patched).digest())
    top = h.digest()
    return hashlib.sha256(PREFIX_TOP + struct.pack("<I", 1) + top).digest()


# ------------------------------------------------------------ block builder

def _lp(data: bytes) -> bytes:
    return struct.pack("<I", len(data)) + data


def build_v2_block(content_digest: bytes, key, cert) -> bytes:
    """Full APK Signing Block containing one v2 signer."""
    digests_seg = _lp(struct.pack("<I", ALG_RSA_PKCS1_SHA256) + _lp(content_digest))
    certs_seg = _lp(cert.public_bytes(serialization.Encoding.DER))
    attrs_seg = b""
    signed_data = _lp(digests_seg) + _lp(certs_seg) + _lp(attrs_seg)

    sig = key.sign(
        signed_data,
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    signatures_seg = _lp(struct.pack("<I", ALG_RSA_PKCS1_SHA256) + _lp(sig))
    public_key = key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    signer = _lp(signed_data) + _lp(signatures_seg) + _lp(public_key)
    # value = length-prefixed sequence of length-prefixed signers
    value = struct.pack("<I", len(signer) + 4) + _lp(signer)

    # AOSP pair format: uint64 size (value length + 4 for the ID) + uint32 ID + value
    pairs = struct.pack("<QI", len(value) + 4, V2_BLOCK_ID) + value
    size = len(pairs) + 24  # second size field + magic
    return struct.pack("<Q", size) + pairs + struct.pack("<Q", size) + BLOCK_MAGIC


# ------------------------------------------------------------------ signing

def locate_eocd(apk_path: str) -> tuple[int, int]:
    """Return (eocd_offset, eocd_size) for a zip32 archive."""
    with open(apk_path, "rb") as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()
        back = min(file_size, 65557)
        f.seek(file_size - back)
        tail = f.read(back)
        pos = tail.rfind(EOCD_SIG)
        if pos < 0:
            raise SignError("EOCD not found")
        eocd_abs = file_size - back + pos
        f.seek(eocd_abs)
        eocd = f.read()
        if len(eocd) < 22:
            raise SignError("truncated EOCD")
        cd_size = struct.unpack_from("<I", eocd, 12)[0]
        cd_offset = struct.unpack_from("<I", eocd, 16)[0]
        eocd_size = 22 + struct.unpack_from("<H", eocd, 20)[0]
        if eocd_abs + eocd_size != file_size:
            raise SignError("unexpected data after EOCD (zip64 not supported)")
        if cd_offset + cd_size != eocd_abs:
            raise SignError(f"central dir end {cd_offset + cd_size} != EOCD @ {eocd_abs}")
        return eocd_abs, eocd_size


def sign_apk(apk_path: str, keydir: str | None = None, out_path: str | None = None,
             on_progress=None) -> str:
    """Sign an unsigned APK (v2). Writes to out_path (default: in-place)."""
    key, cert = load_or_create_key(keydir)
    read_central_directory(apk_path)  # sanity: must parse
    eocd_abs, eocd_size = locate_eocd(apk_path)
    cd_offset = None
    with open(apk_path, "rb") as f:
        f.seek(eocd_abs)
        eocd = f.read(eocd_size)
    cd_offset = struct.unpack_from("<I", eocd, 16)[0]

    if on_progress:
        on_progress(0, 3, "计算内容摘要")
    digest = compute_content_digest(apk_path, cd_offset, cd_offset, eocd_abs, eocd_size)

    if on_progress:
        on_progress(1, 3, "构建签名块")
    block = build_v2_block(digest, key, cert)

    if on_progress:
        on_progress(2, 3, "写入签名")
    out = out_path or apk_path
    with open(apk_path, "rb") as fin, open(out, "wb") as fout:
        fin.seek(0)
        remaining = cd_offset
        while remaining > 0:
            chunk = fin.read(min(8 << 20, remaining))
            if not chunk:
                break
            fout.write(chunk)
            remaining -= len(chunk)
        fout.write(block)
        fin.seek(cd_offset)
        rest = fin.read()
        eocd_in_rest = rest[-eocd_size:]
        patched = eocd_in_rest[:16] + struct.pack("<I", cd_offset + len(block)) + eocd_in_rest[20:]
        fout.write(rest[:len(rest) - eocd_size] + patched)

    if on_progress:
        on_progress(3, 3, "完成")
    return out


# ------------------------------------------------------------------ verify

def extract_signing_block(apk_path: str) -> tuple[int, bytes]:
    """Locate the APK Signing Block.

    Layout: [size1][pairs][size2][magic], size1 == size2 == len(pairs)+24,
    block total = size2+8, block starts at cd_offset-size2-8 (= sb_offset).
    The digest boundary equals the block start, so sign/verify boundaries are
    consistent (sign: cd_offset of unsigned zip; verify: cd_offset-size2-8)."""
    eocd_abs, _ = locate_eocd(apk_path)
    with open(apk_path, "rb") as f:
        f.seek(eocd_abs)
        eocd = f.read(22)
        cd_offset = struct.unpack_from("<I", eocd, 16)[0]
        f.seek(cd_offset - 16)
        if f.read(16) != BLOCK_MAGIC:
            raise SignError("no APK Signing Block present")
        f.seek(cd_offset - 24)
        sb_size2 = struct.unpack("<Q", f.read(8))[0]
        sb_offset = cd_offset - sb_size2 - 8
        f.seek(sb_offset)
        sb_size1 = struct.unpack("<Q", f.read(8))[0]
        if sb_size1 != sb_size2:
            raise SignError("signing block sizes mismatch")
        f.seek(sb_offset)
        block = f.read(cd_offset - sb_offset)
    return sb_offset, block


def parse_v2_signer(block: bytes) -> dict:
    """Parse the v2 block; returns signer fields (for verification)."""
    if block[-16:] != BLOCK_MAGIC:
        raise SignError("bad magic")
    size1 = struct.unpack_from("<Q", block, 0)[0]
    size2 = struct.unpack_from("<Q", block, len(block) - 24)[0]
    if size1 != size2 or size1 != len(block) - 8:
        raise SignError("bad block size")
    data = block[8:-24]
    pairs = {}
    while data:
        plen, pid = struct.unpack_from("<QI", data, 0)
        pairs[pid] = data[12:12 + plen - 4]
        data = data[12 + plen - 4:]
    if V2_BLOCK_ID not in pairs:
        raise SignError("no v2 block")
    value = pairs[V2_BLOCK_ID]

    def take(buf):
        n = struct.unpack_from("<I", buf, 0)[0]
        return buf[4:4 + n], buf[4 + n:]

    seq_len = struct.unpack_from("<I", value, 0)[0]
    if seq_len != len(value) - 4:
        raise SignError("bad signer sequence length")
    signer, _ = take(value[4:])  # signer itself is length-prefixed
    signed_data, signer = take(signer)
    sigs_raw, signer = take(signer)
    pubkey, signer = take(signer)

    digests_seg, rest = take(signed_data)
    certs_seg, rest = take(rest)
    _attrs_seg, _rest = take(rest)
    digest_entry, _ = take(digests_seg)
    d_alg = struct.unpack_from("<I", digest_entry, 0)[0]
    d_len = struct.unpack_from("<I", digest_entry, 4)[0]
    d_val = digest_entry[8:8 + d_len]
    cert_der, _ = take(certs_seg)
    sig_entry, _ = take(sigs_raw)
    sig_alg = struct.unpack_from("<I", sig_entry, 0)[0]
    s_len = struct.unpack_from("<I", sig_entry, 4)[0]
    sig_val = sig_entry[8:8 + s_len]
    return {
        "digest_alg": d_alg, "digest": d_val,
        "cert": cert_der, "pubkey": pubkey,
        "sig_alg": sig_alg, "signature": sig_val,
        "signed_data": signed_data,
    }


def verify_apk(apk_path: str) -> dict:
    """Full local verification: digest + RSA signature + structure."""
    result = {"ok": False, "checks": []}

    def chk(name, ok, detail=""):
        result["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        return ok

    try:
        sb_offset, block = extract_signing_block(apk_path)
        signer = parse_v2_signer(block)
        if signer["digest_alg"] != ALG_RSA_PKCS1_SHA256:
            chk("digest_alg", False, f"unexpected alg {signer['digest_alg']:#x}")
            return result
        chk("structure", True, f"block@{sb_offset}")

        eocd_abs, eocd_size = locate_eocd(apk_path)
        with open(apk_path, "rb") as f:
            f.seek(eocd_abs)
            eocd = f.read(eocd_size)
        cd_actual = struct.unpack_from("<I", eocd, 16)[0]
        expected = compute_content_digest(apk_path, sb_offset, cd_actual, eocd_abs, eocd_size)
        chk("content_digest", expected == signer["digest"], "match" if expected == signer["digest"] else "MISMATCH")
        if expected != signer["digest"]:
            return result

        from cryptography.hazmat.primitives.asymmetric import rsa as rsa_mod
        pub = serialization.load_der_public_key(signer["pubkey"])
        try:
            pub.verify(signer["signature"], signer["signed_data"], padding.PKCS1v15(), hashes.SHA256())
            chk("rsa_signature", True)
        except InvalidSignature:
            chk("rsa_signature", False, "invalid signature")
            return result
        result["ok"] = all(c["ok"] for c in result["checks"])
    except Exception as ex:
        chk("exception", False, str(ex))
    return result


def structural_parse(apk_path: str) -> dict:
    """Cross-check with apksigtool's parser (structure only)."""
    from apksigcopier import extract_v2_sig
    from apksigtool import parse_apk_signing_block, APKSignatureSchemeBlock
    try:
        _off, sig_block = extract_v2_sig(apk_path)
        block = parse_apk_signing_block(sig_block)
        versions = []
        for p in block.pairs:
            if isinstance(p.value, APKSignatureSchemeBlock):
                versions.append(p.value.version)
        return {"ok": True, "versions": versions}
    except Exception as ex:
        return {"ok": False, "error": str(ex)}
