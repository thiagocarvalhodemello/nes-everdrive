"""
End-to-end test for favourites (EDFC/FAVS.DAT) and recently played games (EDFC/RECENTS.DAT).

SD card (temp dir, FAT16 with 4 sectors/cluster so FAVS.DAT spans 8 clusters):
  * FAVS.DAT with slots 0..4 pre-filled (fake records "Dummy N") -> the first
    add lands in slot 5, in the second cluster (exercises the cluster walk)
  * two ROMs
Checks:
  * game menu shows "Favoritar"; adding saves the OS record into slot 5
    (cluster, long name, $55AA), shows "Favorito salvo!", browser redraws
  * adding the same game again -> "Já está nos favoritos.", nothing written
  * START -> main menu has "Favoritos"; the list shows the 6 names in slot order
  * SELECT removes the highlighted favourite (slot 0 cluster zeroed)
  * confirm on a favourite copies the record to *$046A and reaches $B7AC
  * only FAVS.DAT sectors were written, magic/slot bytes intact,
    OS DATA page $0300 unchanged, heap pointer $0450 restored,
    hardware stack never reached the trampoline (S > $B0)
  * card without FAVS.DAT: message, no SD writes at all
  * Recentes: launching from the game menu writes the record + counter into RECENTS.DAT
    (one sector), a second game takes the next slot, launching the first again bumps its
    counter in the same slot; the Recentes screen lists the most recent first

Usage: python tools/test_favorites.py
"""
import os, sys, shutil, tempfile, struct

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
from edfc_emu import EverDriveN8Emu
from fav_runtime import favs_dat, FAV_MAGIC, FAV_TAIL
from art_runtime import T_LIMIT

UP, DOWN, SELECT, START, B, A = 0x08, 0x04, 0x20, 0x10, 0x40, 0x80


def make_rom(seed, battery=False):
    import random
    r = random.Random(seed)
    return b"NES\x1a\x02\x01" + (b"\x12" if battery else b"\x00") + b"\x00" + bytes(8) + bytes(r.randrange(256) for _ in range(32768 + 8192))


def prefilled_favs(n):
    d = bytearray(favs_dat())
    for k in range(n):
        o = k * 512
        struct.pack_into("<I", d, o, 0x7000 + k)          # fake, never launched
        name = f"Dummy {k}".encode()
        d[o + 10:o + 10 + len(name)] = name
    return bytes(d)


def build_sd(root, favs=True):
    os.makedirs(os.path.join(root, "EDFC", "MAPS"))
    os.makedirs(os.path.join(root, "EDFC", "SAVE"))
    shutil.copy(os.path.join(REPO, "EDFC", "MAPROUT.BIN"), os.path.join(root, "EDFC"))
    for f in ("000.RBF", "001.RBF"):
        shutil.copy(os.path.join(REPO, "EDFC", "MAPS", f), os.path.join(root, "EDFC", "MAPS"))
    for f in ("OVLART.BIN", "OVLFAV.BIN", "OVLREC.BIN", "OVLFIND.BIN", "OVLSCAN.BIN", "RECENTS.DAT"):
        shutil.copy(os.path.join(REPO, "EDFC", f), os.path.join(root, "EDFC"))
    open(os.path.join(root, "EDFC", "SAVE", "KEEP.TXT"), "wb").write(b"x")
    if favs:
        open(os.path.join(root, "EDFC", "FAVS.DAT"), "wb").write(prefilled_favs(5))
    open(os.path.join(root, "Alpha Quest (World).nes"), "wb").write(make_rom(1))
    open(os.path.join(root, "Beta Racer (World).nes"), "wb").write(make_rom(2))


def locate(img):
    """(FAVS.DAT, RECENTS.DAT) as {slot: byte offset}: runs of sectors with the magic tail;
    FAVS.DAT is the run whose slot 0 holds the pre-filled "Dummy 0" (None if absent)."""
    runs = []
    for off in range(0, len(img), 512):
        sec = img[off:off + 512]
        if sec[FAV_TAIL + 1:FAV_TAIL + 9] == FAV_MAGIC:
            if sec[FAV_TAIL] == 0:
                runs.append({})
            runs[-1][sec[FAV_TAIL]] = off
    fav = [r for r in runs if b"Dummy 0" in img[r[0]:r[0] + 64]]
    rec = [r for r in runs if b"Dummy 0" not in img[r[0]:r[0] + 64]]
    return (fav[0] if fav else None), (rec[0] if rec else None)


