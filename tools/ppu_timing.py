"""
Timing-aware emulator mode: finds PPU writes that land outside vblank while
rendering is on (they corrupt VRAM on a real NES; the normal emulator, which
fast-forwards vblank waits, cannot see them).

Model (NTSC): 29780.5 CPU cycles per frame (29780 and 29781 alternate, as the odd-frame
skipped dot does on hardware; a fixed length phase-locks the OS's BIT $2002 wait against the
NMI's own $2002 read so that it never sees the flag); vblank flag set and NMI fired at the
start of the frame, flag cleared after VBLANK_CYCLES or by a $2002 read.
Instruction cycles from py65's table (no page-cross penalty); SD sector
transfers cost SD_SECTOR_CYCLES each (the BIOS is stubbed).

Usage:
    from ppu_timing import TimedEmu
    emu = TimedEmu("EDFC/OS.BIN", sd_root)
    emu.run_frames(40); ...
    emu.unsafe   # [(pc, register, cycle_in_frame, mask, label)]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edfc_emu import EverDriveN8Emu
from py65.devices.mpu6502 import MPU

FRAME_CYCLES = 29780
VBLANK_CYCLES = 2273
SD_SECTOR_CYCLES = 16000
_CYC = MPU().cycletime


class TimedEmu(EverDriveN8Emu):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.cyc = 0                 # cycles into the current frame
        self.frames = 0
        self.unsafe = []
        self.label = ""              # caller-set tag (e.g. which flow is running)
        self.ppu_status &= ~0x80

    # --- PPU register side effects with timing
    def read(self, addr):
        a = addr & 0xFFFF
        if 0x2000 <= a < 0x4000 and (a & 7) == 2:
            v = self.ppu_status
            self.ppu_status &= ~0x80
            self.ppu_latch = False
            return v
        return super().read(addr)

    def write(self, addr, val):
        a = addr & 0xFFFF
        reg = None
        if 0x2000 <= a < 0x4000 and (a & 7) in (5, 6, 7):
            reg = 0x2000 | (a & 7)
        elif a == 0x4014:
            reg = 0x4014
        if reg is not None and (self.ppu_mask & 0x18) and self.cyc >= VBLANK_CYCLES:
            self.unsafe.append((self.PC, reg, self.cyc, self.ppu_mask, self.label))
        super().write(addr, val)

    def handle_bios_trap(self, pc):
        off = pc - 0xFC40
        if off in (0x26, 0x28, 0x36):             # sd read / read-to-PPU / write blocks
            self._advance(SD_SECTOR_CYCLES * max(1, self.ram[0x04E6]))
        super().handle_bios_trap(pc)

    def _frame_len(self):
        return FRAME_CYCLES + (self.frames & 1)

    def _advance(self, n, early_read=False):
        self.cyc += n
        while self.cyc >= self._frame_len():
            self.cyc -= self._frame_len()
            self.frames += 1
            if not early_read:                     # flag already seen (and cleared) by the read
                self.ppu_status |= 0x80
            early_read = False
            self._nmi_pending = bool(self.ppu_ctrl & 0x80)
        if self.cyc >= VBLANK_CYCLES:
            self.ppu_status &= ~0x80

    def step(self):
        pc = self.PC
        op = self.read(pc) if not (0x2000 <= pc < 0x4000) else 0
        n = _CYC[op] or 2
        # vblank starting during an instruction whose last cycle reads $2002
        # (BIT/LDA $2002): the read sees the flag, as on hardware.
        early = False
        if op in (0x2C, 0xAD) and self.read(pc + 1) == 0x02 and self.read(pc + 2) == 0x20 \
                and self.cyc + n - 1 >= self._frame_len():
            self.ppu_status |= 0x80
            early = True
        super().step()
        self._advance(n, early)
        if getattr(self, "_nmi_pending", False):
            self._nmi_pending = False
            self.trigger_nmi()

    def run_frames(self, n_frames=1, joy=0):
        self.joy_state = joy
        target = self.frames + n_frames
        guard = 0
        while self.frames < target:
            self.step()
            guard += 1
            if guard > 400000 * n_frames:
                raise RuntimeError("emulation stuck")

    def press_button(self, btn_mask, hold_frames=2, wait_frames=15):
        self.run_frames(hold_frames, joy=btn_mask)
        self.run_frames(wait_frames, joy=0)
