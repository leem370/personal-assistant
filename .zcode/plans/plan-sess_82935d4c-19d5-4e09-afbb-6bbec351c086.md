# Windows 安装包方案（不改原代码版）

## 核心原则
**所有现有后端代码（main.py / core/ / bots/ / analysis/ / 前端/）零改动**。Windows 版全部放新建的 `Windows版/` 文件夹。

## 复用策略
Windows 版通过 **sys.path 插入上级目录** 的方式 import 现有后端模块（core/bots/analysis），业务逻辑直接复用，不复制代码。

只有 3 处必须在 Windows 版里**重新实现跨平台版本**（因为原版用了 Unix 专用命令，不能直接复用）：
- 进程管理（原版用 pgrep/ps，Windows 版用 psutil）
- 路径解析（原版相对路径，Windows 版重定向到用户数据目录）
- 字体（原版 PingFang SC，Windows 版用 Microsoft YaHei）

这 3 个适配文件放 `Windows版/`，import 后端模块用，但不改后端。

## 文件夹结构
```
个人助理/
├── Windows版/                    ← 全新，独立文件夹
│   ├── app.py                    ← 入口（配置向导 + 控制台）
│   ├── process_manager_win.py    ← 跨平台进程管理（psutil）
│   ├── config_loader.py          ← 跨平台路径/配置加载（重定向到用户目录）
│   ├── setup_wizard.py           ← 首次配置向导 GUI
│   ├── build.spec                ← PyInstaller 打包配置
│   ├── installer.nsi             ← NSIS 安装包脚本
│   ├── requirements.txt          ← Windows 版依赖（含 psutil）
│   └── assets/app.ico            ← 图标
├── main.py / core/ / bots/ / ... ← 现有，零改动
└── .github/workflows/build-windows.yml  ← GitHub Actions 云构建
```

## 实施步骤

### 第1步：跨平台适配层（基础，半天）
- `Windows版/process_manager_win.py`：用 psutil 重写进程查找/启停，Mac 和 Windows 都能跑
- `Windows版/config_loader.py`：配置/数据/日志路径重定向到 `~/个人助理数据/`
- 验证：Mac 上 import 现有 core 能正常工作

### 第2步：配置向导 + 控制台（半天）
- `Windows版/setup_wizard.py`：4 步配置（飞书/AI/多维表格/完成），每步测试连接
- `Windows版/app.py`：入口，检测配置→弹向导或控制台，字体跨平台
- 验证：Mac 上跑通完整流程

### 第3步：PyInstaller 打包配置（半天）
- `Windows版/build.spec`：打包入口、依赖、图标
- 在 Mac 本地打 Mac .app 验证打包流程通

### 第4步：GitHub Actions 云构建（半天）
- `.github/workflows/build-windows.yml`：Windows runner + PyInstaller + NSIS
- push 到 GitHub 自动产出 `个人助理Setup.exe`

### 第5步：联调测试（半天）
- 朋友装 + 你帮配 + 修 bug

## 不碰的东西（承诺）
- main.py、core/、bots/、analysis/、前端/ 全部不修改
- 现有 Mac 版功能完全不受影响
- Windows 版是纯增量，删掉 Windows版文件夹不影响现有系统

需要你配合：GitHub 仓库地址（第4步要用）。

从第1步开始？