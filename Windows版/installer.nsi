; 个人助理 Windows 安装包脚本（NSIS）
;
; 构建命令（在 GitHub Actions 里）：
;   cd Windows版 && makensis installer.nsi
;
; 产物：PersonalAssistantSetup.exe（用英文名避免 CI 编码问题）
; 功能：安装到 Program Files、创建桌面快捷方式、开始菜单项、带卸载入口

!include "MUI2.nsh"

#Unicode true

; 基本信息息
Name "个人助理"
OutFile "PersonalAssistantSetup.exe"
InstallDir "$PROGRAMFILES64\PersonalAssistant"
InstallDirRegKey HKLM "Software\PersonalAssistant" "InstallDir"
RequestExecutionLevel admin
ShowInstDetails show

; 图标（如果存在）
Icon "assets\app.ico"
UninstallIcon "assets\app.ico"

; 版本信息
VIProductVersion "1.0.0.0"
VIAddVersionKey "ProductName" "个人助理"
VIAddVersionKey "CompanyName" "PersonalAssistant"
VIAddVersionKey "FileDescription" "个人习惯追踪与效率助理"
VIAddVersionKey "FileVersion" "1.0.0"

; MUI 界面
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

; ========== 安装逻辑 ==========
Section "Install"
    SectionIn RO
    SetOutPath "$INSTDIR"

    ; 复制 PyInstaller 打包产物（dist/PersonalAssistant/）
    ; PyInstaller onedir 产物在 dist/PersonalAssistant/ 下
    File /r "dist\PersonalAssistant\*.*"

    ; 创建快捷方式
    CreateDirectory "$SMPROGRAMS\个人助理"
    CreateShortcut "$SMPROGRAMS\个人助理\个人助理.lnk" "$INSTDIR\PersonalAssistant.exe" "" "$INSTDIR\PersonalAssistant.exe" 0
    CreateShortcut "$DESKTOP\个人助理.lnk" "$INSTDIR\PersonalAssistant.exe" "" "$INSTDIR\PersonalAssistant.exe" 0

    ; 写注册表（卸载入口）
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PersonalAssistant" "DisplayName" "个人助理"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PersonalAssistant" "UninstallString" '"$INSTDIR\uninstall.exe"'
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PersonalAssistant" "DisplayIcon" '"$INSTDIR\PersonalAssistant.exe"'
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PersonalAssistant" "Publisher" "PersonalAssistant"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PersonalAssistant" "DisplayVersion" "1.0.0"
    WriteRegStr HKLM "Software\PersonalAssistant" "InstallDir" "$INSTDIR"

    ; 生成卸载程序
    WriteUninstaller "$INSTDIR\uninstall.exe"

    ; 完成提示
    SetAutoClose false
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
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\PersonalAssistant"
    DeleteRegKey HKLM "Software\PersonalAssistant"

    MessageBox MB_OK "个人助理已卸载。你的数据保留在 用户目录\个人助理数据\，可手动删除。"
SectionEnd
