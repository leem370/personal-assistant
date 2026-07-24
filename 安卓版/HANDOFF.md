# 交接文档 — 安卓版个人助理

## 项目概览

这是一个基于 **Kivy 2.2+ / KivyMD 1.1+** 框架开发的 Android 个人助理应用，用户有 ADHD/CPTSD 背景，app 的核心定位是**认知行为教练**。

**核心机制**：双 AI 人格协作——
- **小闹（Executor）**：管执行、待办、催办，简洁坚定
- **小知（Coach）**：管观察、反思、认知行为教练，遵循 CBT 规则

## 历史完成的工作

### 前期（上次会话）
- 项目结构梳理，通读全部核心代码
- 确认数据库 schema（8 张表）
- 确认定时任务体系
- 前端/后端代码分离：3 个页面从 main.py 拆到 `ui/screens/`
- main.py 从 493 行精简到 134 行
- 尝试 Docker 打包 APK，卡在网络拉取镜像

### 本轮：全面代码审查与修复

共修复 10 类问题，覆盖配置、数据库、后端逻辑、前端交互。下面是本次改动的重要点的总结。

### 本轮：第二次 Docker 打包尝试（详细记录）

构建环境：macOS Sequoia + Docker Desktop 4.82（aarch64）

| 尝试 | 结果 | 原因 |
|------|------|------|
| 直接用 `kivy/buildozer:latest`（arm64） | ❌ | entrypoint 问题是 `buildozer`，传参方式不对 |
| 加 `--entrypoint=""` 正确传参 | ❌ | git clone python-for-android 网络超时 |
| 加 `--network host` 解决网络 | ❌ | NDK zip 解压提示文件冲突（`ipt_ecn.h` 重复） |
| 手动删 NDK 残留后重跑 | ❌ | NDK 解压后 aidl 报错：`Aidl cannot be executed`，缺 32-bit libs |
| 装 libc6-i386 + lib32stdc++6 | ❌ | 同错：aidl 是 x86_64 二进制，容器是 **linux/arm64**，架构不对 |
| 注册 QEMU binfmt 跨架构支持 | ❌ | Docker Desktop 内 `containerd-shim-runc-v2` exec format error |
| 拉 `--platform linux/amd64` 版本 | ❌ | 网络拉取超时（和最初同问题） |

**根本原因**：
- M 系列芯片上的 Docker Desktop 跑的是 **arm64 Linux 容器**
- Android SDK 工具链（aidl/aapt/aapt2）全是 **x86_64 二进制**，arm64 Linux 下无法执行
- `--platform linux/amd64` 可以走 Rosetta 模拟，但 Docker Hub 拉取超时
- 宿主机也无 JDK（Apple stub 而非真 JDK），无法本地打包

**已经缓存在本地的 SDK 资源**（`/tmp/.buildozer/android/platform/` 下，供后续复用）：
- ✅ Android SDK commandlinetools（已下载解压）
- ✅ build-tools 37.0.0
- ✅ Android NDK r25b（已手动解压）
- ✅ platform-tools / licenses
- ❌ aidl 因架构问题无法执行

## 本轮改动详情

### 🔴 致命问题修复

**1. buildozer.spec 修复**
- 移除了 `source.exclude_dirs` 中错误的 `ui/widgets,ui/screens`（之前会把 UI 页面排除在 APK 外导致崩溃）
- `requirements` 加上了缺失的 `schedule` 库
- 删除了未使用的 `pytz`

**2. requirements.txt 同步**
- 加了 `schedule>=1.2.0`
- 删了 `pytz`（代码里没有用到）

**3. SQLite 并发安全**
- `core/db.py` 的 `get_conn()` 加了 `PRAGMA journal_mode=WAL` 和 `PRAGMA busy_timeout=5000`，防止调度线程写操作阻塞 UI 线程读操作

### 🟡 后端逻辑修复

**4. ai.config 隐式访问改为显式导入**
- `bots/xiaonao.py` 和 `bots/xiaozhi.py` 原来写 `ai.config.ai_enabled()`，依赖模块内部 import 的副作用。现在改为直接 `from core import config` 然后 `config.ai_enabled()`

