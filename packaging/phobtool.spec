# PyInstaller : pyinstaller packaging/phobtool.spec
# Place au préalable le binaire VCT compilé (et ses DLL sous Windows) dans ./bin/
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs

root = Path(SPECPATH).parent
datas = [
    (str(root / "vct-pc" / "CMakeLists.txt"), "vct-pc"),
    (str(root / "vct-pc" / "cmake"), "vct-pc/cmake"),
    (str(root / "vct-pc" / "compat"), "vct-pc/compat"),
    (str(root / "vct-pc" / "src"), "vct-pc/src"),
    (str(root / "vct-pc" / "tests"), "vct-pc/tests"),
    (str(root / "gts-pc" / "CMakeLists.txt"), "gts-pc"),
    (str(root / "gts-pc" / "cmake"), "gts-pc/cmake"),
    (str(root / "gts-pc" / "compat"), "gts-pc/compat"),
    (str(root / "gts-pc" / "src"), "gts-pc/src"),
    (str(root / "packaging" / "51-gcadapter.rules"), "packaging"),
]
if (root / "bin").is_dir():
    datas.append((str(root / "bin"), "bin"))

a = Analysis(
    [str(root / "run_phobtool.py")],
    pathex=[str(root)],
    binaries=collect_dynamic_libs("libusb_package"),
    datas=datas,
    hiddenimports=["usb.backend.libusb1", "libusb_package"],
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
is_win = os.name == "nt"
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PhobGCCTool",
          console=False, upx=False,
          icon=str(root / "packaging" / "phobtool.ico") if is_win else None,
          version=str(root / "packaging" / "version_info.txt") if is_win else None)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="PhobGCCTool")
