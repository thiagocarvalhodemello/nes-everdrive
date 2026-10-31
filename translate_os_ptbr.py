import os
import shutil
import struct

ORIG_OS_BIN = r"EDFC\OS.BIN.orig"
FALLBACK_OS_BIN = r"nesos-v1.26\EDFC\OS.BIN"
OUTPUT_OS_BIN = r"EDFC\OS.BIN"
TEST_NES_PATH = r"EDFC\OS_PTBR_TEST.nes"

if os.path.exists(ORIG_OS_BIN):
    BASE_OS_BIN = ORIG_OS_BIN
elif os.path.exists(FALLBACK_OS_BIN):
    BASE_OS_BIN = FALLBACK_OS_BIN
else:
    raise FileNotFoundError(f"Neither {ORIG_OS_BIN} nor {FALLBACK_OS_BIN} found!")

with open(BASE_OS_BIN, "rb") as f:
    base_data = bytearray(f.read())

assert len(base_data) == 57344, f"Expected 57344 bytes, got {len(base_data)}"

# Custom accented characters in unused tile slots 0x01..0x13 (and 0x81..0x93 for highlighted text)
# Each glyph is 8 bytes (rows 0..7, MSB = left pixel).
# Row 2 is 0x00 (1px clear gap between accent on rows 0..1 and letter body on rows 3..6).
ACCENT_GLYPHS = {
    "á": (0x01, [0x0C, 0x18, 0x00, 0x3C, 0x3E, 0x66, 0x3E, 0x00]),
    "ã": (0x02, [0x32, 0x4C, 0x00, 0x3C, 0x3E, 0x66, 0x3E, 0x00]),
    "â": (0x03, [0x18, 0x24, 0x00, 0x3C, 0x3E, 0x66, 0x3E, 0x00]),
    "é": (0x04, [0x0C, 0x18, 0x00, 0x3C, 0x7E, 0x60, 0x3C, 0x00]),
    "ê": (0x05, [0x18, 0x24, 0x00, 0x3C, 0x7E, 0x60, 0x3C, 0x00]),
    "í": (0x06, [0x0C, 0x18, 0x00, 0x38, 0x18, 0x18, 0x3C, 0x00]),
    "ó": (0x07, [0x0C, 0x18, 0x00, 0x3C, 0x66, 0x66, 0x3C, 0x00]),
    "õ": (0x08, [0x32, 0x4C, 0x00, 0x3C, 0x66, 0x66, 0x3C, 0x00]),
    "ô": (0x09, [0x18, 0x24, 0x00, 0x3C, 0x66, 0x66, 0x3C, 0x00]),
    "ú": (0x0A, [0x0C, 0x18, 0x00, 0x66, 0x66, 0x66, 0x3E, 0x00]),
    "ç": (0x0B, [0x00, 0x3C, 0x60, 0x60, 0x60, 0x3C, 0x0C, 0x18]),
    "Á": (0x0C, [0x0C, 0x18, 0x00, 0x3C, 0x66, 0x7E, 0x66, 0x00]),
    "Ã": (0x0D, [0x32, 0x4C, 0x00, 0x3C, 0x66, 0x7E, 0x66, 0x00]),
    "Ç": (0x0E, [0x00, 0x3C, 0x66, 0x60, 0x66, 0x3C, 0x0C, 0x18]),
    "É": (0x0F, [0x0C, 0x18, 0x00, 0x7E, 0x7C, 0x60, 0x7E, 0x00]),
    "Í": (0x10, [0x0C, 0x18, 0x00, 0x7E, 0x18, 0x18, 0x7E, 0x00]),
    "Ó": (0x11, [0x0C, 0x18, 0x00, 0x3C, 0x66, 0x66, 0x3C, 0x00]),
    "Õ": (0x12, [0x32, 0x4C, 0x00, 0x3C, 0x66, 0x66, 0x3C, 0x00]),
    "Ú": (0x13, [0x0C, 0x18, 0x00, 0x66, 0x66, 0x66, 0x7E, 0x00]),
}

