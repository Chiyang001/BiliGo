# BiliGo for Linux

本目录属于独立分支 `Linux`。Windows 主程序继续在原 `BiliGo` 目录的 `main` 分支维护。
Linux 的改动只保存在此分支，不自动合并或上传到主分支。

## 环境与安装

### Windows 本机通过 SSH 一键部署（无需 VNC）

本机在本项目目录执行，`my-server` 替换为 SSH 别名或 `user@服务器公网地址`：

```powershell
# 首次部署：安装依赖、启用后台服务、建立隧道、打开本机浏览器、显示初始密码并持续输出日志。
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy-ssh.ps1 -Server my-server

# 后续连接：不上传、不安装、不重启服务，不改变密码或平台登录态。
powershell -NoProfile -ExecutionPolicy Bypass -File .\connect-ssh.ps1 -Server my-server
```

前提：本机 Windows PowerShell 5.1 / PowerShell 7，已有 OpenSSH 的 `ssh` 和 `scp`；
服务器为 Ubuntu 24.04 或 Debian 12，启用 systemd，使用 root 或具有免密 sudo 权限的管理员连接。
SSH 服务需允许 TCP 转发。部署入口先检查免密登录；已经可用时直接继续。
首次尚未免密时，会在当前终端通过 OpenSSH 提示输入服务器的 SSH 登录密码（输入不回显），
将本机公钥追加到登录用户的 `~/.ssh/authorized_keys`，保留已有公钥并避免重复添加，随后验证免密登录。
验证成功后自动继续部署，后续 SSH/SCP 和连接脚本均使用 BatchMode，不再询问服务器密码。
脚本不读取或保存服务器密码，不上传私钥，不修改服务器 SSH 服务配置，也不创建备份。
服务器如禁用密码登录，需先通过服务器控制台添加公钥；普通用户仍需免密 sudo，脚本不会配置 sudo 权限。
首次连接接受新主机密钥，已有密钥变更会被拒绝；连接超时、主机密钥错误不会触发公钥配置。

默认复用本机 `~/.ssh/id_ed25519`、`id_rsa` 或 `id_ecdsa` 中已有的首个私钥；
没有这些密钥时才创建新的 Ed25519 密钥 `~/.ssh/id_ed25519`，新密钥不设置口令以支持无人值守连接。
已有私钥不会被覆盖；也可用 `-IdentityFile` 指定已有私钥。若已有私钥本身设置了口令，
先将其加载进 ssh-agent，才能在后续步骤使用 BatchMode；脚本不会移除原有密钥口令。
SSH 认证失败时仅重用/生成本机密钥并追加公钥，免密验证未通过不会上传项目或开始部署。
不自动安装本机工具。

安装使用独立的 `biligo-ssh` 服务，与手动安装的 `biligo-linux` 服务分开；
源码 `/opt/biligo-ssh`、数据 `/var/lib/biligo-ssh`、浏览器缓存 `/var/cache/biligo-ssh`，
部署配置 `/etc/biligo-ssh/`。服务以非 root 用户运行，默认只监听服务器 `127.0.0.1:4999`。
本机浏览器打开 `http://127.0.0.1:5500`，通过 SSH 隧道访问；无需新增公网面板端口、域名或 HTTPS 代理。
关闭终端或按 Ctrl+C 会结束隧道及日志连接，服务仍继续运行，服务器重启后自动启动。

常用参数：

```powershell
# 自定义 SSH 端口、私钥和本机端口；后续连接使用相同 SSH 参数。
.\deploy-ssh.ps1 -Server user@server -Port 2222 -IdentityFile "$env:USERPROFILE\.ssh\id_ed25519" -LocalPort 5501
.\connect-ssh.ps1 -Server user@server -Port 2222 -LocalPort 5501

# 默认 Auto 已优先国内镜像；China 固定国内源，不回退官方。只部署、不持续连接。
.\deploy-ssh.ps1 -Server my-server -Mirror China -DeployOnly

# CI/无人值守运行：尚未免密时立即报错，不弹出服务器密码提示。
.\deploy-ssh.ps1 -Server my-server -NonInteractive -DeployOnly

# 自定义 PyPI，或服务器可访问的 HTTP(S) 下载代理。
.\deploy-ssh.ps1 -Server my-server -PipIndex https://pypi.tuna.tsinghua.edu.cn/simple
.\deploy-ssh.ps1 -Server my-server -Proxy http://127.0.0.1:7890

# 本机已有 5500 或服务器已有 4999 服务时分别更换端口；后续连接自动读取远端端口。
.\deploy-ssh.ps1 -Server my-server -RemotePort 5502 -LocalPort 5503

# 保持隧道但不跟随日志；-NoBrowser 禁止自动打开本机浏览器。
.\connect-ssh.ps1 -Server my-server -NoBrowser -NoFollow

# 忘记自定义面板密码时显式重置，撤销所有面板会话；普通连接绝不重置。
.\connect-ssh.ps1 -Server my-server -ResetPanelPassword
```