**5. query_recent_logs N+1 连接问题**
- 原来 `query_recent_logs(days=7)` 循环 7 次开 7 个连接，每次调 `query_logs_by_date`
- 改为单条 SQL 按日期范围查询
- `query_recent_logs_for_task` 也有类似的 `created_at LIKE` bug（只匹配今天），一并修复

**6. 抽取重复代码**
- 新建 `core/notify.py`：提取 xiaonao/xiaozhi 里完全重复的 `_notify()` 函数
- 新建 `core/utils.py`：提取 xiaozhi/archive 里完全重复的 `_iso_week()` 和 xiaonao 里的 `_parse_weekday()`
- xiaonao.py、xiaozhi.py、archive.py 全部改为 import 共享模块

**7. datetime import 规范化**
- xiaonao.py 和 xiaozhi.py 原来在函数体内 `import datetime`，现在统一到文件顶部

**8. archive 归档安全保护**
- `analysis/archive.py` 原来 `run_archive()` 先尝试归档各日期，然后全量删除 >21 天数据——归档失败的日期数据也丢了
- 新增 `db.cleanup_specific_dates()`，只删除已确认归档成功的日期
- `run_archive()` 改为只删除成功归档日期对应的原始明细

**9. 用户画像刷新时保护已有沉淀**
- `analysis/profile.py` 的 `refresh_profile()` 原来完全信任 AI 返回的新画像，AI 遗漏会导致 success_strategies / failure_triggers 永久丢失
- 现在保存前会将旧画像和新画像的这两个字段做合并去重，最多各保留 15 条

**10. 其他微修复**
- `init_db()` 日志计数改为统计实际插入行数而非配置条目数
- `executor._do_log()` 对 AI 返回的 completion_rate / focus_score 加了 clamp（0-100 / 0-10）
- `profile.days_since_start()` 原来只看 logs 表，现在同时看 observations 表（避免用户只聊天不打卡时永远不刷新画像）
- `config.yaml` 补上了缺失的 `fitness_reminder_monday` 和 `fitness_reminder_thursday`
- `core/config.py` 加了默认值合并逻辑，配置文件缺字段时不会崩

### 🟢 前端改进

**11. 三个页面都加了 SnackBar 反馈**
- `TodayScreen`：点击任务条目弹出详情 SnackBar（原来 `show_task_detail` 是空方法）
- `AddTaskScreen`：保存成功后弹出「已添加任务：xxx」提示
- `CompleteScreen`：提交成功后弹出「✅ 已打卡：xxx」提示

**12. 表单校验加强**
- `AddTaskScreen`：加了时间格式校验（HH:MM）、周几格式校验（1-7 逗号分隔）、goal_id 非数字时提示
- `CompleteScreen`：`on_enter` 先清空表单再预填（原来残留上次文字）
- 返回按钮统一清空表单再跳转

## 当前项目文件结构

```
安卓版/
├── main.py              # App 入口
├── buildozer.spec       # Android 打包配置（已修复）
├── requirements.txt     # 依赖清单（已同步）
├── config.yaml          # 应用配置（已补全健身提醒项）
├── .env.example         # 环境变量示例
├── ui/
│   ├── __init__.py
│   ├── screens/
│   │   ├── __init__.py          # 导出三个页面
│   │   ├── today_screen.py      # 今日待办（含 SnackBar）
│   │   ├── add_task_screen.py   # 添加任务（含格式校验 + SnackBar）
│   │   └── complete_screen.py   # 完成打卡（含 SnackBar）
│   └── widgets/
│       └── __init__.py
├── core/
│   ├── db.py            # 数据库层（WAL 模式 + cleanup_specific_dates）
│   ├── config.py        # 配置加载（默认值合并）
│   ├── scheduler.py     # 定时任务调度
│   ├── ai.py            # AI 调用封装
│   ├── memory.py        # 多轮对话记忆
│   ├── notify.py        # 🆕 本地通知封装
│   └── utils.py         # 🆕 通用工具（iso_week, parse_weekday）
├── bots/
│   ├── xiaonao.py       # 小闹（执行/催办）— 已重构
│   ├── xiaozhi.py       # 小知（观察/教练）— 已重构
│   └── executor.py      # 意图执行器（数值 clamp）
└── analysis/
    ├── reflect.py       # 反思与画像调度
    ├── profile.py       # 用户画像（合并保护 + days_since_start 修复）
    ├── archive.py       # 数据归档清理（安全删除）
    └── plan.py          # ⚠ 尚未接入调度系统，待集成
```

