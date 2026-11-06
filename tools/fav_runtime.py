"""
Overlay module LISTA (EDFC/OVLLIST.BIN): favourites and recently played games.
Loaded into the bank $0B overlay area by the resident code (art_runtime.OVL);
entries (jump table after the 4-byte header):
  E0 FAVADD  game menu "Favoritar" (ends with T_EXIT, asks the browser to redraw)
  E1 SCREEN  list screen; V_MODE 0 = Favoritos, 1 = Recentes (RTS back to the menu)
  E2 RECADD  add/bump the game at *$046A in RECENTS.DAT (called before every launch)

Files (created on the PC, shipped in the zip; the console never creates, grows or
renames them - no FAT/directory writes): EDFC/FAVS.DAT and EDFC/RECENTS.DAT,
  32 sectors x 512 bytes, sector K = slot K:
    0..270   copy of the OS "current game" record ($BF16 builds it at *$046A:
             cluster32, ..., long name at +10, $55 $AA at +$10B); cluster 0 = empty
    271..273 RECENTS.DAT: play counter (24 bit, higher = more recent)
    503      K (slot number)          } checked before every write: a wrong LBA
    504..511 "EDFCFAV1"               } can never touch another file
  LBA of sector K: walk the cluster chain K / spc times ($C404), $969A, + K % spc.
Recentes: a launch rewrites the slot of the same game, else the first empty slot,
else the least recent one (one sector written per launch); the list is sorted by counter.

Screens use the OS text routines ($A854 clear + banner, $A864 print line,
$8343 upload, $9F6C wait button); $9F = $7F highlights the next line.
"""
import re

FAV_SLOTS = 32
FAV_TAIL = 503
FAV_MAGIC = b"EDFCFAV1"
SEQ_OFF = 271
ROWS = 19                 # visible list lines (y = 3..21)

# OS
PUSHA, PUSH0, PUSHAX, PUSHEAX = 0xF3B2, 0xF3C4, 0xF3C8, 0xF1EC
OS_MALLOC, OS_FREE = 0xA451, 0xA476            # (size16): LIFO bump allocator at $0450
OS_HEAP_TOP = 0x0450
OS_CL2LBA = 0x969A        # (cluster32) -> lba32 in A/X/sreg
OS_NEXTCL = 0xC404        # (&cluster32) -> 0 ok, cluster updated in place
OS_READ_SECT = 0xAAD5     # (lba32, dst16, n8) -> 0 ok
OS_WRITE_SECT = 0xAB0A    # (src16, n8, lba32) -> 0 ok
OS_FIND_FILE = 0x9DC7     # (dir32, name11*, 0, out32*)
OS_GAME_REC = 0xBF16      # (index8, recptr16) -> 0 ok; builds the "current game" record
OS_START_GAME = 0xB7AC    # starts the game described by the record at *$046A
OS_TXT_BEGIN = 0xA854     # clear screen (banner hook runs), cursor x=2 y=1
OS_TXT_LINE = 0xA864      # (str16) print + next line
OS_TXT_Y = 0x048E
OS_REFRESH_NT = 0x8343
OS_WAIT_BTN = 0x9F6C      # -> A = buttons
OS_RESTORE_SCR = 0x847C
REC_PTR = 0x046A
SPC = 0x04A7
EDFC_CLUSTER = 0x046E
BTN_CONFIRM, BTN_CANCEL = 0x0486, 0x0487
OS_REDRAW = 0x04D4

# page 2 (internal RAM, free; transient). $0280-$02BF = main menu table (art_runtime START)
STRBUF = 0x0200           # 32: text line for $A864
CLW = 0x0220              # 4: cluster walk (written by $C404)
FCL = 0x0224              # 4: file first cluster (written by $9DC7)
BUFP = 0x0228             # 2: sector buffer (OS heap, bank 8)
TMP4 = 0x022A             # 4: slot cluster read back
FNAME = 0x0230            # 12: "FAVS    DAT"
RECCL = 0x023C            # 4: cluster of the game being added
TMPT = 0x0240             # 9: sector tail read back
TMPS = 0x0249             # 3: play counter
NAMEB = 0x0250            # 32: search (find_runtime): name being compared


