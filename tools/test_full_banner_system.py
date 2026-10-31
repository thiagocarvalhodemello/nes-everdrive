import os, sys, struct, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edfc_emu import EverDriveN8Emu, save_png, NES_PALETTE
from test_banner_complete import build_banner_packages, THEMES_DEF

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
def build_bank11_image(packages):
    b11 = bytearray(0x2000) # 8192 bytes
    
    ptr_offset = 0x0000
    data_offset = 0x0012 # 9 themes * 2 bytes = 18 bytes
    
    ptrs = []
    for pkg in packages:
        ptrs.append(0x6000 + data_offset)
        # Theme data:
        # 64 bytes nametable
        b11[data_offset : data_offset + 64] = pkg['nametable']
        data_offset += 64
        # 1 byte num_tiles
        num_tiles = len(pkg['tiles'])
        b11[data_offset] = num_tiles
        data_offset += 1
        # Tiles: slot (1 byte) + data (16 bytes)
        for slot, tile_bytes in pkg['tiles']:
            b11[data_offset] = slot
            b11[data_offset + 1 : data_offset + 17] = tile_bytes
            data_offset += 17
            
    for i, ptr in enumerate(ptrs):
        b11[ptr_offset + i*2] = ptr & 0xFF
        b11[ptr_offset + i*2 + 1] = (ptr >> 8) & 0xFF
        
    print(f"Bank 0x0B data ends at offset 0x{data_offset:04X} (CPU: ${0x6000+data_offset:04X})")
    assert data_offset <= 0x1E00, "Theme data exceeds Bank 0x0B space!"
    
    # LOAD_THEME Routine in Bank 0x0B at $7F00 (offset 0x1F00)
    loader_listing = [
        ("LOAD_THEME", "PHA", None),
        (None, "TXA", None),
        (None, "PHA", None),
        (None, "TYA", None),
        (None, "PHA", None),
        
        # 1. Disable rendering
        (None, "LDA_IMM", 0x00),
        (None, "STA_ABS", 0x2001),
        
        # 2. Upload 16 palette bytes from $827C..$828B to PPU $3F00..$3F0F
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
        
        # 3. Find Theme Package pointer:
        (None, "TSX", None),
        (None, "LDA_ABX", 0x0103), # theme_id from stack
        (None, "ASL", None),
        (None, "TAX", None),
        (None, "LDA_ABX", 0x6000),
        (None, "STA_ZP", 0x9A),
        (None, "LDA_ABX", 0x6001),
        (None, "STA_ZP", 0x9B),
        
        # 4. Copy 64 nametable bytes to internal RAM $0180..$01BF
        (None, "LDY_IMM", 0x3F),
        ("CPY_NT", "LDA_INDY", 0x9A),
        (None, "STA_ABY", 0x0180),
        (None, "DEY", None),
        (None, "BPL", "CPY_NT"),
        
        # 5. Read num_tiles at offset 64:
        (None, "LDY_IMM", 0x40),
        (None, "LDA_INDY", 0x9A),
        (None, "BEQ", "FINISH"),
        (None, "STA_ZP", 0x9C),    # tile count
        
        # Advance pointer past 65 bytes (64 NT + 1 count):
        (None, "LDA_ZP", 0x9A),
        (None, "CLC", None),
        (None, "ADC_IMM", 0x41),
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
        
        # 7. Reset scroll & restore rendering
        ("FINISH", "BIT_ABS", 0x2002),
        (None, "LDA_IMM", 0x00),
        (None, "STA_ABS", 0x2005),
        (None, "STA_ABS", 0x2005),
        (None, "STA_ABS", 0x2006),
        (None, "STA_ABS", 0x2006),
        (None, "LDA_IMM", 0x1E),
        (None, "STA_ABS", 0x2001),
        
        (None, "PLA", None),
        (None, "TAY", None),
        (None, "PLA", None),
        (None, "TAX", None),
        (None, "PLA", None),
        (None, "RTS", None)
    ]
    loader_code = assemble_listing(loader_listing, 0x7F00)
    print(f"Bank 0x0B loader size: {len(loader_code)} bytes ($7F00..${0x7F00+len(loader_code):04X})")
    assert len(loader_code) <= 256, "Loader exceeds page!"
    b11[0x1F00 : 0x1F00 + len(loader_code)] = loader_code
    
    return b11

