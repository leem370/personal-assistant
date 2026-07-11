#!/bin/bash
# 个人助理控制台启动器
# 双击此文件即可打开控制面板 GUI
cd "$(dirname "$0")"
exec /Library/Developer/CommandLineTools/usr/bin/python3 control_panel.py