# ---------------------------------------------------------------------------
# text assembler front end + macros (shared by the resident code and the modules)
# ---------------------------------------------------------------------------
def asm_text(src):
    """Tiny text front end for theme_runtime.assemble.
    'LBL: LDA #expr' imm, 'LDA z:expr' zero page, 'LDA (expr),Y' indy,
    'LDA expr,X' abx, 'LDA expr,Y' aby, 'LDA expr' abs, bare mnemonic imp,
    'DB e1, e2, ...' bytes, 'DS n' n zero bytes, 'DT "text"' text + NUL (\\x01 escapes ok).
    Expressions are Python ($hex allowed); ';' starts a comment (not inside DT)."""
    out, pending = [], None
    for raw in src.splitlines():
        if re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*:\s*)?DT\s", raw):
            line = raw.strip()
        else:
            line = raw.split(";")[0].strip()
        if not line:
            continue
        lbl = None
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if m:
            lbl, line = m.group(1), m.group(2).strip()
            if not line:            # label on its own line: attach to the next instruction
                assert pending is None, raw
                pending = lbl
                continue
        if pending:
            assert lbl is None, raw
            lbl, pending = pending, None
        parts = line.split(None, 1)
        mn = parts[0].upper()
        arg = parts[1].strip() if len(parts) > 1 else None
        fix = lambda e: re.sub(r"\$([0-9A-Fa-f]+)", r"0x\1", e)
        if mn == "DB":
            out.append((lbl, "DB", "data", [fix(e.strip()) for e in arg.split(",")]))
            continue
        if mn == "DS":
            out.append((lbl, "DB", "data", bytes(int(fix(arg), 0))))
            continue
        if mn == "DT":
            txt = eval("b" + arg)
            out.append((lbl, "DB", "data", txt + b"\x00"))
            continue
        if arg is None:
            mode, op = "imp", None
        elif mn in ("BCC", "BCS", "BEQ", "BNE", "BMI", "BPL", "BVC", "BVS"):
            mode, op = "rel", fix(arg)
        elif arg.startswith("#"):
            mode, op = "imm", fix(arg[1:])
        elif arg.startswith("z:"):
            mode, op = "zp", fix(arg[2:])
        elif re.match(r"^\(.*\),\s*[Yy]$", arg):
            mode, op = "indy", fix(arg[1:arg.rindex(")")])
        elif re.search(r",\s*[Xx]$", arg):
            mode, op = "abx", fix(arg[:arg.rindex(",")])
        elif re.search(r",\s*[Yy]$", arg):
            mode, op = "aby", fix(arg[:arg.rindex(",")])
        else:
            mode, op = "abs", fix(arg)
        out.append((lbl, mn, mode, op))
    assert pending is None, f"label {pending} at the end"
    return out


def _call(target, a=0, x=None):
    """OS call through the trampoline (bank 8 mapped during the call); args already
    pushed. 'JSR CALLI' + target + A value (resident helper; X and Y pass through)."""
    s = f"    LDX #{x}\n" if x is not None else ""
    return s + f"    JSR CALLI\n    DB {target & 0xFF}, {target >> 8}, ({a}) & 255\n"


def _push32(var):
    return f"""
        LDA {var}+2
        STA z:$2A
        LDA {var}+3
        STA z:$2B
        LDA {var}
        LDX {var}+1
        JSR {PUSHEAX}
    """


def _pushptr(sym):
    return f"""
        LDA #({sym}) & 0xFF
        LDX #({sym}) >> 8
        JSR {PUSHAX}
    """