def sectors(img, offs):
    """{slot: (offset, sector bytes)} for one file, keeping only intact magic/slot sectors"""
    out = {}
    for k, off in offs.items():
        sec = bytes(img[off:off + 512])
        if sec[FAV_TAIL] == k and sec[FAV_TAIL + 1:FAV_TAIL + 9] == FAV_MAGIC:
            out[k] = (off, sec)
    return out


def counter(sec):
    return sec[271] | sec[272] << 8 | sec[273] << 16


def screen(emu):
    return emu.dump_screen_text()


def select_file(emu, prefix):
    for _ in range(30):
        line = [l for l in screen(emu).split("\n") if l.startswith("28:")]
        if line and prefix in line[0]:
            return
        emu.press_button(DOWN, wait_frames=15)
    raise AssertionError(f"file {prefix!r} not found")


def highlighted_rows(emu):
    rows = []
    for ty in range(30):
        cells = emu.vram[ty * 32:(ty + 1) * 32]
        if any(c & 0x80 and (c & 0x7F) > 32 for c in cells):
            rows.append("".join(chr(c & 0x7F) if 32 <= (c & 0x7F) < 127 else " " for c in cells).strip().lstrip("> "))
    return rows


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
        min_s = [0xFF]
        step = emu.step

        def stepper():
            if emu.S < min_s[0]:
                min_s[0] = emu.S
            step()
        emu.step = stepper
        emu.boot_to_browser()
        p3 = bytes(emu.ram[0x300:0x360]) + bytes(emu.ram[0x380:0x400])
        heap = emu.ram[0x450] | emu.ram[0x451] << 8
        img0 = bytes(emu.sd_img)
        FAV, REC = locate(img0)
        fav_sectors = lambda img: sectors(img, FAV)
        favs0 = fav_sectors(img0)
        expect(sorted(favs0) == list(range(32)) and REC and len(REC) == 32,
               "FAVS.DAT and RECENTS.DAT found on the emulated card (32 slots each)")

        # --- add "Alpha Quest" from the game menu
        select_file(emu, "Alpha Quest")
        emu.press_button(B, wait_frames=60)
        txt = screen(emu)
        expect("Favoritar" in txt and "Carregar jogo" in txt and "Info da ROM" in txt,
               "game menu: Carregar jogo / Info da ROM / Favoritar")
        emu.press_button(DOWN, wait_frames=15)
        emu.press_button(DOWN, wait_frames=15)
        emu.press_button(B, wait_frames=120)
        txt = screen(emu)
        expect("Favorito salvo!" in txt, "Favoritar -> 'Favorito salvo!'")
        rec_ptr = emu.ram[0x46A] | emu.ram[0x46B] << 8
        rec = bytes(emu.read(rec_ptr + i) for i in range(271))
        emu.press_button(B, wait_frames=60)
        expect("Alpha Quest" in screen(emu) and "Favorito" not in screen(emu), "back in the browser after the message")
        favs1 = fav_sectors(bytes(emu.sd_img))
        s5 = favs1[5][1]
        expect(s5[:271] == rec and b"Alpha Quest" in s5[10:80] and s5[0x10B:0x10D] == b"\x55\xAA",
               "slot 5 (2nd cluster) holds the OS game record")
        changed = [o // 512 for o in range(0, len(img0), 512) if emu.sd_img[o:o + 512] != img0[o:o + 512]]
        expect(changed == [favs1[5][0] // 512], f"exactly one sector written (the slot 5 sector): {changed}")

        # --- same game again -> already a favourite, nothing written
        img1 = bytes(emu.sd_img)
        select_file(emu, "Alpha Quest")
        emu.press_button(B, wait_frames=60)
        emu.press_button(DOWN, wait_frames=15)
        emu.press_button(DOWN, wait_frames=15)
        emu.press_button(B, wait_frames=120)
        expect("Já está nos favoritos." in screen(emu), "second add -> 'Já está nos favoritos.'")
        emu.press_button(B, wait_frames=60)
        expect(bytes(emu.sd_img) == img1, "second add wrote nothing")

        # --- START -> main menu -> Favoritos
        emu.press_button(START, wait_frames=60)
        txt = screen(emu)
        expect("Favoritos" in txt and "Op" in txt and "Sobre" in txt, "main menu lists Favoritos")
        for _ in range(2):
            emu.press_button(DOWN, wait_frames=15)
        emu.press_button(B, wait_frames=200)
        txt = screen(emu)
        names = ["Dummy 0", "Dummy 1", "Dummy 2", "Dummy 3", "Dummy 4", "Alpha Quest"]
        pos = [txt.find(n) for n in names]
        expect(all(p >= 0 for p in pos) and pos == sorted(pos) and "SELECT - remover" in txt,
               "favourites screen lists the 6 entries in slot order")
        hl = highlighted_rows(emu)
        expect(any(r.startswith("Dummy 0") for r in hl), f"first entry highlighted ({hl})")

        # --- SELECT removes "Dummy 0"
        emu.press_button(SELECT, wait_frames=200)
        txt = screen(emu)
        favs2 = fav_sectors(bytes(emu.sd_img))
        expect("Dummy 0" not in txt and "Dummy 1" in txt and favs2[0][1][:4] == bytes(4)
               and favs2[0][1][4:] == favs1[0][1][4:], "SELECT removed slot 0 (cluster zeroed)")

        # --- move to "Alpha Quest" (now 5th) and launch
        for _ in range(4):
            emu.press_button(DOWN, wait_frames=30)
        hl = highlighted_rows(emu)
        expect(any(r.startswith("Alpha Quest") for r in hl), f"cursor on Alpha Quest ({hl})")
        expect(emu.ram[0x450] | emu.ram[0x451] << 8 == heap + 512, "sector buffer allocated while the list is open")
        reached = []

        def stop_at_start():
            if emu.PC == 0xB7AC:
                reached.append(bytes(emu.read((emu.ram[0x46A] | emu.ram[0x46B] << 8) + i) for i in range(271)))
                raise StopIteration
            stepper()
        emu.step = stop_at_start
        try:
            emu.press_button(B, wait_frames=200)
        except StopIteration:
            pass
        emu.step = stepper
        expect(reached and reached[0] == rec, "confirm -> record restored at *$046A and $B7AC reached")
        expect(emu.ram[0x450] | emu.ram[0x451] << 8 == heap, "heap pointer restored before starting the game")
        recs = sectors(bytes(emu.sd_img), REC)
        expect(recs[0][1][:271] == rec and counter(recs[0][1]) == 1,
               "the launched favourite was recorded in RECENTS.DAT slot 0 (counter 1)")

        # --- global safety
        img2 = bytes(emu.sd_img)
        ok_offs = set(FAV.values()) | set(REC.values())
        bad = [o for o in range(0, len(img0), 512) if img2[o:o + 512] != img0[o:o + 512] and o not in ok_offs]
        expect(not bad, f"no sector outside FAVS.DAT / RECENTS.DAT changed ({bad[:4]})")
        expect(len(sectors(img2, REC)) == 32, "RECENTS.DAT keeps its magic and slot bytes")
        favs3 = fav_sectors(img2)
        expect(sorted(favs3) == list(range(32)), "all 32 slots keep their magic and slot byte")
        expect((bytes(emu.ram[0x300:0x360]) + bytes(emu.ram[0x380:0x400])) == p3, "OS DATA page $0300 unchanged")
        expect(0x100 + min_s[0] >= T_LIMIT, f"hardware stack stayed above the trampoline (min ${0x100 + min_s[0]:04X})")

    with tempfile.TemporaryDirectory() as root:
        build_sd(root, favs=False)
        emu = EverDriveN8Emu(os.path.join(REPO, "EDFC", "OS.BIN"), root)
        emu.boot_to_browser()
        img0 = bytes(emu.sd_img)
        select_file(emu, "Alpha Quest")
        emu.press_button(B, wait_frames=60)
        emu.press_button(DOWN, wait_frames=15)
        emu.press_button(DOWN, wait_frames=15)
        emu.press_button(B, wait_frames=120)
        expect("Falta o EDFC/FAVS.DAT" in screen(emu), "no FAVS.DAT: message shown")
        emu.press_button(B, wait_frames=60)
        emu.press_button(START, wait_frames=60)
        for _ in range(2):
            emu.press_button(DOWN, wait_frames=15)
        emu.press_button(B, wait_frames=120)
        expect("Falta o EDFC/FAVS.DAT" in screen(emu), "no FAVS.DAT: Favoritos screen shows the message")
        emu.press_button(B, wait_frames=60)
        expect("Favoritos" in screen(emu), "back in the main menu")
        expect(bytes(emu.sd_img) == img0, "no FAVS.DAT: nothing written to the card")

    # --- Recentes
    with tempfile.TemporaryDirectory() as root:
        build_sd(root)

        def launch(img, name):
            """new emulator on the card image, 'Carregar jogo' on name; returns (emu, record)"""
            emu = EverDriveN8Emu(os.path.join(REPO, "EDFC", "OS.BIN"), root)
            if img is not None:
                emu.sd_img[:] = img
            emu.boot_to_browser()
            select_file(emu, name)
            emu.press_button(B, wait_frames=60)
            got, step = [], emu.step

            def stop():
                if emu.PC == 0xB7AC:
                    p = emu.ram[0x46A] | emu.ram[0x46B] << 8
                    got.append(bytes(emu.read(p + i) for i in range(271)))
                    raise StopIteration
                step()
            emu.step = stop
            try:
                emu.press_button(B, wait_frames=300)
            except StopIteration:
                pass
            emu.step = step
            return emu, (got[0] if got else None)

        emu, ra = launch(None, "Alpha Quest")
        img0 = bytes(EverDriveN8Emu(os.path.join(REPO, "EDFC", "OS.BIN"), root).sd_img)
        FAV, REC = locate(img0)
        img1 = bytes(emu.sd_img)
        r1 = sectors(img1, REC)
        changed = [o for o in range(0, len(img0), 512) if img1[o:o + 512] != img0[o:o + 512]]
        expect(ra and r1[0][1][:271] == ra and counter(r1[0][1]) == 1 and changed == [REC[0]],
               f"Carregar jogo: record + counter 1 in RECENTS.DAT slot 0, one sector written ({changed})")
        emu, rb = launch(img1, "Beta Racer")
        img2 = bytes(emu.sd_img)
        r2 = sectors(img2, REC)
        expect(rb and r2[1][1][:271] == rb and counter(r2[1][1]) == 2 and r2[0][1] == r1[0][1],
               "second game: slot 1, counter 2; slot 0 untouched")
        emu, ra2 = launch(img2, "Alpha Quest")
        img3 = bytes(emu.sd_img)
        r3 = sectors(img3, REC)
        expect(counter(r3[0][1]) == 3 and r3[1][1] == r2[1][1] and not any(
            any(r3[k][1][:4]) for k in range(2, 32)), "same game again: its slot is bumped (counter 3), no new slot")
        bad = [o for o in range(0, len(img0), 512) if img3[o:o + 512] != img0[o:o + 512] and o not in REC.values()]
        expect(not bad, f"only RECENTS.DAT sectors written by launches ({bad[:4]})")
        # Recentes screen: most recent first
        emu = EverDriveN8Emu(os.path.join(REPO, "EDFC", "OS.BIN"), root)
        emu.sd_img[:] = img3
        emu.boot_to_browser()
        emu.press_button(START, wait_frames=60)
        for _ in range(3):
            emu.press_button(DOWN, wait_frames=15)
        emu.press_button(B, wait_frames=200)
        txt = screen(emu)
        pa, pb = txt.find("Alpha Quest"), txt.find("Beta Racer")
        expect("Recentes" in txt and 0 <= pa < pb and "SELECT - remover da lista" in txt,
               "Recentes screen: Alpha Quest (most recent) above Beta Racer")
        emu.press_button(A, wait_frames=60)
        expect("Menu Principal" in screen(emu), "cancel -> back to the main menu")

    # --- saves: a favourite / recent game starts through the OS $BF16 like the browser does
    #     (previous game's SRAM -> its EDFC/SAVE file, this game's save -> SRAM). v1.8.3 and
    #     earlier went straight to $B7AC: the save was never loaded, and the next launch from
    #     the browser backed the empty SRAM up over it (the save "vanished")
    with tempfile.TemporaryDirectory() as root:
        build_sd(root)
        for name, seed in (("Alpha Quest (World).nes", 1), ("Beta Racer (World).nes", 2)):
            open(os.path.join(root, name), "wb").write(make_rom(seed, battery=True))
            open(os.path.join(root, "EDFC", "SAVE", name), "wb").write(bytes([0x5A + seed]) * 8192)
        SRAM = 0                                                 # cartridge SRAM = PRG-RAM bank 0

        def reset(prev):
            """console reset: cartridge RAM (all banks but the OS image) and the card survive"""
            emu = EverDriveN8Emu(os.path.join(REPO, "EDFC", "OS.BIN"), root)
            if prev is not None:
                emu.sd_img[:] = prev.sd_img
                for b in list(range(0, 9)) + list(range(16, 64)):
                    emu.prg_ram[b][:] = prev.prg_ram[b]
            emu.boot_to_browser()
            return emu

        def start(emu):
            got, step = [], emu.step

            def stop():
                if emu.PC == 0xB7AC:
                    p = emu.ram[0x46A] | emu.ram[0x46B] << 8
                    got.append(bytes(emu.read(p + 10 + i) for i in range(11)))
                    raise StopIteration
                step()
            emu.step = stop
            try:
                emu.press_button(B, wait_frames=600)
            except StopIteration:
                pass
            emu.step = step
            return got[0] if got else None

        def saved(emu, byte):
            img = bytes(emu.sd_img)
            return sum(img[o:o + 512] == bytes([byte]) * 512 for o in range(0, len(img), 512))

        def fill(emu, byte):
            emu.prg_ram[SRAM][:] = bytes([byte]) * 8192

        emu = reset(None)
        select_file(emu, "Alpha Quest")
        emu.press_button(B, wait_frames=60)
        emu.press_button(DOWN, wait_frames=15)
        emu.press_button(DOWN, wait_frames=15)
        emu.press_button(B, wait_frames=120)                     # Favoritar
        emu.press_button(A, wait_frames=30)
        select_file(emu, "Beta Racer")
        emu.press_button(B, wait_frames=60)
        got = start(emu)
        expect(got == b"Beta Racer " and emu.prg_ram[SRAM][:16] == bytes([0x5C]) * 16,
               f"browser: Beta Racer starts with its save in SRAM ({got})")
        fill(emu, 0xD4)                                          # the game saves progress
        emu = reset(emu)
        emu.press_button(START, wait_frames=60)
        for _ in range(2):
            emu.press_button(DOWN, wait_frames=15)
        emu.press_button(B, wait_frames=200)
        for _ in range(5):
            emu.press_button(DOWN, wait_frames=30)
        expect(any(r.startswith("Alpha Quest") for r in highlighted_rows(emu)), "cursor on the Alpha Quest favourite")
        got = start(emu)
        expect(got == b"Alpha Quest" and emu.prg_ram[SRAM][:16] == bytes([0x5B]) * 16,
               f"favourite: Alpha Quest starts with ITS save in SRAM ({got})")
        expect(saved(emu, 0xD4) == 16, "favourite: the previous game's progress went to its save file first")
        expect((emu.read(0xBFDB), emu.read(0xBFDC)) == (0x71, 0xBC), "$BF16's JSR $BC71 restored after the launch")
        fill(emu, 0xE5)
        emu = reset(emu)
        emu.press_button(START, wait_frames=60)
        for _ in range(3):
            emu.press_button(DOWN, wait_frames=15)
        emu.press_button(B, wait_frames=200)
        emu.press_button(DOWN, wait_frames=30)                   # Alpha (most recent), Beta
        got = start(emu)
        expect(got == b"Beta Racer " and emu.prg_ram[SRAM][:16] == bytes([0xD4]) * 16 and saved(emu, 0xE5) == 16,
               f"recent: Beta Racer gets its saved progress, Alpha's progress was saved first ({got})")

    print(f"\n{'PASSED' if failures == 0 else f'FAILED ({failures})'}")
    return failures


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
