"""
Far-entry dispatcher, theme key and favourites (bank $0B, part of the art runtime blob).

Entry: bank-15 stubs H_INFO/H_MENU/H_MAIN/H_SEL/H_FAVADD store an id in FAR_ID,
map bank $0B and jump to DISPATCH (= B11_DISPATCH). Everything returns to the OS
through the RAM trampoline (T_EXIT) with bank 8 mapped again.

Favourites file EDFC/FAVS.DAT (created on the PC, shipped in the release zip;
the console never creates, grows or renames it - no FAT/directory writes):
  32 sectors x 512 bytes, sector K = slot K:
    0..270   copy of the OS "current game" record ($BF16 builds it at *$046A:
             cluster32, ..., long name at +10, $55 $AA at +$10B); cluster 0 = empty
    503      K (slot number)          } checked before every write: a wrong LBA
    504..511 "EDFCFAV1"               } can never touch another file
  LBA of sector K: walk the cluster chain K / spc times ($C404), $969A, + K % spc.

Screens use the OS text routines ($A854 clear + banner, $A864 print line,
$8343 upload, $9F6C wait button); $9F = $7F highlights the next line.
"""
import re

FAV_SLOTS = 32
FAV_TAIL = 503
FAV_MAGIC = b"EDFCFAV1"
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

# page 2 (internal RAM, free; transient)
STRBUF = 0x0200           # 32: text line for $A864
CLW = 0x0220              # 4: cluster walk (written by $C404)
FCL = 0x0224              # 4: FAVS.DAT first cluster (written by $9DC7)
BUFP = 0x0228             # 2: sector buffer (OS heap, bank 8)
TMP4 = 0x022A             # 4: slot cluster read back
FNAME = 0x0230            # 12: "FAVS    DAT"
RECCL = 0x023C            # 4: cluster of the game being added
TMPT = 0x0240             # 9: sector tail read back


def asm_text(src):
    """Tiny text front end for theme_runtime.assemble.
    'LBL: LDA #expr' imm, 'LDA z:expr' zero page, 'LDA (expr),Y' indy,
    'LDA expr,X' abx, 'LDA expr,Y' aby, 'LDA expr' abs, bare mnemonic imp.
    Expressions are Python ($hex allowed); ';' starts a comment."""
    out, pending = [], None
    for raw in src.splitlines():
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
        if arg is None:
            mode, op = "imp", None
        elif mn in ("BCC", "BCS", "BEQ", "BNE", "BMI", "BPL"):
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
    return out


def _call(target, a=0, x=None):
    """trampoline call (bank 8 mapped during the call); args already pushed"""
    s = f"""
        LDA #{target & 0xFF}
        STA T_JSR+1
        LDA #{target >> 8}
        STA T_JSR+2
    """
    if x is not None:
        s += f"    LDX #{x}\n"
    return s + f"    LDA #{a}\n    JSR T_CALL\n"


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


# bank $0B variables (only our code touches them)
VARS_SRC = {
    "V_K": 0, "V_NFAV": 1, "V_CUR": 2, "V_TOP": 3, "V_FREE": 4, "V_FOUND": 5,
    "V_I": 6, "V_BTN": 7, "V_LBA": 8, "V_MSG": 12,
    "V_DIR": 14,        # art_runtime: game menu LEFT/RIGHT ($FE/$FD), 0 = normal entry
}

DATA = [
    ("D_TITLE", b"Favoritos\x00"),
    ("D_EMPTY", b"\x00"),
    ("D_NONE", b"Nenhum favorito.\x00"),
    ("D_NONE2", b"Use Favoritar no menu do jogo\x00"),
    ("D_HINT", b"SELECT - remover favorito\x00"),
    ("D_SAVED", b"Favorito salvo!\x00"),
    ("D_DUP", b"J\x01 est\x01 nos favoritos.\x00"),
    ("D_FULL", b"Lista cheia (32 jogos).\x00"),
    ("D_NOFILE", b"Falta o EDFC/FAVS.DAT\x00"),
    ("D_IO", b"Erro no EDFC/FAVS.DAT\x00"),
    ("D_MAGIC", FAV_MAGIC),
    ("D_FNAME", b"FAVS    DAT\x00"),
]


