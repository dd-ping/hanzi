# -*- coding: utf-8 -*-
"""
汉字字帖 A4 打印册生成核心模块
- 依赖 hanzi-writer-data 的笔画 SVG 数据（自动下载缓存）
- 生成：每行固定田字格铺满，前 N 格笔顺演示（当前笔红色、已完成黑色、未完成浅灰），
  练习格不足时自动追加练习行；超过一行容量的笔画自动换行继续显示。
"""
import json
import math
import os
import re
import shutil
import sys
import threading
import urllib.parse
import urllib.request
import zipfile
from PIL import Image, ImageDraw, ImageFont

# 兼容 PyInstaller 打包：exe 运行时以 exe 所在目录为基准
if getattr(sys, "frozen", False):
    BASE = os.path.dirname(sys.executable)
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
# 笔画数据缓存（exe 旁 hanzi_data，避免每次联网下载）
DATA_DIR = os.path.join(BASE, "hanzi_data")
_BUNDLED_ZIP = "hanzi_data.zip"
_DATA_LOCK = threading.Lock()


def _bundled_zip_path():
    """内嵌字库 zip（onefile 打包后由 bootloader 解压到临时目录，单文件、解压极快）"""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            p = os.path.join(meipass, _BUNDLED_ZIP)
            if os.path.exists(p):
                return p
    return None


def _bundled_data_dir():
    """兼容旧版：打包内含 hanzi_data 目录时也可直接读取"""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            p = os.path.join(meipass, "hanzi_data")
            if os.path.isdir(p):
                return p
    return None


def char_data_path(ch):
    """返回某个字的数据文件路径：本地缓存优先，其次从内嵌 zip 按需取出，无则 None。
    无需等全量字库解压，任何字都能随时按需加载。"""
    code = f"{ord(ch):04x}.json"
    p = os.path.join(DATA_DIR, code)
    if os.path.exists(p):
        return p
    zp = _bundled_zip_path()
    if zp:
        try:
            with zipfile.ZipFile(zp) as z:
                if code in z.namelist():
                    data = z.read(code)
                    with _DATA_LOCK:
                        if not os.path.exists(p):
                            os.makedirs(DATA_DIR, exist_ok=True)
                            with open(p, "wb") as f:
                                f.write(data)
                    return p
        except Exception:
            pass
    bd = _bundled_data_dir()
    if bd:
        p2 = os.path.join(bd, code)
        if os.path.exists(p2):
            return p2
    return None


def _init_bundled_data():
    """后台把内置字库写入 exe 旁 hanzi_data 作为持久缓存（目标存在即跳过）。
    在守护线程中执行，不阻塞界面启动；界面出现后任何字都能按需加载。"""
    if not getattr(sys, "frozen", False):
        return
    zp = _bundled_zip_path()
    if zp:
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with zipfile.ZipFile(zp) as z:
                for code in z.namelist():
                    if not code.endswith(".json"):
                        continue
                    dst = os.path.join(DATA_DIR, code)
                    if os.path.exists(dst):
                        continue
                    try:
                        data = z.read(code)
                        with _DATA_LOCK:
                            if not os.path.exists(dst):
                                with open(dst, "wb") as f:
                                    f.write(data)
                    except Exception:
                        pass
            return
        except Exception:
            pass
    bd = _bundled_data_dir()
    if not bd:
        return
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except Exception:
        return
    for fn in os.listdir(bd):
        if not fn.endswith(".json"):
            continue
        dst = os.path.join(DATA_DIR, fn)
        if os.path.exists(dst):
            continue
        try:
            with open(os.path.join(bd, fn), "rb") as f:
                data = f.read()
            with _DATA_LOCK:
                if not os.path.exists(dst):
                    with open(dst, "wb") as f:
                        f.write(data)
        except Exception:
            pass


if getattr(sys, "frozen", False):
    # 打包版：后台线程慢慢建立 exe 旁缓存，界面立即显示、字库按需加载
    threading.Thread(target=_init_bundled_data, daemon=True).start()
else:
    _init_bundled_data()  # 源码运行：无内嵌数据，直接返回


def _load_pinyin():
    """加载离线拼音字典（字 -> 带声调拼音）"""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        cands = [os.path.join(meipass, "pinyin.json"),
                 os.path.join(BASE, "pinyin.json")]
    else:
        cands = [os.path.join(BASE, "pinyin.json")]
    for p in cands:
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


