"""
Overlay module BUSCA (EDFC/OVLFIND.BIN): search in the folder the browser shows.
  E0 SEARCH  on-screen keyboard -> name scan -> results; C=1 when a result was chosen
             (the browser selection $8276 is moved to it and a full redraw requested)

Keyboard: d-pad moves, confirm types, SELECT erases, START searches, cancel leaves.
Scan: every entry of the folder (file index 0..count-1, directory order, so the OS
sector cache serves several names per SD read) through $BC71 into a 512-byte OS heap
buffer; case-insensitive substring of the long name (or "NAME    EXT"); up to 32 hits
in the bank $0B cache (name 27 + NUL, file index at 31). Nothing is written to the card.
"""
from fav_runtime import (_call, _puts, ROWS, STRBUF, NAMEB, BUFP, PUSHA, PUSHAX,
                         OS_MALLOC, OS_FREE, OS_HEAP_TOP, OS_TXT_BEGIN, OS_TXT_Y, OS_REFRESH_NT,
                         OS_WAIT_BTN, BTN_CONFIRM, BTN_CANCEL, OS_REDRAW)

OS_GET_ENTRY = 0xBC71
LIST_BASE, LIST_SEL, LIST_COUNT = 0x0466, 0x8276, 0x04B8
KEYS = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -.&"
KCOLS, KROWS = 10, 4
QMAX = 18
assert len(KEYS) == KCOLS * KROWS


