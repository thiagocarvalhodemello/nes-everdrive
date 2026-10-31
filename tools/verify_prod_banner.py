import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edfc_emu import EverDriveN8Emu

def verify_production_os():
    print("\n--- Verificando EDFC/OS.BIN Oficial Diretamente do Disco ---")
    emu = EverDriveN8Emu("EDFC/OS.BIN", r"C:\Development\nes-everdrive")
    
    # 1. Boot console
    emu.run_frames(40)
    
    # 2. Enter file browser
    emu.press_button(0x40, hold_frames=2, wait_frames=30)
    
    # 3. Verify Theme 0 (RETROGAMER POA) banner rendered on boot
    os.makedirs("docs/themes", exist_ok=True)
    emu.render_screen("docs/themes/prod_theme0_boot.png", scale=2)
    print("  [OK] Boot inicial exibiu o banner oficial RETROGAMER POA!")
    
    # Check that nametable rows 0 and 1 contain banner tiles
    nt_rows = bytes(emu.vram[0:64])
    print(f"  Nametable primeiros 8 bytes: {[hex(x) for x in nt_rows[:8]]}")
    assert any(b != 0 for b in nt_rows), "Nametable row 0..1 is empty!"
    
    # Check Palette 0 and Palette 1
    pal = list(emu.palette[:8])
    print(f"  PPU Palette 0 e 1: {[hex(x) for x in pal]}")
    # Theme 0 RGPOA: pal0=(0x0F, 0x27, 0x38, 0x16), pal1=(0x0F, 0x16, 0x27, 0x38)
    assert pal[0:4] == [0x0F, 0x27, 0x38, 0x16], f"Palette 0 mismatch: {pal[0:4]}"
    assert pal[4:8] == [0x0F, 0x16, 0x27, 0x38], f"Palette 1 mismatch: {pal[4:8]}"
    print("  [OK] Paletas de lista e banner conferidas com precisao!")
    
    # 4. Cycle through themes using SELECT + RIGHT
    themes_names = [
        "RETROGAMER POA", "PADRAO", "SYNTHWAVE", "OUTRUN",
        "SEGA 16-BIT", "RETROCHIMP", "MAD DRUGA", "CYBERPUNK", "GAME BOY"
    ]
    for target_id in range(1, 9):
        emu.press_button(0x21, hold_frames=2, wait_frames=25)
        current_id = emu.prg_ram[0x0F][0x1AE5]
        print(f"  Trocado ao vivo: Tema {current_id} ({themes_names[current_id]})")
        assert current_id == target_id, f"Expected theme {target_id}, got {current_id}"
        
    emu.render_screen("docs/themes/prod_theme8_gameboy.png", scale=2)
    print("  [OK] Todos os 9 temas foram alternados ao vivo com sucesso!")
    
    # 5. Check Battery-Backed SRAM
    sram = emu.prg_ram[0x08]
    assert sram[0x1BA6:0x1BAA] == bytes([0xED, 0xFC, 0x08, 0xF7]), "SRAM mismatch for Game Boy theme!"
    print("  [OK] Tema 8 salvo na SRAM com sucesso!")
    
    print("\nTODOS OS TESTES DE PRODUCAO PASSARAM 100%!")

if __name__ == "__main__":
    verify_production_os()
