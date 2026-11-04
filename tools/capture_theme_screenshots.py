"""
Renders one file-browser screenshot per in-system theme from the built
EDFC/OS.BIN (boots through the emulator and cycles with SELECT+RIGHT).

Usage: python tools/capture_theme_screenshots.py  ->  docs/screenshots/*.png
"""
import os, re, sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
from banner_art import THEMES as THEMES_DEF
from test_theme_safety import boot, theme

OUT = os.path.join(REPO, "docs", "screenshots")


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def main():
    os.chdir(REPO)
    os.makedirs(OUT, exist_ok=True)
    emu, _ = boot(os.path.join(REPO, "EDFC", "OS.BIN"))
    for tid, name, *_ in THEMES_DEF:
        if tid:
            emu.press_button(0x20, hold_frames=3, wait_frames=40)   # SELECT: next theme
        assert theme(emu) == tid, f"expected theme {tid}, on {theme(emu)}"
        path = os.path.join(OUT, f"theme{tid}_{slug(name)}.png")
        emu.render_screen(path, scale=2)
        print(f"  {tid}: {name:15s} -> {os.path.relpath(path, REPO)}")


if __name__ == "__main__":
    main()