def encode_ptbr(s):
    out = bytearray()
    for ch in s:
        if ch in ACCENT_GLYPHS:
            out.append(ACCENT_GLYPHS[ch][0])
        else:
            out.append(ord(ch))
    return bytes(out)

# 1. Build CHR Bank 0 (0x0000..0x1FFF) with custom accented glyphs
bank0 = bytearray(base_data[0x0000:0x2000])
for ch, (tile_idx, rows) in ACCENT_GLYPHS.items():
    # Normal tile (0x01..0x13): plane 0 = glyph, plane 1 = ~glyph
    t_off = tile_idx * 16
    for r in range(8):
        bank0[t_off + r] = rows[r]
        bank0[t_off + 8 + r] = rows[r] ^ 0xFF
    # Highlighted tile (0x81..0x93): plane 0 = glyph, plane 1 = 0xFF
    h_off = (tile_idx | 0x80) * 16
    for r in range(8):
        bank0[h_off + r] = rows[r]
        bank0[h_off + 8 + r] = 0xFF

# 2. Extract 32KB PRG-ROM ($8000..$FFFF)
# In v1.26 OS.BIN, PRG-ROM is at 0x6000..0xE000 and is completely unencrypted.
prg = bytearray(base_data[0x6000:0xE000])

# 3. Define PT-BR translations keyed by original string CPU address ($F597..$F9EF)
TRANSLATIONS = {
    0xF597: "Menu Arquivo",                 # 'File Menu'
    0xF5D4: "carregando...",                # 'loading...'
    0xF5EB: "carregando...",                # 'loading...'
    0xF617: "Carregar Cheats",              # 'Load Cheats'
    0xF623: "Cancelar",                     # 'Cancel'
    0xF62A: "Cancelar",                     # 'Cancel'
    0xF631: "Arq. p/ SRAM",                 # 'File To SRAM'
    0xF63E: "SRAM p/ Arq.",                 # 'SRAM To File'
    0xF64B: "Sel. e Iniciar",               # 'Sel. And Start'
    0xF65A: "Apenas Selec.",                # 'Select Only'
    0xF666: "Info da ROM",                  # 'Rom Info'
    0xF66F: "Menu Principal",               # 'Main Menu'
    0xF679: "Opções",                       # 'Options'
    0xF681: "Trapaças",                     # 'Cheats'
    0xF688: "Info Sistema",                 # 'Device Info'
    0xF694: "Sobre",                        # 'About'
    0xF6A3: "Nenhum arquivo",               # 'There are no files'
    0xF6B6: "Info Arquivo",                 # 'File Info'
    0xF6C0: "ROM Inválida",                 # 'Bad ROM'
    0xF6C8: "Imagem FDS",                   # 'FDS Image'
    0xF6D2: "Mapper:",                      # 'Mapper:'
    0xF6DA: "Tam. PRG:",                    # 'PRG Size:'
    0xF6E4: "Tam. CHR:",                    # 'CHR Size:'
    0xF6EE: "Memória:",                     # 'Memory:'
    0xF6F6: "RAM+BAT",                      # 'RAM+BAT'
    0xF6FE: "RAM EX",                       # 'EX RAM'
    0xF705: "NÃO",                          # 'NO'
    0xF708: "Espelho:",                     # 'Mirror:'
    0xF718: "Info Sistema",                 # 'Device Info'
    0xF724: "OS: 1.26 PT-BR v1",            # 'OS ver: 1.' (patched to not append decimal 26)
    0xF72F: "Ver.Bios:",                    # 'Bios ver:'
    0xF739: "Ver.Cpld:",                    # 'Cpld ver:'
    0xF743: "Data: ",                       # 'Adate:'
    0xF752: "Hora: ",                       # 'Atime:'
    0xF760: "EDN8 - 1.26 PT-BR v1",         # 'EDN8'
    0xF765: "Desenv. por I. Golubovskiy",   # 'Developed by I. Golubovskiy'
    0xF782: "Agradecimento:",               # 'Special thanks:'
    0xF792: "Núcleo YM2149: Necronomfive",  # 'YM2149 core by Necronomfive'
    0xF7AE: "Núcleo YM2413: Necronomfive",  # 'YM2413 core by Necronomfive'
    0xF7CB: "Suporte:",                     # 'Support:'
    0xF7E7: "Controles:",                   # 'Control:'
    0xF7F0: "ESQ/DIR - mudar página",       # 'LEFT/RIGHT - switch page'
    0xF809: "START - repetir último jogo",  # 'START - reload last game'
    0xF822: "SELECT - menu principal",      # 'SELECT - main menu'
    0xF835: "B - menu arq. / abrir pasta",  # 'B - file menu / open dir'
    0xF84E: "A - voltar",                   # 'A - back'
    0xF857: "NS:",                          # 'SN:'
    0xF85B: "Ordenar arqs.:",               # 'File sorting:'
    0xF869: "Reset p/ jogo:",               # 'Reset to game:'
    0xF878: "Trocar A/B:",                  # 'Swap A/B:'
    0xF882: "Save State:",                  # 'Save State:'
    0xF88E: "Botão Salvar",                 # 'Save State KEY'
    0xF89D: "Botão Carregar",               # 'Load State KEY'
    0xF8AC: "Balanço Áudio",                # 'Audio Balance'
    0xF8BA: "NÃO",                          # 'OFF'
    0xF8BE: "SIM",                          # 'ON '
    0xF8C2: "Opções",                       # 'Options'
    0xF8CE: "Aperte 2 Botões",              # 'Push Two Buttons'
    0xF90E: "Códigos Game Genie",           # 'Game Genie Codes'
    0xF91F: "Use B+Direc. p/ mudar",        # 'Press B+Dpad to change'
    0xF936: "Select: ativar/desat.",        # 'Press select to on/off'
    0xF94F: "Trapaças ativas",              # 'Cheats enabled '
    0xF95F: "Trapaças desat.",              # 'Cheats disabled'
    0xF971: "Iniciando OS...",              # 'OS init...'
    0xF97C: "Salvando disco FDS...",        # 'Save FDS image...'
    0xF98E: "ERRO: ",                       # 'ERROR:'
    0xF995: "Formato de ROM inválido",      # 'Unknown rom format'
    0xF9A8: "Nenhum jogo selecionado",      # 'Game is not selected'
    0xF9BD: "Mapper não suportado",         # 'Mapper is not supported'
    0xF9D5: "Config. restaurada ao padrão", # 'Settings reset to default'
    0xF9EF: "Erro de leitura no SD",        # 'Disk IO error'
}