def module_find(header):
    rows = ROWS
    return header + f"""
        JMP SEARCH

SEARCH: LDA #0
        STA V_SKX
        STA V_SKY
KB_D:   JSR KDRAW
KB_K:
""" + _call(OS_WAIT_BTN) + f"""
        STA V_BTN
        AND #$08                ; up
        BEQ KB_1
        LDA V_SKY
        BEQ KB_K
        DEC V_SKY
        JMP KB_D
KB_1:   LDA V_BTN
        AND #$04                ; down
        BEQ KB_2
        LDA V_SKY
        CMP #{KROWS - 1}
        BCS KB_K
        INC V_SKY
        JMP KB_D
KB_2:   LDA V_BTN
        AND #$02                ; left (wraps)
        BEQ KB_3
        LDA V_SKX
        BNE KB_2A
        LDA #{KCOLS}
KB_2A:  SEC
        SBC #1
        STA V_SKX
        JMP KB_D
KB_3:   LDA V_BTN
        AND #$01                ; right (wraps)
        BEQ KB_4
        LDX V_SKX
        INX
        CPX #{KCOLS}
        BCC KB_3A
        LDX #0
KB_3A:  STX V_SKX
        JMP KB_D
KB_4:   LDA V_BTN
        AND #$20                ; select: erase
        BEQ KB_5
        LDY V_QLEN
        BEQ KB_K
        DEY
        STY V_QLEN
        LDA #0
        STA V_Q,Y
        JMP KB_D
KB_5:   LDA V_BTN
        AND #$10                ; start: search
        BEQ KB_6
        LDA V_QLEN
        BNE KB_GO
        JMP KB_K
KB_6:   LDA V_BTN
        AND {BTN_CANCEL}
        BEQ KB_7
        CLC
        RTS
KB_7:   LDA V_BTN
        AND {BTN_CONFIRM}
        BNE KB_8
        JMP KB_K
KB_8:   LDY V_QLEN
        CPY #{QMAX}
        BCC KB_8A
        JMP KB_K
KB_8A:  LDA V_SKY               ; key = row * 10 + col
        ASL
        ASL
        CLC
        ADC V_SKY
        ASL
        CLC
        ADC V_SKX
        TAX
        LDA D_KEYS,X
        STA V_Q,Y
        INY
        LDA #0
        STA V_Q,Y
        STY V_QLEN
        JMP KB_D
KB_GO:  JSR DOSCAN
        BCC KB_G1
        LDA #D_ERR & 0xFF
        LDX #D_ERR >> 8
        JSR SHOWMSG
        JMP KB_D
KB_G1:  LDA V_NFAV
        BNE KB_G2
        LDA #D_NOTF & 0xFF
        LDX #D_NOTF >> 8
        JSR SHOWMSG
        JMP KB_D
KB_G2:  JSR RESULTS
        BCS KB_G3
        JMP KB_D
KB_G3:  RTS

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
QD3:    LDA V_Q,Y
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
        CMP V_SKY
        BNE KP
        LDA V_SKX
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

; ---- scan the folder: matches -> cache, V_NFAV = count. C=1 when no buffer
DOSCAN: LDA {OS_HEAP_TOP}+1
        CMP #$7C
        BCC DS_0
        RTS
DS_0:   LDA #0
        LDX #2
        JSR {PUSHAX}
""" + _call(OS_MALLOC, 0, 2) + f"""
        STA {BUFP}
        STX {BUFP}+1
        LDA #0
        STA V_NFAV
        STA V_I
DS_L:   LDA {LIST_COUNT}+1
        BNE DS_1
        LDA V_I
        CMP {LIST_COUNT}
        BCS DS_E
DS_1:   LDA V_I
        JSR {PUSHA}
        LDA {BUFP}
        LDX {BUFP}+1
        JSR {PUSHAX}
        LDA #{OS_GET_ENTRY & 0xFF}
        STA T_JSR+1
        LDA #{OS_GET_ENTRY >> 8}
        STA T_JSR+2
        LDA {BUFP}
        LDX {BUFP}+1
        JSR T_CALL
        BEQ DS_OK
        CMP #$A0
        BNE DS_N
DS_OK:  LDA {BUFP}
        CLC
        ADC #10
        STA z:$9A
        LDA {BUFP}+1
        ADC #0
        STA z:$9B
        LDA #{NAMEB & 0xFF}
        STA z:$9C
        LDA #{NAMEB >> 8}
        STA z:$9D
        LDA #27
        STA CNT
        JSR T_COPY
        LDA #0
        STA {NAMEB + 27}
        JSR MATCH
        BCC DS_N
        LDA V_NFAV
        JSR ENTRY
        LDY #27
DC:     LDA {NAMEB},Y
        STA ($30),Y
        DEY
        BPL DC
        LDY #31
        LDA V_I
        STA ($30),Y
        INC V_NFAV
        LDA V_NFAV
        CMP #32
        BEQ DS_E
DS_N:   INC V_I
        BEQ DS_E
        JMP DS_L
DS_E:   LDA #0
        LDX #2
        JSR {PUSHAX}
""" + _call(OS_FREE, 0, 2) + f"""
        JSR REOPEN
        CLC
        RTS

; ---- C=1 when the query is a substring of NAMEB (letters compared in upper case)
MATCH:  LDA #0
        STA V_MS
MT_S:   LDX V_MS
        LDY #0
MT_C:   LDA V_Q,Y
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
MT_X:   INC V_MS
        JMP MT_S
MT_Y:   SEC
        RTS
MT_N:   CLC
        RTS

; ---- results list; C=1 when one was chosen (browser selection moved to it)
RESULTS: LDA #0
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
        BEQ RS_K
        LDA V_CUR
        JSR ENTRY
        LDY #31
        LDA ($30),Y
        STA V_QC                ; file index
        LDA #0
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
        CLC
        RTS
RG_F:   LDA V_PL
        STA {LIST_SEL}
        LDA V_PH
        STA {LIST_SEL}+1
        LDA #1
        STA {OS_REDRAW}
        SEC
        RTS

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
D_NOTF: DT "Nada encontrado nesta pasta."
D_ERR:  DT "Sem mem\\x07ria para a busca."
V_Q:    DS {QMAX + 1}
V_QLEN: DS 1
V_SKX:  DS 1
V_SKY:  DS 1
V_MS:   DS 1
V_QC:   DS 1
V_PL:   DS 1
V_PH:   DS 1
"""
