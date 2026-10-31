#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EverDrive N8 (EDFC) - Seletor e Personalizador de Temas / Paletas de Cores
Permite trocar a paleta de cores do sistema operacional do flashcart EverDrive N8.
Compatível com hardware Clone (v1.16 criptografado) e Original Krikzz (v1.26).
"""

import os
import sys
import argparse
import shutil
import tempfile

# Definições das 16 cores (PPU Palettes 0..3) para cada tema
# Estrutura dos 16 bytes:
# [0]: Fundo geral (Backdrop)
# [1]: Texto normal e bordas
# [2]: Não utilizado (mesmo que fundo)
# [3]: Texto destacado / selecionado
# [4..11]: Paletas 1 e 2 (fundo)
# [12]: Fundo paleta 3
# [13]: Acento / cabeçalho (normalmente branco ou cor clara)
# [14]: Sombra / texto secundário
# [15]: Destaque secundário
THEMES = {
    "classico": {
        "name": "Clássico EverDrive (Padrão)",
        "desc": "Fundo preto, texto cinza e destaque dourado/amarelo original.",
        "palette": bytes([0x0F, 0x10, 0x0F, 0x28, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x30, 0x00, 0x28])
    },
    "matrix": {
        "name": "Matrix / Terminal Hacker",
        "desc": "Fundo preto fosco com texto verde fosforescente e destaque lima neon.",
        "palette": bytes([0x0F, 0x2A, 0x0F, 0x39, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x30, 0x09, 0x39])
    },
    "cyberpunk": {
        "name": "Cyberpunk 2077 (Neon)",
        "desc": "Fundo azul noturno profundo, texto ciano neon e destaque magenta vibrante.",
        "palette": bytes([0x02, 0x2C, 0x02, 0x24, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02, 0x30, 0x12, 0x24])
    },
    "gameboy": {
        "name": "Game Boy DMG Retrô",
        "desc": "Verde musgo clássico estilo tela LCD do Game Boy original de 1989.",
        "palette": bytes([0x08, 0x19, 0x08, 0x38, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x30, 0x0A, 0x38])
    },
    "ambar": {
        "name": "Âmbar Retrô CRT",
        "desc": "Estilo monitores fósforo âmbar dos computadores dos anos 80.",
        "palette": bytes([0x0F, 0x17, 0x0F, 0x27, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x38, 0x07, 0x27])
    },
    "dark_oled": {
        "name": "Midnight Dark / OLED",
        "desc": "Preto absoluto com texto cinza cristalino e destaque azul celeste elétrico.",
        "palette": bytes([0x0F, 0x20, 0x0F, 0x21, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x31, 0x00, 0x21])
    },
    "crimson": {
        "name": "Crimson Blood / Famicom",
        "desc": "Fundo escuro com texto vermelho rubi e destaque coral brilhante.",
        "palette": bytes([0x0F, 0x16, 0x0F, 0x26, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0x30, 0x06, 0x26])
    },
    "ocean": {
        "name": "Deep Ocean / Azul Safira",
        "desc": "Fundo azul marinho profundo, texto azul celeste e destaque ciano cristalino.",
        "palette": bytes([0x01, 0x21, 0x01, 0x3C, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x30, 0x11, 0x3C])
    },
    "sunset": {
        "name": "Retrô Synthwave Sunset",
        "desc": "Fundo púrpura crepúsculo, texto amarelo suave e destaque laranja pôr do sol.",
        "palette": bytes([0x04, 0x37, 0x04, 0x28, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x30, 0x14, 0x28])
    }
}

# Chave XOR da rotina de descriptografia em hardware da BIOS para o offset da paleta
V116_PALETTE_OFFSET = 0x627C
V116_XOR_KEY = bytes([0x0A, 0x3C, 0x70, 0x37, 0x79, 0xE9, 0x3D, 0x67, 0x1A, 0x8D, 0x81, 0x3D, 0xE5, 0xC4, 0xB7, 0x5E])

V126_PALETTE_OFFSET = 0x625F
TEST_NES_PALETTE_OFFSET = 0x026F

def detect_file_type(data):
    """Identifica se o arquivo é v1.16 (clone), v1.26 (original) ou .nes (test ROM)."""
    if data.startswith(b"NES\x1a"):
        return "nes_test"
    if len(data) == 57344:
        # Testa se é v1.26 (paleta em claro no offset 0x625F)
        if data[0x625F] == 0x0F and data[0x6260] in [0x10, 0x2A, 0x2C, 0x19, 0x17, 0x20, 0x16, 0x21, 0x37]:
            return "v126_original"
        # Testa v1.16 descriptografando com a chave
        dec = bytes(b ^ k for b, k in zip(data[0x627C:0x627C+4], V116_XOR_KEY[:4]))
        if dec[0] == 0x0F:
            return "v116_clone"
    return "unknown"

def patch_palette(file_path, palette_bytes, backup=True):
    """Aplica a paleta de cores no arquivo especificado."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")
    
    with open(file_path, "rb") as f:
        data = bytearray(f.read())
    
    ftype = detect_file_type(data)
    
    if backup:
        bak_path = file_path + ".bak"
        if not os.path.exists(bak_path):
            with open(bak_path, "wb") as f:
                f.write(data)
    
    if ftype == "v116_clone":
        enc_palette = bytes(p ^ k for p, k in zip(palette_bytes, V116_XOR_KEY))
        data[V116_PALETTE_OFFSET:V116_PALETTE_OFFSET+16] = enc_palette
        msg = "EverDrive N8 v1.16 Clone Hardware (Criptografia de BIOS aplicada com sucesso)"
    elif ftype == "v126_original":
        data[V126_PALETTE_OFFSET:V126_PALETTE_OFFSET+16] = palette_bytes
        msg = "EverDrive N8 v1.26 Hardware Original Krikzz (Gravado com sucesso)"
    elif ftype == "nes_test":
        data[TEST_NES_PALETTE_OFFSET:TEST_NES_PALETTE_OFFSET+16] = palette_bytes
        msg = "ROM de Teste Independente .NES (Gravado com sucesso)"
    else:
        # Fallback genérico: busca pelo padrão de 16 bytes
        pattern = bytes([0x0F, 0x10, 0x0F, 0x28])
        idx = data.find(pattern)
        if idx != -1:
            data[idx:idx+16] = palette_bytes
            msg = f"Arquivo genérico (Padrão localizado no offset 0x{idx:04X})"
        else:
            raise ValueError(f"Não foi possível identificar o formato do arquivo: {file_path}")
    
    with open(file_path, "wb") as f:
        f.write(data)
    
    return msg