# Fixed non-UI internal strings in $F5A1..$F616 that must stay at their exact positions
FIXED_ADDRS = {
    0xF5A1, 0xF5BE, 0xF5C3, 0xF5C8, 0xF5DF, 0xF5E3, 0xF5E7,
    0xF5F6, 0xF5FA, 0xF5FE, 0xF603, 0xF608, 0xF60D, 0xF612
}

# Collect all original strings in $F597..$FA00
orig_strings = []
pos = 0x7597
while pos < 0x7A00:
    end = prg.find(0, pos)
    if end == -1 or end >= 0x7A00:
        break
    s_addr = 0x8000 + pos
    raw = bytes(prg[pos:end])
    orig_strings.append((s_addr, raw))
    pos = end + 1

# Map all references in pointer table $FB07..$FB68 and LDA #lo / LDX #hi instructions
ptr_table_refs = {}
lda_ldx_refs = {}
for s_addr, _ in orig_strings:
    lo, hi = s_addr & 0xFF, s_addr >> 8
    # Search pointer table $FB07..$FB68
    ptrs = []
    for addr in range(0xFB07, 0xFB69, 2):
        idx = addr - 0x8000
        if prg[idx] == lo and prg[idx+1] == hi:
            ptrs.append(idx)
    ptr_table_refs[s_addr] = ptrs

    # Search LDA #lo; LDX #hi (A9 lo A2 hi) across code region ($8000..$F597)
    insts = []
    for idx in range(0, 0x7597):
        if prg[idx] == 0xA9 and prg[idx+1] == lo and prg[idx+2] == 0xA2 and prg[idx+3] == hi:
            insts.append(idx)
    lda_ldx_refs[s_addr] = insts

