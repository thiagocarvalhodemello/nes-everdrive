"""
End-to-end test for per-game art on the ROM info popup.

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

ART_CODE = range(0x7C90, 0x8000)     # art runtime in bank $0B
TRAMP = range(0x0300, 0x0400)


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


def open_rom_info(emu, name_prefix):
    for _ in range(30):
        line = [l for l in emu.dump_screen_text().split("\n") if l.startswith("25:")]
        if line and name_prefix in line[0]:
            break
        emu.press_button(0x04, wait_frames=15)
    else:
        raise AssertionError(f"file {name_prefix!r} not found in browser")
    emu.press_button(0x40, wait_frames=20)                       # B: file menu
    emu.press_button(0x04, wait_frames=15)
    emu.press_button(0x04, wait_frames=15)                       # -> "Info da ROM"
    emu.press_button(0x40, wait_frames=60)                       # open popup


def close_popup(emu):
    emu.press_button(0x80, wait_frames=30)                       # A: close popup
    if "Menu Arquivo" in emu.dump_screen_text():
        emu.press_button(0x80, wait_frames=30)                   # A: leave file menu


def main(shot=None):
    os.chdir(REPO)
    art_rom, plain_rom = make_rom(1), make_rom(2)
    art = nes_art.convert(test_image())
    failures = 0

    def expect(cond, msg):
        nonlocal failures
        print(("  [OK]   " if cond else "  [FAIL] ") + msg)
        failures += 0 if cond else 1

    with tempfile.TemporaryDirectory() as root:
        build_sd(root, art_rom, plain_rom, art)
        emu = EverDriveN8Emu(os.path.join(REPO, "EDFC", "OS.BIN"), root)
        watch = Watch(emu)
        emu.run_frames(40)
        emu.press_button(0x80, wait_frames=40)
        emu.run_frames(20)

        # --- ROM with art
        open_rom_info(emu, "Test Game")
        expect("Info Arquivo" in emu.dump_screen_text(), "ROM info popup shown")
        expect(emu.ppu_mask & 0x10 and emu.ppu_ctrl & 0x20, f"sprites on, 8x16 (mask=${emu.ppu_mask:02X} ctrl=${emu.ppu_ctrl:02X})")
        oam = emu.oam
        expect(oam[0] == 47 and oam[1] == 1 and oam[3] == 192 and oam[47 * 4] == 47 + 80 and oam[47 * 4 + 3] == 248,
               f"OAM layout 64x96 at (192,48): first={bytes(oam[0:4]).hex()} last={bytes(oam[188:192]).hex()}")
        expect(all(oam[i * 4] >= 0xEF for i in range(48, 64)), "unused sprites hidden")
        expect(bytes(emu.chr_ram[0x1000:0x1600]) == art[:0x600], "CHR $1000 holds the art tiles")
        pal = art[0x604:0x610]
        got = bytes(emu.palette[0x11 + k * 4 + j] for k in range(4) for j in range(3))
        expect(got == pal, f"sprite palettes {got.hex()} == {pal.hex()}")
        expect(all(oam[i * 4 + 2] == art[0x610 + i] for i in range(48)), "per-sprite palette attributes")
        if shot:
            emu.render_screen(shot, scale=2)
            print(f"  screenshot -> {shot}")
        close_popup(emu)
        sp = watch.sp_hook[-2:]
        expect(len(sp) == 2 and sp[0][0] == 0xCFB2 and sp[1][0] == 0xCFB5 and sp[0][1] == sp[1][1],
               f"C stack balanced across the hook ({[(hex(a), hex(b)) for a, b in sp]})")
        expect(not (emu.ppu_mask & 0x10) and emu.ppu_mask == 0x0A, f"sprites off after closing (mask=${emu.ppu_mask:02X})")
        expect("Info Arquivo" not in emu.dump_screen_text(), "popup closed, browser restored")

        # --- ROM without art
        open_rom_info(emu, "ZZ No Art")
        expect("Info Arquivo" in emu.dump_screen_text(), "no-art ROM: popup shown")
        expect(not (emu.ppu_mask & 0x10), "no-art ROM: no sprites")
        close_popup(emu)
        sp = watch.sp_hook[-2:]
        expect(sp[0][1] == sp[1][1], "no-art ROM: C stack balanced")
        expect("Info Arquivo" not in emu.dump_screen_text(), "no-art ROM: popup closed")

        # --- everything else still works
        before = emu.prg_ram[15][0xFAE5 - 0xE000]
        emu.press_button(0x21, hold_frames=3, wait_frames=30)
        expect(emu.prg_ram[15][0xFAE5 - 0xE000] == (before + 1) % 9, "theme switch still works")
        expect(not watch.bad_writes, f"art code wrote no OS work RAM ({watch.bad_writes[:3]})")

    print(f"\n{'PASSED' if failures == 0 else f'FAILED ({failures})'}")
    return failures


if __name__ == "__main__":
    shot = sys.argv[sys.argv.index("--shot") + 1] if "--shot" in sys.argv else None
    sys.exit(1 if main(shot) else 0)
