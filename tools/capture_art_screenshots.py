"""
Screenshots of the game menu (cover + options), rendered by the emulator from
real ROM files and an EDFC/ARTS folder (as produced by art_pack.py install).

Usage:
  python tools/capture_art_screenshots.py --arts <dir containing EDFC/ARTS> \
      --out docs/screenshots ROM1.nes ROM2.nes ...
Writes art_<n>_<slug>.png per ROM plus art_grid.png (all side by side).
"""
import argparse, os, re, shutil, sys, tempfile

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
from edfc_emu import EverDriveN8Emu
import nes_art
from test_game_art import open_game_menu


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arts", required=True)
    ap.add_argument("--out", default=os.path.join(REPO, "docs", "screenshots"))
    ap.add_argument("roms", nargs="+")
    a = ap.parse_args()
    from PIL import Image
    os.makedirs(a.out, exist_ok=True)
    shots = []
    with tempfile.TemporaryDirectory() as root:
        for d in ("EDFC/MAPS", "EDFC/SAVE", "EDFC/ARTS"):
            os.makedirs(os.path.join(root, d))
        shutil.copy(os.path.join(REPO, "EDFC", "MAPROUT.BIN"), os.path.join(root, "EDFC"))
        shutil.copy(os.path.join(REPO, "EDFC", "MAPS", "000.RBF"), os.path.join(root, "EDFC", "MAPS"))
        open(os.path.join(root, "EDFC", "SAVE", "KEEP.TXT"), "wb").write(b"x")
        for r in a.roms:
            data = open(r, "rb").read()
            shutil.copy(r, root)
            art = os.path.join(a.arts, "EDFC", "ARTS", nes_art.art_filename(data))
            if os.path.exists(art):
                shutil.copy(art, os.path.join(root, "EDFC", "ARTS"))
            else:
                print(f"  no art for {r}")
        emu = EverDriveN8Emu(os.path.join(REPO, "EDFC", "OS.BIN"), root)
        emu.run_frames(40)
        emu.press_button(0x80, wait_frames=40)
        emu.run_frames(20)
        for n, r in enumerate(a.roms):
            name = os.path.splitext(os.path.basename(r))[0]
            open_game_menu(emu, name[:20])
            slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40]
            path = os.path.join(a.out, f"art_{n}_{slug}.png")
            emu.render_screen(path, scale=2)
            shots.append(path)
            print(f"  {path}")
            emu.press_button(0x80, wait_frames=30)
            if "Menu Arquivo" in emu.dump_screen_text():
                emu.press_button(0x80, wait_frames=30)
    imgs = [Image.open(p) for p in shots]
    cols = 3
    w, h = imgs[0].size
    grid = Image.new("RGB", (cols * w + (cols - 1) * 8, ((len(imgs) + cols - 1) // cols) * (h + 8) - 8), (24, 24, 24))
    for i, im in enumerate(imgs):
        grid.paste(im, ((i % cols) * (w + 8), (i // cols) * (h + 8)))
    grid.save(os.path.join(a.out, "art_grid.png"))
    print(f"  {os.path.join(a.out, 'art_grid.png')}")


if __name__ == "__main__":
    main()