# Clear movable string regions:
# Region 1: $F617..$F9FD (998 bytes)
# Region 2: $FC40..$FDA0 (352 bytes in unused padding area above CC65 DATA copy range $F9FF..$FBFE)
# Note: $F9FF..$FBFE contains CC65 initialized DATA copied to RAM at boot, left completely untouched!
for i in range(0x7617, 0x79FD):
    prg[i] = 0
for i in range(0x7C40, 0x7DA0):
    prg[i] = 0

cur_r1 = 0x7617
end_r1 = 0x79FD
cur_r2 = 0x7C40
end_r2 = 0x7DA0

new_addrs = {}
for s_addr, orig_raw in orig_strings:
    if s_addr in FIXED_ADDRS:
        new_addrs[s_addr] = s_addr
        continue
    if s_addr in TRANSLATIONS:
        encoded = encode_ptbr(TRANSLATIONS[s_addr]) + b"\x00"
    else:
        encoded = orig_raw + b"\x00"

    if cur_r1 + len(encoded) <= end_r1:
        prg[cur_r1:cur_r1+len(encoded)] = encoded
        new_addrs[s_addr] = 0x8000 + cur_r1
        cur_r1 += len(encoded)
    elif cur_r2 + len(encoded) <= end_r2:
        prg[cur_r2:cur_r2+len(encoded)] = encoded
        new_addrs[s_addr] = 0x8000 + cur_r2
        cur_r2 += len(encoded)
    else:
        raise RuntimeError(f"Out of string space for ${s_addr:04X}!")

print(f"Region 1 ($F617..$F9FD) used: {cur_r1 - 0x7617}/{end_r1 - 0x7617} bytes")
print(f"Region 2 ($FC40..$FDA0) used: {cur_r2 - 0x7C40}/{end_r2 - 0x7C40} bytes")

# Update all pointer table and instruction references
for s_addr, new_addr in new_addrs.items():
    lo, hi = new_addr & 0xFF, new_addr >> 8
    for idx in ptr_table_refs[s_addr]:
        prg[idx] = lo
        prg[idx+1] = hi
    for idx in lda_ldx_refs[s_addr]:
        prg[idx+1] = lo
        prg[idx+3] = hi

# 4. Code Patches
# A. Center "Códigos Game Genie" (18 chars -> x = (32 - 18)//2 = 7 instead of 8 at $85B1)
assert prg[0x85B0 - 0x8000] == 0xA9 and prg[0x85B1 - 0x8000] == 0x08
prg[0x85B1 - 0x8000] = 0x07

# B. Center "ROM Inválida" (12 chars -> x = (32 - 12)//2 = 10 instead of 12 at $CECF)
assert prg[0xCECE - 0x8000] == 0xA9 and prg[0xCECF - 0x8000] == 0x0C
prg[0xCECF - 0x8000] = 0x0A

# C. OS version display patch: replace trailing decimal 26 print routine ($D0E1..$D0F4) with NOPs
# Original: AD 05 05 85 30 AD 06 05 85 31 A0 00 B1 30 20 C5 F3 20 43 A7 (20 bytes)
d0e1_idx = 0xD0E1 - 0x8000
assert prg[d0e1_idx:d0e1_idx+3] == b"\xAD\x05\x05"
assert prg[d0e1_idx+17:d0e1_idx+20] == b"\x20\x43\xA7"
prg[d0e1_idx:d0e1_idx+20] = b"\xEA" * 20

# D. Hardware Compatibility Patch: Neutralize writes to registers 0x90 and 0x8F
# In v1.26, Krikzz added writes to new registers:
# - Register 0x90 at $B691 (OS version = 0x1A)
# - Register 0x8F at $B135
# On clone cartridges with 2014/2015 Cyclone II FPGA bitstreams, registers 0x8F and 0x90
# do not exist. Due to 4-bit partial address decoding (reg_addr & 0x0F), writing 0x1A
# to register 0x90 aliases directly to Register 0x80 (PRG/CHR bank 0), clobbering the
# initial bank mapping and causing scrambled tiles/pixels on all booted games!
# Neutralizing these writes with NOPs prevents bank aliasing while preserving full OS functionality.

