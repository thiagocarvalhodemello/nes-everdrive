import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.edfc_emu import EverDriveN8Emu

THEMES_4BYTE = [
    (0x0F, 0x10, 0x28, 0x00), # 0: Classico
    (0x0F, 0x2A, 0x39, 0x09), # 1: Matrix
    (0x02, 0x2C, 0x24, 0x12), # 2: Cyberpunk
    (0x08, 0x19, 0x38, 0x0A), # 3: Game Boy
    (0x0F, 0x17, 0x27, 0x07), # 4: Ambar
    (0x0F, 0x20, 0x21, 0x00), # 5: Dark OLED
    (0x0F, 0x16, 0x26, 0x06), # 6: Crimson
    (0x01, 0x21, 0x3C, 0x11), # 7: Ocean
    (0x04, 0x37, 0x28, 0x14), # 8: Sunset
]

table_bytes = bytearray()
for bd, txt, hl, sh in THEMES_4BYTE:
    table_bytes.extend([bd, txt, hl, sh])

op_bytes = {
    "PHA": (0x48,), "PLA": (0x68,), "TXA": (0x8A,), "TAX": (0xAA,), "TYA": (0x98,), "TAY": (0xA8,),
    "SEC": (0x38,), "DEY": (0x88,), "INY": (0xC8,), "ASL": (0x0A,), "RTI": (0x40,), "RTS": (0x60,),
    "LDA_IMM": 0xA9, "CMP_IMM": 0xC9, "CPY_IMM": 0xC0, "SBC_IMM": 0xE9, "LDY_IMM": 0xA0, "EOR_IMM": 0x49,
    "LDA_ABS": 0xAD, "STA_ABS": 0x8D, "CMP_ABS": 0xCD, "INC_ABS": 0xEE, "DEC_ABS": 0xCE, "BIT_ABS": 0x2C,
    "EOR_ABS": 0x4D, "JMP": 0x4C, "JSR": 0x20,
    "LDA_ABX": 0xBD, "STA_ABY": 0x99, "LDA_ABY": 0xB9,
    "BEQ": 0xF0, "BNE": 0xD0, "BCC": 0x90, "BCS": 0xB0, "BPL": 0x10, "BMI": 0x30
}

def assemble_listing(listing, base_addr):
    labels = {}
    pc = base_addr
    for lbl, mnem, arg in listing:
        if lbl: labels[lbl] = pc
        if mnem in ("PHA", "PLA", "TXA", "TAX", "TYA", "TAY", "SEC", "DEY", "INY", "ASL", "RTI", "RTS"):
            pc += 1
        elif mnem.endswith("_IMM") or mnem in ("BEQ", "BNE", "BCC", "BCS", "BPL", "BMI"):
            pc += 2
        else:
            pc += 3

    binary = bytearray()
    pc = base_addr
    for lbl, mnem, arg in listing:
        if mnem in ("PHA", "PLA", "TXA", "TAX", "TYA", "TAY", "SEC", "DEY", "INY", "ASL", "RTI", "RTS"):
            binary.append(op_bytes[mnem][0])
            pc += 1
        elif mnem.endswith("_IMM"):
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

# Memory Map in Bank 15:
# $FAE4: prev_buttons (1 byte)
# $FAE5: current theme_id (1 byte)
# $FAEC..$FB0F: 36-byte palette table (4 bytes * 9 themes)
# $FB10..$FB33: EXPAND_PAL routine (36 bytes)
# $FB34..$FB5C: BOOT_RESTORE routine (41 bytes)
# $FB60..$FBE8: LIVE_SWITCHER routine (136 bytes)
# $FBE8..$FBFF: 24 bytes of free safety margin before $FC00!

TABLE_ADDR  = 0xFAEC
EXPAND_ADDR = 0xFB10
BOOT_ADDR   = 0xFB34
LIVE_ADDR   = 0xFB60