PINYIN = _load_pinyin()


def get_pinyin(ch):
    """返回单字的带声调拼音，无数据返回空串"""
    return PINYIN.get(ch, "")


# ============ 默认配色（适中淡红，打印清晰） ============
C_GRAY = (210, 210, 210)
C_BLACK = (35, 35, 35)
C_RED = (210, 45, 45)
C_GRID_BORDER = (200, 145, 145)  # 田字格外框
C_GRID_AUX = (210, 158, 158)     # 米字辅助线（比外框浅一档，但打印清晰可见）
C_WHITE = (255, 255, 255)

# ============ 默认排版参数（A4 300dpi） ============
DEFAULT_A4 = dict(
    width=2480, height=3508,          # A4 @300dpi
    margin_l=60, margin_r=60,
    margin_t=70, margin_b=50,
    title_h=90,
    label_w=110, gap=8,
)
DEFAULT_PER_PAGE = 20       # 每页最多行数
DEFAULT_GRIDS_PER_ROW = 15  # 每行固定格子数
DEFAULT_MIN_PRACTICE = 4    # 单行最少练习格数，不足则追加练习行


# ============ 几何与 SVG 解析 ============
def _quad(p0, p1, p2, t):
    u = 1 - t
    return (u*u*p0[0] + 2*u*t*p1[0] + t*t*p2[0],
            u*u*p0[1] + 2*u*t*p1[1] + t*t*p2[1])


def _cubic(p0, p1, p2, p3, t):
    u = 1 - t
    return (u**3*p0[0] + 3*u**2*t*p1[0] + 3*u*t**2*p2[0] + t**3*p3[0],
            u**3*p0[1] + 3*u**2*t*p1[1] + 3*u*t**2*p2[1] + t**3*p3[1])


def parse_svg_path(d_str):
    tokens = re.findall(r'[MmLlQqCcZz]|-?\d+\.?\d*', d_str)
    subpaths, current = [], []
    start = pos = None
    i = 0
    S = 20

    def rn():
        nonlocal i
        v = float(tokens[i]); i += 1
        return v

    while i < len(tokens):
        cmd = tokens[i]; i += 1
        rel = cmd.islower(); c = cmd.upper()
        if c == 'M':
            x, y = rn(), rn()
            if rel and pos: x += pos[0]; y += pos[1]
            if current: subpaths.append(current)
            current = [(x, y)]; start = (x, y); pos = (x, y)
            while i < len(tokens) and tokens[i] not in 'MmLlQqCcZz':
                x, y = rn(), rn()
                if rel: x += pos[0]; y += pos[1]
                current.append((x, y)); pos = (x, y)
        elif c == 'L':
            while i < len(tokens) and tokens[i] not in 'MmLlQqCcZz':
                x, y = rn(), rn()
                if rel: x += pos[0]; y += pos[1]
                current.append((x, y)); pos = (x, y)
        elif c == 'Q':
            while i < len(tokens) and tokens[i] not in 'MmLlQqCcZz':
                cx, cy = rn(), rn(); x, y = rn(), rn()
                if rel:
                    cx += pos[0]; cy += pos[1]; x += pos[0]; y += pos[1]
                for s in range(1, S + 1):
                    current.append(_quad(pos, (cx, cy), (x, y), s / S))
                pos = (x, y)
        elif c == 'C':
            while i < len(tokens) and tokens[i] not in 'MmLlQqCcZz':
                a, b = rn(), rn(); c2, d = rn(), rn(); x, y = rn(), rn()
                if rel:
                    a += pos[0]; b += pos[1]; c2 += pos[0]; d += pos[1]
                    x += pos[0]; y += pos[1]
                for s in range(1, S + 1):
                    current.append(_cubic(pos, (a, b), (c2, d), (x, y), s / S))
                pos = (x, y)
        elif c == 'Z':
            if current:
                current.append(start); subpaths.append(current); current = []
            pos = start
    if current:
        subpaths.append(current)
    return subpaths