`-SshConfig 路径` 可指定独立的 OpenSSH 配置；未指定则沿用本机默认配置及跳板机等设置。
`-BrowserDownloadHost https://...` 可指定与当前 Playwright 版本匹配的 Chromium 下载站点。
没有稳定的下载源或可用代理时会报错，不会关闭 TLS 校验或使用未知公共代理。

镜像源策略：默认 `-Mirror Auto` 优先国内 HTTPS 镜像：APT 使用清华源，Python 使用清华 PyPI，
Chromium、Headless Shell 和 FFmpeg 使用 npmmirror 的 Playwright 镜像。
APT 更新、Python 包安装或浏览器下载失败后，仅该类回退官方源；Python 的选择独立于 APT，避免 APT 回退后 Python 也被带回官方。
`-Mirror Official` 固定官方源；`-Mirror China` 固定国内镜像，不回退官方。
自定义 `-PipIndex` 或 `-BrowserDownloadHost` 时只使用指定地址，不自动替换。
APT 设置只作用于本次部署及 Playwright 系统依赖安装，所选源记录在
`/etc/biligo-ssh/apt.sources.list`，不替换 `/etc/apt/sources.list*`。
Python 源、可选 Chromium 下载地址及代理保存在权限为 600 的 `service.env`，供本服务使用。
重复部署需再次传入需要保留的自定义源/代理参数。
已经启动的安装进程不会自动切换镜像，新策略在下一次执行部署脚本时生效；不要并发启动两次部署。
重复部署复用已安装的依赖和已完成的浏览器缓存，无需清空数据或缓存。
代理地址以服务器为视角，`127.0.0.1` 表示服务器自身；不会自动借用本机代理。
此代理用于安装下载及支持这些环境变量的 Python 请求，不会自动改变 Chromium 访问平台时的代理设置。
不修改网卡、DNS、路由、防火墙或 SSH 服务配置。

初始密码会在每次连接时从服务器认证库只读显示；设置自定义密码后只显示“已设置”，无法恢复其明文。
实时日志通过 SSH 跟随 systemd journal，只显示连接后的新记录，不回放可能包含旧初始密码的历史日志。
不将密码写入本机日志文件或访问 URL。上传包仅包含源码、界面资源和无凭据默认模板，排除本机运行配置、
账号资料、数据库、虚拟环境及 Git 内容。重复部署会短暂停服、覆盖源码及更新依赖，保留独立数据目录；
失败时报告错误，不自动备份、创建快照或回滚。

**此模式完全不安装或使用 VNC/noVNC，也不配置远程桌面。** B 站面板内扫码/API 功能可以使用；
抖音、小红书等平台需要服务器图形浏览器交互的首次登录、验证码，仍需要有效桌面和操作途径。
SSH 面板隧道不传输浏览器窗口，不能在无图形环境中代替这些操作；已有有效登录态可运行无头监控。
ARM64 支持安装路径选择，尚需实机验证。Ubuntu 22.04 的默认 Python 不满足要求，此自动部署入口会拒绝该系统。

常用服务器维护命令（通过 SSH 执行）：

```bash
sudo systemctl status biligo-ssh
sudo systemctl restart biligo-ssh
sudo systemctl stop biligo-ssh
sudo journalctl -u biligo-ssh -n 80 --no-pager
```