def get_full_payload():
    # 1. EXPAND_PAL (A = theme_id)
    expand_listing = [
        ("EXPAND", "ASL", None),
        (None, "ASL", None),
        (None, "TAX", None),
        (None, "LDY_IMM", 0x0F),
        (None, "LDA_ABX", TABLE_ADDR),
        ("FILL", "STA_ABY", 0x827C),
        (None, "DEY", None),
        (None, "BPL", "FILL"),

        (None, "LDA_ABX", TABLE_ADDR + 1),
        (None, "STA_ABS", 0x827D),
        (None, "LDA_ABX", TABLE_ADDR + 2),
        (None, "STA_ABS", 0x827F),
        (None, "STA_ABS", 0x828B),
        (None, "LDA_ABX", TABLE_ADDR + 3),
        (None, "STA_ABS", 0x828A),
        (None, "RTS", None)
    ]
    expand_code = assemble_listing(expand_listing, EXPAND_ADDR)

    # 2. BOOT_RESTORE
    boot_listing = [
        ("BOOT", "LDA_ABS", 0x7BA6),
        (None, "CMP_IMM", 0xED),
        (None, "BNE", "DONE"),
        (None, "LDA_ABS", 0x7BA7),
        (None, "CMP_IMM", 0xFC),
        (None, "BNE", "DONE"),
        (None, "LDA_ABS", 0x7BA8),
        (None, "EOR_ABS", 0x7BA9),
        (None, "CMP_IMM", 0xFF),
        (None, "BNE", "DONE"),

        # Valid theme ID
        (None, "LDA_ABS", 0x7BA8),
        (None, "CMP_IMM", 0x09),
        (None, "BCS", "DONE"),
        (None, "STA_ABS", 0xFAE5),
        (None, "JSR", EXPAND_ADDR),

        ("DONE", "JSR", 0x83B0),
        (None, "RTS", None)
    ]
    boot_code = assemble_listing(boot_listing, BOOT_ADDR)

    # 3. LIVE_SWITCHER
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
        (None, "CMP_ABS", 0xFAE4),
        (None, "STA_ABS", 0xFAE4),
        (None, "BNE", "CHECK_BTN"),

        ("EXIT", "PLA", None),
        (None, "TAY", None),
        (None, "PLA", None),
        (None, "TAX", None),
        (None, "PLA", None),
        (None, "RTI", None),

        ("CHECK_BTN", "CMP_IMM", 0x21), # SELECT + RIGHT
        (None, "BEQ", "NEXT"),
        (None, "CMP_IMM", 0x22),        # SELECT + LEFT
        (None, "BEQ", "PREV"),
        (None, "BNE", "EXIT"),

        ("NEXT", "INC_ABS", 0xFAE5),
        (None, "LDA_ABS", 0xFAE5),
        (None, "CMP_IMM", 0x09),
        (None, "BCC", "APPLY"),
        (None, "LDA_IMM", 0x00),
        (None, "STA_ABS", 0xFAE5),
        (None, "BEQ", "APPLY"),

        ("PREV", "DEC_ABS", 0xFAE5),
        (None, "BPL", "APPLY"),
        (None, "LDA_IMM", 0x08),
        (None, "STA_ABS", 0xFAE5),

        ("APPLY", "LDA_ABS", 0xFAE5),
        (None, "JSR", EXPAND_ADDR),

        # Save to Battery-Backed SRAM $7BA6..$7BA9!
        (None, "LDA_IMM", 0xED),
        (None, "STA_ABS", 0x7BA6),
        (None, "LDA_IMM", 0xFC),
        (None, "STA_ABS", 0x7BA7),
        (None, "LDA_ABS", 0xFAE5),
        (None, "STA_ABS", 0x7BA8),
        (None, "EOR_IMM", 0xFF),
        (None, "STA_ABS", 0x7BA9),

        # Clean standalone PPU palette upload (NEVER touches CHR $0000 or ZP $94/$95!)
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

        # Clean PPU scroll & address reset
        (None, "BIT_ABS", 0x2002),
        (None, "LDA_IMM", 0x00),
        (None, "STA_ABS", 0x2005),
        (None, "STA_ABS", 0x2005),
        (None, "STA_ABS", 0x2006),
        (None, "STA_ABS", 0x2006),

        (None, "JMP", "EXIT")
    ]
    live_code = assemble_listing(live_listing, LIVE_ADDR)

    return expand_code, boot_code, live_code

