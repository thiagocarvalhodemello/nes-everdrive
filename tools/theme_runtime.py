"""
Theme runtime injected into OS.BIN (bank 15, CPU $FAE4..$FBFD) plus the hooks
that call into it.

Why this layout (fix for SD card corruption when switching themes)
-------------------------------------------------------------------
The previous runtime applied the theme *inside the NMI handler*. On the
EverDrive N8 the mapper is an index/data pair ($4400 = register index,
$4401 = data), and the OS uses that same pair for everything: $6000 bank
select (reg $81), save-RAM banks, SD/FPGA control registers, etc. The NMI
handler wrote $4400=$81 and forced bank $08 back at $6000 without restoring
anything. If the NMI landed between an OS `STA $4400` / `STA $4401` pair, or
while the OS had a ROM/SAV bank mapped at $6000 to stream sectors, data went
to the wrong register or bank and the FAT got trashed.

It also kept its state inside the OS heap: the OS bump allocator ($0450)
sits at $7BA5 after boot and hands out 12/200/256/512-byte buffers from there
at runtime (the 512-byte one is a sector buffer). The old SRAM signature at
$7BA6..$7BA9 and banner copy at $7C00..$7C5F lived inside those buffers.

New rules:
  * The NMI is the OS's original one (v1.4 hooked it; restored in v1.5).
  * SELECT in the file browser is the theme key: the OS's own SELECT branch
    calls the far entry FAR_SEL, which applies the next theme in the browser's main-thread
    context and asks the browser for a full redraw. START opens the main menu.
  * The theme saved for boot is applied from the OS's "wait for button" idle
    loops (hook 4, $ABBD), where bank 8 is mapped and nothing is in flight.
  * Persistent signature lives at bank 8 $7FF8..$7FFB, above the highest
    address the OS heap can reach ($7BA5 + 988 bytes of runtime allocations
    = $7F81).
  * The banner is read straight from bank $0B on each screen clear (hook 3);
    no copy is kept in OS work RAM.
"""

# ---------------------------------------------------------------------------
# Minimal 6502 assembler (two-pass, label expressions allowed in operands)
# ---------------------------------------------------------------------------
_OPS = {
    # mnemonic: {mode: opcode}
    "ADC": {"imm": 0x69, "abs": 0x6D}, "AND": {"imm": 0x29, "abs": 0x2D},
    "SBC": {"imm": 0xE9, "abs": 0xED},
    "ASL": {"imp": 0x0A},
    "BCC": {"rel": 0x90}, "BCS": {"rel": 0xB0}, "BEQ": {"rel": 0xF0},
    "BMI": {"rel": 0x30}, "BNE": {"rel": 0xD0}, "BPL": {"rel": 0x10},
    "BIT": {"abs": 0x2C}, "CLC": {"imp": 0x18}, "SEC": {"imp": 0x38},
    "CMP": {"imm": 0xC9, "abs": 0xCD, "abx": 0xDD, "aby": 0xD9},
    "CPX": {"imm": 0xE0, "abs": 0xEC}, "CPY": {"imm": 0xC0, "abs": 0xCC},
    "DEC": {"abs": 0xCE}, "DEX": {"imp": 0xCA}, "DEY": {"imp": 0x88},
    "EOR": {"imm": 0x49, "zp": 0x45, "abs": 0x4D},
    "INC": {"abs": 0xEE}, "INX": {"imp": 0xE8}, "INY": {"imp": 0xC8},
    "JMP": {"abs": 0x4C}, "JSR": {"abs": 0x20},
    "LDA": {"imm": 0xA9, "zp": 0xA5, "abs": 0xAD, "abx": 0xBD, "aby": 0xB9, "indy": 0xB1},
    "LDX": {"imm": 0xA2, "abs": 0xAE}, "LDY": {"imm": 0xA0, "abs": 0xAC},
    "LSR": {"imp": 0x4A, "zp": 0x46},
    "ORA": {"imm": 0x09, "abs": 0x0D},
    "PHA": {"imp": 0x48}, "PLA": {"imp": 0x68},
    "ROR": {"zp": 0x66},
    "RTI": {"imp": 0x40}, "RTS": {"imp": 0x60},
    "STA": {"zp": 0x85, "abs": 0x8D, "abx": 0x9D, "aby": 0x99, "indy": 0x91},
    "STX": {"abs": 0x8E},
    "TAX": {"imp": 0xAA}, "TAY": {"imp": 0xA8}, "TXA": {"imp": 0x8A}, "TYA": {"imp": 0x98},
}
_SIZE = {"imp": 1, "imm": 2, "zp": 2, "rel": 2, "indy": 2, "abs": 3, "abx": 3, "aby": 3}


