import os
import struct

test_rom_paths = [
    r"sdcard\4 Traduzidos\Potugues A-Z\Super Mario Bros. (World).nes",
    r"sdcard\4 Traduzidos\Potugues A-Z\Castlevania (USA).nes",
    r"sdcard\4 Traduzidos\Potugues A-Z\Mega Man 2 (USA).nes" if os.path.exists(r"sdcard\4 Traduzidos\Potugues A-Z\Mega Man 2 (USA).nes") else r"sdcard\1 US - G-Q\Mega Man 2 (USA).nes",
    r"sdcard\4 Traduzidos\Potugues A-Z\Super Mario Bros. 3 (USA).nes",
    r"sdcard\4 Traduzidos\Potugues A-Z\Akumajou Densetsu (J).nes",
    r"sdcard\4 Traduzidos\Potugues A-Z\Battletoads (USA).nes",
    r"sdcard\1 US - G-Q\Kirby's Adventure (USA).nes",
]

with open(r"EDFC\MAPROUT.BIN", "rb") as f:
    maprout = f.read()

maps_dir = r"EDFC\MAPS"
avail_rbfs = set(os.listdir(maps_dir))

print(f"Total available RBFs in EDFC/MAPS: {len(avail_rbfs)}")
print("=" * 70)

for path in test_rom_paths:
    if not os.path.exists(path):
        print(f"File NOT found: {path}")
        continue
    with open(path, "rb") as f:
        hdr = f.read(16)
    if hdr[:4] != b"NES\x1a":
        print(f"Invalid header: {path}")
        continue
    prg_pages = hdr[4]
    chr_pages = hdr[5]
    f6 = hdr[6]
    f7 = hdr[7]
    mapper = (f6 >> 4) | (f7 & 0xF0)
    has_battery = bool(f6 & 0x02)
    mirroring = "Vertical" if (f6 & 0x01) else "Horizontal"
    if f6 & 0x08:
        mirroring = "4-Screen"

    rbf_id = maprout[mapper]
    rbf_file = f"{rbf_id:03d}.RBF"
    supported = rbf_file in avail_rbfs

    print(f"Game: {os.path.basename(path)}")
    print(f"  Mapper: {mapper} -> mapped to {rbf_file} (Supported: {supported})")
    print(f"  PRG Size: {prg_pages * 16} KB ({prg_pages} pages)")
    print(f"  CHR Size: {chr_pages * 8} KB ({chr_pages} pages)")
    print(f"  Mirroring: {mirroring}, Battery: {has_battery}")
    print("-" * 70)
