import os, sys, glob

# 1. Accent glyph definitions (10 used characters in slots 0x01..0x0A)
ACCENT_GLYPHS = {
    0x01: [0x0C, 0x18, 0x00, 0x3C, 0x3E, 0x66, 0x3E, 0x00],  # á
    0x02: [0x32, 0x4C, 0x00, 0x3C, 0x3E, 0x66, 0x3E, 0x00],  # ã
    0x03: [0x0C, 0x18, 0x00, 0x3C, 0x7E, 0x60, 0x3C, 0x00],  # é
    0x04: [0x0C, 0x18, 0x00, 0x38, 0x18, 0x18, 0x3C, 0x00],  # í
    0x05: [0x0C, 0x18, 0x00, 0x3C, 0x66, 0x66, 0x3C, 0x00],  # ó
    0x06: [0x32, 0x4C, 0x00, 0x3C, 0x66, 0x66, 0x3C, 0x00],  # õ
    0x07: [0x0C, 0x18, 0x00, 0x66, 0x66, 0x66, 0x3E, 0x00],  # ú
    0x08: [0x00, 0x3C, 0x60, 0x60, 0x60, 0x3C, 0x0C, 0x18],  # ç
    0x09: [0x0C, 0x18, 0x00, 0x3C, 0x66, 0x7E, 0x66, 0x00],  # Á
    0x0A: [0x32, 0x4C, 0x00, 0x3C, 0x66, 0x7E, 0x66, 0x00],  # Ã
}

# Old to new accent mapping in Bank 15 strings
OLD_TO_NEW = {
    0x01: 0x01,  # á
    0x02: 0x02,  # ã
    0x04: 0x03,  # é
    0x06: 0x04,  # í
    0x07: 0x05,  # ó
    0x08: 0x06,  # õ
    0x0A: 0x07,  # ú
    0x0B: 0x08,  # ç
    0x0C: 0x09,  # Á
    0x0D: 0x0A,  # Ã
}

with open("EDFC-ORIGINAL/OS.BIN", "rb") as f:
    orig_data = f.read()
k60 = bytes(b ^ 0x7B for b in orig_data[0xDB00:0xDC00])

def decrypt_bank15(buf, offset=0xC000, pages=28):
    out = bytearray()
    for p in range(pages):
        for i in range(256):
            out.append(buf[offset + p*256 + i] ^ k60[i] ^ (0x60 + p))
    return out

def encrypt_bank15(plain_buf, pages=28):
    out = bytearray(len(plain_buf))
    for p in range(pages):
        for i in range(256):
            out[p*256 + i] = plain_buf[p*256 + i] ^ k60[i] ^ (0x60 + p)
    return out

def patch_font_and_strings(os_bin_path):
    with open(os_bin_path, "rb") as f:
        data = bytearray(f.read())
    
    # 1. Patch Bank 0 font (0x0000..0x2000)
    for tile_idx, rows in ACCENT_GLYPHS.items():
        # Normal tile: plane 0 = glyph, plane 1 = ~glyph
        t_off = tile_idx * 16
        for r in range(8):
            data[t_off + r] = rows[r]
            data[t_off + 8 + r] = rows[r] ^ 0xFF
        # Highlighted tile: plane 0 = glyph, plane 1 = 0xFF
        h_off = (tile_idx | 0x80) * 16
        for r in range(8):
            data[h_off + r] = rows[r]
            data[h_off + 8 + r] = 0xFF
    
    # Pure black separator tile at 0x1F (all 16 bytes = 0x00)
    data[0x1F * 16 : 0x20 * 16] = bytes(16)
    
    # 2. Patch Bank 15 strings ($F600..$F9D8 -> offset 0x1600..0x19D8)
    dec_b15 = decrypt_bank15(data, 0xC000, 28)
    
    replaced = 0
    for i in range(0x1600, 0x19D8):
        b = dec_b15[i]
        if b in OLD_TO_NEW and b != OLD_TO_NEW[b]:
            dec_b15[i] = OLD_TO_NEW[b]
            replaced += 1
            
    # Re-encrypt Bank 15
    data[0xC000:0xDC00] = encrypt_bank15(dec_b15, 28)
    
    with open(os_bin_path, "wb") as f:
        f.write(data)
    print(f"Patched font and remapped {replaced} accent bytes in {os_bin_path}")

def main():
    targets = ["EDFC/OS.BIN"] + glob.glob("THEMES/*/OS.BIN")
    for t in targets:
        if os.path.exists(t):
            patch_font_and_strings(t)

if __name__ == "__main__":
    main()
