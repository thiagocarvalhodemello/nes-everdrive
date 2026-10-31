import os
import struct
import zlib

def save_png(path, width, height, rgb_rows):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + row for row in rgb_rows)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))

NES_PALETTE = [
    (84,84,84), (0,30,116), (8,16,144), (48,0,136), (68,0,100), (92,0,48), (84,4,0), (60,24,0),
    (32,42,0), (8,58,0), (0,64,0), (0,60,0), (0,50,60), (0,0,0), (0,0,0), (0,0,0),
    (152,150,152), (8,76,196), (48,50,236), (92,30,228), (136,20,176), (160,20,100), (152,34,32), (120,60,0),
    (84,90,0), (40,114,0), (8,124,0), (0,118,40), (0,102,120), (0,0,0), (0,0,0), (0,0,0),
    (236,238,236), (76,154,236), (120,124,236), (176,98,236), (228,84,236), (236,88,180), (236,106,100), (212,136,32),
    (160,170,0), (116,196,0), (76,208,32), (56,204,108), (56,180,204), (60,60,60), (0,0,0), (0,0,0),
    (236,238,236), (168,204,236), (188,188,236), (212,178,236), (236,174,236), (236,174,212), (236,180,176), (228,196,144),
    (204,210,120), (180,222,120), (168,226,144), (152,226,180), (160,214,228), (160,162,160), (0,0,0), (0,0,0)
]

def build_fat16_image(root_dir):
    total_sectors = 32768
    bytes_per_sector = 512
    sectors_per_cluster = 4
    reserved_sectors = 1
    num_fats = 2
    root_entries = 512
    root_dir_sectors = (root_entries * 32) // bytes_per_sector
    sectors_per_fat = 32
    img = bytearray(total_sectors * bytes_per_sector)

    part_lba = 64
    part_sectors = total_sectors - part_lba
    img[0x1BE] = 0x80
    img[0x1BE+4] = 0x06
    struct.pack_into("<I", img, 0x1BE+8, part_lba)
    struct.pack_into("<I", img, 0x1BE+12, part_sectors)
    img[0x1FE] = 0x55
    img[0x1FF] = 0xAA

    vbr = part_lba * 512
    img[vbr:vbr+3] = b"\xEB\x3C\x90"
    img[vbr+3:vbr+11] = b"MSDOS5.0"
    struct.pack_into("<H", img, vbr+11, bytes_per_sector)
    img[vbr+13] = sectors_per_cluster
    struct.pack_into("<H", img, vbr+14, reserved_sectors)
    img[vbr+16] = num_fats
    struct.pack_into("<H", img, vbr+17, root_entries)
    struct.pack_into("<H", img, vbr+19, part_sectors if part_sectors < 65536 else 0)
    img[vbr+21] = 0xF8
    struct.pack_into("<H", img, vbr+22, sectors_per_fat)
    struct.pack_into("<H", img, vbr+24, 63)
    struct.pack_into("<H", img, vbr+26, 16)
    struct.pack_into("<I", img, vbr+28, part_lba)
    img[vbr+54:vbr+62] = b"FAT16   "
    img[vbr+510] = 0x55
    img[vbr+511] = 0xAA

    fat1_lba = part_lba + reserved_sectors
    fat2_lba = fat1_lba + sectors_per_fat
    root_lba = fat2_lba + sectors_per_fat
    data_lba = root_lba + root_dir_sectors

    for fat_lba in (fat1_lba, fat2_lba):
        struct.pack_into("<H", img, fat_lba*512 + 0, 0xFFF8)
        struct.pack_into("<H", img, fat_lba*512 + 2, 0xFFFF)

    next_cluster = 2

    def alloc_clusters(data_bytes):
        nonlocal next_cluster
        if len(data_bytes) == 0:
            return 0
        cluster_size = sectors_per_cluster * 512
        n_clusters = (len(data_bytes) + cluster_size - 1) // cluster_size
        start_c = next_cluster
        for i in range(n_clusters):
            c = start_c + i
            nxt = (c + 1) if i < n_clusters - 1 else 0xFFFF
            for fat_lba in (fat1_lba, fat2_lba):
                struct.pack_into("<H", img, fat_lba*512 + c*2, nxt)
            chunk = data_bytes[i*cluster_size:(i+1)*cluster_size]
            c_lba = data_lba + (c - 2) * sectors_per_cluster
            img[c_lba*512:c_lba*512+len(chunk)] = chunk
        next_cluster += n_clusters
        return start_c

    def make_sfn(name):
        base, ext = os.path.splitext(name)
        base = "".join(c for c in base.upper() if c.isalnum() or c in "_-")[:8].ljust(8)
        ext = "".join(c for c in ext[1:].upper() if c.isalnum() or c in "_-")[:3].ljust(3)
        return (base + ext).encode("ascii")

    def make_dir_entry(name_11, attr, cluster, size):
        ent = bytearray(32)
        ent[0:11] = name_11
        ent[11] = attr
        struct.pack_into("<H", ent, 22, (12 << 11) | (0 << 5) | 0)
        struct.pack_into("<H", ent, 24, ((2025 - 1980) << 9) | (1 << 5) | 1)
        struct.pack_into("<H", ent, 26, cluster)
        struct.pack_into("<I", ent, 28, size)
        return ent

    def populate_dir(fs_path, parent_cluster, is_root=False):
        entries = bytearray()
        my_cluster = next_cluster if not is_root else 0
        if not is_root:
            my_cluster = alloc_clusters(bytes(sectors_per_cluster * 512))
            entries += make_dir_entry(b".          ", 0x10, my_cluster, 0)
            entries += make_dir_entry(b"..         ", 0x10, parent_cluster, 0)
        for item in sorted(os.listdir(fs_path)):
            if item in ('sdcard', '.git', '__pycache__', 'screens_en', 'screens_ptbr'):
                continue
            full = os.path.join(fs_path, item)
            if os.path.isdir(full):
                sub_c = populate_dir(full, my_cluster, is_root=False)
                entries += make_dir_entry(make_sfn(item), 0x10, sub_c, 0)
            elif os.path.isfile(full):
                raw = open(full, "rb").read()
                if len(raw) == 0:
                    continue
                fc = alloc_clusters(raw)
                entries += make_dir_entry(make_sfn(item), 0x20, fc, len(raw))
        if is_root:
            img[root_lba*512:root_lba*512+len(entries)] = entries
            return 0
        else:
            c_lba = data_lba + (my_cluster - 2) * sectors_per_cluster
            img[c_lba*512:c_lba*512+len(entries)] = entries
            return my_cluster

    populate_dir(root_dir, 0, is_root=True)
    save_dir = os.path.join(root_dir, "EDFC", "SAVE")
    if os.path.isdir(save_dir):
        root_off = 0
        while img[root_lba*512 + root_off] != 0:
            root_off += 32
        for item in sorted(os.listdir(save_dir)):
            if item.lower().endswith(".nes"):
                full = os.path.join(save_dir, item)
                raw = open(full, "rb").read()
                fc = alloc_clusters(raw)
                ent = make_dir_entry(make_sfn(item), 0x20, fc, len(raw))
                img[root_lba*512 + root_off:root_lba*512 + root_off + 32] = ent
                root_off += 32
        # Also add a valid iNES ROM, a .SAV file, and a .TXT cheat file for testing all File Menus and Rom Info!
        fake_ines = b"NES\x1a\x02\x01\x12\x00" + b"\x00" * 8 + bytes(32768 + 8192)
        fc_nes = alloc_clusters(fake_ines)
        img[root_lba*512 + root_off:root_lba*512 + root_off + 32] = make_dir_entry(b"MARIO   NES", 0x20, fc_nes, len(fake_ines))
        root_off += 32
        fc_sav = alloc_clusters(bytes(8192))
        img[root_lba*512 + root_off:root_lba*512 + root_off + 32] = make_dir_entry(b"MARIO   SAV", 0x20, fc_sav, 8192)
        root_off += 32
        fc_txt = alloc_clusters(b"SXIOPO\r\n")
        img[root_lba*512 + root_off:root_lba*512 + root_off + 32] = make_dir_entry(b"CHEATS  TXT", 0x20, fc_txt, 8)
        root_off += 32
        fake_fds = b"FDS\x1a" + bytes(65500)
        fc_fds = alloc_clusters(fake_fds)
        img[root_lba*512 + root_off:root_lba*512 + root_off + 32] = make_dir_entry(b"ZELDA   FDS", 0x20, fc_fds, len(fake_fds))
        root_off += 32
    return img


