"""Load optional app-local NVIDIA DLLs without changing system settings."""
import ctypes
import os
from pathlib import Path
import sys

_dll_handles = []


def cuda_available() -> bool:
    if os.environ.get("GAMETRANSLATOR_DEVICE") == "cpu":
        return False
    if sys.platform != "win32":
        return False
    root = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    folders = [root / "runtime" / "nvidia" / package / "bin" for package in ("cublas", "cudnn")]
    for folder in folders:
        if folder.is_dir():
            _dll_handles.append(os.add_dll_directory(str(folder)))
            if str(folder) not in os.environ.get("PATH", "").split(os.pathsep):
                os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")
    try:
        ctypes.WinDLL("cublas64_12.dll")
        ctypes.WinDLL("cudnn64_9.dll")
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except (OSError, RuntimeError):
        return False