def generate_preview(theme_key, out_png):
    """Gera um screenshot de demonstração usando o emulador interno edfc_emu."""
    from tools.edfc_emu import EverDriveN8Emu
    
    pal = THEMES[theme_key]["palette"]
    base_bin = "EDFC/OS.BIN"
    if not os.path.exists(base_bin):
        base_bin = "EDFC/OS.BIN.orig"
    
    with open(base_bin, "rb") as f:
        raw = bytearray(f.read())
    
    ftype = detect_file_type(raw)
    if ftype == "v116_clone":
        raw[V116_PALETTE_OFFSET:V116_PALETTE_OFFSET+16] = bytes(p ^ k for p, k in zip(pal, V116_XOR_KEY))
    elif ftype == "v126_original":
        raw[V126_PALETTE_OFFSET:V126_PALETTE_OFFSET+16] = pal
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".BIN") as tmp:
        tmp.write(raw)
        tmp_name = tmp.name
    
    try:
        emu = EverDriveN8Emu(tmp_name, ".")
        emu.run_frames(25)
        # Botoes para ir para a lista de arquivos
        emu.run_frames(4, joy=0x02) # B
        emu.run_frames(10, joy=0)
        os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
        emu.render_screen(out_png)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)

def make_config_dat(theme_id, palette_bytes):
    """Gera o arquivo container de 512 bytes CONFIG.DAT com as configuracoes do tema."""
    buf = bytearray(512)
    buf[0:4] = b"EDFC"
    buf[4] = 0x01
    buf[5] = theme_id & 0xFF
    buf[6] = (theme_id ^ 0xFF) & 0xFF
    buf[0x10:0x20] = palette_bytes[:16]
    msg = b"EverDrive N8 Theme Configuration (EDFC/CONFIG.DAT)"
    buf[0x20:0x20+len(msg)] = msg
    return bytes(buf)

