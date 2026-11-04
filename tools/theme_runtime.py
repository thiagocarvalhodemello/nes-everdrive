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
  * NMI (hook 1) only reads the joypad byte the OS already stored, and only
    writes bank-15 RAM variables + $0484. It never touches $4400/$4401,
    the PPU (except the original $2002 read), or $6000-$7FFF.
  * The theme is applied from the OS's "wait for button" idle loops
    (hook 4, $ABBD), i.e. main-thread UI context, where bank 8 is mapped and
    no register sequence or sector buffer is in flight.
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
    "ADC": {"imm": 0x69}, "AND": {"imm": 0x29},
    "ASL": {"imp": 0x0A},
    "BCC": {"rel": 0x90}, "BCS": {"rel": 0xB0}, "BEQ": {"rel": 0xF0},
    "BMI": {"rel": 0x30}, "BNE": {"rel": 0xD0}, "BPL": {"rel": 0x10},
    "BIT": {"abs": 0x2C},
    "CMP": {"imm": 0xC9, "abs": 0xCD}, "CPY": {"imm": 0xC0},
    "DEC": {"abs": 0xCE}, "DEX": {"imp": 0xCA}, "DEY": {"imp": 0x88},
    "EOR": {"imm": 0x49, "abs": 0x4D},
    "INC": {"abs": 0xEE}, "INX": {"imp": 0xE8}, "INY": {"imp": 0xC8},
    "JMP": {"abs": 0x4C}, "JSR": {"abs": 0x20},
    "LDA": {"imm": 0xA9, "zp": 0xA5, "abs": 0xAD, "abx": 0xBD, "aby": 0xB9},
    "LDX": {"imm": 0xA2, "abs": 0xAE}, "LDY": {"imm": 0xA0},
    "ORA": {"imm": 0x09},
    "PHA": {"imp": 0x48}, "PLA": {"imp": 0x68},
    "RTI": {"imp": 0x40}, "RTS": {"imp": 0x60},
    "STA": {"zp": 0x85, "abs": 0x8D, "abx": 0x9D, "aby": 0x99},
    "TAX": {"imp": 0xAA}, "TAY": {"imp": 0xA8}, "TXA": {"imp": 0x8A}, "TYA": {"imp": 0x98},
}
_SIZE = {"imp": 1, "imm": 2, "zp": 2, "rel": 2, "abs": 3, "abx": 3, "aby": 3}


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
        out.append(_OPS[mn][mode])
        if mode == "rel":
            rel = val(arg) - (pc + 2)
            assert -128 <= rel <= 127, f"branch out of range to {arg}"
            out.append(rel & 0xFF)
        elif mode in ("imm", "zp"):
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

PREV_BTN = 0xFAE4              # last joypad byte seen by the NMI hook
THEME_ID = 0xFAE5              # theme currently on screen
WANT_ID = 0xFAE6               # theme requested (NMI / boot); applied from idle loop
FORCE = 0x80                   # WANT_ID bit 7: apply even if equal (boot palette/CHR)
CODE_START = 0xFAE7

SIG = 0x7FF8                   # bank 8: $ED $FC id ~id (above OS heap ceiling $7F81)

# OS entry points / RAM (from the decrypted v1.26-based OS)
OS_WAIT_VBL = 0x83B0           # BIT $2002 / BPL loop
OS_REFRESH_NT = 0x8343         # uploads nametable shadow $6000-$63FF to PPU
OS_DECSP2 = 0xEF47             # first instruction of $ABBD (USB poll in idle loops)
OS_JOY = 0x0484                # joypad byte written by the NMI handler
OS_VRAM_BUSY = 0xA2            # nonzero while OS streams VRAM in NMI-sensitive loop
B11_LOADER = 0x7F00            # bank $0B: palette + CHR tile loader
B11_PTRS = 0x6000              # bank $0B: per-theme package pointer table

BTN_NEXT = 0x21                # SELECT + RIGHT
BTN_PREV = 0x22                # SELECT + LEFT