# Patch Reg 0x90: $B691 (PRG offset 0x3691)
b691_idx = 0xB691 - 0x8000
assert prg[b691_idx:b691_idx+10] == b"\xA9\x90\x8D\x00\x44\xA9\x1A\x8D\x01\x44", "Unexpected bytes at $B691"
prg[b691_idx:b691_idx+10] = b"\xEA" * 10

# Patch Reg 0x8F: $B135 (PRG offset 0x3135)
b135_idx = 0xB135 - 0x8000
assert prg[b135_idx:b135_idx+8] == b"\xA9\x8F\x8D\x00\x44\x8C\x01\x44", "Unexpected bytes at $B135"
prg[b135_idx:b135_idx+8] = b"\xEA" * 8

# 5. Assemble and write translated OS.BIN (57,344 bytes)
new_os_bin = bytearray(0xE000)
new_os_bin[0x0000:0x2000] = bank0                         # Bank 0: Custom PT-BR font + Save State handler
new_os_bin[0x2000:0x4000] = base_data[0x2000:0x4000]      # Bank 1: 0xAA padding
new_os_bin[0x4000:0x6000] = base_data[0x4000:0x6000]      # Bank 2: 0x00 padding
new_os_bin[0x6000:0xE000] = prg                           # Banks 3-6: 32KB PRG-ROM (unencrypted)

with open(OUTPUT_OS_BIN, "wb") as f:
    f.write(new_os_bin)
print(f"Successfully wrote translated OS.BIN ({len(new_os_bin)} bytes) to {OUTPUT_OS_BIN}")

# 6. Build standalone iNES test ROM for Mesen
nes_prg = bytearray(prg)

# Populate $FC00..$FC3F BIOS vector stubs so standalone test ROM can run
struct.pack_into("<H", nes_prg, 0x7C00 + 0x00, 0x04E0)  # cmd_resp
struct.pack_into("<H", nes_prg, 0x7C00 + 0x02, 0x04E2)  # usb_char
struct.pack_into("<H", nes_prg, 0x7C00 + 0x04, 0x04E4)  # disk_err
struct.pack_into("<H", nes_prg, 0x7C00 + 0x06, 0x04E6)  # block_len
struct.pack_into("<H", nes_prg, 0x7C00 + 0x08, 0x04E8)  # dst_addr
struct.pack_into("<H", nes_prg, 0x7C00 + 0x10, 0x04EA)  # sd_cmd_buf
for idx, off in enumerate(range(0x12, 0x40, 2)):
    fn_addr = 0xFC40 + idx * 12
    struct.pack_into("<H", nes_prg, 0x7C00 + off, fn_addr)
    stub = b"\xA9\x00\x8D\xE0\x04\x8D\xE4\x04\x60"  # LDA #0; STA $04E0; STA $04E4; RTS
    nes_prg[fn_addr - 0x8000 : fn_addr - 0x8000 + len(stub)] = stub

# Set mock date/time
adate = (15 << 9) | (9 << 5) | 27
atime = 22 * 60 + 8
struct.pack_into("<H", nes_prg, 0x7FE8, adate)
struct.pack_into("<H", nes_prg, 0x7FEA, atime)
nes_prg[0x7FEC] = 26
struct.pack_into("<H", nes_prg, 0x7FEE, 12345)

# Standalone bypass for CHR overwrite if running on Mapper 0 without bankswitching
# At $82D2: jump straight to $8307
nes_prg[0x82D2 - 0x8000 : 0x82D5 - 0x8000] = b"\x4C\x07\x83"

# iNES header: 32KB PRG, 8KB CHR, Mapper 0, vertical mirroring + battery WRAM
ines_hdr = b"NES\x1a\x02\x01\x03\x00" + b"\x00" * 8
with open(TEST_NES_PATH, "wb") as f:
    f.write(ines_hdr + nes_prg + bank0)
print(f"Successfully wrote standalone test ROM to {TEST_NES_PATH}")
