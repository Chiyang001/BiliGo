# BiliGo V3 Ultra

<div align="center">

![Version](https://img.shields.io/badge/version-V3_Ultra-blue.svg)
![Status](https://img.shields.io/badge/status-released-brightgreen.svg)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg)
![Docker](https://img.shields.io/badge/Docker-supported-2496ED.svg)

面向 B 站、抖音、小红书、微博和闲鱼的多平台消息自动回复与 AI 客服系统。

[功能概览](#功能概览) · [快速开始](#快速开始) · [AI-回复机制](#ai-回复机制) · [Docker 部署](#docker-部署) · [项目结构](#项目结构) · [更新日志](#更新日志)

</div>

> [!IMPORTANT]
> BiliGo 是非官方自动化工具。平台接口和页面结构可能随时变化，请合理设置检测及发送间隔，并遵守各平台规则和适用法律法规。

## 功能概览

BiliGo V3 Ultra 将五个平台、六类消息入口整合到同一个 Web 管理界面：

| 平台/入口 | 登录方式 | 传统规则回复 | AI 回复 | 说明 |
| --- | --- | --- | --- | --- |
| B 站私信 | `SESSDATA`、`bili_jct` | 文字、图片 | 支持 | 支持关注/取关回复、回复次数限制 |
| B 站评论 | B 站 Cookie | 仅文字 | 支持 | 支持 API/WBI 与可选浏览器抓取模式 |
| 抖音私信 | 浏览器登录 | 文字 | 支持 | Playwright 持久化登录会话 |
| 小红书私信 | 浏览器登录 | 文字 | 支持 | 独立 Cookie、规则、统计与日志 |
| 微博私信 | 浏览器登录 | 文字 | 支持 | 独立 Cookie、规则、统计与日志 |
| 闲鱼消息 | 浏览器登录 | 文字 | 支持 | 独立 Cookie、规则、统计与日志 |

### 自动回复

- 关键词规则、默认回复、启用/停用单条规则。
- 仅回复启动后的新消息，避免首次启动批量处理历史会话。
- 单用户回复次数限制、发送延迟和检测间隔配置。
- B 站私信支持文字和图片；B 站评论及其他浏览器平台使用文字回复。
- 各平台配置、登录状态、回复统计和运行日志相互隔离。
- 支持平台间导入规则，可选择替换或追加；不会复制 Cookie、登录会话和统计数据。

### AI 客服

- 统一管理 OpenAI、Anthropic 和自定义兼容接口。
- 每个平台可独立启用 AI，不影响其他平台继续使用传统规则。
- 支持多知识库、文本或 Markdown 文档导入，以及按平台分配知识库。
- 支持上下文窗口、自动压缩、违禁词拦截和模型参数配置。
- AI 无法可靠处理时可加入人工待回队列。
- 保存会话上下文，并在仪表盘汇总调用量、响应情况和人工待回数据。

### 运维能力

- 统一仪表盘、分类日志、平台运行状态和基础统计。
- 登录失效与运行异常邮件提醒。
- 配置导入导出、Docker 数据卷持久化。
- Windows 单文件 EXE 构建。
- 基础 Docker 镜像以及内置 Chromium 的 Playwright 完整镜像。

## 页面入口

程序默认监听 `4999` 端口：

| 页面 | 地址 |
| --- | --- |
| B 站私信 | <http://localhost:4999/> |
| B 站评论 | <http://localhost:4999/comment> |
| 抖音私信 | <http://localhost:4999/douyin> |
| 小红书私信 | <http://localhost:4999/xiaohongshu> |
| 微博私信 | <http://localhost:4999/weibo> |
| 闲鱼消息 | <http://localhost:4999/xianyu> |
| AI 回复设置 | <http://localhost:4999/ai-reply> |
| 数据仪表盘 | <http://localhost:4999/dashboard> |
| 系统日志 | <http://localhost:4999/logs.html> |
| 使用文档 | <http://localhost:4999/docs.html> |

## 快速开始

### 环境要求

- 推荐 Python 3.11。
- Windows、Linux 或 macOS。
- 浏览器平台建议安装 Chrome；也可以安装 Playwright Chromium。
- 服务器部署推荐 Docker。

### 源码运行

```bash
git clone https://github.com/Chiyang001/BiliGo.git
cd BiliGo
python -m pip install -r requirements.txt
python app.py
```

如需使用抖音、小红书、微博、闲鱼或 B 站评论浏览器模式，再安装 Playwright：

```bash
python -m pip install playwright
playwright install chromium
```

建议把运行数据放到独立目录，避免配置文件与源码混在一起。

PowerShell：

```powershell
$env:BILIGO_DATA_DIR="$PWD\.biligo-data"
python app.py
```

Linux/macOS：

```bash
export BILIGO_DATA_DIR="$PWD/.biligo-data"
python app.py
```

可通过 `PORT` 环境变量修改监听端口：

```bash
PORT=5000 python app.py
```

## Windows 单文件 EXE

项目提供 PyInstaller 构建配置：

```bat
build_exe.bat
```

构建结果位于：

```text
dist/BiliGo.exe
```

EXE 首次运行时会在数据目录生成无凭据的默认配置。浏览器自动化平台仍需要系统 Chrome 或可用的 Playwright Chromium 运行时。

## Docker 部署

### 基础镜像

基础镜像适合 B 站 API 模式及 Web 管理界面：

```bash
docker build -t biligo:latest .
docker run -d \
  --name biligo \
  -p 4999:4999 \
  -v biligo-data:/data \
  --restart unless-stopped \
  biligo:latest
```

也可以使用 Docker Compose：

```bash
docker compose up -d --build
docker compose logs -f
```

### Playwright 完整镜像

需要运行抖音、小红书、微博、闲鱼或 B 站评论浏览器模式时，建议使用包含 Chromium 的完整镜像：

```bash
docker build -t biligo:latest .
docker build -f Dockerfile.playwright -t biligo:playwright .
docker run -d \
  --name biligo \
  -p 4999:4999 \
  -v biligo-data:/data \
  --restart unless-stopped \
  biligo:playwright
```

容器配置、规则、浏览器登录状态和数据库保存在 `/data`。删除容器不会删除命名卷；请勿在未备份时删除 `biligo-data` 卷。

## 平台配置

### B 站

1. 登录 [Bilibili](https://www.bilibili.com/)。
2. 打开浏览器开发者工具，在 B 站域名 Cookie 中找到 `SESSDATA` 和 `bili_jct`。
3. 在 B 站私信页面填写并保存凭据。
4. 配置默认回复、关键词规则、发送间隔和回复次数。
5. 启动监控并观察日志。

程序会为私信账号生成独立的 `im_dev_id`。不要在多个账号之间复制该值，否则可能增加触发 HTTP 412 风控的概率。

### 抖音、小红书、微博和闲鱼

1. 打开对应平台页面。
2. 点击登录按钮，在弹出的浏览器窗口中完成登录。
3. 回到 BiliGo，确认登录状态已更新。
4. 配置传统规则或在统一 AI 页面启用该平台。
5. 点击开始监控，并先使用测试账号验证。

每个平台使用独立浏览器资料目录。退出平台账号、清理资料目录或 Cookie 失效后，需要重新登录。

## AI 回复机制

处理流程如下：

```text
收到新消息
  → 检查平台是否启用 AI
  → 读取该会话的上下文
  → 加载分配给该平台的知识库
  → 调用所配置的大模型接口
  → 违禁词与有效性检查
  → 发送回复，或进入人工待回队列
```

配置步骤：

1. 打开“AI 回复设置”。
2. 选择接口格式，填写 Base URL、模型和 API Key。
3. 测试连接并保存。
4. 按需创建知识库并分配到平台。
5. 独立开启目标平台的 AI 开关。
6. 返回平台页面启动监控。

启用 AI 后，该平台的传统默认回复和关键词规则会锁定。AI 请求失败不会自动发送传统默认回复，以避免错误或重复答复；请通过运行日志检查接口地址、模型、额度、网络和密钥。

## 数据与安全

- 仓库只提供无凭据的默认配置模板，位于 `docker/defaults/`。
- `config.json`、`*_storage.json`、浏览器资料目录和 SQLite 数据库可能包含敏感信息。
- 不要上传 Cookie、`SESSDATA`、`bili_jct`、邮箱授权码或 AI API Key。
- Docker 构建上下文会排除本地配置、登录状态、媒体缓存和数据库。
- 导出的跨平台规则包不包含浏览器登录会话。
- 建议定期备份数据目录，并限制其文件访问权限。

## 项目结构

```text
BiliGo/
├─ app.py                         # Flask 主应用、B 站与统一 API
├─ app_paths.py                   # 源码/EXE/Docker 数据路径管理
├─ ai_reply_service.py            # AI 请求、上下文与知识库组装
├─ ai_conversation_store.py       # AI 会话持久化
├─ ai_handoff_store.py            # 人工待回队列
├─ dashboard_metrics.py           # 仪表盘指标
├─ *_reply_system.py              # 各平台业务与路由
├─ *_playwright.py                # 各平台浏览器自动化
├─ *.html / *.js / *.css          # Web 管理界面
├─ docker/defaults/               # 无凭据默认配置
├─ scripts/                       # 回归与页面冒烟测试
├─ BiliGo.spec                    # PyInstaller 单文件配置
├─ Dockerfile                     # 基础镜像
├─ Dockerfile.playwright          # Chromium 完整镜像
└─ docker-compose.yml             # Docker Compose 部署
```

## 开发与验证

```bash
python scripts/smoke_test_regressions.py
python scripts/smoke_test_platform_login_guards.py
python scripts/smoke_test_xianyu.py
python scripts/smoke_test_comment_ui.py
```

提交代码前，请确认没有加入本地配置、浏览器资料、数据库、日志或打包产物。

## 常见问题

### 浏览器平台提示未登录

先以非无头模式打开登录窗口并完成登录。如果平台验证页面有变化，清理该平台浏览器资料目录后重新登录；清理前请先备份需要保留的数据。

### B 站出现 HTTP 412

暂停监控，在浏览器中手动访问 B 站消息页面并完成验证，然后增加检测和发送间隔。确认每个账号使用独立 `im_dev_id`，不要同时高频发送。

### AI 已配置但没有回复

确认目标平台的 AI 开关和平台监控均已启动，并检查模型名称、Base URL、API Key、账户额度及日志。仅保存 AI 配置不会自动启动平台监控。

### Docker 中浏览器平台无法启动

基础镜像不包含 Chromium，请改用 `biligo:playwright` 镜像，并保证 `/data` 可写。

### 为什么 B 站评论没有图片回复

V3 Ultra 已移除 B 站评论图片回复，评论默认回复和关键词规则统一为文字，减少上传失败和平台兼容问题。B 站私信仍可使用图片回复。

## 更新日志

### V3 Ultra（2026-09-05）

V3 Ultra 已正式发布，在 20260830 稳定版基础上完成多平台与 AI 能力整合。

**新增功能**：

- 接入抖音、小红书、微博和闲鱼消息自动回复。
- 建立五平台、六类消息入口的统一导航和配置导入机制。
- 新增统一 AI 回复设置，支持 OpenAI、Anthropic 与自定义兼容接口。
- 新增多知识库、平台分配、上下文压缩、违禁词和人工待回机制。
- 新增数据仪表盘、AI 会话存储与人工待回存储。
- 新增 Windows 单文件 EXE 与 Playwright Chromium Docker 构建方案。

**修复与优化**：

- 修复 Playwright 浏览器生命周期与重复启动问题。
- 修复闲鱼知识库平台分配问题。
- 移除 B 站评论图片回复，评论规则统一为文字。
- 完善平台登录保护、仅回复新消息基线和跨平台配置转换。
- 打包和 Docker 镜像改用无凭据默认模板，避免误包含本地 Cookie 与 API Key。
- 清理仓库中的 Python 编译缓存，并补充忽略规则和冒烟测试。

### 20260830（2026-08-30）

- 修复多账号并行模式下的关注回复和登录校验。
- 为每个账号使用独立 `im_dev_id`、发送间隔和回复统计。
- 改进 API 重连、登录失效提醒与风控提示。
- 新增 Dockerfile、Docker Compose 和部署脚本。

### 20260518 Emergency（2026-05-18）

- 修复 B 站私信 HTTP 412 大面积失败问题。
- 补充 `csrf_token`、页面预热、风控 Cookie、UA 和 Origin。
- 将 HTTP 412 从普通网络错误中区分出来。

### Ver.20260401（2026-04-01）

- 新增邮件提醒和登录失效通知。
- 完善 B 站评论回复、缓存清理和处理统计。
- 优化规则匹配、页面布局和运行稳定性。

## 使用声明

- 本项目仅供学习、研究和个人效率工具用途。
- 禁止用于骚扰、垃圾信息、绕过平台限制或其他违法违规行为。
- 自动化操作可能触发平台风控、限制或封禁，相关风险由使用者自行承担。
- 平台页面或接口调整后，浏览器自动化功能可能需要同步更新。

## 联系方式

- 作者：炽阳001
- B 站主页：<https://space.bilibili.com/404891612>
- 项目地址：<https://github.com/Chiyang001/BiliGo>
- 问题反馈：请提交 GitHub Issue

<div align="center">

如果这个项目对你有帮助，欢迎点一个 ⭐ Star。

</div>
