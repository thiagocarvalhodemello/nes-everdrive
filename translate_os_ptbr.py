import os
import shutil

OS_BIN_PATH = r"C:\Development\nes-everdrive\EDFC\OS.BIN"
OS_BAK_PATH = r"C:\Development\nes-everdrive\EDFC\OS.BIN.bak"
TEST_NES_PATH = r"C:\Development\nes-everdrive\EDFC\OS_PTBR_TEST.nes"

if not os.path.exists(OS_BAK_PATH):
    shutil.copyfile(OS_BIN_PATH, OS_BAK_PATH)
    print(f"Backed up original OS.BIN to {OS_BAK_PATH}")

with open(OS_BAK_PATH, "rb") as f:
    orig_data = bytearray(f.read())

# Extract exact 256-byte BIOS decryptor page k60 from original OS.BIN[0xDB00:0xDC00] ^ 0x7B
k60 = bytes(b ^ 0x7B for b in orig_data[0xDB00:0xDC00])

# Custom accented characters in unused tile slots 0x01..0x13 (and 0x81..0x93 for highlighted text)
# Each glyph is 8 bytes (rows 0..7, MSB = left pixel).
# Notice row 2 is 0x00 (1px clear gap between the 2-row accent on rows 0..1 and the letter body on rows 3..6)!
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

def decrypt_bank(buf, offset, pages=32):
    out = bytearray()
    for p in range(pages):
        for i in range(256):
            out.append(buf[offset + p*256 + i] ^ k60[i] ^ (0x60 + p))
    return out

def encrypt_bank(plain_buf, pages=32):
    out = bytearray(len(plain_buf))
    for p in range(pages):
        for i in range(256):
            out[p*256 + i] = plain_buf[p*256 + i] ^ k60[i] ^ (0x60 + p)
    return out

# 1. Build CHR bank (Bank 0: 0x0000..0x1FFF) with custom accented glyphs
bank0 = bytearray(orig_data[0x0000:0x2000])
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

# 2. Decrypt 32KB OS ROM ($8000..$FFFF)
rom = (
    decrypt_bank(orig_data, 0x6000, 32)
    + orig_data[0x8000:0xC000]
    + decrypt_bank(orig_data, 0xC000, 28)
    + orig_data[0xDC00:0xE000]
)

