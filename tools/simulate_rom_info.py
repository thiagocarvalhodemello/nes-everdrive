import os

def parse_rom_info(filepath):
    with open(filepath, "rb") as f:
        hdr = f.read(16)
    if hdr[:4] != b"NES\x1a":
        return None
    prg_pages = hdr[4]
    chr_pages = hdr[5]
    f6 = hdr[6]
    f7 = hdr[7]
    mapper = (f6 >> 4) | (f7 & 0xF0)
    has_battery = bool(f6 & 0x02)
    has_trainer = bool(f6 & 0x04)
    four_screen = bool(f6 & 0x08)
    vertical = bool(f6 & 0x01)

    # Mirroring string
    if four_screen:
        mirror = "4"
    elif vertical:
        mirror = "V"
    else:
        mirror = "H"

    # Memory string
    if has_battery:
        mem = "RAM+BAT"
    else:
        mem = "NÃO"

    return {
        "file": os.path.basename(filepath),
        "mapper": mapper,
        "prg_kb": prg_pages * 16,
        "chr_kb": chr_pages * 8,
        "memory": mem,
        "mirror": mirror,
    }

samples = [
    r"sdcard\4 Traduzidos\Potugues A-Z\Super Mario Bros. (World).nes",
    r"sdcard\4 Traduzidos\Potugues A-Z\Castlevania (USA).nes",
    r"sdcard\4 Traduzidos\Potugues A-Z\Super Mario Bros. 3 (USA).nes",
    r"sdcard\4 Traduzidos\Potugues A-Z\Akumajou Densetsu (J).nes",
    r"sdcard\4 Traduzidos\Potugues A-Z\Legend of Zelda, The (USA).nes",
    r"sdcard\1 US - G-Q\Kirby's Adventure (USA) (Rev 1).nes",
]

print("=== SIMULAÇÃO DA TELA 'INFO DA ROM' NO EVERDRIVE N8 (PT-BR) ===")
for p in samples:
    info = parse_rom_info(p)
    if not info:
        continue
    print(f"\n[ {info['file']} ]")
    print("  +----------------------+ ")
    print("  |     Info Arquivo     | ")
    print("  |                      | ")
    print(f"  | Mapper:   {info['mapper']:<11}| ")
    print(f"  | Tam. PRG: {str(info['prg_kb']) + 'K':<11}| ")
    print(f"  | Tam. CHR: {str(info['chr_kb']) + 'K':<11}| ")
    print(f"  | Memória:  {info['memory']:<11}| ")
    print(f"  | Espelho:  {info['mirror']:<11}| ")
    print("  +----------------------+ ")
