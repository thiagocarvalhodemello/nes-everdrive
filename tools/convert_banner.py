#!/usr/bin/env python3
"""
tools/convert_banner.py
======================
Utilitário para converter imagens em banners gráficos de cabeçalho (Header Banners)
para o EverDrive N8 / EDFC no padrão NES/Famicom.

Especificações do Banner NES:
-----------------------------
- Resolução do Banner: 256 x 16 pixels (32 x 2 tiles de 8x8)
- Respiro Inferior: Linha 2 da nametable preenchida com tile 0x1F (preto puro)
- Limite de Tiles Únicos: Máximo de 41 tiles (alocados em 0x0B..0x1E e 0x8B..0x9F)
  (Preserva 100% dos caracteres acentuados PT-BR em 0x01..0x0A e 0x81..0x8A)
- Paleta de Cores: 4 cores por tema (Subpaleta 1 da PPU)
  - Cor 0: Fundo universal (0x0F / Preto)
  - Cor 1: Tom escuro / borda (ex: 0x16 vermelho escuro)
  - Cor 2: Tom médio (ex: 0x27 laranja / chama)
  - Cor 3: Tom claro / destaque (ex: 0x38 amarelo claro / branco)
"""

import os
import sys
import argparse
import struct
import zlib

NES_PALETTE_RGB = [
    (84,84,84), (0,30,116), (8,16,144), (48,0,136), (68,0,100), (92,0,48), (84,4,0), (60,24,0),
    (32,42,0), (8,58,0), (0,64,0), (0,60,0), (0,50,60), (0,0,0), (0,0,0), (0,0,0),
    (152,150,152), (8,76,196), (48,50,236), (92,30,228), (136,20,176), (160,20,100), (152,34,32), (120,60,0),
    (84,90,0), (40,114,0), (8,124,0), (0,118,40), (0,102,120), (0,0,0), (0,0,0), (0,0,0),
    (236,238,236), (76,154,236), (120,124,236), (176,98,236), (228,84,236), (236,88,180), (236,106,100), (212,136,32),
    (160,170,0), (116,196,0), (76,208,32), (56,204,108), (56,180,204), (60,60,60), (0,0,0), (0,0,0),
    (236,238,236), (168,204,236), (188,188,236), (212,178,236), (236,174,236), (236,174,212), (236,180,176), (228,196,144),
    (204,210,120), (180,222,120), (168,226,144), (152,226,180), (160,214,228), (160,162,160), (0,0,0), (0,0,0)
]

BANNER_SLOTS = list(range(0x0B, 0x1F)) + list(range(0x8B, 0xA0))  # 41 slots

THEME_PALETTES = {
    0: ("RETROGAMER POA", (0x0F, 0x27, 0x38, 0x16), (0x0F, 0x16, 0x27, 0x38)),
    1: ("PADRAO",         (0x0F, 0x10, 0x28, 0x00), (0x0F, 0x02, 0x12, 0x30)),
    2: ("SYNTHWAVE",      (0x0F, 0x24, 0x2C, 0x12), (0x0F, 0x14, 0x24, 0x2C)),
    3: ("OUTRUN",         (0x04, 0x27, 0x37, 0x16), (0x0F, 0x16, 0x27, 0x37)),
    4: ("SEGA 16-BIT",    (0x02, 0x21, 0x30, 0x11), (0x0F, 0x12, 0x21, 0x30)),
    5: ("RETROCHIMP",     (0x0F, 0x2A, 0x38, 0x09), (0x0F, 0x1A, 0x2A, 0x38)),
    6: ("MAD DRUGA",      (0x0F, 0x23, 0x30, 0x13), (0x0F, 0x13, 0x23, 0x30)),
    7: ("CYBERPUNK",      (0x02, 0x2C, 0x24, 0x12), (0x0F, 0x12, 0x2C, 0x24)),
    8: ("GAME BOY",       (0x08, 0x19, 0x38, 0x0A), (0x08, 0x0A, 0x19, 0x38)),
}