# -----------------------------------------------------------------
# 2. BANK 15 CODE & DATA
# -----------------------------------------------------------------
PREV_BTN_ADDR = 0xFAE4
THEME_ID_ADDR = 0xFAE5
TABLE_ADDR    = 0xFAE6

def build_bank15_payload():
    # Palette table (36 bytes)
    table_bytes = bytearray()
    for _, _, _, pal0, _ in THEMES_DEF:
        table_bytes.extend(pal0)
    assert len(table_bytes) == 36

    # 1. EXPAND_PAL (A = theme_id) - 48 bytes
    EXPAND_ADDR = TABLE_ADDR + len(table_bytes) # $FB0A
    expand_listing = [
        ("EXPAND", "ASL", None),
        (None, "ASL", None),
        (None, "TAX", None),
        
        # Palette 0 & Palette 1 setup
        (None, "LDA_ABX", TABLE_ADDR),     # bd
        (None, "STA_ABS", 0x827C),
        
        (None, "LDA_ABX", TABLE_ADDR + 1), # txt
        (None, "STA_ABS", 0x827D),
        (None, "STA_ABS", 0x8282),         # Pal 1 col 2 (txt)
        
        (None, "LDA_ABX", TABLE_ADDR + 2), # hl
        (None, "STA_ABS", 0x827E),
        (None, "STA_ABS", 0x828B),
        (None, "STA_ABS", 0x8283),         # Pal 1 col 3 (hl)
        
        (None, "LDA_ABX", TABLE_ADDR + 3), # sh
        (None, "STA_ABS", 0x827F),
        (None, "STA_ABS", 0x828A),
        (None, "STA_ABS", 0x8281),         # Pal 1 col 1 (sh)
        
        (None, "LDA_IMM", 0x0F),           # Black
        (None, "STA_ABS", 0x8280),         # Pal 1 col 0
        (None, "RTS", None)
    ]
    expand_code = assemble_listing(expand_listing, EXPAND_ADDR)

    # 2. DRAW_BANNER (Hook 3 at $83F9) - 26 bytes
    BANNER_ADDR = EXPAND_ADDR + len(expand_code)
    banner_listing = [
        ("BANNER", "LDA_IMM", 0x60),
        (None, "STA_ZP", 0x93),
        
        ("DRAW_NT", "LDX_IMM", 0x3F),
        ("NT_LP", "LDA_ABX", 0x7C00),
        (None, "STA_ABX", 0x6000),
        (None, "DEX", None),
        (None, "BPL", "NT_LP"),
        
        # Attributes
        (None, "LDA_IMM", 0x05),
        (None, "LDX_IMM", 0x07),
        ("ATTR_LP", "STA_ABX", 0x63C0),
        (None, "DEX", None),
        (None, "BPL", "ATTR_LP"),
        (None, "RTS", None)
    ]
    banner_code = assemble_listing(banner_listing, BANNER_ADDR)

    # 3. APPLY_THEME (Shared subroutine) - 50 bytes (saving 5 bytes by not re-writing $4400)
    APPLY_ADDR = BANNER_ADDR + len(banner_code)
    apply_listing = [
        ("APPLY", "JSR", EXPAND_ADDR),
        
        # Save to SRAM $7BA6..$7BA9
        (None, "LDA_IMM", 0xED),
        (None, "STA_ABS", 0x7BA6),
        (None, "LDA_IMM", 0xFC),
        (None, "STA_ABS", 0x7BA7),
        (None, "LDA_ABS", THEME_ID_ADDR),
        (None, "STA_ABS", 0x7BA8),
        (None, "EOR_IMM", 0xFF),
        (None, "STA_ABS", 0x7BA9),
        
        # Map Bank 0x0B (reg 0x81 is selected)
        (None, "LDA_IMM", 0x81),
        (None, "STA_ABS", 0x4400),
        (None, "LDA_IMM", 0x0B),
        (None, "STA_ABS", 0x4401),
        
        # Call Bank 0x0B loader
        (None, "LDA_ABS", THEME_ID_ADDR),
        (None, "JSR", 0x7F00),
        
        # Restore Bank 0x08 ($4400 is already 0x81!)
        (None, "LDA_IMM", 0x08),
        (None, "STA_ABS", 0x4401),
        
        # Copy nametable from $0180 to Bank 8 $7C00
        (None, "LDX_IMM", 0x3F),
        ("NT_CPY", "LDA_ABX", 0x0180),
        (None, "STA_ABX", 0x7C00),
        (None, "DEX", None),
        (None, "BPL", "NT_CPY"),
        
        # Jump directly to DRAW_BANNER to copy to $6000, set attributes, and RTS!
        (None, "JMP", BANNER_ADDR)
    ]
    apply_code = assemble_listing(apply_listing, APPLY_ADDR)

    # 4. BOOT_RESTORE (Hook 2 at $828C) - 45 bytes
    BOOT_ADDR = APPLY_ADDR + len(apply_code)
    boot_listing = [
        ("BOOT", "LDA_ABS", 0x7BA6),
        (None, "CMP_IMM", 0xED),
        (None, "BNE", "IS_ZERO"),
        (None, "LDA_ABS", 0x7BA7),
        (None, "CMP_IMM", 0xFC),
        (None, "BNE", "IS_ZERO"),
        (None, "LDA_ABS", 0x7BA8),
        (None, "EOR_ABS", 0x7BA9),
        (None, "CMP_IMM", 0xFF),
        (None, "BNE", "IS_ZERO"),
        
        # Valid theme ID
        (None, "LDA_ABS", 0x7BA8),
        (None, "CMP_IMM", 0x09),
        (None, "BCC", "VALID"),
        
        ("IS_ZERO", "LDA_IMM", 0x00),
        ("VALID", "STA_ABS", THEME_ID_ADDR),
        (None, "JSR", APPLY_ADDR),
        (None, "JSR", 0x83B0),
        (None, "RTS", None)
    ]
    boot_code = assemble_listing(boot_listing, BOOT_ADDR)

    # 5. LIVE_SWITCHER (Hook 1 at $8103) - 62 bytes
    LIVE_ADDR = BOOT_ADDR + len(boot_code)
    live_listing = [
        ("LIVE", "BIT_ABS", 0x2002),
        (None, "PLA", None),
        (None, "PHA", None),
        (None, "TXA", None),
        (None, "PHA", None),
        (None, "TYA", None),
        (None, "PHA", None),
        
        # Check buttons ($0484)
        (None, "LDA_ABS", 0x0484),
        (None, "CMP_ABS", PREV_BTN_ADDR),
        (None, "STA_ABS", PREV_BTN_ADDR),
        (None, "BNE", "CHECK_BTN"),
        
        ("EXIT", "PLA", None),
        (None, "TAY", None),
        (None, "PLA", None),
        (None, "TAX", None),
        (None, "PLA", None),
        (None, "RTI", None),
        
        ("CHECK_BTN", "CMP_IMM", 0x22), # SELECT + LEFT
        (None, "BEQ", "PREV"),
        (None, "CMP_IMM", 0x21),        # SELECT + RIGHT
        (None, "BNE", "EXIT"),
        
        # NEXT:
        (None, "INC_ABS", THEME_ID_ADDR),
        (None, "LDA_ABS", THEME_ID_ADDR),
        (None, "CMP_IMM", 0x09),
        (None, "BCC", "DO_APPLY"),
        (None, "LDA_IMM", 0x00),
        (None, "STA_ABS", THEME_ID_ADDR),
        
        ("DO_APPLY", "JSR", APPLY_ADDR),
        (None, "JMP", "EXIT"),
        
        ("PREV", "DEC_ABS", THEME_ID_ADDR),
        (None, "BPL", "DO_APPLY"),
        (None, "LDA_IMM", 0x08),
        (None, "STA_ABS", THEME_ID_ADDR),
        (None, "BNE", "DO_APPLY")
    ]
    live_code = assemble_listing(live_listing, LIVE_ADDR)

    end_addr = LIVE_ADDR + len(live_code)
    print(f"\nBank 15 Layout Summary:")
    print(f"  Table:         {len(table_bytes)} bytes (${TABLE_ADDR:04X}..${TABLE_ADDR+len(table_bytes):04X})")
    print(f"  Expand helper: {len(expand_code)} bytes (${EXPAND_ADDR:04X}..${EXPAND_ADDR+len(expand_code):04X})")
    print(f"  Draw banner:   {len(banner_code)} bytes (${BANNER_ADDR:04X}..${BANNER_ADDR+len(banner_code):04X})")
    print(f"  Apply theme:   {len(apply_code)} bytes (${APPLY_ADDR:04X}..${APPLY_ADDR+len(apply_code):04X})")
    print(f"  Boot restore:  {len(boot_code)} bytes (${BOOT_ADDR:04X}..${BOOT_ADDR+len(boot_code):04X})")
    print(f"  Live switcher: {len(live_code)} bytes (${LIVE_ADDR:04X}..${LIVE_ADDR+len(live_code):04X})")
    print(f"  End Address:   ${end_addr:04X} (Safety margin before $FC00: {0xFC00 - end_addr} bytes)")
    assert end_addr <= 0xFC00, f"Exceeds $FC00 boundary: ${end_addr:04X}"

    full_payload = bytearray(end_addr - PREV_BTN_ADDR)
    full_payload[0] = 0 # prev_btn
    full_payload[1] = 0 # theme_id
    full_payload[TABLE_ADDR - PREV_BTN_ADDR : TABLE_ADDR - PREV_BTN_ADDR + len(table_bytes)] = table_bytes
    full_payload[EXPAND_ADDR - PREV_BTN_ADDR : EXPAND_ADDR - PREV_BTN_ADDR + len(expand_code)] = expand_code
    full_payload[BANNER_ADDR - PREV_BTN_ADDR : BANNER_ADDR - PREV_BTN_ADDR + len(banner_code)] = banner_code
    full_payload[APPLY_ADDR - PREV_BTN_ADDR : APPLY_ADDR - PREV_BTN_ADDR + len(apply_code)] = apply_code
    full_payload[BOOT_ADDR - PREV_BTN_ADDR : BOOT_ADDR - PREV_BTN_ADDR + len(boot_code)] = boot_code
    full_payload[LIVE_ADDR - PREV_BTN_ADDR : LIVE_ADDR - PREV_BTN_ADDR + len(live_code)] = live_code

    return bytes(full_payload), BANNER_ADDR, BOOT_ADDR, LIVE_ADDR

