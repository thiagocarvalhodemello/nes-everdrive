"""
End-to-end test for the search (main menu -> Busca, overlay EDFC/OVLFIND.BIN).

SD card (temp dir): ROMs "Alpha Quest", "Beta Racer", "Super Alpha Bros",
"zeta alpha (lower case)", a .TXT; Hacks/ with "Alpha Hack" .nes, an "alpha" .sav, a plain
8.3 ALPHAZ.NES (no long name), "Zeta Alpha Two" .nes and Hacks/Deep/"Alpha Deep" .fds; an
"ALPHA" .NES inside EDFC (system folder, never searched). The root goes through the OS ($923B),
the subfolders through the module's own directory parser.
Checks:
  * main menu: Lista de jogos first, Busca second; Busca opens the keyboard
  * typing A-L-P-H-A with the d-pad + confirm, SELECT erases, START searches
  * progress screen while every folder is scanned
  * results: the 5 .nes/.fds names containing "alpha" (any case) in all folders (not Beta,
    the .sav, the .TXT or anything in EDFC)
  * confirm on a result: back in the browser with that file selected (status bar), also in
    a subfolder two levels down; cancel then walks back up to Hacks and the root
  * "ZZQ" -> "Nada encontrado."
  * nothing written to the card, OS DATA page $0300 unchanged, heap pointer restored
  * a subfolder longer than one cluster: every entry once (the cluster walk pointer must be
    internal RAM: $C404 runs with bank 8 mapped)
  * page 1 wiped while in the browser (a reset after a game): the main menu opens again, no crash
  * missing OVLFIND.BIN -> message, menu still works

Usage: python tools/test_search.py
"""
import os, sys, shutil, tempfile

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
from edfc_emu import EverDriveN8Emu
from testparts import part
from find_runtime import KEYS, KCOLS
from test_favorites import make_rom

UP, DOWN, LEFT, RIGHT, SELECT, START, B, A = 0x08, 0x04, 0x02, 0x01, 0x20, 0x10, 0x40, 0x80
NAMES = ["Alpha Quest (World).nes", "Beta Racer (World).nes", "Super Alpha Bros (USA).nes",
         "zeta alpha (lower case).nes"]
SUB = [("Hacks", "Alpha Hack (Hack).nes"), ("Hacks", "alpha save.sav"),
       (os.path.join("Hacks", "Deep"), "Alpha Deep (Hack).fds"), ("EDFC", "ALPHAX.NES"),
       ("Hacks", "ALPHAZ.NES"), ("Hacks", "Zeta Alpha Two (Hack).nes")]
FOUND = [NAMES[0], NAMES[2], NAMES[3], SUB[0][1], SUB[2][1], "ALPHAZ  NES", SUB[5][1]]


def build_sd(root, find=True):
    os.makedirs(os.path.join(root, "EDFC", "MAPS"))
    os.makedirs(os.path.join(root, "EDFC", "SAVE"))
    os.makedirs(os.path.join(root, "Hacks"))
    shutil.copy(os.path.join(REPO, "EDFC", "MAPROUT.BIN"), os.path.join(root, "EDFC"))
    for f in ("000.RBF", "001.RBF"):
        shutil.copy(os.path.join(REPO, "EDFC", "MAPS", f), os.path.join(root, "EDFC", "MAPS"))
    files = ["OVLART.BIN", "OVLFAV.BIN", "OVLREC.BIN", "RECENTS.DAT", "FAVS.DAT"] + (["OVLFIND.BIN", "OVLSCAN.BIN"] if find else [])
    for f in files:
        shutil.copy(os.path.join(REPO, "EDFC", f), os.path.join(root, "EDFC"))
    open(os.path.join(root, "EDFC", "SAVE", "KEEP.TXT"), "wb").write(b"x")
    open(os.path.join(root, "notes.txt"), "wb").write(b"alpha notes")
    os.makedirs(os.path.join(root, "Hacks", "Deep"))
    for i, (d, n) in enumerate(SUB):
        open(os.path.join(root, d, n), "wb").write(make_rom(30 + i))
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


