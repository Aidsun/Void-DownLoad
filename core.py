"""
Void-DownLoad 核心模块
======================
从 bosch_dl.py 抽出,可被 GUI / CLI 复用。

公开 API:
    detect_media_kind(url) -> str      # 探测资源类型
    estimate_size(url) -> int | None   # HEAD 请求估大小
    extract_via_playwright(page_url) -> list[MediaItem]
    download_simple(url, dest) -> int
    list_chromium() -> str | None
"""

import asyncio
import os
import re
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Windows 终端 GBK 修正
if sys.platform == "win32":
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

# ============== 资源分类 ==============
VIDEO_EXTS = {"mp4", "webm", "mkv", "mov", "m4v", "avi", "flv", "ts", "m3u8", "mpd"}
IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "avif", "heic"}
AUDIO_EXTS = {"mp3", "wav", "flac", "aac", "ogg", "m4a", "wma"}
DOC_EXTS = {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "md", "rtf", "odt"}
ARCHIVE_EXTS = {"zip", "rar", "7z", "tar", "gz", "bz2", "xz"}

KIND_LABELS = {
    "video":   "🎬 视频",
    "image":   "🖼️ 图片",
    "audio":   "🎵 音频",
    "pdf":     "📕 PDF",
    "doc":     "📝 文档",
    "archive": "📦 压缩包",
    "web":     "🌐 网页",
    "other":   "🔗 其他",
}

def detect_media_kind(url: str, ctype: str = "") -> str:
    """从 URL 扩展名 + Content-Type 探测类型。"""
    path = re.split(r"[?&#]", url)[0].lower()
    ext = path.rsplit(".", 1)[-1] if "." in path else ""
    ctype = (ctype or "").lower()
    if ext in VIDEO_EXTS or "video" in ctype: return "video"
    if ext in IMAGE_EXTS or ctype.startswith("image/"): return "image"
    if ext in AUDIO_EXTS or "audio" in ctype: return "audio"
    if ext == "pdf" or "pdf" in ctype: return "pdf"
    if ext in DOC_EXTS: return "doc"
    if ext in ARCHIVE_EXTS: return "archive"
    if ext in ("html", "htm", "php", "asp", "aspx", "jsp") or "text/html" in ctype:
        return "web"
    return "other"

def kind_label(k: str) -> str:
    return KIND_LABELS.get(k, k)

# ============== 数据类 ==============
@dataclass
class MediaItem:
    url: str
    title: str = ""
    kind: str = "other"          # video / image / audio / pdf / doc / archive / web / other
    size: Optional[int] = None    # 字节; 未知则 None
    source_page: str = ""        # 哪个页面找到的
    selected: bool = False

    def display_name(self) -> str:
        if self.title:
            return self.title
        path = re.split(r"[?&#]", self.url)[0]
        name = path.rstrip("/").split("/")[-1] or "unnamed"
        # 解 URL 编码
        from urllib.parse import unquote
        return unquote(name)[:80]

    def size_str(self) -> str:
        if self.size is None: return "未知大小"
        return _human_size(self.size)

def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} PB"

# ============== 找 Chromium ==============
def find_chromium_exe() -> Optional[str]:
    """在 %LOCALAPPDATA%\\ms-playwright\\ 下找 chromium 可执行文件."""
    # 1) 优先用 PyInstaller/frozen 內嵌的 chromium (随 exe 打包的)
    bundled = _extract_bundled_chromium()
    if bundled:
        return bundled
    # 2) 用户系统上装好的
    pdir = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    if not pdir.exists():
        return None
    # 1) 普通 chromium
    for d in pdir.iterdir():
        if d.name.startswith("chromium-") and d.is_dir():
            for sub in (
                d / "chrome-win64" / "chrome.exe",
                d / "chrome-win" / "chrome.exe",
            ):
                if sub.exists():
                    return str(sub)
    # 2) headless shell
    for d in pdir.iterdir():
        if d.name.startswith("chromium_headless_shell-") and d.is_dir():
            for sub in (
                d / "chrome-headless-shell-win64" / "chrome-headless-shell.exe",
                d / "chrome-win" / "chrome.exe",
            ):
                if sub.exists():
                    return str(sub)
    return None

_BUNDLED_CHROMIUM_EXTRACTED = None  # cache

