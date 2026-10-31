import os, sys, glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_full_banner_system import (
    build_banner_packages,
    build_bank11_image,
    build_bank15_payload,
    PREV_BTN_ADDR
)

# 1. Load immutable XOR keys from EDFC-ORIGINAL/OS.BIN
with open("EDFC-ORIGINAL/OS.BIN", "rb") as f:
    orig_data = f.read()

# Bank 15 XOR key starts at file offset 0xDAE4 (CPU $FAE4)
XOR_B15 = orig_data[0xDAE4 : 0xDAE4 + 282]

# Hook 1 at CPU $8103 (file 0x6103 in Bank 12): JMP LIVE_ADDR; NOP; NOP
XOR_HOOK1 = bytes([0x9E, 0xFB, 0x89, 0xEF, 0x60])

# Hook 2 at CPU $828C (file 0x628C in Bank 12): JSR BOOT_ADDR
XOR_HOOK2 = bytes([0x2F, 0xC7, 0x0A])

# Hook 3 at CPU $83F9 (file 0x63F9 in Bank 12): JMP BANNER_ADDR; NOP; NOP
XOR_HOOK3 = bytes([0xB6, 0x4E, 0x17, 0x3E, 0x38])

def patch_os_bin(os_bin_path, pkgs, b11_img, payload, bnr_addr, boot_addr, live_addr):
    with open(os_bin_path, "rb") as f:
        data = bytearray(f.read())

    # 1. Inject Theme 0 CHR tiles into Bank 0x09 (unencrypted, offset 0..0x1000)
    t0 = pkgs[0]
    for slot, tb in t0['tiles']:
        data[slot*16 : (slot+1)*16] = tb

    # 2. Inject Bank 0x0B image into offset 0x4000..0x6000 (unencrypted)
    data[0x4000 : 0x6000] = b11_img

    # 3. Inject encrypted Bank 15 payload starting at file offset 0xDAE4
    enc_payload = bytes(p ^ k for p, k in zip(payload, XOR_B15[:len(payload)]))
    data[0xDAE4 : 0xDAE4 + len(payload)] = enc_payload

    # 4. Bank 12 Hook 1 (NMI live switch) at 0x6103: JMP LIVE_ADDR; NOP; NOP
    hook1_plain = bytes([0x4C, live_addr & 0xFF, live_addr >> 8, 0xEA, 0xEA])
    enc_h1 = bytes(p ^ k for p, k in zip(hook1_plain, XOR_HOOK1))
    data[0x6103 : 0x6108] = enc_h1

    # 5. Bank 12 Hook 2 (Boot screen init) at 0x628C: JSR BOOT_ADDR
    hook2_plain = bytes([0x20, boot_addr & 0xFF, boot_addr >> 8])
    enc_h2 = bytes(p ^ k for p, k in zip(hook2_plain, XOR_HOOK2))
    data[0x628C : 0x628F] = enc_h2

    # 6. Bank 12 Hook 3 (Screen clear banner) at 0x63F9: JMP BANNER_ADDR; NOP; NOP
    hook3_plain = bytes([0x4C, bnr_addr & 0xFF, bnr_addr >> 8, 0xEA, 0xEA])
    enc_h3 = bytes(p ^ k for p, k in zip(hook3_plain, XOR_HOOK3))
    data[0x63F9 : 0x63FE] = enc_h3

    with open(os_bin_path, "wb") as f:
        f.write(data)
    print(f"  [OK] Successfully patched: {os_bin_path}")

def main():
    print("Construindo pacotes graficos de temas e banners (Theme & Banner System)...")
    pkgs = build_banner_packages()
    b11_img = build_bank11_image(pkgs)
    payload, bnr_addr, boot_addr, live_addr = build_bank15_payload()

    targets = [
        "EDFC/OS.BIN",
        "sdcard/EDFC/OS.BIN"
    ] + glob.glob("THEMES/*/OS.BIN")

    for t in targets:
        if os.path.exists(t):
            patch_os_bin(t, pkgs, b11_img, payload, bnr_addr, boot_addr, live_addr)

    print("\nTodos os arquivos OS.BIN foram atualizados com sucesso com o sistema completo de banners e temas!")

if __name__ == "__main__":
    main()
