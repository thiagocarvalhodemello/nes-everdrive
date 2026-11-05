"""
Builds the two release archives into releases/ (extract either at the SD root):

  EDFC-N8-PTBR-v<ver>.zip            the system (OS, mapper cores, routing table, SAVE)
  EDFC-N8-PTBR-v<ver>-com-capas.zip  the same + EDFC/ARTS covers

--arts DIR: folder containing EDFC/ARTS, e.g. the output of
    python tools/art_pack.py install --sd DIR --roms <collection>

Usage: python tools/package_releases.py --version 1.5 --arts DIR
"""
import argparse, os, zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "releases")

# what goes on the card besides EDFC/MAPS: the OS, the mapper routing table, the mapper chart
SD_FILES = ["EDFC/OS.BIN", "EDFC/MAPROUT.BIN", "EDFC/mappers.png", "EDFC/FAVS.DAT"]

README_SD = """EverDrive N8 - OS PT-BR v{ver} (placas clone V3.1 / Cyclone II)

Instalacao: extraia este .zip na RAIZ do cartao MicroSD (FAT16/FAT32).
Deve ficar:  EDFC/OS.BIN, EDFC/MAPROUT.BIN, EDFC/FAVS.DAT, EDFC/MAPS/*.RBF, EDFC/SAVE/{arts}

Controles no navegador de arquivos:
  A/B (confirmar)  menu do jogo: capa, Carregar jogo, Info da ROM, Favoritar
  SELECT           proximo tema (9 temas, fica salvo)
  START            Menu Principal (Opcoes, Trapacas, Info Sistema, ..., Favoritos)

Favoritos ficam em EDFC/FAVS.DAT (ate 32). Ao ATUALIZAR o sistema, nao
substitua o FAVS.DAT do cartao se quiser manter a sua lista.
"""


def _system(z):
    for f in SD_FILES:
        z.write(os.path.join(REPO, f), f)
    maps = os.path.join(REPO, "EDFC", "MAPS")
    for f in sorted(os.listdir(maps)):
        z.write(os.path.join(maps, f), f"EDFC/MAPS/{f}")
    z.writestr("EDFC/SAVE/", "")            # the OS refuses to start without it


def build(ver, arts_root=None):
    os.makedirs(OUT, exist_ok=True)
    out = []
    path = os.path.join(OUT, f"EDFC-N8-PTBR-v{ver}.zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        _system(z)
        z.writestr("LEIA-ME.txt", README_SD.format(ver=ver, arts=""))
    out.append(path)
    if arts_root:
        src = os.path.join(arts_root, "EDFC", "ARTS")
        arts = sorted(os.listdir(src))
        path = os.path.join(OUT, f"EDFC-N8-PTBR-v{ver}-com-capas.zip")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            _system(z)
            for f in arts:
                z.write(os.path.join(src, f), f"EDFC/ARTS/{f}")
            z.writestr("LEIA-ME.txt", README_SD.format(
                ver=ver, arts=f", EDFC/ARTS/ ({len(arts)} capas)\n"
                "Capas: libretro-thumbnails, direitos dos respectivos detentores."))
        out.append(path)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--arts")
    a = ap.parse_args()
    for p in build(a.version, a.arts):
        print(f"  {os.path.relpath(p, REPO)}  ({os.path.getsize(p) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
