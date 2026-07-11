; 个人助理 Windows 安装包脚本（NSIS）
;
; 构建命令（在 GitHub Actions 里自动执行）：
;   makensis installer.nsi
;
; 产物：个人助理Setup.exe
; 功能：安装到 Program Files、创建桌面快捷方式、开始菜单项、带卸载入口

#Unicode true

; 基本信息息
Name "个人助理"
OutFile "个人助理Setup.exe"
InstallDir "$PROGRAMFILES64\个人助理"
InstallDirRegKey HKLM "Software\个人助理" "InstallDir"
RequestExecutionLevel admin

; 界面
Icon "assets\app.ico"
UninstallIcon "assets\app.ico"

; 版本信息
VIProductVersion "1.0.0.0"
VIAddVersionKey "ProductName" "个人助理"
VIAddVersionKey "CompanyName" "个人助理"
VIAddVersionKey "FileDescription" "个人习惯追踪与效率助理"
VIAddVersionKey "FileVersion" "1.0.0"

; ========== 安装逻辑 ==========
Section "Install"
    SetOutPath "$INSTDIR"

    ; 复制 PyInstaller 打包产物（dist/个人助理/ 整个目录）
    File /r "dist\个人助理\*.*"

    ; 创建快捷方式
    CreateDirectory "$SMPROGRAMS\个人助理"
    CreateShortcut "$SMPROGRAMS\个人助理\个人助理.lnk" "$INSTDIR\个人助理.exe" "" "$INSTDIR\个人助理.exe" 0
    CreateShortcut "$DESKTOP\个人助理.lnk" "$INSTDIR\个人助理.exe" "" "$INSTDIR\个人助理.exe" 0

    ; 写注册表（卸载入口）
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\个人助理" "DisplayName" "个人助理"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\个人助理" "UninstallString" '"$INSTDIR\uninstall.exe"'
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\个人助理" "DisplayIcon" '"$INSTDIR\个人助理.exe"'
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\个人助理" "Publisher" "个人助理"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\个人助理" "DisplayVersion" "1.0.0"
    WriteRegStr HKLM "Software\个人助理" "InstallDir" "$INSTDIR"

    ; 生成卸载程序
    WriteUninstaller "$INSTDIR\uninstall.exe"

    ; 完成提示
    MessageBox MB_YESNO "安装完成！是否立即启动个人助理？" IDNO skip_launch
        Exec "$INSTDIR\个人助理.exe"
    skip_launch:
SectionEnd

; ========== 卸载逻辑 ==========
Section "Uninstall"
    ; 删除安装目录（保留用户数据，用户数据在 ~/个人助理数据/）
    RMDir /r "$INSTDIR"

    ; 删除快捷方式
    Delete "$SMPROGRAMS\个人助理\个人助理.lnk"
    RMDir "$SMPROGRAMS\个人助理"
    Delete "$DESKTOP\个人助理.lnk"

    ; 清除注册表
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\个人助理"
    DeleteRegKey HKLM "Software\个人助理"

    MessageBox MB_OK "个人助理已卸载。你的数据保留在 用户目录\个人助理数据\，可手动删除。"
SectionEnd
