"""
Theme banners (256x16 px, rows 0-1 of the screen), generated from code.

Each banner is drawn with the 4 colours of the theme's banner palette
(attribute palette 1, filled by the theme loader from the theme colours):
  0 = background (theme bd)   1 = shadow (sh)   2 = text (txt)   3 = highlight (hl)
Title: 8x16 cells (bold 5x7 font scaled to 6x14, highlight top / text bottom,
1 px shadow). Decorations are made of a few tiles repeated, so every banner
stays within the CHR budget (MAX_TILES unique tiles + the blank spacer tile).

build_banner_packages() returns, per theme:
  {'name', 'tiles': [(slot, 16 bytes)], 'nametable': 96 bytes, 'pal0', 'pixels'}
"""
import os

# id, name, banner title, pal0 = (bd, txt, hl, sh) — NES colours, as the theme loader uses them:
#   file list (palette 0): 1 = txt (file names), 2 = hl (LIST BACKGROUND), 3 = sh (folders/selection)
#   popups / status bar (palette 3): background = sh, text = white $30, highlight = hl
#   banner (palette 1): 0 = bd, 1 = sh, 2 = txt, 3 = hl
# So hl must be light and txt/sh dark. check_contrast() enforces it (CIE L* differences):
# v1.5 shipped PADRAO/SYNTHWAVE/CYBERPUNK/RETROCHIMP with text ~4-8 L* from the
# background, which a TV smears into unreadable fragments (looked like corruption).
THEMES = [
    (0, "RETROGAMER POA", "RETROGAMER POA", (0x0F, 0x17, 0x38, 0x16)),
    (1, "PADRAO",         "EVERDRIVE N8",   (0x0F, 0x00, 0x30, 0x02)),
    (2, "SYNTHWAVE",      "SYNTHWAVE",      (0x0F, 0x14, 0x3C, 0x12)),
    (3, "OUTRUN",         "OUTRUN",         (0x04, 0x17, 0x37, 0x16)),
    (4, "16-BIT",         "16-BIT",         (0x02, 0x01, 0x30, 0x11)),
    (5, "RETROCHIMP",     "RETROCHIMP",     (0x0F, 0x0A, 0x38, 0x19)),
    (6, "MAD DRUGA",      "MAD DRUGA",      (0x0F, 0x04, 0x30, 0x13)),
    (7, "CYBERPUNK",      "CYBERPUNK",      (0x02, 0x0C, 0x34, 0x12)),
    (8, "GAME BOY",       "GAME BOY",       (0x08, 0x19, 0x38, 0x0A)),
]
MIN_CONTRAST = 40          # L* between list text/selection and list background
MIN_POPUP_CONTRAST = 45    # L* between white popup text and popup background (sh)


def _lstar(c):
    from nes_art import NES_RGB
    r, g, b = [x / 255 for x in NES_RGB[c]]
    f = lambda v: ((v + 0.055) / 1.055) ** 2.4 if v > 0.04045 else v / 12.92
    y = 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
    return 116 * (y ** (1 / 3) if y > 0.008856 else 7.787 * y + 16 / 116) - 16


def check_contrast():
    bad = []
    for tid, name, _, (bd, txt, hl, sh) in THEMES:
        if abs(_lstar(txt) - _lstar(hl)) < MIN_CONTRAST:
            bad.append(f"{name}: file text vs list background")
        if abs(_lstar(sh) - _lstar(hl)) < MIN_CONTRAST:
            bad.append(f"{name}: folders/selection vs list background")
        if _lstar(0x30) - _lstar(sh) < MIN_POPUP_CONTRAST:
            bad.append(f"{name}: popup text vs popup background")
    assert not bad, "unreadable theme colours: " + "; ".join(bad)

# CHR slots the OS font leaves free (control-code slots of both font halves)
FREE_SLOTS = list(range(0x0B, 0x1F)) + list(range(0x8B, 0xA0))
BLANK_SLOT = 0x1F               # all-background tile, also used for the spacer row
MAX_TILES = 39                  # keeps the 9 packages inside bank $0B

FONT5x7 = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    " ": ["00000"] * 7,
}

W, H = 256, 16


def _canvas():
    return [[0] * W for _ in range(H)]


def _title(px, text, x0):
    """Draw text in 8-px cells starting at x0: bold 6x14 glyphs in hl (the light colour), shadow sh."""
    for i, ch in enumerate(text):
        g = FONT5x7[ch]
        cx = x0 + i * 8
        body = set()
        for gy, row in enumerate(g):
            for gx, bit in enumerate(row):
                if bit == "1":
                    for dy in (0, 1):
                        for dx in (0, 1):                 # 1x2 scale + 1 px bold
                            body.add((cx + gx + dx, 1 + gy * 2 + dy))
        for (x, y) in body:                               # shadow first
            if (x + 1, y + 1) not in body and x + 1 < W and y + 1 < H:
                px[y + 1][x + 1] = 1
        for (x, y) in body:
            px[y][x] = 3


