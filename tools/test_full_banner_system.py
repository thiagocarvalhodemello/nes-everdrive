import os, sys, struct, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edfc_emu import EverDriveN8Emu, save_png, NES_PALETTE
from test_banner_complete import build_banner_packages, THEMES_DEF
from theme_runtime import B11_LOADER
from art_runtime import ART_MAIN, install_into_bank11

# Opcode dictionary for assembler
op_bytes = {
    "PHA": (0x48,), "PLA": (0x68,), "TXA": (0x8A,), "TAX": (0xAA,), "TYA": (0x98,), "TAY": (0xA8,),
    "SEC": (0x38,), "CLC": (0x18,), "DEY": (0x88,), "INY": (0xC8,), "DEX": (0xCA,), "INX": (0xE8,),
    "ASL": (0x0A,), "LSR": (0x4A,), "RTI": (0x40,), "RTS": (0x60,), "TSX": (0xBA,),
    "LDA_IMM": 0xA9, "CMP_IMM": 0xC9, "CPY_IMM": 0xC0, "CPX_IMM": 0xE0, "SBC_IMM": 0xE9, "ADC_IMM": 0x69,
    "LDY_IMM": 0xA0, "LDX_IMM": 0xA2, "EOR_IMM": 0x49,
    "LDA_ABS": 0xAD, "STA_ABS": 0x8D, "CMP_ABS": 0xCD, "INC_ABS": 0xEE, "DEC_ABS": 0xCE, "BIT_ABS": 0x2C,
    "EOR_ABS": 0x4D, "JMP": 0x4C, "JSR": 0x20, "STX_ABS": 0x8E, "STY_ABS": 0x8C, "LDX_ABS": 0xAE, "LDY_ABS": 0xAC,
    "LDA_ZP": 0xA5, "STA_ZP": 0x85, "STX_ZP": 0x86, "STY_ZP": 0x84, "DEC_ZP": 0xC6, "INC_ZP": 0xE6,
    "ADC_ZP": 0x65, "SBC_ZP": 0xE5, "LDX_ZP": 0xA6, "LDY_ZP": 0xA4,
    "LDA_ABX": 0xBD, "STA_ABX": 0x9D, "STA_ABY": 0x99, "LDA_ABY": 0xB9,
    "LDA_INDY": 0xB1, "STA_INDY": 0x91,
    "BEQ": 0xF0, "BNE": 0xD0, "BCC": 0x90, "BCS": 0xB0, "BPL": 0x10, "BMI": 0x30
}

def assemble_listing(listing, base_addr):
    labels = {}
    pc = base_addr
    for lbl, mnem, arg in listing:
        if lbl: labels[lbl] = pc
        if mnem in ("PHA", "PLA", "TXA", "TAX", "TYA", "TAY", "SEC", "CLC", "DEY", "INY", "DEX", "INX", "ASL", "LSR", "RTI", "RTS", "TSX"):
            pc += 1
        elif mnem.endswith("_IMM") or mnem.endswith("_ZP") or mnem.endswith("_INDY") or mnem in ("BEQ", "BNE", "BCC", "BCS", "BPL", "BMI"):
            pc += 2
        else:
            pc += 3

    binary = bytearray()
    pc = base_addr
    for lbl, mnem, arg in listing:
        if mnem in ("PHA", "PLA", "TXA", "TAX", "TYA", "TAY", "SEC", "CLC", "DEY", "INY", "DEX", "INX", "ASL", "LSR", "RTI", "RTS", "TSX"):
            binary.append(op_bytes[mnem][0])
            pc += 1
        elif mnem.endswith("_IMM") or mnem.endswith("_ZP") or mnem.endswith("_INDY"):
            binary.append(op_bytes[mnem])
            binary.append(arg & 0xFF)
            pc += 2
        elif mnem in ("BEQ", "BNE", "BCC", "BCS", "BPL", "BMI"):
            target = labels[arg]
            rel = target - (pc + 2)
            assert -128 <= rel <= 127, f"Branch out of range: {rel} to {arg}"
            binary.append(op_bytes[mnem])
            binary.append(rel & 0xFF)
            pc += 2
        elif mnem in ("JMP", "JSR"):
            target = labels[arg] if isinstance(arg, str) else arg
            binary.append(op_bytes[mnem])
            binary.append(target & 0xFF)
            binary.append((target >> 8) & 0xFF)
            pc += 3
        else:
            binary.append(op_bytes[mnem])
            binary.append(arg & 0xFF)
            binary.append((arg >> 8) & 0xFF)
            pc += 3
    return bytes(binary)

