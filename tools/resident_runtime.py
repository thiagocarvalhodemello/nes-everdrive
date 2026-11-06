"""
Resident far code in bank $0B (from B11_DISPATCH) + the overlay modules on the SD card.

The bank $0B window is too small for everything, so only this part is resident:
  DISPATCH   far-call entry (bank-15 stubs store an id in FAR_ID and jump here)
  SELT       SELECT in the browser: next theme
  R_INFO/R_MENU   covers -> overlay ART (plain OS behaviour when it is missing)
  R_FAVADD   game menu "Favoritar" -> overlay LISTA
  LAUNCH     "Carregar jogo" ($D5B1): LISTA records the game in RECENTS.DAT, then $B7AC
  START      START in the browser and once after boot: copies the 9-item main menu
             table to page 2 ($0280) and runs the OS main menu ($CB50)
  MMENU      the main menu's $CA0D call ($CB68): 0 Lista de jogos (close), 1 Busca,
             2 Favoritos, 3 Recentes (overlays), 4-8 -> OS items 0-4
  OVL        overlay loader, SETUP/ZPOUT/HIDE/REOPEN/RESTORE, SHOWMSG/PUTS/PRINT, ENTRY
  trampoline image (copied to $0100 by SETUP)

Overlays: EDFC/OVLART.BIN (covers + LEFT/RIGHT), OVLLIST.BIN (favourites + recents),
OVLFIND.BIN (search). Each is assembled for OVL_BASE (first page after the resident
code) and padded to whole sectors; header "O", id, build id (2 bytes, hash of the
resident symbols: an overlay from another build is refused), then a JMP table.
OVL reads the file with the OS ($9541) into CHR $1000 (rendering off, the pattern
table the OS does not use) and copies it from the PPU into bank $0B. Nothing outside
our own bank changes; a missing/old file only disables that feature (message).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from theme_runtime import (assemble, build_runtime, B11_DISPATCH, B11_VARS, B11_VARS2, B11_DATA2,
                           B11_PAL_TABLE, MAIN_MENU_STRS, MAIN_RAM_TABLE, MAIN_ITEMS,
                           FAR_ID, THEME_ID, NUM_THEMES, OS_REDRAW)
import fav_runtime as F
import find_runtime
from art_runtime import (build_tramp, art_module_listing, SAVE3, EDFC_CLUSTER, BROWSE_DIR, OS_OPEN_DIR,
                         OS_WAIT_VBL, OS_WAIT_BTN, OS_MENU, OS_READ_FILE, OS_FIND_FILE,
                         PUSHA, PUSH0, PUSHAX, PUSHEAX)

VARS2 = {"OVL_CUR": 0, "V_MSEL": 1, "OVL_WANT": 2}   # at B11_VARS2 (8 bytes)
OVL_ART, OVL_FAV, OVL_REC, OVL_FIND = 1, 2, 3, 4
OVL_FILES = {OVL_ART: "OVLART  BIN", OVL_FAV: "OVLFAV  BIN", OVL_REC: "OVLREC  BIN", OVL_FIND: "OVLFIND BIN"}
OS_MAIN_MENU, OS_START_GAME, OS_RESTORE_SCR = 0xCB50, 0xB7AC, 0x847C
OS_TXT_BEGIN, OS_REFRESH_NT, OS_TXT_LINE = 0xA854, 0x8343, 0xA864
OVL_END = SAVE3             # module code + variables must end before the SAVE3 scratch


def overlay_file_names():
    return [n[:8].strip() + "." + n[8:] for n in OVL_FILES.values()]


def main_table_data():
    """Main menu table copied to MAIN_RAM_TABLE: title + 9 item pointers + our strings."""
    own = [b"Lista de jogos", b"Busca", b"Favoritos", b"Recentes"]
    ptrs, strs, a = [], bytearray(), MAIN_RAM_TABLE + 2 * (1 + MAIN_ITEMS)
    for t in own:
        ptrs.append(a + len(strs))
        strs += t + b"\x00"
    ptrs += MAIN_MENU_STRS[1:]
    assert len(ptrs) == MAIN_ITEMS
    tab = b"".join(bytes([p & 0xFF, p >> 8]) for p in [MAIN_MENU_STRS[0]] + ptrs)
    data = tab + bytes(strs)
    assert MAIN_RAM_TABLE + len(data) <= 0x0300 and len(data) <= 128
    return data


def resident_source(apply_addr, ovl_base, build):
    _call = F._call
    e = lambda k: ovl_base + 4 + 3 * k
    pages = (0x8000 - ovl_base) >> 8
    nsect = (pages + 1) // 2
    names = b"".join(OVL_FILES[k].encode() for k in sorted(OVL_FILES))
    jt = ", ".join(f"(({x})-1) & 255, (({x})-1) >> 8"
                   for x in ("R_INFO", "R_MENU", "MMENU", "SELT", "R_FAVADD", "START", "LAUNCH"))
    return f"""
