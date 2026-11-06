"""
Regression test for the "theme switch corrupts the SD card" bug.

Boots the real (encrypted) OS.BIN through the emulator's decryptor and checks:
  1. The NMI never touches the mapper ($4400/$4401), the PPU (other than the
     original $2002 read), or $6000-$7FFF while switching themes.
  2. An NMI that lands in the middle of an OS mapper sequence (register index
     selected, foreign bank mapped at $6000) leaves both exactly as they were.
  3. Theme code never writes into the OS heap window of bank 8 ($7BA5..$7FF7).
  4. The theme is actually applied (palette, banner nametable, CHR tiles) and
     persisted, and restored after a reboot that keeps bank 8.

Usage: python tools/test_theme_safety.py [path/to/OS.BIN]   (default EDFC/OS.BIN)
"""
import os, sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
from edfc_emu import EverDriveN8Emu
from banner_art import build_banner_packages

THEME_ID = 0xFAE5
SIG = 0x7FF8
HEAP_LO, HEAP_HI = 0x7BA5, 0x7FF7          # OS bump-allocator window in bank 8
NMI_OK_RAM = range(0x0000, 0x0800)         # OS NMI writes $9E/$A0/$A1/$0484 + stack
NMI_OK_B15 = range(0xFAE5, 0xFAE8)         # theme runtime variables ($FAE4 stays 0)


class Probe:
    def __init__(self, emu):
        self.emu = emu
        self.in_nmi = False
        self.nmi_violations = []
        self.heap_violations = []
        w, step, nmi = emu.write, emu.step, emu.trigger_nmi

        def write(a, v):
            a &= 0xFFFF
            pc = emu.PC
            if self.in_nmi and not (a in NMI_OK_RAM or a in NMI_OK_B15 or a == 0x4016):
                self.nmi_violations.append((pc, a, v))
            bank = emu.reg_data[0x81] & 0x3F
            theme_code = 0xFAE4 <= pc < 0xFC00 or (0x7F00 <= pc < 0x8000)
            if theme_code and bank == 8 and HEAP_LO <= a <= HEAP_HI:
                self.heap_violations.append((pc, a, v))
            w(a, v)

        def trigger():
            self.in_nmi = True
            nmi()

        def stepper():
            was_rti = emu.read(emu.PC) == 0x40
            step()
            if was_rti:
                self.in_nmi = False

        emu.write, emu.step, emu.trigger_nmi = write, stepper, trigger


def boot(os_path, bank8=None):
    emu = EverDriveN8Emu(os_path, REPO)
    if bank8 is not None:
        emu.prg_ram[8][:] = bank8               # cartridge RAM kept across reset
    probe = Probe(emu)
    emu.boot_to_browser()                       # boot, close the main menu shown after boot
    return emu, probe


def theme(emu):
    return emu.prg_ram[15][THEME_ID - 0xE000]


def sig(emu):
    return list(emu.prg_ram[8][SIG - 0x6000: SIG - 0x6000 + 4])


def check_applied(emu, pkgs, tid, label, nt_from_shadow=False):
    """Palette (all 16 colours), banner nametable and banner CHR tiles of theme tid.
    nt_from_shadow: check the OS nametable shadow (bank 8 $6000) instead of VRAM; the
    plain emulator fires its NMI by instruction count, which can land between an OS
    $2006 pair during boot and misplace a VRAM row (not something hardware does)."""
    pkg = pkgs[tid]
    ok = True
    if bytes(emu.palette[0:16]) != bytes(pkg['palette']):
        print(f"    FAIL {label}: palette {bytes(emu.palette[0:16]).hex()} != {bytes(pkg['palette']).hex()}")
        ok = False
    # screen rows 0-3: black row (overscan), banner rows 1-2, black spacer row 3
    nt = bytes(emu.prg_ram[8][0:128]) if nt_from_shadow else bytes(emu.vram[0:128])
    blank = bytes(pkg['nametable'][64:96])
    if nt != blank + bytes(pkg['nametable'][:64]) + blank:
        print(f"    FAIL {label}: banner nametable in {'shadow' if nt_from_shadow else 'VRAM'} differs")
        ok = False
    bad = [s for s, tb in pkg['tiles'] if bytes(emu.chr_ram[s*16:(s+1)*16]) != bytes(tb)]
    if bad:
        print(f"    FAIL {label}: {len(bad)} CHR tiles not uploaded")
        ok = False
    return ok


