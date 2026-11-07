"""
Search the whole card: two overlay modules, chained by the resident code (MMENU):
  EDFC/OVLFIND.BIN  E0 NEWQ     keyboard with an empty query; C=1 = search (query ready)
                    E1 RESULTS  results list; C=1 when one was chosen (the browser opens its
                                folder with the file selected; full redraw), C=0 = back
                    E2 KEYB     keyboard again, query kept
  EDFC/OVLSCAN.BIN  E0 DOSCAN   scan of every folder with a progress screen -> cache, V_NFAV

Keyboard: d-pad moves, confirm types, SELECT erases, START searches, cancel leaves. The query,
its length and the cursor live in cache entry 31 (they survive the module swaps).
Scan: breadth first from the root (cluster 0), EDFC skipped, at most MAXD levels; the folder
queue (ring of QCAP x 4 bytes: cluster 24 bit + depth) is a 512-byte OS heap buffer
(malloc/free, LIFO), so every folder is read exactly once.
  * root: opened with the OS's own $8DA9 (it also knows the FAT16 fixed root), each entry
    read with $923B (name into *$0468, cluster of a folder into DCL)
  * subfolders: their directory sectors are read straight into SBUF ($0500-$06FF, internal
    RAM the OS never uses: the cc65 stack stays above $0700) and parsed here - long names
    from the LFN entries (low byte of each UTF-16 char), else "NAME    EXT" as the OS shows
    it; same filter and index as $8DA9 (no $E5, no '.', no hidden/volume, stops at $FE).
    About 10x faster than $923B per file, which re-reads and re-assembles every entry.
Only names ending in "es"/"ds" (.nes/.fds; longer than NMAX: not checked) are matched:
case-insensitive substring of the first NMAX characters. Up to MAXHITS hits in the bank $0B
cache: name 26 + NUL, depth (27), folder cluster (28-30), file index (31). Cancel stops the
scan and shows what was found. Progress ("Pastas lidas: X de Y", hits) is written straight
to the PPU in vblank (2 rows, 64 bytes, like the OS status-bar upload) once per folder and
per hit. Afterwards the browser folder is reopened. Nothing is written to the card.
Choosing a result opens the folder like the browser ($8DA9 + $C67D) and checks the name at
the stored index with $923B; when it differs, the folder is searched for the name.
"""
from fav_runtime import (_call, _puts, _push32, _pushptr, ROWS, STRBUF, NAMEB,
                         PUSHA, PUSH0, PUSHAX, PUSHEAX,
                         OS_MALLOC, OS_FREE, OS_HEAP_TOP, OS_CL2LBA, OS_NEXTCL, OS_READ_SECT, SPC,
                         OS_TXT_BEGIN, OS_TXT_Y, OS_REFRESH_NT,
                         OS_WAIT_BTN, BTN_CONFIRM, BTN_CANCEL, OS_REDRAW)
from theme_runtime import B11_CACHE
from art_runtime import LIST_FLAGS, OS_OPEN_DIR, BROWSE_DIR, OS_WAIT_VBL

PUSHA0 = 0xF3C6
OS_DIR_ENTRY = 0x923B     # (index16, name16*, cluster32* or 0, 0) -> 0 ok; name -> *name, cluster -> *
OS_LIST_ORDER = 0xC67D    # the browser runs it after $8DA9: display order table *$0466
FAT_TYPE = 0x04A6         # 1 = FAT16 (else FAT32)
DIR_NAME = 0x0468         # u16: OS name buffer (bank 8)
SEL_STACK = 0x0456        # u16: browser selection per folder level (64 B, bank 8)
DEPTH = 0x8275            # browser folder depth
REOPEN_FLAG = 0x04D5      # browser: reopen $8278 at the next loop
JOY = 0x0484
LIST_BASE, LIST_SEL, LIST_COUNT = 0x0466, 0x8276, 0x04B8
PROG = STRBUF             # 64: the two progress rows (STRBUF + the free bytes after it)
DCL = 0x0240              # 4: cluster of the folder entry just read
QBUF = 0x0244             # 2: folder queue (OS heap, bank 8); fav_runtime.BUFP is inside PROG
LBAT = 0x0246             # 4: sector being read
W_CL = 0x024A             # 4: cluster walked with $C404 - it gets a POINTER, read and written with
                          #    bank 8 mapped: it must be internal RAM, never a bank $0B variable
