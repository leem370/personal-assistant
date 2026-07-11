# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：个人助理 Windows 版。

构建命令（Windows 上）：
    cd Windows版
    pyinstaller build.spec

产物：dist/个人助理/个人助理.exe（onedir 模式，启动快）

打包架构：
  - 入口：app.py（Tkinter GUI，windowed 模式不弹控制台黑窗）
  - 后端代码（core/bots/analysis/main.py）作为数据文件打包进去
  - 运行时 sys.path 临时指向解压目录，让 app.py 能 import 后端模块
"""
import os

block_cipher = None
SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
ROOT = os.path.dirname(SPEC_DIR)  # 项目根（Windows版 的上一级）

# 需要打包进去的后端代码目录/文件（作为数据文件，运行时解压）
datas = []
for pkg in ("core", "bots", "analysis"):
    pkg_path = os.path.join(ROOT, pkg)
    if os.path.isdir(pkg_path):
        datas.append((pkg_path, pkg))
# main.py
main_path = os.path.join(ROOT, "main.py")
if os.path.isfile(main_path):
    datas.append((main_path, "."))
# config.yaml 模板
config_template = os.path.join(ROOT, "config.yaml")
if os.path.isfile(config_template):
    datas.append((config_template, "."))

# 用 collect_all 强制收集整个包（含动态导入的子模块和数据文件）
from PyInstaller.utils.hooks import collect_all, collect_submodules

extra_datas = []
extra_binaries = []
extra_hiddenimports = []

# lark-oapi：内部大量动态导入，必须 collect_all
for pkg in ("lark_oapi",):
    d, b, h = collect_all(pkg)
    extra_datas += d
    extra_binaries += b
    extra_hiddenimports += h

# psutil：平台相关子模块
extra_hiddenimports += collect_submodules("psutil")

a = Analysis(
    ["app.py"],
    pathex=[SPEC_DIR],
    binaries=extra_binaries,
    datas=datas + extra_datas,
    hiddenimports=extra_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["flask", "django"],  # lark_oapi 的 flask/django adapter 不用，排除避免警告
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="个人助理",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # windowed 模式：不弹控制台黑窗
    disable_windowed_traceback=False,
    icon=os.path.join(SPEC_DIR, "assets", "app.ico")
         if os.path.exists(os.path.join(SPEC_DIR, "assets", "app.ico")) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="个人助理",
)
