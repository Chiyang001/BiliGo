# BiliGo - B站私信和评论自动回复系统

<div align="center">

![Version](https://img.shields.io/badge/version-2.1-blue.svg)
![Python](https://img.shields.io/badge/python-3.7+-green.svg)
![License](https://img.shields.io/badge/license-MIT-orange.svg)

一个功能强大的 B站（Bilibili）私信和评论自动回复工具，支持关键词匹配、图片回复、关注者欢迎等多种功能。

[功能特性](#功能特性) • [快速开始](#快速开始) • [使用教程](#使用教程) • [常见问题](#常见问题) • [更新日志](#更新日志)

</div>

---

## 📖 目录

- [功能特性](#功能特性)
- [系统要求](#系统要求)
- [快速开始](#快速开始)
- [详细配置](#详细配置)
- [使用教程](#使用教程)
- [常见问题](#常见问题)
- [注意事项](#注意事项)
- [更新日志](#更新日志)
- [联系方式](#联系方式)
- [开源协议](#开源协议)

---

## ✨ 功能特性

### 🔥 核心功能

#### 私信自动回复
- ✅ **关键词匹配回复** - 支持多关键词匹配，智能识别用户消息
- ✅ **文字/图片回复** - 支持发送文字消息或图片消息
- ✅ **默认回复** - 未匹配关键词时自动发送默认回复
- ✅ **仅回复新消息** - 可选择只回复程序启动后的新消息
- ✅ **回复次数限制** - 防止对同一用户重复回复，避免骚扰

#### 评论自动回复
- ✅ **视频评论监控** - 自动监控最新视频的评论
- ✅ **关键词匹配** - 根据评论内容智能回复
- ✅ **独立配置** - 评论系统与私信系统完全独立

#### 关注者管理
- ✅ **新关注欢迎** - 自动向新关注者发送欢迎消息
- ✅ **取消关注告别** - 检测到取消关注时发送告别消息
- ✅ **重复关注检测** - 支持检测用户重复关注行为
- ✅ **智能间隔控制** - 默认5分钟检查间隔，避免触发风控

### 🎯 高级特性

- 🚀 **极速响应** - 0.05秒消息检测间隔，快速响应用户
- 🔄 **自动重启** - 长时间无消息时自动重启，保持系统稳定
- 📊 **实时日志** - 详细的运行日志，支持按类型筛选
- 🎨 **现代化界面** - 响应式设计，支持移动端访问
- 🔐 **安全可靠** - 本地运行，数据安全有保障
- 📁 **规则导入导出** - 支持批量导入导出关键词规则

---

## 💻 系统要求

- **Python**: 3.7 或更高版本
- **操作系统**: Windows / Linux / macOS
- **网络**: 稳定的网络连接
- **浏览器**: Chrome / Firefox / Edge（用于访问 Web 界面）

---

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/Chiyang001/BiliGo.git
cd BiliGo
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

如果没有 `requirements.txt`，手动安装以下依赖：

```bash
pip install flask requests
```

### 3. 运行程序

```bash
python app.py
```

### 4. 访问界面

打开浏览器访问：`http://localhost:5000`

### 5. 配置登录信息

1. 在浏览器中登录 B站账号
2. 按 `F12` 打开开发者工具
3. 切换到 `Application` 或 `存储` 标签
4. 在 `Cookies` 中找到 `SESSDATA` 和 `bili_jct`
5. 复制这两个值到 BiliGo 的配置页面

---

## ⚙️ 详细配置

### 私信回复配置

#### 基础设置
- **默认回复开关**: 启用后，未匹配关键词的消息会收到默认回复
- **默认回复内容**: 设置默认回复的文字或图片
- **仅回复新消息**: 只回复程序启动后收到的消息
- **单用户最大回复次数**: 防止对同一用户重复回复（建议 3-5 次）

#### 关键词规则
- **规则名称**: 便于管理的规则标识
- **关键词**: 支持多个关键词，用逗号分隔（如：你好，您好，hi）
- **回复内容**: 匹配成功后发送的内容
- **回复类型**: 文字或图片
- **启用状态**: 可随时启用/禁用规则

#### 时间间隔配置
- **消息监测间隔**: 0.05 秒（推荐），越小响应越快
- **发送等待间隔**: 1 秒以上（推荐），避免触发风控
- **自动重启间隔**: 300 秒（5分钟），无消息时自动重启

### 关注者管理配置

#### 新关注欢迎
- **欢迎消息**: 向新关注者发送的欢迎内容
- **消息类型**: 支持文字或图片
- **检查间隔**: 最低 5 分钟（300秒），建议 10 分钟以上

#### 取消关注告别
- **告别消息**: 向取消关注者发送的告别内容
- **消息类型**: 支持文字或图片

⚠️ **重要提示**: 关注者检查间隔过短可能触发 B站风控，建议设置为 10 分钟以上！

### 评论回复配置

- **评论检查间隔**: 30 秒（推荐）
- **评论回复延迟**: 2 秒以上
- **仅回复新评论**: 只回复程序启动后的新评论
- **关键词规则**: 与私信规则类似，独立配置

---

## 📚 使用教程

### 视频教程

👉 [点击观看 B站视频教程](https://www.bilibili.com/video/BV1F8e4z7Eae/)

### 文字教程

#### 第一步：获取登录凭证

1. 在浏览器中登录 B站
2. 按 `F12` 打开开发者工具
3. 找到 `Application` → `Cookies` → `https://www.bilibili.com`
4. 复制 `SESSDATA` 和 `bili_jct` 的值

#### 第二步：配置系统

1. 在 BiliGo 界面粘贴 `SESSDATA` 和 `bili_jct`
2. 点击"保存登录配置"
3. 配置默认回复（可选）
4. 添加关键词规则

#### 第三步：添加关键词规则

1. 点击"添加新规则"
2. 填写规则名称（如：打招呼）
3. 填写关键词（如：你好，您好，hi）
4. 填写回复内容
5. 选择回复类型（文字/图片）
6. 点击"保存规则"

#### 第四步：启动监控

1. 点击"开始监控"按钮
2. 系统开始自动监控私信
3. 在日志页面查看运行状态

---

## ❓ 常见问题

### Q1: 提示"登录状态失效"怎么办？

**A**: 重新获取 `SESSDATA` 和 `bili_jct`，B站的登录凭证会定期过期。

### Q2: 为什么没有自动回复？

**A**: 检查以下几点：
- 登录配置是否正确
- 监控是否已启动
- 关键词规则是否启用
- 查看日志页面是否有错误信息

### Q3: 如何避免触发 B站风控？

**A**: 
- 发送间隔设置为 1 秒以上
- 关注者检查间隔设置为 10 分钟以上
- 不要频繁修改配置
- 单用户回复次数限制在 3-5 次

### Q4: 可以同时监控私信和评论吗？

**A**: 可以！私信和评论系统完全独立，可以同时启动。

### Q5: 图片回复不成功怎么办？

**A**: 
- 确保图片文件存在且路径正确
- 图片大小不超过 20MB
- 支持的格式：jpg、png、gif、bmp、webp

### Q6: 程序长时间运行后出现异常？

**A**: v2.1 版本已优化：
- 自动重启机制
- 内存清理优化
- 异常恢复机制
- 如仍有问题，可手动重启程序

### Q7: 如何部署到服务器？

**A**: 
```bash
# 使用 nohup 后台运行
nohup python app.py > biligo.log 2>&1 &

# 或使用 screen
screen -S biligo
python app.py
# 按 Ctrl+A+D 退出 screen
```

### Q8: 支持多账号吗？

**A**: 当前版本不支持多账号，每个实例只能配置一个 B站账号。

---

## ⚠️ 注意事项

### 使用规范

1. **遵守 B站规则**: 不要发送违规内容，不要骚扰用户
2. **合理使用**: 不要过度频繁地发送消息
3. **保护隐私**: 不要泄露 `SESSDATA` 和 `bili_jct`
4. **风控预防**: 严格遵守推荐的时间间隔设置

### 安全建议

- 🔒 定期更换登录凭证
- 🔒 不要在公共场合展示配置信息
- 🔒 建议在本地或私有服务器运行
- 🔒 定期备份关键词规则

### 免责声明

本工具仅供学习交流使用，使用本工具产生的任何后果由使用者自行承担。请遵守 B站用户协议和相关法律法规。

---

## 📝 更新日志

### v2.1 (2025-11-22)

#### 🎉 新增功能
- ✨ 添加"检查更新"按钮，快速跳转到 GitHub Releases
- ✨ 添加"使用教程"按钮，快速访问 B站视频教程
- ✨ 显示当前版本号（v2.1）

#### 🔧 优化改进
- 🚀 修复长时间运行后监控循环异常的问题
- 🚀 优化关注者检测逻辑，移除重复 API 调用
- 🚀 关注者检查间隔默认改为 5 分钟，最低 5 分钟
- 🚀 添加健康检查机制，自动检测并修复异常状态
- 🚀 优化内存管理，减少长时间运行的内存占用
- 🚀 改进异常处理和恢复机制

#### 🐛 Bug 修复
- 🔨 修复全局变量声明导致的语法错误
- 🔨 修复关注者检测中的重复验证问题
- 🔨 修复自动重启时的状态初始化问题

### v2.0
- 🎉 全新的 Web 界面
- 🎉 支持评论自动回复
- 🎉 支持关注者管理
- 🎉 添加实时日志系统

### v1.0
- 🎉 基础私信自动回复功能
- 🎉 关键词匹配系统
- 🎉 图片回复支持

---

## 📞 联系方式

- **QQ**: 3083248889
- **GitHub**: [https://github.com/Chiyang001/BiliGo](https://github.com/Chiyang001/BiliGo)
- **Issues**: [提交问题](https://github.com/Chiyang001/BiliGo/issues)

如有问题或建议，欢迎通过以上方式联系我！

---

## 🌟 Star History

如果这个项目对你有帮助，请给个 Star ⭐ 支持一下！

---

## 📄 开源协议

本项目采用 [MIT License](LICENSE) 开源协议。

```
MIT License

Copyright (c) 2025 Chiyang001

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 🙏 致谢

感谢所有使用和支持 BiliGo 的用户！

---

<div align="center">

**[⬆ 回到顶部](#biligo---b站私信和评论自动回复系统)**

Made with ❤️ by [Chiyang001](https://github.com/Chiyang001)

</div>