SBUF = 0x0500             # 512: directory sector (internal RAM, unused by the OS)
NMAX = 47                 # name characters compared (NAMEB holds 48)
KEYS = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -.&"
KCOLS, KROWS = 10, 4
QMAX = 18
assert len(KEYS) == KCOLS * KROWS
MAXD = 10                 # folder levels searched below the root
MAXHITS = 31              # cache entry 31 holds the query
V_Q = B11_CACHE + 32 * MAXHITS      # QMAX + 1 bytes, then length and cursor
V_QLEN, V_SKX, V_SKY = V_Q + QMAX + 1, V_Q + QMAX + 2, V_Q + QMAX + 3
assert V_SKY < B11_CACHE + 32 * 32
QCAP = 128                # folder queue entries (512-byte heap buffer)
DS_Y = 3                  # text line of the progress rows
PROG_PPU = 0x2000 + 32 * (DS_Y + 3)   # OS text line y is screen row y + 3
LFN_OFF = [1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30]   # UTF-16 chars of an LFN entry


def module_find(header):
    """keyboard + results (EDFC/OVLFIND.BIN)"""
    rows = ROWS
    return header + f"""
        JMP NEWQ
        JMP RESULTS
        JMP KEYB

NEWQ:   LDA #0
        STA {V_QLEN}
        STA {V_SKX}
        STA {V_SKY}
        STA {V_Q}
KEYB:   JSR KDRAW
        JMP KB_K
KB_D:   JSR KDRAW
KB_K:
""" + _call(OS_WAIT_BTN) + f"""
        STA V_BTN
        AND #$08                ; up
        BEQ KB_1
        LDA {V_SKY}
        BEQ KB_K
        DEC {V_SKY}
        JMP KB_D
KB_1:   LDA V_BTN
        AND #$04                ; down
        BEQ KB_2
        LDA {V_SKY}
        CMP #{KROWS - 1}
        BCS KB_K
        INC {V_SKY}
        JMP KB_D
KB_2:   LDA V_BTN
        AND #$02                ; left (wraps)
        BEQ KB_3
        LDA {V_SKX}
        BNE KB_2A
        LDA #{KCOLS}
KB_2A:  SEC
        SBC #1
        STA {V_SKX}
        JMP KB_D
KB_3:   LDA V_BTN
        AND #$01                ; right (wraps)
        BEQ KB_4
        LDX {V_SKX}
        INX
        CPX #{KCOLS}
        BCC KB_3A
        LDX #0
KB_3A:  STX {V_SKX}
        JMP KB_D
KB_4:   LDA V_BTN
        AND #$20                ; select: erase
        BEQ KB_5
        LDY {V_QLEN}
        BEQ KB_K
        DEY
        STY {V_QLEN}
        LDA #0
        STA {V_Q},Y
        JMP KB_D
KB_5:   LDA V_BTN
        AND #$10                ; start: search (the resident code loads the scan)
        BEQ KB_6
        LDA {V_QLEN}
        BEQ KB_K
        SEC
        RTS
KB_6:   LDA V_BTN
        AND {BTN_CANCEL}
        BEQ KB_7
        CLC
        RTS
KB_7:   LDA V_BTN
        AND {BTN_CONFIRM}
        BNE KB_8
        JMP KB_K
KB_8:   LDY {V_QLEN}
        CPY #{QMAX}
        BCC KB_8A
        JMP KB_K
KB_8A:  LDA {V_SKY}             ; key = row * 10 + col
        ASL
        ASL
        CLC
        ADC {V_SKY}
        ASL
        CLC
        ADC {V_SKX}
        TAX
        LDA D_KEYS,X
        STA {V_Q},Y
        INY
        LDA #0
        STA {V_Q},Y
        STY {V_QLEN}
        JMP KB_D

; ---- keyboard screen
KDRAW:
""" + _call(OS_TXT_BEGIN) + _puts("D_TITLE", True) + _puts("D_EMPTY") + f"""
        LDX #0
QD1:    LDA D_NOME,X
        BEQ QD2
        STA {STRBUF},X
        INX
        BNE QD1
QD2:    LDY #0
QD3:    LDA {V_Q},Y
        BEQ QD4
        STA {STRBUF},X
        INX
        INY
        BNE QD3
QD4:    LDA #95                 ; '_'
        STA {STRBUF},X
        LDA #0
        STA {STRBUF + 1},X
        JSR PRINT
""" + _puts("D_EMPTY") + f"""
        LDA #0
        STA V_I
KR:     LDX #23
        LDA #32
KF:     STA {STRBUF},X
        DEX
        BPL KF
        LDA #0
        STA {STRBUF + 24}
        LDA V_I
        ASL
        ASL
        CLC
        ADC V_I
        ASL
        TAY
        LDX #3
KC:     LDA D_KEYS,Y
        CMP #32
        BNE KC1
        LDA #95                 ; space key shown as '_'
KC1:    STA {STRBUF},X
        INY
        INX
        INX
        CPX #{3 + 2 * KCOLS}
        BNE KC
        LDA V_I
        CMP {V_SKY}
        BNE KP
        LDA {V_SKX}
        ASL
        TAX
        LDA #91                 ; '['
        STA {STRBUF + 2},X
        LDA #93                 ; ']'
        STA {STRBUF + 4},X
KP:     JSR PRINT
""" + _puts("D_EMPTY") + f"""
        INC V_I
        LDA V_I
        CMP #{KROWS}
        BNE KR
        LDA #21
        STA {OS_TXT_Y}
""" + _puts("D_H1") + _puts("D_H2") + """
        LDY #0
""" + _call(OS_REFRESH_NT) + f"""
        RTS

; ---- results list; C=1 when one was chosen (the browser shows it), C=0 = back
RESULTS: LDA V_NFAV
        BNE RS_0
        LDA #D_NOTF & 0xFF
        LDX #D_NOTF >> 8
        JSR SHOWMSG
        CLC
        RTS
RS_0:   LDA #0
        STA V_CUR
        STA V_TOP
RS_D:   JSR RDRAW
RS_K:
""" + _call(OS_WAIT_BTN) + f"""
        STA V_BTN
        AND #$08
        BEQ RS_2
        LDA V_CUR
        BEQ RS_K
        DEC V_CUR
        LDA V_CUR
        CMP V_TOP
        BCS RS_D
        STA V_TOP
        JMP RS_D
RS_2:   LDA V_BTN
        AND #$04
        BEQ RS_3
        LDX V_CUR
        INX
        CPX V_NFAV
        BCS RS_K
        STX V_CUR
        TXA
        SEC
        SBC V_TOP
        CMP #{rows}
        BCC RS_D
        INC V_TOP
        JMP RS_D
RS_3:   LDA V_BTN
        AND {BTN_CANCEL}
        BEQ RS_4
        CLC
        RTS
RS_4:   LDA V_BTN
        AND {BTN_CONFIRM}
        BNE RS_5
        JMP RS_K
RS_5:   LDA V_CUR
        JSR ENTRY
        LDY #27
        LDA ($30),Y
        STA V_SP                ; folder depth
        INY
        LDA ($30),Y
        STA {BROWSE_DIR}
        INY
        LDA ($30),Y
        STA {BROWSE_DIR}+1
        INY
        LDA ($30),Y
        STA {BROWSE_DIR}+2
        INY
        LDA ($30),Y
        STA V_QC                ; file index
        STA V_PL
        LDA #0
        STA {BROWSE_DIR}+3
        STA {REOPEN_FLAG}
        JSR REOPEN              ; open it as the browser does: $8DA9, then $C67D
        LDY #0
""" + _call(OS_LIST_ORDER) + f"""
        LDA V_SP                ; browser depth; parent selections = 0 (going back works)
        STA {DEPTH}
        BEQ RV_0
        STA CNT
        LDA #0
        TAX
RZ:     STA {STRBUF},X
        INX
        CPX CNT
        BNE RZ
        LDA #{STRBUF & 0xFF}
        STA z:$9A
        LDA #{STRBUF >> 8}
        STA z:$9B
        LDA {SEL_STACK}
        STA z:$9C
        LDA {SEL_STACK}+1
        STA z:$9D
        JSR T_COPY
; ---- the stored index should hold that name; else look for it in the folder
RV_0:   LDA V_QC
        JSR SAMEN
        BEQ RG_0
        LDA #0
        STA V_QC
RV_L:   LDA V_QC
        CMP {LIST_COUNT}
        BCS RV_N
        JSR SAMEN
        BEQ RG_0
        INC V_QC
        BNE RV_L
RV_N:   LDA V_PL                ; not found: the stored index
        STA V_QC
RG_0:   LDA #0
        STA V_PL
        STA V_PH
RG_L:   LDA {LIST_BASE}
        CLC
        ADC V_PL
        STA z:$30
        LDA {LIST_BASE}+1
        ADC V_PH
        STA z:$31
        JSR T_PEEK
        LDA CLUS
        CMP V_QC
        BEQ RG_F
        INC V_PL
        BNE RG_1
        INC V_PH
RG_1:   LDA V_PL
        CMP {LIST_COUNT}
        LDA V_PH
        SBC {LIST_COUNT}+1
        BCC RG_L
        LDA #0                  ; not there any more: top of the folder
        STA V_PL
        STA V_PH
RG_F:   LDA V_PL
        STA {LIST_SEL}
        LDA V_PH
        STA {LIST_SEL}+1
        LDA #1
        STA {OS_REDRAW}
        SEC
        RTS

; ---- SAMEN: A = file index of the open folder -> Z=1 when its name ($923B) is the chosen one
SAMEN:  JSR {PUSHA0}
        LDA {DIR_NAME}
        LDX {DIR_NAME}+1
        JSR {PUSHAX}
        JSR {PUSH0}
        JSR {PUSH0}
""" + _call(OS_DIR_ENTRY, 0, 0) + f"""
        BNE SN_X
        LDA {DIR_NAME}
        STA z:$9A
        LDA {DIR_NAME}+1
        STA z:$9B
        LDA #{NAMEB & 0xFF}
        STA z:$9C
        LDA #{NAMEB >> 8}
        STA z:$9D
        LDA #26
        STA CNT
        JSR T_COPY
        LDA #0
        STA {NAMEB + 26}
        LDA V_CUR
        JSR ENTRY
        LDY #26
SN_C:   LDA ($30),Y
        CMP {NAMEB},Y
        BNE SN_X
        DEY
        BPL SN_C
        LDA #0
SN_X:   RTS

RDRAW:
""" + _call(OS_TXT_BEGIN) + _puts("D_RES", True) + _puts("D_EMPTY") + f"""
        LDA V_TOP
        STA V_I
RD_L:   LDA V_I
        CMP V_NFAV
        BCS RD_H
        SEC
        SBC V_TOP
        CMP #{rows}
        BCS RD_H
        LDA V_I
        JSR ENTRY
        LDY #27
RD_C:   LDA ($30),Y
        STA {STRBUF + 2},Y
        DEY
        BPL RD_C
        LDA #32
        STA {STRBUF}
        STA {STRBUF + 1}
        LDA V_I
        CMP V_CUR
        BNE RD_P
        LDA #62
        STA {STRBUF}
        LDA #$7F
        STA z:$9F
RD_P:   JSR PRINT
        INC V_I
        JMP RD_L
RD_H:   LDA #23
        STA {OS_TXT_Y}
""" + _puts("D_RH") + """
        LDY #0
""" + _call(OS_REFRESH_NT) + f"""
        RTS

D_KEYS: DB {", ".join(str(b) for b in KEYS)}
D_TITLE: DT "Busca"
D_EMPTY: DB 0
D_NOME: DT "Nome: "
D_H1:   DT "START buscar  SELECT apagar"
D_H2:   DT "B digitar     A voltar"
D_RES:  DT "Resultados"
D_RH:   DT "B ir para o jogo   A voltar"
D_NOTF: DT "Nada encontrado."
V_QC:   DS 1
V_PL:   DS 1
V_PH:   DS 1
V_SP:   DS 1
"""