def export_all_theme_folders(out_dir="THEMES"):
    """Exporta versões prontas do OS.BIN para cada tema em pastas organizadas."""
    os.makedirs(out_dir, exist_ok=True)
    base_v116 = "EDFC/OS.BIN"
    
    with open(base_v116, "rb") as f:
        base_data = bytearray(f.read())
    
    for theme_idx, (key, info) in enumerate(THEMES.items()):
        theme_dir = os.path.join(out_dir, key.upper())
        os.makedirs(theme_dir, exist_ok=True)
        
        # Gera o OS.BIN com o tema
        themed_os = bytearray(base_data)
        enc_palette = bytes(p ^ k for p, k in zip(info["palette"], V116_XOR_KEY))
        themed_os[V116_PALETTE_OFFSET:V116_PALETTE_OFFSET+16] = enc_palette
        
        dest_bin = os.path.join(theme_dir, "OS.BIN")
        with open(dest_bin, "wb") as f:
            f.write(themed_os)
            
        # Gera o CONFIG.DAT do tema
        dest_cfg = os.path.join(theme_dir, "CONFIG.DAT")
        with open(dest_cfg, "wb") as f:
            f.write(make_config_dat(theme_idx, info["palette"]))

        # Copia imagem de preview para a pasta do tema
        preview_src = f"docs/themes/{key}.png"
        if os.path.exists(preview_src):
            shutil.copy(preview_src, os.path.join(theme_dir, "preview.png"))
                
        print(f"Exportado tema '{info['name']}' -> {theme_dir} (OS.BIN + CONFIG.DAT + preview.png)")

def interactive_menu():
    """Menu interativo no terminal para seleção de temas."""
    print("=" * 65)
    print("  🎨 EverDrive N8 (EDFC) - Seletor de Temas e Paletas")
    print("=" * 65)
    keys = list(THEMES.keys())
    for i, k in enumerate(keys, 1):
        info = THEMES[k]
        pal_hex = " ".join(f"{b:02X}" for b in info["palette"][:4])
        print(f"  [{i}] {info['name']}")
        print(f"      Paleta: {pal_hex} | {info['desc']}")
    print(f"  [E] Exportar todas as pastas de temas (para THEMES/)")
    print(f"  [P] Gerar imagens de pré-visualização (PNG) de todos os temas")
    print(f"  [0] Sair")
    print("-" * 65)
    
    choice = input("Digite o número do tema desejado ou opção: ").strip()
    if choice in ["0", "q", "quit", "exit"]:
        print("Operação cancelada.")
        return
    
    if choice.upper() == "E":
        export_all_theme_folders()
        print("\nTodas as pastas de temas foram geradas com sucesso!")
        return
        
    if choice.upper() == "P":
        print("Gerando screenshots de pré-visualização...")
        for k in keys:
            out_png = f"docs/themes/{k}.png"
            generate_preview(k, out_png)
            print(f"  -> {out_png}")
        print("\nTodas as pré-visualizações foram geradas com sucesso!")
        return
    
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(keys):
            selected_key = keys[idx]
        else:
            print("Opção inválida.")
            return
    except ValueError:
        print("Entrada inválida.")
        return
    
    theme_info = THEMES[selected_key]
    print(f"\nAplicando tema: {theme_info['name']}...")
    
    # Aplica no EDFC/OS.BIN
    if os.path.exists("EDFC/OS.BIN"):
        res = patch_palette("EDFC/OS.BIN", theme_info["palette"])
        print(f"  ✓ EDFC/OS.BIN: {res}")
    
    # Aplica na ROM de teste se existir
    if os.path.exists("EDFC/OS_PTBR_TEST.nes"):
        res_nes = patch_palette("EDFC/OS_PTBR_TEST.nes", theme_info["palette"])
        print(f"  ✓ EDFC/OS_PTBR_TEST.nes: {res_nes}")
    
    # Gera screenshot atualizado
    preview_path = f"docs/themes/current_theme.png"
    try:
        generate_preview(selected_key, preview_path)
        print(f"  ✓ Screenshot de pré-visualização salvo em: {preview_path}")
    except Exception as e:
        print(f"  (Pré-visualização não gerada: {e})")
        
    print(f"\n✨ Tema '{theme_info['name']}' instalado e ativado com sucesso!")