def transform_strokes(parsed, target_size):
    all_pts = []
    for sps in parsed:
        for sp in sps:
            all_pts.extend(sp)
    xs = [p[0] for p in all_pts]; ys = [p[1] for p in all_pts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    flip = maxy
    ow, oh = maxx - minx, maxy - miny
    scale = target_size / max(ow, oh)
    dw, dh = ow * scale, oh * scale
    ox = (target_size - dw) / 2 - minx * scale
    oy = (target_size - dh) / 2
    result = []
    for sps in parsed:
        tsps = []
        for sp in sps:
            tsps.append([(x * scale + ox, (flip - y) * scale + oy) for x, y in sp])
        result.append(tsps)
    return result


# ============ 绘制 ============
def draw_dashed(draw, x1, y1, x2, y2, color, dash=5, gap=4, width=1):
    L = math.hypot(x2 - x1, y2 - y1)
    if L == 0:
        return
    dx, dy = (x2 - x1) / L, (y2 - y1) / L
    p = 0
    while p < L:
        e = min(p + dash, L)
        draw.line([(x1 + dx * p, y1 + dy * p), (x1 + dx * e, y1 + dy * e)],
                  fill=color, width=width)
        p = e + gap


def draw_mi_grid(draw, x, y, size):
    draw.rectangle([x, y, x + size, y + size], outline=C_GRID_BORDER, width=2)
    # 米字虚线：dash 加长、线宽 2px，保证 300dpi 打印清晰可见
    draw_dashed(draw, x, y + size // 2, x + size, y + size // 2, C_GRID_AUX,
                dash=9, gap=5, width=2)
    draw_dashed(draw, x + size // 2, y, x + size // 2, y + size, C_GRID_AUX,
                dash=9, gap=5, width=2)
    draw_dashed(draw, x, y, x + size, y + size, C_GRID_AUX, dash=9, gap=5, width=2)
    draw_dashed(draw, x + size, y, x, y + size, C_GRID_AUX, dash=9, gap=5, width=2)


def fill_stroke(draw, sps, color):
    for sp in sps:
        if len(sp) >= 3:
            draw.polygon(sp, fill=color)


def load_font(size):
    for p in [r"C:\Windows\Fonts\msyh.ttc",
              r"C:\Windows\Fonts\simhei.ttf",
              r"C:\Windows\Fonts\simsun.ttc"]:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ============ 笔画数据下载 ============
# 多源下载（国内稳定优先）：
#  1. jsdelivr npm CDN（国内有节点，稳定）
#  2. unpkg npm CDN（备用）
#  3. GitHub raw（最后兜底）
# 下载成功的字会自动写入离线库 DATA_DIR（下次直接离线使用）
STROKE_SOURCES = [
    "https://cdn.jsdelivr.net/npm/hanzi-writer-data@2.0.1/{safe}.json",
    "https://unpkg.com/hanzi-writer-data@2.0.1/{safe}.json",
    "https://raw.githubusercontent.com/chanind/hanzi-writer-data/master/data/{safe}.json",
]


def download_char(ch):
    """下载单个字笔画数据，多源 + 重试，成功后写入离线库。返回路径或 None"""
    existing = char_data_path(ch)
    if existing:
        return existing  # 离线缓存或内嵌字库已有，直接可用
    safe = urllib.parse.quote(ch)
    path = os.path.join(DATA_DIR, f"{ord(ch):04x}.json")
    os.makedirs(DATA_DIR, exist_ok=True)
    for url_tpl in STROKE_SOURCES:
        for _attempt in range(2):
            url = url_tpl.format(safe=safe)
            try:
                req = urllib.request.Request(url,
                                             headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = resp.read()
                json.loads(data)  # 校验是合法 JSON
                with _DATA_LOCK:
                    if not os.path.exists(path):
                        with open(path, "wb") as f:
                            f.write(data)  # 加入离线库
                return path
            except Exception:
                continue
    return None


def download_all(chars, progress=None, workers=8):
    """并发下载所有缺失笔画数据，返回 (成功数, 失败列表)"""
    os.makedirs(DATA_DIR, exist_ok=True)
    total = len(chars)
    if total == 0:
        return 0, []
    ok = 0
    fail = []
    lock = threading.Lock()
    done = [0]

    def dl(ch):
        nonlocal ok
        r = download_char(ch)
        with lock:
            if r:
                ok += 1
            else:
                fail.append(ch)
            done[0] += 1
            if progress and done[0] % 25 == 0:
                progress(done[0], total, ok)

    threads = [threading.Thread(target=dl, args=(c,), daemon=True)
               for c in chars]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if progress:
        progress(total, total, ok)
    return ok, fail


def get_stroke_count(ch):
    path = char_data_path(ch)
    if not path:
        return 1
    try:
        with open(path, encoding="utf-8") as f:
            return len(json.load(f)["strokes"])
    except Exception:
        return 1


def char_lines(ch, grids_per_row, min_practice, align_rows=False):
    """该字占用的行数（笔顺多行 + 必要时补练习行）
    align_rows=True 时所有字统一至少占两行（笔画少的多给一整行练习格）"""
    n = get_stroke_count(ch)
    stroke_rows = (n + grids_per_row - 1) // grids_per_row
    if align_rows:
        return max(2, stroke_rows)
    last_free = stroke_rows * grids_per_row - n
    return stroke_rows if last_free >= min_practice else stroke_rows + 1


def paginate(chars, per_page, grids_per_row, min_practice, align_rows=False):
    pages, cur, used = [], [], 0
    for ch in chars:
        ln = char_lines(ch, grids_per_row, min_practice, align_rows)
        if used + ln > per_page:
            pages.append(cur); cur = []; used = 0
        cur.append(ch); used += ln
    if cur:
        pages.append(cur)
    return pages


# ============ 单字/单行渲染 ============
class Layout:
    """封装整页排版参数"""
    def __init__(self, per_page=DEFAULT_PER_PAGE,
                 grids_per_row=DEFAULT_GRIDS_PER_ROW,
                 min_practice=DEFAULT_MIN_PRACTICE,
                 paper=None):
        paper = dict(DEFAULT_A4) if paper is None else dict(paper)
        self.w = paper["width"]
        self.h = paper["height"]
        self.margin_l = paper["margin_l"]
        self.margin_r = paper["margin_r"]
        self.margin_t = paper["margin_t"]
        self.margin_b = paper["margin_b"]
        self.title_h = paper["title_h"]
        self.label_w = paper["label_w"]
        self.gap = paper["gap"]
        self.per_page = per_page
        self.grids_per_row = grids_per_row
        self.min_practice = min_practice
        self.content_w = self.w - self.margin_l - self.margin_r
        self.content_h = self.h - self.margin_t - self.margin_b
        self.row_h = (self.content_h - self.title_h) // per_page


def _text_metrics(draw, text, font):
    """测量文本：返回 (宽, 高, 字形顶部偏移 bbox[1])。
    绘制时若以 (x, y) 为锚点，字形实际顶部在 y+bbox[1]；
    补偿 offset 后（y-offset）可让字形顶部精确落在 y。"""
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1], bbox[1]


def render_stroke_row_partial(layout, ch, start, label_show=False, show_pinyin=True):
    """渲染一行：从第 start 笔开始连续 grids_per_row 个格子"""
    row_w = layout.content_w
    row_h = layout.row_h
    img = Image.new("RGB", (row_w, row_h), C_WHITE)
    draw = ImageDraw.Draw(img)
    data_path = char_data_path(ch)
    if not data_path:
        draw.text((10, 10), f"{ch}(无数据)", fill=C_RED, font=load_font(28))
        return img
    try:
        with open(data_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        draw.text((10, 10), f"{ch}(无数据)", fill=C_RED, font=load_font(28))
        return img
    n = len(data["strokes"])
    parsed = [parse_svg_path(s) for s in data["strokes"]]
    grids = layout.grids_per_row
    avail_w = row_w - layout.label_w - 24
    gs = int((avail_w - (grids - 1) * layout.gap) / grids)
    gs = min(gs, row_h - 20)
    transformed = transform_strokes(parsed, gs - 8)
    cy = (row_h - gs) // 2
    x0 = layout.label_w + 12

    if label_show:
        top = (row_h - gs) // 2
        # 拼音（带声调）
        py = get_pinyin(ch) if show_pinyin else ""
        py_font = py_w = py_h = py_b1 = None
        if py:
            py_size = max(14, int(gs * 0.20))
            while True:
                py_font = load_font(py_size)
                py_w, _h, _b = _text_metrics(draw, py, py_font)
                if py_w <= layout.label_w - 6 or py_size <= 13:
                    break
                py_size -= 1
            _, py_h, py_b1 = _text_metrics(draw, py, py_font)
        # 笔数
        font_info = load_font(18)
        info_txt = f"{n}笔"
        info_w, info_h, info_b1 = _text_metrics(draw, info_txt, font_info)
        # 标签字：字号自适应，保证 拼音+字+笔数 三者不重叠（高度含字形偏移）
        ch_size = int(gs * 0.72)
        ch_gap = 2
        font_ch = ch_w = ch_h = ch_b1 = None
        while ch_size > 26:
            font_ch = load_font(ch_size)
            ch_w, ch_h, ch_b1 = _text_metrics(draw, ch, font_ch)
            need = (py_h or 0) + ch_h + info_h + ch_gap * 2
            if need <= gs and ch_w <= layout.label_w - 4:
                break
            ch_size -= 2
        # 绘制：拼音顶部 -> 字 -> 笔数贴底（补偿字形偏移，使元素顶部精确对齐 y）
        y = top
        if py and py_font:
            draw.text(((layout.label_w - py_w) / 2, y - py_b1), py,
                      fill=(85, 100, 125), font=py_font)
            y += py_h + ch_gap
        draw.text(((layout.label_w - ch_w) / 2, y - ch_b1), ch, fill=C_BLACK, font=font_ch)
        draw.text(((layout.label_w - info_w) / 2, top + gs - info_h - 1 - info_b1),
                  info_txt, fill=(140, 140, 140), font=font_info)

    for idx in range(grids):
        gx = x0 + idx * (gs + layout.gap)
        draw_mi_grid(draw, gx, cy, gs)
        si = start + idx
        if si >= n:
            continue  # 空白练习格
        # 先画非当前笔画（已完成黑色 / 未完成浅灰），红色最后画确保最上层
        for i in range(n):
            if i == si:
                continue
            color = C_BLACK if i < si else C_GRAY
            shifted = [[(px + gx + 4, py + cy + 4) for px, py in sp]
                       for sp in transformed[i]]
            fill_stroke(draw, shifted, color)
        shifted = [[(px + gx + 4, py + cy + 4) for px, py in sp]
                   for sp in transformed[si]]
        fill_stroke(draw, shifted, C_RED)
    return img


def render_practice_row(layout):
    """整行空白练习格（无文字）"""
    row_w = layout.content_w
    row_h = layout.row_h
    img = Image.new("RGB", (row_w, row_h), C_WHITE)
    draw = ImageDraw.Draw(img)
    grids = layout.grids_per_row
    avail_w = row_w - layout.label_w - 24
    gs = int((avail_w - (grids - 1) * layout.gap) / grids)
    gs = min(gs, row_h - 20)
    cy = (row_h - gs) // 2
    x0 = layout.label_w + 12
    for idx in range(grids):
        gx = x0 + idx * (gs + layout.gap)
        draw_mi_grid(draw, gx, cy, gs)
    return img


def render_char_block(layout, ch, show_pinyin=True, align_rows=False):
    """渲染一个字块：笔顺多行显示，末尾练习格不足时补练习行。
    align_rows=True：所有字统一至少占两行（笔画少的多给一整行空白练习格）"""
    n = get_stroke_count(ch)
    gpr = layout.grids_per_row
    stroke_rows = (n + gpr - 1) // gpr
    last_free = stroke_rows * gpr - n
    if align_rows:
        lines = max(2, stroke_rows)
    else:
        lines = stroke_rows if last_free >= layout.min_practice else stroke_rows + 1
    block = Image.new("RGB", (layout.content_w, layout.row_h * lines), C_WHITE)
    for r in range(stroke_rows):
        row_img = render_stroke_row_partial(layout, ch, r * gpr,
                                            label_show=(r == 0),
                                            show_pinyin=show_pinyin)
        block.paste(row_img, (0, r * layout.row_h))
    for r in range(stroke_rows, lines):
        block.paste(render_practice_row(layout), (0, r * layout.row_h))
    return block


def render_page(layout, chars_page, page_num, total_pages, title, show_pinyin=True,
                align_rows=False):
    img = Image.new("RGB", (layout.w, layout.h), C_WHITE)
    draw = ImageDraw.Draw(img)
    font_title = load_font(36)
    font_page = load_font(22)
    draw.text((layout.margin_l, 20), title, fill=C_BLACK, font=font_title)
    page_info = f"第 {page_num}/{total_pages} 页"
    bbox = draw.textbbox((0, 0), page_info, font=font_page)
    draw.text((layout.w - layout.margin_r - (bbox[2] - bbox[0]), 30),
              page_info, fill=(100, 100, 100), font=font_page)
    draw.line([(layout.margin_l, 72), (layout.w - layout.margin_r, 72)],
              fill=C_RED, width=2)

    y = layout.margin_t + layout.title_h - 20
    for ch in chars_page:
        block = render_char_block(layout, ch, show_pinyin=show_pinyin,
                                  align_rows=align_rows)
        img.paste(block, (layout.margin_l, y))
        y += block.size[1]
    return img


# ============ 总入口 ============
def render_zitie(chars, title="汉字字帖", per_page=DEFAULT_PER_PAGE,
                 grids_per_row=DEFAULT_GRIDS_PER_ROW,
                 min_practice=DEFAULT_MIN_PRACTICE,
                 paper=None, show_pinyin=True, align_rows=False, progress=None):
    """
    只渲染页面图片（不写 PDF）。
    - 返回: (pages_img 列表[PIL], 失败字列表)
    - 用于"先预览，满意后再导出 PDF"的流程。
    """
    if isinstance(chars, str):
        chars = list(chars)
    chars = [c for c in chars if '\u4e00' <= c <= '\u9fff']
    if not chars:
        raise ValueError("没有可生成的汉字")

    ok, fail = download_all(chars, progress)
    if not ok:
        raise RuntimeError(f"笔画数据全部下载失败: {fail}")

    layout = Layout(per_page=per_page, grids_per_row=grids_per_row,
                    min_practice=min_practice, paper=paper)
    pages_chars = paginate(chars, per_page, grids_per_row, min_practice,
                           align_rows)
    n_pages = len(pages_chars)

    pages_img = []
    for p, page_chars in enumerate(pages_chars):
        img = render_page(layout, page_chars, p + 1, n_pages, title,
                          show_pinyin=show_pinyin, align_rows=align_rows)
        pages_img.append(img)
        if progress:
            progress(p + 1, n_pages, 0)
    return pages_img, fail


def pages_to_pdf(pages_img, out_pdf, resolution=300.0):
    """把已渲染的页面图片写为 PDF 文件"""
    if not pages_img:
        raise ValueError("没有页面可导出")
    pages_img[0].save(out_pdf, "PDF", resolution=resolution, save_all=True,
                      append_images=pages_img[1:])


def generate_zitie(chars, title="汉字字帖", per_page=DEFAULT_PER_PAGE,
                   grids_per_row=DEFAULT_GRIDS_PER_ROW,
                   min_practice=DEFAULT_MIN_PRACTICE,
                   paper=None, out_pdf=None, out_dir=None,
                   show_pinyin=True, progress=None):
    """
    生成 A4 字帖 PDF（渲染 + 落盘一步到位）。
    - chars: 汉字字符串或列表（保持顺序）
    - out_pdf: 输出 PDF 路径；None 时保存到 out_dir
    - 返回: (pdf_path, [页PIL图], 失败字列表)
    """
    if isinstance(chars, str):
        chars = list(chars)
    pages_img, fail = render_zitie(chars, title=title, per_page=per_page,
                                   grids_per_row=grids_per_row,
                                   min_practice=min_practice, paper=paper,
                                   show_pinyin=show_pinyin, progress=progress)
    if out_dir is None:
        out_dir = os.path.join(BASE, "output")
    os.makedirs(out_dir, exist_ok=True)
    if out_pdf is None:
        out_pdf = os.path.join(out_dir, "字帖.pdf")
    pages_to_pdf(pages_img, out_pdf)
    return out_pdf, pages_img, fail


if __name__ == "__main__":
    # 命令行测试
    pdf, pages, fails = generate_zitie("堂表兄弟姐妹姑阿舅爸妈我叔伯父",
                                       title="测试字帖", out_dir=r"output_test")
    print("PDF:", pdf)
    print("页数:", len(pages))
    print("失败:", fails)