DISPATCH: LDA {FAR_ID}
        ASL
        TAX
        LDA DJT+1,X
        PHA
        LDA DJT,X
        PHA
        RTS
DJT:    DB {jt}

; ---- SELECT in the browser: next theme (main thread), full redraw
SELT:   JSR SETUP
        LDA {THEME_ID}
        CLC
        ADC #1
        CMP #{NUM_THEMES}
        BCC SE1
        LDA #0
SE1:    STA V_I
        LDA #{apply_addr & 0xFF}
        STA T_JSR+1
        LDA #{apply_addr >> 8}
        STA T_JSR+2
        LDA V_I
        JSR T_CALL
        LDA #1
        STA {OS_REDRAW}
        JSR ZPOUT
        JMP T_EXIT

; ---- covers: overlay ART, or the plain OS behaviour without it
R_INFO: JSR SETUP
        LDA #{OVL_ART}
        JSR OVL
        BCS RI_F
        JMP {e(0)}
RI_F:   JSR ZPOUT
""" + _call(OS_WAIT_BTN) + f"""
        JMP T_EXIT
R_MENU: JSR SETUP
        LDA #{OVL_ART}
        JSR OVL
        BCS RM_F
        JMP {e(1)}
RM_F:   JSR ZPOUT
""" + _call(OS_MENU, 0, 3) + f"""
        CMP #$FD                ; LEFT/RIGHT without the module: cancel
        BCC RM_X
        LDA #$FF
RM_X:   JMP T_EXIT

; ---- game menu "Favoritar": overlay FAV
R_FAVADD: JSR SETUP
        LDA #{OVL_FAV}
        JSR OVL
        BCS RF_F
        JMP {e(0)}
RF_F:   JSR OVLERR
        LDA #1
        STA {OS_REDRAW}
        JSR ZPOUT
        JMP T_EXIT
OVLERR: LDA #D_OVLERR & 0xFF
        LDX #D_OVLERR >> 8
        JMP SHOWMSG

; ---- "Carregar jogo": recently played list first, then the OS starts the game
LAUNCH: JSR SETUP
        JSR LAUNCH_GO
        JMP T_EXIT
LAUNCH_GO: LDA #{OVL_REC}
        JSR OVL
        BCS LA1
        JSR {e(0)}              ; RECADD (record at *$046A)
LA1:    JSR ZPOUT
""" + _call(OS_START_GAME) + f"""
        RTS

; ---- START in the browser (and once after boot): menu table -> page 2, OS main menu
START:  JSR SETUP
        LDX #{len(main_table_data()) - 1}
ST1:    LDA MT_SRC,X
        STA {MAIN_RAM_TABLE},X
        DEX
        BPL ST1
        LDA #0
        STA V_MSEL
        JSR ZPOUT
        LDY #0
""" + _call(OS_MAIN_MENU) + f"""
        JMP T_EXIT

; ---- main menu ($CB68, its $CA0D call; args pushed): items 0-3 are ours,
;      4-8 are the OS items 0-4 (returned as such: the OS dispatch runs them)
MMENU:  JSR SETUP
MM_A:   LDA V_MSEL
        LDY #0
        STA ($28),Y             ; cursor starts on the last item used
