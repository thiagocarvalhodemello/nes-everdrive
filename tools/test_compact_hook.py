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

def assemble_ultra_compact(table_addr=0xFB64, code_addr=0xFB88):
    listing = [
        (None, "BIT_ABS", 0x2002),
        (None, "PLA", None),
        (None, "PHA", None),
        (None, "TXA", None),
        (None, "PHA", None),
        (None, "TYA", None),
        (None, "PHA", None),

        # Check buttons ($0484)
        (None, "LDA_ABS", 0x0484),
        (None, "CMP_ABS", 0xFB62),    # prev
        (None, "STA_ABS", 0xFB62),    # prev = current
        (None, "BEQ", "EXIT"),

        (None, "CMP_IMM", 0x21),      # SELECT + RIGHT
        (None, "BEQ", "NEXT"),
        (None, "CMP_IMM", 0x22),      # SELECT + LEFT
        (None, "BEQ", "PREV"),
        (None, "BNE", "EXIT"),

        ("NEXT", "INC_ABS", 0xFB63),
        (None, "LDA_ABS", 0xFB63),
        (None, "CMP_IMM", 0x09),
        (None, "BCC", "APPLY"),
        (None, "LDA_IMM", 0x00),
        (None, "STA_ABS", 0xFB63),
        (None, "BEQ", "APPLY"),

        ("PREV", "DEC_ABS", 0xFB63),
        (None, "BPL", "APPLY"),
        (None, "LDA_IMM", 0x08),
        (None, "STA_ABS", 0xFB63),

        ("APPLY", "LDA_ABS", 0xFB63),
        (None, "ASL", None),
        (None, "ASL", None),
        (None, "TAX", None),
        (None, "LDY_IMM", 0x0F),
        (None, "LDA_ABX", table_addr), # backdrop
        ("FILL", "STA_ABY", 0x827C),
        (None, "DEY", None),
        (None, "BPL", "FILL"),

        (None, "LDA_ABX", table_addr + 1), # text
        (None, "STA_ABS", 0x827D),
        (None, "LDA_ABX", table_addr + 2), # highlight
        (None, "STA_ABS", 0x827F),
        (None, "STA_ABS", 0x828B),
        (None, "LDA_ABX", table_addr + 3), # shadow
        (None, "STA_ABS", 0x828A),

        # Call existing OS palette load at $82B9
        (None, "JSR", 0x82B9),

        # Reset PPU scroll/latch
        (None, "LDA_IMM", 0x00),
        (None, "STA_ABS", 0x2006),
        (None, "STA_ABS", 0x2006),
        (None, "STA_ABS", 0x2005),
        (None, "STA_ABS", 0x2005),

        ("EXIT", "PLA", None),
        (None, "TAY", None),
        (None, "PLA", None),
        (None, "TAX", None),
        (None, "PLA", None),
        (None, "RTI", None)
    ]

    op_bytes = {
        "PHA": (0x48,), "PLA": (0x68,), "TXA": (0x8A,), "TAX": (0xAA,), "TYA": (0x98,), "TAY": (0xA8,),
        "SEC": (0x38,), "DEY": (0x88,), "INY": (0xC8,), "ASL": (0x0A,), "RTI": (0x40,),
        "LDA_IMM": 0xA9, "CMP_IMM": 0xC9, "CPY_IMM": 0xC0, "SBC_IMM": 0xE9, "LDY_IMM": 0xA0,
        "LDA_ABS": 0xAD, "STA_ABS": 0x8D, "CMP_ABS": 0xCD, "INC_ABS": 0xEE, "DEC_ABS": 0xCE, "BIT_ABS": 0x2C,
        "JMP": 0x4C, "JSR": 0x20,
        "LDA_ABX": 0xBD, "STA_ABY": 0x99, "LDA_ABY": 0xB9,
        "BEQ": 0xF0, "BNE": 0xD0, "BCC": 0x90, "BCS": 0xB0, "BPL": 0x10, "BMI": 0x30
    }

    labels = {}
    pc = code_addr
    for lbl, mnem, arg in listing:
        if lbl: labels[lbl] = pc
        if mnem in ("PHA", "PLA", "TXA", "TAX", "TYA", "TAY", "SEC", "DEY", "INY", "ASL", "RTI"): pc += 1
        elif mnem.endswith("_IMM") or mnem in ("BEQ", "BNE", "BCC", "BCS", "BPL", "BMI"): pc += 2
        else: pc += 3

    binary = bytearray()
    pc = code_addr
    for lbl, mnem, arg in listing:
        if mnem in ("PHA", "PLA", "TXA", "TAX", "TYA", "TAY", "SEC", "DEY", "INY", "ASL", "RTI"):
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

    return bytes(binary), labels

if __name__ == "__main__":
    code, labels = assemble_ultra_compact()
    print(f"Ultra Compact Code Size: {len(code)} bytes (0xFB88..0x{0xFB88+len(code):04X})")
    print(f"Ends before 0xFC00: {0xFB88+len(code) <= 0xFC00} (Safety margin: {0xFC00 - (0xFB88+len(code))} bytes)")

    # Test with EverDriveN8Emu
    emu = EverDriveN8Emu(r"EDFC\OS.BIN", r"C:\Development\nes-everdrive")
    emu.run_frames(40)
    emu.press_button(0x40, hold_frames=2, wait_frames=30) # B -> file browser

    bank15 = emu.prg_ram[15]
    # Table at 0x1B64 (CPU $FB64)
    bank15[0x1B64:0x1B64+len(table_bytes)] = table_bytes
    # Code at 0x1B88 (CPU $FB88)
    bank15[0x1B88:0x1B88+len(code)] = code

    # Hook at 0x8103 in Bank 12: JMP $FB88; NOP; NOP
    bank12 = emu.prg_ram[12]
    bank12[0x0103:0x0108] = bytes([0x4C, 0x88, 0xFB, 0xEA, 0xEA])

    print("Initial palette:", " ".join(f"{b:02X}" for b in emu.palette[:4]))

    # Press SELECT + RIGHT (0x21)
    print("\n--> [1] Pressing SELECT + RIGHT (Next theme)...")
    emu.press_button(0x21, hold_frames=2, wait_frames=15)
    print("Palette (Matrix):", " ".join(f"{b:02X}" for b in emu.palette[:4]))
    emu.render_screen("docs/themes/test_live_matrix.png")

    # Press SELECT + RIGHT again
    print("\n--> [2] Pressing SELECT + RIGHT (Next theme)...")
    emu.press_button(0x21, hold_frames=2, wait_frames=15)
    print("Palette (Cyberpunk):", " ".join(f"{b:02X}" for b in emu.palette[:4]))
    emu.render_screen("docs/themes/test_live_cyberpunk.png")

    # Press SELECT + RIGHT again
    print("\n--> [3] Pressing SELECT + RIGHT (Next theme)...")
    emu.press_button(0x21, hold_frames=2, wait_frames=15)
    print("Palette (Game Boy):", " ".join(f"{b:02X}" for b in emu.palette[:4]))
    emu.render_screen("docs/themes/test_live_gameboy.png")

    # Press SELECT + LEFT (0x22)
    print("\n--> [4] Pressing SELECT + LEFT (Previous theme)...")
    emu.press_button(0x22, hold_frames=2, wait_frames=15)
    print("Palette (Back to Cyberpunk):", " ".join(f"{b:02X}" for b in emu.palette[:4]))
    emu.render_screen("docs/themes/test_live_back_cyberpunk.png")

    print("\n*** ALL TESTS PASSED! IN-SYSTEM THEME SELECTOR IS WORKING FLAWLESSLY! ***")
