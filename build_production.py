"""Build the production .exe, install it locally and add a desktop shortcut."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = ROOT / "venv" / "Scripts" / "python.exe"
ICON = ROOT / "app.ico"
APP_NAME = "Billing Software"
EXE_NAME = APP_NAME + ".exe"


def run(*args, **kwargs):
    print(">", " ".join(str(a) for a in args))
    subprocess.run([str(a) for a in args], check=True, cwd=ROOT, **kwargs)


def powershell(command):
    return subprocess.run(["powershell", "-NoProfile", "-Command", command],
                          check=True, cwd=ROOT, text=True,
                          capture_output=True).stdout.strip()


def main():
    if not ICON.exists():
        run(PY, ROOT / "make_icon.py")

    run(PY, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
        "--windowed", "--icon", ICON, "--name", APP_NAME, ROOT / "ui.py")

    built = ROOT / "dist" / EXE_NAME
    if not built.exists():
        raise SystemExit(f"Build failed: {built} not found")

    local = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home())
    install_dir = local / "Programs" / "BillingSoftware"
    data_dir = local / "BillingSoftware"
    install_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    installed = install_dir / EXE_NAME
    shutil.copy2(built, installed)

    target_db = data_dir / "billing.db"
    source_db = ROOT / "billing.db"
    if not target_db.exists() and source_db.exists():
        shutil.copy2(source_db, target_db)
        print("copied existing database to", target_db)

    desktop = powershell("[Environment]::GetFolderPath('Desktop')")
    shortcut = Path(desktop) / (APP_NAME + ".lnk")
    script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$sc = $ws.CreateShortcut('{shortcut}'); "
        f"$sc.TargetPath = '{installed}'; "
        f"$sc.WorkingDirectory = '{install_dir}'; "
        f"$sc.IconLocation = '{installed},0'; "
        f"$sc.Description = '{APP_NAME}'; "
        "$sc.Save()"
    )
    powershell(script)

    print("\nProduction build ready:")
    print("  exe:     ", installed)
    print("  database:", target_db)
    print("  shortcut:", shortcut)


if __name__ == "__main__":
    main()
