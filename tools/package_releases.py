"""
Builds the release archives into releases/.

  EDFC-N8-PTBR-v<ver>.zip        SD card contents (extract at the card root)
  EDFC-N8-Capas-v<ver>.zip       ready-to-copy covers: EDFC/ARTS/<fingerprint>.BIN
  EDFC-N8-ArtPack-Completo.zip   every libretro NES cover, for tools/art_pack.py install

The covers archives are optional inputs:
  --arts DIR   folder containing EDFC/ARTS (output of `art_pack.py install --sd DIR --roms <collection>`)
  --pack ZIP   output of `art_pack.py build` (default releases/EDFC-ARTPACK-NES.zip)

Usage: python tools/package_releases.py --version 1.4 [--arts DIR] [--pack ZIP]
"""
import argparse, os, shutil, zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "releases")

# what goes on the card: the OS, mapper cores, routing table, the theme demo ROM
SD_FILES = ["EDFC/OS.BIN", "EDFC/MAPROUT.BIN", "EDFC/THEMES.NES", "EDFC/mappers.png", "TEMAS.NES"]

README_SD = """EverDrive N8 - OS PT-BR v{ver} (placas clone V3.1 / Cyclone II)

Instalacao: extraia este .zip na RAIZ do cartao MicroSD (FAT16/FAT32).
Deve ficar:  EDFC/OS.BIN, EDFC/MAPROUT.BIN, EDFC/MAPS/*.RBF, EDFC/SAVE/

Capas dos jogos (opcional): extraia tambem EDFC-N8-Capas-v{ver}.zip na raiz.
Elas aparecem em Menu Arquivo -> Info da ROM.

Temas: SELECT + DIREITA / SELECT + ESQUERDA no navegador de arquivos.
"""


def sd_zip(ver):
    path = os.path.join(OUT, f"EDFC-N8-PTBR-v{ver}.zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in SD_FILES:
            z.write(os.path.join(REPO, f), f)
        maps = os.path.join(REPO, "EDFC", "MAPS")
        for f in sorted(os.listdir(maps)):
            z.write(os.path.join(maps, f), f"EDFC/MAPS/{f}")
        z.writestr("EDFC/SAVE/", "")            # the OS refuses to start without it
        z.writestr("LEIA-ME.txt", README_SD.format(ver=ver))
    return path


def covers_zip(ver, arts_root):
    src = os.path.join(arts_root, "EDFC", "ARTS")
    path = os.path.join(OUT, f"EDFC-N8-Capas-v{ver}.zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(src)):
            z.write(os.path.join(src, f), f"EDFC/ARTS/{f}")
        z.writestr("LEIA-ME-CAPAS.txt",
                   "Capas para a tela Info da ROM (OS PT-BR v1.4+). Extraia na raiz do cartao.\n"
                   "Cada arquivo EDFC/ARTS/<CRC>.BIN corresponde ao CRC-32 dos bytes 512..2559 da ROM,\n"
                   "entao funciona com dumps padrao (No-Intro / GoodNES), qualquer que seja o nome do arquivo.\n"
                   "Para outras colecoes: python tools/art_pack.py install --sd <cartao>\n"
                   "Capas: libretro-thumbnails; direitos dos respectivos detentores.\n")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--arts")
    ap.add_argument("--pack", default=os.path.join(OUT, "EDFC-ARTPACK-NES.zip"))
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    out = [sd_zip(a.version)]
    if a.arts:
        out.append(covers_zip(a.version, a.arts))
    if os.path.exists(a.pack):
        dst = os.path.join(OUT, "EDFC-N8-ArtPack-Completo.zip")
        if os.path.abspath(a.pack) != os.path.abspath(dst):
            shutil.copy(a.pack, dst)
        out.append(dst)
    for p in out:
        print(f"  {os.path.relpath(p, REPO)}  ({os.path.getsize(p) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
