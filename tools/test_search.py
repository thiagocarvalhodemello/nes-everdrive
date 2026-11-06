"""
End-to-end test for the search (main menu -> Busca, overlay EDFC/OVLFIND.BIN).

SD card (temp dir): a folder, ROMs "Alpha Quest", "Beta Racer", "Super Alpha Bros",
"zeta alpha (lower case)", a .TXT.
Checks:
  * main menu: Lista de jogos first, Busca second; Busca opens the keyboard
  * typing A-L-P-H-A with the d-pad + confirm, SELECT erases, START searches
  * results: the 3 names containing "alpha" (case-insensitive), not Beta
  * confirm on a result: back in the browser with that file selected (status bar)
  * "ZZQ" -> "Nada encontrado nesta pasta."
  * nothing written to the card, OS DATA page $0300 unchanged, heap pointer restored
  * missing OVLFIND.BIN -> message, menu still works

Usage: python tools/test_search.py
"""
import os, sys, shutil, tempfile

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
from edfc_emu import EverDriveN8Emu
from find_runtime import KEYS, KCOLS
from test_favorites import make_rom

UP, DOWN, LEFT, RIGHT, SELECT, START, B, A = 0x08, 0x04, 0x02, 0x01, 0x20, 0x10, 0x40, 0x80
NAMES = ["Alpha Quest (World).nes", "Beta Racer (World).nes", "Super Alpha Bros (USA).nes",
         "zeta alpha (lower case).nes"]


def build_sd(root, find=True):
    os.makedirs(os.path.join(root, "EDFC", "MAPS"))
    os.makedirs(os.path.join(root, "EDFC", "SAVE"))
    os.makedirs(os.path.join(root, "Hacks"))
    shutil.copy(os.path.join(REPO, "EDFC", "MAPROUT.BIN"), os.path.join(root, "EDFC"))
    for f in ("000.RBF", "001.RBF"):
        shutil.copy(os.path.join(REPO, "EDFC", "MAPS", f), os.path.join(root, "EDFC", "MAPS"))
    files = ["OVLART.BIN", "OVLFAV.BIN", "OVLREC.BIN", "RECENTS.DAT", "FAVS.DAT"] + (["OVLFIND.BIN"] if find else [])
    for f in files:
        shutil.copy(os.path.join(REPO, "EDFC", f), os.path.join(root, "EDFC"))
    open(os.path.join(root, "EDFC", "SAVE", "KEEP.TXT"), "wb").write(b"x")
    open(os.path.join(root, "notes.txt"), "wb").write(b"alpha notes")
    for i, n in enumerate(NAMES):
        open(os.path.join(root, n), "wb").write(make_rom(10 + i))


def screen(emu):
    return emu.dump_screen_text()


def type_text(emu, text, pos):
    """d-pad from pos (col,row) to each key and confirm; returns the final pos"""
    cx, cy = pos
    for ch in text:
        i = KEYS.index(ch.encode())
        tx, ty = i % KCOLS, i // KCOLS
        while cy < ty:
            emu.press_button(DOWN, wait_frames=12); cy += 1
        while cy > ty:
            emu.press_button(UP, wait_frames=12); cy -= 1
        while cx < tx:
            emu.press_button(RIGHT, wait_frames=12); cx += 1
        while cx > tx:
            emu.press_button(LEFT, wait_frames=12); cx -= 1
        emu.press_button(B, wait_frames=12)
    return cx, cy


def open_search(emu):
    emu.press_button(START, wait_frames=60)
    emu.press_button(DOWN, wait_frames=15)
    emu.press_button(B, wait_frames=150)