# -----------------------------------------------------------------
# 3. EMULATOR TEST
# -----------------------------------------------------------------
def run_emu_test():
    print("\n--- Running Comprehensive Emulator Verification ---")
    pkgs = build_banner_packages()
    b11_img = build_bank11_image(pkgs)
    payload, bnr_addr, boot_addr, live_addr = build_bank15_payload()
    
    # 1. Load OS.BIN and inject components
    with open("EDFC/OS.BIN", "rb") as f:
        os_bin = bytearray(f.read())
        
    # Inject Theme 0 tiles into Bank 0x09 (0..0x1000)
    t0 = pkgs[0]
    for slot, tb in t0['tiles']:
        os_bin[slot*16 : (slot+1)*16] = tb
        
    # Inject Bank 0x0B image (0x4000..0x6000)
    os_bin[0x4000 : 0x6000] = b11_img
    
    # Save temporary test OS.BIN
    test_os_path = "EDFC/OS_TEST.BIN"
    with open(test_os_path, "wb") as f:
        f.write(os_bin)
        
    # Initialize emulator
    emu = EverDriveN8Emu(test_os_path, r"C:\Development\nes-everdrive")
    emu.run_frames(40) # let boot decryptor run
    
    # Inject Bank 15 payload
    b15 = emu.prg_ram[0x0F]
    b15[PREV_BTN_ADDR - 0xE000 : PREV_BTN_ADDR - 0xE000 + len(payload)] = payload
    
    # Set Hooks in Bank 12:
    b12 = emu.prg_ram[0x0C]
    # Hook 1 at $8103 (NMI): JMP LIVE_ADDR; NOP; NOP
    b12[0x0103 : 0x0108] = bytes([0x4C, live_addr & 0xFF, live_addr >> 8, 0xEA, 0xEA])
    # Hook 2 at $828C (Boot screen init): JSR BOOT_ADDR
    b12[0x028C : 0x028F] = bytes([0x20, boot_addr & 0xFF, boot_addr >> 8])
    # Hook 3 at $83F9 (Screen clear banner): JMP BANNER_ADDR; NOP; NOP
    b12[0x03F9 : 0x03FE] = bytes([0x4C, bnr_addr & 0xFF, bnr_addr >> 8, 0xEA, 0xEA])
    
    # Preload Theme 0 nametable into Bank 8 $7C00
    wram = emu.prg_ram[0x08]
    wram[0x1C00 : 0x1C40] = t0['nametable']
    
    # Initialize Palette 0 and Palette 1
    emu.palette[0:4] = bytes(t0['pal0'])
    emu.palette[4:8] = bytes(t0['pal1'])
    
    # Enter File Browser
    emu.press_button(0x40, hold_frames=2, wait_frames=30)
    
    # Render Theme 0 Boot Screen
    os.makedirs("docs/themes", exist_ok=True)
    emu.render_screen("docs/themes/test_theme0_boot.png", scale=2)
    print("  [OK] Theme 0 (RETROGAMER POA) rendered to docs/themes/test_theme0_boot.png")
    
    # Test Live Switching to Theme 1 (PADRAO)
    print("  Testing Live Switch: SELECT + RIGHT -> Theme 1 (PADRAO)...")
    emu.press_button(0x21, hold_frames=2, wait_frames=20)
    print(f"  Current Theme ID: {b15[0x1AE5]}")
    assert b15[0x1AE5] == 1, f"Expected theme 1, got {b15[0x1AE5]}"
    emu.render_screen("docs/themes/test_theme1_switch.png", scale=2)
    print("  [OK] Theme 1 (PADRAO) rendered to docs/themes/test_theme1_switch.png")
    
    # Test Live Switching to Theme 2 (SYNTHWAVE)
    print("  Testing Live Switch: SELECT + RIGHT -> Theme 2 (SYNTHWAVE)...")
    emu.press_button(0x21, hold_frames=2, wait_frames=20)
    print(f"  Current Theme ID: {b15[0x1AE5]}")
    assert b15[0x1AE5] == 2, f"Expected theme 2, got {b15[0x1AE5]}"
    emu.render_screen("docs/themes/test_theme2_switch.png", scale=2)
    print("  [OK] Theme 2 (SYNTHWAVE) rendered to docs/themes/test_theme2_switch.png")

    # Test Live Switching to Theme 3 (OUTRUN)
    print("  Testing Live Switch: SELECT + RIGHT -> Theme 3 (OUTRUN)...")
    emu.press_button(0x21, hold_frames=2, wait_frames=20)
    print(f"  Current Theme ID: {b15[0x1AE5]}")
    assert b15[0x1AE5] == 3, f"Expected theme 3, got {b15[0x1AE5]}"
    emu.render_screen("docs/themes/test_theme3_switch.png", scale=2)
    print("  [OK] Theme 3 (OUTRUN) rendered to docs/themes/test_theme3_switch.png")

    # Check SRAM persistence
    sram = emu.prg_ram[0x08]
    sig = list(sram[0x1BA6 : 0x1BAA])
    print(f"  Battery-Backed SRAM at $7BA6..$7BA9: {[hex(x) for x in sig]}")
    assert sig == [0xED, 0xFC, 0x03, 0xFC], f"Invalid SRAM signature: {sig}"
    print("  [OK] SRAM persistence verified!")

    # Test Reboot Restore
    print("  Testing Reboot Restore from SRAM...")
    saved_sram = bytes(emu.prg_ram[0x08])
    emu2 = EverDriveN8Emu(test_os_path, r"C:\Development\nes-everdrive")
    emu2.run_frames(40) # boot
    
    # Restore SRAM in new instance
    emu2.prg_ram[0x08][:] = saved_sram
    
    # Inject Bank 15 & Hooks
    emu2.prg_ram[0x0F][PREV_BTN_ADDR - 0xE000 : PREV_BTN_ADDR - 0xE000 + len(payload)] = payload
    emu2.prg_ram[0x0C][0x0103 : 0x0108] = bytes([0x4C, live_addr & 0xFF, live_addr >> 8, 0xEA, 0xEA])
    emu2.prg_ram[0x0C][0x028C : 0x028F] = bytes([0x20, boot_addr & 0xFF, boot_addr >> 8])
    emu2.prg_ram[0x0C][0x03F9 : 0x03FE] = bytes([0x4C, bnr_addr & 0xFF, bnr_addr >> 8, 0xEA, 0xEA])

    # Now run boot screen init naturally by setting PC to $828C
    # In Bank 12, $828C is called via JSR $828C. Its return address should return to $ED4F or $8290.
    # But notice: $828C routine ends at $8312 with RTS!
    # So if we push return address $8001 and set PC = 0x828C:
    emu2.PC = 0x828C
    emu2.push(0x80)
    emu2.push(0x00) # returns to $8001 when $8312 executes!
    for _ in range(5000):
        if emu2.PC == 0x8001:
            break
        emu2.step()
        
    print(f"  Theme ID after reboot restore: {emu2.prg_ram[0x0F][0x1AE5]}")
    assert emu2.prg_ram[0x0F][0x1AE5] == 3, f"Failed reboot restore, got {emu2.prg_ram[0x0F][0x1AE5]}"
    
    # Now verify Bank 8 $7C00 has Outrun nametable:
    t3 = pkgs[3]
    assert emu2.prg_ram[0x08][0x1C00:0x1C40] == t3['nametable'], "Outrun nametable not loaded to $7C00!"
    print("  [OK] Theme 3 nametable successfully loaded into Bank 8 $7C00!")
    
    # Check that Outrun CHR tiles are in PPU CHR-RAM:
    for slot, tb in t3['tiles']:
        ppu_tile = bytes(emu2.chr_ram[slot*16 : (slot+1)*16])
        assert ppu_tile == tb, f"Tile slot {hex(slot)} does not match!"
    print("  [OK] All Outrun CHR tiles verified in PPU CHR-RAM!")

    # Enter File Browser
    emu2.press_button(0x40, hold_frames=2, wait_frames=30)
    emu2.render_screen("docs/themes/test_theme3_reboot.png", scale=2)
    print("  [OK] Reboot restore verified! Rendered docs/themes/test_theme3_reboot.png")
    print("\nALL VERIFICATIONS PASSED 100% PERFECTLY!")

if __name__ == "__main__":
    run_emu_test()
