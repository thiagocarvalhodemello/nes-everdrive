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
        base = "".join(c for c in base.upper() if c.isascii() and (c.isalnum() or c in "_-"))[:8].ljust(8)
        ext = "".join(c for c in ext[1:].upper() if c.isascii() and (c.isalnum() or c in "_-"))[:3].ljust(3)
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

    def is_plain_83(name):
        base, ext = os.path.splitext(name)
        ok = lambda s: all(c.isalnum() or c in "_-" for c in s) and s == s.upper()
        return 0 < len(base) <= 8 and len(ext) <= 4 and ok(base) and ok(ext[1:])

    def make_sfn_unique(name, used):
        sfn = make_sfn(name)
        if is_plain_83(name):
            used.add(sfn)
            return sfn
        base, ext = sfn[:8].rstrip(), sfn[8:]
        for n in range(1, 1000):
            tail = b"~" + str(n).encode()
            cand = (base[:8 - len(tail)] + tail).ljust(8) + ext
            if cand not in used:
                used.add(cand)
                return cand
        raise ValueError("too many SFN collisions")

    def lfn_entries(name, sfn11):
        """VFAT long-name entries (to be placed before the 8.3 entry)."""
        csum = 0
        for b in sfn11:
            csum = (((csum & 1) << 7) + (csum >> 1) + b) & 0xFF
        u = name.encode("utf-16-le") + b"\x00\x00"
        chunks = [u[i:i + 26] for i in range(0, len(u), 26)]
        chunks[-1] = chunks[-1].ljust(26, b"\xff")
        out = bytearray()
        for seq in range(len(chunks), 0, -1):
            c = chunks[seq - 1]
            e = bytearray(32)
            e[0] = seq | (0x40 if seq == len(chunks) else 0)
            e[1:11], e[11], e[13] = c[0:10], 0x0F, csum
            e[14:26], e[28:32] = c[10:22], c[22:26]
            out += e
        return out

    def named_entry(item, attr, cluster, size, used):
        sfn = make_sfn_unique(item, used)
        pre = b"" if is_plain_83(item) else lfn_entries(item, sfn)
        return pre + make_dir_entry(sfn, attr, cluster, size)

    def skip(item):
        return item.startswith(".") or item in ('sdcard', 'releases', '__pycache__', 'screens_en', 'screens_ptbr')

    def populate_dir(fs_path, parent_cluster, is_root=False):
        entries = bytearray()
        used = set()
        my_cluster = next_cluster if not is_root else 0
        if not is_root:
            # size the directory for its entries (8.3 + long-name entries)
            n = 2 + sum(1 + (len(i) + 13) // 13 for i in os.listdir(fs_path) if not skip(i))
            clusters = (n * 32 + sectors_per_cluster * 512 - 1) // (sectors_per_cluster * 512)
            my_cluster = alloc_clusters(bytes(clusters * sectors_per_cluster * 512))
            entries += make_dir_entry(b".          ", 0x10, my_cluster, 0)
            entries += make_dir_entry(b"..         ", 0x10, parent_cluster, 0)
        for item in sorted(os.listdir(fs_path)):
            if skip(item):
                continue
            full = os.path.join(fs_path, item)
            if os.path.isdir(full):
                sub_c = populate_dir(full, my_cluster, is_root=False)
                entries += named_entry(item, 0x10, sub_c, 0, used)
            elif os.path.isfile(full):
                raw = open(full, "rb").read()
                if len(raw) == 0:
                    continue
                fc = alloc_clusters(raw)
                entries += named_entry(item, 0x20, fc, len(raw), used)
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
        # The patched OS.BIN overwrites file 0xDB00.. with the theme runtime, so the
        # decryptor page must come from the untouched factory image.
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        k60_src = os.path.join(repo_root, "EDFC-ORIGINAL", "OS.BIN")
        if not os.path.exists(k60_src):
            k60_src = os_bin_path
        orig_os = open(k60_src, "rb").read()
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
        self.oam = bytearray(256)
        self.oam_addr = 0
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
        elif addr >= 0x8000:
            if self.boot_decrypting and addr < 0x8200:
                return self.k60[addr & 0xFF]
            if addr >= 0xFC00 and (self.reg_data[0x09] & 0x04):
                if addr < 0xFFFA:
                    return self.bios_rom[addr - 0xFC00]
            # $8000-$FFFF is mapped to PRG-RAM banks 0x0C, 0x0D, 0x0E, 0x0F
            return self.prg_ram[0x0C + ((addr - 0x8000) >> 13)][addr & 0x1FFF]
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
            elif reg == 0x2003:
                self.oam_addr = val
            elif reg == 0x2004:
                self.oam[self.oam_addr] = val
                self.oam_addr = (self.oam_addr + 1) & 0xFF
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
        elif addr == 0x4014:
            page = val << 8
            for k in range(256):
                self.oam[(self.oam_addr + k) & 0xFF] = self.read(page + k)
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

    def _imm(self):
        v = self.PC; self.PC = (self.PC + 1) & 0xFFFF; return v
    def _zp(self):
        v = self.read(self.PC); self.PC = (self.PC + 1) & 0xFFFF; return v
    def _zpx(self):
        v = (self.read(self.PC) + self.X) & 0xFF; self.PC = (self.PC + 1) & 0xFFFF; return v
    def _zpy(self):
        v = (self.read(self.PC) + self.Y) & 0xFF; self.PC = (self.PC + 1) & 0xFFFF; return v
    def _abso(self):
        lo = self.read(self.PC); hi = self.read(self.PC + 1); self.PC = (self.PC + 2) & 0xFFFF; return lo | (hi << 8)
    def _absx(self):
        return (self._abso() + self.X) & 0xFFFF
    def _absy(self):
        return (self._abso() + self.Y) & 0xFFFF
    def _indx(self):
        z = (self.read(self.PC) + self.X) & 0xFF; self.PC = (self.PC + 1) & 0xFFFF
        return self.read(z) | (self.read((z + 1) & 0xFF) << 8)
    def _indy(self):
        z = self.read(self.PC); self.PC = (self.PC + 1) & 0xFFFF
        base = self.read(z) | (self.read((z + 1) & 0xFF) << 8)
        return (base + self.Y) & 0xFFFF

    def _adc(self, v):
        c = 1 if (self.P & 1) else 0
        r = self.A + v + c
        if r > 0xFF: self.P |= 1
        else: self.P &= ~1
        if (~(self.A ^ v) & (self.A ^ r)) & 0x80: self.P |= 0x40
        else: self.P &= ~0x40
        self.A = self.set_zn(r)

    def _sbc(self, v):
        self._adc(v ^ 0xFF)

    def _cmp(self, reg, v):
        r = reg - v
        if reg >= v: self.P |= 1
        else: self.P &= ~1
        self.set_zn(r)

    def _branch(self, cond):
        off = self.read(self.PC)
        self.PC = (self.PC + 1) & 0xFFFF
        if cond:
            if off & 0x80: off -= 256
            self.PC = (self.PC + off) & 0xFFFF


    def step(self):
        if 0xFC50 <= self.PC < 0xFC80 and (self.reg_data[0x09] & 0x04):
            self.handle_bios_trap(self.PC)

        pc = self.PC
        op = self.read(pc)
        self.PC = (pc + 1) & 0xFFFF

        f = _OPS[op]
        if f is None:
            raise RuntimeError(f"Unknown opcode ${op:02X} at PC=${pc:04X}")
        f(self, op, pc)

    def run_frames(self, n_frames=1, joy=0):
        self.joy_state = joy
        for _ in range(n_frames):
            # Run ~4000 instructions per frame (or break early on VBlank wait loop at $83B3)
            for _ in range(8000):
                # Fast-forward VBlank wait loops
                if self.read(self.PC) == 0x2C and self.read(self.PC+1) == 0x02 and self.read(self.PC+2) == 0x20:
                    self.ppu_status |= 0x80
                if self.PC in (0x839E, 0x838C) and self.ram[0x9E] == 0:
                    break
                self.step()
            self.ppu_status |= 0x80
            if self.ppu_ctrl & 0x80:
                self.trigger_nmi()

    def boot_to_main_menu(self, max_frames=300):
        """Run the boot until the OS shows the main menu (opened once after boot). True if seen.
        A fresh cartridge RAM has no OS settings: the OS recreates them and shows error A7
        waiting for a button (as on a real console the first time) - confirm it."""
        for _ in range(max_frames // 5):
            self.run_frames(5)
            txt = self.dump_screen_text()
            if "Menu Principal" in txt:
                self.run_frames(5)
                return True
            if any(l.strip().endswith("A7") for l in txt.splitlines()):
                self.press_button(0x40, hold_frames=8, wait_frames=10)
        return False

    def boot_to_browser(self):
        """Boot, then close the main menu shown after boot (A = cancel) -> file browser."""
        seen = self.boot_to_main_menu()
        if seen:
            self.press_button(0x80, wait_frames=40)
        self.run_frames(20)
        return seen

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
        if self.ppu_mask & 0x10:
            self._render_sprites(grid)
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

    def _render_sprites(self, grid):
        tall = bool(self.ppu_ctrl & 0x20)
        for n in range(63, -1, -1):             # lower index drawn last = on top
            y, tile, attr, x = self.oam[n*4:n*4+4]
            y += 1
            if y >= 240:
                continue
            if tall:
                table, tile = (0x1000 if tile & 1 else 0), tile & 0xFE
            else:
                table = 0x1000 if self.ppu_ctrl & 0x08 else 0
            pal = 0x10 + (attr & 3) * 4
            for py in range(16 if tall else 8):
                sy = py if not (attr & 0x80) else (15 if tall else 7) - py
                t = tile + (sy >> 3)
                off = table + t * 16 + (sy & 7)
                p0, p1 = self.chr_ram[off], self.chr_ram[off + 8]
                for px in range(8):
                    bit = 7 - px if not (attr & 0x40) else px
                    c = ((p0 >> bit) & 1) | (((p1 >> bit) & 1) << 1)
                    if c and 0 <= y + py < 240 and x + px < 256:
                        grid[y + py][x + px] = NES_PALETTE[self.palette[pal + c] & 0x3F]

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


# ---- opcode handlers: one function per opcode group (generated from the old if/elif chain)
def _op0(self, op, pc):  # $00
    # BRK
    self.PC = (self.PC + 1) & 0xFFFF
    self.push(self.PC >> 8); self.push(self.PC & 0xFF); self.push(self.P | 0x30)
    self.P |= 0x04
    self.PC = self.read(0xFFFE) | (self.read(0xFFFF) << 8)
def _op1(self, op, pc):  # $EA
    pass
def _op2(self, op, pc):  # $78
    self.P |= 0x04   # SEI
def _op3(self, op, pc):  # $58
    self.P &= ~0x04  # CLI
def _op4(self, op, pc):  # $D8
    self.P &= ~0x08  # CLD
def _op5(self, op, pc):  # $F8
    self.P |= 0x08   # SED
def _op6(self, op, pc):  # $18
    self.P &= ~0x01  # CLC
def _op7(self, op, pc):  # $38
    self.P |= 0x01   # SEC
def _op8(self, op, pc):  # $B8
    self.P &= ~0x40  # CLV
def _op9(self, op, pc):  # $A9
    self.A = self.set_zn(self.read(self._imm()))
def _op10(self, op, pc):  # $A5
    self.A = self.set_zn(self.read(self._zp()))
def _op11(self, op, pc):  # $B5
    self.A = self.set_zn(self.read(self._zpx()))
def _op12(self, op, pc):  # $AD
    self.A = self.set_zn(self.read(self._abso()))
def _op13(self, op, pc):  # $BD
    self.A = self.set_zn(self.read(self._absx()))
def _op14(self, op, pc):  # $B9
    self.A = self.set_zn(self.read(self._absy()))
def _op15(self, op, pc):  # $A1
    self.A = self.set_zn(self.read(self._indx()))
def _op16(self, op, pc):  # $B1
    self.A = self.set_zn(self.read(self._indy()))
def _op17(self, op, pc):  # $A2
    self.X = self.set_zn(self.read(self._imm()))
def _op18(self, op, pc):  # $A6
    self.X = self.set_zn(self.read(self._zp()))
def _op19(self, op, pc):  # $B6
    self.X = self.set_zn(self.read(self._zpy()))
def _op20(self, op, pc):  # $AE
    self.X = self.set_zn(self.read(self._abso()))
def _op21(self, op, pc):  # $BE
    self.X = self.set_zn(self.read(self._absy()))
def _op22(self, op, pc):  # $A0
    self.Y = self.set_zn(self.read(self._imm()))
def _op23(self, op, pc):  # $A4
    self.Y = self.set_zn(self.read(self._zp()))
def _op24(self, op, pc):  # $B4
    self.Y = self.set_zn(self.read(self._zpx()))
def _op25(self, op, pc):  # $AC
    self.Y = self.set_zn(self.read(self._abso()))
def _op26(self, op, pc):  # $BC
    self.Y = self.set_zn(self.read(self._absx()))
def _op27(self, op, pc):  # $85
    self.write(self._zp(), self.A)
def _op28(self, op, pc):  # $95
    self.write(self._zpx(), self.A)
def _op29(self, op, pc):  # $8D
    self.write(self._abso(), self.A)
def _op30(self, op, pc):  # $9D
    self.write(self._absx(), self.A)
def _op31(self, op, pc):  # $99
    self.write(self._absy(), self.A)
def _op32(self, op, pc):  # $81
    self.write(self._indx(), self.A)
def _op33(self, op, pc):  # $91
    self.write(self._indy(), self.A)
def _op34(self, op, pc):  # $86
    self.write(self._zp(), self.X)
def _op35(self, op, pc):  # $96
    self.write(self._zpy(), self.X)
def _op36(self, op, pc):  # $8E
    self.write(self._abso(), self.X)
def _op37(self, op, pc):  # $84
    self.write(self._zp(), self.Y)
def _op38(self, op, pc):  # $94
    self.write(self._zpx(), self.Y)
def _op39(self, op, pc):  # $8C
    self.write(self._abso(), self.Y)
def _op40(self, op, pc):  # $AA
    self.X = self.set_zn(self.A)
def _op41(self, op, pc):  # $8A
    self.A = self.set_zn(self.X)
def _op42(self, op, pc):  # $A8
    self.Y = self.set_zn(self.A)
def _op43(self, op, pc):  # $98
    self.A = self.set_zn(self.Y)
def _op44(self, op, pc):  # $9A
    self.S = self.X
def _op45(self, op, pc):  # $BA
    self.X = self.set_zn(self.S)
def _op46(self, op, pc):  # $48
    self.push(self.A)
def _op47(self, op, pc):  # $68
    self.A = self.set_zn(self.pull())
def _op48(self, op, pc):  # $08
    self.push(self.P | 0x30)
def _op49(self, op, pc):  # $28
    self.P = (self.pull() & ~0x10) | 0x20
def _op50(self, op, pc):  # $4C
    self.PC = self._abso()
def _op51(self, op, pc):  # $6C
    a = self._abso()
    lo = self.read(a)
    hi = self.read((a & 0xFF00) | ((a + 1) & 0xFF))
    self.PC = lo | (hi << 8)
def _op52(self, op, pc):  # $20
    t = self._abso()
    ret = (self.PC - 1) & 0xFFFF
    self.push(ret >> 8); self.push(ret & 0xFF)
    self.PC = t
def _op53(self, op, pc):  # $60
    lo = self.pull(); hi = self.pull()
    self.PC = ((lo | (hi << 8)) + 1) & 0xFFFF
def _op54(self, op, pc):  # $40
    self.P = (self.pull() & ~0x10) | 0x20
    lo = self.pull(); hi = self.pull()
    self.PC = lo | (hi << 8)
def _op55(self, op, pc):  # $10
    self._branch(not (self.P & 0x80))  # BPL
def _op56(self, op, pc):  # $30
    self._branch(bool(self.P & 0x80))  # BMI
def _op57(self, op, pc):  # $50
    self._branch(not (self.P & 0x40))  # BVC
def _op58(self, op, pc):  # $70
    self._branch(bool(self.P & 0x40))  # BVS
def _op59(self, op, pc):  # $90
    self._branch(not (self.P & 0x01))  # BCC
def _op60(self, op, pc):  # $B0
    self._branch(bool(self.P & 0x01))  # BCS
def _op61(self, op, pc):  # $D0
    self._branch(not (self.P & 0x02))  # BNE
def _op62(self, op, pc):  # $F0
    self._branch(bool(self.P & 0x02))  # BEQ
def _op63(self, op, pc):  # $29
    self.A = self.set_zn(self.A & self.read(self._imm()))
def _op64(self, op, pc):  # $25
    self.A = self.set_zn(self.A & self.read(self._zp()))
def _op65(self, op, pc):  # $35
    self.A = self.set_zn(self.A & self.read(self._zpx()))
def _op66(self, op, pc):  # $2D
    self.A = self.set_zn(self.A & self.read(self._abso()))
def _op67(self, op, pc):  # $3D
    self.A = self.set_zn(self.A & self.read(self._absx()))
def _op68(self, op, pc):  # $39
    self.A = self.set_zn(self.A & self.read(self._absy()))
def _op69(self, op, pc):  # $21
    self.A = self.set_zn(self.A & self.read(self._indx()))
def _op70(self, op, pc):  # $31
    self.A = self.set_zn(self.A & self.read(self._indy()))
def _op71(self, op, pc):  # $09
    self.A = self.set_zn(self.A | self.read(self._imm()))
def _op72(self, op, pc):  # $05
    self.A = self.set_zn(self.A | self.read(self._zp()))
def _op73(self, op, pc):  # $15
    self.A = self.set_zn(self.A | self.read(self._zpx()))
def _op74(self, op, pc):  # $0D
    self.A = self.set_zn(self.A | self.read(self._abso()))
def _op75(self, op, pc):  # $1D
    self.A = self.set_zn(self.A | self.read(self._absx()))
def _op76(self, op, pc):  # $19
    self.A = self.set_zn(self.A | self.read(self._absy()))
def _op77(self, op, pc):  # $01
    self.A = self.set_zn(self.A | self.read(self._indx()))
def _op78(self, op, pc):  # $11
    self.A = self.set_zn(self.A | self.read(self._indy()))
def _op79(self, op, pc):  # $49
    self.A = self.set_zn(self.A ^ self.read(self._imm()))
def _op80(self, op, pc):  # $45
    self.A = self.set_zn(self.A ^ self.read(self._zp()))
def _op81(self, op, pc):  # $55
    self.A = self.set_zn(self.A ^ self.read(self._zpx()))
def _op82(self, op, pc):  # $4D
    self.A = self.set_zn(self.A ^ self.read(self._abso()))
def _op83(self, op, pc):  # $5D
    self.A = self.set_zn(self.A ^ self.read(self._absx()))
def _op84(self, op, pc):  # $59
    self.A = self.set_zn(self.A ^ self.read(self._absy()))
def _op85(self, op, pc):  # $41
    self.A = self.set_zn(self.A ^ self.read(self._indx()))
def _op86(self, op, pc):  # $51
    self.A = self.set_zn(self.A ^ self.read(self._indy()))
def _op87(self, op, pc):  # $24, $2C
    v = self.read(self._zp() if op == 0x24 else self._abso())
    if (self.A & v) == 0: self.P |= 0x02
    else: self.P &= ~0x02
    self.P = (self.P & ~0xC0) | (v & 0xC0)
def _op88(self, op, pc):  # $69
    self._adc(self.read(self._imm()))
def _op89(self, op, pc):  # $65
    self._adc(self.read(self._zp()))
def _op90(self, op, pc):  # $75
    self._adc(self.read(self._zpx()))
def _op91(self, op, pc):  # $6D
    self._adc(self.read(self._abso()))
def _op92(self, op, pc):  # $7D
    self._adc(self.read(self._absx()))
def _op93(self, op, pc):  # $79
    self._adc(self.read(self._absy()))
def _op94(self, op, pc):  # $61
    self._adc(self.read(self._indx()))
def _op95(self, op, pc):  # $71
    self._adc(self.read(self._indy()))
def _op96(self, op, pc):  # $E9
    self._sbc(self.read(self._imm()))
def _op97(self, op, pc):  # $E5
    self._sbc(self.read(self._zp()))
def _op98(self, op, pc):  # $F5
    self._sbc(self.read(self._zpx()))
def _op99(self, op, pc):  # $ED
    self._sbc(self.read(self._abso()))
def _op100(self, op, pc):  # $FD
    self._sbc(self.read(self._absx()))
def _op101(self, op, pc):  # $F9
    self._sbc(self.read(self._absy()))
def _op102(self, op, pc):  # $E1
    self._sbc(self.read(self._indx()))
def _op103(self, op, pc):  # $F1
    self._sbc(self.read(self._indy()))
def _op104(self, op, pc):  # $C9
    self._cmp(self.A, self.read(self._imm()))
def _op105(self, op, pc):  # $C5
    self._cmp(self.A, self.read(self._zp()))
def _op106(self, op, pc):  # $D5
    self._cmp(self.A, self.read(self._zpx()))
def _op107(self, op, pc):  # $CD
    self._cmp(self.A, self.read(self._abso()))
def _op108(self, op, pc):  # $DD
    self._cmp(self.A, self.read(self._absx()))
def _op109(self, op, pc):  # $D9
    self._cmp(self.A, self.read(self._absy()))
def _op110(self, op, pc):  # $C1
    self._cmp(self.A, self.read(self._indx()))
def _op111(self, op, pc):  # $D1
    self._cmp(self.A, self.read(self._indy()))
def _op112(self, op, pc):  # $E0
    self._cmp(self.X, self.read(self._imm()))
def _op113(self, op, pc):  # $E4
    self._cmp(self.X, self.read(self._zp()))
def _op114(self, op, pc):  # $EC
    self._cmp(self.X, self.read(self._abso()))
def _op115(self, op, pc):  # $C0
    self._cmp(self.Y, self.read(self._imm()))
def _op116(self, op, pc):  # $C4
    self._cmp(self.Y, self.read(self._zp()))
def _op117(self, op, pc):  # $CC
    self._cmp(self.Y, self.read(self._abso()))
def _op118(self, op, pc):  # $E8
    self.X = self.set_zn((self.X + 1) & 0xFF)
def _op119(self, op, pc):  # $CA
    self.X = self.set_zn((self.X - 1) & 0xFF)
def _op120(self, op, pc):  # $C8
    self.Y = self.set_zn((self.Y + 1) & 0xFF)
def _op121(self, op, pc):  # $88
    self.Y = self.set_zn((self.Y - 1) & 0xFF)
def _op122(self, op, pc):  # $E6, $F6, $EE, $FE
    a = self._zp() if op == 0xE6 else (self._zpx() if op == 0xF6 else (self._abso() if op == 0xEE else self._absx()))
    self.write(a, self.set_zn((self.read(a) + 1) & 0xFF))
def _op123(self, op, pc):  # $C6, $D6, $CE, $DE
    a = self._zp() if op == 0xC6 else (self._zpx() if op == 0xD6 else (self._abso() if op == 0xCE else self._absx()))
    self.write(a, self.set_zn((self.read(a) - 1) & 0xFF))
def _op124(self, op, pc):  # $0A
    self.P = (self.P & ~1) | ((self.A >> 7) & 1)
    self.A = self.set_zn((self.A << 1) & 0xFF)
def _op125(self, op, pc):  # $06, $16, $0E, $1E
    a = self._zp() if op == 0x06 else (self._zpx() if op == 0x16 else (self._abso() if op == 0x0E else self._absx()))
    v = self.read(a)
    self.P = (self.P & ~1) | ((v >> 7) & 1)
    self.write(a, self.set_zn((v << 1) & 0xFF))
def _op126(self, op, pc):  # $4A
    self.P = (self.P & ~1) | (self.A & 1)
    self.A = self.set_zn(self.A >> 1)
def _op127(self, op, pc):  # $46, $56, $4E, $5E
    a = self._zp() if op == 0x46 else (self._zpx() if op == 0x56 else (self._abso() if op == 0x4E else self._absx()))
    v = self.read(a)
    self.P = (self.P & ~1) | (v & 1)
    self.write(a, self.set_zn(v >> 1))
def _op128(self, op, pc):  # $2A
    c = self.P & 1
    self.P = (self.P & ~1) | ((self.A >> 7) & 1)
    self.A = self.set_zn(((self.A << 1) & 0xFF) | c)
def _op129(self, op, pc):  # $26, $36, $2E, $3E
    a = self._zp() if op == 0x26 else (self._zpx() if op == 0x36 else (self._abso() if op == 0x2E else self._absx()))
    v = self.read(a); c = self.P & 1
    self.P = (self.P & ~1) | ((v >> 7) & 1)
    self.write(a, self.set_zn(((v << 1) & 0xFF) | c))
def _op130(self, op, pc):  # $6A
    c = (self.P & 1) << 7
    self.P = (self.P & ~1) | (self.A & 1)
    self.A = self.set_zn((self.A >> 1) | c)
def _op131(self, op, pc):  # $66, $76, $6E, $7E
    a = self._zp() if op == 0x66 else (self._zpx() if op == 0x76 else (self._abso() if op == 0x6E else self._absx()))
    v = self.read(a); c = (self.P & 1) << 7
    self.P = (self.P & ~1) | (v & 1)
    self.write(a, self.set_zn((v >> 1) | c))

_OPS = [None] * 256
_OPS[0x00] = _op0
_OPS[0xEA] = _op1
_OPS[0x78] = _op2
_OPS[0x58] = _op3
_OPS[0xD8] = _op4
_OPS[0xF8] = _op5
_OPS[0x18] = _op6
_OPS[0x38] = _op7
_OPS[0xB8] = _op8
_OPS[0xA9] = _op9
_OPS[0xA5] = _op10
_OPS[0xB5] = _op11
_OPS[0xAD] = _op12
_OPS[0xBD] = _op13
_OPS[0xB9] = _op14
_OPS[0xA1] = _op15
_OPS[0xB1] = _op16
_OPS[0xA2] = _op17
_OPS[0xA6] = _op18
_OPS[0xB6] = _op19
_OPS[0xAE] = _op20
_OPS[0xBE] = _op21
_OPS[0xA0] = _op22
_OPS[0xA4] = _op23
_OPS[0xB4] = _op24
_OPS[0xAC] = _op25
_OPS[0xBC] = _op26
_OPS[0x85] = _op27
_OPS[0x95] = _op28
_OPS[0x8D] = _op29
_OPS[0x9D] = _op30
_OPS[0x99] = _op31
_OPS[0x81] = _op32
_OPS[0x91] = _op33
_OPS[0x86] = _op34
_OPS[0x96] = _op35
_OPS[0x8E] = _op36
_OPS[0x84] = _op37
_OPS[0x94] = _op38
_OPS[0x8C] = _op39
_OPS[0xAA] = _op40
_OPS[0x8A] = _op41
_OPS[0xA8] = _op42
_OPS[0x98] = _op43
_OPS[0x9A] = _op44
_OPS[0xBA] = _op45
_OPS[0x48] = _op46
_OPS[0x68] = _op47
_OPS[0x08] = _op48
_OPS[0x28] = _op49
_OPS[0x4C] = _op50
_OPS[0x6C] = _op51
_OPS[0x20] = _op52
_OPS[0x60] = _op53
_OPS[0x40] = _op54
_OPS[0x10] = _op55
_OPS[0x30] = _op56
_OPS[0x50] = _op57
_OPS[0x70] = _op58
_OPS[0x90] = _op59
_OPS[0xB0] = _op60
_OPS[0xD0] = _op61
_OPS[0xF0] = _op62
_OPS[0x29] = _op63
_OPS[0x25] = _op64
_OPS[0x35] = _op65
_OPS[0x2D] = _op66
_OPS[0x3D] = _op67
_OPS[0x39] = _op68
_OPS[0x21] = _op69
_OPS[0x31] = _op70
_OPS[0x09] = _op71
_OPS[0x05] = _op72
_OPS[0x15] = _op73
_OPS[0x0D] = _op74
_OPS[0x1D] = _op75
_OPS[0x19] = _op76
_OPS[0x01] = _op77
_OPS[0x11] = _op78
_OPS[0x49] = _op79
_OPS[0x45] = _op80
_OPS[0x55] = _op81
_OPS[0x4D] = _op82
_OPS[0x5D] = _op83
_OPS[0x59] = _op84
_OPS[0x41] = _op85
_OPS[0x51] = _op86
_OPS[0x24] = _op87
_OPS[0x2C] = _op87
_OPS[0x69] = _op88
_OPS[0x65] = _op89
_OPS[0x75] = _op90
_OPS[0x6D] = _op91
_OPS[0x7D] = _op92
_OPS[0x79] = _op93
_OPS[0x61] = _op94
_OPS[0x71] = _op95
_OPS[0xE9] = _op96
_OPS[0xE5] = _op97
_OPS[0xF5] = _op98
_OPS[0xED] = _op99
_OPS[0xFD] = _op100
_OPS[0xF9] = _op101
_OPS[0xE1] = _op102
_OPS[0xF1] = _op103
_OPS[0xC9] = _op104
_OPS[0xC5] = _op105
_OPS[0xD5] = _op106
_OPS[0xCD] = _op107
_OPS[0xDD] = _op108
_OPS[0xD9] = _op109
_OPS[0xC1] = _op110
_OPS[0xD1] = _op111
_OPS[0xE0] = _op112
_OPS[0xE4] = _op113
_OPS[0xEC] = _op114
_OPS[0xC0] = _op115
_OPS[0xC4] = _op116
_OPS[0xCC] = _op117
_OPS[0xE8] = _op118
_OPS[0xCA] = _op119
_OPS[0xC8] = _op120
_OPS[0x88] = _op121
_OPS[0xE6] = _op122
_OPS[0xF6] = _op122
_OPS[0xEE] = _op122
_OPS[0xFE] = _op122
_OPS[0xC6] = _op123
_OPS[0xD6] = _op123
_OPS[0xCE] = _op123
_OPS[0xDE] = _op123
_OPS[0x0A] = _op124
_OPS[0x06] = _op125
_OPS[0x16] = _op125
_OPS[0x0E] = _op125
_OPS[0x1E] = _op125
_OPS[0x4A] = _op126
_OPS[0x46] = _op127
_OPS[0x56] = _op127
_OPS[0x4E] = _op127
_OPS[0x5E] = _op127
_OPS[0x2A] = _op128
_OPS[0x26] = _op129
_OPS[0x36] = _op129
_OPS[0x2E] = _op129
_OPS[0x3E] = _op129
_OPS[0x6A] = _op130
_OPS[0x66] = _op131
_OPS[0x76] = _op131
_OPS[0x6E] = _op131
_OPS[0x7E] = _op131


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