def _extract_bundled_chromium() -> Optional[str]:
    """从 PyInstaller 临时目录 / 开发环境 bundle/ 目录提取 chromium 到用户磁盘。"""
    global _BUNDLED_CHROMIUM_EXTRACTED
    if _BUNDLED_CHROMIUM_EXTRACTED:
        if Path(_BUNDLED_CHROMIUM_EXTRACTED).exists():
            return _BUNDLED_CHROMIUM_EXTRACTED
        _BUNDLED_CHROMIUM_EXTRACTED = None  # 被删了, 重提

    import sys as _sys
    meipass = getattr(_sys, "_MEIPASS", None)
    bundle_root = Path(meipass) if meipass else Path(__file__).resolve().parent.parent
    # 优先选目录形式 (包含全部 300+ 文件)
    chromium_dir_src = bundle_root / "bundle" / "chromium"
    chromium_exe_src = bundle_root / "bundle" / "chromium.exe"

    # 解到 %LOCALAPPDATA%\Void-DownLoad\chromium\
    dest_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "Void-DownLoad" / "chromium"
    dest_dir.mkdir(parents=True, exist_ok=True)

    if chromium_dir_src.is_dir() and (chromium_dir_src / "chrome.exe").exists():
        # 整个目录打包形式 (spec 里 datas=('bundle/chromium', 'bundle/chromium'))
        src_dir = chromium_dir_src
        src_chrome = src_dir / "chrome.exe"
        dest = dest_dir / "chrome.exe"
        if not dest.exists() or dest.stat().st_size != src_chrome.stat().st_size:
            import shutil
            if dest_dir.exists():
                shutil.rmtree(dest_dir, ignore_errors=True)
            shutil.copytree(src_dir, dest_dir)
        _BUNDLED_CHROMIUM_EXTRACTED = str(dest)
        return _BUNDLED_CHROMIUM_EXTRACTED
    elif chromium_exe_src.is_file():
        # 单文件形式 (备用)
        dest = dest_dir / "chrome.exe"
        if not dest.exists() or dest.stat().st_size != chromium_exe_src.stat().st_size:
            import shutil
            shutil.copy2(chromium_exe_src, dest)
        _BUNDLED_CHROMIUM_EXTRACTED = str(dest)
        return _BUNDLED_CHROMIUM_EXTRACTED
    return None

