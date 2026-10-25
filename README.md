# BiliGo V3.2.2 Ultra

<div align="center">

![Version](https://img.shields.io/badge/version-V3.2.2_Ultra-blue.svg)
![Status](https://img.shields.io/badge/status-released-brightgreen.svg)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg)
![Docker](https://img.shields.io/badge/Docker-supported-2496ED.svg)

面向 B 站、抖音、小红书、微博和闲鱼的多平台消息自动回复与 AI 客服系统。

[功能概览](#功能概览) · [快速开始](#快速开始) · [AI-回复机制](#ai-回复机制) · [Docker 部署](#docker-部署) · [项目结构](#项目结构) · [更新日志](#更新日志)

</div>

> [!IMPORTANT]
> BiliGo 是非官方自动化工具。平台接口和页面结构可能随时变化，请合理设置检测及发送间隔，并遵守各平台规则和适用法律法规。

## 功能概览

BiliGo V3.2.2 Ultra 将五个平台、六类消息入口整合到同一个 Web 管理界面：

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

## 面板密码与文件访问安全

启动后，所有平台页面、账号 Cookie、配置、日志、导入导出与管理接口都需要先登录面板。B 站账号登录与面板密码相互独立。

- 首次启动自动生成随机初始密码；**尚未设置自定义密码时，每次启动都会在本机终端显示同一个初始密码**，不会写入网页日志或访问链接。显示发生在浏览器运行时检查之前。
- 使用初始密码登录后，必须在“设置你的面板密码”页设置至少 8 个字符且与原密码不同的新密码，才能访问工作台或任何业务接口。设置成功后，初始密码立即失效、所有登录会话被撤销，此后终端不再显示初始密码。初始登录只发放 15 分钟的浏览器会话，不提供记住登录。
- 右上角可选择“跟随系统 / 明亮模式 / 黑暗模式”。默认跟随系统，手动选择仅作为此浏览器的外观偏好保存。
- 默认登录使用浏览器会话 Cookie，关闭浏览器后需要重新登录，服务端最长有效期为 12 小时。勾选“记住密码并自动登录”后，此浏览器可自动登录 30 天；其他设备或浏览器仍需输入密码。浏览器恢复会话功能可能保留会话 Cookie，共用设备请主动点击“退出面板”。
- 页面顶部的“面板安全”可修改密码，修改后立即撤销所有设备的登录。退出面板会撤销当前浏览器的会话；不会停止正在运行的回复任务。
- 自定义密码仅保存加盐 PBKDF2 哈希，设备会话仅保存令牌哈希，保存在数据目录的 `.biligo_web_auth.sqlite3` 中。初始密码在尚未完成设置时临时保存在这个受限数据库内，用于下次启动显示；设置自定义密码时会清除临时值，并开启 SQLite 安全删除。旧版 URL token、`BILIGO_WEB_TOKEN` 和 `BILIGO_WEB_AUTH=0` 不再提供访问权限。
- 旧版仅保存密码哈希，无法还原初始密码，也无法判断当时是否已自定义。升级时保留原密码，首次登录后要求设置新的自定义密码；如旧密码已经丢失，在相同 `BILIGO_DATA_DIR` 下执行 `python web_access.py --reset-initial-password`，终端会显示新的初始密码，所有旧会话立即失效。新版 EXE 可运行 `BiliGo_V3.2.2_Ultra.exe --reset-panel-password`。重置只影响面板密码，平台账号和配置不变。
- 如忘记密码，在使用相同 `BILIGO_DATA_DIR` 的服务器终端执行 `python web_access.py --reset-password`，按提示输入新密码。EXE 或 Docker 也可设置 `BILIGO_PANEL_PASSWORD` 后重启来重置。该变量如一直保留，**每次启动都会以其值为准**，覆盖网页内后续修改的密码；重置后建议移除此环境变量。
- 静态文件只允许访问明确列出的界面资源；配置 JSON、源码、数据库、浏览器资料、隐藏文件和目录均不能通过静态 URL 下载，即使已经登录。
- 图片选择、预览和发送限制在数据目录的 `images/` 中。请将旧图片移到此目录后重新选择；如需其他目录，请由服务器管理员设置 `BILIGO_IMAGE_ROOT`，不能在网页中扩大目录边界。跨目录路径、Windows 特殊路径和指向目录外的软链接/联接均被拒绝。Markdown 知识库读取与删除同样检查真实路径边界。
- 非只读管理接口检查会话 CSRF 令牌与请求来源；连续输错密码会暂时限制登录。`/health` 仅返回 `ok`，供容器健康检查使用。

对外提供服务时，请通过 HTTPS 反向代理访问，并设置 `BILIGO_COOKIE_SECURE=1`，确保浏览器只通过 HTTPS 发送会话凭证。使用反向代理时保留原始 `Host`，或将转发的 `Origin` 与应用收到的主机地址保持一致。代理应只转发应用端口，不要把项目目录或数据目录配置成可直接访问的静态站点目录。

这里的保护针对网页访问。平台 Cookies 仍作为运行凭据保存在服务器数据目录，应限制该目录的系统访问权限。如果旧服务曾对外开放并暴露配置文件，请在对应平台的账号安全设置中撤销旧登录会话，再重新登录；同时轮换可能泄露的 AI API Key 和邮件授权码。

## Windows 单文件 EXE

项目提供 PyInstaller 构建配置：

```bat
build_exe.bat
```

构建结果位于：

```text
dist/BiliGo_V3.2.2_Ultra.exe
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
python scripts/test_playwright_runtime.py
```

提交代码前，请确认没有加入本地配置、浏览器资料、数据库、日志或打包产物。

## 常见问题

### 浏览器平台提示未登录

先以非无头模式打开登录窗口并完成登录。如果平台验证页面有变化，清理该平台浏览器资料目录后重新登录；清理前请先备份需要保留的数据。

### 提示 `Executable doesn't exist` 或找不到 `chromium_headless_shell`

这是 Playwright 与浏览器版本不匹配，不能据此认定平台登录失效。新版会按当前 Python 环境所需的版本校验 Chromium 和 Headless Shell，优先使用匹配的项目目录或系统缓存；缺失时安装到当前配置的浏览器目录。浏览器运行异常会保留账号登录信息。

Windows 源码运行推荐使用 `start.bat`，或明确使用项目环境：`.\.venv\Scripts\python.exe app.py`。若手动安装浏览器，请使用同一个 Python 执行 `.\.venv\Scripts\python.exe -m playwright install chromium`，避免全局 Python 和项目环境使用不同版本。EXE 缺少内置浏览器时会提示重新打包，不会把 EXE 当成 Python 反复调用安装命令。

### B 站出现 HTTP 412

暂停监控，在浏览器中手动访问 B 站消息页面并完成验证，然后增加检测和发送间隔。确认每个账号使用独立 `im_dev_id`，不要同时高频发送。

### AI 已配置但没有回复

确认目标平台的 AI 开关和平台监控均已启动，并检查模型名称、Base URL、API Key、账户额度及日志。仅保存 AI 配置不会自动启动平台监控。

### Docker 中浏览器平台无法启动

基础镜像不包含 Chromium，请改用 `biligo:playwright` 镜像，并保证 `/data` 可写。

### 为什么 B 站评论没有图片回复

V3 Ultra 已移除 B 站评论图片回复，评论默认回复和关键词规则统一为文字，减少上传失败和平台兼容问题。B 站私信仍可使用图片回复。

## 更新日志

### V3.2.2 Ultra（2026-10-25）

- 完善初始密码显示、首次强制改密与 8 位密码设置，增加本机密码重置入口。
- 重做登录和密码设置页，统一明暗模式、手机布局、密码显隐和提交反馈；顶部工具栏仅保留紧凑的“面板安全”入口。
- 修复 Playwright 与 Chromium / Headless Shell 版本不匹配，以及浏览器异常被误判为登录失效的问题。
- 运行配置不再纳入代码仓库；首次运行从无凭据模板生成配置，升级保留已有账号和用户数据。

### V3.2.1 Ultra（2026-10-25）

- 修复任意文件下载与目录越界，静态资源改为白名单，图片及知识库操作检查真实路径边界。
- 增加面板密码、设备独立会话、30 天自动登录、密码修改和退出撤销，以及登录重试限制与 CSRF 校验。
- 单文件 EXE 包含登录页及内置 Chromium；更新界面、配置导出与 Windows 文件属性中的版本信息。
- 安装包仅包含无凭据默认配置，不打包本机平台 Cookies、账号配置或登录会话。

### V3.2 Ultra（2026-09-25）

修复 EXE 重启后配置丢失问题，用户数据迁移至 `%APPDATA%\\BiliGo` 持久化目录。

### V3.1 Ultra（2026-09-13）

在 V3 Ultra 基础上继续迭代，完善视频号私信、本地 Web UI 访问控制与 Playwright 便携部署体验。

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