本机 SSH 部署验证（2026-11-01）：在独立 WSL Ubuntu 24.04 / x86_64 测试目标中，
使用临时 SSH 密钥、独立 sshd 监听端口及合成账号数据，实际运行了 Windows 部署/连接脚本。
官方源及清华 APT/PyPI 源安装、SCP 校验、回环监听、非 root 服务、面板初始登录与改密、
实时日志、断开后服务持续运行及日志进程清理、重连、自定义端口、显式密码重置、
重复部署保留认证库和数据均通过。PowerShell 5.1 和 7 连接通过；自动打开浏览器的调用在
隧道健康后触发，并核对了 URL（测试替换了系统浏览器启动器，未启动用户浏览器）。
Chromium 真实无头启动通过，现有 37 项回归和新增 4 项认证显示检查通过，
两个 PowerShell 版本的打包、中文/长文件名、凭据排除及参数检查通过。
源码上传包通过 .NET 生成 UTF-8 PAX tar.gz，不依赖 Windows tar 的区域设置或本机 Python。
后续加入首次自动配置公钥：PowerShell 5.1 / 7 均通过真实 OpenSSH 密码认证、生成并安装公钥、
免密验证及再次运行不提示密码的完整链路；使用临时 Linux 账号和仅供测试的 AskPass 提供合成密码，
未使用真实服务器密码。新增公钥追加、重复跳过、权限和软链接边界检查后，该测试文件共 8 项检查通过。
另验证了免密已就绪时跳过配置、网络错误不触发密码提示、`-NonInteractive` 立即失败及免密验证失败时停止。
国内镜像优先策略另有 8 项隔离检查，覆盖三类源的优先级、失败回退、自定义覆盖、固定模式和回退后清除浏览器镜像设置。
本机 Ubuntu 实际下载验证通过：清华源下载匹配版本的 Playwright wheel（48.5 MB，约 3.3 秒），
npmmirror 全新下载 Chromium、Headless Shell、FFmpeg，并成功启动无头 Chromium。
上述时间仅代表本机测试网络，不代表远程服务器的下载速度；测试缓存均位于独立临时目录并已清理。
可选实际下载检查：使用已安装 Playwright 的 Linux Python 执行 `python scripts/test_download_sources.py --smoke-downloads`，
会在临时目录下载匹配版本的 Playwright wheel 和浏览器，并验证 Chromium 无头启动，完成后清理临时下载。
测试未使用真实平台账号，未连接或修改用户远程服务器；测试服务完成后清理。
Debian 12、ARM64、无 CA 证书的极简系统及指定代理仍需对应环境验证。

本机可重跑的独立检查（检查脚本需要 Python 标准库读取并验证归档；部署本身不需要本机 Python）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test_ssh_deployment.ps1
python .\scripts\test_ssh_deployment.py
```

Linux 可执行 `python3 scripts/test_download_sources.py` 检查镜像策略，不连接外网或安装系统包。

### 手动安装

适配目标为 Ubuntu 22.04 / 24.04 和 Debian 12，使用 Python 3.11 或更新版本。
当前新增自动检查覆盖 Ubuntu 22.04 / 24.04；其他发行版和 ARM64 仍需实机验证。
浏览器依赖以 [Playwright 官方系统要求](https://playwright.dev/python/docs/intro#system-requirements)为准。

将此分支的源码放到 Linux 上，进入项目目录后执行：

```bash
# 以 Ubuntu 24.04 为例；其他版本安装对应的 Python 3.11+ 和 venv 包。
sudo apt-get update
sudo apt-get install -y python3 python3-venv
bash install_linux.sh --with-deps
bash start.sh
```

安装脚本会创建独立的 `.venv-linux`，安装 Python 依赖、Chromium 及其系统库。
`--with-deps` 安装系统库时可能需要 sudo；已经安装系统库时可执行 `bash install_linux.sh`。
如系统默认 Python 低于 3.11，先安装较新版本，再用 `PYTHON_BIN=python3.11 bash install_linux.sh --with-deps`。
安装和运行应使用同一普通用户，系统库安装步骤按提示提权即可。

面板地址为 `http://服务器地址:4999`。初始密码显示在启动终端，首次登录后必须修改。
启动脚本支持含空格的项目目录；无需先激活虚拟环境，也可以从其他目录调用。

## 与 Windows 的隔离

| 内容 | Linux 默认位置 |
| --- | --- |
| Python 虚拟环境 | 项目目录下 `.venv-linux/` |
| 配置、账号、规则、数据库与浏览器登录资料 | `${XDG_DATA_HOME:-$HOME/.local/share}/biligo-linux/` |
| Chromium 缓存 | `${XDG_CACHE_HOME:-$HOME/.cache}/biligo-linux/ms-playwright/` |

`start.sh` 和 `install_linux.sh` 共享上述默认路径。可用 `BILIGO_DATA_DIR`、`BILIGO_VENV_DIR`、
`PLAYWRIGHT_BROWSERS_PATH` 覆盖；相对路径按项目目录解析。数据目录首次创建时使用受限权限。
这些入口不会自动读取或迁移 Windows 账号数据，也不会自动创建备份或快照。
不要让 Windows 和 Linux 实例共用数据目录或浏览器 profile。
若绕过脚本直接运行 `python app.py`，仍沿用原有路径行为，请自行设置 `BILIGO_DATA_DIR`。

常用命令：

```bash
PORT=5000 bash start.sh
BILIGO_OPEN_BROWSER=0 bash start.sh
bash start.sh --version
bash start.sh --reset-panel-password
```

