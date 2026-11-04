import os, sys
sys.path.insert(0, 'tools')
from edfc_emu import EverDriveN8Emu

def verify_all():
    print("=== 1. Testando Boot & Tela Principal (Banner + Espaçamento) ===")
    emu = EverDriveN8Emu("EDFC/OS.BIN", r"C:\Development\nes-everdrive")
    emu.run_frames(40)
    emu.press_button(0x40, hold_frames=2, wait_frames=30) # B -> file browser

    # Check nametable rows 0, 1, 2
    row0 = list(emu.vram[0:32])
    row1 = list(emu.vram[32:64])
    row2 = list(emu.vram[64:96])
    row3 = list(emu.vram[96:128])

    print("Row 0 primeiros 8 tiles:", [hex(b) for b in row0[:8]])
    print("Row 1 primeiros 8 tiles:", [hex(b) for b in row1[:8]])
    print("Row 2 (Linha de espaçamento vazia):", [hex(b) for b in row2[:8]])
    print("Row 3 (Primeiro arquivo):", [hex(b) for b in row3[:8]])

    # Verify banner is in rows 0 and 1
    assert any(b != 0 for b in row0), "Row 0 should contain banner tiles"
    assert any(b != 0 for b in row1), "Row 1 should contain banner tiles"
    # Verify row 2 is pure black separator tile 0x1F
    assert all(b == 0x1F for b in row2), f"Row 2 must be pure black separator (0x1F), got: {set(row2)}"
    # Verify row 3 contains first file
    assert row3[1] == 0x3E, "Row 3 must start with cursor '>'"

    os.makedirs("docs/verify", exist_ok=True)
    emu.render_screen("docs/verify/01_file_browser_banner.png", scale=2)
    print("  [OK] Banner e linha de espaçamento vazia abaixo do banner verificados!")

    print("\n=== 2. Testando Menu Principal (Validação de Caracteres) ===")
    emu.press_button(0x20, hold_frames=1, wait_frames=20) # SELECT -> Menu Principal
    emu.render_screen("docs/verify/02_main_menu.png", scale=2)

    # Let's inspect the tiles of 'Opções' and 'Trapaças'
    # Opções is on Row 8, cols 13..18
    # Trapaças is on Row 10, cols 12..19
    r8 = [emu.vram[8*32 + c] for c in range(13, 19)]
    r10 = [emu.vram[10*32 + c] for c in range(12, 20)]

    print("Bytes de 'Opções' no Menu:", [hex(b) for b in r8])
    print("Bytes de 'Trapaças' no Menu:", [hex(b) for b in r10])

    # In our translation:
    # 'ç' is 0x08 (highlighted: 0x88)
    # 'õ' is 0x06 (highlighted: 0x86)
    # 'Opções' selected: O (0xCF), p (0xF0), ç (0x88), õ (0x86), e (0xE5), s (0xF3)
    assert r8[2] == 0x88, f"Expected highlighted 'ç' (0x88), got {hex(r8[2])}"
    assert r8[3] == 0x86, f"Expected highlighted 'õ' (0x86), got {hex(r8[3])}"

    # 'Trapaças' unselected: T (0x54), r (0x72), a (0x61), p (0x70), a (0x61), ç (0x08), a (0x61), s (0x73)
    assert r10[5] == 0x08, f"Expected unselected 'ç' (0x08), got {hex(r10[5])}"

    # Verify that tile 0x08 and tile 0x88 in CHR-RAM are indeed 'ç' glyphs (not banner graphics!)
    ç_normal = list(emu.chr_ram[0x08 * 16 : 0x09 * 16])
    ç_high = list(emu.chr_ram[0x88 * 16 : 0x89 * 16])
    print("Glyph de 'ç' (0x08) plane 0:", [hex(b) for b in ç_normal[:8]])
    print("Glyph de 'ç' destacado (0x88) plane 1:", [hex(b) for b in ç_high[8:]])

    # In translate_os_ptbr, ç rows are: [0x00, 0x3C, 0x60, 0x60, 0x60, 0x3C, 0x0C, 0x18]
    assert ç_normal[:8] == [0x00, 0x3C, 0x60, 0x60, 0x60, 0x3C, 0x0C, 0x18], "Corrupted 'ç' glyph!"
    assert all(b == 0xFF for b in ç_high[8:]), "Highlighted 'ç' plane 1 corrupted!"
    print("  [OK] Caracteres 'ç' e 'õ' em 'Opções' e 'Trapaças' 100% corretos!")

    print("\n=== 3. Testando Alternância de Temas ao Vivo (SELECT + DIREITA) ===")
    for tid in range(1, 9):
        emu.press_button(0x80, hold_frames=1, wait_frames=15) # A -> dismiss menu
        emu.press_button(0x21, hold_frames=2, wait_frames=25) # SELECT + RIGHT -> next theme
        current_id = emu.prg_ram[0x0F][0x1AE5]
        print(f"  Tema {current_id} carregado ao vivo.")
        # Verify row 2 is still pure black separator line!
        r2 = [emu.vram[64 + c] for c in range(32)]
        assert all(b == 0x1F for b in r2), f"Row 2 separator lost in theme {current_id}!"
        # Verify accented characters in CHR-RAM are still intact!
        ç_chk = list(emu.chr_ram[0x08 * 16 : 0x08 * 16 + 8])
        assert ç_chk == [0x00, 0x3C, 0x60, 0x60, 0x60, 0x3C, 0x0C, 0x18], f"Accents corrupted in theme {current_id}!"

    print("  [OK] Todos os temas mantêm a linha de espaçamento e os caracteres acentuados intactos!")
    print("\nTODAS AS VERIFICACOES PASSARAM COM 100% DE SUCESSO!")

if __name__ == "__main__":
    verify_all()