def _title_x(text):
    return ((W - len(text) * 8) // 2) // 8 * 8          # tile aligned


def _fill(px, x0, x1, fn):
    for y in range(H):
        for x in range(x0, x1):
            c = fn(x, y)
            if c is not None:
                px[y][x] = c


# ---- per-theme decorations (left and right of the title) -------------------
def deco_flames(x, y):                       # RETROGAMER POA: flames rising from the bottom
    h = (3, 5, 8, 11, 7, 4, 9, 12)[(x // 2) % 8]
    if y >= H - h:
        return 3 if y >= H - h // 2 else 2
    return 1 if y == 0 else None


def deco_lines(x, y):                        # PADRAO: classic double rule
    return {1: 3, 3: 1, 12: 1, 14: 3}.get(y)


def deco_grid(x, y):                         # SYNTHWAVE: horizon + grid
    if y in (7,):
        return 3
    if y > 7 and (y in (10, 14) or (x % 8 == 0)):
        return 1
    if y < 7 and (x % 16) in (6, 7, 8, 9) and y > 2:
        return 1
    return None


def deco_sunset(x, y):                       # OUTRUN: sunset bands
    return (3, 3, 2, 3, 2, 2, 1, 2, 1, 1, 0, 1, 0, 0, 1, 0)[y] or None


def deco_scan(x, y):                         # 16-BIT: chequered scanlines
    if y % 4 == 3:
        return 1
    return 3 if ((x // 4) + (y // 4)) % 2 == 0 else None


def deco_stars(x, y):                        # RETROCHIMP: twinkling stars
    sx, sy = x % 16, y % 8
    if (sx, sy) in ((4, 3), (12, 6)):
        return 3
    if (sx, sy) in ((3, 3), (5, 3), (4, 2), (4, 4)):
        return 1
    return 1 if y == 15 else None


def deco_hazard(x, y):                       # MAD DRUGA: hazard stripes
    if y in (0, 15):
        return 1
    return 3 if ((x + y) // 4) % 2 == 0 else 1


def deco_circuit(x, y):                      # CYBERPUNK: circuit traces
    if y == 4 or y == 11:
        return 1
    if x % 16 == 5 and 4 <= y <= 11:
        return 3
    if (x % 16, y) in ((4, 3), (5, 3), (6, 3), (4, 12), (5, 12), (6, 12)):
        return 3
    return None


def deco_dots(x, y):                         # GAME BOY: dot-matrix screen
    if y in (0, 15):
        return 3
    return 1 if (x % 4 == 1 and y % 4 == 2) else None


DECOS = [deco_flames, deco_lines, deco_grid, deco_sunset, deco_scan,
         deco_stars, deco_hazard, deco_circuit, deco_dots]


def draw(theme_id):
    _, _, title, _ = THEMES[theme_id]
    px = _canvas()
    tx = _title_x(title)
    _fill(px, 0, tx - 8, DECOS[theme_id])
    _fill(px, tx + len(title) * 8 + 8, W, DECOS[theme_id])
    _title(px, title, tx)
    return px


def _tile(px, cx, cy):
    lo = bytearray(8)
    hi = bytearray(8)
    for r in range(8):
        for c in range(8):
            v = px[cy * 8 + r][cx * 8 + c]
            lo[r] |= (v & 1) << (7 - c)
            hi[r] |= ((v >> 1) & 1) << (7 - c)
    return bytes(lo + hi)


def package(theme_id):
    px = draw(theme_id)
    blank = bytes(16)
    slots, tiles, nt = {}, [], bytearray(96)
    free = iter(FREE_SLOTS)
    for cy in range(2):
        for cx in range(32):
            t = _tile(px, cx, cy)
            if t == blank:
                nt[cy * 32 + cx] = BLANK_SLOT
                continue
            if t not in slots:
                slots[t] = next(free)
                tiles.append((slots[t], t))
            nt[cy * 32 + cx] = slots[t]
    nt[64:96] = bytes([BLANK_SLOT] * 32)
    tiles.append((BLANK_SLOT, blank))
    assert len(tiles) - 1 <= MAX_TILES, f"theme {theme_id}: {len(tiles) - 1} tiles > {MAX_TILES}"
    _, name, _, pal0 = THEMES[theme_id]
    return {"name": name, "tiles": tiles, "nametable": bytes(nt), "pal0": pal0, "pixels": px}


def build_banner_packages():
    check_contrast()
    return [package(t[0]) for t in THEMES]


def preview(pkg, scale=3):
    """Banner rendered with the NES palette (PIL image)."""
    from PIL import Image
    from nes_art import NES_RGB
    bd, txt, hl, sh = pkg["pal0"]
    cols = [NES_RGB[bd], NES_RGB[sh], NES_RGB[txt], NES_RGB[hl]]
    img = Image.new("RGB", (W, H))
    for y in range(H):
        for x in range(W):
            img.putpixel((x, y), cols[pkg["pixels"][y][x]])
    return img.resize((W * scale, H * scale), Image.NEAREST)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from PIL import Image
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "themes", "banners")
    os.makedirs(out, exist_ok=True)
    pk = build_banner_packages()
    sheet = Image.new("RGB", (W * 3, H * 3 * len(pk) + 4 * (len(pk) - 1)), (40, 40, 40))
    for i, p in enumerate(pk):
        im = preview(p)
        im.save(os.path.join(out, f"banner{i}.png"))
        sheet.paste(im, (0, i * (H * 3 + 4)))
        print(f"  {i} {p['name']:15s} {len(p['tiles']) - 1} tiles")
    sheet.save(os.path.join(out, "all_banners.png"))
