import os, sys, glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_full_banner_system import build_banner_packages, build_bank11_image
from theme_runtime import patch_runtime, REGION_START, REGION_LEN

# Immutable reference image: its bytes provide the keystream for encrypted banks.
with open("EDFC-ORIGINAL/OS.BIN", "rb") as f:
    orig_data = f.read()


def patch_os_bin(os_bin_path, pkgs, b11_img):
    with open(os_bin_path, "rb") as f:
        data = bytearray(f.read())

    # 1. Theme 0 CHR tiles into bank $09 (unencrypted, offset 0..0x1000)
    for slot, tb in pkgs[0]['tiles']:
        data[slot*16 : (slot+1)*16] = tb

    # 2. Bank $0B image (theme packages, palette table, loader) at 0x4000..0x6000
    data[0x4000 : 0x6000] = b11_img

    # 3. Bank 15 runtime ($FAE4..$FBFD) + hooks (NMI, boot, banner, idle)
    labels = patch_runtime(data, orig_data)

    with open(os_bin_path, "wb") as f:
        f.write(data)
    print(f"  [OK] {os_bin_path}  (runtime {labels['_END'] - REGION_START}/{REGION_LEN} bytes)")


def main():
    print("Construindo pacotes graficos de temas e banners (Theme & Banner System)...")
    pkgs = build_banner_packages()
    b11_img = build_bank11_image(pkgs)

    targets = [
        "EDFC/OS.BIN",
        "sdcard/EDFC/OS.BIN"
    ]

    for t in targets:
        if os.path.exists(t):
            patch_os_bin(t, pkgs, b11_img)

    print("\nTodos os arquivos OS.BIN foram atualizados com sucesso com o sistema completo de banners e temas!")

if __name__ == "__main__":
    main()