def _puts(sym, hl=False):
    s = "    LDA #$7F\n    STA z:$9F\n" if hl else ""
    return s + f"    LDA #({sym}) & 0xFF\n    LDX #({sym}) >> 8\n    JSR PUTS\n"


_n = [0]


def _mstr(sym0, sym1):
    """A/X = sym0 (V_MODE 0) or sym1 (V_MODE 1)"""
    _n[0] += 1
    k = _n[0]
    return f"""
        LDA V_MODE
        BEQ MS0_{k}
        LDA #({sym1}) & 0xFF
        LDX #({sym1}) >> 8
        BNE MS1_{k}
MS0_{k}: LDA #({sym0}) & 0xFF
        LDX #({sym0}) >> 8
MS1_{k}:
"""


def _mputs(sym0, sym1, hl=False):
    s = "    LDA #$7F\n    STA z:$9F\n" if hl else ""
    return s + _mstr(sym0, sym1) + "    JSR PUTS\n"


# bank $0B variables (resident; only our code touches them)
VARS_SRC = {
    "V_K": 0, "V_NFAV": 1, "V_CUR": 2, "V_TOP": 3, "V_FREE": 4, "V_FOUND": 5,
    "V_I": 6, "V_BTN": 7, "V_LBA": 8, "V_MSG": 12,
    "V_DIR": 14,        # art module: game menu LEFT/RIGHT ($FE/$FD), 0 = normal entry
}