def decode_png(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Arquivo não é um PNG válido: {path}")
    w, h = struct.unpack(">II", data[16:24])
    ct = data[25]
    idx = 8
    idat = b""
    palette = []
    while idx < len(data):
        l, t = struct.unpack(">I4s", data[idx:idx+8])
        chunk = data[idx+8 : idx+8+l]
        idx += 8 + l + 4
        if t == b"PLTE":
            for i in range(0, len(chunk), 3):
                palette.append((chunk[i], chunk[i+1], chunk[i+2]))
        elif t == b"IDAT":
            idat += chunk

    decomp = zlib.decompress(idat)
    bpp = 3 if ct == 2 else (4 if ct == 6 else 1)
    stride = 1 + w * bpp
    rows = []
    prev_row = bytearray(w * bpp)

    def paeth(a, b, c):
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        if pa <= pb and pa <= pc: return a
        elif pb <= pc: return b
        else: return c

    for y in range(h):
        line = decomp[y*stride:(y+1)*stride]
        ft = line[0]
        row = bytearray(line[1:])
        if ft == 1:
            for x in range(bpp, len(row)): row[x] = (row[x] + row[x - bpp]) & 0xFF
        elif ft == 2:
            for x in range(len(row)): row[x] = (row[x] + prev_row[x]) & 0xFF
        elif ft == 3:
            for x in range(len(row)):
                a = row[x - bpp] if x >= bpp else 0
                b = prev_row[x]
                row[x] = (row[x] + ((a + b) // 2)) & 0xFF
        elif ft == 4:
            for x in range(len(row)):
                a = row[x - bpp] if x >= bpp else 0
                b = prev_row[x]
                c = prev_row[x - bpp] if x >= bpp else 0
                row[x] = (row[x] + paeth(a, b, c)) & 0xFF

        if ct == 2:
            rgb_row = bytes(row)
        elif ct == 6:
            rgb_row = bytearray(w * 3)
            for px in range(w): rgb_row[px*3:px*3+3] = row[px*4:px*4+3]
            rgb_row = bytes(rgb_row)
        elif ct == 3:
            rgb_row = bytearray(w * 3)
            for px in range(w):
                c = palette[row[px]] if row[px] < len(palette) else (0, 0, 0)
                rgb_row[px*3:px*3+3] = bytes(c)
            rgb_row = bytes(rgb_row)
        elif ct == 0:
            rgb_row = bytearray(w * 3)
            for px in range(w): rgb_row[px*3:px*3+3] = bytes([row[px]] * 3)
            rgb_row = bytes(rgb_row)
        else:
            raise ValueError(f"Color type {ct} não suportado.")
        rows.append(rgb_row)
        prev_row = row

    return w, h, rows

def save_png(path, w, h, rgb_rows):
    def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + r for r in rgb_rows)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))

