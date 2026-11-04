"""
Box-art <-> EverDrive N8 art file (.BIN) conversion and ROM fingerprints.

Art file (2048 bytes, 4 SD sectors) — loaded by the OS straight into CHR-RAM $1000:
  0x000-0x5FF  48 sprites (8 columns x 6 rows of 8x16), 32 bytes each
               (top 8x8 tile, then bottom 8x8 tile, NES 2bpp planar)
  0x600-0x601  magic "NA"
  0x602        version (1)
  0x603        reserved
  0x604-0x60F  4 sprite palettes x 3 colours (NES palette indices; colour 0 = transparent, unused)
  0x610-0x63F  palette index (0-3) for each of the 48 sprites
Image size: 64 x 96 px, shown right of the "Info Arquivo" popup.

Fingerprint (what the console computes, so art follows ROM content, not file names):
  CRC-32 of file bytes [512, 2560)   -> EDFC/ARTS/<8 hex>.BIN
Full CRC (matching against No-Intro / libretro database):
  CRC-32 of the ROM without its 16-byte iNES header (and trainer, if flagged)
"""
import zlib

ART_W, ART_H = 64, 96
COLS, ROWS = 8, 6
ART_SIZE = 2048
META = 0x600
FP_START, FP_LEN = 512, 2048

# 2C02 palette (same table the emulator renders with)
NES_RGB = [
    (84,84,84), (0,30,116), (8,16,144), (48,0,136), (68,0,100), (92,0,48), (84,4,0), (60,24,0),
    (32,42,0), (8,58,0), (0,64,0), (0,60,0), (0,50,60), (0,0,0), (0,0,0), (0,0,0),
    (152,150,152), (8,76,196), (48,50,236), (92,30,228), (136,20,176), (160,20,100), (152,34,32), (120,60,0),
    (84,90,0), (40,114,0), (8,124,0), (0,118,40), (0,102,120), (0,0,0), (0,0,0), (0,0,0),
    (236,238,236), (76,154,236), (120,124,236), (176,98,236), (228,84,236), (236,88,180), (236,106,100), (212,136,32),
    (160,170,0), (116,196,0), (76,208,32), (56,204,108), (56,180,204), (60,60,60), (0,0,0), (0,0,0),
    (236,238,236), (168,204,236), (188,188,236), (212,178,236), (236,174,236), (236,174,212), (236,180,176), (228,196,144),
    (204,210,120), (180,222,120), (168,226,144), (152,226,180), (160,214,228), (160,162,160), (0,0,0), (0,0,0),
]
# usable colours: drop the "blacker than black" $0D and duplicate blacks / white
USABLE = [i for i in range(64) if i not in (0x0D, 0x0E, 0x1D, 0x1E, 0x1F, 0x2E, 0x2F, 0x3E, 0x3F, 0x30)]



# ---------------------------------------------------------------- fingerprints
def fingerprint(rom: bytes) -> int:
    return zlib.crc32(rom[FP_START:FP_START + FP_LEN]) & 0xFFFFFFFF


def full_crc(rom: bytes) -> int:
    body = rom
    if rom[:4] == b"NES\x1a":
        body = rom[16 + (512 if rom[6] & 0x04 else 0):]
    return zlib.crc32(body) & 0xFFFFFFFF


def art_filename(rom: bytes) -> str:
    return f"{fingerprint(rom):08X}.BIN"


# ---------------------------------------------------------------- conversion
def _lab(rgb):
    """sRGB (..., 3) uint8 -> CIELAB (..., 3) float."""
    import numpy as np
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


_NES_LAB = None
L_WEIGHT = (1.6, 1.0, 1.0)      # favour lightness: keeps shapes/contrast readable


def _nes_tables():
    global _NES_LAB
    if _NES_LAB is None:
        import numpy as np
        lab = _lab(np.array([NES_RGB[i] for i in USABLE], dtype=np.uint8))
        dist = (((lab[:, None, :] - lab[None, :, :]) * L_WEIGHT) ** 2).sum(-1)
        _NES_LAB = (lab, dist)
    return _NES_LAB


def _load(img_or_path):
    from PIL import Image, ImageEnhance, ImageOps
    import numpy as np
    img = img_or_path if hasattr(img_or_path, "size") else Image.open(img_or_path)
    img = img.convert("RGBA")
    bg = Image.new("RGBA", img.size, (0, 0, 0, 255))
    img = Image.alpha_composite(bg, img).convert("RGB")
    img = ImageOps.fit(img, (ART_W, ART_H), method=Image.LANCZOS, centering=(0.5, 0.5))
    img = ImageEnhance.Color(img).enhance(1.2)
    img = ImageEnhance.Sharpness(img).enhance(1.6)
    return np.asarray(img, dtype=np.uint8)


def _snap(pix):
    """Nearest usable NES colour (index into USABLE) per pixel, in Lab."""
    import numpy as np
    lab, _ = _nes_tables()
    plab = _lab(pix).reshape(-1, 3)
    d = (((plab[:, None, :] - lab[None, :, :]) * L_WEIGHT) ** 2).sum(-1)
    return d.argmin(1).reshape(ART_H, ART_W)