# ============== HEAD 估大小 ==============
def estimate_size(url: str, referer: str = "", timeout: int = 10) -> Optional[int]:
    """HEAD 请求拿 Content-Length, Range 请求 fallback."""
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          "AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/131.0.0.0 Safari/537.36")
    # 1) HEAD
    try:
        req = urllib.request.Request(url, method="HEAD", headers={
            "User-Agent": ua, "Referer": referer,
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            cl = r.headers.get("Content-Length")
            if cl:
                return int(cl)
    except Exception:
        pass
    # 2) Range GET 拿 1 字节 + Content-Range
    try:
        req = urllib.request.Request(url, method="GET", headers={
            "User-Agent": ua, "Referer": referer, "Range": "bytes=0-0",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            cr = r.headers.get("Content-Range")
            if cr:
                m = re.search(r"/(\d+)", cr)
                if m:
                    return int(m.group(1))
    except Exception:
        pass
    return None

# ============== Playwright 提取 ==============
URL_PATTERN = re.compile(r"^https?://(www\.)?bosch-pt\.com\.cn/", re.IGNORECASE)
POLL_TIMEOUT = 90

async def extract_via_playwright(page_url: str, log=None) -> list[MediaItem]:
    """打开页面, 触发 jwplayer, 提取所有可见媒体资源。"""
    from playwright.async_api import async_playwright

    items: list[MediaItem] = []

    chromium_exe = find_chromium_exe()
    launch_kwargs = dict(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--autoplay-policy=no-user-gesture-required",
        ],
    )
    if chromium_exe:
        launch_kwargs["executable_path"] = chromium_exe

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(**launch_kwargs)
        try:
            ctx = await browser.new_context(
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/131.0.0.0 Safari/537.36"),
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
                ignore_https_errors=True,
            )
            page = await ctx.new_page()
            page.set_default_timeout(60000)

            # 屏蔽广告 / 字体 / 跟踪
            async def route_handler(route):
                try:
                    req = route.request
                    rtype = req.resource_type
                    rurl = req.url
                    if rtype in ("image", "font") and "mycliplister" not in rurl:
                        await route.abort(); return
                    if any(x in rurl for x in (
                        "google-analytics", "googletagmanager",
                        "facebook", "doubleclick", "hotjar",
                        "qualtrics", "tealium",
                    )):
                        await route.abort(); return
                except Exception:
                    pass
                try:
                    await route.continue_()
                except Exception:
                    pass
            await page.route("**/*", route_handler)

            # 拦截所有 mycliplister / dlc 响应, 直接拿 mp4 URL
            captured: list[dict] = []

            def on_response(resp):
                try:
                    rurl = resp.url
                    if "mycliplister.com" in rurl and "type=source" in rurl:
                        captured.append({"url": rurl, "ctype": resp.headers.get("content-type", "")})
                except Exception:
                    pass
            page.on("response", on_response)

            # 导航
            try:
                await page.goto(page_url, wait_until="commit", timeout=20000)
            except Exception:
                pass

            # 等容器 + 滚动 + 点击
            try:
                await page.wait_for_selector(
                    '[id^="cliplister_video_"]',
                    state="attached", timeout=15000,
                )
                await page.evaluate(
                    "() => { const e = document.querySelector('[id^=\"cliplister_video_\"]');"
                    "if (e) e.scrollIntoView({block:'center'}); }"
                )
                await page.wait_for_timeout(500)
                await page.click('[id^="cliplister_video_"]', force=True, timeout=5000)
            except Exception:
                pass

            # 轮询 jwplayer.getPlaylist()
            t0 = time.time()
            playlist_info = None
            while time.time() - t0 < POLL_TIMEOUT:
                await page.wait_for_timeout(2000)
                info = await page.evaluate(
                    """() => {
                        if (!window.jwplayer) return null;
                        try {
                            const inst = (typeof jwplayer === 'function') ? jwplayer() : null;
                            if (!inst || !inst.getPlaylist) return null;
                            const pl = inst.getPlaylist();
                            if (pl && pl.length) {
                                const p = pl[0];
                                return {
                                    url: (p.sources && p.sources[0] && p.sources[0].file) || p.file,
                                    image: p.image,
                                    title: p.title,
                                };
                            }
                        } catch (e) { return {err: String(e)}; }
                        return null;
                    }"""
                )
                if info and isinstance(info, dict) and info.get("url"):
                    playlist_info = info
                    break

            if playlist_info:
                # 主视频
                _title = playlist_info.get("title") or ""
                items.append(MediaItem(
                    url=playlist_info["url"],
                    title=_title,
                    kind="video",
                    source_page=page_url,
                ))
                # 缩略图
                if playlist_info.get("image"):
                    _t = (_title + "_thumb").strip("_") if _title else "thumbnail"
                    items.append(MediaItem(
                        url=playlist_info["image"],
                        title=_t,
                        kind="image",
                        source_page=page_url,
                    ))

            # 加上网络拦截抓到的 (通常和 playlist 重复, 去重)
            for c in captured:
                if not any(i.url == c["url"] for i in items):
                    items.append(MediaItem(
                        url=c["url"],
                        title="cliplister_source",
                        kind=detect_media_kind(c["url"], c.get("ctype", "")),
                        source_page=page_url,
                    ))

            # 顺手扫一下页面里所有 <img>/<video>/<source> 的 src
            try:
                more = await page.evaluate(
                    """() => {
                        const out = [];
                        document.querySelectorAll('img[src]').forEach(el => {
                            if (el.src && !el.src.startsWith('data:')) {
                                out.push({url: el.src, kind: 'image'});
                            }
                        });
                        document.querySelectorAll('video source[src], video[src]').forEach(el => {
                            const u = el.src || el.getAttribute('src');
                            if (u) out.push({url: u, kind: 'video'});
                        });
                        document.querySelectorAll('a[href$=".pdf"], a[href$=".PDF"]').forEach(el => {
                            if (el.href) out.push({url: el.href, kind: 'pdf'});
                        });
                        return out;
                    }"""
                )
                for m in (more or []):
                    if not any(i.url == m["url"] for i in items):
                        items.append(MediaItem(
                            url=m["url"],
                            title="",
                            kind=m.get("kind", "other"),
                            source_page=page_url,
                        ))
            except Exception:
                pass

        finally:
            await browser.close()

    # 异步估大小 (并发 HEAD)
    if items:
        async def _head(it):
            try:
                loop = asyncio.get_event_loop()
                size = await loop.run_in_executor(
                    None, estimate_size, it.url, page_url, 10
                )
                it.size = size
            except Exception:
                pass
        await asyncio.gather(*[_head(it) for it in items])

    return items

# ============== 普通下载 ==============
def download_simple(url: str, dest: Path, referer: str = "",
                    progress_cb=None, chunk: int = 1024 * 1024) -> int:
    """下载文件, progress_cb(done, total) 可选.

    优化: 默认 1MB chunk (减少系统调用 4x), 
    设 TCP window 调优, 改用单次 urlopen 避免重连.
    """
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/131.0.0.0 Safari/537.36"),
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as r:
        total = int(r.headers.get("Content-Length") or 0)
        ctype = r.headers.get("Content-Type", "")
        if not dest.suffix and "mp4" in ctype.lower():
            dest = dest.with_suffix(".mp4")
        elif not dest.suffix and "image" in ctype.lower():
            ext = ".jpg" if "jpeg" in ctype.lower() else ".png"
            dest = dest.with_suffix(ext)
        with open(dest, "wb") as f:
            got = 0
            while True:
                buf = r.read(chunk)
                if not buf:
                    break
                f.write(buf)
                got += len(buf)
                if progress_cb:
                    progress_cb(got, total)
    return got

# ============== 入口 (CLI fallback) ==============
def main():
    url = sys.argv[1] if len(sys.argv) > 1 else input("Bosch-PT URL: ").strip()
    if not url:
        print("URL 不能为空", file=sys.stderr)
        return 1
    items = asyncio.run(extract_via_playwright(url))
    print(f"\n找到 {len(items)} 个资源:")
    for i, it in enumerate(items, 1):
        print(f"  [{i}] {kind_label(it.kind):8s} {it.display_name():50s}  {it.size_str():>12s}  {it.url[:80]}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