重置密码时必须使用服务实际采用的同一个数据目录。更改端口后，访问地址也要相应修改。

## 桌面登录与无桌面服务器

B 站的 Cookie/API 功能以及已有有效登录态的无头监控可以在无桌面环境运行。
抖音、小红书、微博、闲鱼、视频号等平台的首次登录或人工验证需要操作服务器上的浏览器窗口。
远程访问 Web 面板不会把这个浏览器窗口传到本地电脑。

- Linux 桌面：从桌面终端运行 `bash start.sh`，在该桌面的浏览器完成平台登录。
- 服务器：先建立可操作的 VNC/远程桌面会话，在该会话的终端运行安装及启动命令，再完成登录。
- 登录后可切换到无头监控。若之后使用 systemd，应让服务使用相同的数据目录、缓存和运行用户，
  并先停止桌面中运行的实例；同一个浏览器 profile 不能同时被两个进程使用。

Linux 的有界面 Chromium 需要有效的 X11 `DISPLAY`；Wayland 桌面需提供 XWayland。
只有 Xvfb 虚拟显示而没有远程桌面入口，无法让用户操作登录窗口。
缺少 `DISPLAY` 时，程序会说明图形登录条件，保留已有账号资料。
无桌面启动默认不自动打开面板浏览器；桌面启动默认打开，可以用 `BILIGO_OPEN_BROWSER=0` 关闭。

运行中的浏览器自动修复只下载用户级浏览器，不会自动执行 apt/sudo。
如果提示缺少系统库，停止服务后手动重新运行 `bash install_linux.sh --with-deps`。

## Linux Docker 部署

本分支提供独立 Compose 配置，使用单独的项目名、镜像名和数据卷，默认宿主机端口为 `5000`，
避免与原版的 `biligo` 容器及 `4999` 端口重名。安装 Docker 后执行：

```bash
docker compose -f docker-compose.linux.yml up -d --build
docker compose -f docker-compose.linux.yml logs -f
```

访问 `http://服务器地址:5000`；设置 `BILIGO_LINUX_PORT` 可以换端口。
容器内默认没有可操作的桌面，图形登录的条件同上，不能仅通过面板完成需要浏览器操作的登录。
不要用原版的 `docker-deploy.sh` 启动此配置；该脚本仍指向原有 Compose 文件。

## systemd 后台服务

模板在 `deploy/linux/biligo-linux.service`，默认源码路径为 `/opt/biligo-linux`。
先将此分支源码放到该路径，再执行以下命令；已有同名用户时跳过创建用户那一步。

```bash
sudo useradd --system --user-group --home-dir /var/lib/biligo-linux --shell /usr/sbin/nologin biligo
sudo install -d -m 700 -o biligo -g biligo /var/lib/biligo-linux /var/cache/biligo-linux
sudo chown -R biligo:biligo /opt/biligo-linux

# 系统库由管理员安装，浏览器文件由服务用户安装，避免缓存目录和文件属主不一致。
sudo python3 -m venv /opt/biligo-linux/.venv-linux
sudo chown -R biligo:biligo /opt/biligo-linux/.venv-linux
sudo -u biligo /opt/biligo-linux/.venv-linux/bin/python -m pip install -r /opt/biligo-linux/requirements.txt
sudo /opt/biligo-linux/.venv-linux/bin/python -m playwright install-deps chromium
sudo -u biligo env HOME=/var/lib/biligo-linux \
  BILIGO_DATA_DIR=/var/lib/biligo-linux \
  PLAYWRIGHT_BROWSERS_PATH=/var/cache/biligo-linux/ms-playwright \
  bash /opt/biligo-linux/install_linux.sh

sudo install -m 644 /opt/biligo-linux/deploy/linux/biligo-linux.service /etc/systemd/system/biligo-linux.service
sudo systemctl daemon-reload
sudo systemctl enable --now biligo-linux
sudo journalctl -u biligo-linux -n 60 --no-pager
```

部署路径不同时修改模板的 `WorkingDirectory` 和 `ExecStart`。模板不自带远程桌面。
初始密码在 journal 中查看。停服用 `sudo systemctl stop biligo-linux`；日志用 `sudo journalctl -u biligo-linux -f`。

可选配置文件 `/etc/biligo-linux.env` 使用 systemd 的 `KEY=value` 格式，不是 Shell 脚本：

```ini
PORT=4999
BILIGO_OPEN_BROWSER=0
```

