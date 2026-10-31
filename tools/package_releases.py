import os
import zipfile

def package_all():
    os.makedirs("releases", exist_ok=True)

    # 1. EDFC-PTBR-v1.16-CloneHardware.zip
    print("Packaging EDFC-PTBR-v1.16-CloneHardware.zip...")
    clone_zip = "releases/EDFC-PTBR-v1.16-CloneHardware.zip"
    ignored_edfc_files = {
        "OS.BIN.orig", "OS.BIN.bak", "OS_PTBR_TEST.nes", 
        "OS_V116_ORIGINAL_PTBR.BIN", "OS_V126_PATCHED.BIN"
    }
    with zipfile.ZipFile(clone_zip, "w", zipfile.ZIP_DEFLATED) as z:
        # Root TEMAS.NES
        if os.path.exists("TEMAS.NES"):
            z.write("TEMAS.NES", "TEMAS.NES")
        
        # Files in EDFC/
        for root, dirs, files in os.walk("EDFC"):
            for file in sorted(files):
                if file.endswith((".py", ".tmp", ".bak")) or file in ignored_edfc_files:
                    continue
                full_path = os.path.join(root, file)
                arcname = os.path.relpath(full_path, ".")
                z.write(full_path, arcname)

    # 2. EDFC-THEMES-AllVariants.zip
    print("Packaging EDFC-THEMES-AllVariants.zip...")
    themes_zip = "releases/EDFC-THEMES-AllVariants.zip"
    with zipfile.ZipFile(themes_zip, "w", zipfile.ZIP_DEFLATED) as z:
        if os.path.exists("TEMAS.NES"):
            z.write("TEMAS.NES", "TEMAS.NES")
        for root, dirs, files in os.walk("THEMES"):
            for file in files:
                full_path = os.path.join(root, file)
                arcname = os.path.relpath(full_path, ".")
                z.write(full_path, arcname)

    # 3. EDFC-PTBR-Standalone-TestROM.zip
    print("Packaging EDFC-PTBR-Standalone-TestROM.zip...")
    test_zip = "releases/EDFC-PTBR-Standalone-TestROM.zip"
    with zipfile.ZipFile(test_zip, "w", zipfile.ZIP_DEFLATED) as z:
        if os.path.exists("EDFC/OS_PTBR_TEST.nes"):
            z.write("EDFC/OS_PTBR_TEST.nes", "OS_PTBR_TEST.nes")
        if os.path.exists("TEMAS.NES"):
            z.write("TEMAS.NES", "TEMAS.NES")

    print("All release archives packaged successfully!")

if __name__ == "__main__":
    package_all()
