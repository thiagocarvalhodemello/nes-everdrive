"""
End-to-end test for per-game covers (game menu and ROM info popup).

Builds a throwaway SD card (temp dir) with:
  * a ROM that has art in EDFC/ARTS/<fingerprint>.BIN (synthetic test image)
  * a ROM without art
boots EDFC/OS.BIN, opens "Info da ROM" for each and checks:
  * art ROM: 48 sprites at x=192/y=48, 8x16 mode, sprite rendering on,
    CHR $1000 and sprite palettes match the art file, C stack balanced,
    art code never writes $6000-$7FFF itself, sprites off after closing
  * no-art ROM: popup unchanged, no sprites, returns normally
  * the browser and theme switching still work afterwards

Usage: python tools/test_game_art.py [--shot out.png]
"""
import os, sys, shutil, tempfile

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
from edfc_emu import EverDriveN8Emu
import nes_art

ART_CODE = range(0x73D0, 0x8000)     # far code in bank $0B (art_runtime + fav_runtime)
TRAMP = range(0x0100, 0x01B0)


def make_rom(seed, mapper=0):
    import random
    r = random.Random(seed)
    hdr = b"NES\x1a\x02\x01" + bytes([(mapper & 15) << 4, mapper & 0xF0]) + bytes(8)
    return hdr + bytes(r.randrange(256) for _ in range(32768 + 8192))


def test_image():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (128, 192), (20, 40, 160))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 127, 40], fill=(220, 30, 30))
    d.ellipse([24, 60, 104, 140], fill=(250, 220, 40))
    d.rectangle([10, 150, 118, 182], fill=(240, 240, 240))
    return img


def build_sd(root, art_rom, plain_rom, art):
    os.makedirs(os.path.join(root, "EDFC", "MAPS"))
    os.makedirs(os.path.join(root, "EDFC", "SAVE"))
    os.makedirs(os.path.join(root, "EDFC", "ARTS"))
    shutil.copy(os.path.join(REPO, "EDFC", "MAPROUT.BIN"), os.path.join(root, "EDFC"))
    for f in ("000.RBF", "001.RBF"):
        shutil.copy(os.path.join(REPO, "EDFC", "MAPS", f), os.path.join(root, "EDFC", "MAPS"))
    open(os.path.join(root, "EDFC", "SAVE", "KEEP.TXT"), "wb").write(b"x")
    open(os.path.join(root, "Test Game With Art (World).nes"), "wb").write(art_rom)
    open(os.path.join(root, "ZZ No Art (World).nes"), "wb").write(plain_rom)
    open(os.path.join(root, "EDFC", "ARTS", nes_art.art_filename(art_rom)), "wb").write(art)


class Watch:
    def __init__(self, emu):
        self.bad_writes = []
        self.sp_hook = []                       # (sp at $CFB2 entry, sp at $CFB5 return)
        w, step = emu.write, emu.step

        def stepper():
            if emu.PC in (0xCFB2, 0xCFB5):
                self.sp_hook.append((emu.PC, emu.ram[0x28] | emu.ram[0x29] << 8))
            step()
        emu.step = stepper

        def write(a, v):
            a &= 0xFFFF
            if 0x6000 <= a < 0x8000 and (emu.PC in ART_CODE or emu.PC in TRAMP) \
                    and (emu.reg_data[0x81] & 0x3F) != 0x0B:
                self.bad_writes.append((emu.PC, a))
            w(a, v)
        emu.write = write


def select_file(emu, name_prefix):
    for _ in range(30):
        line = [l for l in emu.dump_screen_text().split("\n") if l.startswith("28:")]
        if line and name_prefix in line[0]:
            return
        emu.press_button(0x04, wait_frames=15)
    raise AssertionError(f"file {name_prefix!r} not found in browser")


def open_game_menu(emu, name_prefix):
    select_file(emu, name_prefix)
    emu.press_button(0x40, wait_frames=60)                       # confirm (B): game menu


def open_rom_info(emu, name_prefix):
    open_game_menu(emu, name_prefix)
    emu.press_button(0x04, wait_frames=15)                       # -> "Info da ROM"
    emu.press_button(0x40, wait_frames=60)