def crop_or_resize_to_256x16(w, h, rows):
    """
    Normaliza a imagem para exatamente 256x16 pixels.
    Se a imagem for um preview do Mega Drive (640x448 ou 320x224), extrai o banner do topo.
    Se a arte tiver mais de 16px de altura (ex: 18..24px como nos temas originais),
    redimensiona proporcionalmente a altura para 16px para preservar 100% dos detalhes
    inferiores (sombras, contornos e linhas de base), sem nenhum corte no desenho!
    """
    if w == 640 and h == 448:
        # Previa VDP 2x: amostragem 1:2 para 320x224, banner nos primeiros 32px
        md_rows = []
        for y in range(0, 32 * 2, 2):
            r = bytearray(320 * 3)
            for x in range(0, 640, 2):
                r[(x//2)*3 : (x//2)*3+3] = rows[y][x*3 : x*3+3]
            md_rows.append(bytes(r))
        w, h, rows = 320, 32, md_rows

    start_x = (w - 256) // 2 if w >= 256 else 0

    # Detecta a altura real do desenho (primeira e última linha com pixels visíveis)
    first_y = 0
    last_y = min(h - 1, 23)
    for y in range(min(h, 24)):
        if any(c > 20 for c in rows[y]):
            first_y = y
            break
    for y in range(min(h - 1, 23), first_y - 1, -1):
        if any(c > 20 for c in rows[y]):
            last_y = y
            break

    art_h = last_y - first_y + 1

    out_rows = []
    if art_h > 16:
        # Redimensionamento vertical proporcional para caber 100% em 16px
        for dy in range(16):
            sy = first_y + int(dy * (art_h - 1) / 15.0 + 0.5)
            r = bytearray(256 * 3)
            src_line = rows[min(h - 1, sy)]
            for x in range(256):
                src_x = start_x + x
                if src_x < w:
                    r[x*3:x*3+3] = src_line[src_x*3:src_x*3+3]
            out_rows.append(bytes(r))
    else:
        # Se cabe em 16px, centraliza verticalmente dentro dos 16px
        pad_top = (16 - art_h) // 2
        for _ in range(pad_top):
            out_rows.append(bytes(256 * 3))
        for y in range(first_y, last_y + 1):
            r = bytearray(256 * 3)
            src_line = rows[y]
            for x in range(256):
                src_x = start_x + x
                if src_x < w:
                    r[x*3:x*3+3] = src_line[src_x*3:src_x*3+3]
            out_rows.append(bytes(r))
        while len(out_rows) < 16:
            out_rows.append(bytes(256 * 3))

    return 256, 16, out_rows

def quantize_pixel(r, g, b, pal_rgb=None):
    if pal_rgb is not None:
        # Escolhe a cor mais próxima euclidiana da paleta do tema
        best_idx = 0
        best_dist = 999999
        for idx, (pr, pg, pb) in enumerate(pal_rgb):
            dist = (r - pr)**2 + (g - pg)**2 + (b - pb)**2
            if dist < best_dist:
                best_dist = dist
                best_idx = idx
        return best_idx
    # Quantização por luminância padrão (0=preto, 1=escuro, 2=médio, 3=claro)
    lum = (r * 299 + g * 587 + b * 114) // 1000
    if lum < 35: return 0
    if lum < 100: return 1
    if lum < 180: return 2
    return 3

def tile_diff(t1, t2):
    return sum(bin(b1 ^ b2).count("1") for b1, b2 in zip(t1, t2))

def convert_image_to_banner(image_path, theme_id=0, custom_pal=None):
    w, h, rows = decode_png(image_path)
    w, h, rows = crop_or_resize_to_256x16(w, h, rows)

    pal1_indices = custom_pal if custom_pal else THEME_PALETTES.get(theme_id, THEME_PALETTES[0])[2]
    pal_rgb = [NES_PALETTE_RGB[c & 0x3F] for c in pal1_indices]

    # Converte os pixels para 64 tiles NES 2bpp (32 colunas x 2 linhas)
    all_grid_tiles = []
    quant_pixels = []
    for ty in range(2):
        row_pixels = []
        for tx in range(32):
            b0 = []
            b1 = []
            for py in range(8):
                y = ty * 8 + py
                line = rows[y]
                p0 = 0
                p1 = 0
                for px in range(8):
                    idx = (tx * 8 + px) * 3
                    c = quantize_pixel(line[idx], line[idx+1], line[idx+2], pal_rgb)
                    p0 = (p0 << 1) | (c & 1)
                    p1 = (p1 << 1) | ((c >> 1) & 1)
                b0.append(p0)
                b1.append(p1)
            all_grid_tiles.append(bytes(b0 + b1))

    # Otimização e deduplicação estrita para <= 41 slots
    threshold = 0
    while True:
        unique_tiles = []
        for tb in all_grid_tiles:
            if all(b == 0 for b in tb): continue
            found = False
            for u in unique_tiles:
                if tile_diff(tb, u) <= threshold:
                    found = True
                    break
            if not found:
                unique_tiles.append(tb)
        if len(unique_tiles) <= len(BANNER_SLOTS):
            break
        threshold += 1

    tile_cache = {}
    tile_bytes_list = []
    for i, tb in enumerate(unique_tiles):
        slot = BANNER_SLOTS[i]
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

    # Adiciona linha 2 de respiro (32 tiles 0x1F)
    nametable.extend([0x1F] * 32)

    return {
        "theme_id": theme_id,
        "pal1": pal1_indices,
        "pal_rgb": pal_rgb,
        "num_tiles": len(unique_tiles),
        "threshold": threshold,
        "tiles": tile_bytes_list,
        "nametable": bytes(nametable),
        "quant_tiles": all_grid_tiles
    }

def generate_preview_png(banner_data, out_path, scale=2):
    # Reconstrói a imagem 256x24 (16px banner + 8px linha de respiro)
    pal_rgb = banner_data["pal_rgb"]
    quant_tiles = banner_data["quant_tiles"]

    h = 24
    w = 256
    screen_rows = [bytearray(w * 3) for _ in range(h)]

    # Linhas 0 e 1: banner
    for ty in range(2):
        for tx in range(32):
            tb = quant_tiles[ty * 32 + tx]
            b0 = tb[:8]
            b1 = tb[8:]
            for py in range(8):
                y = ty * 8 + py
                p0 = b0[py]
                p1 = b1[py]
                for px in range(8):
                    shift = 7 - px
                    c = ((p0 >> shift) & 1) | (((p1 >> shift) & 1) << 1)
                    rgb = pal_rgb[c]
                    x = tx * 8 + px
                    screen_rows[y][x*3:x*3+3] = bytes(rgb)

    # Linha 2: respiro preto (cor 0x0F / (0,0,0))
    for y in range(16, 24):
        for x in range(256):
            screen_rows[y][x*3:x*3+3] = bytes(pal_rgb[0])

    if scale > 1:
        scaled_rows = []
        for y in range(h):
            s_row = bytearray(w * scale * 3)
            for x in range(w):
                pix = screen_rows[y][x*3:x*3+3]
                for sx in range(scale):
                    s_row[(x*scale + sx)*3 : (x*scale + sx)*3+3] = pix
            for _ in range(scale):
                scaled_rows.append(bytes(s_row))
        save_png(out_path, w * scale, h * scale, scaled_rows)
    else:
        save_png(out_path, w, h, screen_rows)
    print(f"  [OK] Imagem de preview salva em: {out_path}")

def print_specs():
    print("""
================================================================================
GUIA DE ESPECIFICACOES PARA CRIAÇÃO DE BANNERS DO EVERDRIVE N8 / EDFC
================================================================================

1. MEDIDAS E RESOLUCAO DA IMAGEM:
   - Formato do Arquivo: PNG (RGB, RGBA ou Indexado de 8-bits)
   - Resolucao Exata: 256 pixels de largura por 16 pixels de altura (256 x 16 px)
   - Grade de Tiles: 32 colunas x 2 linhas de blocos 8x8 pixels (64 tiles no total)
   - Area Segura para TVs de Tubo (CRT Overscan):
     * Linha 0 (Y = 0..7 px): Pode ficar oculta no topo em TVs CRT antigas.
       Recomenda-se usar para decoracoes de topo, ceu, bordas ou metade superior de logos altos.
     * Linha 1 (Y = 8..15 px): Totalmente visivel em qualquer TV. Coloque os textos principais aqui.
     * Linha 2 (Y = 16..23 px): O sistema preenche automaticamente com PRETO PURO (tile 0x1F)
       para criar o respiro/linha vazia antes da lista de jogos (que comeca na Linha 3).

2. LIMITE DE TILES UNICOS:
   - Maximo de 41 tiles diferentes (8x8 px).
   - O script reduz e otimiza automaticamente tiles repetidos ou muito semelhantes.
   - Os slots de 0x0B..0x1E (20 slots) e 0x8B..0x9F (21 slots) sao reservados exclusivamente
     ao banner, garantindo que nenhum caracter acentuado em PT-BR (0x01..0x0A) seja corrompido!

3. PALETA DE CORES (4 CORES POR TEMA):
   O NES suporta 4 cores por bloco de fundo (Paleta 1):
   - Indice 0: Transparente / Preto Fundo Universal (Sempre 0x0F = Preto #000000)
   - Indice 1: Cor escura / Sombra / Borda
   - Indice 2: Cor intermediaria / Corpo do texto
   - Indice 3: Cor clara / Brilho / Destaque

   Tabela de Cores dos Temas Padrao:
   * Tema 0 (RETROGAMER POA): [0x0F Preto, 0x16 Vermelho Escuro, 0x27 Laranja, 0x38 Amarelo/Ouro]
   * Tema 1 (PADRAO):         [0x0F Preto, 0x02 Azul Escuro,     0x12 Azul Medio, 0x30 Branco]
   * Tema 2 (SYNTHWAVE):      [0x0F Preto, 0x14 Roxo Escuro,     0x24 Rosa/Magenta, 0x2C Ciano]
   * Tema 3 (OUTRUN):         [0x0F Preto, 0x16 Vermelho,        0x27 Laranja, 0x37 Amarelo]
   * Tema 4 (SEGA 16-BIT):    [0x0F Preto, 0x12 Azul Sega,       0x21 Ciano Claro, 0x30 Branco]
   * Tema 5 (RETROCHIMP):     [0x0F Preto, 0x1A Verde Escuro,    0x2A Verde Claro, 0x38 Amarelo]
   * Tema 6 (MAD DRUGA):      [0x0F Preto, 0x13 Verde Arcade,    0x23 Verde Fluorescente, 0x30 Branco]
   * Tema 7 (CYBERPUNK):      [0x0F Preto, 0x12 Azul Escuro,     0x2C Ciano Neon, 0x24 Magenta]
   * Tema 8 (GAME BOY):       [0x08 Verde Escuro, 0x0A Verde Medio, 0x19 Verde Claro, 0x38 Amarelo GB]

4. DICA DE EXPORTACAO NO PHOTOSHOP / ASEPRITE / GIMP:
   - Crie uma tela de 256x16 pixels.
   - Use no maximo 3 cores + fundo preto.
   - Salve como PNG simples.
   - Execute:
     python tools/convert_banner.py --image meu_banner.png --theme 0 --preview preview.png
================================================================================
""")

def main():
    parser = argparse.ArgumentParser(description="Conversor de Imagens para Banners do EverDrive N8 / EDFC")
    parser.add_argument("--image", "-i", type=str, help="Caminho do arquivo PNG de entrada")
    parser.add_argument("--theme", "-t", type=int, default=0, help="ID do tema alvo (0 a 8, padrao 0)")
    parser.add_argument("--palette", "-p", type=str, help="Paleta customizada (4 valores hex, ex: 0x0F,0x16,0x27,0x38)")
    parser.add_argument("--preview", type=str, default="banner_preview.png", help="Caminho para salvar o PNG de preview")
    parser.add_argument("--specs", action="store_true", help="Exibe o guia completo de especificacoes tecnicas")
    args = parser.parse_args()

    if args.specs or not args.image:
        print_specs()
        if not args.image:
            return

    custom_pal = None
    if args.palette:
        custom_pal = [int(x.strip(), 16) for x in args.palette.split(",")]
        assert len(custom_pal) == 4, "A paleta deve conter exatamente 4 valores hexadecimais!"

    print(f"Processando imagem: {args.image}...")
    res = convert_image_to_banner(args.image, theme_id=args.theme, custom_pal=custom_pal)
    print(f"  [OK] Imagem convertida para 256x16 com sucesso!")
    print(f"  Tiles unicos necessarios: {res['num_tiles']} / 41 permitidos (Threshold de diff: {res['threshold']})")
    print(f"  Paleta NES utilizada: {[hex(c) for c in res['pal1']]}")

    generate_preview_png(res, args.preview, scale=3)
    print(f"\nConversao concluida com sucesso!")

if __name__ == "__main__":
    main()
