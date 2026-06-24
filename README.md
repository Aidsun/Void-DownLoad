<h1 align="center">
  <img src="https://img.icons8.com/fluency/96/download--v1.png" width="80" alt="快抓">
  <br>
  快抓 · Void-DownLoad
</h1>


<p align="center">
  <strong>宝宝专用的网页资源嗅探下载器</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/GUI-PySide6_/_Qt6-green?logo=qt" alt="PySide6">
  <img src="https://img.shields.io/badge/Engine-Playwright-orange?logo=playwright" alt="Playwright">
  <img src="https://img.shields.io/badge/License-MIT-lightgrey" alt="License">
</p>

---

## 📖 简介

快抓是一款**桌面端网页资源嗅探下载工具**，基于 Playwright 无头浏览器技术，能够自动提取网页中隐藏的视频、图片、PDF、文档、音频和压缩包链接，并支持多分类筛选、批量并发下载。

### ✨ 特性

- 🔍 **智能嗅探** — Playwright 驱动 Chromium，支持 JavaScript 渲染页面（含 jwplayer 等视频播放器）
- 🎬 **多类型支持** — 视频、图片、PDF、文档、音频、压缩包自动分类识别
- 🚀 **并发下载** — 3 线程并发，单文件 >100 MB/s，支持进度实时展示
- 🎨 **蓝白主题 UI** — 圆角边框、自定义标题栏、瀑布流卡片布局
- 📥 **批量操作** — 全选 / 分类筛选 / 单选，一键批量下载
- 📊 **进度弹窗** — 实时速度、百分比、状态表格，一目了然
- 💾 **可自定义保存路径** — 支持任意目录，默认桌面 `VoidDownloader/`

---

## 📸 界面预览

<p align="center">
  <em>（运行截图将在此处展示）</em>
</p>

---

## 🔧 技术栈

| 层 | 技术 |
|---|---|
| 语言 | Python 3.10+ |
| GUI 框架 | PySide6 (Qt 6) |
| 浏览器引擎 | Playwright (Chromium) |
| 打包 | PyInstaller (onedir 目录分发) |
| 样式 | QSS (类 CSS) |

---

## 🚀 快速开始

### 方式一：Python 直接运行

```bash
# 1. 克隆仓库
git clone https://github.com/Aidsun/Void-DownLoad.git
cd Void-DownLoad

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动（确保系统已安装 Chrome 或 Edge）
python Void-DownLoad.py
```

### 方式二：打包 .exe 分发版（Windows）

```bash
# 确保已安装 PyInstaller
pip install pyinstaller

# 一键打包
pyinstaller Void-DownLoad.spec --clean --noconfirm

# 产物: dist/Void-DownLoad/ 目录 (~215MB)
# 打 zip 分发即可，解压运行 Void-DownLoad.exe
```

---

## 📁 项目结构

```
Void-DownLoad/
├── Void-DownLoad.py       # 🔌 入口脚本
├── Void-DownLoad.spec     # 📦 PyInstaller 打包配置
├── build_exe.bat          # 🏗  Windows 一键打包脚本
├── .gitignore
├── README.md
├── requirements.txt       # (见下方)
└── src/
    ├── __init__.py        # 包声明 + 版本号
    ├── gui.py            # 主窗口 (MainWindow, DownloadProgressDialog)
    ├── widgets.py        # 自定义组件 (MediaItemWidget, TitleBar, ...)
    ├── workers.py        # 后台线程 (ExtractWorker, DownloadWorker)
    ├── core.py           # 核心逻辑 (MediaItem, download_simple, 嗅探, ...)
    └── style.qss         # QSS 样式表 (蓝白主题)
```

---

## 📦 依赖

创建 `requirements.txt`：

```txt
PySide6>=6.5.0
playwright>=1.40.0
```

---

## 🖥️ 系统要求

- **操作系统**: Windows 10/11 x64
- **Python**: 3.10 或更高
- **磁盘空间**: 系统需安装 Chrome 或 Edge 浏览器（用于页面嗅探）
- **打包后目录大小**: ~215MB，EXE 仅 3.1MB（无需 Python 环境）

---

## ⚡ 优化记录

| 版本 | 改动 | EXE 大小 | 启动耗时 |
|------|------|----------|----------|
| v1 | 初始版本（内置 Chromium 400MB + onefile） | 264 MB | 5-10s |
| v1.1 | 移除内置 Chromium，改用系统 Chrome/Edge | 81 MB | 16s |
| v1.2 | 切换为 onedir 目录分发，免除解压 | 3.1 MB | **3.7s** ✅ |

> 💡 **核心优化**：不再将 Chromium 浏览器打包进 EXE，启动时也不需要解压。
> 系统优先使用 Google Chrome → Microsoft Edge → Playwright 自带 Chromium。

---

## 🧪 支持的网页类型

- Bosch-PT 产品页 (`bosch-pt.com.cn` / `mycliplister.com`)
- jwplayer 嵌入式播放器
- 标准 `<video>` / `<audio>` / `<a>` 标签页面
- 任何 Chromium 可渲染的动态页面

---

## 🛠️ 开发

```bash
# 语法检查
python -c "import py_compile; py_compile.compile('src/gui.py', doraise=True)"

# 快速测试单个模块
python -c "from src.core import MediaItem; print(MediaItem)"

# 打包
build_exe.bat
```

---

## 📄 License

MIT © [Aidsun](https://github.com/Aidsun)

---

<p align="center">
  <sub>Made with ❤️ for 宝宝</sub>
</p>