def module_list(header, mode):
    """Assembly text of the FAVORITOS (mode 0: E0 FAVADD, E1 SCREEN) or RECENTES
    (mode 1: E0 RECADD, E1 SCREEN) overlay. SCREEN returns C=1 when a favourite was
    chosen (record at *$046A; the resident code records it in Recentes and starts it)."""
    rows = ROWS
    fav, rec = mode == 0, mode == 1
    s = header + ("""
        JMP FAVADD
        JMP SCREEN
""" if fav else """
        JMP RECADD
        JMP SCREEN
""")
    if fav:
        s += f"""
; ---- game menu item "Favoritar"
FAVADD: LDY #0
        LDA ($28),Y             ; file index (menu local)
        JSR {PUSHA}
        LDA {REC_PTR}
        LDX {REC_PTR}+1
        JSR {PUSHAX}
""" + _call(OS_GAME_REC) + f"""
        BEQ FA0
        JMP FA_IO2
FA0:    JSR RECCL_SET
        JSR F_OPEN
        BCC FA1
        LDA #D_NOFILE & 0xFF
        LDX #D_NOFILE >> 8
        JMP FA_MSG
FA1:    JSR F_SCAN
        BCS FA_IO
        LDA V_FOUND
        BEQ FA2
        LDA #D_DUP & 0xFF
        LDX #D_DUP >> 8
        JMP FA_CL
FA2:    LDA V_FREE
        BPL FA3
        LDA #D_FULL & 0xFF
        LDX #D_FULL >> 8
        JMP FA_CL
FA3:    STA V_K
        JSR F_READ
        BCS FA_IO
        JSR CPREC
        JSR F_WRITE
        BCS FA_IO
        LDA #D_SAVED & 0xFF
        LDX #D_SAVED >> 8
        JMP FA_CL
FA_IO:  LDA #D_IO & 0xFF
        LDX #D_IO >> 8
FA_CL:  STA V_MSG
        STX V_MSG+1
        JSR F_CLOSE
        LDA V_MSG
        LDX V_MSG+1
FA_MSG: JSR SHOWMSG
        LDA #1
        STA {OS_REDRAW}
        JSR ZPOUT
        JMP T_EXIT
FA_IO2: LDA #D_IO & 0xFF
        LDX #D_IO >> 8
        JMP FA_MSG
"""
    s += f"""
; ---- RECCL = cluster of the record at *$046A
RECCL_SET: LDA #0
        TAX
        JSR REC_SRC
        LDA #{RECCL & 0xFF}
        STA z:$9C
        LDA #{RECCL >> 8}
        STA z:$9D
        LDA #4
        STA CNT
        JMP T_COPY

; ---- record (*$046A, 271 bytes) -> sector buffer
CPREC:  LDA #0
        TAX
        JSR REC_SRC
        LDA #0
        TAX
        JSR BUF_DST
        LDA #0
        STA CNT                 ; 256 bytes
        JSR T_COPY
        LDA #0
        LDX #1
        JSR REC_SRC
        LDA #0
        LDX #1
        JSR BUF_DST
        LDA #15                 ; record bytes 256..270
        STA CNT
        JMP T_COPY
"""
    if rec:
        s += f"""
; ---- recently played: add or bump the game at *$046A (silent; errors ignored)
RECADD: JSR RECCL_SET
        JSR F_OPEN
        BCS RA_X
        JSR F_SCAN
        BCS RA_C
        LDA V_FOUND
        BEQ RA1
        SEC
        SBC #1
        JMP RA3
RA1:    LDA V_FREE
        BPL RA3
        LDA V_MINK
RA3:    STA V_K
        JSR F_READ
        BCS RA_C
        JSR CPREC
        LDA V_MAXS
        CLC
        ADC #1
        STA {TMPS}
        LDA V_MAXS+1
        ADC #0
        STA {TMPS}+1
        LDA V_MAXS+2
        ADC #0
        STA {TMPS}+2
        LDA #{TMPS & 0xFF}
        STA z:$9A
        LDA #{TMPS >> 8}
        STA z:$9B
        LDA #{SEQ_OFF & 0xFF}
        LDX #{SEQ_OFF >> 8}
        JSR BUF_DST
        LDA #3
        STA CNT
        JSR T_COPY
        JSR F_WRITE
RA_C:   JSR F_CLOSE
RA_X:   RTS
"""
    s += f"""
; ---- list screen (from the main menu)
SCREEN: LDA #0
        STA {RECCL}
        STA {RECCL}+1
        STA {RECCL}+2
        STA {RECCL}+3
        JSR F_OPEN
        BCC FS0
        LDA #D_NOFILE & 0xFF
        LDX #D_NOFILE >> 8
        JSR SHOWMSG
        CLC
        RTS
FS0:    JSR SCAN_S
        BCC FS1
        JMP FS_IO
FS1:    LDA #0
        STA V_CUR
        STA V_TOP
FS_D:   JSR DRAW
FS_K:
""" + _call(OS_WAIT_BTN) + f"""
        STA V_BTN
        AND #$08                ; up
        BEQ FS_2
        LDA V_CUR
        BEQ FS_K
        DEC V_CUR
        LDA V_CUR
        CMP V_TOP
        BCS FS_D
        STA V_TOP
        JMP FS_D
FS_2:   LDA V_BTN
        AND #$04                ; down
        BEQ FS_3
        LDX V_CUR
        INX
        CPX V_NFAV
        BCS FS_K
        STX V_CUR
        TXA
        SEC
        SBC V_TOP
        CMP #{rows}
        BCC FS_D
        INC V_TOP
        JMP FS_D
FS_3:   LDA V_BTN
        AND {BTN_CANCEL}
        BEQ FS_4
        JSR F_CLOSE             ; back to the main menu
        CLC
        RTS
FS_4:   LDA V_NFAV
        BEQ FS_K
        LDA V_BTN
        AND {BTN_CONFIRM}
        BEQ FS_5
        JMP FS_GO
FS_5:   LDA V_BTN
        AND #$20                ; select: remove
        BNE FS_6
        JMP FS_K
FS_6:   JSR SLOTK
        JSR F_READ
        BCS FS_IO
        LDA #0
        STA {TMP4}
        STA {TMP4}+1
        STA {TMP4}+2
        STA {TMP4}+3
        LDA #{TMP4 & 0xFF}
        STA z:$9A
        LDA #{TMP4 >> 8}
        STA z:$9B
        LDA #0
        TAX
        JSR BUF_DST
        LDA #4
        STA CNT
        JSR T_COPY
        JSR F_WRITE
        BCS FS_IO
        JSR SCAN_S
        BCS FS_IO
        LDA V_CUR
        CMP V_NFAV
        BCC FS_7
        LDA V_NFAV
        BEQ FS_7A
        SEC
        SBC #1
FS_7A:  STA V_CUR
FS_7:   LDA V_CUR
        CMP V_TOP
        BCS FS_8
        STA V_TOP
FS_8:   JMP FS_D
FS_IO:  JSR F_CLOSE
        LDA #D_IO & 0xFF
        LDX #D_IO >> 8
        JSR SHOWMSG
        CLC
        RTS
FS_GO:  JSR SLOTK
        JSR F_READ
        BCS FS_IO
        LDA #0
        TAX
        JSR BUF_SRC
        LDA #0
        TAX
        JSR REC_DST
        LDA #0
        STA CNT
        JSR T_COPY
        LDA #0
        LDX #1
        JSR BUF_SRC
        LDA #0
        LDX #1
        JSR REC_DST
        LDA #15
        STA CNT
        JSR T_COPY
        JSR F_CLOSE
""" + ("""        SEC                     ; favourite chosen: the resident code starts it
        RTS
""" if fav else """        JSR RECADD
        JSR ZPOUT
""" + _call(OS_START_GAME) + """        CLC
        RTS
""") + ("""
SCAN_S: JMP F_SCAN
""" if fav else """
; ---- F_SCAN, then most recent first
SCAN_S: JSR F_SCAN
        BCS SS_X
        JSR SORT
        CLC
SS_X:   RTS
""") + (f"""
; ---- bubble sort of the cache by counter (bytes 28..30), descending
SORT:   LDA V_NFAV
        CMP #2
        BCC SO_X
SO_P:   LDA #0
        STA V_SW
        STA V_I
SO_L:   LDX V_I
        INX
        CPX V_NFAV
        BCS SO_E
        LDA V_I
        JSR ENTRY
        LDA z:$30
        CLC
        ADC #32
        STA z:$9A
        LDA z:$31
        ADC #0
        STA z:$9B
        LDY #30
        LDA ($30),Y
        CMP ($9A),Y
        BCC SO_S
        BNE SO_N
        DEY
        LDA ($30),Y
        CMP ($9A),Y
        BCC SO_S
        BNE SO_N
        DEY
        LDA ($30),Y
        CMP ($9A),Y
        BCS SO_N
SO_S:   LDY #31
SO_W:   LDA ($30),Y
        PHA
        LDA ($9A),Y
        STA ($30),Y
        PLA
        STA ($9A),Y
        DEY
        BPL SO_W
        LDA #1
        STA V_SW
SO_N:   INC V_I
        JMP SO_L
SO_E:   LDA V_SW
        BNE SO_P
SO_X:   RTS
""" if rec else "") + f"""
SLOTK:  LDA V_CUR
        JSR ENTRY
        LDY #31
        LDA ($30),Y
        STA V_K
        RTS

; ---- draw the list
DRAW:
""" + _call(OS_TXT_BEGIN) + _puts("D_TITLE", True) + _puts("D_EMPTY") + f"""
        LDA V_NFAV
        BNE DR0
""" + _puts("D_NONE") + _puts("D_NONE2") + f"""
        JMP DR_H
DR0:    LDA V_TOP
        STA V_I
DR_L:   LDA V_I
        CMP V_NFAV
        BCS DR_H
        SEC
        SBC V_TOP
        CMP #{rows}
        BCS DR_H
        LDA V_I
        JSR ENTRY
        LDY #27
DR_C:   LDA ($30),Y
        STA {STRBUF + 2},Y
        DEY
        BPL DR_C
        LDA #32
        STA {STRBUF}
        STA {STRBUF + 1}
        LDA V_I
        CMP V_CUR
        BNE DR_P
        LDA #62                 ; '>'
        STA {STRBUF}
        LDA #$7F
        STA z:$9F
DR_P:   JSR PRINT
        INC V_I
        JMP DR_L
DR_H:   LDA #23
        STA {OS_TXT_Y}
""" + _puts("D_HINT") + """
        LDY #0
""" + _call(OS_REFRESH_NT) + f"""
        RTS

; ---- pointers for T_COPY: A/X = offset
BUF_SRC: CLC
        ADC {BUFP}
        STA z:$9A
        TXA
        ADC {BUFP}+1
        STA z:$9B
        RTS
BUF_DST: CLC
        ADC {BUFP}
        STA z:$9C
        TXA
        ADC {BUFP}+1
        STA z:$9D
        RTS
REC_SRC: CLC
        ADC {REC_PTR}
        STA z:$9A
        TXA
        ADC {REC_PTR}+1
        STA z:$9B
        RTS
REC_DST: CLC
        ADC {REC_PTR}
        STA z:$9C
        TXA
        ADC {REC_PTR}+1
        STA z:$9D
        RTS

; ---- F_OPEN: find EDFC/FAVS.DAT (V_MODE 0) or RECENTS.DAT (1), allocate the sector
;      buffer. C=1 on failure
F_OPEN: LDX #11
FO_N:   LDA D_FNAME,X
        STA {FNAME},X
        DEX
        BPL FO_N
        LDA #0
        STA {FCL}
        STA {FCL}+1
        STA {FCL}+2
        STA {FCL}+3
""" + _push32(EDFC_CLUSTER) + _pushptr(FNAME) + f"""
        JSR {PUSH0}
""" + _pushptr(FCL) + _call(OS_FIND_FILE, FCL & 0xFF, FCL >> 8) + f"""
        BNE FO_F
        LDA {FCL}
        ORA {FCL}+1
        ORA {FCL}+2
        ORA {FCL}+3
        BEQ FO_F
        LDA {OS_HEAP_TOP}+1     ; heap must have room below $7E00 (signature at $7FF8)
        CMP #$7C
        BCS FO_F
        LDA #0
        LDX #2
        JSR {PUSHAX}
""" + _call(OS_MALLOC, 0, 2) + f"""
        STA {BUFP}
        STX {BUFP}+1
        CLC
        RTS
FO_F:   JSR REOPEN
        SEC
        RTS

F_CLOSE: LDA #0
        LDX #2
        JSR {PUSHAX}
""" + _call(OS_FREE, 0, 2) + f"""
        JMP REOPEN

; ---- F_LBA: V_LBA = LBA of sector V_K of the file. C=1 on failure
F_LBA:  LDX #3
FL_C:   LDA {FCL},X
        STA {CLW},X
        DEX
        BPL FL_C
        LDA V_K
        STA V_I
FL_W:   LDA V_I
        CMP {SPC}
        BCC FL_D
        SEC
        SBC {SPC}
        STA V_I
""" + _pushptr(CLW) + _call(OS_NEXTCL, CLW & 0xFF, CLW >> 8) + f"""
        BNE FL_F
        JMP FL_W
FL_D:
""" + _push32(CLW) + _call(OS_CL2LBA) + f"""
        CLC
        ADC V_I
        STA V_LBA
        TXA
        ADC #0
        STA V_LBA+1
        LDA z:$2A
        ADC #0
        STA V_LBA+2
        LDA z:$2B
        ADC #0
        STA V_LBA+3
        CLC
        RTS
FL_F:   SEC
        RTS

; ---- F_READ: sector V_K -> buffer, checks slot byte + magic, TMP4 = slot cluster
F_READ: JSR F_LBA
        BCS FR_R
""" + _push32("V_LBA") + f"""
        LDA {BUFP}
        LDX {BUFP}+1
        JSR {PUSHAX}
        LDA #1
        JSR {PUSHA}
""" + _call(OS_READ_SECT, 1) + f"""
        BNE FR_F
        LDA #{FAV_TAIL & 0xFF}
        LDX #{FAV_TAIL >> 8}
        JSR BUF_SRC
        LDA #{TMPT & 0xFF}
        STA z:$9C
        LDA #{TMPT >> 8}
        STA z:$9D
        LDA #9
        STA CNT
        JSR T_COPY
        LDA {TMPT}
        CMP V_K
        BNE FR_F
        LDX #7
FR_M:   LDA {TMPT + 1},X
        CMP D_MAGIC,X
        BNE FR_F
        DEX
        BPL FR_M
        LDA #0
        TAX
        JSR BUF_SRC
        LDA #{TMP4 & 0xFF}
        STA z:$9C
        LDA #{TMP4 >> 8}
        STA z:$9D
        LDA #4
        STA CNT
        JSR T_COPY
        CLC
        RTS
FR_F:   SEC
FR_R:   RTS

; ---- F_WRITE: buffer -> sector V_K (only after F_READ of the same slot)
F_WRITE: JSR F_LBA
        BCS FW_R
        LDA {BUFP}
        LDX {BUFP}+1
        JSR {PUSHAX}
        LDA #1
        JSR {PUSHA}
""" + _push32("V_LBA") + _call(OS_WRITE_SECT) + f"""
        BNE FW_F
        CLC
        RTS
FW_F:   SEC
FW_R:   RTS

; ---- F_SCAN: all slots -> cache (name 27 + NUL, counter at 28..30, slot at 31),
;      V_NFAV, V_FREE (first empty or $FF), V_FOUND (slot+1 with cluster RECCL, or 0),
;      V_MAXS (highest counter), V_MINK (slot with the lowest counter). C=1 on failure
F_SCAN: LDA #$FF
        STA V_FREE
""" + ("" if fav else """        STA V_MINS
        STA V_MINS+1
        STA V_MINS+2
""") + """        LDA #0
        STA V_FOUND
        STA V_NFAV
        STA V_K
""" + ("" if fav else """        STA V_MINK
        STA V_MAXS
        STA V_MAXS+1
        STA V_MAXS+2
""") + f"""SC_L:   JSR F_READ
        BCC SC0
        RTS
SC0:    LDA {TMP4}
        ORA {TMP4}+1
        ORA {TMP4}+2
        ORA {TMP4}+3
        BNE SC_U
        LDA V_FREE
        BPL SC_J
        LDA V_K
        STA V_FREE
SC_J:   JMP SC_N
SC_U:   LDX #3
SC_C:   LDA {TMP4},X
        CMP {RECCL},X
        BNE SC_NE
        DEX
        BPL SC_C
        LDX V_K
        INX
        STX V_FOUND
SC_NE:
""" + ("        NOP" + chr(10) if fav else f"""
        LDA #{SEQ_OFF & 0xFF}
        LDX #{SEQ_OFF >> 8}
        JSR BUF_SRC
        LDA #{TMPS & 0xFF}
        STA z:$9C
        LDA #{TMPS >> 8}
        STA z:$9D
        LDA #3
        STA CNT
        JSR T_COPY
        LDA V_MAXS+2            ; counter > max ?
        CMP {TMPS}+2
        BCC SC_GT
        BNE SC_LT
        LDA V_MAXS+1
        CMP {TMPS}+1
        BCC SC_GT
        BNE SC_LT
        LDA V_MAXS
        CMP {TMPS}
        BCS SC_LT
SC_GT:  LDA {TMPS}
        STA V_MAXS
        LDA {TMPS}+1
        STA V_MAXS+1
        LDA {TMPS}+2
        STA V_MAXS+2
SC_LT:  LDA {TMPS}+2            ; counter < min ?
        CMP V_MINS+2
        BCC SC_LO
        BNE SC_NM
        LDA {TMPS}+1
        CMP V_MINS+1
        BCC SC_LO
        BNE SC_NM
        LDA {TMPS}
        CMP V_MINS
        BCS SC_NM
SC_LO:  LDA {TMPS}
        STA V_MINS
        LDA {TMPS}+1
        STA V_MINS+1
        LDA {TMPS}+2
        STA V_MINS+2
        LDA V_K
        STA V_MINK
""") + f"""
SC_NM:  LDA #10
        LDX #0
        JSR BUF_SRC
        LDA #{STRBUF & 0xFF}
        STA z:$9C
        LDA #{STRBUF >> 8}
        STA z:$9D
        LDA #27
        STA CNT
        JSR T_COPY
        LDA V_NFAV
        JSR ENTRY
        LDY #0
SC_CP:  LDA {STRBUF},Y
        STA ($30),Y
        INY
        CPY #27
        BNE SC_CP
        LDA #0
        STA ($30),Y
        INY
        LDA {TMPS}
        STA ($30),Y
        INY
        LDA {TMPS}+1
        STA ($30),Y
        INY
        LDA {TMPS}+2
        STA ($30),Y
        INY
        LDA V_K
        STA ($30),Y
        INC V_NFAV
SC_N:   INC V_K
        LDA V_K
        CMP #{FAV_SLOTS}
        BEQ SC_E
        JMP SC_L
SC_E:   CLC
        RTS

; ---- strings
D_MAGIC: DB {", ".join(str(b) for b in FAV_MAGIC)}
D_EMPTY: DB 0
""" + ("""D_FNAME: DT "FAVS    DAT"
D_TITLE: DT "Favoritos"
D_NONE: DT "Nenhum favorito."
D_NONE2: DT "Use Favoritar no menu do jogo"
D_HINT: DT "SELECT - remover favorito"
D_SAVED: DT "Favorito salvo!"
D_DUP:  DT "J\\x01 est\\x01 nos favoritos."
D_FULL: DT "Lista cheia (32 jogos)."
D_NOFILE: DT "Falta o EDFC/FAVS.DAT"
D_IO:   DT "Erro no EDFC/FAVS.DAT"
""" if fav else """D_FNAME: DT "RECENTS DAT"
D_TITLE: DT "Recentes"
D_NONE: DT "Nenhum jogo recente."
D_NONE2: DT "Os jogos iniciados ficam aqui"
D_HINT: DT "SELECT - remover da lista"
D_NOFILE: DT "Falta o EDFC/RECENTS.DAT"
D_IO:   DT "Erro no EDFC/RECENTS.DAT"
V_SW:   DS 1
V_MINK: DS 1
V_MAXS: DS 3
V_MINS: DS 3
""")
    return s


def entry_listing():
    """ENTRY (A = cache index -> ($30) = B11_CACHE + 32*A): shared, resident."""
    from theme_runtime import B11_CACHE
    return f"""
ENTRY:  PHA
        LSR
        LSR
        LSR
        CLC
        ADC #{B11_CACHE >> 8}
        STA z:$31
        PLA
        AND #7
        ASL
        ASL
        ASL
        ASL
        ASL
        CLC
        ADC #{B11_CACHE & 0xFF}
        STA z:$30
        LDA z:$31
        ADC #0
        STA z:$31
        RTS
"""


def fav_symbols(vars_base):
    return {k: vars_base + v for k, v in VARS_SRC.items()}


def favs_dat():
    """EDFC/FAVS.DAT and EDFC/RECENTS.DAT as shipped: 32 empty slots."""
    out = bytearray()
    for k in range(FAV_SLOTS):
        sec = bytearray(512)
        sec[FAV_TAIL] = k
        sec[FAV_TAIL + 1:FAV_TAIL + 9] = FAV_MAGIC
        out += sec
    return bytes(out)