def assemble(listing, base, symbols=None):
    """listing: [(label|None, mnemonic, mode, operand)] -> (bytes, labels).
    operand may be int or a python expression string using labels/symbols."""
    labels = {}
    pc = base
    for lbl, mn, mode, _ in listing:
        if lbl:
            assert lbl not in labels, f"duplicate label {lbl}"
            labels[lbl] = pc
        pc += _SIZE[mode]

    env = dict(symbols or {})
    env.update(labels)

    def val(x):
        return eval(x, {}, env) if isinstance(x, str) else x

    out = bytearray()
    pc = base
    for lbl, mn, mode, arg in listing:
        env["_pc"] = pc
        out.append(_OPS[mn][mode])
        if mode == "rel":
            rel = val(arg) - (pc + 2)
            assert -128 <= rel <= 127, f"branch out of range to {arg}"
            out.append(rel & 0xFF)
        elif mode in ("imm", "zp", "indy"):
            v = val(arg)
            assert 0 <= v <= 0xFF, f"byte operand out of range: {arg}"
            out.append(v)
        elif mode in ("abs", "abx", "aby"):
            v = val(arg)
            out += bytes((v & 0xFF, (v >> 8) & 0xFF))
        pc += _SIZE[mode]
    return bytes(out), labels


# ---------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------
NUM_THEMES = 9

REGION_START = 0xFAE4          # bank 15 RAM, all-zero plaintext in the original OS
REGION_LEN = 282               # $FAE4..$FBFD (same window the previous build used)
FILE_REGION = 0xDAE4           # file offset of REGION_START in OS.BIN

FAR_ID = 0xFAE4                # entry number for the bank $0B dispatcher (see FAR)
THEME_ID = 0xFAE5              # theme currently on screen
WANT_ID = 0xFAE6               # theme requested by BOOT; applied from the idle loop
FORCE = 0x80                   # WANT_ID bit 7: apply even if equal (boot palette/CHR)
CODE_START = 0xFAE7

SIG = 0x7FF8                   # bank 8: $ED $FC id ~id (above OS heap ceiling $7F81)

# OS entry points / RAM (from the decrypted v1.26-based OS)
OS_WAIT_VBL = 0x83B0           # BIT $2002 / BPL loop
OS_REFRESH_NT = 0x8343         # uploads nametable shadow $6000-$63FF to PPU
OS_DECSP2 = 0xEF47             # first instruction of $ABBD (USB poll in idle loops)
OS_MAIN_MENU = 0xCB50          # "Menu Principal" (Y=0)
OS_BROWSER_LOOP = 0xD89E       # file browser main loop (checks the redraw flags)
OS_REDRAW = 0x04D4             # browser: clear + redraw the whole screen when nonzero
B11_PTRS = 0x6000              # bank $0B: per-theme package pointer table
NT_BYTES = 64                  # banner nametable rows 0-1 (row 2 = black spacer, generated)
BLACK_TILE = 0x1F

# bank $0B layout (shared with test_full_banner_system / art_runtime)
B11_DATA2 = 0x6E10             # some favourites strings (art_runtime.DATA2); theme data must end before
B11_PAL_TABLE = 0x6E60         # 9 x 16 palette bytes (banner_art.palette16)
B11_LOADER = 0x6F00            # palette + CHR tile loader (<= 0xC0 bytes)
B11_VARS = 0x6FC0              # favourites variables (16 bytes)
B11_CACHE = 0x6FD0             # favourites name cache: 32 x 32 bytes
B11_DISPATCH = 0x73D0          # far code: dispatcher, covers, theme key, favourites (art_runtime)
FAR_INFO, FAR_MENU, FAR_MAIN, FAR_SEL, FAR_FAVADD = range(5)