def module_scan(header):
    """scan of every folder with progress (EDFC/OVLSCAN.BIN)"""
    return header + f"""
        JMP DOSCAN

DOSCAN:
""" + _call(OS_TXT_BEGIN) + _puts("D_SCAN", True) + _puts("D_EMPTY") * 4 + _puts("D_CANC") + """
        LDY #0
""" + _call(OS_REFRESH_NT) + f"""
        LDX #63
        LDA #32
DS_B:   STA {PROG},X
        DEX
        BPL DS_B
        LDX #12
DS_T:   LDA D_PAS,X
        STA {PROG + 2},X
        DEX
        BPL DS_T
        LDX #1
DS_T1:  LDA D_DE,X
        STA {PROG + 20},X
        DEX
        BPL DS_T1
        LDX #11
DS_T2:  LDA D_ACH,X
        STA {PROG + 34},X
        DEX
        BPL DS_T2
        LDA #0
        STA V_NFAV
        STA V_AB
        STA V_NDL
        STA V_NDH
        STA V_NTL
        STA V_NTH
        STA V_QH
        STA V_QT
        STA {DCL}
        STA {DCL + 1}
        STA {DCL + 2}
        STA {DCL + 3}
        LDA {OS_HEAP_TOP}+1
        CMP #$7C
        BCC DS_M
        JMP REOPEN              ; no room for the queue (never seen): nothing found
DS_M:   LDA #0
        LDX #2
        JSR {PUSHAX}
""" + _call(OS_MALLOC, 0, 2) + f"""
        STA {QBUF}
        STX {QBUF}+1
        LDA {V_Q}               ; MATCH looks for the first query letter in either case
        STA V_Q0
        CMP #65
        BCC DS_Q0
        CMP #91
        BCS DS_Q0
        ORA #$20
DS_Q0:  STA V_Q0L
        LDA #0
        STA {NAMEB + NMAX}      ; never overwritten by the parser (it writes below NMAX)
        LDA #$FF                ; the root: depth -1 + 1 = 0, total folders 1
        STA V_SP
        JSR ENQ
; ---- next folder from the queue
DS_Q:   LDA V_AB
        BNE DS_EX
        LDA V_QH
        CMP V_QT
        BNE DS_Q1
DS_EX:  JMP DS_E
DS_Q1:  JSR QADDR
        STA z:$30
        STX z:$31
        JSR T_PEEK
        INC V_QH
        LDX #2
DS_Q2:  LDA CLUS,X
        STA V_CL,X
        DEX
        BPL DS_Q2
        LDA #0
        STA V_CL+3
        STA V_I
        LDA CLUS+3
        STA V_SP                ; depth
        INC V_NDL
        BNE DS_Q3
        INC V_NDH
DS_Q3:  JSR PROGS
        LDA V_CL
        ORA V_CL+1
        ORA V_CL+2
        BEQ DS_R
        JSR SUBDIR              ; a subfolder: its sectors, parsed here
        JMP DS_Q
DS_R:   JSR OPENCL              ; the root: through the OS
        BNE DS_Q
DS_L:   LDA {JOY}
        AND {BTN_CANCEL}
        BEQ DS_L0
        INC V_AB                ; cancel: show what was found
DS_L0:  LDA V_AB
        BEQ DS_L1
        JMP DS_Q
DS_L1:  LDA V_I
        CMP {LIST_COUNT}        ; (the OS lists at most $FD entries)
        BCS DS_Q
        LDA {LIST_FLAGS}
        CLC
        ADC V_I
        STA z:$30
        LDA {LIST_FLAGS}+1
        ADC #0
        STA z:$31
        JSR T_PEEK
        LDA CLUS
        STA V_FL                ; bit 7 = folder
        LDA V_I
        JSR {PUSHA0}
        LDA {DIR_NAME}
        LDX {DIR_NAME}+1
        JSR {PUSHAX}
        LDA #{DCL & 0xFF}
        LDX #{DCL >> 8}
        JSR {PUSHAX}
        JSR {PUSH0}
""" + _call(OS_DIR_ENTRY, 0, 0) + f"""
        BNE DS_N
        LDA {DIR_NAME}
        STA z:$9A
        LDA {DIR_NAME}+1
        STA z:$9B
        LDA #{NAMEB & 0xFF}
        STA z:$9C
        LDA #{NAMEB >> 8}
        STA z:$9D
        LDA #{NMAX}
        STA CNT
        JSR T_COPY
        LDA #0
        STA {NAMEB + NMAX}
        LDA V_FL
        BPL DS_F
; ---- folder: queue it (not EDFC)
        LDX #3
DS_D1:  LDA {NAMEB},X
        CMP D_EDFC,X
        BNE DS_D2
        DEX
        BPL DS_D1
        LDA {NAMEB + 4}         ; "EDFC" + NUL, or "EDFC    " (8.3 name, no long name)
        BEQ DS_N
        CMP #32
        BEQ DS_N
DS_D2:  LDA {DCL + 3}
        BNE DS_N
        JSR QFOLD
        JMP DS_N
DS_F:   JSR EXTOK
        BCC DS_N
        JSR HIT
DS_N:   INC V_I
        JMP DS_L
DS_E:   LDA #0
        LDX #2
        JSR {PUSHAX}
""" + _call(OS_FREE, 0, 2) + f"""
        JMP REOPEN              ; the browser folder again

; ---- SUBDIR: folder V_CL straight from its directory sectors
SUBDIR: LDX #3
SB0:    LDA V_CL,X
        STA {W_CL},X
        DEX
        BPL SB0
        LDA #0
        STA V_LV
        STA V_SN
SB_C:   JSR EOC                 ; C=1: end of the cluster chain
        BCC SB_C1
        RTS
SB_C1:
""" + _push32(W_CL) + _call(OS_CL2LBA) + f"""
        STA V_LBA
        STX V_LBA+1
        LDA z:$2A
        STA V_LBA+2
        LDA z:$2B
        STA V_LBA+3
        LDA #0
        STA V_SC
SB_S:   LDA V_LBA
        CLC
        ADC V_SC
        STA {LBAT}
        LDX #1
SB_A:   LDA V_LBA,X
        ADC #0
        STA {LBAT},X
        INX
        CPX #4
        BNE SB_A
""" + _push32(LBAT) + _pushptr(SBUF) + f"""
        LDA #1
        JSR {PUSHA}
""" + _call(OS_READ_SECT, 1) + f"""
        BEQ SB_R
        RTS
SB_R:   LDA #{SBUF & 0xFF}      ; ($30) = current entry
        STA z:$30
        LDA #{SBUF >> 8}
        STA z:$31
SB_E:   LDA {JOY}
        AND {BTN_CANCEL}
        BNE SB_AB
        JSR PENT                ; C=1: end of the folder
        BCS SB_X
        LDA V_AB
        BNE SB_X
        LDA z:$30
        CLC
        ADC #32
        STA z:$30
        BCC SB_E
        INC z:$31
        LDA z:$31
        CMP #{(SBUF + 512) >> 8}
        BNE SB_E
        INC V_SN                ; (a broken chain cannot loop forever)
        BEQ SB_X
        INC V_SC
        LDA V_SC
        CMP {SPC}
        BCS SB_NC
        JMP SB_S
SB_NC:
""" + _pushptr(W_CL) + _call(OS_NEXTCL, W_CL & 255, W_CL >> 8) + f"""
        BNE SB_X
        JMP SB_C
SB_AB:  INC V_AB
SB_X:   RTS

; ---- EOC: C=1 when {W_CL} is not a data cluster (0/1, or end of chain for FAT16/FAT32)
EOC:    LDA {W_CL}+3
        ORA {W_CL}+2
        ORA {W_CL}+1
        BNE EO1
        LDA {W_CL}
        CMP #2
        BCC EO_Y
EO1:    LDA {W_CL}+1
        CMP #$FF
        BNE EO_N
        LDA {W_CL}
        CMP #$F8
        BCC EO_N
        LDA {FAT_TYPE}
        CMP #1
        BEQ EO_Y                ; FAT16: $FFF8+
        LDA {W_CL}+3
        CMP #$0F
        BCC EO_N
        LDA {W_CL}+2
        CMP #$FF
        BNE EO_N
EO_Y:   SEC
        RTS
EO_N:   CLC
        RTS

; ---- PENT: one 32-byte entry; C=1 when the folder ends here
PENT:   LDY #0
        LDA ($30),Y
        BNE PE1
        SEC                     ; first byte 0: no more entries
        RTS
PE_R:   LDA #0                  ; skipped entry (also ends a long name)
        STA V_LV
        CLC
        RTS
PE1:    STA V_B0
        CMP #$E5                ; deleted
        BEQ PE_R
        LDY #11
        LDA ($30),Y
        STA V_AT
        CMP #$0F
        BNE PE_S
        JMP PL1
; ---- the 8.3 entry: same filter as $8DA9
PE_S:   LDA V_B0
        CMP #46                 ; '.', '..'
        BEQ PE_R
        LDA V_AT
        AND #$0A                ; hidden, volume label
        BNE PE_R
        LDA V_LV
        CMP #1
        BEQ PE_N                ; the long name is complete
        LDY #0                  ; else the 11 raw characters "NAME    EXT", as the OS shows it
PS1:    LDA ($30),Y
        STA {NAMEB},Y
        INY
        CPY #11
        BNE PS1
        LDA #0
        STA {NAMEB},Y
PE_N:   LDA #0
        STA V_LV
        LDA V_AT
        AND #$10
        BEQ PE_F
        LDY #21                 ; folder: cluster (24 bit) -> queue
        LDA ($30),Y
        BNE PE_I
        LDY #20
        LDA ($30),Y
        STA {DCL + 2}
        LDY #26
        LDA ($30),Y
        STA {DCL}
        INY
        LDA ($30),Y
        STA {DCL + 1}
        JSR QFOLD
        JMP PE_I
PE_F:   LDY #10
        LDA ($30),Y
        CMP #83                 ; 'S'
        BNE PE_I
        DEY
        LDA ($30),Y
        CMP #69                 ; 'E'
        BEQ PE_H
        CMP #68                 ; 'D'
        BNE PE_I
PE_H:   LDA z:$30               ; HIT moves ($30) to the cache entry
        PHA
        LDA z:$31
        PHA
        JSR HIT
        PLA
        STA z:$31
        PLA
        STA z:$30
PE_I:   INC V_I                 ; the OS index of the next entry
        LDA V_I
        CMP #$FE                ; the OS lists no more
        RTS

; ---- part of a long name: 13 characters at (order - 1) * 13
PL1:    LDA V_B0
        AND #$1F
        STA V_LV
        SEC
        SBC #1
        CMP #4                  ; parts past NMAX characters are not kept
        BCS PL_D0
        STA N_R
        ASL
        ADC N_R
        ASL
        ASL
        ADC N_R
        TAX
        LDA N_R
        CMP #3
        BNE PL_U
        JMP PL_SL               ; 4th part (characters 39..51): only up to NMAX
PL_Z0:  STA {NAMEB},X           ; (branch targets within reach of the unrolled copy)
PL_D0:  CLC
        RTS
PL_U:
        LDY #1
        LDA ($30),Y
        BEQ PL_Z0
        STA {NAMEB},X
        INX
        LDY #3
        LDA ($30),Y
        BEQ PL_Z0
        STA {NAMEB},X
        INX
        LDY #5
        LDA ($30),Y
        BEQ PL_Z0
        STA {NAMEB},X
        INX
        LDY #7
        LDA ($30),Y
        BEQ PL_Z0
        STA {NAMEB},X
        INX
        LDY #9
        LDA ($30),Y
        BEQ PL_Z0
        STA {NAMEB},X
        INX
        LDY #14
        LDA ($30),Y
        BEQ PL_Z0
        STA {NAMEB},X
        INX
        LDY #16
        LDA ($30),Y
        BEQ PL_Z0
        STA {NAMEB},X
        INX
        LDY #18
        LDA ($30),Y
        BEQ PL_Z
        STA {NAMEB},X
        INX
        LDY #20
        LDA ($30),Y
        BEQ PL_Z
        STA {NAMEB},X
        INX
        LDY #22
        LDA ($30),Y
        BEQ PL_Z
        STA {NAMEB},X
        INX
        LDY #24
        LDA ($30),Y
        BEQ PL_Z
        STA {NAMEB},X
        INX
        LDY #28
        LDA ($30),Y
        BEQ PL_Z
        STA {NAMEB},X
        INX
        LDY #30
        LDA ($30),Y
        BEQ PL_Z
        STA {NAMEB},X
        INX
        LDA V_B0                ; the last part (it comes first) ends the name
        AND #$40
        BEQ PL_D
        LDA #0
PL_Z:   STA {NAMEB},X           ; A = 0: terminator
PL_D:   CLC
        RTS
PL_SL:  LDA #0
        STA V_K2
PL2:    LDY V_K2
        LDA D_LFO,Y
        TAY
        LDA ($30),Y
        BEQ PL_Z
        CPX #{NMAX}
        BCS PL_D
        STA {NAMEB},X
        INX
        INC V_K2
        LDA V_K2
        CMP #13
        BNE PL2
        BEQ PL_D

; ---- QFOLD: queue folder DCL unless too deep or the queue is full
QFOLD:  LDA V_SP
        CMP #{MAXD}
        BCS QF_N
        LDA V_QT
        SEC
        SBC V_QH
        BMI QF_N                ; {QCAP} folders waiting
        JMP ENQ
QF_N:   RTS

; ---- HIT: game NAMEB at index V_I (extension already checked): a match goes to the cache;
;      V_AB = 1 when it is full
HIT:    LDA V_NFAV
        CMP #{MAXHITS}
        BCS HT_N
        JSR MATCH
        BCC HT_N
        LDA V_NFAV
        JSR ENTRY
        LDY #25
HT_C:   LDA {NAMEB},Y
        STA ($30),Y
        DEY
        BPL HT_C
        LDY #26
        LDA #0
        STA ($30),Y
        LDX #0
HT_C2:  INY
        LDA V_SP,X              ; depth, cluster (V_SP and V_CL are adjacent)
        STA ($30),Y
        INX
        CPX #4
        BNE HT_C2
        INY
        LDA V_I
        STA ($30),Y
        INC V_NFAV
        JSR PROGS
        LDA V_NFAV
        CMP #{MAXHITS}
        BNE HT_N
        INC V_AB
HT_N:   RTS

; ---- ENQ: DCL (cluster, byte 3 = depth V_SP + 1) -> queue tail; total folders + 1
ENQ:    LDY V_SP
        INY
        STY {DCL + 3}
        LDA V_QT
        JSR QADDR
        STA z:$9C
        STX z:$9D
        LDA #{DCL & 0xFF}
        STA z:$9A
        LDA #{DCL >> 8}
        STA z:$9B
        LDA #4
        STA CNT
        JSR T_COPY
        INC V_QT
        INC V_NTL
        BNE EQ1
        INC V_NTH
EQ1:    RTS

; ---- QADDR: A = queue index -> A/X = QBUF + 4 * (index mod QCAP)
QADDR:  AND #{QCAP - 1}
        LDX #0
        STX N_H
        ASL
        ROL N_H
        ASL
        ROL N_H
        CLC
        ADC {QBUF}
        PHA
        LDA N_H
        ADC {QBUF}+1
        TAX
        PLA
        RTS

; ---- $8DA9(V_CL) as the browser calls it; A = 0 (Z=1) when open
OPENCL: LDA V_CL+2
        STA z:$2A
        LDA V_CL+3
        STA z:$2B
        LDA V_CL
        LDX V_CL+1
        JSR {PUSHEAX}
        LDA #{OS_OPEN_DIR & 0xFF}
        STA T_JSR+1
        LDA #{OS_OPEN_DIR >> 8}
        STA T_JSR+2
        LDA V_CL
        LDX V_CL+1
        JMP T_CALL

; ---- C=1 when NAMEB ends in es/ds (any case); names longer than NMAX are not checked
EXTOK:  LDX #0
EX1:    LDA {NAMEB},X
        BEQ EX2
        INX
        CPX #{NMAX}
        BNE EX1
        SEC
        RTS
EX2:    LDA {NAMEB - 1},X
        AND #$DF
        CMP #83                 ; 'S'
        BNE EX_N
        LDA {NAMEB - 2},X
        AND #$DF
        CMP #69                 ; 'E'
        BEQ EX_Y
        CMP #68                 ; 'D'
        BEQ EX_Y
EX_N:   CLC
        RTS
EX_Y:   SEC
        RTS

; ---- progress rows -> PPU (numbers first); 64 bytes in one vblank like the OS status bar
PROGS:  LDA V_NDL
        LDX V_NDH
        LDY #18
        JSR NUM
        LDA V_NTL
        LDX V_NTH
        LDY #26
        JSR NUM
        LDA V_NFAV
        LDX #0
        LDY #50
        JSR NUM
        LDA #1
        STA z:$A2               ; NMI: no joypad read during the upload (as $8343 does)
        JSR {OS_WAIT_VBL}
        LDA #$80
        STA $2000
        LDA #{PROG_PPU >> 8}
        STA $2006
        LDA #{PROG_PPU & 0xFF}
        STA $2006
        LDX #0
PG1:    LDA {PROG},X
        STA $2007
        INX
        CPX #64
        BNE PG1
        LDA #0
        STA $2005
        STA $2005
        STA z:$A2
        RTS

; ---- A/X = 16-bit value -> decimal digits ending at PROG+Y (right aligned)
NUM:    STA N_L
        STX N_H
NU1:    LDA #0
        STA N_R
        LDX #16
NU2:    ASL N_L
        ROL N_H
        ROL N_R
        LDA N_R
        CMP #10
        BCC NU3
        SBC #10
        STA N_R
        INC N_L
NU3:    DEX
        BNE NU2
        LDA N_R
        ORA #48
        STA {PROG},Y
        DEY
        LDA N_L
        ORA N_H
        BNE NU1
        RTS

; ---- C=1 when the query is a substring of NAMEB (letters compared in upper case)
MATCH:  LDX #0
MT_F:   LDA {NAMEB},X           ; look for the first query letter (either case)
        BEQ MT_N
        CMP V_Q0
        BEQ MT_K
        CMP V_Q0L
        BEQ MT_K
        INX
        BNE MT_F
MT_N:   CLC
        RTS
MT_K:   STX V_MS
        LDY #0
MT_C:   LDA {V_Q},Y
        BEQ MT_Y
        STA V_QC
        LDA {NAMEB},X
        BEQ MT_N
        CMP #97                 ; 'a'..'z' -> upper case
        BCC MT_U
        CMP #123
        BCS MT_U
        AND #$DF
MT_U:   CMP V_QC
        BNE MT_X
        INX
        INY
        BNE MT_C
MT_X:   LDX V_MS
        INX
        JMP MT_F
MT_Y:   SEC
        RTS

D_LFO:  DB {", ".join(str(o) for o in LFN_OFF)}
D_EMPTY: DB 0
D_SCAN: DT "Buscando em todas as pastas"
D_CANC: DT "A cancelar"
D_PAS:  DT "Pastas lidas:"
D_DE:   DT "de"
D_ACH:  DT "Encontrados:"
D_EDFC: DT "EDFC"
V_MS:   DS 1
V_QC:   DS 1
V_Q0:   DS 1
V_Q0L:  DS 1
V_FL:   DS 1
V_AB:   DS 1
V_SP:   DS 1
V_CL:   DS 4
V_NDL:  DS 1
V_NDH:  DS 1
V_NTL:  DS 1
V_NTH:  DS 1
V_QH:   DS 1
V_QT:   DS 1
V_SC:   DS 1
V_SN:   DS 1
V_LV:   DS 1
V_B0:   DS 1
V_AT:   DS 1
V_K2:   DS 1
N_L:    DS 1
N_H:    DS 1
N_R:    DS 1
"""