# 3. Define PT-BR translations keyed by original string CPU address ($F580..$F9CB)
# Note: Non-UI internal strings ($F58A..$F600 except $F580, $F5BD, $F5D9) are kept identical.
TRANSLATIONS = {
    0xF580: "Menu Arquivo",                 # 'File Menu' (box width 16)
    0xF5BD: "carregando...",                # 'loading...'
    0xF5D9: "carregando...",                # 'loading...'
    0xF605: "Carregar Cheats",              # 'Load Cheats' (box width 16)
    0xF611: "Cancelar",                     # 'Cancel'
    0xF618: "Cancelar",                     # 'Cancel'
    0xF61F: "Arq. p/ SRAM",                 # 'File To SRAM'
    0xF62C: "SRAM p/ Arq.",                 # 'SRAM To File'
    0xF639: "Sel. e Iniciar",               # 'Sel. And Start'
    0xF648: "Apenas Selec.",                # 'Select Only'
    0xF654: "Info da ROM",                  # 'Rom Info'
    0xF65D: "Menu Principal",               # 'Main Menu'
    0xF667: "Opções",                       # 'Options'
    0xF66F: "Trapaças",                     # 'Cheats'
    0xF676: "Info Sistema",                 # 'Device Info'
    0xF682: "Info Mappers",                 # 'Mapper Info'
    0xF68E: "Sobre",                        # 'About'
    0xF69D: "Nenhum arquivo",               # 'There are no files'
    0xF6B0: "Info Arquivo",                 # 'File Info'
    0xF6BA: "ROM Inválida",                 # 'Bad ROM'
    0xF6C2: "Imagem FDS",                   # 'FDS Image'
    0xF6CC: "Mapper:",                      # 'Mapper:'
    0xF6D8: "Tam. PRG:",                    # 'PRG Size:'
    0xF6E2: "Tam. CHR:",                    # 'CHR Size:'
    0xF6EC: "Memória:",                     # 'Memory:'
    0xF6F4: "RAM+BAT",                      # 'RAM+BAT'
    0xF6FC: "RAM EX",                       # 'EX RAM'
    0xF703: "NÃO",                          # 'NO'
    0xF706: "Espelho:",                     # 'Mirror:'
    0xF714: "Não Suportado",                # 'Not Supported'
    0xF722: "Suportado!",                   # 'Supported!'
    0xF72D: "Info Sistema",                 # 'Device Info'
    0xF739: "Ver. OS:",                     # 'OS ver:'
    0xF741: "Ver.Bios:",                    # 'Bios ver:'
    0xF74B: "Ver.Cpld:",                    # 'Cpld ver:'
    0xF755: "Data: ",                       # 'Adate:' (max 6 chars in 16-col box)
    0xF764: "Hora: ",                       # 'Atime:'
    0xF772: "Brinquedo de Famicom/NES",     # 'Famicom/NES Toy'
    0xF782: "Desenv. por I. Golubovskiy",   # 'Developed by I. Golubovskiy'
    0xF79F: "Suporte:",                     # 'Support:'
    0xF7CD: "Controles:",                   # 'Control:'
    0xF7D6: "ESQ/DIR - mudar página",       # 'LEFT/RIGHT - switch page'
    0xF7EF: "START - repetir último jogo",  # 'START - reload last game'
    0xF808: "SELECT - menu principal",      # 'SELECT - main menu'
    0xF81B: "B - menu arq. / abrir pasta",  # 'B - file menu / open dir'
    0xF834: "A - voltar",                   # 'A - back'
    0xF83D: "NS:",                          # 'SN:'
    0xF841: "Vol. mix áudio:",              # 'Audio mix vol:'
    0xF850: "Ordenar arqs.:",               # 'File sorting:'
    0xF85E: "Reset p/ jogo:",               # 'Reset to game:'
    0xF86D: "Trocar A/B:",                  # 'Swap A/B:'
    0xF877: "Save State:",                  # 'Save State:'
    0xF883: "Botão Salvar",                 # 'Save State KEY'
    0xF892: "Botão Carregar",               # 'Load State KEY'
    0xF8A1: "Opções",                       # 'Options'
    0xF8A9: "BX",                           # 'LO'
    0xF8AC: "NÃO",                          # 'OFF'
    0xF8B0: "AL",                           # 'HI'
    0xF8B3: "SIM",                          # 'ON '
    0xF8B7: "Aperte 2 Botões",              # 'Push Two Buttons'
    0xF8C8: "Lista de Mappers Suportados",  # 'Supported Mapers List'
    0xF8E3: "Total:",                       # 'Total:'
    0xF8EA: "Códigos Game Genie",           # 'Game Genie Codes'
    0xF8FB: "Use B+Direc. p/ mudar",        # 'Press B+Dpad to change'
    0xF912: "Select: ativar/desat.",        # 'Press select to on/off'
    0xF92B: "Trapaças ativas",              # 'Cheats enabled ' (15 chars)
    0xF93B: "Trapaças desat.",              # 'Cheats disabled' (15 chars)
    0xF94D: "Iniciando OS...",              # 'OS init...'
    0xF958: "Salvando disco FDS...",        # 'Save FDS image...'
    0xF96A: "ERRO: ",                       # 'ERROR:'
    0xF971: "Formato de ROM inválido",      # 'Unknown rom format'
    0xF984: "Nenhum jogo selecionado",      # 'Game is not selected'
    0xF999: "Mapper não suportado",         # 'Mapper is not supported'
    0xF9B1: "Config. restaurada ao padrão", # 'Settings reset to default'
    0xF9CB: "Erro de leitura no SD",        # 'Disk IO error'
}

# Collect all original strings and their references BEFORE modifying rom
orig_strings = []
pos = 0x7580
while pos < 0x79D9:
    end = rom.find(0, pos)
    s_addr = 0x8000 + pos
    raw_bytes = bytes(rom[pos:end])
    orig_strings.append((s_addr, raw_bytes))
    pos = end + 1