# Main menu: the OS table at $03C9 (title + 5 items) is full, so the menu points to a
# new table in our region with a 6th item, "Favoritos" (result 5).
MAIN_MENU_STRS = [0xF693, 0xF6A2, 0xF6A9, 0xF6B2, 0xF6BF, 0xF6CC]   # title, 5 OS items

# Sites patched in the OS. Value: keystream (orig_enc ^ orig_plain) for the
# bytes written; banks 13/14 are stored in plaintext (keystream 0).
HOOK_BOOT = 0x828C             # orig: JSR $83B0               -> JSR BOOT
HOOK_BANNER = 0x83F9           # orig: LDA #$60 / STA $93 / RTS -> JMP BANNER / NOP / NOP
HOOK_IDLE = 0xABBD             # orig: JSR $EF47               -> JSR IDLE
HOOK_ART = 0xCFB2              # orig: JSR $9F6C (ROM info wait) -> JSR ART_HOOK
HOOK_ART_MENU = 0xD582         # orig: JSR $CA0D (ROM file menu) -> JSR ART_MENU_HOOK
SITE_NMI = 0x8103              # v1.4 hooked the NMI here; restored to the original
SITE_START = 0xDBE7            # browser START: was "restart last game" -> main menu
SITE_SELECT = 0xDBFC           # browser SELECT: was main menu -> next theme
SITE_MENU_COUNT = 0xD579       # ROM file menu: 3 items -> 2
SITE_MENU_ITEM1 = 0xD5BA       # "CMP #$01" (item 1 = "Apenas Selec.") -> never; item 1 = ROM info
SITE_ITEMS = 0xFA9F            # DATA image of the ROM menu item table, item 1 pointer
SITE_LOAD_STR = 0xF66A         # "Sel. e Iniciar" -> "Carregar jogo"
SITE_FAV_STR = 0xF679          # "Apenas Selec." (unused since v1.5) -> "Favoritar"
SITE_ITEMS2 = 0xFAA1           # DATA image: ROM menu item 2 pointer -> "Favoritar"
SITE_FAVADD = 0xD5BD           # ROM menu result 2 (was the "Apenas Selec." code) -> add favourite
SITE_MAIN_TABLE = 0xCB56       # main menu: operands of LDA #<table / LDX #>table
SITE_MAIN_COUNT = 0xCB5D       # main menu: 5 items -> 6
SITE_MAIN_DISP = 0xCBAF        # main menu: LDY #0 / LDA (sp),Y / BNE $CB55 -> JSR H_MAIN
# browser status bar (selected name): was attribute row 6 = $FF (screen rows 24-27, palette 3) with
# the name on list rows $17/$18 (screen rows 25/26); now only the top half of attribute row 7
# (screen rows 28-29, the bottom of the screen) and the name on rows 28/29
SITE_BAR_ATTR_ROW = 0xC81F     # LDA #$F0 (offset of attribute row 6 in the shadow) -> #$F8 (row 7)
SITE_BAR_ATTR_VAL = 0xC833     # LDA #$FF (4 quadrants palette 3) -> #$0F (top quadrants only)
SITE_BAR_ROWS = (0xC8BF, 0xC8C7, 0xC8DF, 0xC941)   # clear row $17, clear $18, print $17, print $18
SITE_BAR_PPU = 0x8442          # cursor-move partial upload: LDA #$20 (PPU $2320 = row 25) -> #$80 (row 28)
SITE_BAR_SRC = 0x8449          # ... LDA $6260,Y (Y=$C0: shadow $6320) -> $62C0,Y (shadow $6380)
# game menu: LEFT/RIGHT = previous/next game. $CA0D's "no confirm/cancel" exit (JMP $CA40 at $CB34)
# goes to a check in the dead "Apenas Selec." code: only for the game menu table ($03C1, the only
# table with low byte $C1) it returns $FE (left) / $FD (right); art_runtime.ART_MENU handles them
SITE_MENU_LR = 0xCB34          # JMP $CA40 -> JMP MENU_LR
MENU_LR = 0xD5C5               # 28 unreachable bytes after SITE_FAVADD
GAME_MENU_TABLE = 0x03C1
BAR_LINE = 0x1A                # list row of the first name line (+2 = screen row 28)

