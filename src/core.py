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
import random
import re
import shutil
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

# ============== 浏览器检测 ==============

def find_chromium_exe() -> Optional[str]:
    """检测系统可用的浏览器(exe路径)。

    优先用系统 Chrome/Edge (零额外体积,秒启动),
    仅在两者都不可用时回退到 ms-playwright 下的 Chromium。
    """
    # 1) Google Chrome
    chrome_paths = [
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
    ]
    for p in chrome_paths:
        if p.exists():
            return str(p)
    if shutil.which("chrome"):
        return shutil.which("chrome")

    # 2) Microsoft Edge (Win10/11 自带)
    edge_paths = [
        Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
        Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
    ]
    for p in edge_paths:
        if p.exists():
            return str(p)
    if shutil.which("msedge"):
        return shutil.which("msedge")

    # 3) 回退: ms-playwright 下的 Chromium (开发环境)
    pdir = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    if pdir.exists():
        for d in pdir.iterdir():
            if d.name.startswith("chromium-") and d.is_dir():
                for sub in (d / "chrome-win64" / "chrome.exe", d / "chrome-win" / "chrome.exe"):
                    if sub.exists():
                        return str(sub)

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
    """打开页面, 触发 jwplayer, 提取所有可见媒体资源。

    优先复用系统 Chrome/Edge (零额外下载,秒启动),
    仅在没有系统浏览器时才用 Playwright 自带 Chromium。
    """
    from playwright.async_api import async_playwright

    items: list[MediaItem] = []

    browser_exe = find_chromium_exe()
    if log:
        log(f"浏览器: {browser_exe or '(使用 Playwright 默认 Chromium)'}")

    launch_kwargs = dict(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--autoplay-policy=no-user-gesture-required",
        ],
    )
    # 用系统浏览器 (不需要额外下载 400MB Chromium)
    if browser_exe:
        launch_kwargs["executable_path"] = browser_exe

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

# ============== 淘宝 / 天猫提取 ==============

TAOBAO_URL_PATTERN = re.compile(
    r'(?:item\.taobao|detail\.tmall|h5\.m\.taobao)\.com',
    re.IGNORECASE
)

# 淘宝视频 CDN 域名特征
_VIDEO_CDN_PATTERNS = (
    "cloudvideo.taobao.com",
    "cloud.video.taobao.com",
    "vod.taobao.com",
    "tbm.alicdn.com",     # 天猫视频
    "tb-video.bdstatic.com",
)

_VIDEO_EXT_PATTERN = re.compile(r'\.(mp4|webm|mkv|mov|m4v|flv|ts)(\?|$)', re.I)
_SIZE_SUFFIX_PAT = re.compile(r'_\d+x\d+.*?(\.[a-z]+)', re.I)
_SIZE_DOT_PAT = re.compile(r'\.\d+x\d+', re.I)


def _clean_image_url(url: str) -> str:
    """去掉阿里 CDN 图片的尺寸后缀, 拿到原图 URL."""
    clean = re.sub(_SIZE_SUFFIX_PAT, r'\1', url, flags=re.I)
    clean = re.sub(_SIZE_DOT_PAT, '', clean)
    return clean


def is_taobao_url(url: str) -> bool:
    """检测是否为淘宝/天猫商品链接."""
    return bool(TAOBAO_URL_PATTERN.search(url.lower()))