需要服务连接既有远程桌面时，由管理员在配置文件中填入该用户实际可访问的 `DISPLAY` 和 `XAUTHORITY`，
同时保持桌面会话运行。不要用 `xhost +` 开放显示权限。
原 README 的面板密码、HTTPS 反向代理和 `BILIGO_COOKIE_SECURE` 配置继续适用。

## 验证与分支维护

```bash
.venv-linux/bin/python scripts/test_linux_support.py
.venv-linux/bin/python scripts/test_playwright_runtime.py
.venv-linux/bin/python scripts/test_web_security.py
.venv-linux/bin/python scripts/test_linux_support.py --smoke-server

# 浏览器测试使用安装脚本的同一个缓存目录。
export PLAYWRIGHT_BROWSERS_PATH="${XDG_CACHE_HOME:-$HOME/.cache}/biligo-linux/ms-playwright"
.venv-linux/bin/python scripts/test_playwright_runtime.py --smoke-browser
.venv-linux/bin/python scripts/smoke_test_web_auth_ui.py

# 在有 DISPLAY 的桌面中验证五个平台浏览器模块；只打开本地测试页面。
.venv-linux/bin/python scripts/test_linux_support.py --smoke-desktop
```

`.github/workflows/linux.yml` 仅针对 Linux 分支推送、面向该分支的 PR 和手动触发运行，
检查 Ubuntu 上的安装、真实 Chromium 启动、面板登录及服务启动/退出。
工作流随分支推送后才会执行，未执行不能视为实机验证通过。

当前 Windows 开发机通过 Git worktree 隔离两个目录，二者共享 Git 历史但各自有独立工作文件。
在本目录运行 `git branch --show-current` 应显示 `Linux`。
发布此分支后，Linux 可单独克隆：

```bash
git clone --branch Linux --single-branch https://github.com/Chiyang001/BiliGo.git biligo-linux
```

只需部署源码时，也可从已提交的 Linux 分支用 `git archive` 导出；不要把 worktree 的 `.git` 指针当成独立仓库复制。
后续 Windows 更新需要在本分支单独审查、合入和验证，不自动同步运行数据。

## 本机 WSL 验证记录（2026-10-31）

已安装独立 WSL 2 实例 `Ubuntu-BiliGo`，发行版文件位于 `C:\WSL\Ubuntu-BiliGo`，默认用户为 `biligo`。
源码位于 Ubuntu 的 `/home/biligo/BiliGo`，从 `Linux` 分支传入，不包含 Windows 运行数据或 Git worktree 指针。
原 Windows `BiliGo` 项目的 `main` 分支保持不变，WSL 默认发行版仍为原来的 `docker-desktop`。

本次环境为 Ubuntu 24.04.5 LTS / x86_64、Python 3.12.3、Playwright 1.64.1、Chromium 156.0.8078.4，
使用 WSLg 的 `DISPLAY=:0` 和 systemd。

| 检查 | 结果 |
| --- | --- |
| Linux 安装脚本、独立虚拟环境和浏览器缓存 | 通过 |
| 启动与路径隔离、浏览器运行时、面板安全回归 | 37 项通过 |
| 真实 Chromium 无头启动 | 通过 |
| 抖音、小红书、微博、闲鱼、视频号浏览器模块的图形启动、切换无头模式、持久化测试 Cookie | 全部通过，仅使用本地测试页面 |
| 真实浏览器中的面板登录、改密、记住设备及初始密码流程 | 通过 |
| `start.sh` 启动、健康检查、未登录访问限制、退出清理 | 通过 |
| systemd 非 root 运行、目录权限、重启后面板凭据保持、停服 | 通过 |
| Windows 通过 localhost 访问 Ubuntu 的 5500 端口 | 通过 |

systemd 验证使用临时单元和独立数据目录，测试结束后已停服并清理，未设置开机自启。
未使用真实平台账号或发送消息，平台账号登录、实际收发和长期监控仍需后续验证；Docker 镜像本次未构建。
Ubuntu 22.04、Debian 12 和 ARM64 仍需分别实机验证。

在 Windows PowerShell 中启动已安装的 Linux 副本：

```powershell
wsl -d Ubuntu-BiliGo -u biligo --cd /home/biligo/BiliGo --exec env PORT=5500 BILIGO_OPEN_BROWSER=0 bash start.sh
```

然后访问 `http://localhost:5500`，初始密码在此终端显示，按 `Ctrl+C` 停止。
这个副本使用 Linux 自己的数据目录；后续 Windows 工作目录中的源码改动需要单独同步到 Ubuntu 副本。
如需以管理员身份管理 Ubuntu，可使用 `wsl -d Ubuntu-BiliGo -u root`；无需调整 Windows 版依赖。