def choose(emu, name):
    """pick the search result whose row contains name; -> (screen, status bar lines)"""
    rows = [l for l in screen(emu).splitlines() if "lpha" in l.lower() and "Resultados" not in l and "Nome" not in l]
    k = next(i for i, l in enumerate(rows) if name[:20] in l)
    for _ in range(k):
        emu.press_button(DOWN, wait_frames=15)
    emu.press_button(B, wait_frames=150)
    t = screen(emu)
    return t, [l for l in t.splitlines() if l.startswith("28:")]


def main():
    os.chdir(REPO)
    failures = 0

    def expect(cond, msg):
        nonlocal failures
        print(("  [OK]   " if cond else "  [FAIL] ") + msg)
        failures += 0 if cond else 1

    for root in part(1):
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
        sp = [0x800]
        step0 = emu.step

        def step():
            sp[0] = min(sp[0], emu.ram[0x28] | emu.ram[0x29] << 8)
            return step0()
        emu.step = step
        emu.press_button(START, wait_frames=1)
        seen = ""
        for _ in range(400):
            emu.run_frames(1)
            t = screen(emu)
            if "Buscando" in t and "Pastas lidas:" in t:
                seen = t
            if "Resultados" in t:
                break
        expect("Buscando em todas as pastas" in seen and "Encontrados:" in seen and " de " in seen,
               "progress screen during the scan")
        emu.run_frames(30)
        emu.step = step0
        expect(0x700 <= sp[0] < 0x800, f"cc65 stack stays above the sector buffer $0500-$06FF (lowest ${sp[0]:04X})")
        txt = screen(emu)
        found = [n for n in FOUND + [NAMES[1], SUB[1][1], "ALPHAX"] if n[:20] in txt]
        expect("Resultados" in txt and sorted(found) == sorted(FOUND) and "ALPHAX" not in txt,
               f"results: .nes/.fds names containing 'alpha' in every folder but EDFC ({found})")

        txt, status = choose(emu, NAMES[2])
        expect("Menu Principal" not in txt and status and "Super Alpha Bros" in status[0],
               f"result chosen: browser with it selected ({status})")
        emu.press_button(B, wait_frames=90)
        expect("Carregar jogo" in screen(emu) and "Super Alpha" in screen(emu), "its game menu opens")
        emu.press_button(A, wait_frames=60)

        open_search(emu)                                        # (the game menu loaded another module)
        type_text(emu, "ALPHA", (0, 0))
        emu.press_button(START, wait_frames=300)
        txt, status = choose(emu, SUB[2][1])
        expect(status and "Alpha Deep" in status[0] and "Alpha Quest" not in txt,
               f"result in Hacks/Deep: browser opens that folder with it selected ({status})")
        emu.press_button(A, wait_frames=120)
        txt = screen(emu)
        expect("Alpha Hack" in txt and "Deep" in txt and "Alpha Quest" not in txt, "cancel -> parent folder Hacks")
        emu.press_button(A, wait_frames=120)
        txt = screen(emu)
        expect("Hacks" in txt and "Alpha Quest" in txt, "cancel again -> root")

        open_search(emu)
        for _ in range(5):
            emu.press_button(SELECT, wait_frames=12)
        type_text(emu, "ZZQ", (0, 0))
        emu.press_button(START, wait_frames=200)
        expect("Nada encontrado." in screen(emu), "no match -> message")
        emu.press_button(B, wait_frames=60)
        expect("Nome: ZZQ_" in screen(emu), "back to the keyboard with the query")
        emu.press_button(A, wait_frames=90)
        expect("Menu Principal" in screen(emu), "cancel -> main menu")
        emu.press_button(A, wait_frames=60)
        expect(bytes(emu.sd_img) == img0, "search wrote nothing to the card")
        expect(bytes(emu.ram[0x300:0x360]) + bytes(emu.ram[0x380:0x400]) == p3, "OS DATA page $0300 unchanged")
        expect(emu.ram[0x450] | emu.ram[0x451] << 8 == heap, "heap pointer restored")

    for root in part(2):              # a folder longer than one cluster
        build_sd(root)
        os.makedirs(os.path.join(root, "Muitos"))
        for i in range(40):                                    # 3 LFN entries + 1 each: 5+ clusters
            open(os.path.join(root, "Muitos", f"Zork Long Name Number {i:03d} (USA).nes"), "wb").write(bytes(16))
        emu = EverDriveN8Emu(os.path.join(REPO, "EDFC", "OS.BIN"), root)
        emu.boot_to_browser()
        open_search(emu)
        type_text(emu, "ZORK", (0, 0))
        emu.press_button(START, wait_frames=400)
        from theme_runtime import B11_CACHE
        b11 = emu.prg_ram[0x0B]
        names = [bytes(b11[B11_CACHE - 0x6000 + 32 * k: B11_CACHE - 0x6000 + 32 * k + 26]).split(bytes(1))[0]
                 for k in range(31)]
        nums = sorted(int(n[22:25]) for n in names if n.startswith(b"Zork"))
        expect(nums == list(range(31)), f"multi-cluster folder: 31 distinct hits 000..030 ({nums[:3]}..{nums[-3:]})")

    for root in part(3):              # reset after a game
        build_sd(root)
        emu = EverDriveN8Emu(os.path.join(REPO, "EDFC", "OS.BIN"), root)
        emu.boot_to_browser()
        import random
        rnd = random.Random(7)                                 # the game used page 1 as its stack;
        for a in range(0x100, 0x1B0):                          # bank $0B (our state) survives the reset
            emu.ram[a] = rnd.randrange(256)
        ok = False
        for _ in range(60):
            emu.run_frames(5)
            if "Menu Principal" in screen(emu):
                ok = True
                break
        expect(ok, "page 1 wiped (reset after a game): no crash, the main menu opens again")
        emu.press_button(A, wait_frames=60)
        expect("Menu Principal" not in screen(emu) and "Alpha" in screen(emu), "... and closes back to the browser")

    for root in part(4):
        build_sd(root, find=False)
        emu = EverDriveN8Emu(os.path.join(REPO, "EDFC", "OS.BIN"), root)
        emu.boot_to_browser()
        open_search(emu)
        expect("Falta EDFC/OVL*.BIN" in screen(emu), "missing OVLFIND.BIN -> message")
        emu.press_button(B, wait_frames=60)
        expect("Menu Principal" in screen(emu), "back in the main menu")

    for root in part(5):              # results inside Hacks: after a folder / an 8.3 name
        build_sd(root)
        emu = EverDriveN8Emu(os.path.join(REPO, "EDFC", "OS.BIN"), root)
        emu.boot_to_browser()
        img0 = bytes(emu.sd_img)
        p3 = bytes(emu.ram[0x300:0x360]) + bytes(emu.ram[0x380:0x400])
        heap = emu.ram[0x450] | emu.ram[0x451] << 8
        for want in (SUB[5][1], "ALPHAZ  NES"):
            open_search(emu)
            type_text(emu, "ALPHA", (0, 0))
            emu.press_button(START, wait_frames=300)
            txt, status = choose(emu, want)
            expect(status and want in status[0], f"result in Hacks: {want!r} selected ({status})")
        expect(bytes(emu.sd_img) == img0, "search wrote nothing to the card (Hacks results)")
        expect(bytes(emu.ram[0x300:0x360]) + bytes(emu.ram[0x380:0x400]) == p3, "OS DATA page $0300 unchanged (Hacks results)")
        expect(emu.ram[0x450] | emu.ram[0x451] << 8 == heap, "heap pointer restored (Hacks results)")

    print(f"\n{'PASSED' if failures == 0 else f'FAILED ({failures})'}")
    return failures


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