def main():
    os.chdir(REPO)
    failures = 0

    def expect(cond, msg):
        nonlocal failures
        print(("  [OK]   " if cond else "  [FAIL] ") + msg)
        failures += 0 if cond else 1

    with tempfile.TemporaryDirectory() as root:
        build_sd(root)
        emu = EverDriveN8Emu(os.path.join(REPO, "EDFC", "OS.BIN"), root)
        expect(emu.boot_to_main_menu(), "main menu opens by itself after boot")
        lines = [l for l in screen(emu).splitlines() if l.strip()]
        items = [k for l in lines for k in ("Lista de jogos", "Busca", "Favoritos", "Recentes", "Sobre") if k in l]
        expect(items[:4] == ["Lista de jogos", "Busca", "Favoritos", "Recentes"] and "Sobre" in items,
               f"main menu: Lista de jogos, Busca, Favoritos, Recentes, ... Sobre ({items})")
        emu.press_button(B, wait_frames=60)                    # "Lista de jogos" closes the menu
        expect("Menu Principal" not in screen(emu) and "Alpha" in screen(emu), "Lista de jogos -> browser")
        img0 = bytes(emu.sd_img)
        p3 = bytes(emu.ram[0x300:0x360]) + bytes(emu.ram[0x380:0x400])
        heap = emu.ram[0x450] | emu.ram[0x451] << 8

        open_search(emu)
        txt = screen(emu)
        expect("Busca" in txt and "Nome: _" in txt and "[A]" in txt, "Busca: keyboard with the cursor on A")
        pos = type_text(emu, "ALPX", (0, 0))
        emu.press_button(SELECT, wait_frames=12)                # erase the X
        pos = type_text(emu, "HA", pos)
        expect("Nome: ALPHA_" in screen(emu), "typed ALPHA (SELECT erased a letter)")
        emu.press_button(START, wait_frames=200)
        txt = screen(emu)
        found = [n for n in NAMES if n[:20] in txt]
        expect("Resultados" in txt and found == [NAMES[0], NAMES[2], NAMES[3]],
               f"results: names containing 'alpha', case-insensitive ({found})")
        emu.press_button(DOWN, wait_frames=15)
        emu.press_button(B, wait_frames=120)                    # -> "Super Alpha Bros"
        txt = screen(emu)
        status = [l for l in txt.splitlines() if l.startswith("28:")]
        expect("Menu Principal" not in txt and status and "Super Alpha Bros" in status[0],
               f"result chosen: browser with it selected ({status})")
        emu.press_button(B, wait_frames=90)
        expect("Carregar jogo" in screen(emu) and "Super Alpha" in screen(emu), "its game menu opens")
        emu.press_button(A, wait_frames=60)

        open_search(emu)
        type_text(emu, "ZZQ", (0, 0))
        emu.press_button(START, wait_frames=200)
        expect("Nada encontrado nesta pasta." in screen(emu), "no match -> message")
        emu.press_button(B, wait_frames=60)
        expect("Nome: ZZQ_" in screen(emu), "back to the keyboard with the query")
        emu.press_button(A, wait_frames=90)
        expect("Menu Principal" in screen(emu), "cancel -> main menu")
        emu.press_button(A, wait_frames=60)
        expect(bytes(emu.sd_img) == img0, "search wrote nothing to the card")
        expect(bytes(emu.ram[0x300:0x360]) + bytes(emu.ram[0x380:0x400]) == p3, "OS DATA page $0300 unchanged")
        expect(emu.ram[0x450] | emu.ram[0x451] << 8 == heap, "heap pointer restored")

    with tempfile.TemporaryDirectory() as root:
        build_sd(root, find=False)
        emu = EverDriveN8Emu(os.path.join(REPO, "EDFC", "OS.BIN"), root)
        emu.boot_to_browser()
        open_search(emu)
        expect("Falta EDFC/OVL*.BIN" in screen(emu), "missing OVLFIND.BIN -> message")
        emu.press_button(B, wait_frames=60)
        expect("Menu Principal" in screen(emu), "back in the main menu")

    print(f"\n{'PASSED' if failures == 0 else f'FAILED ({failures})'}")
    return failures


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