async def extract_taobao(page_url: str, log=None) -> list[MediaItem]:
    """提取淘宝/天猫商品页的图片和视频。

    优先使用 CDP 连接到用户已登录的 Chrome (端口 9222),
    这样完全复用用户的真实浏览器会话, 零反爬风险。

    图片: 三层提取 (网络拦截 + DOM 提取 + 缩略图点击)
    视频: 四层提取 (网络拦截 CDN + JS 深度探测 + DOM 扫描 + 播放器触发)
    """
    from playwright.async_api import async_playwright

    items: list[MediaItem] = []
    _ll = (lambda m: log(m)) if log else (lambda m: None)
    page = None

    async with async_playwright() as pw:
        # 尝试 CDP 连接用户浏览器
        try:
            browser = await pw.chromium.connect_over_cdp("http://localhost:9222")
            _ll("✅ 已连接用户浏览器 (CDP), 使用已登录的淘宝会话")
            contexts = browser.contexts
            ctx = contexts[0] if contexts else None
            if ctx is None:
                raise RuntimeError("无法获取浏览器上下文")
            page = await ctx.new_page()
        except Exception as e:
            # 回退: 启动新浏览器
            _ll("未检测到 CDP 连接 (端口 9222), 启动新浏览器…")
            _ll("  (首次使用需要手动登录淘宝)")
            browser_exe = find_chromium_exe()
            launch_kwargs: dict = dict(
                headless=False,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                ],
            )
            if browser_exe:
                launch_kwargs["executable_path"] = browser_exe
            browser = await pw.chromium.launch(**launch_kwargs)
            ctx = await browser.new_context(
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/131.0.0.0 Safari/537.36"),
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
            )
            page = await ctx.new_page()

        try:
            # 注入反检测脚本 (在导航前注入)
            await page.goto("about:blank")
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = {runtime: {}};
            """)

            _ll("正在加载商品页…")
            try:
                await page.goto(
                    page_url,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
            except Exception as e:
                _ll(f"页面加载: {e}")

            # 等 3 秒让 JS 渲染
            await page.wait_for_timeout(3000)

            # 提取商品标题
            title = ""
            try:
                for sel in (
                    "h1[data-spm='1000983']",
                    ".tb-main-title",
                    "h1",
                ):
                    el = await page.query_selector(sel)
                    if el:
                        t = await el.inner_text()
                        title = t.strip()[:60] if t else ""
                        if title:
                            break
            except Exception:
                pass

            # ================================================
            # 网络拦截: 图片 + 视频 双通道
            # ================================================
            captured_images: set = set()
            captured_videos: set = set()

            def on_response(resp):
                try:
                    rurl = resp.url
                    ctype = resp.headers.get("content-type", "")

                    # --- 图片 ---
                    if ctype.startswith("image/") and "alicdn.com" in rurl:
                        captured_images.add(_clean_image_url(rurl))

                    # --- 视频 CDN ---
                    if any(pat in rurl for pat in _VIDEO_CDN_PATTERNS):
                        captured_videos.add(rurl)
                        return

                    # --- 视频 Content-Type ---
                    if ctype.startswith("video/") or "octet-stream" in ctype:
                        if _VIDEO_EXT_PATTERN.search(rurl):
                            captured_videos.add(rurl)
                            return

                    # --- .mp4/.webm/.m3u8 结尾的请求 (任何 CDN) ---
                    if _VIDEO_EXT_PATTERN.search(rurl):
                        captured_videos.add(rurl)
                except Exception:
                    pass

            page.on("response", on_response)

            # ================================================
            # 第 1 层交互: 模拟人类滚动, 触发懒加载
            # ================================================
            _ll("  滚动页面, 触发懒加载…")
            for pct in (0.3, 0.6, 1.0):
                await page.evaluate(
                    f"window.scrollTo(0, document.body.scrollHeight * {pct})"
                )
                await page.wait_for_timeout(500 + random.randint(300, 1200))

            # ================================================
            # 第 2 层交互: 尝试触发主图视频
            # ================================================
            _ll("  尝试触发商品视频播放器…")
            try:
                # 淘宝主图视频通常有一个 play 按钮或 video 容器
                video_triggered = await page.evaluate("""
                    () => {
                        // 尝试点击视频播放按钮
                        const selectors = [
                            '#J_ImgBooth .tb-video-play',
                            '.tb-video',
                            '[class*="videoPlay"]',
                            '[class*="video-play"]',
                            '.tb-main-video',
                            '#J_Video',
                            '[data-spm="video"]',
                            '.J_VideoBooth',
                            '[class*="J_ItemVideo"]',
                        ];
                        for (const sel of selectors) {
                            const el = document.querySelector(sel);
                            if (el) {
                                el.click();
                                return sel;
                            }
                        }
                        // 检查是否有 video 标签, 有就 play
                        const v = document.querySelector('video');
                        if (v) { v.play(); return 'video tag found'; }
                        return null;
                    }
                """)
                if video_triggered:
                    _ll(f"    触发: {video_triggered}")
                    await page.wait_for_timeout(3000)  # 等视频加载
            except Exception:
                pass

            # ================================================
            # 第 3 层交互: 缩略图点击 (触发不同 SKU 图)
            # ================================================
            _ll("  点击 SKU 缩略图, 触发多规格图片…")
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(1000)
            try:
                thumbs = []
                for sel in (
                    "#J_UlThumb li",
                    "#J_UlThumb a",
                    ".tb-thumb-item",
                    ".tb-thumb-content li",
                    "[class*='thumbItem']",
                    "ul[id*='Thumb'] li",
                ):
                    thumbs = await page.query_selector_all(sel)
                    if thumbs:
                        break
                for i, t in enumerate((thumbs or [])[:8]):
                    try:
                        await t.click(timeout=800)
                        await page.wait_for_timeout(250 + random.randint(100, 400))
                        if i == 0:
                            _ll(f"    找到 {len(thumbs)} 个缩略图")
                    except Exception:
                        continue
            except Exception:
                pass

            # 等待网络请求全部完成
            await page.wait_for_timeout(3000)

            # ================================================
            # DOM 提取: 图片 (三层覆盖)
            # ================================================
            dom_images: set = set()

            # 1) 主图容器
            try:
                for sel in (
                    "#J_ImgBooth",
                    "#J_ImgBooth img",
                    "#J_UlThumb img",
                    "#J_UlThumb [data-src]",
                    "img[src*='alicdn.com']",
                    "[data-src*='alicdn.com']",
                    ".J_ImgBooth img",
                    "[class*='ImgBooth'] img",
                ):
                    els = await page.query_selector_all(sel)
                    for el in els:
                        src = (
                            await el.get_attribute("src")
                            or await el.get_attribute("data-src")
                            or await el.get_attribute("data-ks-lazyload")
                            or await el.get_attribute("data-original")
                        )
                        if src and not src.startswith("data:") and "alicdn.com" in src:
                            dom_images.add(_clean_image_url(src))
            except Exception:
                pass

            # 2) 详情页图片
            try:
                for sel in (
                    "#J_DivItemDesc img",
                    "#description img",
                    "div[class*='desc'] img",
                    "div[id*='desc'] img",
                    "div[id*='detail'] img",
                ):
                    els = await page.query_selector_all(sel)
                    for el in els:
                        src = (
                            await el.get_attribute("data-src")
                            or await el.get_attribute("src")
                            or await el.get_attribute("data-original")
                        )
                        if src and not src.startswith("data:") and "alicdn.com" in src:
                            captured_images.add(src)
            except Exception:
                pass

            # 3) Open Graph / meta 图中重定向的原图
            try:
                meta_img = await page.query_selector(
                    'meta[property="og:image"], meta[name="twitter:image"]'
                )
                if meta_img:
                    src = await meta_img.get_attribute("content")
                    if src and "alicdn.com" in src:
                        captured_images.add(_clean_image_url(src))
            except Exception:
                pass

            # 合并去重
            all_images = dom_images | captured_images

            # ================================================
            # 视频提取 (四层)
            # ================================================
            video_urls: set = set()

            # 1) 网络拦截的 CDN 视频 (已在 captured_videos 中)
            video_urls |= captured_videos

            # 2) DOM 扫描 video 元素 (扩展选择器)
            try:
                for sel in (
                    "video source[src]",
                    "video[src]",
                    "video",
                    "video source[data-src]",
                    "[class*='video'] source",
                    "[id*='Video'] source",
                    "[id*='video'] source",
                ):
                    els = await page.query_selector_all(sel)
                    for el in els:
                        src = (
                            await el.get_attribute("src")
                            or await el.get_attribute("data-src")
                        )
                        if src and not src.startswith("data:") and not src.startswith("blob:"):
                            video_urls.add(src)
                        # 也检查 video 标签自身的 poster (偶尔含视频信息)
                        poster = await el.get_attribute("poster")
                        if poster and not poster.startswith("data:"):
                            captured_images.add(poster)
            except Exception:
                pass

            # 3) JS 深度探测: 从页面数据对象中挖视频
            try:
                js_videos = await page.evaluate("""
                    () => {
                        const found = [];
                        const seen = new Set();

                        // 淘宝 g_config / __INIT_DATA__
                        const configs = [window.g_config, window.__INIT_DATA__,
                                         window.__data, window.__PRELOADED_STATE__,
                                         window._config, window.pageConfig];
                        for (const cfg of configs) {
                            if (!cfg) continue;
                            const s = JSON.stringify(cfg);
                            const re = /https?:\\/\\/[^"\\s,}]+\\.(mp4|webm|m3u8)[^"\\s,}]*/gi;
                            let m;
                            while ((m = re.exec(s)) !== null) {
                                if (!seen.has(m[0])) {
                                    seen.add(m[0]);
                                    found.push(m[0]);
                                }
                            }
                        }

                        // 扫描所有 <script type="application/json"> / <script type="text/template">
                        const scripts = document.querySelectorAll(
                            'script[type="application/json"], script[type="application/ld+json"], ' +
                            'script[id*="data"], script[id*="config"]'
                        );
                        for (const s of scripts) {
                            const txt = s.textContent || s.innerHTML || '';
                            const re = /https?:\\/\\/[^"\\s,}]+\\.(mp4|webm|m3u8)[^"\\s,}]*/gi;
                            let m;
                            while ((m = re.exec(txt)) !== null) {
                                if (!seen.has(m[0])) {
                                    seen.add(m[0]);
                                    found.push(m[0]);
                                }
                            }
                        }

                        // 淘宝特有: 从 __INIT_DATA__ 的 videoInfo / videoList
                        try {
                            const id = window.__INIT_DATA__;
                            if (id && id.videoInfo) {
                                const vi = id.videoInfo;
                                if (vi.videoUrl) found.push(vi.videoUrl);
                                if (vi.url) found.push(vi.url);
                            }
                        } catch(e) {}

                        // TShop 全局对象 (天猫)
                        try {
                            if (window.g_config) {
                                const gc = window.g_config;
                                if (gc.videoUrl) found.push(gc.videoUrl);
                                if (gc.videoId && gc.videoInfo) {
                                    if (gc.videoInfo.url) found.push(gc.videoInfo.url);
                                }
                            }
                        } catch(e) {}

                        return [...new Set(found)];
                    }
                """)
                if js_videos:
                    _ll(f"    JS 探测到 {len(js_videos)} 个视频 URL")
                    video_urls.update(js_videos)
            except Exception as e:
                _ll(f"    JS 探测出错: {e}")

            # 4) 详情描述中嵌入的视频 / iframe
            try:
                for sel in (
                    "#J_DivItemDesc iframe[src]",
                    "#description iframe[src]",
                    "div[class*='desc'] iframe[src]",
                ):
                    els = await page.query_selector_all(sel)
                    for el in els:
                        src = await el.get_attribute("src")
                        if src:
                            # youku/tudou 等嵌入播放器, URL 中含 vid
                            if any(d in src for d in ("youku", "tudou", "iqiyi")):
                                captured_images.add(src)  # 标记为可访问链接
            except Exception:
                pass

            # ================================================
            # 构建 MediaItem
            # ================================================
            idx = 0
            for img_url in sorted(all_images):
                idx += 1
                label = f"{title}_{idx}" if title else f"商品图 {idx}"
                items.append(MediaItem(
                    url=img_url,
                    title=label,
                    kind="image",
                    source_page=page_url,
                ))
            for vid_url in sorted(video_urls):
                idx += 1
                label = f"{title}_视频_{idx}" if title else f"商品视频 {idx}"
                items.append(MediaItem(
                    url=vid_url,
                    title=label,
                    kind="video",
                    source_page=page_url,
                ))

            n_img = sum(1 for i in items if i.kind == "image")
            n_vid = sum(1 for i in items if i.kind == "video")
            _ll(f"提取完成: {len(items)} 个资源 ({n_img} 图 + {n_vid} 视频)")

        finally:
            if page and not page.is_closed():
                await page.close()
            # CDP 模式下不关闭 browser (会杀掉用户浏览器)
            # 非 CDP 模式关闭
            try:
                if browser and not browser.is_connected():
                    pass  # CDP 已断
            except Exception:
                pass

    # 异步估大小 (并发 HEAD)
    if items:
        async def _head_tb(it):
            try:
                loop = asyncio.get_event_loop()
                size = await loop.run_in_executor(
                    None, estimate_size, it.url, page_url, 10
                )
                it.size = size
            except Exception:
                pass
        await asyncio.gather(*[_head_tb(it) for it in items])

    return items


# ============== URL 分发 ==============

async def extract_media(page_url: str, log=None) -> list[MediaItem]:
    """根据 URL 自动选择提取器."""
    if is_taobao_url(page_url):
        return await extract_taobao(page_url, log)
    return await extract_via_playwright(page_url, log)


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
    url = sys.argv[1] if len(sys.argv) > 1 else input("URL (淘宝/天猫/Bosch): ").strip()
    if not url:
        print("URL 不能为空", file=sys.stderr)
        return 1
    items = asyncio.run(extract_media(url))
    print(f"\n找到 {len(items)} 个资源:")
    for i, it in enumerate(items, 1):
        print(f"  [{i}] {kind_label(it.kind):8s} {it.display_name():50s}  {it.size_str():>12s}  {it.url[:80]}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