class EverDriveN8Emu:
    def __init__(self, os_bin_path, sd_root_dir):
        with open(os_bin_path, "rb") as f:
            os_data = bytearray(f.read())
        assert len(os_data) == 0xE000

        # Extract the 256-byte BIOS decryptor page k60 from original OS.BIN[0xDB00:0xDC00] ^ 0x7B
        # (Wait: in case 0xDB00 in translated OS.BIN has data, we use the fixed k60 from the original BIOS!)
        orig_os = open(r"C:\Development\nes-everdrive\EDFC\OS.BIN.bak" if os.path.exists(r"C:\Development\nes-everdrive\EDFC\OS.BIN.bak") else os_bin_path, "rb").read()
        self.k60 = bytes(b ^ 0x7B for b in orig_os[0xDB00:0xDC00])

        self.sd_img = build_fat16_image(sd_root_dir)

        # 512KB PRG-RAM (64 banks of 8KB)
        self.prg_ram = [bytearray(0x2000) for _ in range(64)]
        # Load OS.BIN into banks 0x09..0x0F (7 banks of 8KB)
        for b in range(7):
            self.prg_ram[0x09 + b][:] = os_data[b*0x2000:(b+1)*0x2000]

        # 2KB internal NES RAM ($0000-$07FF)
        self.ram = bytearray(0x0800)
        # $4800-$4FFF 2KB buffer window
        self.buf_4800 = bytearray(0x0800)

        # EverDrive registers
        self.reg_addr = 0
        self.reg_data = bytearray(256)
        self.reg_data[0x09] = 0x00  # BIOS map register
        self.reg_data[0x0A] = 10    # CPLD version 10 (v1.10)
        self.reg_data[0x80] = 0     # $4800 bank
        self.reg_data[0x81] = 0x08  # $6000-$7FFF bank (default 8 = OS WRAM)
        self.reg_data[0x82] = 0     # CHR bank
        self.reg_data[0x8A] = 0     # FPGA status (not 0x52 'R')

        # Build 1KB onboard BIOS ROM ($FC00-$FFFF when reg[0x09] & 4 or during boot)
        self.bios_rom = bytearray(0x0400)
        # Set BIOS vector table at $FC00..$FC3F (32 u16 pointers)
        # Data pointers in RAM ($0500..$051F, unused by OS since stack is $0100 and BSS ends at $04DA, C stack is $0800..$0FFF -> wait: $0500 is inside C stack $0500..$07FF? Wait: C stack starts at $0800 and grows down from $0800, so $04E0..$04FF is completely free!)
        struct.pack_into("<H", self.bios_rom, 0x00, 0x04E0)  # $0410: cmd_resp
        struct.pack_into("<H", self.bios_rom, 0x02, 0x04E2)  # $0412: usb_char
        struct.pack_into("<H", self.bios_rom, 0x04, 0x04E4)  # $0414: disk_err
        struct.pack_into("<H", self.bios_rom, 0x06, 0x04E6)  # $0416: block_len
        struct.pack_into("<H", self.bios_rom, 0x08, 0x04E8)  # $0418: dst_addr (u16)
        struct.pack_into("<H", self.bios_rom, 0x10, 0x04EA)  # $0420: sd_cmd_buf[6]
        # Function pointers at $FC40+ (each has RTS 0x60 at $FC40 + idx)
        for off in range(0x12, 0x40, 2):
            fn_addr = 0xFC00 + 0x40 + off
            struct.pack_into("<H", self.bios_rom, off, fn_addr)
            self.bios_rom[0x40 + off] = 0x60  # RTS

        # BIOS version / date / time / SN at $FFE8..$FFEF (offset 0x3E8..0x3EF)
        # Date: (year << 9) | (month << 5) | day -> 2015.09.27
        adate = (15 << 9) | (9 << 5) | 27
        # Time: hour * 60 + min -> 22:08 = 1328
        atime = 22 * 60 + 8
        struct.pack_into("<H", self.bios_rom, 0x3E8, adate)
        struct.pack_into("<H", self.bios_rom, 0x3EA, atime)
        self.bios_rom[0x3EC] = 11  # BIOS ver v1.11
        struct.pack_into("<H", self.bios_rom, 0x3EE, 12345)  # SN

        # PPU state
        self.chr_ram = bytearray(0x2000)
        self.vram = bytearray(0x1000)
        self.palette = bytearray(0x20)
        self.ppu_ctrl = 0
        self.ppu_mask = 0
        self.ppu_status = 0x80
        self.ppu_addr = 0
        self.ppu_latch = False
        self.ppu_buf = 0

        # Controller state
        self.joy_state = 0
        self.joy_shift = 0
        self.joy_strobe = 0

        # CPU state
        self.A = 0
        self.X = 0
        self.Y = 0
        self.S = 0xFD
        self.P = 0x24
        self.PC = 0x8000
        self.boot_decrypting = True  # Starts in BIOS k60 self-decryptor!

    def set_zn(self, val):
        val &= 0xFF
        if val == 0:
            self.P |= 0x02
        else:
            self.P &= ~0x02
        if val & 0x80:
            self.P |= 0x80
        else:
            self.P &= ~0x80
        return val

    def read(self, addr):
        addr &= 0xFFFF
        if addr < 0x2000:
            return self.ram[addr & 0x07FF]
        elif addr < 0x4000:
            reg = 0x2000 | (addr & 7)
            if reg == 0x2002:
                v = self.ppu_status
                self.ppu_status &= ~0x80  # clear VBlank on read
                self.ppu_latch = False
                return v
            elif reg == 0x2007:
                a = self.ppu_addr & 0x3FFF
                inc = 32 if (self.ppu_ctrl & 0x04) else 1
                self.ppu_addr = (self.ppu_addr + inc) & 0x3FFF
                if a < 0x2000:
                    ret = self.ppu_buf
                    self.ppu_buf = self.chr_ram[a]
                    return ret
                elif a < 0x3F00:
                    ret = self.ppu_buf
                    self.ppu_buf = self.vram[a & 0x0FFF]
                    return ret
                else:
                    return self.palette[a & 0x1F]
            return 0
        elif addr == 0x4016:
            v = (self.joy_shift & 1)
            self.joy_shift >>= 1
            return v
        elif addr == 0x4017:
            return 0
        elif addr == 0x4400:
            return self.reg_addr
        elif addr == 0x4401:
            return self.reg_data[self.reg_addr]
        elif 0x4800 <= addr < 0x5000:
            return self.buf_4800[addr - 0x4800]
        elif 0x6000 <= addr < 0x8000:
            bank = self.reg_data[0x81] & 0x3F
            return self.prg_ram[bank][addr - 0x6000]
        else:
            if self.boot_decrypting and addr < 0x8200:
                return self.k60[addr & 0xFF]
            if addr >= 0xFC00 and (self.reg_data[0x09] & 0x04):
                # Wait: at $FFFA..$FFFF, if OS vectors were written to PRG-RAM, return PRG-RAM or BIOS
                if addr < 0xFFFA:
                    return self.bios_rom[addr - 0xFC00]
            # $8000-$FFFF is mapped to PRG-RAM banks 0x0C, 0x0D, 0x0E, 0x0F
            bank = 0x0C + ((addr - 0x8000) >> 13)
            return self.prg_ram[bank][addr & 0x1FFF]

    def write(self, addr, val):
        addr &= 0xFFFF
        val &= 0xFF
        if addr < 0x2000:
            self.ram[addr & 0x07FF] = val
        elif addr < 0x4000:
            reg = 0x2000 | (addr & 7)
            if reg == 0x2000:
                self.ppu_ctrl = val
            elif reg == 0x2001:
                self.ppu_mask = val
            elif reg == 0x2005:
                self.ppu_latch = not self.ppu_latch
            elif reg == 0x2006:
                if not self.ppu_latch:
                    self.ppu_addr = ((val & 0x3F) << 8) | (self.ppu_addr & 0x00FF)
                else:
                    self.ppu_addr = (self.ppu_addr & 0xFF00) | val
                self.ppu_latch = not self.ppu_latch
            elif reg == 0x2007:
                a = self.ppu_addr & 0x3FFF
                if a < 0x2000:
                    self.chr_ram[a] = val
                elif a < 0x3F00:
                    self.vram[a & 0x0FFF] = val
                else:
                    pa = a & 0x1F
                    if pa in (0x10, 0x14, 0x18, 0x1C):
                        pa &= ~0x10
                    self.palette[pa] = val
                inc = 32 if (self.ppu_ctrl & 0x04) else 1
                self.ppu_addr = (self.ppu_addr + inc) & 0x3FFF
        elif addr == 0x4016:
            if (self.joy_strobe & 1) and not (val & 1):
                self.joy_shift = int(f"{self.joy_state & 0xFF:08b}"[::-1], 2)
            self.joy_strobe = val
        elif addr == 0x4400:
            self.reg_addr = val
        elif addr == 0x4401:
            self.reg_data[self.reg_addr] = val
        elif 0x4800 <= addr < 0x5000:
            self.buf_4800[addr - 0x4800] = val
        elif 0x6000 <= addr < 0x8000:
            bank = self.reg_data[0x81] & 0x3F
            self.prg_ram[bank][addr - 0x6000] = val
        else:
            bank = 0x0C + ((addr - 0x8000) >> 13)
            self.prg_ram[bank][addr & 0x1FFF] = val
            if self.boot_decrypting and addr == 0x8000 and val == 0x78:
                # The k60 decryptor just wrote 0x78 (SEI) to $8000 right before JMP $8000!
                self.boot_decrypting = False

    def handle_bios_trap(self, pc):
        off = pc - 0xFC40
        # Pointers in RAM:
        # $04E0: cmd_resp, $04E2: usb_char, $04E4: disk_err, $04E6: block_len, $04E8: dst_addr, $04EA: sd_cmd_buf
        if off == 0x1C:  # usbCheckRx ($042C)
            self.ram[0x04E4] = 0  # 0 = no USB data waiting
        elif off == 0x2C:  # sdSendCmd ($043C)
            self.ram[0x04E0] = 0  # cmd_resp = 0 (OK)
        elif off == 0x30:  # sdCloseCmd ($0440)
            self.ram[0x04E4] = 0
        elif off == 0x32:  # sdOpenRead ($0442)
            self.ram[0x04E4] = 0
        elif off == 0x3E:  # sdInit ($044E)
            self.ram[0x04E4] = 0
        elif off == 0x3A:  # fpgaInit ($044A)
            self.ram[0x04E4] = 0
        elif off == 0x26:  # sdReadBlocks ($0436)
            lba = struct.unpack("<I", bytes(self.read(0x8271 + i) for i in range(4)))[0]
            slen = self.ram[0x04E6]
            dst = self.ram[0x04E8] | (self.ram[0x04E9] << 8)
            for s in range(slen):
                sec_off = (lba + s) * 512
                for b in range(512):
                    val = self.sd_img[sec_off + b] if sec_off + b < len(self.sd_img) else 0
                    self.write(dst + s*512 + b, val)
            self.ram[0x04E4] = 0
        elif off == 0x28:  # sdReadBlocksPPU ($0438)
            lba = struct.unpack("<I", bytes(self.read(0x8271 + i) for i in range(4)))[0]
            slen = self.ram[0x04E6]
            for s in range(slen):
                sec_off = (lba + s) * 512
                for b in range(512):
                    val = self.sd_img[sec_off + b] if sec_off + b < len(self.sd_img) else 0
                    self.write(0x2007, val)
            self.ram[0x04E4] = 0
        elif off == 0x36:  # sdWriteBlocks ($0446)
            lba = struct.unpack("<I", bytes(self.read(0x8271 + i) for i in range(4)))[0]
            slen = self.ram[0x04E6]
            src = self.ram[0x04E8] | (self.ram[0x04E9] << 8)
            for s in range(slen):
                sec_off = (lba + s) * 512
                for b in range(512):
                    if sec_off + b < len(self.sd_img):
                        self.sd_img[sec_off + b] = self.read(src + s*512 + b)
            self.ram[0x04E4] = 0

    def push(self, val):
        self.ram[0x0100 | self.S] = val & 0xFF
        self.S = (self.S - 1) & 0xFF

    def pull(self):
        self.S = (self.S + 1) & 0xFF
        return self.ram[0x0100 | self.S]

    def trigger_nmi(self):
        self.push((self.PC >> 8) & 0xFF)
        self.push(self.PC & 0xFF)
        self.push((self.P & ~0x10) | 0x20)
        self.P |= 0x04
        lo = self.read(0xFFFA)
        hi = self.read(0xFFFB)
        self.PC = lo | (hi << 8)

    def step(self):
        if 0xFC50 <= self.PC < 0xFC80 and (self.reg_data[0x09] & 0x04):
            self.handle_bios_trap(self.PC)

        pc = self.PC
        op = self.read(pc)
        self.PC = (pc + 1) & 0xFFFF

        # Addressing mode helpers
        def imm():
            v = self.PC; self.PC = (self.PC + 1) & 0xFFFF; return v
        def zp():
            v = self.read(self.PC); self.PC = (self.PC + 1) & 0xFFFF; return v
        def zpx():
            v = (self.read(self.PC) + self.X) & 0xFF; self.PC = (self.PC + 1) & 0xFFFF; return v
        def zpy():
            v = (self.read(self.PC) + self.Y) & 0xFF; self.PC = (self.PC + 1) & 0xFFFF; return v
        def abso():
            lo = self.read(self.PC); hi = self.read(self.PC + 1); self.PC = (self.PC + 2) & 0xFFFF; return lo | (hi << 8)
        def absx():
            return (abso() + self.X) & 0xFFFF
        def absy():
            return (abso() + self.Y) & 0xFFFF
        def indx():
            z = (self.read(self.PC) + self.X) & 0xFF; self.PC = (self.PC + 1) & 0xFFFF
            return self.read(z) | (self.read((z + 1) & 0xFF) << 8)
        def indy():
            z = self.read(self.PC); self.PC = (self.PC + 1) & 0xFFFF
            base = self.read(z) | (self.read((z + 1) & 0xFF) << 8)
            return (base + self.Y) & 0xFFFF

        def adc(v):
            c = 1 if (self.P & 1) else 0
            r = self.A + v + c
            if r > 0xFF: self.P |= 1
            else: self.P &= ~1
            if (~(self.A ^ v) & (self.A ^ r)) & 0x80: self.P |= 0x40
            else: self.P &= ~0x40
            self.A = self.set_zn(r)

        def sbc(v):
            adc(v ^ 0xFF)

        def cmp(reg, v):
            r = reg - v
            if reg >= v: self.P |= 1
            else: self.P &= ~1
            self.set_zn(r)

        def branch(cond):
            off = self.read(self.PC)
            self.PC = (self.PC + 1) & 0xFFFF
            if cond:
                if off & 0x80: off -= 256
                self.PC = (self.PC + off) & 0xFFFF

        # Opcodes
        if op == 0x00:  # BRK
            self.PC = (self.PC + 1) & 0xFFFF
            self.push(self.PC >> 8); self.push(self.PC & 0xFF); self.push(self.P | 0x30)
            self.P |= 0x04
            self.PC = self.read(0xFFFE) | (self.read(0xFFFF) << 8)
        elif op == 0xEA: pass  # NOP
        elif op == 0x78: self.P |= 0x04   # SEI
        elif op == 0x58: self.P &= ~0x04  # CLI
        elif op == 0xD8: self.P &= ~0x08  # CLD
        elif op == 0xF8: self.P |= 0x08   # SED
        elif op == 0x18: self.P &= ~0x01  # CLC
        elif op == 0x38: self.P |= 0x01   # SEC
        elif op == 0xB8: self.P &= ~0x40  # CLV
        # LDA
        elif op == 0xA9: self.A = self.set_zn(self.read(imm()))
        elif op == 0xA5: self.A = self.set_zn(self.read(zp()))
        elif op == 0xB5: self.A = self.set_zn(self.read(zpx()))
        elif op == 0xAD: self.A = self.set_zn(self.read(abso()))
        elif op == 0xBD: self.A = self.set_zn(self.read(absx()))
        elif op == 0xB9: self.A = self.set_zn(self.read(absy()))
        elif op == 0xA1: self.A = self.set_zn(self.read(indx()))
        elif op == 0xB1: self.A = self.set_zn(self.read(indy()))
        # LDX
        elif op == 0xA2: self.X = self.set_zn(self.read(imm()))
        elif op == 0xA6: self.X = self.set_zn(self.read(zp()))
        elif op == 0xB6: self.X = self.set_zn(self.read(zpy()))
        elif op == 0xAE: self.X = self.set_zn(self.read(abso()))
        elif op == 0xBE: self.X = self.set_zn(self.read(absy()))
        # LDY
        elif op == 0xA0: self.Y = self.set_zn(self.read(imm()))
        elif op == 0xA4: self.Y = self.set_zn(self.read(zp()))
        elif op == 0xB4: self.Y = self.set_zn(self.read(zpx()))
        elif op == 0xAC: self.Y = self.set_zn(self.read(abso()))
        elif op == 0xBC: self.Y = self.set_zn(self.read(absx()))
        # STA
        elif op == 0x85: self.write(zp(), self.A)
        elif op == 0x95: self.write(zpx(), self.A)
        elif op == 0x8D: self.write(abso(), self.A)
        elif op == 0x9D: self.write(absx(), self.A)
        elif op == 0x99: self.write(absy(), self.A)
        elif op == 0x81: self.write(indx(), self.A)
        elif op == 0x91: self.write(indy(), self.A)
        # STX
        elif op == 0x86: self.write(zp(), self.X)
        elif op == 0x96: self.write(zpy(), self.X)
        elif op == 0x8E: self.write(abso(), self.X)
        # STY
        elif op == 0x84: self.write(zp(), self.Y)
        elif op == 0x94: self.write(zpx(), self.Y)
        elif op == 0x8C: self.write(abso(), self.Y)
        # Transfers
        elif op == 0xAA: self.X = self.set_zn(self.A)
        elif op == 0x8A: self.A = self.set_zn(self.X)
        elif op == 0xA8: self.Y = self.set_zn(self.A)
        elif op == 0x98: self.A = self.set_zn(self.Y)
        elif op == 0x9A: self.S = self.X
        elif op == 0xBA: self.X = self.set_zn(self.S)
        # Stack
        elif op == 0x48: self.push(self.A)
        elif op == 0x68: self.A = self.set_zn(self.pull())
        elif op == 0x08: self.push(self.P | 0x30)
        elif op == 0x28: self.P = (self.pull() & ~0x10) | 0x20
        # Jumps / Calls
        elif op == 0x4C: self.PC = abso()
        elif op == 0x6C:
            a = abso()
            lo = self.read(a)
            hi = self.read((a & 0xFF00) | ((a + 1) & 0xFF))
            self.PC = lo | (hi << 8)
        elif op == 0x20:
            t = abso()
            ret = (self.PC - 1) & 0xFFFF
            self.push(ret >> 8); self.push(ret & 0xFF)
            self.PC = t
        elif op == 0x60:
            lo = self.pull(); hi = self.pull()
            self.PC = ((lo | (hi << 8)) + 1) & 0xFFFF
        elif op == 0x40:
            self.P = (self.pull() & ~0x10) | 0x20
            lo = self.pull(); hi = self.pull()
            self.PC = lo | (hi << 8)
        # Branches
        elif op == 0x10: branch(not (self.P & 0x80))  # BPL
        elif op == 0x30: branch(bool(self.P & 0x80))  # BMI
        elif op == 0x50: branch(not (self.P & 0x40))  # BVC
        elif op == 0x70: branch(bool(self.P & 0x40))  # BVS
        elif op == 0x90: branch(not (self.P & 0x01))  # BCC
        elif op == 0xB0: branch(bool(self.P & 0x01))  # BCS
        elif op == 0xD0: branch(not (self.P & 0x02))  # BNE
        elif op == 0xF0: branch(bool(self.P & 0x02))  # BEQ
        # AND
        elif op == 0x29: self.A = self.set_zn(self.A & self.read(imm()))
        elif op == 0x25: self.A = self.set_zn(self.A & self.read(zp()))
        elif op == 0x35: self.A = self.set_zn(self.A & self.read(zpx()))
        elif op == 0x2D: self.A = self.set_zn(self.A & self.read(abso()))
        elif op == 0x3D: self.A = self.set_zn(self.A & self.read(absx()))
        elif op == 0x39: self.A = self.set_zn(self.A & self.read(absy()))
        elif op == 0x21: self.A = self.set_zn(self.A & self.read(indx()))
        elif op == 0x31: self.A = self.set_zn(self.A & self.read(indy()))
        # ORA
        elif op == 0x09: self.A = self.set_zn(self.A | self.read(imm()))
        elif op == 0x05: self.A = self.set_zn(self.A | self.read(zp()))
        elif op == 0x15: self.A = self.set_zn(self.A | self.read(zpx()))
        elif op == 0x0D: self.A = self.set_zn(self.A | self.read(abso()))
        elif op == 0x1D: self.A = self.set_zn(self.A | self.read(absx()))
        elif op == 0x19: self.A = self.set_zn(self.A | self.read(absy()))
        elif op == 0x01: self.A = self.set_zn(self.A | self.read(indx()))
        elif op == 0x11: self.A = self.set_zn(self.A | self.read(indy()))
        # EOR
        elif op == 0x49: self.A = self.set_zn(self.A ^ self.read(imm()))
        elif op == 0x45: self.A = self.set_zn(self.A ^ self.read(zp()))
        elif op == 0x55: self.A = self.set_zn(self.A ^ self.read(zpx()))
        elif op == 0x4D: self.A = self.set_zn(self.A ^ self.read(abso()))
        elif op == 0x5D: self.A = self.set_zn(self.A ^ self.read(absx()))
        elif op == 0x59: self.A = self.set_zn(self.A ^ self.read(absy()))
        elif op == 0x41: self.A = self.set_zn(self.A ^ self.read(indx()))
        elif op == 0x51: self.A = self.set_zn(self.A ^ self.read(indy()))
        # BIT
        elif op in (0x24, 0x2C):
            v = self.read(zp() if op == 0x24 else abso())
            if (self.A & v) == 0: self.P |= 0x02
            else: self.P &= ~0x02
            self.P = (self.P & ~0xC0) | (v & 0xC0)
        # ADC / SBC
        elif op == 0x69: adc(self.read(imm()))
        elif op == 0x65: adc(self.read(zp()))
        elif op == 0x75: adc(self.read(zpx()))
        elif op == 0x6D: adc(self.read(abso()))
        elif op == 0x7D: adc(self.read(absx()))
        elif op == 0x79: adc(self.read(absy()))
        elif op == 0x61: adc(self.read(indx()))
        elif op == 0x71: adc(self.read(indy()))
        elif op == 0xE9: sbc(self.read(imm()))
        elif op == 0xE5: sbc(self.read(zp()))
        elif op == 0xF5: sbc(self.read(zpx()))
        elif op == 0xED: sbc(self.read(abso()))
        elif op == 0xFD: sbc(self.read(absx()))
        elif op == 0xF9: sbc(self.read(absy()))
        elif op == 0xE1: sbc(self.read(indx()))
        elif op == 0xF1: sbc(self.read(indy()))
        # CMP / CPX / CPY
        elif op == 0xC9: cmp(self.A, self.read(imm()))
        elif op == 0xC5: cmp(self.A, self.read(zp()))
        elif op == 0xD5: cmp(self.A, self.read(zpx()))
        elif op == 0xCD: cmp(self.A, self.read(abso()))
        elif op == 0xDD: cmp(self.A, self.read(absx()))
        elif op == 0xD9: cmp(self.A, self.read(absy()))
        elif op == 0xC1: cmp(self.A, self.read(indx()))
        elif op == 0xD1: cmp(self.A, self.read(indy()))
        elif op == 0xE0: cmp(self.X, self.read(imm()))
        elif op == 0xE4: cmp(self.X, self.read(zp()))
        elif op == 0xEC: cmp(self.X, self.read(abso()))
        elif op == 0xC0: cmp(self.Y, self.read(imm()))
        elif op == 0xC4: cmp(self.Y, self.read(zp()))
        elif op == 0xCC: cmp(self.Y, self.read(abso()))
        # INC / DEC / INX / DEX / INY / DEY
        elif op == 0xE8: self.X = self.set_zn((self.X + 1) & 0xFF)
        elif op == 0xCA: self.X = self.set_zn((self.X - 1) & 0xFF)
        elif op == 0xC8: self.Y = self.set_zn((self.Y + 1) & 0xFF)
        elif op == 0x88: self.Y = self.set_zn((self.Y - 1) & 0xFF)
        elif op in (0xE6, 0xF6, 0xEE, 0xFE):
            a = zp() if op == 0xE6 else (zpx() if op == 0xF6 else (abso() if op == 0xEE else absx()))
            self.write(a, self.set_zn((self.read(a) + 1) & 0xFF))
        elif op in (0xC6, 0xD6, 0xCE, 0xDE):
            a = zp() if op == 0xC6 else (zpx() if op == 0xD6 else (abso() if op == 0xCE else absx()))
            self.write(a, self.set_zn((self.read(a) - 1) & 0xFF))
        # Shifts / Rotates
        elif op == 0x0A:
            self.P = (self.P & ~1) | ((self.A >> 7) & 1)
            self.A = self.set_zn((self.A << 1) & 0xFF)
        elif op in (0x06, 0x16, 0x0E, 0x1E):
            a = zp() if op == 0x06 else (zpx() if op == 0x16 else (abso() if op == 0x0E else absx()))
            v = self.read(a)
            self.P = (self.P & ~1) | ((v >> 7) & 1)
            self.write(a, self.set_zn((v << 1) & 0xFF))
        elif op == 0x4A:
            self.P = (self.P & ~1) | (self.A & 1)
            self.A = self.set_zn(self.A >> 1)
        elif op in (0x46, 0x56, 0x4E, 0x5E):
            a = zp() if op == 0x46 else (zpx() if op == 0x56 else (abso() if op == 0x4E else absx()))
            v = self.read(a)
            self.P = (self.P & ~1) | (v & 1)
            self.write(a, self.set_zn(v >> 1))
        elif op == 0x2A:
            c = self.P & 1
            self.P = (self.P & ~1) | ((self.A >> 7) & 1)
            self.A = self.set_zn(((self.A << 1) & 0xFF) | c)
        elif op in (0x26, 0x36, 0x2E, 0x3E):
            a = zp() if op == 0x26 else (zpx() if op == 0x36 else (abso() if op == 0x2E else absx()))
            v = self.read(a); c = self.P & 1
            self.P = (self.P & ~1) | ((v >> 7) & 1)
            self.write(a, self.set_zn(((v << 1) & 0xFF) | c))
        elif op == 0x6A:
            c = (self.P & 1) << 7
            self.P = (self.P & ~1) | (self.A & 1)
            self.A = self.set_zn((self.A >> 1) | c)
        elif op in (0x66, 0x76, 0x6E, 0x7E):
            a = zp() if op == 0x66 else (zpx() if op == 0x76 else (abso() if op == 0x6E else absx()))
            v = self.read(a); c = (self.P & 1) << 7
            self.P = (self.P & ~1) | (v & 1)
            self.write(a, self.set_zn((v >> 1) | c))
        else:
            raise RuntimeError(f"Unknown opcode ${op:02X} at PC=${pc:04X}")

    def run_frames(self, n_frames=1, joy=0):
        self.joy_state = joy
        for _ in range(n_frames):
            # Run ~4000 instructions per frame (or break early on VBlank wait loop at $83B3)
            for _ in range(8000):
                # Fast-forward VBlank wait loops
                if self.read(self.PC) == 0x2C and self.read(self.PC+1) == 0x02 and self.read(self.PC+2) == 0x20:
                    self.ppu_status |= 0x80
                if self.PC == 0x839E and self.ram[0x9E] == 0:
                    break
                self.step()
            self.ppu_status |= 0x80
            if self.ppu_ctrl & 0x80:
                self.trigger_nmi()

    def press_button(self, btn_mask, hold_frames=1, wait_frames=15):
        self.run_frames(hold_frames, joy=btn_mask)
        self.ram[0x0484] = 0
        self.run_frames(wait_frames, joy=0)

    def render_screen(self, out_path, scale=2):
        bg_table = 0x1000 if (self.ppu_ctrl & 0x10) else 0x0000
        grid = [[(0, 0, 0)] * 256 for _ in range(240)]
        for ty in range(30):
            for tx in range(32):
                tile_idx = self.vram[ty * 32 + tx]
                attr_byte = self.vram[0x03C0 + (ty // 4) * 8 + (tx // 4)]
                shift = ((ty % 4) // 2) * 4 + ((tx % 4) // 2) * 2
                pal_idx = (attr_byte >> shift) & 3
                tile_off = bg_table + tile_idx * 16
                for py in range(8):
                    p0 = self.chr_ram[tile_off + py]
                    p1 = self.chr_ram[tile_off + py + 8]
                    for px in range(8):
                        bit = 7 - px
                        c_low = ((p0 >> bit) & 1) | (((p1 >> bit) & 1) << 1)
                        if c_low == 0:
                            nes_col = self.palette[0] & 0x3F
                        else:
                            nes_col = self.palette[pal_idx * 4 + c_low] & 0x3F
                        grid[ty * 8 + py][tx * 8 + px] = NES_PALETTE[nes_col]
        rgb_rows = []
        for y in range(240):
            row_bytes = bytearray()
            for x in range(256):
                r, g, b = grid[y][x]
                for _ in range(scale):
                    row_bytes.extend((r, g, b))
            for _ in range(scale):
                rgb_rows.append(bytes(row_bytes))
        save_png(out_path, 256 * scale, 240 * scale, rgb_rows)

    def dump_screen_text(self):
        accent_map = {
            0x01: "á", 0x02: "ã", 0x03: "â", 0x04: "é", 0x05: "ê",
            0x06: "í", 0x07: "ó", 0x08: "õ", 0x09: "ô", 0x0A: "ú",
            0x0B: "ç", 0x0C: "Á", 0x0D: "Ã", 0x0E: "Ç", 0x0F: "É",
            0x10: "Í", 0x11: "Ó", 0x12: "Õ", 0x13: "Ú",
        }
        lines = []
        for ty in range(30):
            row = []
            for tx in range(32):
                c = self.vram[ty * 32 + tx] & 0x7F
                if c in accent_map:
                    row.append(accent_map[c])
                elif 32 <= c < 127:
                    row.append(chr(c))
                else:
                    row.append(" ")
            s = "".join(row).rstrip()
            if s:
                lines.append(f"{ty:02d}: {s}")
        return "\n".join(lines)


if __name__ == "__main__":
    emu = EverDriveN8Emu(
        r"C:\Development\nes-everdrive\EDFC\OS.BIN",
        r"C:\Development\nes-everdrive"
    )
    # Run initial boot -> decrypts OS.BIN via k60, runs osInit, shows "Settings reset to default"
    emu.run_frames(20)
    print("=== Screen 1 (First Boot / Settings Reset) ===")
    print(emu.dump_screen_text())
    # Press A (0x80) or B (0x40) to dismiss error and enter File Browser!
    emu.press_button(0x80, wait_frames=20)
    print("=== Screen 2 (File Browser) ===")
    print(emu.dump_screen_text())