def _cell_hists(idx):
    import numpy as np
    n = len(USABLE)
    h = np.zeros((COLS * ROWS, n))
    for i in range(COLS * ROWS):
        cx, cy = (i % COLS) * 8, (i // COLS) * 16
        h[i] = np.bincount(idx[cy:cy + 16, cx:cx + 8].ravel(), minlength=n)
    return h


def _pal_cost(hist, pal, dist):
    """hist: (cells, n) -> per-cell error of mapping each colour to nearest in pal."""
    return hist @ dist[:, list(pal)].min(1)


def _best3(hist_sum, dist):
    """Exhaustive best 3-colour palette for a colour histogram."""
    import itertools
    import numpy as np
    present = np.nonzero(hist_sum)[0]
    if len(present) <= 3:
        p = list(present) + [present[0]] * (3 - len(present))
        return tuple(p)
    # keep the 14 most frequent colours as candidates (C(14,3) = 364 subsets)
    cand = present[np.argsort(-hist_sum[present])][:14]
    best, best_c = None, None
    for trio in itertools.combinations(cand, 3):
        c = float(hist_sum @ dist[:, list(trio)].min(1))
        if best_c is None or c < best_c:
            best, best_c = trio, c
    return best


def _fit_palettes(hist, dist, seed):
    import numpy as np
    rng = np.random.default_rng(seed)
    cells = hist.shape[0]
    assign = rng.integers(0, 4, cells) if seed else None
    if assign is None:
        # deterministic start: split cells by dominant-colour lightness quartile
        lab, _ = _nes_tables()
        dom = hist.argmax(1)
        order = np.argsort(lab[dom, 0])
        assign = np.empty(cells, dtype=int)
        assign[order] = np.arange(cells) * 4 // cells
    pals = [None] * 4
    for _ in range(6):
        for k in range(4):
            members = hist[assign == k]
            src = members.sum(0) if len(members) else hist.sum(0)
            pals[k] = _best3(src, dist)
        costs = np.stack([_pal_cost(hist, p, dist) for p in pals], 1)
        new = costs.argmin(1)
        if (new == assign).all():
            break
        assign = new
    return pals, assign, float(costs.min(1).sum())


def convert(img_or_path) -> bytes:
    import numpy as np
    _, dist = _nes_tables()
    pix = _load(img_or_path)
    idx = _snap(pix)
    hist = _cell_hists(idx)

    best = None
    for seed in range(4):                       # a few restarts, keep the best
        r = _fit_palettes(hist, dist, seed)
        if best is None or r[2] < best[2]:
            best = r
    pal_idx, assign, _ = best
    pals = [[USABLE[c] for c in p] for p in pal_idx]

    data = bytearray(ART_SIZE)
    for i in range(COLS * ROWS):
        cx, cy = (i % COLS) * 8, (i // COLS) * 16
        p = list(pal_idx[assign[i]])
        block = idx[cy:cy + 16, cx:cx + 8]
        vals = (1 + dist[block.ravel()][:, p].argmin(1)).tolist()
        for half in range(2):
            base = i * 32 + half * 16
            for row in range(8):
                v = vals[(half * 8 + row) * 8:(half * 8 + row) * 8 + 8]
                lo = hi = 0
                for x, c in enumerate(v):
                    lo |= (c & 1) << (7 - x)
                    hi |= ((c >> 1) & 1) << (7 - x)
                data[base + row] = lo
                data[base + 8 + row] = hi
    data[META:META + 4] = b"NA\x01\x00"
    for k in range(4):
        data[META + 4 + k * 3: META + 7 + k * 3] = bytes(pals[k])
    data[META + 16: META + 64] = bytes(int(a) for a in assign)
    return bytes(data)


def render(art: bytes, scale=4):
    """Decode an art file back to a PIL image (what the console shows)."""
    from PIL import Image
    assert art[META:META + 2] == b"NA", "not an art file"
    img = Image.new("RGB", (ART_W, ART_H))
    for i in range(48):
        pal = art[META + 4 + art[META + 16 + i] * 3:][:3]
        cx, cy = (i % COLS) * 8, (i // COLS) * 16
        for half in range(2):
            base = i * 32 + half * 16
            for row in range(8):
                lo, hi = art[base + row], art[base + 8 + row]
                for x in range(8):
                    c = ((lo >> (7 - x)) & 1) | (((hi >> (7 - x)) & 1) << 1)
                    img.putpixel((cx + x, cy + half * 8 + row), NES_RGB[pal[c - 1]] if c else (0, 0, 0))
    return img.resize((ART_W * scale, ART_H * scale), Image.NEAREST)


if __name__ == "__main__":
    import sys
    src, dst = sys.argv[1], sys.argv[2]
    art = convert(src)
    open(dst, "wb").write(art)
    if len(sys.argv) > 3:
        render(art).save(sys.argv[3])