if __name__ == "__main__":
    expand_code, boot_code, live_code = get_full_payload()
    print(f"Table:         {len(table_bytes)} bytes (${TABLE_ADDR:04X}..${TABLE_ADDR+len(table_bytes):04X})")
    print(f"Expand helper: {len(expand_code)} bytes (${EXPAND_ADDR:04X}..${EXPAND_ADDR+len(expand_code):04X})")
    print(f"Boot restore:  {len(boot_code)} bytes (${BOOT_ADDR:04X}..${BOOT_ADDR+len(boot_code):04X})")
    print(f"Live switcher: {len(live_code)} bytes (${LIVE_ADDR:04X}..${LIVE_ADDR+len(live_code):04X})")
    end_addr = LIVE_ADDR + len(live_code)
    print(f"End address:   ${end_addr:04X} (Safety margin before $FC00: {0xFC00 - end_addr} bytes)")
    assert end_addr <= 0xFC00, "Exceeds $FC00!"

    print("\nStarting emulator test...")
    emu = EverDriveN8Emu(r"EDFC\OS.BIN", r"C:\Development\nes-everdrive")
    emu.run_frames(40)
    emu.press_button(0x40, hold_frames=2, wait_frames=30) # B -> file browser

    # Inject into Bank 15
    bank15 = emu.prg_ram[15]
    bank15[0x1AE4] = 0x00 # prev buttons = 0
    bank15[0x1AE5] = 0x00 # theme_id = 0
    bank15[TABLE_ADDR - 0xE000 : TABLE_ADDR - 0xE000 + len(table_bytes)] = table_bytes
    bank15[EXPAND_ADDR - 0xE000 : EXPAND_ADDR - 0xE000 + len(expand_code)] = expand_code
    bank15[BOOT_ADDR - 0xE000 : BOOT_ADDR - 0xE000 + len(boot_code)] = boot_code
    bank15[LIVE_ADDR - 0xE000 : LIVE_ADDR - 0xE000 + len(live_code)] = live_code

    # Hook NMI at $8103 in Bank 12: JMP $FB60; NOP; NOP
    bank12 = emu.prg_ram[12]
    bank12[0x0103:0x0108] = bytes([0x4C, LIVE_ADDR & 0xFF, LIVE_ADDR >> 8, 0xEA, 0xEA])

    # Hook Screen Init at $828C in Bank 12: JSR $FB60
    bank12[0x028C:0x028F] = bytes([0x20, BOOT_ADDR & 0xFF, BOOT_ADDR >> 8])

    print("Initial palette:", " ".join(f"{b:02X}" for b in emu.palette[:4]))

    # Switch to Matrix (Theme 1)
    print("\n--> [1] Switching to Matrix (Theme 1)...")
    emu.press_button(0x21, hold_frames=2, wait_frames=15)
    print("Palette (Matrix):", " ".join(f"{b:02X}" for b in emu.palette[:4]))

    # Switch to Cyberpunk (Theme 2)
    print("\n--> [2] Switching to Cyberpunk (Theme 2)...")
    emu.press_button(0x21, hold_frames=2, wait_frames=15)
    print("Palette (Cyberpunk):", " ".join(f"{b:02X}" for b in emu.palette[:4]))

    # Check SRAM
    b8 = emu.prg_ram[8]
    sram_sig = [b8[0x1BA6 + i] for i in range(4)]
    print("SRAM $7BA6..$7BA9:", " ".join(f"{b:02X}" for b in sram_sig))
    assert sram_sig == [0xED, 0xFC, 0x02, 0xFD], f"Incorrect SRAM save: {sram_sig}"
    print("[OK] SRAM successfully saved Theme 2 (Cyberpunk)!")

    # NOW TEST REBOOT!
    print("\n--> [3] SIMULATING REBOOT / RESET...")
    # Reset active palette in $827C back to default Classic to simulate cold reload of OS.BIN from SD card
    bank12[0x027C:0x028C] = bytes([0x0F, 0x10, 0x0F, 0x28, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x30, 0x00, 0x28])
    
    # Run screen init hook at $828C (which calls JSR $FB34)
    emu.PC = 0x828C
    for _ in range(100):
        emu.step()
    
    print("Palette buffer in $827C after reboot hook:", " ".join(f"{bank12[0x027C+i]:02X}" for i in range(4)))
    assert bank12[0x027C] == 0x02 and bank12[0x027D] == 0x2C, "Theme was not restored on reboot!"
    print("[SUCCESS] Theme 2 (Cyberpunk) was automatically restored from SRAM upon reboot!")
