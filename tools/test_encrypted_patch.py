import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.edfc_emu import EverDriveN8Emu
from tools.test_compact_hook import assemble_ultra_compact, table_bytes

code, labels = assemble_ultra_compact()
print(f"Code size: {len(code)}, Table size: {len(table_bytes)}")

with open(r"EDFC\OS.BIN", "rb") as f:
    orig = bytearray(f.read())

# 1. Bank 15 patches (file offset 0xDB64 for table, 0xDB88 for code)
# Key is orig[0xDB64..]
xor_b15 = orig[0xDB64 : 0xDB64 + len(table_bytes) + len(code)]
payload = table_bytes + code
enc_payload = bytes(p ^ k for p, k in zip(payload, xor_b15))
orig[0xDB64 : 0xDB64 + len(payload)] = enc_payload

# 2. Bank 12 hook at 0x6103 (CPU $8103)
xor_b12 = bytes([0x9E, 0xFB, 0x89, 0xEF, 0x60])
hook_inst = bytes([0x4C, 0x88, 0xFB, 0xEA, 0xEA]) # JMP $FB88; NOP; NOP
orig[0x6103 : 0x6108] = bytes(p ^ k for p, k in zip(hook_inst, xor_b12))

with tempfile.NamedTemporaryFile(delete=False, suffix=".BIN") as tmp:
    tmp.write(orig)
    tmp_path = tmp.name

try:
    print("Testing patched OS.BIN with hardware boot decryptor...")
    emu = EverDriveN8Emu(tmp_path, r"C:\Development\nes-everdrive")
    emu.run_frames(40) # Decrypts via k60 and boots
    
    # Check decrypted code in Bank 15
    dec_code = bytes(emu.prg_ram[15][0x1B88:0x1B88+10])
    print("Decrypted bytes at $FB88 in PRG-RAM:", " ".join(f"{b:02X}" for b in dec_code))
    assert dec_code == code[:10], f"Decryption mismatch! Got: {dec_code.hex()}, expected: {code[:10].hex()}"
    
    # Check decrypted hook in Bank 12
    dec_hook = bytes(emu.prg_ram[12][0x0103:0x0108])
    print("Decrypted hook at $8103 in Bank 12:", " ".join(f"{b:02X}" for b in dec_hook))
    assert dec_hook == hook_inst, f"Decrypted hook mismatch! Got: {dec_hook.hex()}"
    
    emu.press_button(0x40, hold_frames=2, wait_frames=30) # B -> file browser
    print("Initial palette:", " ".join(f"{b:02X}" for b in emu.palette[:4]))
    
    # 1. Next theme -> Matrix
    print("\n[Test 1] Pressing SELECT + RIGHT...")
    emu.press_button(0x21, hold_frames=2, wait_frames=15)
    print("  Palette:", " ".join(f"{b:02X}" for b in emu.palette[:4]))
    assert emu.palette[0] == 0x0F and emu.palette[1] == 0x2A and emu.palette[3] == 0x39
    
    # 2. Next theme -> Cyberpunk
    print("\n[Test 2] Pressing SELECT + RIGHT...")
    emu.press_button(0x21, hold_frames=2, wait_frames=15)
    print("  Palette:", " ".join(f"{b:02X}" for b in emu.palette[:4]))
    assert emu.palette[0] == 0x02 and emu.palette[1] == 0x2C and emu.palette[3] == 0x24
    
    # 3. Next theme -> Game Boy
    print("\n[Test 3] Pressing SELECT + RIGHT...")
    emu.press_button(0x21, hold_frames=2, wait_frames=15)
    print("  Palette:", " ".join(f"{b:02X}" for b in emu.palette[:4]))
    assert emu.palette[0] == 0x08 and emu.palette[1] == 0x19 and emu.palette[3] == 0x38
    
    # 4. Prev theme -> Cyberpunk
    print("\n[Test 4] Pressing SELECT + LEFT...")
    emu.press_button(0x22, hold_frames=2, wait_frames=15)
    print("  Palette:", " ".join(f"{b:02X}" for b in emu.palette[:4]))
    assert emu.palette[0] == 0x02 and emu.palette[1] == 0x2C and emu.palette[3] == 0x24
    
    print("\n🎉 END-TO-END VERIFICATION PASSED WITH 100% SUCCESS!")
finally:
    if os.path.exists(tmp_path):
        os.remove(tmp_path)
