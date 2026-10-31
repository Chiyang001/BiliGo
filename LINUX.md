# BiliGo for Linux

本目录属于独立分支 `codex/linux-support`。Windows 主程序继续在原 `BiliGo` 目录的 `main` 分支维护。
Linux 的改动只保存在此分支，不自动合并或上传到主分支。

## 环境与安装

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
```

`.github/workflows/linux.yml` 仅针对 Linux 分支推送、面向该分支的 PR 和手动触发运行，
检查 Ubuntu 上的安装、真实 Chromium 启动、面板登录及服务启动/退出。
工作流随分支推送后才会执行，未执行不能视为实机验证通过。

当前 Windows 开发机通过 Git worktree 隔离两个目录，二者共享 Git 历史但各自有独立工作文件。
在本目录运行 `git branch --show-current` 应显示 `codex/linux-support`。
发布此分支后，Linux 可单独克隆：

```bash
git clone --branch codex/linux-support --single-branch https://github.com/Chiyang001/BiliGo.git biligo-linux
```

只需部署源码时，也可从已提交的 Linux 分支用 `git archive` 导出；不要把 worktree 的 `.git` 指针当成独立仓库复制。
后续 Windows 更新需要在本分支单独审查、合入和验证，不自动同步运行数据。
