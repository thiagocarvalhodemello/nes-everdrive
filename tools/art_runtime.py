"""
Per-game box art on the "Info Arquivo" (ROM info) popup.

Flow (all main-thread, hooked at $CFB2 where the OS waits for a button with
the popup on screen; never from the NMI):
  1. bank-15 stub maps bank $0B and jumps to ART_MAIN (this code, $7B90).
  2. ART_MAIN copies a small trampoline into internal RAM page $0300. Calls
     into the OS FAT API go through it: it maps bank 8 (OS work RAM) around
     the call and maps $0B back, so this code never runs with the wrong bank.
  3. Rendering off. The selected file is read (sectors 0..4) with the OS's
     own file API straight into CHR-RAM $1000 (the OS never uses the $1000
     pattern table), and CRC-32 of file bytes [512, 2560) is computed from
     the PPU. -> name "XXXXXXXXBIN".
  4. EDFC/ARTS/XXXXXXXX.BIN is looked up (the OS dir matcher compares
     exactly 4 characters, hence ARTS) and its 4 sectors streamed to $1000.
  5. OAM is built in page $0200 (48 8x16 sprites, 64x96 px at x=192, y=48),
     sprite palettes written, OAM DMA, 8x16 sprites + sprite rendering on.
  6. The OS button wait ($9F6C) runs; afterwards sprites are switched off.
No OS heap / work RAM is written: the only RAM used is pages $0200-$03FF
(cleared at reset, never used by the OS) and zero page $9A-$9D (scratch the
OS uses only inside its own nametable upload).
If anything fails (no ART dir, no file, bad magic) the popup behaves as before.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from theme_runtime import assemble, ART_ENTRY

ART_MAIN = 0x7C90           # bank $0B, after theme packages, palette table, loader
assert ART_MAIN == ART_ENTRY
ART_LIMIT = 0x8000          # end of bank $0B window
HOOK_ART = 0xCFB2           # orig: JSR $9F6C (bank 14, stored in plaintext)
HOOK_ART_KEYSTREAM = bytes(3)

# OS entry points
OS_WAIT_VBL = 0x83B0
OS_WAIT_BTN = 0x9F6C
OS_READ_FILE = 0x9541       # (cluster32, dst16, nsect8); dst < $2000 => PPU
OS_FIND_DIR = 0xAD3B        # (parent32, name*, out32*)
OS_FIND_FILE = 0x9DC7       # (dir32, name11*, 0, out32*)
OS_OPEN_DIR = 0x8DA9        # (cluster32): sets the FAT layer's current directory
BROWSE_DIR = 0x8278         # cluster32 of the directory the browser is showing
PUSHA, PUSH0, PUSHAX, PUSHEAX = 0xF3B2, 0xF3C4, 0xF3C8, 0xF1EC
EDFC_CLUSTER = 0x046E       # set by OS init (cluster of /EDFC)

C0, C1, C2, C3 = 0x9A, 0x9B, 0x9C, 0x9D    # CRC accumulator (zero page scratch)
OAM = 0x0200
ART_X, ART_Y = 192, 48

# ---- RAM trampoline (assembled for $0300, stored in bank $0B and copied)
T = 0x0300


def _map(bank):
    return [(None, "LDA", "imm", 0x81), (None, "STA", "abs", 0x4400),
            (None, "LDA", "imm", bank), (None, "STA", "abs", 0x4401)]


def build_tramp():
    L = [("T_CALL", "STA", "abs", "T_A"), (None, "STX", "abs", "T_X")]
    L += _map(0x08)
    L += [(None, "LDA", "abs", "T_A"), (None, "LDX", "abs", "T_X"),
          ("T_JSR", "JSR", "abs", 0x0000),
          (None, "STA", "abs", "T_A")]
    L += _map(0x0B)
    L += [(None, "LDA", "abs", "T_A"), (None, "RTS", "imp", None)]
    L += [("T_EXIT", "LDA", "imm", 0x81)] + _map(0x08)[1:] + [(None, "RTS", "imp", None)]
    L += [("T_PEEK", "LDA", "imm", 0x81)] + _map(0x08)[1:]
    L += [(None, "LDY", "imm", 3),
          ("PK", "LDA", "indy", 0x30), (None, "STA", "aby", "CLUS"),
          (None, "DEY", "imp", None), (None, "BPL", "rel", "PK")]
    L += _map(0x0B) + [(None, "RTS", "imp", None)]
    VARS = [("ARTSTR", b"arts\x00"), ("NAME11", b"00000000BIN\x00"),
            ("T_A", b"\x00"), ("T_X", b"\x00"), ("CNT", b"\x00"), ("ADDR", b"\x00"),
            ("CLUS", bytes(4)), ("DIR32", bytes(4)), ("FILE32", bytes(4)), ("PAL", bytes(12))]
    # pass 1 with placeholder variable addresses to learn the code size
    code, _ = assemble(L, T, {n: 0 for n, _ in VARS})
    sym, v, init = {}, T + len(code), bytearray()
    for n, b in VARS:
        sym[n] = v
        v += len(b)
        init += b
    code, lab = assemble(L, T, sym)
    lab.update(sym)
    data = code + bytes(init)
    assert len(data) <= 0x100, f"trampoline too big: {len(data)}"
    return data, lab


def _call(target, a_expr, x_expr=None):
    """Point the trampoline at target and call it with A (and X) as the OS does."""
    r = [(None, "LDA", "imm", target & 0xFF), (None, "STA", "abs", "T_JSR+1"),
         (None, "LDA", "imm", target >> 8), (None, "STA", "abs", "T_JSR+2")]
    if x_expr is not None:
        r.append((None, "LDX", "imm", x_expr))
    r += [(None, "LDA", "imm", a_expr), (None, "JSR", "abs", "T_CALL")]
    return r


def _push32(var):
    return [(None, "LDA", "abs", f"{var}+2"), (None, "STA", "zp", 0x2A),
            (None, "LDA", "abs", f"{var}+3"), (None, "STA", "zp", 0x2B),
            (None, "LDA", "abs", var), (None, "LDX", "abs", f"{var}+1"),
            (None, "JSR", "abs", PUSHEAX)]


def _pushptr(sym):
    return [(None, "LDA", "imm", f"{sym} & 0xFF"), (None, "LDX", "imm", f"{sym} >> 8"),
            (None, "JSR", "abs", PUSHAX)]


def _jne(target):
    """long BNE: BEQ over a JMP"""
    return [(None, "BEQ", "rel", "_pc+5"), (None, "JMP", "abs", target)]


def _jeq(target):
    return [(None, "BNE", "rel", "_pc+5"), (None, "JMP", "abs", target)]


def _nonzero32(var, fail):
    return [(None, "LDA", "abs", var), (None, "ORA", "abs", f"{var}+1"),
            (None, "ORA", "abs", f"{var}+2"), (None, "ORA", "abs", f"{var}+3"),
            *_jeq(fail)]


def _ppu_addr(hi, lo):
    return [(None, "BIT", "abs", 0x2002), (None, "LDA", "imm", hi), (None, "STA", "abs", 0x2006),
            (None, "LDA", "imm", lo), (None, "STA", "abs", 0x2006)]


def build_main(tramp_len, sym):
    L = [
        # 1. trampoline -> $0300
        ("ART_MAIN", "LDX", "imm", tramp_len - 1),
        ("CP", "LDA", "abx", "TSRC"), (None, "STA", "abx", T),
        (None, "DEX", "imp", None), (None, "CPX", "imm", 0xFF), (None, "BNE", "rel", "CP"),
        # 2. file record pointer (C stack frame of the ROM info function) -> cluster
        (None, "LDY", "imm", 1), (None, "LDA", "indy", 0x28), (None, "STA", "zp", 0x30),
        (None, "INY", "imp", None), (None, "LDA", "indy", 0x28), (None, "STA", "zp", 0x31),
        (None, "JSR", "abs", "T_PEEK"),
        # 3. rendering off, read sectors 0..4 of the ROM into CHR $1000
        (None, "JSR", "abs", OS_WAIT_VBL), (None, "LDA", "imm", 0), (None, "STA", "abs", 0x2001),
    ]
    L += _push32("CLUS") + [(None, "LDA", "imm", 0x00), (None, "LDX", "imm", 0x10), (None, "JSR", "abs", PUSHAX),
                            (None, "LDA", "imm", 5), (None, "JSR", "abs", PUSHA)]
    # one call: sectors 0..4 -> $1000-$19FF (sectors 1..4 = file bytes 512..2559 at $1200)
    L += _call(OS_READ_FILE, 5) + [*_jne("FAIL_N")]
    # 4. CRC-32 of PPU $1200-$19FF (= file bytes 512..2559)
    L += [(None, "LDA", "imm", 0xFF), (None, "STA", "zp", C0), (None, "STA", "zp", C1),
          (None, "STA", "zp", C2), (None, "STA", "zp", C3)]
    L += _ppu_addr(0x12, 0x00) + [(None, "LDA", "abs", 0x2007),
          (None, "LDX", "imm", 8), (None, "LDY", "imm", 0),
          ("CB", "LDA", "abs", 0x2007), (None, "EOR", "zp", C0), (None, "STA", "zp", C0),
          (None, "LDA", "imm", 8), (None, "STA", "abs", "CNT"),
          ("BL", "LSR", "zp", C3), (None, "ROR", "zp", C2), (None, "ROR", "zp", C1), (None, "ROR", "zp", C0),
          (None, "BCC", "rel", "NX"),
          (None, "LDA", "zp", C3), (None, "EOR", "imm", 0xED), (None, "STA", "zp", C3),
          (None, "LDA", "zp", C2), (None, "EOR", "imm", 0xB8), (None, "STA", "zp", C2),
          (None, "LDA", "zp", C1), (None, "EOR", "imm", 0x83), (None, "STA", "zp", C1),
          (None, "LDA", "zp", C0), (None, "EOR", "imm", 0x20), (None, "STA", "zp", C0),
          ("NX", "DEC", "abs", "CNT"), (None, "BNE", "rel", "BL"),
          (None, "INY", "imp", None), (None, "BNE", "rel", "CB"),
          (None, "DEX", "imp", None), (None, "BNE", "rel", "CB"),
          # 5. name: hex(~crc) big-endian + "BIN"
          (None, "LDX", "imm", 0),
          (None, "LDA", "zp", C3), (None, "JSR", "abs", "HEX2"),
          (None, "LDA", "zp", C2), (None, "JSR", "abs", "HEX2"),
          (None, "LDA", "zp", C1), (None, "JSR", "abs", "HEX2"),
          (None, "LDA", "zp", C0), (None, "JSR", "abs", "HEX2")]
    # 6. find EDFC/ART, then the file
    L += [(None, "LDA", "abs", EDFC_CLUSTER + 2), (None, "STA", "zp", 0x2A),
          (None, "LDA", "abs", EDFC_CLUSTER + 3), (None, "STA", "zp", 0x2B),
          (None, "LDA", "abs", EDFC_CLUSTER), (None, "LDX", "abs", EDFC_CLUSTER + 1),
          (None, "JSR", "abs", PUSHEAX)]
    L += _pushptr("ARTSTR") + _pushptr("DIR32")
    L += _call(OS_FIND_DIR, "DIR32 & 0xFF", "DIR32 >> 8") + [*_jne("FAIL_N")]
    L += _nonzero32("DIR32", "FAIL_N")
    L += _push32("DIR32") + _pushptr("NAME11") + [(None, "JSR", "abs", PUSH0)] + _pushptr("FILE32")
    L += _call(OS_FIND_FILE, "FILE32 & 0xFF", "FILE32 >> 8") + [*_jne("FAIL_N")]
    L += _nonzero32("FILE32", "FAIL_N")
    # 7. art file -> CHR $1000-$17FF
    L += _push32("FILE32") + [(None, "LDA", "imm", 0x00), (None, "LDX", "imm", 0x10), (None, "JSR", "abs", PUSHAX),
                              (None, "LDA", "imm", 4), (None, "JSR", "abs", PUSHA)]
    L += _call(OS_READ_FILE, 4) + [*_jne("FAIL_N")]
    # the lookups re-pointed the OS "current directory": give it back to the browser
    L += [(None, "JSR", "abs", "REOPEN")]
    # 8. metadata at $1600: "NA", ver, res, 12 palette bytes, 48 attributes -> OAM byte 2
    L += _ppu_addr(0x16, 0x00) + [(None, "LDA", "abs", 0x2007),
          (None, "LDA", "abs", 0x2007), (None, "CMP", "imm", ord("N")), *_jne("FAIL_N"),
          (None, "LDA", "abs", 0x2007), (None, "CMP", "imm", ord("A")), *_jne("FAIL_N"),
          (None, "LDA", "abs", 0x2007), (None, "LDA", "abs", 0x2007),
          (None, "LDX", "imm", 0),
          ("PL", "LDA", "abs", 0x2007), (None, "STA", "abx", "PAL"),
          (None, "INX", "imp", None), (None, "CPX", "imm", 12), (None, "BNE", "rel", "PL"),
          (None, "LDX", "imm", 2),
          ("AL", "LDA", "abs", 0x2007), (None, "AND", "imm", 3), (None, "STA", "abx", OAM),
          (None, "INX", "imp", None), (None, "INX", "imp", None), (None, "INX", "imp", None), (None, "INX", "imp", None),
          (None, "CPX", "imm", 2 + 48 * 4), (None, "BNE", "rel", "AL"),
          # 9. OAM Y / tile / X for 48 sprites, hide the rest
          (None, "LDX", "imm", 0), (None, "LDY", "imm", 0),
          ("OL", "TYA", "imp", None), (None, "AND", "imm", 0xF8), (None, "ASL", "imp", None),
          (None, "CLC", "imp", None), (None, "ADC", "imm", ART_Y - 1), (None, "STA", "abx", OAM),
          (None, "TYA", "imp", None), (None, "ASL", "imp", None), (None, "ORA", "imm", 1), (None, "STA", "abx", OAM + 1),
          (None, "TYA", "imp", None), (None, "AND", "imm", 7), (None, "ASL", "imp", None), (None, "ASL", "imp", None),
          (None, "ASL", "imp", None), (None, "CLC", "imp", None), (None, "ADC", "imm", ART_X), (None, "STA", "abx", OAM + 3),
          (None, "TXA", "imp", None), (None, "CLC", "imp", None), (None, "ADC", "imm", 4), (None, "TAX", "imp", None),
          (None, "INY", "imp", None), (None, "CPY", "imm", 48), (None, "BNE", "rel", "OL"),
          (None, "LDA", "imm", 0xF0),
          ("HL", "STA", "abx", OAM), (None, "INX", "imp", None), (None, "BNE", "rel", "HL"),
          # 10. sprite palettes $3F11.. (skip $3F10/14/18/1C: they mirror BG entries)
          (None, "LDX", "imm", 0), (None, "LDA", "imm", 0x11), (None, "STA", "abs", "ADDR"),
          ("SP", "BIT", "abs", 0x2002), (None, "LDA", "imm", 0x3F), (None, "STA", "abs", 0x2006),
          (None, "LDA", "abs", "ADDR"), (None, "STA", "abs", 0x2006),
          (None, "LDA", "abx", "PAL"), (None, "STA", "abs", 0x2007),
          (None, "LDA", "abx", "PAL+1"), (None, "STA", "abs", 0x2007),
          (None, "LDA", "abx", "PAL+2"), (None, "STA", "abs", 0x2007),
          (None, "INX", "imp", None), (None, "INX", "imp", None), (None, "INX", "imp", None),
          (None, "LDA", "abs", "ADDR"), (None, "CLC", "imp", None), (None, "ADC", "imm", 4), (None, "STA", "abs", "ADDR"),
          (None, "CPX", "imm", 12), (None, "BNE", "rel", "SP"),
          # 11. OAM DMA, then sprites on (8x16) at the next vblank
          (None, "LDA", "imm", 0), (None, "STA", "abs", 0x2003),
          (None, "LDA", "imm", OAM >> 8), (None, "STA", "abs", 0x4014),
          (None, "JSR", "abs", "RESTORE"),
          (None, "LDA", "imm", 0xA0), (None, "STA", "abs", 0x2000),
          (None, "LDA", "imm", 0x1E), (None, "STA", "abs", 0x2001)]
    L += _call(OS_WAIT_BTN, 0)
    L += [(None, "JSR", "abs", OS_WAIT_VBL),
          (None, "LDA", "imm", 0x80), (None, "STA", "abs", 0x2000),
          (None, "LDA", "imm", 0x0A), (None, "STA", "abs", 0x2001),
          (None, "JMP", "abs", "T_EXIT"),
          # failure: just restore the screen and wait as the OS would
          ("FAIL_N", "JSR", "abs", "REOPEN"),
          (None, "JSR", "abs", "RESTORE"),
          (None, "LDA", "imm", 0x0A), (None, "STA", "abs", 0x2001)]
    L += _call(OS_WAIT_BTN, 0)
    L += [(None, "JMP", "abs", "T_EXIT"),
          ("REOPEN", "LDA", "abs", BROWSE_DIR + 2), (None, "STA", "zp", 0x2A),
          (None, "LDA", "abs", BROWSE_DIR + 3), (None, "STA", "zp", 0x2B),
          (None, "LDA", "abs", BROWSE_DIR), (None, "LDX", "abs", BROWSE_DIR + 1),
          (None, "JSR", "abs", PUSHEAX),
          (None, "LDA", "imm", OS_OPEN_DIR & 0xFF), (None, "STA", "abs", "T_JSR+1"),
          (None, "LDA", "imm", OS_OPEN_DIR >> 8), (None, "STA", "abs", "T_JSR+2"),
          (None, "LDA", "abs", BROWSE_DIR), (None, "LDX", "abs", BROWSE_DIR + 1),
          (None, "JMP", "abs", "T_CALL"),
          ("RESTORE", "BIT", "abs", 0x2002), (None, "LDA", "imm", 0),
          (None, "STA", "abs", 0x2006), (None, "STA", "abs", 0x2006),
          (None, "STA", "abs", 0x2005), (None, "STA", "abs", 0x2005),
          (None, "JMP", "abs", OS_WAIT_VBL),
          ("HEX2", "EOR", "imm", 0xFF),               # final CRC inversion
          (None, "PHA", "imp", None),
          (None, "LSR", "imp", None), (None, "LSR", "imp", None), (None, "LSR", "imp", None), (None, "LSR", "imp", None),
          (None, "JSR", "abs", "HEX1"), (None, "PLA", "imp", None), (None, "AND", "imm", 0x0F),
          ("HEX1", "CMP", "imm", 10), (None, "BCC", "rel", "HD"), (None, "ADC", "imm", 6),
          ("HD", "ADC", "imm", 0x30), (None, "STA", "abx", "NAME11"), (None, "INX", "imp", None),
          (None, "RTS", "imp", None)]
    # TSRC = trampoline bytes appended after the code
    code, lab = assemble(L, ART_MAIN, dict(sym, TSRC=0))
    tsrc = ART_MAIN + len(code)
    code, lab = assemble(L, ART_MAIN, dict(sym, TSRC=tsrc))
    return code, lab


def build_art_blob():
    tramp, tlab = build_tramp()
    code, lab = build_main(len(tramp), tlab)
    blob = code + tramp
    end = ART_MAIN + len(blob)
    assert end <= ART_LIMIT, f"art runtime too large: ends ${end:04X} > ${ART_LIMIT:04X}"
    lab.update({"_END": end, "_TRAMP": len(tramp)})
    return blob, lab


def install_into_bank11(b11):
    """Place the art runtime into a bank $0B image (bytearray, 0x2000)."""
    blob, lab = build_art_blob()
    off = ART_MAIN - 0x6000
    assert not any(b11[off:off + len(blob)]), "bank $0B area for art runtime is not free"
    b11[off:off + len(blob)] = blob
    return lab


if __name__ == "__main__":
    blob, lab = build_art_blob()
    print(f"art runtime ${ART_MAIN:04X}..${lab['_END']:04X} ({len(blob)} bytes, trampoline {lab['_TRAMP']})")