# Find all pointer table refs ($FA8D..$FABF) and LDA/LDX refs for each string address
ptr_table_refs = {}
lda_ldx_refs = {}
for s_addr, _ in orig_strings:
    lo, hi = s_addr & 0xFF, s_addr >> 8
    ptrs = []
    for addr in range(0xFA8D, 0xFAC0, 2):
        idx = addr - 0x8000
        if rom[idx] == lo and rom[idx+1] == hi:
            ptrs.append(idx)
    ptr_table_refs[s_addr] = ptrs

    insts = []
    # Only search code regions (exclude $F580..$FBFF string/data region)
    for idx in range(0, 0x7580):
        if rom[idx] == 0xA9 and rom[idx+1] == lo and rom[idx+2] == 0xA2 and rom[idx+3] == hi:
            insts.append(idx)
    lda_ldx_refs[s_addr] = insts

# Keep $F58A..$F604 (RLDUTEBA..edfc, save, maps, MAPROUT BIN, FPGA, NES, HVC, FDS, FAT, .NES..TXT) fixed in-place,
# EXCEPT $F5BD ('loading...') and $F5D9 ('loading...') which can be placed in the main string pool!
FIXED_ADDRS = {
    0xF58A, 0xF5A7, 0xF5AC, 0xF5B1, 0xF5C8, 0xF5CD, 0xF5D1, 0xF5D5,
    0xF5E4, 0xF5E8, 0xF5EC, 0xF5F1, 0xF5F6, 0xF5FB, 0xF600
}

# Clear movable string regions:
# Region 1: $F605..$F9D8 (979 bytes)
# Region 2: $FAE4..$FBFF (284 bytes, right after DATA segment at $F9DA..$FAE3!)
for i in range(0x7605, 0x79D9):
    rom[i] = 0
for i in range(0x7AE4, 0x7C00):
    rom[i] = 0

cur_r1 = 0x7605
end_r1 = 0x79D9
cur_r2 = 0x7AE4
end_r2 = 0x7C00

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
        rom[cur_r1:cur_r1+len(encoded)] = encoded
        new_addrs[s_addr] = 0x8000 + cur_r1
        cur_r1 += len(encoded)
    elif cur_r2 + len(encoded) <= end_r2:
        rom[cur_r2:cur_r2+len(encoded)] = encoded
        new_addrs[s_addr] = 0x8000 + cur_r2
        cur_r2 += len(encoded)
    else:
        raise RuntimeError(f"Out of string space for ${s_addr:04X}!")

print(f"Region 1 ($F605..$F9D8) used: {cur_r1 - 0x7605}/{end_r1 - 0x7605} bytes")
print(f"Region 2 ($FAE4..$FBFF) used: {cur_r2 - 0x7AE4}/{end_r2 - 0x7AE4} bytes")

# Update all pointer table references and LDA/LDX instruction references
for s_addr, new_addr in new_addrs.items():
    lo, hi = new_addr & 0xFF, new_addr >> 8
    for idx in ptr_table_refs[s_addr]:
        rom[idx] = lo
        rom[idx+1] = hi
    for idx in lda_ldx_refs[s_addr]:
        rom[idx+1] = lo
        rom[idx+3] = hi

# Center "Códigos Game Genie" (18 chars -> x = (32 - 18)//2 = 7 instead of 8 at $855C)
assert rom[0x855B - 0x8000] == 0xA9 and rom[0x855C - 0x8000] == 0x08
rom[0x855C - 0x8000] = 0x07

# Center "ROM Inválida" (12 chars -> x = (32 - 12)//2 = 10 instead of 12 at $CD96)
assert rom[0xCD95 - 0x8000] == 0xA9 and rom[0xCD96 - 0x8000] == 0x0C
rom[0xCD96 - 0x8000] = 0x0A

# Center "ERRO: " + hex code at x = 11 (already x=11, "ERRO: A7" is 8 chars, centered!)

# 4. Re-encrypt OS.BIN for real EverDrive N8 hardware
# Note: byte 0 of 0x6000 ($8000) in plaintext before encryption is 0x60 (since BIOS k60 writes 0x78 to $8000 after decryption)
rom_for_edfc = bytearray(rom)
rom_for_edfc[0] = 0x60