def close_popup(emu):
    emu.press_button(0x80, wait_frames=30)                       # A: close popup
    if "Menu Arquivo" in emu.dump_screen_text():
        emu.press_button(0x80, wait_frames=30)                   # A: leave the game menu


def page3(emu):
    """OS DATA segment in RAM, minus $0360-$037F (variables the OS itself updates)."""
    return bytes(emu.ram[0x300:0x360]) + bytes(emu.ram[0x380:0x400])


def main(shot=None):
    os.chdir(REPO)
    art_rom, plain_rom = make_rom(1), make_rom(2)
    art = nes_art.convert(test_image())
    failures = 0

    def expect(cond, msg):
        nonlocal failures
        print(("  [OK]   " if cond else "  [FAIL] ") + msg)
        failures += 0 if cond else 1

    def check_art(emu, label):
        oam = emu.oam
        expect(emu.ppu_mask & 0x10 and emu.ppu_ctrl & 0x20,
               f"{label}: sprites on, 8x16 (mask=${emu.ppu_mask:02X} ctrl=${emu.ppu_ctrl:02X})")
        expect(oam[0] == 47 and oam[1] == 1 and oam[3] == 192 and oam[47 * 4] == 47 + 80 and oam[47 * 4 + 3] == 248
               and all(oam[i * 4] >= 0xEF for i in range(48, 64)),
               f"{label}: OAM layout 64x96 at (192,48), unused sprites hidden")
        pal = art[0x604:0x610]
        got = bytes(emu.palette[0x11 + k * 4 + j] for k in range(4) for j in range(3))
        expect(bytes(emu.chr_ram[0x1000:0x1600]) == art[:0x600] and got == pal
               and all(oam[i * 4 + 2] == art[0x610 + i] for i in range(48)),
               f"{label}: CHR tiles, palettes and attributes from the art file")

    with tempfile.TemporaryDirectory() as root:
        build_sd(root, art_rom, plain_rom, art)
        emu = EverDriveN8Emu(os.path.join(REPO, "EDFC", "OS.BIN"), root)
        watch = Watch(emu)
        emu.run_frames(40)
        emu.press_button(0x80, wait_frames=40)
        emu.run_frames(20)
        p3 = page3(emu)

        # --- game menu: cover + "Carregar jogo" + "Info da ROM"
        open_game_menu(emu, "Test Game")
        txt = emu.dump_screen_text()
        expect("Carregar jogo" in txt and "Info da ROM" in txt and "Apenas" not in txt and "Sel. e" not in txt,
               "game menu items: Carregar jogo, Info da ROM")
        check_art(emu, "game menu")
        if shot:
            emu.render_screen(shot, scale=2)
            print(f"  screenshot -> {shot}")

        # --- "Info da ROM" from the game menu: popup + cover again
        emu.press_button(0x04, wait_frames=15)
        emu.press_button(0x40, wait_frames=60)
        expect("Info Arquivo" in emu.dump_screen_text(), "Info da ROM opens from the game menu")
        check_art(emu, "ROM info")
        close_popup(emu)
        sp = watch.sp_hook[-2:]
        expect(len(sp) == 2 and sp[0][0] == 0xCFB2 and sp[1][0] == 0xCFB5 and sp[0][1] == sp[1][1],
               f"C stack balanced across the ROM info hook ({[(hex(a), hex(b)) for a, b in sp]})")
        expect(emu.ppu_mask == 0x0A, f"sprites off after closing (mask=${emu.ppu_mask:02X})")
        txt = emu.dump_screen_text()
        expect("Info Arquivo" not in txt and "Menu Arquivo" not in txt, "back in the browser")

        # --- ROM without art: menu works, no sprites
        open_game_menu(emu, "ZZ No Art")
        expect("Carregar jogo" in emu.dump_screen_text() and not (emu.ppu_mask & 0x10),
               "no-art ROM: game menu shown without sprites")
        close_popup(emu)
        expect("Menu Arquivo" not in emu.dump_screen_text(), "no-art ROM: menu closed")

        # --- OS state untouched, theme key still works
        expect(page3(emu) == p3, "OS DATA segment ($0300-$03FF) unchanged by the cover code")
        before = emu.prg_ram[15][0xFAE5 - 0xE000]
        emu.press_button(0x20, hold_frames=3, wait_frames=40)
        expect(emu.prg_ram[15][0xFAE5 - 0xE000] == (before + 1) % 9, "SELECT theme switch still works")
        expect(not watch.bad_writes, f"art code wrote no OS work RAM ({watch.bad_writes[:3]})")

        # --- LEFT/RIGHT in the game menu: previous/next .nes/.fds (folders, .TXT, .SAV skipped, wraps)
        # card (sorted): EDFC/ CHEATS.TXT MARIO.NES MARIO.SAV Test Game ZELDA.FDS ZZ No Art
        status = lambda: str([l for l in emu.dump_screen_text().splitlines() if l.startswith("28:")])
        loop_sp, step0 = [], emu.step

        def at_loop():                                           # C sp at the top of the browser loop
            if emu.PC == 0xD89E:
                loop_sp.append(emu.ram[0x28] | emu.ram[0x29] << 8)
            step0()
        emu.step = at_loop
        select_file(emu, "Test Game")
        emu.press_button(0x40, wait_frames=60)
        seen = []
        for btn in (0x01, 0x01, 0x01, 0x02, 0x02, 0x02):
            emu.press_button(btn, wait_frames=90)
            seen.append((status()[7:17], "Carregar jogo" in emu.dump_screen_text(), bool(emu.ppu_mask & 0x10)))
        want = [("ZELDA   FD", True, False), ("ZZ No Art ", True, False), ("MARIO   NE", True, False),
                ("ZZ No Art ", True, False), ("ZELDA   FD", True, False), ("Test Game ", True, True)]
        expect(seen == want, f"RIGHT/LEFT switch games, skip non-games, wrap, cover follows ({seen})")
        close_popup(emu)
        emu.press_button(0x04, wait_frames=15)
        emu.step = step0
        expect(len(set(loop_sp)) == 1, f"C stack balanced after switching games ({sorted(set(map(hex, loop_sp)))})")
        expect(page3(emu) == p3, "OS DATA segment unchanged after switching games")
        open_game_menu(emu, "Test Game")
        emu.press_button(0x01, wait_frames=90)                   # -> ZELDA, then "Carregar jogo"
        reached = []
        step = emu.step

        def stop_at_launch():
            if emu.PC == 0xB7AC:
                rec = emu.ram[0x46A] | emu.ram[0x46B] << 8
                reached.append(bytes(emu.read(rec + 10 + i) for i in range(9)))
                raise StopIteration
            step()
        emu.step = stop_at_launch
        try:
            emu.press_button(0x40, wait_frames=60)               # Carregar jogo
        except StopIteration:
            pass
        emu.step = step
        expect(reached == [b"ZELDA   F"], f"Carregar jogo after switching starts the switched game ({reached})")

    with tempfile.TemporaryDirectory() as root:
        build_sd(root, art_rom, plain_rom, art)
        emu = EverDriveN8Emu(os.path.join(REPO, "EDFC", "OS.BIN"), root)
        emu.run_frames(40)
        emu.press_button(0x80, wait_frames=40)
        emu.run_frames(20)

        # --- "Carregar jogo" starts the game through the OS ($BF16 select, $B7AC start)
        open_game_menu(emu, "Test Game")
        reached = []
        step = emu.step

        def stop_at_start():
            if emu.PC in (0xBF16, 0xB7AC):
                reached.append((emu.PC, emu.ppu_mask))
                if emu.PC == 0xB7AC:
                    raise StopIteration
            step()
        emu.step = stop_at_start
        try:
            emu.press_button(0x40, wait_frames=60)
        except StopIteration:
            pass
        emu.step = step
        expect([r[0] for r in reached][-2:] == [0xBF16, 0xB7AC] and reached[-1][1] == 0x0A,
               f"Carregar jogo -> OS select + start, cover hidden first ({[(hex(a), hex(m)) for a, m in reached]})")

    print(f"\n{'PASSED' if failures == 0 else f'FAILED ({failures})'}")
    return failures


if __name__ == "__main__":
    shot = sys.argv[sys.argv.index("--shot") + 1] if "--shot" in sys.argv else None
    sys.exit(1 if main(shot) else 0)