def main():
    parser = argparse.ArgumentParser(description="Seletor e Personalizador de Temas do EverDrive N8")
    parser.add_argument("--theme", choices=list(THEMES.keys()), help="Aplica o tema especificado diretamente")
    parser.add_argument("--file", default="EDFC/OS.BIN", help="Caminho do arquivo OS.BIN ou .NES a modificar")
    parser.add_argument("--list", action="store_true", help="Lista todos os temas disponíveis")
    parser.add_argument("--preview", choices=list(THEMES.keys()), help="Gera preview PNG do tema")
    parser.add_argument("--generate-all-previews", action="store_true", help="Gera previews de todos os temas")
    parser.add_argument("--export-all", action="store_true", help="Exporta todas as pastas de temas prontas")
    parser.add_argument("--custom", help="Paleta personalizada com 16 bytes em hex (ex: 0F,2A,0F,39,...)")
    
    args = parser.parse_args()
    
    if args.list:
        print("Temas disponíveis:")
        for k, v in THEMES.items():
            print(f"  - {k:12s}: {v['name']} ({v['desc']})")
        return
        
    if args.generate_all_previews:
        print("Gerando previews de todos os temas...")
        for k in THEMES:
            out_png = f"docs/themes/{k}.png"
            generate_preview(k, out_png)
            print(f"  -> {out_png}")
        return
        
    if args.preview:
        out_png = f"docs/themes/{args.preview}.png"
        generate_preview(args.preview, out_png)
        print(f"Preview gerado: {out_png}")
        return
        
    if args.export_all:
        export_all_theme_folders()
        return
        
    if args.custom:
        bytes_list = [int(x.strip(), 16) for x in args.custom.replace(" ", ",").split(",") if x.strip()]
        if len(bytes_list) < 16:
            # Completa com zeros/fundo
            bytes_list += [bytes_list[0]] * (16 - len(bytes_list))
        pal = bytes(bytes_list[:16])
        res = patch_palette(args.file, pal)
        print(f"Paleta customizada aplicada em {args.file}: {res}")
        return
        
    if args.theme:
        pal = THEMES[args.theme]["palette"]
        res = patch_palette(args.file, pal)
        print(f"Tema '{THEMES[args.theme]['name']}' aplicado em {args.file}: {res}")
        theme_idx = list(THEMES.keys()).index(args.theme)
        cfg_bytes = make_config_dat(theme_idx, pal)
        with open("EDFC/CONFIG.DAT", "wb") as f:
            f.write(cfg_bytes)
        with open("CONFIG.DAT", "wb") as f:
            f.write(cfg_bytes)
        print("Arquivo container de configuracao gravado: EDFC/CONFIG.DAT e CONFIG.DAT")
        if os.path.exists("EDFC/OS_PTBR_TEST.nes") and args.file == "EDFC/OS.BIN":
            patch_palette("EDFC/OS_PTBR_TEST.nes", pal)
            print(f"Tema também sincronizado em EDFC/OS_PTBR_TEST.nes")
        return
        
    interactive_menu()

if __name__ == "__main__":
    main()
