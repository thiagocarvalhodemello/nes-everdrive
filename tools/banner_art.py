"""
Themes: colours (one explicit 16-colour PPU palette per theme) and banners
(256x16 px, screen rows 0-1) generated from code.

Palette roles (what the OS draws with each entry):
  0  bd        universal backdrop (banner background, empty cells)
  1  file      file names in the list (palette 0, normal font)
  2  bg        LIST BACKGROUND (palette 0 colour 2 fills the list area)
  3  folder    folders, cursor and the selected entry (highlighted font)
  5-7          banner colours: dark, mid, bright (attribute palette 1)
  9-11         banner corner icons (attribute palette 2, x < 32 and x >= 224)
  13 popup_txt popups and status bar text (palette 3)
  14 popup_bg  popups and status bar background
  15 popup_hl  highlighted popup item
check_contrast() enforces readable pairs (CIE L*). v1.5 derived everything from
4 colours and put the theme highlight in the list background: PADRAO/SYNTHWAVE/
CYBERPUNK/RETROCHIMP ended up with text 4-8 L* from it (unreadable on a TV).

build_banner_packages() returns, per theme:
  {'name', 'tiles': [(slot, 16 bytes)], 'nametable': 96 bytes, 'palette': 16 bytes, 'pixels'}
"""
import os


def T(bd, file, bg, folder, banner, popup, icon=None):
    """banner = (dark, mid, bright); popup = (text, background, highlight); icon = 3 colours."""
    return dict(bd=bd, file=file, bg=bg, folder=folder, banner=banner, popup=popup, icon=icon or banner)


# id, name, banner title, colours
THEMES = [
    (0, "RETROGAMER POA", "RETROGAMER POA", T(0x0F, 0x17, 0x38, 0x16, (0x16, 0x17, 0x38), (0x30, 0x16, 0x38))),
    (1, "PADRAO",         "EVERDRIVE N8",   T(0x0F, 0x00, 0x30, 0x02, (0x02, 0x00, 0x30), (0x30, 0x02, 0x30))),
    (2, "SYNTHWAVE",      "SYNTHWAVE",      T(0x0F, 0x14, 0x3C, 0x12, (0x12, 0x14, 0x3C), (0x30, 0x12, 0x3C))),
    (3, "OUTRUN",         "OUTRUN",         T(0x04, 0x17, 0x37, 0x16, (0x16, 0x17, 0x37), (0x30, 0x16, 0x37))),
    (4, "16-BIT",         "16-BIT",         T(0x02, 0x01, 0x30, 0x11, (0x11, 0x01, 0x30), (0x30, 0x11, 0x30))),
    # Retrochimp Games: navy, cream/orange title, the chimp in the corners
    (5, "RETROCHIMP",     "RETROCHIMP",     T(0x0F, 0x3D, 0x01, 0x27, (0x17, 0x27, 0x37), (0x37, 0x1C, 0x30),
                                              icon=(0x07, 0x27, 0x30))),
    # Maddrugamers (youtube.com/@maddrugamers): black, chunky green title, arcade joysticks
    (6, "MADDRUGAMERS",   "MADDRUGAMERS",   T(0x0F, 0x2A, 0x0F, 0x39, (0x09, 0x1A, 0x2A), (0x0F, 0x1A, 0x30),
                                              icon=(0x00, 0x10, 0x16))),
    (7, "CYBERPUNK",      "CYBERPUNK",      T(0x02, 0x0C, 0x34, 0x12, (0x12, 0x0C, 0x34), (0x30, 0x12, 0x34))),
    (8, "GAME BOY",       "GAME BOY",       T(0x08, 0x19, 0x38, 0x0A, (0x0A, 0x19, 0x38), (0x30, 0x0A, 0x38))),
]
MIN_CONTRAST = 40          # L*: list text / folders vs list background, popup text vs popup background
MIN_HL_CONTRAST = 20       # L*: highlighted popup item vs popup background


def palette16(c):
    """The 16 bytes the theme loader copies to the OS palette ($827C) and the PPU."""
    return bytes([c["bd"], c["file"], c["bg"], c["folder"],
                  0x0F, *c["banner"],
                  0x0F, *c["icon"],
                  0x0F, *c["popup"]])


def _lstar(c):
    from nes_art import NES_RGB
    r, g, b = [x / 255 for x in NES_RGB[c]]
    f = lambda v: ((v + 0.055) / 1.055) ** 2.4 if v > 0.04045 else v / 12.92
    y = 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
    return 116 * (y ** (1 / 3) if y > 0.008856 else 7.787 * y + 16 / 116) - 16