# "Sobre" screen ($D1C4): 14 lines, each "LDA #<str / LDX #>str / JSR pushax / JSR println".
# The string block $F7B9-$F899 (bank 15) is rewritten and the 14 pointers repointed.
ABOUT_BLOCK = 0xF7B9
ABOUT_BLOCK_LEN = 225          # up to "NS:" at $F89A, which stays
ABOUT_SITES = [0xD1C7, 0xD1D1, 0xD1DB, 0xD1E5, 0xD1F3, 0xD1FD, 0xD207,
               0xD211, 0xD21F, 0xD229, 0xD233, 0xD23D, 0xD247, 0xD251]
# lines 1-4 use the OS title style, 5-14 the normal one (the OS sets $9F = $7F before line 5).
# Byte 0x01 is the font's "a with acute" slot.
ABOUT_LINES = [
    b"",
    b"Brinquedo de Famicom/NES",
    b"por I. Golubovskiy",
    b"krikzz.com",
    b"Mod por thenobre e",
    b"Antonio Scartezzini do",
    b"grupo RETROGAMER POA",
    b"",
    b"Controles:",
    b"ESQ/DIR - p\x01gina",
    b"START - menu principal",
    b"SELECT - trocar tema",
    b"B - abrir jogo/pasta",
    b"A - voltar",
]

KEYSTREAM = {
    HOOK_BOOT: bytes([0x2F, 0xC7, 0x0A]),
    HOOK_BANNER: bytes([0xB6, 0x4E, 0x17, 0x3E, 0x38]),
    SITE_NMI: bytes([0x9E, 0xFB, 0x89, 0xEF, 0x60]),
    SITE_ITEMS: bytes([0x5E, 0xF0]),
    SITE_LOAD_STR: bytes.fromhex("8bf1897610f9758ee1b2458ea9b0c9"),
    SITE_FAV_STR: bytes.fromhex("63086e1e2864236dfd29730e9995"),
    SITE_ITEMS2: bytes.fromhex("98a3"),
    SITE_BAR_PPU: bytes([0x64]),
    SITE_BAR_SRC: bytes.fromhex("b490"),
    ABOUT_BLOCK: bytes.fromhex(
        "87e9d8967a203ee9b50a512a317f9917c6c0c2f96a53b20156a890b257cccbcfec7698595127b256fa14d9a988"
        "7781e08aee59436c3c2a08812ca743ecfa6838a25a032a2cb4e49200da87e290f67958f66838f67858d1f9f578"
        "3cd878d18730c123f8b187887d30b03461f810da58b177a87ada64b1878859f5793cd178fde8d118fde9d878c9"
        "e82178f93de9e9e8b0a88c9ee9b2a897345df8d100f578f83478f8727477877787778737ccca6c41264885ff87"
        "781ef77b80efbc4b80a7bec76d066010266a2d63f3277d00979b27ffdead4435dd108ba1bf1d9a334532b6be2c"),
}


def about_patches():
    """String block + the 14 pointer operands of the "Sobre" screen."""
    assert len(ABOUT_LINES) == len(ABOUT_SITES)
    assert all(len(l) <= 28 for l in ABOUT_LINES), "About line wider than the screen"
    block, ptrs = bytearray(), []
    for line in ABOUT_LINES:
        ptrs.append(ABOUT_BLOCK + len(block))
        block += line + b"\x00"
    assert len(block) <= ABOUT_BLOCK_LEN, f"About text too long: {len(block)} > {ABOUT_BLOCK_LEN}"
    block += bytes(ABOUT_BLOCK_LEN - len(block))
    out = {ABOUT_BLOCK: bytes(block)}
    for site, ptr in zip(ABOUT_SITES, ptrs):
        out[site + 1] = bytes([ptr & 0xFF])      # LDA #lo
        out[site + 3] = bytes([ptr >> 8])        # LDX #hi
    return out


def _map(bank):
    return [
        (None, "LDA", "imm", 0x81), (None, "STA", "abs", 0x4400),
        (None, "LDA", "imm", bank), (None, "STA", "abs", 0x4401),
    ]


