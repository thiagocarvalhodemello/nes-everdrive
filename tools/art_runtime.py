"""
Per-game box art (EDFC/ARTS/<CRC>.BIN) on the game menu and the ROM info popup.

Entries (bank $0B, reached through bank-15 stubs; always main thread):
  ART_MENU  hook at $D582 (JSR $CA0D in the ROM file menu "Menu Arquivo"):
            fetches the selected file's record with the OS ($BC71), shows the
            cover, runs the OS menu ($CA0D) and hides the cover afterwards.
  ART_INFO  hook at $CFB2 (JSR $9F6C in "Info Arquivo"): record comes from the
            ROM info function's own buffer; shows the cover during the wait.
LOAD: rendering off, ROM sectors 0..4 -> CHR $1000 through the OS file API,
CRC-32 of file bytes 512..2559 read back from the PPU -> "XXXXXXXXBIN",
EDFC/ARTS lookup (the OS dir matcher compares exactly 4 characters), art
sectors -> CHR $1000, 48 8x16 sprites (64x96 px) at x=192 y=48.

RAM: internal RAM only, outside OS data:
  $0100-$018F  trampoline + variables (hardware stack never goes below $01DF)
  $0200-$02FF  file record buffer, then the OAM table (OS never reads page 2)
  zero page $9A-$9D and $30/$31 as scratch (saved/restored around the entries).
v1.4 kept the trampoline at $0300, which is the OS's cc65 DATA segment (menu
tables and directory variables): that corrupted the file list until reboot.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from theme_runtime import (assemble, build_runtime, B11_DISPATCH, B11_VARS, B11_CACHE, B11_DATA2, B11_PAL_TABLE,
                           GAME_MENU_TABLE,
                           FAR_ID, THEME_ID, NUM_THEMES, OS_REDRAW,
                           FAR_INFO, FAR_MENU, FAR_MAIN, FAR_SEL, FAR_FAVADD)
from fav_runtime import fav_listing, fav_symbols, DATA

ART_MAIN = B11_DISPATCH     # bank $0B far code: dispatcher first
ART_LIMIT = 0x8000          # end of bank $0B window

# OS entry points
OS_WAIT_VBL = 0x83B0
OS_WAIT_BTN = 0x9F6C
OS_MENU = 0xCA0D            # generic cursor menu (args already on the C stack)
OS_GET_ENTRY = 0xBC71       # (index8, buf16) -> file record: cluster32, ..., name
LIST_BASE, LIST_SEL = 0x0466, 0x8276   # *(u8*)(*LIST_BASE + *LIST_SEL) = file index
LIST_FLAGS = 0x0464         # *(u8*)(*LIST_FLAGS + file index): bit 7 = folder
LIST_COUNT = 0x04B8         # u16: entries in the browser list
OS_BROWSER_DRAW = 0xC7E2    # (redraw8): browser list + status bar for LIST_SEL (its loop calls it with 0)
OS_READ_FILE = 0x9541       # (cluster32, dst16, nsect8); dst < $2000 => PPU
OS_FIND_DIR = 0xAD3B        # (parent32, name*, out32*)
OS_FIND_FILE = 0x9DC7       # (dir32, name11*, 0, out32*)
OS_OPEN_DIR = 0x8DA9        # (cluster32): sets the FAT layer's current directory
BROWSE_DIR = 0x8278         # cluster32 of the directory the browser is showing
PUSHA, PUSH0, PUSHAX, PUSHEAX = 0xF3B2, 0xF3C4, 0xF3C8, 0xF1EC
EDFC_CLUSTER = 0x046E       # set by OS init (cluster of /EDFC)

C0, C1, C2, C3 = 0x9A, 0x9B, 0x9C, 0x9D    # CRC accumulator (zero page scratch)
OAM = 0x0200
REC = 0x0200               # record buffer (consumed before the OAM table is built)
SAVE3 = 0x7FE0             # bank $0B scratch: $BC71 writes the 8.3 name at buf+$100 (11 bytes)
ART_X, ART_Y = 192, 48

# ---- RAM trampoline (assembled for $0100, stored in bank $0B and copied)
T = 0x0100
T_LIMIT = 0x01B0            # hardware stack measured never below $01DF


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
    # exit to the OS with bank 8 mapped, A preserved (menu result)
    L += [("T_EXIT", "STA", "abs", "T_A"), (None, "LDA", "imm", 0x81)] + _map(0x08)[1:] + \
         [(None, "LDA", "abs", "T_A"), (None, "RTS", "imp", None)]
    L += [("T_PEEK", "LDA", "imm", 0x81)] + _map(0x08)[1:]
    L += [(None, "LDY", "imm", 3),
          ("PK", "LDA", "indy", 0x30), (None, "STA", "aby", "CLUS"),
          (None, "DEY", "imp", None), (None, "BPL", "rel", "PK")]
    L += _map(0x0B) + [(None, "RTS", "imp", None)]
    # T_COPY: copy CNT bytes (0 = 256) from ($9A) to ($9C) with bank 8 mapped
    L += [("T_COPY", "LDA", "imm", 0x81)] + _map(0x08)[1:]
    L += [(None, "LDY", "imm", 0),
          ("CPYL", "LDA", "indy", 0x9A), (None, "STA", "indy", 0x9C),
          (None, "INY", "imp", None), (None, "CPY", "abs", "CNT"), (None, "BNE", "rel", "CPYL")]
    L += _map(0x0B) + [(None, "RTS", "imp", None)]
    VARS = [("ARTSTR", b"arts\x00"), ("NAME11", b"00000000BIN\x00"),
            ("T_A", b"\x00"), ("T_X", b"\x00"), ("RES", b"\x00"), ("ZP", bytes(6)), ("CNT", b"\x00"), ("ADDR", b"\x00"),
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
    assert T + len(data) <= T_LIMIT, f"trampoline too big: {len(data)}"
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


DATA2 = ("D_DUP", "D_FULL", "D_NOFILE", "D_MAGIC")   # strings kept in the gap before the palettes
lab_data2 = []


def build_main(tramp_len, sym):
    L = [
        # ---- ART_INFO: record = ROM info function's buffer (word at C sp+1)
        ("ART_INFO", "JSR", "abs", "SETUP"),
        (None, "LDY", "imm", 1), (None, "LDA", "indy", 0x28), (None, "STA", "zp", 0x30),
        (None, "INY", "imp", None), (None, "LDA", "indy", 0x28), (None, "STA", "zp", 0x31),
        (None, "JSR", "abs", "T_PEEK"),
        (None, "JSR", "abs", "LOAD"),
        (None, "JSR", "abs", "ZPOUT"),
        *_call(OS_WAIT_BTN, 0),
        (None, "JSR", "abs", "HIDE"),
        (None, "JMP", "abs", "T_EXIT"),
        # ---- ART_MENU: index -> record via the OS, then the OS menu itself.
        # LEFT/RIGHT (menu result $FE/$FD, theme_runtime.menu_lr_code) move the browser
        # selection to the previous/next .NES/.FDS file and reopen the menu for it.
        ("ART_MENU", "JSR", "abs", "SETUP"),
        (None, "LDA", "imm", 0), (None, "STA", "abs", "V_DIR"),
        (None, "JSR", "abs", "GETREC"),
        ("AM_SHOW", "BEQ", "rel", "GOTREC"),
        (None, "CMP", "imm", 0xA0), (None, "BNE", "rel", "NOREC"),
        ("GOTREC", "LDX", "imm", 3),
        ("CR", "LDA", "abx", REC), (None, "STA", "abx", "CLUS"), (None, "DEX", "imp", None), (None, "BPL", "rel", "CR"),
        (None, "JSR", "abs", "LOAD"),
        ("NOREC", "JSR", "abs", "ZPOUT"),         # the OS menu runs with its own zero page
        *_call(OS_MENU, 0, 3),
        (None, "CMP", "imm", 0xFD), (None, "BCC", "rel", "MDONE"),
        (None, "CMP", "imm", 0xFF), (None, "BNE", "rel", "STEP"),
        ("MDONE", "STA", "abs", "RES"),
        (None, "JSR", "abs", "HIDE"),
        (None, "LDA", "abs", "RES"),
        (None, "JMP", "abs", "T_EXIT"),
        # ---- STEP: $FE = previous, $FD = next (the menu already popped its args: C sp -> file index)
        ("STEP", "STA", "abs", "V_DIR"),
        (None, "JSR", "abs", "HIDE"),
        (None, "JSR", "abs", "SETUP"),
        ("NXT", "LDA", "abs", "V_DIR"), (None, "LSR", "imp", None), (None, "BCS", "rel", "FWD"),
        (None, "LDA", "abs", LIST_SEL), (None, "ORA", "abs", LIST_SEL + 1), (None, "BNE", "rel", "BK1"),
        (None, "LDA", "abs", LIST_COUNT), (None, "STA", "abs", LIST_SEL),
        (None, "LDA", "abs", LIST_COUNT + 1), (None, "STA", "abs", LIST_SEL + 1),
        ("BK1", "LDA", "abs", LIST_SEL), (None, "BNE", "rel", "BK2"), (None, "DEC", "abs", LIST_SEL + 1),
        ("BK2", "DEC", "abs", LIST_SEL), (None, "JMP", "abs", "ISDIR"),
        ("FWD", "INC", "abs", LIST_SEL), (None, "BNE", "rel", "FW1"), (None, "INC", "abs", LIST_SEL + 1),
        ("FW1", "LDA", "abs", LIST_SEL), (None, "CMP", "abs", LIST_COUNT), (None, "BNE", "rel", "ISDIR"),
        (None, "LDA", "abs", LIST_SEL + 1), (None, "CMP", "abs", LIST_COUNT + 1), (None, "BNE", "rel", "ISDIR"),
        (None, "LDA", "imm", 0), (None, "STA", "abs", LIST_SEL), (None, "STA", "abs", LIST_SEL + 1),
        # folders: flag table *LIST_FLAGS indexed by file index, bit 7
        ("ISDIR", "JSR", "abs", "SELIDX"),
        (None, "LDA", "abs", "CLUS"), (None, "CLC", "imp", None), (None, "ADC", "abs", LIST_FLAGS),
        (None, "STA", "zp", 0x30), (None, "LDA", "abs", LIST_FLAGS + 1), (None, "ADC", "imm", 0),
        (None, "STA", "zp", 0x31), (None, "JSR", "abs", "T_PEEK"),
        (None, "LDA", "abs", "CLUS"), (None, "BMI", "rel", "NXT"),
        (None, "JSR", "abs", "GETREC"),
        (None, "CPY", "imm", 0), (None, "BNE", "rel", "NXT"),   # not .NES/.FDS
        (None, "PHA", "imp", None),
        (None, "LDA", "abs", "CLUS"), (None, "LDY", "imm", 0), (None, "STA", "indy", 0x28),  # $D556 uses it next
        (None, "TYA", "imp", None), (None, "JSR", "abs", PUSHA),  # browser redraw, as its loop does
        *_call(OS_BROWSER_DRAW, 0),
        (None, "LDA", "imm", GAME_MENU_TABLE & 0xFF), (None, "LDX", "imm", GAME_MENU_TABLE >> 8),
        (None, "JSR", "abs", PUSHAX),
        (None, "LDA", "imm", 3), (None, "JSR", "abs", PUSHA),
        (None, "LDA", "imm", 0), (None, "JSR", "abs", PUSHA),
        (None, "PLA", "imp", None), (None, "JMP", "abs", "AM_SHOW"),
        # ---- SELIDX: CLUS[0] = file index of the browser selection
        ("SELIDX", "LDA", "abs", LIST_BASE), (None, "CLC", "imp", None), (None, "ADC", "abs", LIST_SEL),
        (None, "STA", "zp", 0x30),
        (None, "LDA", "abs", LIST_BASE + 1), (None, "ADC", "abs", LIST_SEL + 1), (None, "STA", "zp", 0x31),
        (None, "JMP", "abs", "T_PEEK"),
        # ---- GETREC: record of the selection into REC; A = $BC71 status,
        # Y != 0 when stepping (V_DIR) and the name does not end in ES / DS (.nes, .fds)
        ("GETREC", "JSR", "abs", "SELIDX"),       # CLUS[0] = file index
        (None, "LDX", "imm", 15),                  # $BC71 overruns REC by 11 bytes into $0300:
        ("S3", "LDA", "abx", 0x0300), (None, "STA", "abx", SAVE3),   # keep the OS DATA there
        (None, "DEX", "imp", None), (None, "BPL", "rel", "S3"),
        (None, "LDA", "abs", "CLUS"), (None, "JSR", "abs", PUSHA),
        (None, "LDA", "imm", REC & 0xFF), (None, "LDX", "imm", REC >> 8), (None, "JSR", "abs", PUSHAX),
        *_call(OS_GET_ENTRY, REC & 0xFF, REC >> 8),
        (None, "PHA", "imp", None),
        (None, "LDY", "imm", 0),
        (None, "LDA", "abs", "V_DIR"), (None, "BEQ", "rel", "EXTOK"),
        (None, "LDX", "imm", 10),                  # display name (long, or "NAME    EXT"): its last 2 chars
        ("EL", "LDA", "abx", REC), (None, "BEQ", "rel", "EEND"), (None, "INX", "imp", None), (None, "BNE", "rel", "EL"),
        ("EEND", "LDA", "abx", REC - 1), (None, "AND", "imm", 0xDF), (None, "CMP", "imm", ord("S")),
        (None, "BNE", "rel", "EXTNO"),
        (None, "LDA", "abx", REC - 2), (None, "AND", "imm", 0xDF),
        (None, "CMP", "imm", ord("E")), (None, "BEQ", "rel", "EXTOK"),
        (None, "CMP", "imm", ord("D")), (None, "BEQ", "rel", "EXTOK"),
        ("EXTNO", "INY", "imp", None),
        ("EXTOK", "LDX", "imm", 15),
        ("R3", "LDA", "abx", SAVE3), (None, "STA", "abx", 0x0300),
        (None, "DEX", "imp", None), (None, "BPL", "rel", "R3"),
        (None, "PLA", "imp", None),
        (None, "RTS", "imp", None),
        # ---- SETUP: trampoline -> $0100, save zero page scratch
        ("SETUP", "LDX", "imm", tramp_len - 1),
        ("CP", "LDA", "abx", "TSRC"), (None, "STA", "abx", T),
        (None, "DEX", "imp", None), (None, "CPX", "imm", 0xFF), (None, "BNE", "rel", "CP"),
        (None, "LDX", "imm", 3),
        ("ZI", "LDA", "abx", C0), (None, "STA", "abx", "ZP"), (None, "DEX", "imp", None), (None, "BPL", "rel", "ZI"),
        (None, "LDA", "zp", 0x30), (None, "STA", "abs", "ZP+4"), (None, "LDA", "zp", 0x31), (None, "STA", "abs", "ZP+5"),
        (None, "RTS", "imp", None),
        ("ZPOUT", "LDX", "imm", 3),
        ("ZO", "LDA", "abx", "ZP"), (None, "STA", "abx", C0), (None, "DEX", "imp", None), (None, "BPL", "rel", "ZO"),
        (None, "LDA", "abs", "ZP+4"), (None, "STA", "zp", 0x30), (None, "LDA", "abs", "ZP+5"), (None, "STA", "zp", 0x31),
        (None, "RTS", "imp", None),
        ("HIDE", "JSR", "abs", OS_WAIT_VBL),
        (None, "LDA", "imm", 0x80), (None, "STA", "abs", 0x2000),
        (None, "LDA", "imm", 0x0A), (None, "STA", "abs", 0x2001),
        (None, "RTS", "imp", None),
        # ---- LOAD: show the cover for cluster CLUS (sprites on) or leave the screen as it was
        ("LOAD", "JSR", "abs", OS_WAIT_VBL),
        (None, "LDA", "imm", 0), (None, "STA", "abs", 0x2001),
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
          (None, "LDA", "imm", 0x1E), (None, "STA", "abs", 0x2001),
          (None, "RTS", "imp", None),
          # failure: give the directory back and restore the screen
          ("FAIL_N", "JSR", "abs", "REOPEN"),
          (None, "JSR", "abs", "RESTORE"),
          (None, "LDA", "imm", 0x0A), (None, "STA", "abs", 0x2001),
          (None, "RTS", "imp", None),
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
    # dispatcher + theme key + favourites first (DISPATCH must sit at B11_DISPATCH)
    consts = dict(FAR_ID=FAR_ID, THEME_ID=THEME_ID, NUM_THEMES=NUM_THEMES, B11_CACHE=B11_CACHE)
    L = fav_listing(build_runtime()[1]["APPLY"], consts) + L
    sym = dict(sym, **fav_symbols(B11_VARS))
    # layout: code | strings (DATA) | trampoline image (TSRC)
    dummy = {n: 0 for n, _ in DATA}
    code, _ = assemble(L, ART_MAIN, dict(sym, TSRC=0, **dummy))
    dsym, a, data, data2 = {}, ART_MAIN + len(code), bytearray(), bytearray()
    for n, b in DATA:
        if n in DATA2:
            dsym[n] = B11_DATA2 + len(data2)
            data2 += b
        else:
            dsym[n] = a + len(data)
            data += b
    assert B11_DATA2 + len(data2) <= B11_PAL_TABLE, "DATA2 strings overlap the palettes"
    lab_data2[:] = [bytes(data2)]
    tsrc = ART_MAIN + len(code) + len(data)
    code, lab = assemble(L, ART_MAIN, dict(sym, TSRC=tsrc, **dsym))
    assert lab["DISPATCH"] == B11_DISPATCH
    lab.update(dsym)
    return code + bytes(data), lab


def build_art_blob():
    tramp, tlab = build_tramp()
    code, lab = build_main(len(tramp), tlab)
    blob = code + tramp
    end = ART_MAIN + len(blob)
    assert end <= SAVE3, f"art runtime too large: ends ${end:04X} > ${SAVE3:04X}"
    lab.update({"_END": end, "_TRAMP": len(tramp)})
    return blob, lab


def install_into_bank11(b11):
    """Place the art runtime into a bank $0B image (bytearray, 0x2000)."""
    blob, lab = build_art_blob()
    off = ART_MAIN - 0x6000
    assert not any(b11[off:off + len(blob)]), "bank $0B area for art runtime is not free"
    b11[off:off + len(blob)] = blob
    d2, off2 = lab_data2[0], B11_DATA2 - 0x6000
    assert not any(b11[off2:off2 + len(d2)]), "bank $0B DATA2 area is not free (theme data too big?)"
    b11[off2:off2 + len(d2)] = d2
    return lab


if __name__ == "__main__":
    blob, lab = build_art_blob()
    print(f"art runtime ${ART_MAIN:04X}..${lab['_END']:04X} ({len(blob)} bytes, trampoline {lab['_TRAMP']})")
