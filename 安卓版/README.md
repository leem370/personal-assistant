# 个人助理安卓版

基于 Kivy + KivyMD 框架开发的 Android 个人助理应用。

## 功能清单

- **今日待办**：查看当天所有待办任务
- **添加任务**：新增固定/弹性任务
- **完成打卡**：记录完成度、专注分、情绪
- **观察记录**：随手记录当下的状态和感受
- **数据分析**：查看近 14 天数据和 AI 分析
- **用户画像**：查看系统对你的理解

## 技术栈

- **框架**：Kivy 2.2+（跨平台 UI）
- **组件库**：KivyMD 1.1+（Material Design）
- **核心逻辑**：复用 `../core` 和 `../bots` 模块
- **打包工具**：Buildozer（Python → Android APK）

## 快速开始

### 1. 安装依赖（开发环境）

```bash
pip install -r requirements.txt
```

### 2. 运行应用（桌面测试）

```bash
python main.py
```

### 3. 打包 Android APK

需要 Linux 环境（macOS/Windows 需用 Docker 或虚拟机）：

```bash
# 安装 Buildozer
pip install buildozer

# 初始化（首次）
buildozer init

# 打包 APK
buildozer android debug

# 打包并部署到手机
buildozer android debug deploy run
```

## 项目结构

```
安卓版/
├── main.py              # App 入口
├── buildozer.spec       # 打包配置
├── config.yaml          # 应用配置
├── requirements.txt     # 依赖清单
├── .env.example         # 环境变量示例
├── assets/              # 图标、字体等资源
└── ui/                  # UI 界面
    ├── screens/         # 各个页面（今日待办、添加任务等）
    └── widgets/         # 自定义控件
```

## 核心逻辑复用

安卓版复用了 PC 版的核心模块：

- `../core/db.py`：数据库层（SQLite）
- `../core/ai.py`：AI 调用封装
- `../core/memory.py`：多轮对话记忆
- `../bots/executor.py`：意图执行器
- `../analysis/profile.py`：用户画像
- `../analysis/archive.py`：数据归档

**不需要** PC 版的飞书相关模块（已删除）：
- ~~`../core/feishu.py`~~
- ~~`../core/bitable.py`~~

## 配置

1. 复制 `.env.example` 为 `.env`
2. 填入 AI API 密钥：
   ```
   AI_API_KEY=your_api_key
   AI_API_BASE=https://api.openai.com/v1
   ```

## 注意事项

- 数据库默认存放在 `./data/personal_assistant.db`
- Android 打包需要在 Linux 环境下进行（推荐 Ubuntu）
- macOS 下可以用 Docker 运行 Buildozer：
  ```bash
  docker pull kivy/buildozer
  docker run --rm -v "$PWD":/app kivy/buildozer android debug
  ```