# Hook sites. key = CPU address in bank 12/13 (file offset = cpu - 0x2000),
# value = (original plaintext, keystream) — keystream = orig_enc ^ orig_plain.
HOOK_NMI = 0x8103              # orig: LDA $2002 / PLA / RTI   -> JMP LIVE / NOP / NOP
HOOK_BOOT = 0x828C             # orig: JSR $83B0               -> JSR BOOT
HOOK_BANNER = 0x83F9           # orig: LDA #$60 / STA $93 / RTS -> JMP BANNER / NOP / NOP
HOOK_IDLE = 0xABBD             # orig: JSR $EF47               -> JSR IDLE
HOOK_KEYSTREAM = {
    HOOK_NMI: bytes([0x9E, 0xFB, 0x89, 0xEF, 0x60]),
    HOOK_BOOT: bytes([0x2F, 0xC7, 0x0A]),
    HOOK_BANNER: bytes([0xB6, 0x4E, 0x17, 0x3E, 0x38]),
    HOOK_IDLE: bytes([0x00, 0x00, 0x00]),        # bank 13 is stored in plaintext
}


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
        # BANNER_BODY: copy 96-byte banner nametable of THEME_ID from bank $0B
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
        (None, "LDY", "imm", 0x5F),
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
        (None, "LDA", "imm", 0x05),                # attribute row 0: palette 1 for banner
        (None, "LDX", "imm", 0x07),
        ("ALP", "STA", "abx", 0x63C0),
        (None, "DEX", "imp", None),
        (None, "BPL", "rel", "ALP"),
        (None, "RTS", "imp", None),
    ]

    # --- Hook 1: NMI tail. A was pushed by the OS NMI entry; X/Y are NOT saved,
    # so only A is used. No mapper, no PPU (besides the original $2002 read),
    # no $6000-$7FFF access.
    L += [
        ("LIVE", "LDA", "zp", OS_VRAM_BUSY),
        (None, "BNE", "rel", "LEXIT"),
        (None, "LDA", "abs", OS_JOY),
        (None, "CMP", "abs", PREV_BTN),
        (None, "STA", "abs", PREV_BTN),
        (None, "BEQ", "rel", "LHELD"),
        (None, "CMP", "imm", BTN_NEXT),
        (None, "BEQ", "rel", "LNEXT"),
        (None, "CMP", "imm", BTN_PREV),
        (None, "BNE", "rel", "LEXIT"),
        (None, "DEC", "abs", WANT_ID),
        (None, "LDA", "abs", WANT_ID),
        (None, "CMP", "imm", NUM_THEMES),          # also catches $80|id - 1
        (None, "BCC", "rel", "LCONS"),
        (None, "LDA", "imm", NUM_THEMES - 1),
        (None, "BPL", "rel", "LSTORE"),
        ("LNEXT", "INC", "abs", WANT_ID),
        (None, "LDA", "abs", WANT_ID),
        (None, "CMP", "imm", NUM_THEMES),
        (None, "BCC", "rel", "LCONS"),
        (None, "LDA", "imm", 0x00),
        ("LSTORE", "STA", "abs", WANT_ID),
        # swallow the combo (also while held) so the OS doesn't act on SELECT
        ("LCONS", "LDA", "imm", 0x00),
        (None, "STA", "abs", OS_JOY),
        ("LEXIT", "BIT", "abs", 0x2002),           # original: LDA $2002
        (None, "PLA", "imp", None),
        (None, "RTI", "imp", None),
        ("LHELD", "CMP", "imm", BTN_NEXT),
        (None, "BEQ", "rel", "LCONS"),
        (None, "CMP", "imm", BTN_PREV),
        (None, "BEQ", "rel", "LCONS"),
        (None, "BNE", "rel", "LEXIT"),
    ]

    # --- Hook 2: boot screen init (replaces JSR $83B0). The bank mapped at
    # $6000 here is whatever the loader left (observed: $0A); the OS maps bank 8
    # itself a few instructions later, so mapping it now is safe. Only reads
    # the signature and requests the theme — the real apply happens from the
    # idle loop once the OS has finished uploading CHR/palette.
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

    # --- Hook 4: $ABBD, called only from the OS "wait for button" loops.
    # Main thread, bank 8 mapped, no transfer in progress -> safe to bank-switch,
    # touch the PPU and write the signature.
    L += [
        ("IDLE", "LDA", "abs", WANT_ID),
        (None, "CMP", "abs", THEME_ID),
        (None, "BNE", "rel", "IGO"),
        (None, "JMP", "abs", OS_DECSP2),
        ("IGO", "AND", "imm", 0x7F),               # drop FORCE bit
        (None, "STA", "abs", THEME_ID),
        (None, "STA", "abs", WANT_ID),
        (None, "TXA", "imp", None),
        (None, "PHA", "imp", None),
        (None, "TYA", "imp", None),
        (None, "PHA", "imp", None),
        (None, "JSR", "abs", OS_WAIT_VBL),
    ]
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
        (None, "JSR", "abs", OS_REFRESH_NT),       # push updated shadow to the PPU
        (None, "PLA", "imp", None),
        (None, "TAY", "imp", None),
        (None, "PLA", "imp", None),
        (None, "TAX", "imp", None),
        (None, "JMP", "abs", OS_DECSP2),
    ]

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


def hook_plaintexts(labels):
    return {
        HOOK_NMI: bytes([0x4C, labels["LIVE"] & 0xFF, labels["LIVE"] >> 8, 0xEA, 0xEA]),
        HOOK_BOOT: bytes([0x20, labels["BOOT"] & 0xFF, labels["BOOT"] >> 8]),
        HOOK_BANNER: bytes([0x4C, labels["BANNER"] & 0xFF, labels["BANNER"] >> 8, 0xEA, 0xEA]),
        HOOK_IDLE: bytes([0x20, labels["IDLE"] & 0xFF, labels["IDLE"] >> 8]),
    }


def patch_runtime(data, orig_data):
    """Patch bank-15 runtime + hooks into an OS.BIN bytearray (in place).
    orig_data: EDFC-ORIGINAL/OS.BIN (its bytes in the region are the keystream,
    since the original plaintext there is all zeros)."""
    payload, labels = build_runtime()
    key = orig_data[FILE_REGION: FILE_REGION + REGION_LEN]
    data[FILE_REGION: FILE_REGION + REGION_LEN] = bytes(p ^ k for p, k in zip(payload, key))
    for cpu, plain in hook_plaintexts(labels).items():
        ks = HOOK_KEYSTREAM[cpu]
        assert len(ks) == len(plain)
        off = cpu - 0x2000
        data[off: off + len(plain)] = bytes(p ^ k for p, k in zip(plain, ks))
    return labels


if __name__ == "__main__":
    payload, labels = build_runtime()
    for k in ("BANNER", "BANNER_BODY", "LIVE", "BOOT", "IDLE", "_END"):
        print(f"  {k:12s} ${labels[k]:04X}")
    print(f"  used {labels['_END'] - REGION_START} / {REGION_LEN} bytes")