; $CA0D draws item k on row ($0B - count) + 2k ($CA41; $CABF: LDY #2/CLC/TYA/ADC (sp),Y).
; 9 items do not fit its box: rows ($0F - count) + k (LDY #2/TYA/LSR/ADC) during this call
; only (bank 14 is RAM; the other menus keep the original code)
        LDA #$0F
        STA $CA41
        LDA #$98
        STA $CAC1
        LDA #$4A
        STA $CAC2
        JSR ZPOUT
""" + _call(OS_MENU) + f"""
        LDX #$0B
        STX $CA41
        LDX #$18
        STX $CAC1
        LDX #$98
        STX $CAC2
        CMP #$FF
        BEQ MM_X
        STA V_MSEL
        CMP #4
        BCC MM_OWN
        SEC
        SBC #4
MM_X:   JMP T_EXIT
MM_OWN: CMP #0
        BNE MM_1
        LDA #$FF                ; "Lista de jogos": close the menu
        JMP T_EXIT
MM_1:   JSR SETUP
        LDA V_MSEL
        CMP #1
        BNE MM_2
        LDA #{OVL_FIND}
        JSR OVL
        BCS MM_E
        JSR {e(0)}
        BCC MM_R
        JSR ZPOUT               ; a search result was chosen: back to the browser
        LDA #$FF
        JMP T_EXIT
MM_2:   CMP #2
        BNE MM_3
        LDA #{OVL_FAV}
        JSR OVL
        BCS MM_E
        JSR {e(1)}
        BCC MM_R
        JSR LAUNCH_GO           ; a favourite was chosen
        JMP MM_R
MM_3:   LDA #{OVL_REC}
        JSR OVL
        BCS MM_E
        JSR {e(1)}
        JMP MM_R
MM_E:   JSR OVLERR
MM_R:   JSR ZPOUT
        LDY #0
""" + _call(OS_RESTORE_SCR) + f"""
        LDA #{MAIN_RAM_TABLE & 0xFF}    ; $CA0D popped its arguments: push them again
        LDX #{MAIN_RAM_TABLE >> 8}
        JSR {PUSHAX}
        LDA #{MAIN_ITEMS}
        JSR {PUSHA}
        LDA V_MSEL
        JSR {PUSHA}
        JMP MM_A

; ---- OVL: A = module id -> loaded at OVL_BASE. C=1 when missing/invalid.
;      EDFC/<file> ({nsect} sectors) -> CHR $1000 (rendering off) -> bank $0B.
OVL:    CMP OVL_CUR
        BNE OV0
        CLC
        RTS
OV_FX:  JMP OV_F
OV0:    STA OVL_WANT
        TAY
        LDA #0
        STA OVL_CUR
        LDX OVN_IDX-1,Y
        LDY #0
OV1:    LDA OVN,X
        STA NAME11,Y
        INX
        INY
        CPY #11
        BNE OV1
        LDA #0
        STA FILE32
        STA FILE32+1
        STA FILE32+2
        STA FILE32+3
""" + F._push32(EDFC_CLUSTER) + F._pushptr("NAME11") + f"""
        JSR {PUSH0}
""" + F._pushptr("FILE32") + f"""
        LDA #{OS_FIND_FILE & 0xFF}
        STA T_JSR+1
        LDA #{OS_FIND_FILE >> 8}
        STA T_JSR+2
        LDA #FILE32 & 255
        LDX #FILE32 >> 8
        JSR T_CALL
        BNE OV_FX
        LDA FILE32
        ORA FILE32+1
        ORA FILE32+2
        ORA FILE32+3
        BEQ OV_FX
        JSR {OS_WAIT_VBL}
        LDA #0
        STA $2001
""" + F._push32("FILE32") + f"""
        LDA #0
        LDX #$10
        JSR {PUSHAX}
        LDA #{nsect}
        JSR {PUSHA}
""" + _call(OS_READ_FILE, nsect) + f"""
        BNE OV_F
        BIT $2002
        LDA #$10
        STA $2006
        LDA #0
        STA $2006
        LDA $2007
        LDA #{ovl_base & 0xFF}
        STA z:$9A
        LDA #{ovl_base >> 8}
        STA z:$9B
        LDX #{pages}
        LDY #0
OV2:    LDA $2007
        STA ($9A),Y
        INY
        BNE OV2
        INC z:$9B
        DEX
        BNE OV2
        LDA {ovl_base}
        CMP #$4F
        BNE OV_F
        LDA {ovl_base + 1}
        CMP OVL_WANT
        BNE OV_F
        LDA {ovl_base + 2}
        CMP #{build & 0xFF}
        BNE OV_F
        LDA {ovl_base + 3}
        CMP #{build >> 8}
        BNE OV_F
        JSR OV_END
        LDA OVL_WANT
        STA OVL_CUR
        CLC
        RTS
OV_F:   JSR OV_END
        SEC
        RTS
OV_END: JSR REOPEN
        JSR RESTORE
        LDA #$0A
        STA $2001
        RTS
OVN_IDX: DB 0, 11, 22, 33
OVN:    DB {", ".join(str(b) for b in names)}

; ---- CALLI: JSR CALLI / DB target lo, target hi, A -> OS call through the trampoline
;      (X and Y pass through to the OS routine)
CALLI:  STY CI_Y
        PLA                     ; return address = last byte of the JSR
        STA CI_A+1
        CLC
        ADC #3
        TAY
        PLA
        STA CI_A+2
        ADC #0
        PHA                     ; continue after the 3 inline bytes
        TYA
        PHA
        LDY #3
CI_A:   LDA $FFFF,Y
        STA CI_T-1,Y
        DEY
        BNE CI_A
        LDA CI_T
        STA T_JSR+1
        LDA CI_T+1
        STA T_JSR+2
        LDY CI_Y
        LDA CI_T+2
        JMP T_CALL
CI_Y:   DS 1
CI_T:   DS 3

; ---- SETUP: trampoline -> $0100, save zero page scratch
SETUP:  LDX #TLEN-1
CP:     LDA TSRC,X
        STA $0100,X
        DEX
        CPX #$FF
        BNE CP
        LDX #3
ZI:     LDA $9A,X
        STA ZP,X
        DEX
        BPL ZI
        LDA z:$30
        STA ZP+4
        LDA z:$31
        STA ZP+5
        RTS
ZPOUT:  LDX #3
ZO:     LDA ZP,X
        STA $9A,X
        DEX
        BPL ZO
        LDA ZP+4
        STA z:$30
        LDA ZP+5
        STA z:$31
        RTS
HIDE:   JSR {OS_WAIT_VBL}
        LDA #$80
        STA $2000
        LDA #$0A
        STA $2001
        RTS
REOPEN: LDA {BROWSE_DIR + 2}
        STA z:$2A
        LDA {BROWSE_DIR + 3}
        STA z:$2B
        LDA {BROWSE_DIR}
        LDX {BROWSE_DIR + 1}
        JSR {PUSHEAX}
        LDA #{OS_OPEN_DIR & 0xFF}
        STA T_JSR+1
        LDA #{OS_OPEN_DIR >> 8}
        STA T_JSR+2
        LDA {BROWSE_DIR}
        LDX {BROWSE_DIR + 1}
        JMP T_CALL
RESTORE: BIT $2002
        LDA #0
        STA $2006
        STA $2006
        STA $2005
        STA $2005
        JMP {OS_WAIT_VBL}

; ---- full-screen message (A/X = string), waits for a button
SHOWMSG: STA V_MSG
        STX V_MSG+1
""" + _call(OS_TXT_BEGIN) + f"""
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
        STA {F.STRBUF},Y
        BEQ PRINT
        INY
        BNE PS_L
PRINT:
""" + F._pushptr(F.STRBUF) + _call(OS_TXT_LINE, F.STRBUF & 0xFF, F.STRBUF >> 8) + """
        RTS
""" + F.entry_listing()


def _data2_listing():
    """main menu table source + missing-overlay message, in the gap before the palettes"""
    return [("MT_SRC", "DB", "data", main_table_data()),
            ("D_OVLERR", "DB", "data", b"Falta EDFC/OVL*.BIN\x00")]


def _symbols(tlab):
    sym = dict(tlab)
    sym.update(F.fav_symbols(B11_VARS))
    sym.update({k: B11_VARS2 + v for k, v in VARS2.items()})
    return sym


def build_resident(ovl_base=None, build=0):
    """(resident bytes incl. trampoline image, labels, data2 bytes)"""
    tramp, tlab = build_tramp()
    sym = _symbols(tlab)
    d2, d2lab = assemble(_data2_listing(), B11_DATA2)
    assert B11_DATA2 + len(d2) <= B11_PAL_TABLE, "DATA2 overlaps the palettes"
    sym.update(d2lab)
    sym["TLEN"] = len(tramp)
    apply_addr = build_runtime()[1]["APPLY"]
    base = ovl_base or 0x7F00
    for _ in range(2):           # pass 1 finds the size (and OVL_BASE when not given)
        L = F.asm_text(resident_source(apply_addr, base, build))
        code, lab = assemble(L, B11_DISPATCH, dict(sym, TSRC=0))
        tsrc = B11_DISPATCH + len(code)
        code, lab = assemble(L, B11_DISPATCH, dict(sym, TSRC=tsrc))
        end = tsrc + len(tramp)
        if ovl_base is None:
            base = (end + 0xFF) & ~0xFF
    assert lab["DISPATCH"] == B11_DISPATCH
    lab.update(sym)
    lab.update({"TSRC": tsrc, "_RES_END": end, "OVL_BASE": base})
    return code + tramp, lab, d2


def _build_id(lab):
    import hashlib
    h = hashlib.sha1(repr(sorted((k, v) for k, v in lab.items() if isinstance(v, int))).encode()).digest()
    return h[0] | h[1] << 8


def _header(mid, build):
    return f"OVH: DB $4F, {mid}, {build & 0xFF}, {build >> 8}\n"


_cache = []


def build_all():
    """-> (resident bytes, labels, data2 bytes, {file name: overlay bytes})"""
    if _cache:
        return _cache[0]
    _, lab0, _ = build_resident()
    base = lab0["OVL_BASE"]
    _, lab1, _ = build_resident(base, 0)
    build = _build_id(lab1)
    res, lab, d2 = build_resident(base, build)
    assert lab["OVL_BASE"] == base and lab["_RES_END"] <= base
    pages = (0x8000 - base) >> 8
    nsect = (pages + 1) // 2
    mods = {
        OVL_ART: [("OVH", "DB", "data", [0x4F, OVL_ART, build & 0xFF, build >> 8]),
                  (None, "JMP", "abs", "ART_INFO"), (None, "JMP", "abs", "ART_MENU")] + art_module_listing(),
        OVL_FAV: F.asm_text(F.module_list(_header(OVL_FAV, build), 0)),
        OVL_REC: F.asm_text(F.module_list(_header(OVL_REC, build), 1)),
        OVL_FIND: F.asm_text(find_runtime.module_find(_header(OVL_FIND, build))),
    }
    files, sizes, mlabs = {}, {}, {}
    for mid, L in mods.items():
        code, mlab = assemble(L, base, lab)
        name = OVL_FILES[mid]
        fname = name[:8].strip() + "." + name[8:]
        assert base + len(code) <= OVL_END, \
            f"overlay {fname} too big: ends ${base + len(code):04X} > ${OVL_END:04X}"
        files[fname] = code + bytes(nsect * 512 - len(code))
        sizes[fname] = len(code)
        mlabs[fname] = mlab
    lab["_SIZES"], lab["_BUILD"], lab["_MLABS"] = sizes, build, mlabs
    _cache.append((res, lab, d2, files))
    return _cache[0]


def install_into_bank11(b11):
    """Place the resident code (+ DATA2) into a bank $0B image; returns labels."""
    res, lab, d2, files = build_all()
    off = B11_DISPATCH - 0x6000
    assert not any(b11[off:off + len(res)]), "bank $0B area for the resident code is not free"
    b11[off:off + len(res)] = res
    off2 = B11_DATA2 - 0x6000
    assert not any(b11[off2:off2 + len(d2)]), "bank $0B DATA2 area is not free (theme data too big?)"
    b11[off2:off2 + len(d2)] = d2
    return lab


def write_overlays(edfc_dir):
    """EDFC/OVL*.BIN for the current build (must match the OS.BIN built with it)."""
    _, lab, _, files = build_all()
    for name, data in files.items():
        with open(os.path.join(edfc_dir, name), "wb") as f:
            f.write(data)
    return lab


if __name__ == "__main__":
    res, lab, d2, files = build_all()
    print(f"resident ${B11_DISPATCH:04X}..${lab['_RES_END']:04X} ({len(res)} bytes, "
          f"trampoline {len(build_tramp()[0])}), DATA2 {len(d2)} bytes")
    print(f"overlay area ${lab['OVL_BASE']:04X}..${OVL_END:04X} ({OVL_END - lab['OVL_BASE']} bytes), "
          f"build {lab['_BUILD']:04X}")
    for n, sz in lab["_SIZES"].items():
        print(f"  {n:12s} {sz} bytes")
