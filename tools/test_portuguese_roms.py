import os
import struct

rom_dir = r"sdcard\4 Traduzidos\Potugues A-Z"
maprout_path = r"EDFC\MAPROUT.BIN"
maps_dir = r"EDFC\MAPS"

with open(maprout_path, "rb") as f:
    maprout = f.read()

avail_rbfs = set(os.listdir(maps_dir))

total = 0
supported_count = 0
unsupported = []
mapper_counts = {}

for f in sorted(os.listdir(rom_dir)):
    if not f.lower().endswith(".nes"):
        continue
    total += 1
    full_path = os.path.join(rom_dir, f)
    with open(full_path, "rb") as rf:
        hdr = rf.read(16)
    if hdr[:4] != b"NES\x1a":
        unsupported.append((f, "Header inválido"))
        continue

    prg_pages = hdr[4]
    chr_pages = hdr[5]
    f6 = hdr[6]
    f7 = hdr[7]
    mapper = (f6 >> 4) | (f7 & 0xF0)
    has_battery = bool(f6 & 0x02)
    mirror = "V" if (f6 & 0x01) else "H"
    if f6 & 0x08:
        mirror = "4"

    rbf_id = maprout[mapper]
    rbf_name = f"{rbf_id:03d}.RBF"
    is_supported = rbf_name in avail_rbfs

    mapper_counts[mapper] = mapper_counts.get(mapper, 0) + 1

    if is_supported:
        supported_count += 1
    else:
        unsupported.append((f, f"Mapper {mapper} -> {rbf_name} ausente"))

print(f"=== RESULTADO DOS TESTES COM ROMS PT-BR ===")
print(f"Total de ROMs testadas: {total}")
print(f"ROMs suportadas com sucesso: {supported_count} ({supported_count/total*100:.1f}%)")
print(f"ROMs não suportadas: {len(unsupported)}")

print("\nDistribuição de Mappers das ROMs PT-BR:")
for m in sorted(mapper_counts.keys()):
    rbf = f"{maprout[m]:03d}.RBF"
    status = "OK" if rbf in avail_rbfs else "AUSENTE"
    print(f"  Mapper {m:3d}: {mapper_counts[m]:3d} jogos -> Core {rbf} [{status}]")

if unsupported:
    print("\nJogos não suportados:")
    for name, reason in unsupported:
        print(f"  - {name}: {reason}")
