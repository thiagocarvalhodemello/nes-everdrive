"""
Screenshots of the main menu (shown after boot), the search (keyboard + results) and
the Recentes list, rendered by the emulator from the built EDFC/OS.BIN + EDFC/OVL*.BIN.

Usage: python tools/capture_menu_screenshots.py  ->  docs/screenshots/{menu_principal,
       busca_teclado,busca_progresso,busca_resultados,recentes}.png
"""
import os, re, sys, struct, tempfile

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
from edfc_emu import EverDriveN8Emu
from fav_runtime import favs_dat
import test_search as ts

OUT = os.path.join(REPO, "docs", "screenshots")
GAMES = ["Castlevania (USA).nes", "Contra (USA).nes", "Mega Man 2 (USA).nes", "Mega Man 3 (USA).nes",
         "Mega Man 4 (USA).nes", "Metroid (USA).nes", "Super Mario Bros. 3 (USA).nes", "Zelda II (USA).nes"]


def recents_dat(names):
    d = bytearray(favs_dat())
    for k, n in enumerate(names):
        o = k * 512
        struct.pack_into("<I", d, o, 0x7000 + k)
        d[o + 10:o + 10 + len(n)] = n.encode()
        d[o + 271] = len(names) - k            # first name = most recent
    return bytes(d)


def main():
    os.chdir(REPO)
    with tempfile.TemporaryDirectory() as root:
        ts.build_sd(root)
        for n in ts.NAMES:
            os.remove(os.path.join(root, n))
        for i, n in enumerate(GAMES):
            open(os.path.join(root, n), "wb").write(ts.make_rom(40 + i))
        for d, n in (("Hacks", "Mega Man 2 - Turbo (Hack).nes"), ("Japao", "Rockman 2 (Japan).nes"),
                     ("Japao", "Mega Man 3 (Japan) [T-Port].nes"), ("Prototipos", "Mega Man 5 (Proto).nes")):
            os.makedirs(os.path.join(root, d), exist_ok=True)
            open(os.path.join(root, d, n), "wb").write(ts.make_rom(len(n)))
        open(os.path.join(root, "EDFC", "RECENTS.DAT"), "wb").write(
            recents_dat(["Mega Man 2 (USA).nes", "Contra (USA).nes", "Metroid (USA).nes"]))
        emu = EverDriveN8Emu(os.path.join(REPO, "EDFC", "OS.BIN"), root)
        emu.boot_to_main_menu()
        emu.render_screen(os.path.join(OUT, "menu_principal.png"), scale=2)
        emu.press_button(0x80, wait_frames=60)
        ts.open_search(emu)
        ts.type_text(emu, "MEGA", (0, 0))
        emu.render_screen(os.path.join(OUT, "busca_teclado.png"), scale=2)
        emu.press_button(0x10, wait_frames=1)
        for _ in range(400):                    # progress: grab it after the 3rd folder
            emu.run_frames(1)
            t = emu.dump_screen_text()
            if re.search(r"Pastas lidas: +3 de", t):
                emu.render_screen(os.path.join(OUT, "busca_progresso.png"), scale=2)
                break
        emu.run_frames(200)
        emu.render_screen(os.path.join(OUT, "busca_resultados.png"), scale=2)
        emu.press_button(0x80, wait_frames=60)
        emu.press_button(0x80, wait_frames=90)
        for _ in range(2):
            emu.press_button(0x04, wait_frames=15)
        emu.press_button(0x40, wait_frames=200)
        emu.render_screen(os.path.join(OUT, "recentes.png"), scale=2)
    for n in ("menu_principal", "busca_teclado", "busca_progresso", "busca_resultados", "recentes"):
        print(f"  docs/screenshots/{n}.png")


if __name__ == "__main__":
    main()
