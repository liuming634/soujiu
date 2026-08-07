import os
import subprocess
import sys
from setuptools import setup, Extension
import pybind11


def find_include_dirs(hint_dirs, header_subdir, header_name):
    for d in hint_dirs:
        candidate = os.path.join(d, header_subdir, header_name)
        if os.path.isfile(candidate):
            return [os.path.join(d, header_subdir)]
        candidate = os.path.join(d, header_name)
        if os.path.isfile(candidate):
            return [d]
        if not os.path.isdir(d):
            continue
        try:
            for entry in os.listdir(d):
                entry_path = os.path.join(d, entry)
                if not os.path.isdir(entry_path):
                    continue
                sub = os.path.join(entry_path, header_name)
                if os.path.isfile(sub):
                    return [entry_path, d]
                inc = os.path.join(entry_path, header_subdir)
                if os.path.isdir(inc):
                    sub = os.path.join(inc, header_name)
                    if os.path.isfile(sub):
                        return [inc, entry_path]
                    for subdir2 in os.listdir(inc):
                        sub = os.path.join(inc, subdir2, header_name)
                        if os.path.isfile(sub):
                            return [os.path.join(inc, subdir2), inc, entry_path]
        except PermissionError:
            pass
    return []


def find_library_dir(hint_dirs, lib_name):
    for d in hint_dirs:
        if not os.path.isdir(d):
            continue
        for root, dirs, files in os.walk(d):
            for f in files:
                if f.startswith(lib_name) and (f.endswith(".lib") or f.endswith(".dll")):
                    return root
    return ""


def pkg_config_libs(names):
    libs = []
    for name in names:
        try:
            out = subprocess.check_output(
                ["pkg-config", "--libs", name], stderr=subprocess.DEVNULL, universal_newlines=True
            ).strip()
            inc = subprocess.check_output(
                ["pkg-config", "--cflags", name], stderr=subprocess.DEVNULL, universal_newlines=True
            ).strip()
            libs.append((out, inc))
        except Exception:
            libs.append(("", ""))
    return libs


include_dirs = [
    "src",
    "src/hal",
    pybind11.get_include(),
]
library_dirs = []
libraries = []
extra_compile_args = []
extra_link_args = []

is_linux = sys.platform.startswith("linux")
is_win = sys.platform.startswith("win")

if is_linux:
    try:
        pkg_config = pkg_config_libs([
            "libusb-1.0", "libsodium",
            "libavcodec", "libavformat", "libswscale", "libavutil",
        ])
        for out, inc in pkg_config:
            if inc:
                for arg in inc.split():
                    if arg.startswith("-I"):
                        include_dirs.append(arg[2:])
            if out:
                for arg in out.split():
                    if arg.startswith("-L"):
                        library_dirs.append(arg[2:])
                    elif arg.startswith("-l"):
                        libraries.append(arg[2:])
    except Exception:
        pass

    if not libraries:
        include_dirs += ["/usr/include/libusb-1.0", "/usr/include"]
        libraries = ["usb-1.0", "sodium", "avcodec", "avformat", "swscale", "avutil"]

    extra_compile_args = [
        "-std=c++20",
        "-Wno-unused-function", "-Wno-format-security",
        "-Wno-unused-variable", "-Wno-unused-but-set-variable",
    ]

elif is_win:
    extra_compile_args = [
        "/std:c++20", "/EHsc", "/utf-8",
        "/D_CRT_SECURE_NO_WARNINGS", "/wd4805", "/wd4996",
    ]
    libraries = ["libusb-1.0", "libsodium", "ws2_32"]

    _vcpkg_root = os.environ.get("VCPKG_ROOT", "")
    if not _vcpkg_root or not os.path.isdir(_vcpkg_root):
        # try relative to project root
        _vcpkg_candidate = os.path.join(os.path.dirname(os.path.dirname(__file__)), "vcpkg")
        if os.path.isdir(_vcpkg_candidate):
            _vcpkg_root = _vcpkg_candidate
        else:
            _vcpkg_root = ""
    _vcpkg_installed = os.path.join(_vcpkg_root, "installed", "x64-windows") if _vcpkg_root else ""

    # libusb
    _libusb_inc = os.path.join(_vcpkg_installed, "include", "libusb-1.0")
    if os.path.isdir(_libusb_inc):
        include_dirs.append(_libusb_inc)
    _libusb_lib = os.path.join(_vcpkg_installed, "lib")
    if os.path.isdir(_libusb_lib):
        library_dirs.append(_libusb_lib)

    # sodium
    _sodium_inc = os.path.join(_vcpkg_installed, "include")
    if os.path.isfile(os.path.join(_sodium_inc, "sodium.h")):
        include_dirs.append(_sodium_inc)
    _sodium_lib = os.path.join(_vcpkg_installed, "lib")
    if os.path.isdir(_sodium_lib) and _sodium_lib not in library_dirs:
        library_dirs.append(_sodium_lib)

    # FFmpeg from gyan.dev pre-built dev package
    _setup_dir = os.path.dirname(os.path.abspath(__file__))
    _ffmpeg_dev = os.path.join(_setup_dir, "ffmpeg_dev", "ffmpeg-dev",
                               "ffmpeg-8.1.2-full_build-shared")
    if os.path.isdir(os.path.join(_ffmpeg_dev, "include", "libavcodec")):
        include_dirs.append(os.path.join(_ffmpeg_dev, "include"))
        library_dirs.append(os.path.join(_ffmpeg_dev, "lib"))
        libraries += ["avcodec", "avutil", "swscale", "avformat"]

    env_inc = os.environ.get("INCLUDE", "")
    for p in env_inc.split(";"):
        p = p.strip()
        if p and os.path.isdir(p) and p not in include_dirs:
            include_dirs.append(p)

    env_lib = os.environ.get("LIB", "")
    for p in env_lib.split(";"):
        p = p.strip()
        if p and os.path.isdir(p) and p not in library_dirs:
            library_dirs.append(p)

sources = [
    "src/module.cpp",
    "src/receiver.cpp",
    "src/WFBProcessor.cpp",
    "src/fec.c",
    "src/Rtl8812aDevice.cpp",
    "src/WiFiDriver.cpp",
    "src/FrameParser.cpp",
    "src/RtlUsbAdapter.cpp",
    "src/FirmwareManager.cpp",
    "src/HalModule.cpp",
    "src/EepromManager.cpp",
    "src/RadioManagementModule.cpp",

    "src/hal/Hal8812PwrSeq.c",
    "src/hal/hal8812a_fw.c",
]

ext = Extension(
    "fpv_rx",
    sources=sources,
    include_dirs=include_dirs,
    library_dirs=library_dirs,
    libraries=libraries,
    extra_compile_args=extra_compile_args,
    extra_link_args=extra_link_args,
    language="c++",
)

setup(
    name="fpv_rx",
    version="0.1.0",
    description="FPV WFB-ng receiver for RTL8812AU",
    ext_modules=[ext],
    zip_safe=False,
)
