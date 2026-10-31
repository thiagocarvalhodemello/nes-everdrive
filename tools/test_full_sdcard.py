import os
import struct

base_sd = "sdcard"
maprout_path = r"EDFC\MAPROUT.BIN"
maps_dir = r"EDFC\MAPS"

with open(maprout_path, "rb") as f:
    maprout = f.read()

avail_rbfs = set(os.listdir(maps_dir))

categories = [
    "1 US - A-F",
    "1 US - G-Q",
    "1 US - R-Z",
    "2 Europe - A-Z",
    "2 Japan - A-Z",
    "4 Traduzidos",
]

print("=== TESTE GERAL DE COMPATIBILIDADE DA PASTA SDCARD ===")
overall_total = 0
overall_supported = 0

for cat in categories:
    cat_path = os.path.join(base_sd, cat)
    if not os.path.exists(cat_path):
        continue
    cat_total = 0
    cat_supported = 0
    cat_unsupported = []
    for root, dirs, files in os.walk(cat_path):
        for f in files:
            if not f.lower().endswith(".nes"):
                continue
            cat_total += 1
            full_path = os.path.join(root, f)
            try:
                with open(full_path, "rb") as rf:
                    hdr = rf.read(16)
                if hdr[:4] != b"NES\x1a":
                    cat_unsupported.append((f, "Header inválido"))
                    continue
                mapper = (hdr[6] >> 4) | (hdr[7] & 0xF0)
                rbf_id = maprout[mapper]
                rbf_name = f"{rbf_id:03d}.RBF"
                if rbf_name in avail_rbfs:
                    cat_supported += 1
                else:
                    cat_unsupported.append((f, f"Mapper {mapper} -> {rbf_name}"))
            except Exception as e:
                cat_unsupported.append((f, str(e)))

    overall_total += cat_total
    overall_supported += cat_supported
    pct = (cat_supported / cat_total * 100) if cat_total > 0 else 0
    print(f"Pasta '{cat}':")
    print(f"  Total de ROMs: {cat_total}")
    print(f"  Suportadas: {cat_supported} ({pct:.1f}%)")
    if cat_unsupported:
        print(f"  Não suportadas: {len(cat_unsupported)} (ex: {cat_unsupported[0][0]}: {cat_unsupported[0][1]})")
    print("-" * 55)

print(f"\nTOTAL GERAL TESTADO: {overall_total} jogos")
print(f"TOTAL SUPORTADOS COM SUCESSO: {overall_supported} ({overall_supported/overall_total*100:.1f}%)")
