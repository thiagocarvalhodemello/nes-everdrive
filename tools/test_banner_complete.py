import os, sys, struct, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def decode_rgb_png(path):
    """
    Decodes standard PNG files (RGB, RGBA, Indexed) supporting all 5 PNG filters
    (0=None, 1=Sub, 2=Up, 3=Average, 4=Paeth) without any external libraries.
    """
    with open(path, "rb") as f:
        data = f.read()
    
    w, h = struct.unpack(">II", data[16:24])
    ct = data[25]  # 2 = RGB, 6 = RGBA, 3 = Indexed, 0 = Grayscale
    
    idx = 8
    idat = b""
    palette = []
    
    while idx < len(data):
        length, chunk_type = struct.unpack(">I4s", data[idx:idx+8])
        chunk_data = data[idx+8 : idx+8+length]
        idx += 8 + length + 4
        
        if chunk_type == b"PLTE":
            for i in range(0, len(chunk_data), 3):
                palette.append((chunk_data[i], chunk_data[i+1], chunk_data[i+2]))
        elif chunk_type == b"IDAT":
            idat += chunk_data
            
    decomp = zlib.decompress(idat)
    
    if ct == 2:      # RGB
        bpp = 3
    elif ct == 6:    # RGBA
        bpp = 4
    elif ct == 3:    # Indexed (1 byte per pixel)
        bpp = 1
    elif ct == 0:    # Grayscale
        bpp = 1
    else:
        raise ValueError(f"Unsupported PNG color type {ct} in {path}")
        
    stride = 1 + w * bpp
    rows = []
    prev_row = bytearray(w * bpp)
    
    def paeth_predictor(a, b, c):
        p = a + b - c
        pa = abs(p - a)
        pb = abs(p - b)
        pc = abs(p - c)
        if pa <= pb and pa <= pc:
            return a
        elif pb <= pc:
            return b
        else:
            return c
            
    for y in range(h):
        line = decomp[y * stride : (y + 1) * stride]
        filter_type = line[0]
        row = bytearray(line[1:])
        
        if filter_type == 1:  # Sub
            for x in range(bpp, len(row)):
                row[x] = (row[x] + row[x - bpp]) & 0xFF
        elif filter_type == 2:  # Up
            for x in range(len(row)):
                row[x] = (row[x] + prev_row[x]) & 0xFF
        elif filter_type == 3:  # Average
            for x in range(len(row)):
                a = row[x - bpp] if x >= bpp else 0
                b = prev_row[x]
                row[x] = (row[x] + ((a + b) // 2)) & 0xFF
        elif filter_type == 4:  # Paeth
            for x in range(len(row)):
                a = row[x - bpp] if x >= bpp else 0
                b = prev_row[x]
                c = prev_row[x - bpp] if x >= bpp else 0
                row[x] = (row[x] + paeth_predictor(a, b, c)) & 0xFF
                
        # Convert to 24-bit RGB rows
        if ct == 2:
            rgb_row = bytes(row)
        elif ct == 6:
            rgb_row = bytearray(w * 3)
            for px in range(w):
                rgb_row[px*3 : px*3+3] = row[px*4 : px*4+3]
            rgb_row = bytes(rgb_row)
        elif ct == 3:
            rgb_row = bytearray(w * 3)
            for px in range(w):
                pal_idx = row[px]
                c = palette[pal_idx] if pal_idx < len(palette) else (0, 0, 0)
                rgb_row[px*3 : px*3+3] = bytes(c)
            rgb_row = bytes(rgb_row)
        elif ct == 0:
            rgb_row = bytearray(w * 3)
            for px in range(w):
                val = row[px]
                rgb_row[px*3 : px*3+3] = bytes([val, val, val])
            rgb_row = bytes(rgb_row)
            
        rows.append(rgb_row)
        prev_row = row
        
    return w, h, rows

def quant(r, g, b):
    lum = (r * 299 + g * 587 + b * 114) // 1000
    if lum < 35: return 0
    if lum < 100: return 1
    if lum < 180: return 2
    return 3

def tile_diff(t1, t2):
    return sum(bin(b1 ^ b2).count('1') for b1, b2 in zip(t1, t2))

# Reserved slots:
# 0x00: space
# 0x01..0x0A (1..10): Normal Portuguese accented characters (á, ã, é, í, ó, õ, ú, ç, Á, Ã)
# 0x1F (31): Pure black separator line tile
# 0x80 (128): Inverted space
# 0x81..0x8A (129..138): Highlighted Portuguese accented characters
#
# Available for banner:
# Low range: 0x0B..0x1E (11..30) = 20 slots
# High range: 0x8B..0x9F (139..159) = 21 slots
# Total available banner slots: 41 slots
SLOTS = list(range(0x0B, 0x1F)) + list(range(0x8B, 0xA0))

THEMES_DEF = [
    (0, 'RETROGAMER POA', 'rgpoa_banner.png', (15, 39, 56, 22), (15, 22, 39, 56)),
    (1, 'PADRAO', 'padrao_banner.png', (15, 16, 40, 0), (15, 2, 18, 48)),
    (2, 'SYNTHWAVE', 'synthwave_banner.png', (15, 36, 44, 18), (15, 20, 36, 44)),
    (3, 'OUTRUN', 'outrun_banner.png', (4, 39, 55, 22), (15, 22, 39, 55)),
    (4, 'SEGA 16-BIT', 'sega16_banner.png', (2, 33, 48, 17), (15, 18, 33, 48)),
    (5, 'RETROCHIMP', 'retrochimp_banner.png', (15, 42, 56, 9), (15, 26, 42, 56)),
    (6, 'MAD DRUGA', 'maddrugamers_banner.png', (15, 35, 48, 19), (15, 19, 35, 48)),
    (7, 'CYBERPUNK', 'synthwave_banner.png', (2, 44, 36, 18), (15, 18, 44, 36)),
    (8, 'GAME BOY', 'rgpoa_banner.png', (8, 25, 56, 10), (8, 10, 25, 56)),
]

def build_banner_packages():
    theme_packages = []
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ref_dir = os.path.join(base_dir, "docs", "themes", "ref_md")

    for tid, name, png_name, pal0, pal1 in THEMES_DEF:
        path = os.path.join(ref_dir, png_name)
        w, h, rows = decode_rgb_png(path)
        
        # Center horizontally to 256 pixels (32 tiles * 8px)
        if w >= 256:
            start_x = (w - 256) // 2
        else:
            start_x = 0

        # Scale vertical artwork (y=0..19, 20px) proportionally into 16px (dy=0..15)
        # so that the entire banner (top border, letters, shadows, and bottom baseline)
        # is 100% complete and fully visible, with ZERO pixels cut off at the bottom!
        scaled_rows = []
        for dy in range(16):
            sy = min(h - 1, int(dy * 19.0 / 15.0 + 0.5))
            r = bytearray(256 * 3)
            src_line = rows[sy]
            for x in range(256):
                src_x = start_x + x
                if src_x < w:
                    r[x*3 : x*3+3] = src_line[src_x*3 : src_x*3+3]
            scaled_rows.append(bytes(r))

        all_grid_tiles = []
        for ty in range(2):
            for tx in range(32):
                b0 = []
                b1 = []
                for py in range(8):
                    y = ty * 8 + py
                    line = scaled_rows[y]
                    p0 = 0
                    p1 = 0
                    for px in range(8):
                        idx = (tx * 8 + px) * 3
                        c = quant(line[idx], line[idx+1], line[idx+2])
                        p0 = (p0 << 1) | (c & 1)
                        p1 = (p1 << 1) | ((c >> 1) & 1)
                    b0.append(p0)
                    b1.append(p1)
                all_grid_tiles.append(bytes(b0 + b1))

        # Optimize tiles with smallest diff threshold to strictly fit within len(SLOTS) (41 slots)
        threshold = 0
        while True:
            unique_tiles = []
            for tb in all_grid_tiles:
                if all(b == 0 for b in tb):
                    continue
                found = False
                for u in unique_tiles:
                    if tile_diff(tb, u) <= threshold:
                        found = True
                        break
                if not found:
                    unique_tiles.append(tb)
            if len(unique_tiles) <= len(SLOTS):
                break
            threshold += 1

        tile_cache = {}
        tile_bytes_list = [(0x1F, bytes(16))]  # Slot 0x1F is pure black separator line
        for i, tb in enumerate(unique_tiles):
            slot = SLOTS[i]
            tile_cache[tb] = slot
            tile_bytes_list.append((slot, tb))

        nametable = []
        for tb in all_grid_tiles:
            if all(b == 0 for b in tb):
                nametable.append(0)
            else:
                matched_slot = None
                for u in unique_tiles:
                    if tile_diff(tb, u) <= threshold:
                        matched_slot = tile_cache[u]
                        break
                nametable.append(matched_slot)

        # Row 2 (32 tiles): Empty line of spacing below banner (pure black tile 0x1F)
        nametable.extend([0x1F] * 32)

        theme_packages.append({
            'id': tid,
            'name': name,
            'pal0': pal0,
            'pal1': pal1,
            'nametable': bytes(nametable),
            'tiles': tile_bytes_list
        })

    return theme_packages

if __name__ == "__main__":
    pkgs = build_banner_packages()
    for p in pkgs:
        print(f"Theme {p['id']} ({p['name']}): {len(p['tiles'])} tiles (including 0x1F), slots: min={min(s for s, _ in p['tiles'])} max={max(s for s, _ in p['tiles'])}")