def fav_source(apply_addr, consts):
    """Assembly text: dispatcher + SELT + MAIN + FAVADD + FAVSCREEN + helpers.
    consts: dict of FAR ids / THEME_ID / NUM_THEMES / B11_CACHE."""
    c = consts
    rows = ROWS
    return f"""
DISPATCH: LDA {c['FAR_ID']}
        BNE DI1
        JMP ART_INFO
DI1:    CMP #1
        BNE DI2
        JMP ART_MENU
DI2:    CMP #2
        BNE DI3
        JMP MAIN
DI3:    CMP #3
        BNE DI4
        JMP SELT
DI4:    JMP FAVADD

; ---- SELECT in the browser: next theme (main thread), full redraw
SELT:   JSR SETUP
        LDA {c['THEME_ID']}
        CLC
        ADC #1
        CMP #{c['NUM_THEMES']}
        BCC SE1
        LDA #0
SE1:    STA V_I
""" + _call(apply_addr) .replace("LDA #0\n    JSR T_CALL", "LDA V_I\n    JSR T_CALL") + f"""
        LDA #1
        STA {OS_REDRAW}
        JSR ZPOUT
        JMP T_EXIT

; ---- main menu dispatch ($CBAF): 0 -> Opcoes (return), 5 -> favourites, else loop
MAIN:   JSR SETUP
        LDY #0
        LDA ($28),Y
        BNE MA1
        JSR ZPOUT
        JMP T_EXIT
MA1:    CMP #5
        BNE MA2
        JSR FAVSCREEN
        LDY #0
""" + _call(OS_RESTORE_SCR) + f"""
MA2:    PLA                     ; return to $CB55 (menu loop) instead of $CBB2
        PLA
        LDA #$CB
        PHA
        LDA #$54
        PHA
        JSR ZPOUT
        JMP T_EXIT

; ---- game menu item "Favoritar"
FAVADD: JSR SETUP
        LDY #0
        LDA ($28),Y             ; file index (menu local)
        JSR {PUSHA}
        LDA {REC_PTR}
        LDX {REC_PTR}+1
        JSR {PUSHAX}
""" + _call(OS_GAME_REC) + f"""
        BEQ FA0
        JMP FA_IO2
FA0:    LDA #0
        TAX
        JSR REC_SRC
        LDA #{RECCL & 0xFF}
        STA z:$9C
        LDA #{RECCL >> 8}
        STA z:$9D
        LDA #4
        STA CNT
        JSR T_COPY
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
        LDA #0
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
        JSR T_COPY
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

; ---- favourites screen (from the main menu)
FAVSCREEN: JSR F_OPEN
        BCC FS0
        LDA #D_NOFILE & 0xFF
        LDX #D_NOFILE >> 8
        JMP SHOWMSG
FS0:    JSR F_SCAN
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
        JMP F_CLOSE             ; back to the main menu
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
        JSR F_SCAN
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
        JMP SHOWMSG
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
        JSR ZPOUT
""" + _call(OS_START_GAME) + f"""
        RTS

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
        LDY #28
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

; ---- full-screen message (A/X = string), waits for a button
SHOWMSG: STA V_MSG
        STX V_MSG+1
""" + _call(OS_TXT_BEGIN) + _puts("D_TITLE", True) + _puts("D_EMPTY") + f"""
        LDA V_MSG
        LDX V_MSG+1
        JSR PUTS
        LDY #0
""" + _call(OS_REFRESH_NT) + _call(OS_WAIT_BTN) + f"""
        RTS

; ---- PUTS: copy a bank $0B string (A/X) to STRBUF and print it
PUTS:   STA PS_L+1
        STX PS_L+2
        LDY #0
PS_L:   LDA $FFFF,Y
        STA {STRBUF},Y
        BEQ PRINT
        INY
        BNE PS_L
PRINT:
""" + _pushptr(STRBUF) + _call(OS_TXT_LINE, STRBUF & 0xFF, STRBUF >> 8) + f"""
        RTS

; ---- ENTRY: A = cache index -> ($30) = B11_CACHE + 32*A
ENTRY:  PHA
        LSR
        LSR
        LSR
        CLC
        ADC #{c['B11_CACHE'] >> 8}
        STA z:$31
        PLA
        AND #7
        ASL
        ASL
        ASL
        ASL
        ASL
        CLC
        ADC #{c['B11_CACHE'] & 0xFF}
        STA z:$30
        LDA z:$31
        ADC #0
        STA z:$31
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

; ---- F_OPEN: find EDFC/FAVS.DAT, allocate the sector buffer. C=1 on failure
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

; ---- F_LBA: V_LBA = LBA of sector V_K of FAVS.DAT. C=1 on failure
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

; ---- F_SCAN: all slots -> name cache, V_NFAV, V_FREE (first empty or $FF),
;      V_FOUND (slot with cluster RECCL). C=1 on failure
F_SCAN: LDA #$FF
        STA V_FREE
        LDA #0
        STA V_FOUND
        STA V_NFAV
        STA V_K
SC_L:   JSR F_READ
        BCC SC0
        RTS
SC0:    LDA {TMP4}
        ORA {TMP4}+1
        ORA {TMP4}+2
        ORA {TMP4}+3
        BNE SC_U
        LDA V_FREE
        BPL SC_N
        LDA V_K
        STA V_FREE
        JMP SC_N
SC_U:   LDX #3
SC_C:   LDA {TMP4},X
        CMP {RECCL},X
        BNE SC_NE
        DEX
        BPL SC_C
        LDA #1
        STA V_FOUND
SC_NE:  LDA #10
        LDX #0
        JSR BUF_SRC
        LDA #{STRBUF & 0xFF}
        STA z:$9C
        LDA #{STRBUF >> 8}
        STA z:$9D
        LDA #28
        STA CNT
        JSR T_COPY
        LDA V_NFAV
        JSR ENTRY
        LDY #0
SC_CP:  LDA {STRBUF},Y
        STA ($30),Y
        INY
        CPY #28
        BNE SC_CP
        LDA #0
        STA ($30),Y
        LDY #31
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
"""


def fav_listing(apply_addr, consts):
    return asm_text(fav_source(apply_addr, consts))


def fav_symbols(vars_base):
    return {k: vars_base + v for k, v in VARS_SRC.items()}


def favs_dat():
    """EDFC/FAVS.DAT as shipped: 32 empty slots."""
    out = bytearray()
    for k in range(FAV_SLOTS):
        sec = bytearray(512)
        sec[FAV_TAIL] = k
        sec[FAV_TAIL + 1:FAV_TAIL + 9] = FAV_MAGIC
        out += sec
    return bytes(out)