def build_runtime():
    """Returns (payload[REGION_LEN], labels)."""
    L = []

    # --- Hook 3: end of the OS clear-screen routine ($83E2). Main context, bank 8.
    L += [
        ("BANNER", "LDA", "imm", 0x60),
        (None, "STA", "zp", 0x93),                 # instruction replaced by the hook
        # BANNER_BODY: banner rows 0-1 of THEME_ID from bank $0B + black row 2,
        # into the OS nametable shadow ($6000) and its popup backup ($6400).
        ("BANNER_BODY", "LDA", "imm", 0x81),
        (None, "STA", "abs", 0x4400),
        (None, "LDA", "imm", 0x0B),
        (None, "STA", "abs", 0x4401),
        (None, "LDA", "abs", THEME_ID),
        (None, "ASL", "imp", None),
        (None, "TAX", "imp", None),
        (None, "LDA", "abx", B11_PTRS),
        (None, "STA", "abs", "SMC+1"),
        (None, "LDA", "abx", B11_PTRS + 1),
        (None, "STA", "abs", "SMC+2"),
        (None, "LDY", "imm", NT_BYTES - 1),
        ("BLP", "LDA", "imm", 0x0B),
        (None, "STA", "abs", 0x4401),
        ("SMC", "LDA", "aby", 0x0000),             # operand patched above
        (None, "TAX", "imp", None),
        (None, "LDA", "imm", 0x08),
        (None, "STA", "abs", 0x4401),
        (None, "TXA", "imp", None),
        (None, "STA", "aby", 0x6000),
        (None, "STA", "aby", 0x6400),
        (None, "DEY", "imp", None),
        (None, "BPL", "rel", "BLP"),
        (None, "LDA", "imm", BLACK_TILE),          # row 2: spacer between banner and list
        (None, "LDY", "imm", 31),
        ("RLP", "STA", "aby", 0x6000 + NT_BYTES),
        (None, "STA", "aby", 0x6400 + NT_BYTES),
        (None, "DEY", "imp", None),
        (None, "BPL", "rel", "RLP"),
        (None, "LDA", "imm", 0x05),                # attribute row 0: palette 1 for banner
        (None, "LDX", "imm", 0x07),
        ("ALP", "STA", "abx", 0x63C0),
        (None, "DEX", "imp", None),
        (None, "BPL", "rel", "ALP"),
        (None, "LDA", "imm", 0x0A),                # banner corners (x<32, x>=224): palette 2 (icons)
        (None, "STA", "abs", 0x63C0),
        (None, "STA", "abs", 0x63C7),
        (None, "RTS", "imp", None),
    ]

    # --- Hook 2: boot screen init (replaces JSR $83B0). Maps bank 8, reads the
    # signature and requests the theme; the apply happens from the idle loop.
    L += _map(0x08)
    L[-4] = ("BOOT",) + L[-4][1:]
    L += [
        (None, "LDA", "abs", SIG),
        (None, "CMP", "imm", 0xED),
        (None, "BNE", "rel", "BDONE"),
        (None, "LDA", "abs", SIG + 1),
        (None, "CMP", "imm", 0xFC),
        (None, "BNE", "rel", "BDONE"),
        (None, "LDA", "abs", SIG + 2),
        (None, "EOR", "abs", SIG + 3),
        (None, "CMP", "imm", 0xFF),
        (None, "BNE", "rel", "BDONE"),
        (None, "LDA", "abs", SIG + 2),
        (None, "CMP", "imm", NUM_THEMES),
        (None, "BCS", "rel", "BDONE"),
        (None, "ORA", "imm", FORCE),
        (None, "STA", "abs", WANT_ID),
        ("BDONE", "JMP", "abs", OS_WAIT_VBL),
    ]

    # --- APPLY (A = theme id): palette + CHR + banner + signature. Main thread,
    # bank 8 mapped; leaves bank 8 mapped. Clobbers A/X/Y.
    L += [("APPLY", "STA", "abs", THEME_ID),
          (None, "STA", "abs", WANT_ID),
          (None, "JSR", "abs", OS_WAIT_VBL)]
    L += _map(0x0B)
    L += [
        (None, "LDA", "abs", THEME_ID),
        (None, "JSR", "abs", B11_LOADER),          # palette + CHR tiles (rendering off/on)
        (None, "JSR", "abs", "BANNER_BODY"),       # leaves bank 8 mapped
        (None, "LDA", "imm", 0xED),
        (None, "STA", "abs", SIG),
        (None, "LDA", "imm", 0xFC),
        (None, "STA", "abs", SIG + 1),
        (None, "LDA", "abs", THEME_ID),
        (None, "STA", "abs", SIG + 2),
        (None, "EOR", "imm", 0xFF),
        (None, "STA", "abs", SIG + 3),
        (None, "RTS", "imp", None),
    ]

    # --- Hook 4: $ABBD (OS "wait for button" loops): applies the boot request.
    L += [
        ("IDLE", "LDA", "abs", WANT_ID),
        (None, "CMP", "abs", THEME_ID),
        (None, "BNE", "rel", "IGO"),
        (None, "JMP", "abs", OS_DECSP2),
        ("IGO", "AND", "imm", 0x7F),               # drop FORCE bit
        (None, "TAX", "imp", None),
        (None, "TYA", "imp", None),
        (None, "PHA", "imp", None),
        (None, "TXA", "imp", None),
        (None, "JSR", "abs", "APPLY"),
        (None, "JSR", "abs", OS_REFRESH_NT),       # push updated shadow to the PPU
        (None, "PLA", "imp", None),
        (None, "TAY", "imp", None),
        (None, "JMP", "abs", OS_DECSP2),
    ]

    # --- Far calls into bank $0B (art_runtime: covers, theme key, favourites). Each
    # hook site JSRs a 5-byte entry that loads the entry number and jumps to FAR;
    # the bank $0B code returns through its RAM trampoline with bank 8 mapped.
    L += [
        ("H_INFO", "LDA", "imm", FAR_INFO), (None, "JMP", "abs", "FAR"),
        ("H_MENU", "LDA", "imm", FAR_MENU), (None, "JMP", "abs", "FAR"),
        ("H_MAIN", "LDA", "imm", FAR_MAIN), (None, "JMP", "abs", "FAR"),
        ("H_SEL", "LDA", "imm", FAR_SEL), (None, "JMP", "abs", "FAR"),
        ("H_FAVADD", "LDA", "imm", FAR_FAVADD),        # falls into FAR
        ("FAR", "STA", "abs", FAR_ID),
    ]
    L += _map(0x0B)
    L += [(None, "JMP", "abs", B11_DISPATCH)]

    code, labels = assemble(L, CODE_START)
    # main menu table (title + 6 items) and the "Favoritos" item text, after the code
    table_at = CODE_START + len(code)
    fav_str = table_at + 2 * (len(MAIN_MENU_STRS) + 1)
    table = b"".join(bytes([p & 0xFF, p >> 8]) for p in MAIN_MENU_STRS + [fav_str])
    code = code + table + b"Favoritos\x00"
    labels["MAIN_TABLE"], labels["FAV_STR"] = table_at, fav_str
    end = CODE_START + len(code)
    assert end <= REGION_START + REGION_LEN, \
        f"theme runtime too large: ends at ${end:04X}, limit ${REGION_START + REGION_LEN:04X}"

    payload = bytearray(REGION_LEN)   # vars start at 0, unused tail stays 0
    # First idle pass after boot always applies theme 0 (or the saved theme,
    # which BOOT stores with FORCE set) so palette and CHR match the banner.
    payload[WANT_ID - REGION_START] = FORCE | 0
    payload[CODE_START - REGION_START: CODE_START - REGION_START + len(code)] = code
    labels["_END"] = end
    return bytes(payload), labels