# -----------------------------------------------------------------
# 1. BUILD BANK 0x0B DATA & ROUTINE
# -----------------------------------------------------------------
# Bank $0B layout: theme packages | palette table | theme loader | art runtime
PAL_TABLE = 0x7B90
LOADER = B11_LOADER          # $7BC0

def build_bank11_image(packages):
    b11 = bytearray(0x2000) # 8192 bytes
    
    # Theme package pointers at $6000..$6011 (9 themes * 2 bytes = 18 bytes)
    ptr_offset = 0x0000
    data_offset = 0x0012
    
    ptrs = []
    for pkg in packages:
        ptrs.append(0x6000 + data_offset)
        # 96 bytes nametable
        b11[data_offset : data_offset + 96] = pkg['nametable']
        data_offset += 96
        # 1 byte num_tiles
        num_tiles = len(pkg['tiles'])
        b11[data_offset] = num_tiles
        data_offset += 1
        # Tiles
        for slot, tile_bytes in pkg['tiles']:
            b11[data_offset] = slot
            b11[data_offset + 1 : data_offset + 17] = tile_bytes
            data_offset += 17
            
    for i, ptr in enumerate(ptrs):
        b11[ptr_offset + i*2] = ptr & 0xFF
        b11[ptr_offset + i*2 + 1] = (ptr >> 8) & 0xFF
        
    print(f"Bank 0x0B theme data ends at offset 0x{data_offset:04X} (CPU: ${0x6000+data_offset:04X})")
    assert data_offset <= PAL_TABLE - 0x6000, "Theme data exceeds Bank 0x0B space!"

    # Palette table (36 bytes) right after the theme packages
    pal_table_offset = PAL_TABLE - 0x6000
    pal_table_cpu = PAL_TABLE
    for i, (_, _, _, pal0, _) in enumerate(THEMES_DEF):
        b11[pal_table_offset + i*4 : pal_table_offset + i*4 + 4] = pal0

    # LOAD_THEME routine at LOADER (address shared with theme_runtime.B11_LOADER)
    # A = theme_id
    loader_listing = [
        ("LOAD_THEME", "PHA", None),
        (None, "TXA", None),
        (None, "PHA", None),
        (None, "TYA", None),
        (None, "PHA", None),

        # 1. Disable rendering
        (None, "LDA_IMM", 0x00),
        (None, "STA_ABS", 0x2001),

        # 2. Expand Palette from $7E00 into $827C..$828B
        (None, "TSX", None),
        (None, "LDA_ABX", 0x0103), # theme_id from stack
        (None, "ASL", None),
        (None, "ASL", None),
        (None, "TAX", None),
        (None, "LDA_ABX", pal_table_cpu),     # bd
        (None, "STA_ABS", 0x827C),
        (None, "LDA_ABX", pal_table_cpu + 1), # txt
        (None, "STA_ABS", 0x827D),
        (None, "STA_ABS", 0x8282),
        (None, "LDA_ABX", pal_table_cpu + 2), # hl
        (None, "STA_ABS", 0x827E),
        (None, "STA_ABS", 0x828B),
        (None, "STA_ABS", 0x8283),
        (None, "LDA_ABX", pal_table_cpu + 3), # sh
        (None, "STA_ABS", 0x827F),
        (None, "STA_ABS", 0x828A),
        (None, "STA_ABS", 0x8281),
        (None, "LDA_IMM", 0x0F),               # black
        (None, "STA_ABS", 0x8280),

        # 3. Upload 16 palette bytes from $827C..$828B to PPU $3F00..$3F0F
        (None, "BIT_ABS", 0x2002),
        (None, "LDA_IMM", 0x3F),
        (None, "STA_ABS", 0x2006),
        (None, "LDA_IMM", 0x00),
        (None, "STA_ABS", 0x2006),
        (None, "LDY_IMM", 0x00),
        ("PALLP", "LDA_ABY", 0x827C),
        (None, "STA_ABS", 0x2007),
        (None, "INY", None),
        (None, "CPY_IMM", 0x10),
        (None, "BNE", "PALLP"),

        # 4. Find Theme Package pointer:
        (None, "TSX", None),
        (None, "LDA_ABX", 0x0103), # theme_id from stack
        (None, "ASL", None),
        (None, "TAX", None),
        (None, "LDA_ABX", 0x6000),
        (None, "STA_ZP", 0x9A),
        (None, "LDA_ABX", 0x6001),
        (None, "STA_ZP", 0x9B),

        # 5. Read num_tiles at offset 96:
        (None, "LDY_IMM", 0x60),
        (None, "LDA_INDY", 0x9A),
        (None, "BEQ", "FINISH"),
        (None, "STA_ZP", 0x9C),    # tile count

        # Advance pointer past 97 bytes (96 NT + 1 count):
        (None, "LDA_ZP", 0x9A),
        (None, "CLC", None),
        (None, "ADC_IMM", 0x61),
        (None, "STA_ZP", 0x9A),
        (None, "LDA_ZP", 0x9B),
        (None, "ADC_IMM", 0x00),
        (None, "STA_ZP", 0x9B),

        # 6. Tile Upload Loop
        ("TILE_LP", "LDY_IMM", 0x00),
        (None, "LDA_INDY", 0x9A),  # slot
        (None, "TAX", None),
        (None, "LSR", None),
        (None, "LSR", None),
        (None, "LSR", None),
        (None, "LSR", None),
        (None, "STA_ZP", 0x9D),    # temp PPU addr high
        (None, "TXA", None),
        (None, "ASL", None),
        (None, "ASL", None),
        (None, "ASL", None),
        (None, "ASL", None),       # PPU addr low in A

        # Set PPU address
        (None, "BIT_ABS", 0x2002),
        (None, "LDX_ZP", 0x9D),
        (None, "STX_ABS", 0x2006),
        (None, "STA_ABS", 0x2006),

        # Write 16 bytes to $2007
        (None, "INY", None),
        ("WR16", "LDA_INDY", 0x9A),
        (None, "STA_ABS", 0x2007),
        (None, "INY", None),
        (None, "CPY_IMM", 0x11),
        (None, "BNE", "WR16"),

        # Advance pointer by 17 bytes:
        (None, "LDA_ZP", 0x9A),
        (None, "CLC", None),
        (None, "ADC_IMM", 0x11),
        (None, "STA_ZP", 0x9A),
        (None, "LDA_ZP", 0x9B),
        (None, "ADC_IMM", 0x00),
        (None, "STA_ZP", 0x9B),

        (None, "DEC_ZP", 0x9C),
        (None, "BNE", "TILE_LP"),

        # 7. Reset scroll & restore background rendering (0x0A)
        ("FINISH", "BIT_ABS", 0x2002),
        (None, "LDA_IMM", 0x00),
        (None, "STA_ABS", 0x2005),
        (None, "STA_ABS", 0x2005),
        (None, "STA_ABS", 0x2006),
        (None, "STA_ABS", 0x2006),
        (None, "LDA_IMM", 0x0A),   # Match OS mask 0x0A (sprites OFF, BG ON)
        (None, "STA_ABS", 0x2001),

        (None, "PLA", None),
        (None, "TAY", None),
        (None, "PLA", None),
        (None, "TAX", None),
        (None, "PLA", None),
        (None, "RTS", None)
    ]
    loader_code = assemble_listing(loader_listing, LOADER)
    print(f"Bank 0x0B loader size: {len(loader_code)} bytes (${LOADER:04X}..${LOADER+len(loader_code):04X})")
    assert LOADER + len(loader_code) <= ART_MAIN, "Loader overlaps the art runtime!"
    b11[LOADER - 0x6000 : LOADER - 0x6000 + len(loader_code)] = loader_code
    install_into_bank11(b11)
    return b11

# -----------------------------------------------------------------
# 2. BANK 15 RUNTIME
# -----------------------------------------------------------------
# The bank-15 runtime (NMI hotkey hook, boot restore, banner hook and the
# idle-loop theme apply) lives in theme_runtime.py. The previous version that
# lived here applied the theme from inside the NMI and kept state in the OS
# heap ($7BA6 / $7C00), which corrupted SD transfers. The emulator test is in
# test_theme_safety.py.

if __name__ == "__main__":
    import test_theme_safety
    test_theme_safety.main()
