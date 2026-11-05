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
    calls SELNEXT, which applies the next theme in the browser's main-thread
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
    "ADC": {"imm": 0x69, "abs": 0x6D}, "AND": {"imm": 0x29},
    "ASL": {"imp": 0x0A},
    "BCC": {"rel": 0x90}, "BCS": {"rel": 0xB0}, "BEQ": {"rel": 0xF0},
    "BMI": {"rel": 0x30}, "BNE": {"rel": 0xD0}, "BPL": {"rel": 0x10},
    "BIT": {"abs": 0x2C}, "CLC": {"imp": 0x18}, "SEC": {"imp": 0x38},
    "CMP": {"imm": 0xC9, "abs": 0xCD}, "CPX": {"imm": 0xE0}, "CPY": {"imm": 0xC0},
    "DEC": {"abs": 0xCE}, "DEX": {"imp": 0xCA}, "DEY": {"imp": 0x88},
    "EOR": {"imm": 0x49, "zp": 0x45, "abs": 0x4D},
    "INC": {"abs": 0xEE}, "INX": {"imp": 0xE8}, "INY": {"imp": 0xC8},
    "JMP": {"abs": 0x4C}, "JSR": {"abs": 0x20},
    "LDA": {"imm": 0xA9, "zp": 0xA5, "abs": 0xAD, "abx": 0xBD, "aby": 0xB9, "indy": 0xB1},
    "LDX": {"imm": 0xA2, "abs": 0xAE}, "LDY": {"imm": 0xA0},
    "LSR": {"imp": 0x4A, "zp": 0x46},
    "ORA": {"imm": 0x09, "abs": 0x0D},
    "PHA": {"imp": 0x48}, "PLA": {"imp": 0x68},
    "ROR": {"zp": 0x66},
    "RTI": {"imp": 0x40}, "RTS": {"imp": 0x60},
    "STA": {"zp": 0x85, "abs": 0x8D, "abx": 0x9D, "aby": 0x99},
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
B11_PAL_TABLE = 0x79A0         # 9 x 16 palette bytes (banner_art.palette16)
B11_LOADER = 0x7A70            # palette + CHR tile loader (<= 208 bytes)
ART_ENTRY_INFO = 0x7B40        # art_runtime: ROM info entry
ART_ENTRY_MENU = 0x7B6C        # art_runtime: game menu entry (asserted by art_runtime)

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

    # --- Browser SELECT (replaces LDY #0 / JSR $CB50 at $DBFC; the OS then
    # jumps to its browser loop): next theme, applied right here in the
    # browser's own context, and a full redraw of the screen.
    L += [
        ("SELNEXT", "LDX", "abs", THEME_ID),
        (None, "INX", "imp", None),
        (None, "CPX", "imm", NUM_THEMES),
        (None, "BCC", "rel", "SN"),
        (None, "LDX", "imm", 0),
        ("SN", "TXA", "imp", None),
        (None, "JSR", "abs", "APPLY"),
        (None, "LDA", "imm", 1),
        (None, "STA", "abs", OS_REDRAW),
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

    # --- Hooks 5/6: art runtime entries in bank $0B (art_runtime.py); they
    # return through their RAM trampoline with bank 8 mapped again.
    L += _map(0x0B)
    L[-4] = ("ART_HOOK",) + L[-4][1:]
    L += [(None, "JMP", "abs", ART_ENTRY_INFO)]
    L += _map(0x0B)
    L[-4] = ("ART_MENU_HOOK",) + L[-4][1:]
    L += [(None, "JMP", "abs", ART_ENTRY_MENU)]

    code, labels = assemble(L, CODE_START)
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


def os_patches(labels, orig_data):
    """{cpu address: plaintext bytes} for every site changed in the OS."""
    j = lambda op, a: bytes([op, a & 0xFF, a >> 8])
    return {
        HOOK_BOOT: j(0x20, labels["BOOT"]),
        HOOK_BANNER: j(0x4C, labels["BANNER"]) + b"\xEA\xEA",
        HOOK_IDLE: j(0x20, labels["IDLE"]),
        HOOK_ART: j(0x20, labels["ART_HOOK"]),
        HOOK_ART_MENU: j(0x20, labels["ART_MENU_HOOK"]),
        SITE_NMI: bytes.fromhex("ad02206840"),                       # LDA $2002 / PLA / RTI
        SITE_START: bytes([0xA0, 0x00]) + j(0x20, OS_MAIN_MENU) + j(0x4C, OS_BROWSER_LOOP),
        SITE_SELECT: j(0x20, labels["SELNEXT"]) + b"\xEA\xEA",     # then JMP $D89E (original)
        SITE_MENU_COUNT: bytes([0x02]),
        SITE_MENU_ITEM1: bytes([0xFE]),
        SITE_ITEMS: bytes([0x87, 0xF6]),                             # -> "Info da ROM"
        SITE_LOAD_STR: b"Carregar jogo\x00\x00",                     # 15 bytes, same slot
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
    for k in ("BANNER", "BANNER_BODY", "BOOT", "APPLY", "SELNEXT", "IDLE", "ART_HOOK", "ART_MENU_HOOK", "_END"):
        print(f"  {k:14s} ${labels[k]:04X}")
    print(f"  used {labels['_END'] - REGION_START} / {REGION_LEN} bytes")
