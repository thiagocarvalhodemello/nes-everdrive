import os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_persistent_theme import (
    table_bytes, get_full_payload,
    TABLE_ADDR, EXPAND_ADDR, BOOT_ADDR, LIVE_ADDR
)

# Extract immutable XOR keys directly from EDFC-ORIGINAL/OS.BIN
with open("EDFC-ORIGINAL/OS.BIN", "rb") as f:
    orig_data = f.read()

# Bank 15 XOR key starts at offset 0xDAE4 (CPU $FAE4) through 0xDBFE
# Total length: 0xDBFE - 0xDAE4 = 282 bytes
XOR_B15 = orig_data[0xDAE4:0xDBFE]

# Hook 1 at CPU $8103 (file 0x6103 in Bank 12): JMP $FB60; NOP; NOP
XOR_HOOK1 = bytes([0x9E, 0xFB, 0x89, 0xEF, 0x60])
HOOK1_BYTES = bytes([0x4C, LIVE_ADDR & 0xFF, LIVE_ADDR >> 8, 0xEA, 0xEA])

# Hook 2 at CPU $828C (file 0x628C in Bank 12): JSR $FB34
XOR_HOOK2 = bytes([0x2F, 0xC7, 0x0A])
HOOK2_BYTES = bytes([0x20, BOOT_ADDR & 0xFF, BOOT_ADDR >> 8])

def build_bank15_payload():
    expand_code, boot_code, live_code = get_full_payload()
    
    # Base layout from $FAE4
    payload = bytearray(0xDBFE - 0xDAE4)
    # $FAE4: prev_buttons = 0, $FAE5: theme_id = 0
    payload[0x00] = 0x00
    payload[0x01] = 0x00
    
    # Table at $FAEC (offset 0x08 from $FAE4)
    off_tbl = TABLE_ADDR - 0xFAE4
    payload[off_tbl : off_tbl + len(table_bytes)] = table_bytes
    
    # Expand helper at $FB10
    off_exp = EXPAND_ADDR - 0xFAE4
    payload[off_exp : off_exp + len(expand_code)] = expand_code
    
    # Boot restore at $FB34
    off_boot = BOOT_ADDR - 0xFAE4
    payload[off_boot : off_boot + len(boot_code)] = boot_code
    
    # Live switcher at $FB60
    off_live = LIVE_ADDR - 0xFAE4
    payload[off_live : off_live + len(live_code)] = live_code
    
    return bytes(payload)

def patch_os_bin(os_bin_path):
    with open(os_bin_path, "rb") as f:
        data = bytearray(f.read())
    
    # 1. Bank 15 payload
    payload = build_bank15_payload()
    enc_payload = bytes(p ^ k for p, k in zip(payload, XOR_B15[:len(payload)]))
    data[0xDAE4 : 0xDAE4 + len(payload)] = enc_payload
    
    # 2. Bank 12 Hook 1 (NMI live switch) at 0x6103
    enc_h1 = bytes(p ^ k for p, k in zip(HOOK1_BYTES, XOR_HOOK1))
    data[0x6103 : 0x6108] = enc_h1
    
    # 3. Bank 12 Hook 2 (Boot screen init) at 0x628C
    enc_h2 = bytes(p ^ k for p, k in zip(HOOK2_BYTES, XOR_HOOK2))
    data[0x628C : 0x628F] = enc_h2
    
    with open(os_bin_path, "wb") as f:
        f.write(data)
    print(f"  [OK] Successfully patched: {os_bin_path}")

def main():
    print("Aplicando o Seletor de Temas com Persistencia e Fix de Graficos nos arquivos OS.BIN...")
    targets = ["EDFC/OS.BIN"] + glob.glob("THEMES/*/OS.BIN")
    for t in targets:
        if os.path.exists(t):
            patch_os_bin(t)
    print("Concluido com sucesso!")

if __name__ == "__main__":
    main()