def check_contrast():
    bad = []
    d = lambda a, b: abs(_lstar(a) - _lstar(b))
    for tid, name, _, c in THEMES:
        txt, bg, hl = c["popup"]
        if d(c["file"], c["bg"]) < MIN_CONTRAST:
            bad.append(f"{name}: file names vs list background")
        if d(c["folder"], c["bg"]) < MIN_CONTRAST:
            bad.append(f"{name}: folders/selection vs list background")
        if d(txt, bg) < MIN_CONTRAST:
            bad.append(f"{name}: popup text vs popup background")
        if d(hl, bg) < MIN_HL_CONTRAST:
            bad.append(f"{name}: popup highlight vs popup background")
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


def _title(px, text, x0, style="plain"):
    """Draw text in 8-px cells starting at x0: bold 6x14 glyphs.
    plain: bright (3) with a 1 px dark shadow (1)
    chunky: bright top / mid bottom (3/2) with a 2 px dark 3D shadow (1)   (Maddrugamers)
    duo: bright top / mid bottom (3/2) with a 1 px dark shadow (1)          (Retrochimp)"""
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
        depth = (1, 2) if style == "chunky" else (1,)
        for d in depth:                                   # shadow first
            for (x, y) in body:
                if (x + d, y + d) not in body and x + d < W and y + d < H:
                    px[y + d][x + d] = 1
        for (x, y) in body:
            px[y][x] = 3 if style == "plain" or y < 8 else 2


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


def deco_chimp_stripes(x, y):               # RETROCHIMP: orange/cream racing stripes
    return {3: 3, 4: 2, 6: 1, 9: 1, 11: 2, 12: 3}.get(y)


def deco_maddruga(x, y):                     # MADDRUGAMERS: faint scanlines + a few pixels of "stars"
    if y % 3 == 2:
        return 1
    return 2 if (x * 7 + y * 13) % 97 == 0 else None


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
         deco_chimp_stripes, deco_maddruga, deco_circuit, deco_dots]
STYLES = {5: "duo", 6: "chunky"}


# ---- corner icons (x < 32 and x >= 224 use attribute palette 2: colours 1-3 = theme "icon")
def icon_joystick(px, x0):
    """arcade joystick: light grey base (2), dark stick/ball (1), red button (3)"""
    for y in range(10, 15):
        for x in range(x0 + 2, x0 + 26):
            px[y][x] = 2 if y < 14 else 1
    for x in range(x0 + 4, x0 + 9):                       # red button
        px[11][x] = 3
        px[12][x] = 3
    sx = x0 + 17
    for y in range(4, 10):                                # stick
        px[y][sx] = 1
        px[y][sx + 1] = 1
    for y in range(0, 5):                                 # ball
        for x in range(sx - 2, sx + 4):
            if (x - sx - 0.5) ** 2 + (y - 2) ** 2 <= 6.5:
                px[y][x] = 1
    px[1][sx - 1] = 2                                     # shine


def icon_chimp(px, x0):
    """chimp face: brown fur (1), orange face (2), white cap and eyes (3)"""
    art = [
        "....33333333....",
        "...3333333333...",
        "..333333333333..",
        "..111111111111..",
        ".11122222222111.",
        "1112222222222111",
        "1122333223332211",
        "1122313223132211",
        "1122333223332211",
        ".11222222222211.",
        "..122222222221..",
        "..122211112221..",
        "..122222222221..",
        "...1222222221...",
        "....11111111....",
        "................",
    ]
    for y, row in enumerate(art):
        for x, ch in enumerate(row):
            if ch != ".":
                px[y][x0 + x] = int(ch)


ICONS = {5: icon_chimp, 6: icon_joystick}


def draw(theme_id):
    _, _, title, _ = THEMES[theme_id]
    px = _canvas()
    tx = _title_x(title)
    left, right = (0, W) if theme_id not in ICONS else (32, W - 32)
    _fill(px, left, tx - 8, DECOS[theme_id])
    _fill(px, tx + len(title) * 8 + 8, right, DECOS[theme_id])
    _title(px, title, tx, STYLES.get(theme_id, "plain"))
    if theme_id in ICONS:
        ICONS[theme_id](px, 4 if theme_id == 6 else 8)
        ICONS[theme_id](px, W - 32 + (2 if theme_id == 6 else 8))
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
    _, name, _, colours = THEMES[theme_id]
    pal = palette16(colours)
    return {"name": name, "tiles": tiles, "nametable": bytes(nt), "palette": pal, "pal0": tuple(pal[:4]),
            "pixels": px}


def build_banner_packages():
    check_contrast()
    return [package(t[0]) for t in THEMES]


def preview(pkg, scale=3):
    """Banner rendered with the NES palette (PIL image)."""
    from PIL import Image
    from nes_art import NES_RGB
    pal = pkg["palette"]
    img = Image.new("RGB", (W, H))
    for y in range(H):
        for x in range(W):
            v = pkg["pixels"][y][x]
            base = 8 if (x < 32 or x >= W - 32) else 4          # corners: attribute palette 2
            img.putpixel((x, y), NES_RGB[pal[0] if v == 0 else pal[base + v]])
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