def main(os_path=None):
    os_path = os_path or os.path.join(REPO, "EDFC", "OS.BIN")
    os.chdir(REPO)
    pkgs = build_banner_packages()
    failures = 0

    def expect(cond, msg):
        nonlocal failures
        print(("  [OK]   " if cond else "  [FAIL] ") + msg)
        if not cond:
            failures += 1

    print(f"OS image: {os_path}")
    emu, probe = boot(os_path)
    expect(theme(emu) == 0 and check_applied(emu, pkgs, 0, "boot"), "boots on theme 0 with banner")

    # --- 1. SELECT in the browser: next theme (cycles), applied + full redraw
    for want in (1, 2, 3, 4, 5, 6, 7, 8, 0, 1, 2, 3):
        emu.press_button(0x20, hold_frames=3, wait_frames=40)
        expect(theme(emu) == want and check_applied(emu, pkgs, want, f"theme {want}"),
               f"SELECT -> theme {want} applied")
    expect("Menu Principal" not in emu.dump_screen_text(), "SELECT no longer opens the main menu")
    expect(sig(emu) == [0xED, 0xFC, 3, 0xFC], f"signature at ${SIG:04X} = {bytes(sig(emu)).hex()}")
    expect(not probe.nmi_violations,
           f"NMI made no mapper/PPU/work-RAM writes ({len(probe.nmi_violations)} found: "
           + ", ".join(f"PC=${p:04X} [${a:04X}]={v:02X}" for p, a, v in probe.nmi_violations[:4]) + ")")
    expect(not probe.heap_violations,
           f"theme code never wrote OS heap ${HEAP_LO:04X}-${HEAP_HI:04X} ({len(probe.heap_violations)} found: "
           + ", ".join(f"PC=${p:04X} [${a:04X}]" for p, a, v in probe.heap_violations[:4]) + ")")
    expect(bytes(emu.read(0x8103 + i) for i in range(5)) == bytes.fromhex("ad02206840"),
           "NMI tail is the OS original (LDA $2002 / PLA / RTI)")

    # --- 2. START opens the main menu; closing it returns to the browser
    emu.press_button(0x10, hold_frames=2, wait_frames=30)
    expect("Menu Principal" in emu.dump_screen_text(), "START opens the main menu")
    emu.press_button(0x80, hold_frames=2, wait_frames=30)
    expect("Menu Principal" not in emu.dump_screen_text(), "main menu closes back to the browser")

    # --- 2b. an NMI landing mid-transaction leaves the mapper alone
    emu.reg_addr = 0x09
    emu.reg_data[0x81] = 0x12
    ret_pc = emu.PC
    emu.trigger_nmi()
    for _ in range(500):
        emu.step()
        if not probe.in_nmi:
            break
    expect(emu.PC == ret_pc, "NMI returned to interrupted code")
    expect(emu.reg_addr == 0x09 and emu.reg_data[0x81] == 0x12, "mapper index and $6000 bank preserved across NMI")
    emu.reg_addr = 0x81
    emu.reg_data[0x81] = 0x08

    # --- 3. persistence across reset (bank 8 retained, OS.BIN reloaded)
    saved = bytes(emu.prg_ram[8])
    emu2, probe2 = boot(os_path, bank8=saved)
    expect(theme(emu2) == 3 and check_applied(emu2, pkgs, 3, "reboot", nt_from_shadow=True), "theme 3 restored after reboot")
    expect(not probe2.nmi_violations and not probe2.heap_violations, "no unsafe writes during reboot restore")

    # --- 4. garbage in bank 8 must not select an invalid theme
    junk = bytearray(saved)
    junk[SIG - 0x6000: SIG - 0x6000 + 4] = bytes([0xED, 0xFC, 0x0C, 0xF3])
    emu3, _ = boot(os_path, bank8=bytes(junk))
    expect(theme(emu3) == 0, "invalid signature falls back to theme 0")

    print(f"\n{'PASSED' if failures == 0 else f'FAILED ({failures})'}")
    return failures


if __name__ == "__main__":
    sys.exit(1 if main(sys.argv[1] if len(sys.argv) > 1 else None) else 0)