new_os_bin = bytearray(0xE000)
new_os_bin[0x0000:0x2000] = bank0                        # Bank 0: CHR font (with PT-BR accents) + Save State handler
new_os_bin[0x2000:0x4000] = orig_data[0x2000:0x4000]     # Bank 1: FDS BIOS (encrypted)
new_os_bin[0x4000:0x6000] = orig_data[0x4000:0x6000]     # Bank 2: Zeros
new_os_bin[0x6000:0x8000] = encrypt_bank(rom_for_edfc[0x0000:0x2000], 32)  # Bank 3: $8000..$9FFF (encrypted)
new_os_bin[0x8000:0xC000] = rom_for_edfc[0x2000:0x6000]  # Banks 4-5: $A000..$DFFF (plain)
new_os_bin[0xC000:0xDC00] = encrypt_bank(rom_for_edfc[0x6000:0x7C00], 28)  # Bank 6: $E000..$FBFF (encrypted)
new_os_bin[0xDC00:0xE000] = rom_for_edfc[0x7C00:0x8000]  # Bank 6 tail: $FC00..$FFFF (vectors)

with open(OS_BIN_PATH, "wb") as f:
    f.write(new_os_bin)
print(f"Wrote translated OS.BIN ({len(new_os_bin)} bytes) to {OS_BIN_PATH}")

# 5. Also build a standalone iNES (.nes) test ROM for Mesen.exe!
# In the standalone .nes ROM, PRG-ROM is 32KB (decrypted rom with $8000 = 0x78 SEI)
# and CHR-ROM is 8KB (bank0 with our PT-BR font)!
nes_prg = bytearray(rom)
nes_prg[0] = 0x78  # SEI at $8000

# Populate $FC00..$FC3F BIOS vector table in nes_prg so Mesen Lua or standalone execution works!
import struct
struct.pack_into("<H", nes_prg, 0x7C00 + 0x00, 0x04E0)  # cmd_resp
struct.pack_into("<H", nes_prg, 0x7C00 + 0x02, 0x04E2)  # usb_char
struct.pack_into("<H", nes_prg, 0x7C00 + 0x04, 0x04E4)  # disk_err
struct.pack_into("<H", nes_prg, 0x7C00 + 0x06, 0x04E6)  # block_len
struct.pack_into("<H", nes_prg, 0x7C00 + 0x08, 0x04E8)  # dst_addr
struct.pack_into("<H", nes_prg, 0x7C00 + 0x10, 0x04EA)  # sd_cmd_buf
for off in range(0x12, 0x40, 2):
    fn_addr = 0xFC00 + 0x40 + off
    struct.pack_into("<H", nes_prg, 0x7C00 + off, fn_addr)
    # Put LDA #$00; STA $04E0; STA $04E4; RTS at each stub!
    # Wait: each stub is 2 bytes apart if we use $FC40 + off, so space them 12 bytes apart at $FC40 + (off - 0x12)*6!
for idx, off in enumerate(range(0x12, 0x40, 2)):
    fn_addr = 0xFC40 + idx * 12
    struct.pack_into("<H", nes_prg, 0x7C00 + off, fn_addr)
    stub = b"\xA9\x00\x8D\xE0\x04\x8D\xE4\x04\x60"  # LDA #0; STA $04E0; STA $04E4; RTS
    nes_prg[fn_addr - 0x8000 : fn_addr - 0x8000 + len(stub)] = stub

adate = (15 << 9) | (9 << 5) | 27
atime = 22 * 60 + 8
struct.pack_into("<H", nes_prg, 0x7FE8, adate)
struct.pack_into("<H", nes_prg, 0x7FEA, atime)
nes_prg[0x7FEC] = 11
struct.pack_into("<H", nes_prg, 0x7FEE, 12345)

# Patch $828C CHR copy in standalone .nes so it doesn't overwrite CHR-RAM with zeroed WRAM when Mapper 0 has no bankswitching:
# At $82DF: LDA #$00; STA $2006; STA $2006 ... -> jump straight to $8307 (enables NMI & rendering) since CHR-ROM already has the font!
nes_prg[0x82D2 - 0x8000 : 0x82D5 - 0x8000] = b"\x4C\x07\x83"  # JMP $8307

# iNES header: 2x 16KB PRG-ROM (32KB), 1x 8KB CHR-ROM, Mapper 0, vertical mirroring + battery WRAM
ines_hdr = b"NES\x1a\x02\x01\x03\x00" + b"\x00" * 8
with open(TEST_NES_PATH, "wb") as f:
    f.write(ines_hdr + nes_prg + bank0)
print(f"Wrote standalone test ROM to {TEST_NES_PATH}")