## 当前进展

| 项目 | 状态 |
|------|------|
| 项目结构梳理 | ✅ 完成 |
| 前后端分离 | ✅ 完成 |
| 代码审查与修复 | ✅ 本轮完成（10 类问题） |
| Docker 打包 APK | ❌ 架构不兼容 + 网络拉取超时（见下方详细记录） |
| plan.py 接入调度 | ⏳ 待做 |

## 下一步建议

1. **打包 APK 的可行路线**（按推荐顺序）：
   - **方案 A（最推荐）**：找一台 x86_64 Linux 机器或云服务器，直接 `buildozer android debug`——所有依赖一步到位
   - **方案 B**：配置 GitHub Actions CI 自动打包，每次推送自动生成 APK
   - **方案 C**：在有 brew 和稳定网络的 Mac 上，`brew install openjdk` + `pip install buildozer` 本地打包
2. **接入 plan.py**：`analysis/plan.py` 的 `suggest_daily_plan()` 尚未被调用。可以在小闹早间定时任务中加入「今日规划建议」，或用户 @小闹 时触发
3. **写单元测试**：核心 repo 函数（db.py）目前没有测试，后续改动风险高。建议从 db.py 开始加 pytest

## 经验与注意事项（保留 + 新增）

1. **Docker 打包在 macOS 上的坑（第二次尝试总结）**：
   - Docker Desktop 在 aarch64 Mac 上安装后，`docker` CLI 需手动从 `/Applications/Docker.app/Contents/Resources/bin/docker` 调用或加入 PATH
   - `kivy/buildozer:latest` 镜像的 entrypoint 就是 `buildozer`，所以 `docker run kivy/buildozer:latest buildozer android debug` 会被解释为 `buildozer buildozer android debug`，需要用 `--entrypoint=""` 覆盖
   - 容器内 HOME=/root（不是 /home/user），`--volume /tmp/.buildozer:/root/.buildozer` 才持久化缓存
   - **架构问题**：Docker Desktop on Apple Silicon 的默认容器是 linux/arm64，但 Android SDK 工具链是 x86_64 原生二进制，无法在 arm64 Linux 下执行（QEMU binfmt 注册也因 Docker Desktop 限制不完整）
   - **解决方案**：找 x86_64 Linux 机器 / 云服务器 / GitHub Actions 打包，或者用 `brew install openjdk` 后在 macOS 上 `pip install buildozer` 直接跑
   - 已缓存的 SDK/NDK 在 `/tmp/.buildozer/android/platform/`，打包时可复用避免重新下载

2. **项目结构约定**：
   - UI 页面 → `ui/screens/`，每个页面一个文件
   - 自定义控件 → `ui/widgets/`
   - 核心逻辑在 `core/`、`bots/`、`analysis/` 中，不依赖 Kivy 框架
   - 共享工具（notify, utils）在 `core/` 下，不要重复定义
   - 新增页面：在 `ui/screens/` 创建 → `__init__.py` 导出 → `main.py` ScreenManager 注册

3. **数据库**：SQLite + repo 模式 + WAL 模式。`cleanup_specific_dates` 是新的安全删除接口

4. **AI 相关**：需要 `.env`（AI_API_KEY, AI_API_BASE, AI_MODEL）；不可用时有正则后备

5. **用户偏好**：使用中文交流；偏好文字描述而非表格

6. **代码格式（本轮统一后的约定）**：
   - datetime 统一在文件顶部导入，不在函数体内 `import datetime`
   - 通知用 `from core.notify import notify`
   - 日期工具用 `from core.utils import iso_week, parse_weekday`
   - 前端页面统一提供 `show_snackbar()` 方法用于用户反馈
   - buildozer.spec 的 `source.exclude_dirs` 千万不要排除 `ui/` 下的任何目录
