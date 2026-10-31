import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
from edfc_emu import EverDriveN8Emu

BTN_A      = 0x80  # Back / Cancel
BTN_B      = 0x40  # Confirm / Open
BTN_SELECT = 0x20  # Main Menu / Toggle
BTN_START  = 0x10
BTN_UP     = 0x08
BTN_DOWN   = 0x04
BTN_LEFT   = 0x02
BTN_RIGHT  = 0x01

emu = EverDriveN8Emu(
    r"C:\Development\nes-everdrive\EDFC\OS.BIN",
    r"C:\Development\nes-everdrive"
)

out_dir = r"C:\Users\ghoti\.gemini\antigravity-cli\brain\de84c112-2a71-437f-a9a6-722bda301fc4\scratch\screens_ptbr"
os.makedirs(out_dir, exist_ok=True)

# 1. First Boot / Settings Reset Error
emu.run_frames(50)
print("=== 1. Error Reset ===")
print(emu.dump_screen_text())
emu.render_screen(os.path.join(out_dir, "01_error_reset.png"))

# 2. File Browser
emu.press_button(BTN_B, hold_frames=2, wait_frames=50)
print("=== 2. File Browser ===")
print(emu.dump_screen_text())
emu.render_screen(os.path.join(out_dir, "02_file_browser.png"))

# 3. Main Menu (SELECT)
emu.press_button(BTN_SELECT, hold_frames=1, wait_frames=20)
print("=== 3. Main Menu ===")
print(emu.dump_screen_text())
emu.render_screen(os.path.join(out_dir, "03_main_menu.png"))

# 4. Item 0: Options (press B)
emu.press_button(BTN_B, hold_frames=1, wait_frames=20)
print("=== 4. Options ===")
print(emu.dump_screen_text())
emu.render_screen(os.path.join(out_dir, "04_options.png"))
# Back to Main Menu
emu.press_button(BTN_A, hold_frames=1, wait_frames=20)

# 5. Item 1: Cheats (DOWN -> B)
emu.press_button(BTN_DOWN, hold_frames=1, wait_frames=15)
emu.press_button(BTN_B, hold_frames=1, wait_frames=25)
print("=== 5a. Cheats ===")
print(emu.dump_screen_text())
emu.render_screen(os.path.join(out_dir, "05a_cheats.png"))
# Toggle cheats
emu.press_button(BTN_SELECT, hold_frames=1, wait_frames=20)
print("=== 5b. Cheats Toggled ===")
print(emu.dump_screen_text())
emu.render_screen(os.path.join(out_dir, "05b_cheats_toggled.png"))
# Back to File Browser (Cheats exits directly to File Browser)
emu.press_button(BTN_A, hold_frames=1, wait_frames=25)

# 6. Item 2: Device Info
emu.press_button(BTN_SELECT, hold_frames=1, wait_frames=20)
emu.press_button(BTN_DOWN, hold_frames=1, wait_frames=15)
emu.press_button(BTN_DOWN, hold_frames=1, wait_frames=15)
emu.press_button(BTN_B, hold_frames=1, wait_frames=25)
print("=== 6. Device Info ===")
print(emu.dump_screen_text())
emu.render_screen(os.path.join(out_dir, "06_device_info.png"))
# Back to Main Menu
emu.press_button(BTN_A, hold_frames=1, wait_frames=20)

# 7. Item 3: Mapper Info
emu.press_button(BTN_DOWN, hold_frames=1, wait_frames=15)
emu.press_button(BTN_B, hold_frames=1, wait_frames=25)
print("=== 7. Mapper Info ===")
print(emu.dump_screen_text())
emu.render_screen(os.path.join(out_dir, "07_mapper_info.png"))
# Back to Main Menu
emu.press_button(BTN_A, hold_frames=1, wait_frames=20)

# 8. Item 4: About
emu.press_button(BTN_DOWN, hold_frames=1, wait_frames=15)
emu.press_button(BTN_B, hold_frames=1, wait_frames=25)
print("=== 8. About ===")
print(emu.dump_screen_text())
emu.render_screen(os.path.join(out_dir, "08_about.png"))
# Back to Main Menu, then back to File Browser
emu.press_button(BTN_A, hold_frames=1, wait_frames=20)
emu.press_button(BTN_A, hold_frames=1, wait_frames=20)

# In File Browser: find items by stepping down
# Helper function to step down until status bar matches filename
def select_file(target_name):
    for _ in range(30):
        lines = [l for l in emu.dump_screen_text().split("\n") if l.startswith("25:")]
        if lines and target_name in lines[0]:
            return True
        emu.press_button(BTN_DOWN, hold_frames=1, wait_frames=15)
    return False

# 9. File Menu TXT (CHEATS.TXT)
if select_file("CHEATS  TXT"):
    emu.press_button(BTN_B, hold_frames=1, wait_frames=20)
    print("=== 9. File Menu TXT ===")
    print(emu.dump_screen_text())
    emu.render_screen(os.path.join(out_dir, "09_file_menu_txt.png"))
    emu.press_button(BTN_A, hold_frames=1, wait_frames=20)

# 10 & 11a. File Menu ROM & Valid Rom Info (MARIO.NES)
if select_file("MARIO   NES"):
    emu.press_button(BTN_B, hold_frames=1, wait_frames=20)
    print("=== 10. File Menu ROM ===")
    print(emu.dump_screen_text())
    emu.render_screen(os.path.join(out_dir, "10_file_menu_rom.png"))
    
    # Down x2 -> Info da ROM
    emu.press_button(BTN_DOWN, hold_frames=1, wait_frames=15)
    emu.press_button(BTN_DOWN, hold_frames=1, wait_frames=15)
    emu.press_button(BTN_B, hold_frames=1, wait_frames=25)
    print("=== 11a. Rom Info Valid ===")
    print(emu.dump_screen_text())
    emu.render_screen(os.path.join(out_dir, "11a_rom_info_valid.png"))
    emu.press_button(BTN_A, hold_frames=1, wait_frames=20)

# 11b. Bad Rom Info (BATMAN-TNES)
if select_file("BATMAN-TNES"):
    emu.press_button(BTN_B, hold_frames=1, wait_frames=20)
    emu.press_button(BTN_DOWN, hold_frames=1, wait_frames=15)
    emu.press_button(BTN_DOWN, hold_frames=1, wait_frames=15)
    emu.press_button(BTN_B, hold_frames=1, wait_frames=25)
    print("=== 11b. Rom Info Bad ===")
    print(emu.dump_screen_text())
    emu.render_screen(os.path.join(out_dir, "11b_rom_info_bad.png"))
    emu.press_button(BTN_A, hold_frames=1, wait_frames=20)

# 12. File Menu SAV (MARIO.SAV)
if select_file("MARIO   SAV"):
    emu.press_button(BTN_B, hold_frames=1, wait_frames=20)
    print("=== 12. File Menu SAV ===")
    print(emu.dump_screen_text())
    emu.render_screen(os.path.join(out_dir, "12_file_menu_sav.png"))
    emu.press_button(BTN_A, hold_frames=1, wait_frames=20)

# 13. File Menu FDS (ZELDA.FDS)
if select_file("ZELDA   FDS"):
    emu.press_button(BTN_B, hold_frames=1, wait_frames=20)
    print("=== 13. File Menu FDS ===")
    print(emu.dump_screen_text())
    emu.render_screen(os.path.join(out_dir, "13_file_menu_fds.png"))
    emu.press_button(BTN_A, hold_frames=1, wait_frames=20)

print("ALL SCREENS CAPTURED SUCCESSFULLY!")