def menu_lr_code():
    """LEFT/RIGHT in the game menu -> result $FE/$FD (other menus: unchanged loop)."""
    code, _ = assemble([
        (None, "LDY", "imm", 0x08), (None, "LDA", "indy", 0x28),      # item table (low byte) on the C stack
        (None, "CMP", "imm", GAME_MENU_TABLE & 0xFF), (None, "BNE", "rel", "BACK"),
        (None, "LDA", "abs", 0x0484), (None, "AND", "imm", 0x03), (None, "BEQ", "rel", "BACK"),
        (None, "ORA", "imm", 0xFC),                                   # right $01 -> $FD, left $02 -> $FE
        (None, "JMP", "abs", 0xCB3B),                                 # menu exit with A as the result
        ("BACK", "JMP", "abs", 0xCA40),
    ], MENU_LR, {})
    assert len(code) <= 0xD5E1 - MENU_LR, len(code)
    return code


def os_patches(labels, orig_data):
    """{cpu address: plaintext bytes} for every site changed in the OS."""
    j = lambda op, a: bytes([op, a & 0xFF, a >> 8])
    assert labels["MAIN_TABLE"] & 0xFF != GAME_MENU_TABLE & 0xFF, "main menu table would get LEFT/RIGHT"
    return {
        HOOK_BOOT: j(0x20, labels["BOOT"]),
        HOOK_BANNER: j(0x4C, labels["BANNER"]) + b"\xEA\xEA",
        HOOK_IDLE: j(0x20, labels["IDLE"]),
        HOOK_ART: j(0x20, labels["H_INFO"]),
        HOOK_ART_MENU: j(0x20, labels["H_MENU"]),
        SITE_NMI: bytes.fromhex("ad02206840"),                       # LDA $2002 / PLA / RTI
        SITE_START: bytes([0xA0, 0x00]) + j(0x20, OS_MAIN_MENU) + j(0x4C, OS_BROWSER_LOOP),
        SITE_SELECT: j(0x20, labels["H_SEL"]) + b"\xEA\xEA",       # then JMP $D89E (original)
        SITE_MENU_COUNT: bytes([0x03]),                              # Carregar, Info da ROM, Favoritar
        SITE_MENU_ITEM1: bytes([0x02]),                              # result 2 -> $D5BD; 1 -> ROM info
        SITE_ITEMS: bytes([0x87, 0xF6]),                             # item 1 -> "Info da ROM"
        SITE_ITEMS2: bytes([SITE_FAV_STR & 0xFF, SITE_FAV_STR >> 8]),  # item 2 -> "Favoritar"
        SITE_LOAD_STR: b"Carregar jogo\x00\x00",                     # 15 bytes, same slot
        SITE_FAV_STR: b"Favoritar\x00\x00\x00\x00\x00",              # 14 bytes, same slot
        # result 2: add favourite, then return 0 (stay in the browser) like the other items
        SITE_FAVADD: j(0x20, labels["H_FAVADD"]) + bytes([0xA9, 0x00]) + j(0x4C, 0xD5E5),
        SITE_MAIN_TABLE: bytes([labels["MAIN_TABLE"] & 0xFF, 0xA2, labels["MAIN_TABLE"] >> 8]),
        SITE_MAIN_COUNT: bytes([0x06]),
        SITE_MAIN_DISP: j(0x20, labels["H_MAIN"]) + b"\xEA\xEA\xEA",
        SITE_MENU_LR: j(0x4C, MENU_LR),
        MENU_LR: menu_lr_code(),
        SITE_BAR_ATTR_ROW: bytes([0xF8]),
        SITE_BAR_ATTR_VAL: bytes([0x0F]),
        SITE_BAR_PPU: bytes([0x80]),
        SITE_BAR_SRC: bytes([0xC0, 0x62]),
        **{a: bytes([BAR_LINE + (i & 1)]) for i, a in enumerate(SITE_BAR_ROWS)},
        **about_patches(),
    }


def patch_runtime(data, orig_data):
    """Patch bank-15 runtime + OS sites into an OS.BIN bytearray (in place).
    orig_data: EDFC-ORIGINAL/OS.BIN (its bytes in the region are the keystream,
    since the original plaintext there is all zeros)."""
    payload, labels = build_runtime()
    key = orig_data[FILE_REGION: FILE_REGION + REGION_LEN]
    data[FILE_REGION: FILE_REGION + REGION_LEN] = bytes(p ^ k for p, k in zip(payload, key))
    for cpu, plain in os_patches(labels, orig_data).items():
        ks = KEYSTREAM.get(cpu, bytes(len(plain)))
        assert len(ks) == len(plain), hex(cpu)
        off = cpu - 0x2000
        data[off: off + len(plain)] = bytes(p ^ k for p, k in zip(plain, ks))
    return labels


if __name__ == "__main__":
    payload, labels = build_runtime()
    for k in ("BANNER", "BANNER_BODY", "BOOT", "APPLY", "IDLE", "H_INFO", "FAR", "MAIN_TABLE", "_END"):
        print(f"  {k:14s} ${labels[k]:04X}")
    print(f"  used {labels['_END'] - REGION_START} / {REGION_LEN} bytes")
