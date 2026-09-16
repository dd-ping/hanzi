# -*- coding: utf-8 -*-
"""
汉字字帖 A4 生成器  v1.3.2
v1.3.2 新增：
  - 笔画显示样式：灰色描红（默认，笔画统一灰色，步骤清晰）/ 红黑教学（已写黑、当前红、未写浅灰）
v1.3.1 新增：
  - 默认排版改为"每个字统一占两行田字格"（对齐排版，即两行字帖版式）
  - 田字格颜色切换：红 / 蓝 / 黑 / 绿（格子边框+辅助线随颜色，笔顺红笔不变）
v1.3 练字功能（参考 an2.net 练字工具集）：
  - 字帖类型：常规汉字字帖 / 看拼音写词语（听写纸）/ 拼音四线三格 / 空白模板
  - 看拼音写词语：每词自动生成带声调拼音 + 空格田字格，重复行供反复听写
  - 拼音四线三格：浅灰示例字母描红 + 空白格临摹，可调每行组数
  - 空白模板：米字格 / 田字格 / 四线三格，一键打印空白练习纸
v1.2 体验优化（保留）：
  - 自定义圆角按钮（悬停/按下/禁用反馈），告别系统默认丑按钮
  - 预览为独立可拖动子窗口，主窗口专注操作，互不干扰
  - PDF 预览体验升级：放大/缩小/适合窗口/实际大小、Ctrl+滚轮缩放、
    放大后拖拽平移、滚轮翻页、页码跳转
  - 打印预览：可调页边距(mm)，红色虚线标出打印区域，显示纸张/边距信息
  - 标签字上方显示拼音（带声调，可开关）
  - 工作流：先预览，满意后再导出 PDF
用法：
  python app.py          （启动界面）
  python app.py --selftest （打包自检）
"""
import os
import queue
import sys
import tempfile
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, scrolledtext, ttk

from PIL import Image, ImageDraw, ImageTk

import ocr_engine as ocr
import zitie_core as core

APP_VERSION = "v1.3.2"
APP_NAME = "汉字字帖生成器"

# ---- 字帖类型（参考 an2.net 练字工具集）----
MODE_HANZI = "常规汉字字帖"
MODE_TINGXIE = "看拼音写词语"
MODE_PINYIN = "拼音四线三格"
MODE_BLANK = "空白模板"
MODES = [MODE_HANZI, MODE_TINGXIE, MODE_PINYIN, MODE_BLANK]
MODE_HINTS = {
    MODE_HANZI: "输入要练习的汉字（可多字、可换行），或点“从图片识别”自动采集",
    MODE_TINGXIE: "每行输入一个词语，如：学校 / 老师 / 天气真好（生成拼音提示 + 空格田字格听写纸）",
    MODE_PINYIN: "输入拼音字母或音节，用空格或换行分隔，如：a o e b p m f ai ei ui",
    MODE_BLANK: "无需输入文字，选择模板类型后直接生成空白练习纸",
}

# ---- 主题色 ----
COLOR_BG = "#F1F4F7"        # 窗口背景
COLOR_PANEL = "#FFFFFF"     # 面板背景
COLOR_PRIMARY = "#1F7A8C"   # 主色（青蓝）
COLOR_PRIMARY_HOVER = "#2B8B9E"
COLOR_PRIMARY_ACTIVE = "#14626F"
COLOR_ACCENT = "#E8833A"    # 强调色（预览按钮）
COLOR_ACCENT_HOVER = "#F09652"
COLOR_ACCENT_ACTIVE = "#C96B27"
COLOR_TEXT = "#2B333B"
COLOR_MUTED = "#7A8694"
COLOR_LINE = "#DCE3E9"
COLOR_DISABLED = "#DFE4E9"

ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 0.1, 2.0, 1.2


# ---------------- 颜色工具 ----------------
def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mix(c1, c2, t):
    a, b = _hex_to_rgb(c1), _hex_to_rgb(c2)
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _lighten(c, t=0.12):
    return _mix(c, "#FFFFFF", t)


def _darken(c, t=0.14):
    return _mix(c, "#0A1420", t)


# ---------------- 自定义圆角按钮 ----------------
def _round_rect_points(x1, y1, x2, y2, r):
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


class RoundButton(tk.Canvas):
    """Canvas 自绘圆角按钮，带 hover/按下/禁用 三态反馈"""

    def __init__(self, master, text="", command=None, bg=COLOR_PRIMARY,
                 hover_bg=None, active_bg=None, fg="white",
                 disabled_bg=COLOR_DISABLED, disabled_fg="#9AA4AE",
                 radius=10, font=("Microsoft YaHei", 10, "bold"),
                 padx=16, pady=8, parent_bg=None):
        pb = parent_bg if parent_bg is not None else getattr(master, "_panel_bg", COLOR_PANEL)
        super().__init__(master, highlightthickness=0, bd=0, bg=pb, cursor="hand2")
        self._text = text
        self._command = command
        self._bg = bg
        self._hover_bg = hover_bg or _lighten(bg, 0.10)
        self._active_bg = active_bg or _darken(bg, 0.12)
        self._fg = fg
        self._disabled_bg = disabled_bg
        self._disabled_fg = disabled_fg
        self._radius = radius
        self._font = font
        self._padx = padx
        self._pady = pady
        self._state = "normal"
        self._hover = False
        self._pressed = False

        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._draw()

    def set_state(self, state):
        self._state = state
        self._draw()

    def get_state(self):
        return self._state

    def _set_hover(self, on):
        if self._state != "normal":
            return
        self._hover = on
        self._draw()

    def _on_press(self, _e):
        if self._state != "normal":
            return
        self._pressed = True
        self._draw()

    def _on_release(self, _e):
        if self._state != "normal":
            return
        was = self._pressed
        self._pressed = False
        self._draw()
        if was and self._command:
            try:
                self._command()
            except Exception as ex:
                messagebox.showerror("错误", str(ex))

    def _draw(self):
        self.delete("all")
        f = tkfont.Font(family=self._font[0], size=self._font[1],
                        weight=self._font[2] if len(self._font) > 2 else "normal")
        tw, th = f.measure(self._text), f.metrics("linespace")
        w, h = tw + self._padx * 2, th + self._pady * 2
        self.configure(width=w, height=h)
        if self._state == "disabled":
            bg, fgc = self._disabled_bg, self._disabled_fg
        elif self._pressed:
            bg, fgc = self._active_bg, self._fg
        elif self._hover:
            bg, fgc = self._hover_bg, self._fg
        else:
            bg, fgc = self._bg, self._fg
        self.create_polygon(_round_rect_points(1, 1, w - 1, h - 1, self._radius),
                            smooth=True, fill=bg, outline="")
        self.create_text(w / 2, h / 2, text=self._text, fill=fgc, font=self._font)


# ---------------- 主应用 ----------------
class ZitieApp:
    def __init__(self, root):
        self.root = root
        root.title(f"{APP_NAME} {APP_VERSION}")
        root.geometry("560x820")
        root.minsize(500, 720)
        root.configure(bg=COLOR_BG)

        self._pages_img = []
        self._page_idx = 0
        self._preview_photo = None
        self._pdf_path = None
        self._preview_params = None
        self._fit_mode = "page"
        self._scale = 1.0
        self._off_x = 0.0
        self._off_y = 0.0
        self._pan_anchor = None
        self._queue = queue.Queue()
        self._busy = False

        # 独立预览子窗口
        self._preview_win = None
        self._preview_canvas = None
        self._preview_pinfo = None
        self._ocr_btn = None  # 由 _build_ui 赋值

        self._build_style()
        self._build_ui()
        self.root.after(120, self._poll_queue)
        self._update_input_stats()

    # ---------------- 样式 ----------------
    def _build_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(".", font=("Microsoft YaHei", 10), foreground=COLOR_TEXT)
        style.configure("TFrame", background=COLOR_BG)
        style.configure("Panel.TFrame", background=COLOR_PANEL)
        style.configure("TLabelframe", background=COLOR_PANEL, bordercolor=COLOR_LINE)
        style.configure("TLabelframe.Label", background=COLOR_PANEL,
                        foreground=COLOR_PRIMARY, font=("Microsoft YaHei", 11, "bold"))
        style.configure("Header.TLabel", background=COLOR_PRIMARY,
                        foreground="white", font=("Microsoft YaHei", 16, "bold"))
        style.configure("Sub.TLabel", background=COLOR_PRIMARY,
                        foreground="#DFEFF4", font=("Microsoft YaHei", 9))
        style.configure("Body.TLabel", background=COLOR_PANEL, foreground=COLOR_TEXT)
        style.configure("Muted.TLabel", background=COLOR_PANEL, foreground=COLOR_MUTED,
                        font=("Microsoft YaHei", 9))
        style.configure("Count.TLabel", background=COLOR_PANEL, foreground=COLOR_PRIMARY,
                        font=("Microsoft YaHei", 10, "bold"))
        style.configure("TEntry", fieldbackground="white", bordercolor=COLOR_LINE)
        style.map("TEntry", bordercolor=[("focus", COLOR_PRIMARY)])
        style.configure("TSpinbox", fieldbackground="white")
        style.configure("TCheckbutton", background=COLOR_PANEL, foreground=COLOR_TEXT)
        style.map("TCheckbutton", background=[("active", COLOR_PANEL)])
        style.configure("Horizontal.TProgressbar",
                        troughcolor="#E3E9EE", background=COLOR_PRIMARY, borderwidth=0)

    # ---------------- 主窗口界面 ----------------
    def _build_ui(self):
        outer = ttk.Frame(self.root, style="TFrame", padding=12)
        outer.pack(fill="both", expand=True)

        # 横幅
        banner = tk.Frame(outer, bg=COLOR_PRIMARY, padx=14, pady=9)
        banner.pack(fill="x")
        ttk.Label(banner, text=APP_NAME, style="Header.TLabel").pack(anchor="w")
        ttk.Label(banner,
                  text="输入汉字或从图片识别 → 先预览 → 满意后导出 PDF 打印",
                  style="Sub.TLabel").pack(anchor="w", pady=(2, 0))

        # ① 输入汉字
        in_panel = ttk.LabelFrame(outer, text="① 输入内容", style="TLabelframe", padding=10)
        in_panel.pack(fill="x", pady=(10, 0))
        in_panel._panel_bg = COLOR_PANEL

        self.var_hint = tk.StringVar(value=MODE_HINTS[MODE_HANZI])
        ttk.Label(in_panel, textvariable=self.var_hint, style="Muted.TLabel",
                  wraplength=480, justify="left").pack(anchor="w", pady=(0, 4))

        self.txt = scrolledtext.ScrolledText(
            in_panel, height=6, font=("Microsoft YaHei", 12),
            wrap="char", relief="flat", highlightthickness=1,
            highlightbackground=COLOR_LINE, bd=0)
        self.txt.pack(fill="x")
        self.txt.bind("<KeyRelease>", lambda e: self._update_input_stats())

        toolbar = ttk.Frame(in_panel, style="Panel.TFrame")
        toolbar.pack(fill="x", pady=(8, 0))
        toolbar._panel_bg = COLOR_PANEL
        self._ocr_btn = RoundButton(toolbar, text="从图片识别", command=self._on_ocr_click,
                    bg="#EAF1F5", fg=COLOR_PRIMARY, hover_bg="#DCE8EE",
                    active_bg="#C9DCE4", font=("Microsoft YaHei", 9),
                    padx=12, pady=5, radius=8, parent_bg=COLOR_PANEL)
        self._ocr_btn.pack(side="left")
        RoundButton(toolbar, text="填入示例", command=self._fill_example,
                    bg="#EAF1F5", fg=COLOR_PRIMARY, hover_bg="#DCE8EE",
                    active_bg="#C9DCE4", font=("Microsoft YaHei", 9),
                    padx=12, pady=5, radius=8, parent_bg=COLOR_PANEL).pack(side="left", padx=6)
        RoundButton(toolbar, text="清空", command=self._clear_input,
                    bg="#EAF1F5", fg=COLOR_PRIMARY, hover_bg="#DCE8EE",
                    active_bg="#C9DCE4", font=("Microsoft YaHei", 9),
                    padx=12, pady=5, radius=8, parent_bg=COLOR_PANEL).pack(side="left")

        self.var_count = tk.StringVar(value="已输入 0 字")
        ttk.Label(in_panel, textvariable=self.var_count, style="Count.TLabel").pack(anchor="w", pady=(6, 0))
        self.var_coverage = tk.StringVar(value="")
        ttk.Label(in_panel, textvariable=self.var_coverage, style="Muted.TLabel",
                  wraplength=480, justify="left").pack(anchor="w")

        # ② 生成参数 + 打印设置
        param_panel = ttk.LabelFrame(outer, text="② 生成参数 / 打印设置", style="TLabelframe", padding=10)
        param_panel.pack(fill="x", pady=(10, 0))
        param_panel._panel_bg = COLOR_PANEL

        self.var_title = tk.StringVar(value="汉字字帖")
        self.var_mode = tk.StringVar(value=MODE_HANZI)
        self.var_repeat = tk.IntVar(value=2)
        self.var_groups = tk.IntVar(value=5)
        self.var_blank_kind = tk.StringVar(value="米字格")
        self.var_perpage = tk.IntVar(value=core.DEFAULT_PER_PAGE)
        self.var_grids = tk.IntVar(value=core.DEFAULT_GRIDS_PER_ROW)
        self.var_dedup = tk.BooleanVar(value=True)
        self.var_margin_t = tk.DoubleVar(value=12)
        self.var_margin_b = tk.DoubleVar(value=10)
        self.var_margin_l = tk.DoubleVar(value=8)
        self.var_margin_r = tk.DoubleVar(value=8)
        self.var_show_margin = tk.BooleanVar(value=True)
        self.var_show_pinyin = tk.BooleanVar(value=True)
        self.var_align_rows = tk.BooleanVar(value=True)  # 默认统一两行对齐（图2排版）
        self.var_grid_color = tk.StringVar(value=core.DEFAULT_GRID_COLOR)
        self.var_stroke_style = tk.StringVar(value="灰色描红")

        grid = ttk.Frame(param_panel, style="Panel.TFrame")
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)
        grid._panel_bg = COLOR_PANEL

        ttk.Label(grid, text="字帖类型：", style="Body.TLabel").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Combobox(grid, textvariable=self.var_mode, values=MODES,
                     state="readonly", width=20,
                     font=("Microsoft YaHei", 9)).grid(row=0, column=1, sticky="w", padx=(6, 0))
        self.var_mode.trace_add("write", lambda *a: self._on_mode_change())

        ttk.Label(grid, text="标题：", style="Body.TLabel").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(grid, textvariable=self.var_title, width=28).grid(row=1, column=1, sticky="we", padx=(6, 0))

        row1 = ttk.Frame(grid, style="Panel.TFrame")
        row1.grid(row=2, column=0, columnspan=2, sticky="we", pady=2)
        row1._panel_bg = COLOR_PANEL
        ttk.Label(row1, text="每页行数：", style="Body.TLabel").pack(side="left")
        ttk.Spinbox(row1, from_=5, to=30, textvariable=self.var_perpage,
                    width=5).pack(side="left", padx=(4, 14))
        ttk.Label(row1, text="每行格数：", style="Body.TLabel").pack(side="left")
        ttk.Spinbox(row1, from_=5, to=20, textvariable=self.var_grids,
                    width=5).pack(side="left", padx=(4, 0))

        row1b = ttk.Frame(grid, style="Panel.TFrame")
        row1b.grid(row=3, column=0, columnspan=2, sticky="we", pady=2)
        row1b._panel_bg = COLOR_PANEL
        ttk.Label(row1b, text="格子颜色：", style="Body.TLabel").pack(side="left")
        ttk.Combobox(row1b, textvariable=self.var_grid_color,
                     values=list(core.GRID_COLORS.keys()),
                     state="readonly", width=6, font=("Microsoft YaHei", 9)
                     ).pack(side="left", padx=(4, 14))
        ttk.Label(row1b, text="笔画：", style="Body.TLabel").pack(side="left")
        self.cmb_stroke = ttk.Combobox(row1b, textvariable=self.var_stroke_style,
                     values=list(core.STROKE_STYLE_NAMES.keys()),
                     state="readonly", width=8, font=("Microsoft YaHei", 9))
        self.cmb_stroke.pack(side="left", padx=(4, 0))

        row2 = ttk.Frame(grid, style="Panel.TFrame")
        row2.grid(row=4, column=0, columnspan=2, sticky="we", pady=2)
        row2._panel_bg = COLOR_PANEL
        ttk.Label(row2, text="页边距mm：", style="Body.TLabel").pack(side="left")
        for text, var in (("上", self.var_margin_t), ("下", self.var_margin_b),
                          ("左", self.var_margin_l), ("右", self.var_margin_r)):
            ttk.Label(row2, text=text, style="Muted.TLabel").pack(side="left", padx=(4, 1))
            sp = ttk.Spinbox(row2, from_=0, to=60, increment=1, textvariable=var, width=4)
            sp.pack(side="left", padx=(0, 3))
            sp.bind("<KeyRelease>", lambda e: self._on_margin_change())

        # 按字帖类型动态显示的参数行
        row_extra = ttk.Frame(grid, style="Panel.TFrame")
        row_extra.grid(row=5, column=0, columnspan=2, sticky="we", pady=2)
        row_extra._panel_bg = COLOR_PANEL
        self.lb_repeat = ttk.Label(row_extra, text="每词重复行数：", style="Body.TLabel")
        self.lb_repeat.grid(row=0, column=0, sticky="w")
        self.sp_repeat = ttk.Spinbox(row_extra, from_=1, to=6, textvariable=self.var_repeat, width=4)
        self.sp_repeat.grid(row=0, column=1, padx=(4, 14))
        self.lb_groups = ttk.Label(row_extra, text="每行组数：", style="Body.TLabel")
        self.lb_groups.grid(row=0, column=2, sticky="w")
        self.sp_groups = ttk.Spinbox(row_extra, from_=2, to=8, textvariable=self.var_groups, width=4)
        self.sp_groups.grid(row=0, column=3, padx=(4, 14))
        self.lb_blank = ttk.Label(row_extra, text="模板：", style="Body.TLabel")
        self.lb_blank.grid(row=0, column=4, sticky="w")
        self.cb_blank = ttk.Combobox(row_extra, textvariable=self.var_blank_kind,
                                     values=["米字格", "田字格", "四线三格"],
                                     state="readonly", width=8, font=("Microsoft YaHei", 9))
        self.cb_blank.grid(row=0, column=5, padx=(4, 0))
        self._on_mode_change()  # 初始化显隐

        ttk.Checkbutton(grid, text="图片识别时自动去重（推荐）",
                        variable=self.var_dedup).grid(row=6, column=0, columnspan=2, sticky="w", pady=(3, 0))
        ttk.Checkbutton(grid, text="标签字上方显示拼音（推荐）",
                        variable=self.var_show_pinyin).grid(row=7, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(grid, text="预览中显示页边距线（打印预览）",
                        variable=self.var_show_margin,
                        command=lambda: self._redraw_preview()).grid(row=8, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(grid, text="每个字统一占两行田字格（笔画少的自动补一整行练习格）",
                        variable=self.var_align_rows,
                        command=lambda: self._update_printinfo()).grid(row=9, column=0, columnspan=2, sticky="w")
        ttk.Label(param_panel,
                  text="页边距会真实作用于导出的 PDF；笔画超出一行自动换行，练习格不足自动补行。",
                  style="Muted.TLabel", wraplength=480, justify="left").pack(anchor="w", pady=(6, 0))

        # ③ 预览 / 导出
        btn_panel = ttk.Frame(outer, style="TFrame")
        btn_panel.pack(fill="x", pady=(12, 0))
        btn_panel._panel_bg = COLOR_BG
        self.btn_preview = RoundButton(btn_panel, text="预览字帖", command=self._on_preview_click,
                                       bg=COLOR_ACCENT, hover_bg=COLOR_ACCENT_HOVER,
                                       active_bg=COLOR_ACCENT_ACTIVE, font=("Microsoft YaHei", 12, "bold"),
                                       padx=22, pady=9, radius=11, parent_bg=COLOR_BG)
        self.btn_preview.pack(side="left", expand=True, fill="x")
        self.btn_export = RoundButton(btn_panel, text="导出 PDF", command=self._on_export_click,
                                      bg=COLOR_PRIMARY, hover_bg=COLOR_PRIMARY_HOVER,
                                      active_bg=COLOR_PRIMARY_ACTIVE, font=("Microsoft YaHei", 12, "bold"),
                                      padx=22, pady=9, radius=11, parent_bg=COLOR_BG)
        self.btn_export.pack(side="left", padx=(8, 0), expand=True, fill="x")

        # 进度 + 状态
        self.progress = ttk.Progressbar(outer, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(10, 0))
        self.var_status = tk.StringVar(value="就绪：输入汉字或从图片识别，点“预览字帖”查看效果")
        ttk.Label(outer, textvariable=self.var_status, style="Muted.TLabel",
                  wraplength=520, justify="left").pack(fill="x", pady=(6, 0))

    # ---------------- 独立预览子窗口 ----------------
    def _ensure_preview_window(self):
        """确保独立预览子窗口存在（关闭后可重新打开）"""
        if self._preview_win is not None and self._preview_win.winfo_exists():
            self._preview_win.lift()
            self._preview_win.deiconify()
            return
        win = tk.Toplevel(self.root)
        win.title(f"{APP_NAME} - 预览")
        win.geometry("780x860")
        win.configure(bg=COLOR_BG)
        win._panel_bg = COLOR_PANEL
        win.protocol("WM_DELETE_WINDOW", self._on_preview_close)
        self._preview_win = win

        body = ttk.Frame(win, style="TFrame", padding=8)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        # 工具栏：缩放 + 导航 + 打开
        ptool = ttk.Frame(body, style="Panel.TFrame")
        ptool.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ptool._panel_bg = COLOR_PANEL

        zoom_grp = ttk.Frame(ptool, style="Panel.TFrame")
        zoom_grp.pack(side="left")
        zoom_grp._panel_bg = COLOR_PANEL
        RoundButton(zoom_grp, text="－ 缩小", command=self._zoom_out,
                    bg="#EEF3F6", fg=COLOR_TEXT, hover_bg="#E1EAEF", active_bg="#D3E0E7",
                    font=("Microsoft YaHei", 9), padx=9, pady=4, radius=7, parent_bg=COLOR_PANEL).pack(side="left")
        self.var_zoom = tk.StringVar(value="100%")
        ttk.Label(zoom_grp, textvariable=self.var_zoom, style="Count.TLabel",
                  width=6, anchor="center").pack(side="left", padx=4)
        RoundButton(zoom_grp, text="放大 ＋", command=self._zoom_in,
                    bg="#EEF3F6", fg=COLOR_TEXT, hover_bg="#E1EAEF", active_bg="#D3E0E7",
                    font=("Microsoft YaHei", 9), padx=9, pady=4, radius=7, parent_bg=COLOR_PANEL).pack(side="left")
        RoundButton(zoom_grp, text="适合窗口", command=self._zoom_fit,
                    bg="#EEF3F6", fg=COLOR_TEXT, hover_bg="#E1EAEF", active_bg="#D3E0E7",
                    font=("Microsoft YaHei", 9), padx=9, pady=4, radius=7, parent_bg=COLOR_PANEL).pack(side="left", padx=6)
        RoundButton(zoom_grp, text="实际大小", command=self._zoom_actual,
                    bg="#EEF3F6", fg=COLOR_TEXT, hover_bg="#E1EAEF", active_bg="#D3E0E7",
                    font=("Microsoft YaHei", 9), padx=9, pady=4, radius=7, parent_bg=COLOR_PANEL).pack(side="left")

        nav_grp = ttk.Frame(ptool, style="Panel.TFrame")
        nav_grp.pack(side="right")
        nav_grp._panel_bg = COLOR_PANEL
        RoundButton(nav_grp, text="◀ 上一页", command=self._prev_page,
                    bg="#EEF3F6", fg=COLOR_TEXT, hover_bg="#E1EAEF", active_bg="#D3E0E7",
                    font=("Microsoft YaHei", 9), padx=9, pady=4, radius=7, parent_bg=COLOR_PANEL).pack(side="left")
        self.var_pageno = tk.StringVar(value="尚未生成")
        ttk.Label(nav_grp, textvariable=self.var_pageno, style="Body.TLabel").pack(side="left", padx=6)
        RoundButton(nav_grp, text="下一页 ▶", command=self._next_page,
                    bg="#EEF3F6", fg=COLOR_TEXT, hover_bg="#E1EAEF", active_bg="#D3E0E7",
                    font=("Microsoft YaHei", 9), padx=9, pady=4, radius=7, parent_bg=COLOR_PANEL).pack(side="left")
        RoundButton(nav_grp, text="打开 PDF", command=self._open_pdf,
                    bg="#EEF3F6", fg=COLOR_TEXT, hover_bg="#E1EAEF", active_bg="#D3E0E7",
                    font=("Microsoft YaHei", 9), padx=9, pady=4, radius=7, parent_bg=COLOR_PANEL).pack(side="left", padx=(6, 0))

        # 画布
        canvas = tk.Canvas(body, bg="#E8ECF0", highlightthickness=1,
                           highlightbackground=COLOR_LINE, bd=0)
        canvas.grid(row=1, column=0, sticky="nsew")
        canvas.bind("<Configure>", lambda e: self._on_canvas_resize())
        canvas.bind("<MouseWheel>", self._on_wheel)
        canvas.bind("<Button-1>", self._on_pan_start)
        canvas.bind("<B1-Motion>", self._on_pan_move)
        canvas.bind("<ButtonRelease-1>", self._on_pan_end)
        self._preview_canvas = canvas

        # 打印信息 + 提示
        self.var_printinfo = tk.StringVar(value="")
        ttk.Label(body, textvariable=self.var_printinfo, style="Muted.TLabel",
                  foreground=COLOR_PRIMARY, font=("Microsoft YaHei", 9, "bold")).grid(
            row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Label(body,
                  text="Ctrl+滚轮 缩放 · 放大后按住左键拖动平移 · 普通滚轮 翻页 · 红色虚线为打印区域",
                  style="Muted.TLabel").grid(row=3, column=0, sticky="w", pady=(2, 0))

        self._redraw_preview()

    def _on_preview_close(self):
        if self._preview_win is not None:
            self._preview_win.destroy()
        self._preview_win = None
        self._preview_canvas = None
        self._preview_pinfo = None

    # ---------------- 输入工具 ----------------
    def _read_hanzi(self):
        text = self.txt.get("1.0", "end")
        return [c for c in text if '\u4e00' <= c <= '\u9fff']

    def _read_items(self):
        """按当前字帖类型解析输入内容"""
        mode = self.var_mode.get()
        text = self.txt.get("1.0", "end")
        if mode == MODE_HANZI:
            return [c for c in text if '\u4e00' <= c <= '\u9fff']
        if mode == MODE_TINGXIE:
            return [ln.strip() for ln in text.splitlines() if ln.strip()]
        if mode == MODE_PINYIN:
            return [t for t in text.replace("\n", " ").split() if t.strip()]
        return []  # 空白模板

    def _fill_example(self):
        self.txt.delete("1.0", "end")
        if self.var_mode.get() == MODE_HANZI:
            self.txt.insert("1.0", "堂表兄弟姐妹姑阿舅爸妈我叔伯父")
        elif self.var_mode.get() == MODE_TINGXIE:
            self.txt.insert("1.0", "学校\n老师\n同学\n天气真好")
        elif self.var_mode.get() == MODE_PINYIN:
            self.txt.insert("1.0", "a o e b p m f ai ei ui")
        self._update_input_stats()

    def _clear_input(self):
        self.txt.delete("1.0", "end")
        self._update_input_stats()

    def _on_mode_change(self):
        """字帖类型切换：动态显示参数、更新提示/标题、禁用不适用的项"""
        mode = self.var_mode.get()
        # 动态参数显隐
        show_repeat = mode == MODE_TINGXIE
        show_groups = mode == MODE_PINYIN
        show_blank = mode == MODE_BLANK
        for w, show in ((self.lb_repeat, show_repeat), (self.sp_repeat, show_repeat),
                        (self.lb_groups, show_groups), (self.sp_groups, show_groups),
                        (self.lb_blank, show_blank), (self.cb_blank, show_blank)):
            (w.grid() if show else w.grid_remove())
        # 提示
        self.var_hint.set(MODE_HINTS.get(mode, ""))
        # 标题默认值（仅当用户没改过标题时跟随）
        default_titles = {MODE_HANZI: "汉字字帖", MODE_TINGXIE: "看拼音写词语",
                          MODE_PINYIN: "拼音四线三格", MODE_BLANK: "空白字帖模板"}
        if self.var_title.get() in default_titles.values():
            self.var_title.set(default_titles[mode])
        # OCR 仅汉字模式可用
        if self._ocr_btn is not None:
            self._ocr_btn.set_state("normal" if mode == MODE_HANZI else "disabled")
        # 笔画样式仅汉字模式可用
        self.cmb_stroke.configure(state="readonly" if mode == MODE_HANZI else "disabled")
        self._update_input_stats()
        if hasattr(self, "var_printinfo"):
            self._update_printinfo()

    def _update_input_stats(self):
        mode = self.var_mode.get()
        items = self._read_items()
        if mode == MODE_HANZI:
            self.var_count.set(f"已输入 {len(items)} 字")
            if not items:
                self.var_coverage.set("输入后自动检查离线字库覆盖情况")
                return
            offline = sum(1 for c in items if core.char_data_path(c))
            need = len(items) - offline
            if need == 0:
                self.var_coverage.set(f"离线字库：{offline} 字全部直接可用，无需联网")
            else:
                self.var_coverage.set(f"离线字库 {offline} 字可用 · {need} 字将联网下载")
        elif mode == MODE_TINGXIE:
            self.var_count.set(f"已输入 {len(items)} 个词语")
            self.var_coverage.set("每个词自动生成带声调拼音 + 空格田字格，重复行供反复听写")
        elif mode == MODE_PINYIN:
            self.var_count.set(f"已输入 {len(items)} 个拼音项")
            self.var_coverage.set("每组 = 1 个浅灰示例格 + 空白格临摹")
        else:
            self.var_count.set("空白模板")
            self.var_coverage.set("选择模板类型后直接生成，无需输入")

    # ---------------- 状态 ----------------
    def _set_busy(self, busy):
        self._busy = busy
        st = "disabled" if self._busy else "normal"
        self.btn_preview.set_state(st)
        self.btn_export.set_state(st)

    def _set_status(self, msg):
        self.var_status.set(msg)

    def _set_progress(self, val):
        self.progress["value"] = val

    def _set_progress_mode(self, indeterminate):
        self.progress.configure(mode="indeterminate" if indeterminate else "determinate")
        if indeterminate:
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress["value"] = 0

    def _current_params(self):
        return (self.var_title.get().strip() or "汉字字帖",
                max(5, min(30, self.var_perpage.get())),
                max(5, min(20, self.var_grids.get())),
                max(0, min(60, self.var_margin_t.get())),
                max(0, min(60, self.var_margin_b.get())),
                max(0, min(60, self.var_margin_l.get())),
                max(0, min(60, self.var_margin_r.get())),
                bool(self.var_show_pinyin.get()),
                bool(self.var_align_rows.get()),
                self.var_mode.get(),
                max(1, min(6, self.var_repeat.get())),
                max(2, min(8, self.var_groups.get())),
                self.var_blank_kind.get(),
                self.var_grid_color.get(),
                self.var_stroke_style.get())

    def _build_paper(self, params):
        _t, _p, _g, mt, mb, ml, mr = params[:7]
        mm = 300 / 25.4
        paper = dict(core.DEFAULT_A4)
        paper["margin_t"] = int(mt * mm)
        paper["margin_b"] = int(mb * mm)
        paper["margin_l"] = int(ml * mm)
        paper["margin_r"] = int(mr * mm)
        return paper

    def _on_margin_change(self):
        self._update_printinfo()
        self._redraw_preview()

    # ---------------- OCR 识别 ----------------
    def _on_ocr_click(self):
        if self._busy:
            messagebox.showinfo("提示", "有任务正在进行，请稍候。")
            return
        path = filedialog.askopenfilename(
            title="选择要识别的图片",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.bmp *.webp"),
                       ("所有文件", "*.*")])
        if not path:
            return
        self._set_busy(True)
        self._set_progress_mode(True)
        self._set_status("正在识别图片文字…（首次使用需加载模型，约几秒）")
        t = threading.Thread(target=self._ocr_worker, args=(path,), daemon=True)
        t.start()

    def _ocr_worker(self, path):
        try:
            chars, lines = ocr.extract_hanzi(path, dedup=self.var_dedup.get())
            self._queue.put(("ocr_result", chars, lines, path))
        except Exception as e:
            self._queue.put(("error", f"图片识别失败：{e}"))

    # ---------------- 预览渲染 ----------------
    def _on_preview_click(self):
        if self._busy:
            messagebox.showinfo("提示", "有任务正在进行，请稍候。")
            return
        mode = self.var_mode.get()
        items = self._read_items()
        if mode != MODE_BLANK and not items:
            if mode == MODE_HANZI:
                messagebox.showwarning("提示", "请先输入要练习的汉字。")
            elif mode == MODE_TINGXIE:
                messagebox.showwarning("提示", "请先输入词语，每行一个。")
            else:
                messagebox.showwarning("提示", "请先输入拼音字母或音节。")
            return
        params = self._current_params()
        self._set_busy(True)
        self._set_progress_mode(False)
        if mode == MODE_BLANK:
            self._set_status("正在生成空白模板…")
        else:
            self._set_status(f"正在渲染 {len(items)} 项字帖…（离线没有的字会自动下载）")
        t = threading.Thread(target=self._render_worker, args=(items, params, "preview"),
                             daemon=True)
        t.start()

    def _render_worker(self, items, params, purpose):
        title, per_page, grids = params[:3]
        show_pinyin = params[7]
        align_rows = params[8]
        mode = params[9]
        repeat = params[10]
        groups = params[11]
        blank_kind = params[12]
        grid_color = params[13]
        stroke_style = params[14]
        paper = self._build_paper(params)
        try:
            def prog(done, total, ok):
                if total > 20:
                    self._queue.put(("progress", int(done * 100 / max(total, 1)),
                                     f"下载笔画数据 {done}/{total}（成功 {ok}）"))
                else:
                    self._queue.put(("progress", int(done * 100 / max(total, 1)),
                                     f"渲染页面 {done}/{total}"))
            fails = []
            if mode == MODE_HANZI:
                stroke_style_key = core.STROKE_STYLE_NAMES.get(stroke_style,
                                                               core.DEFAULT_STROKE_STYLE)
                pages, fails = core.render_zitie(
                    items, title=title, per_page=per_page, grids_per_row=grids,
                    paper=paper, show_pinyin=show_pinyin, align_rows=align_rows,
                    grid_color=grid_color, stroke_style=stroke_style_key,
                    progress=prog)
            elif mode == MODE_TINGXIE:
                pages = core.render_tingxie(items, title=title, per_page=per_page,
                                            grids_per_row=grids, repeat=repeat,
                                            paper=paper, grid_color=grid_color,
                                            progress=prog)
            elif mode == MODE_PINYIN:
                pages = core.render_pinyin(items, title=title, per_page=per_page,
                                           groups_per_row=groups, paper=paper,
                                           grid_color=grid_color, progress=prog)
            else:
                kind_map = {"米字格": "mi", "田字格": "tian", "四线三格": "pinyin"}
                pages = core.render_blank(kind_map.get(blank_kind, "mi"),
                                          title=title, per_page=per_page,
                                          grids_per_row=grids, paper=paper,
                                          grid_color=grid_color)
            self._queue.put((purpose + "_result", pages, fails, params))
        except Exception as e:
            self._queue.put(("error", f"渲染失败：{e}"))

    def _apply_render_result(self, pages, fails, params):
        self._set_busy(False)
        self._set_progress(100)
        self._pages_img = pages
        self._page_idx = 0
        self._preview_params = params
        self._pdf_path = None
        self._fit_mode = "page"
        self._off_x = self._off_y = 0.0
        self._ensure_preview_window()
        self._redraw_preview()
        extra = f"；{len(fails)} 字缺少数据被跳过：{' '.join(fails)}" if fails else ""
        self._set_status(f"✅ 预览已生成：共 {len(pages)} 页{extra}，满意后可点“导出 PDF”")

    # ---------------- 导出 PDF ----------------
    def _on_export_click(self):
        if self._busy:
            messagebox.showinfo("提示", "有任务正在进行，请稍候。")
            return
        mode = self.var_mode.get()
        items = self._read_items()
        if mode != MODE_BLANK and not items:
            messagebox.showwarning("提示", "请先输入内容再导出。")
            return
        params = self._current_params()
        if self._pages_img and self._preview_params == params:
            self._ask_save_and_export()
            return
        self._set_busy(True)
        self._set_progress_mode(False)
        self._set_status("正在按最新参数渲染…（完成后自动导出）")
        t = threading.Thread(target=self._render_worker, args=(items, params, "export"),
                             daemon=True)
        t.start()

    def _ask_save_and_export(self):
        title = self._preview_params[0] if self._preview_params else "汉字字帖"
        out_path = filedialog.asksaveasfilename(
            title="导出字帖 PDF", defaultextension=".pdf",
            initialfile=f"{title}.pdf", filetypes=[("PDF 文件", "*.pdf")])
        if not out_path:
            self._set_status("已取消导出。")
            return
        try:
            core.pages_to_pdf(self._pages_img, out_path)
            self._pdf_path = out_path
            self._set_status(f"✅ 已导出：{out_path}")
            messagebox.showinfo("完成",
                                f"字帖已导出到：\n{out_path}\n\n可点“打开 PDF”查看或直接打印。")
        except Exception as e:
            self._set_busy(False)
            self._set_status(f"导出失败：{e}")
            messagebox.showerror("导出失败", str(e))

    # ---------------- 后台消息 ----------------
    def _poll_queue(self):
        try:
            while True:
                msg = self._queue.get_nowait()
                self._handle_msg(msg)
        except queue.Empty:
            pass
        self.root.after(120, self._poll_queue)

    def _handle_msg(self, msg):
        kind = msg[0]
        if kind == "progress":
            _k, pct, text = msg
            self._set_progress(pct)
            self._set_status(text)
        elif kind == "ocr_result":
            _k, chars, lines, path = msg
            self._set_busy(False)
            self._set_progress_mode(False)
            if not chars:
                self._set_status("未能从图片中识别到汉字。请换更清晰的图片试试。")
                messagebox.showinfo("提示", "没有识别到汉字。请确认图片清晰、文字为正体。")
                return
            self.txt.delete("1.0", "end")
            text = "".join(chars)
            rows = "\n".join(text[i:i + 15] for i in range(0, len(text), 15))
            self.txt.insert("1.0", rows)
            self._update_input_stats()
            self._set_status(
                f"✅ 识别成功：共 {len(chars)} 个汉字（来源：{os.path.basename(path)}），可预览。")
        elif kind == "preview_result":
            _k, pages, fails, params = msg
            self._apply_render_result(pages, fails, params)
        elif kind == "export_result":
            _k, pages, fails, params = msg
            self._apply_render_result(pages, fails, params)
            self._ask_save_and_export()
        elif kind == "error":
            self._set_busy(False)
            self._set_progress_mode(False)
            self._set_status(msg[1])
            messagebox.showerror("出错了", msg[1])

    # ---------------- 预览显示（缩放/平移） ----------------
    def _canvas(self):
        return self._preview_canvas

    def _on_canvas_resize(self):
        if self._fit_mode in ("page", "width"):
            self._redraw_preview()

    def _cur_scale(self):
        if not self._pages_img:
            return 1.0
        img = self._pages_img[self._page_idx]
        cv = self._canvas()
        cw = (cv.winfo_width() if cv else 0) or 1
        ch = (cv.winfo_height() if cv else 0) or 1
        if self._fit_mode == "page":
            return min(cw / img.width, ch / img.height)
        if self._fit_mode == "width":
            return cw / img.width
        return self._scale

    def _redraw_preview(self):
        cv = self._canvas()
        if cv is None:
            return
        cv.delete("all")
        if not self._pages_img:
            cw = cv.winfo_width() or 300
            ch = cv.winfo_height() or 300
            cv.create_text(cw / 2, ch / 2 - 16, text="输入汉字后点“预览字帖”",
                           fill="#98A2AE", font=("Microsoft YaHei", 14))
            cv.create_text(cw / 2, ch / 2 + 16, text="先看效果，满意再导出 PDF",
                           fill="#B8C1CA", font=("Microsoft YaHei", 11))
            self.var_pageno.set("尚未生成")
            self.var_zoom.set("100%")
            self._update_printinfo()
            return
        img = self._pages_img[self._page_idx]
        cw = cv.winfo_width() or 300
        ch = cv.winfo_height() or 300
        scale = self._cur_scale()
        nw = max(1, int(img.width * scale))
        nh = max(1, int(img.height * scale))

        maxx = max(0, nw - cw)
        maxy = max(0, nh - ch)
        self._off_x = min(max(0, self._off_x), maxx)
        self._off_y = min(max(0, self._off_y), maxy)

        if nw <= cw:
            x0 = (cw - nw) // 2
        else:
            x0 = -int(self._off_x)
        if nh <= ch:
            y0 = (ch - nh) // 2
        else:
            y0 = -int(self._off_y)

        cv.create_rectangle(x0, y0, x0 + nw, y0 + nh,
                            fill="white", outline=COLOR_LINE)
        thumb = img.resize((nw, nh), Image.BILINEAR)
        self._preview_photo = ImageTk.PhotoImage(thumb)
        cv.create_image(x0, y0, image=self._preview_photo, anchor="nw")

        if self.var_show_margin.get():
            _t, _p, _g, mt, mb, ml, mr = self._current_params()[:7]
            mm = 300 / 25.4
            x1 = x0 + ml * mm * scale
            y1 = y0 + mt * mm * scale
            x2 = x0 + nw - mr * mm * scale
            y2 = y0 + nh - mb * mm * scale
            if x2 > x1 and y2 > y1:
                cv.create_rectangle(x1, y1, x2, y2,
                                    outline="#E8573A", dash=(7, 5), width=1)
                cv.create_text(x1 + 6, y1 + 3, anchor="nw",
                               text=f"打印区域（边距 上{int(mt)} 下{int(mb)} 左{int(ml)} 右{int(mr)}mm）",
                               fill="#E8573A", font=("Microsoft YaHei", 8))

        self.var_pageno.set(f"第 {self._page_idx + 1} / {len(self._pages_img)} 页")
        self.var_zoom.set(f"{int(scale * 100)}%")
        self._update_printinfo()

    def _update_printinfo(self):
        _t, per_page, _g, mt, mb, ml, mr = self._current_params()[:7]
        n = len(self._pages_img)
        if not n:
            self.var_printinfo.set(
                f"打印设置：A4 纸(210×297mm) · 页边距 上{int(mt)} 下{int(mb)} 左{int(ml)} 右{int(mr)}mm · 每页{per_page}行")
        else:
            self.var_printinfo.set(
                f"打印预览：A4 纸(210×297mm) · 页边距 上{int(mt)} 下{int(mb)} 左{int(ml)} 右{int(mr)}mm"
                f" · 每页{per_page}行 · 共{n}页")

    def _zoom_in(self):
        if self._pages_img and self._canvas():
            self._zoom_at(self._canvas().winfo_width() / 2,
                          self._canvas().winfo_height() / 2, ZOOM_STEP)

    def _zoom_out(self):
        if self._pages_img and self._canvas():
            self._zoom_at(self._canvas().winfo_width() / 2,
                          self._canvas().winfo_height() / 2, 1 / ZOOM_STEP)

    def _zoom_fit(self):
        if not self._pages_img:
            return
        self._fit_mode = "page"
        self._off_x = self._off_y = 0.0
        self._redraw_preview()

    def _zoom_actual(self):
        if not self._pages_img:
            return
        self._fit_mode = None
        self._scale = 1.0
        self._off_x = self._off_y = 0.0
        self._redraw_preview()

    def _zoom_at(self, cx, cy, factor):
        if not self._pages_img:
            return
        cv = self._canvas()
        if cv is None:
            return
        img = self._pages_img[self._page_idx]
        cw = cv.winfo_width() or 1
        ch = cv.winfo_height() or 1
        cur = self._cur_scale()
        new = min(max(cur * factor, ZOOM_MIN), ZOOM_MAX)
        self._fit_mode = None
        self._scale = new
        old_dw, old_dh = img.width * cur, img.height * cur
        old_x0 = (cw - old_dw) / 2 if old_dw <= cw else -self._off_x
        old_y0 = (ch - old_dh) / 2 if old_dh <= ch else -self._off_y
        img_x = cx - old_x0
        img_y = cy - old_y0
        ndw, ndh = img.width * new, img.height * new
        if ndw <= cw:
            self._off_x = 0.0
        else:
            self._off_x = min(max(cx - img_x, 0), ndw - cw)
        if ndh <= ch:
            self._off_y = 0.0
        else:
            self._off_y = min(max(cy - img_y, 0), ndh - ch)
        self._redraw_preview()

    def _on_wheel(self, e):
        if not self._pages_img:
            return
        if e.state & 0x0004:
            factor = ZOOM_STEP if e.delta > 0 else 1 / ZOOM_STEP
            self._zoom_at(e.x, e.y, factor)
        else:
            self._page_idx -= 1 if e.delta > 0 else -1
            self._page_idx = min(max(self._page_idx, 0), len(self._pages_img) - 1)
            self._redraw_preview()

    def _on_pan_start(self, e):
        self._pan_anchor = (e.x, e.y, self._off_x, self._off_y)

    def _on_pan_move(self, e):
        if not self._pages_img or not self._pan_anchor:
            return
        cv = self._canvas()
        if cv is None:
            return
        img = self._pages_img[self._page_idx]
        cw = cv.winfo_width() or 1
        ch = cv.winfo_height() or 1
        scale = self._cur_scale()
        nw, nh = img.width * scale, img.height * scale
        if nw <= cw and nh <= ch:
            return
        sx, sy, ox, oy = self._pan_anchor
        maxx = max(0, nw - cw)
        maxy = max(0, nh - ch)
        self._off_x = min(max(ox + (sx - e.x), 0), maxx)
        self._off_y = min(max(oy + (sy - e.y), 0), maxy)
        self._redraw_preview()

    def _on_pan_end(self, _e):
        self._pan_anchor = None

    # ---------------- 页码与打开 ----------------
    def _prev_page(self):
        if self._pages_img and self._page_idx > 0:
            self._page_idx -= 1
            self._redraw_preview()

    def _next_page(self):
        if self._pages_img and self._page_idx < len(self._pages_img) - 1:
            self._page_idx += 1
            self._redraw_preview()

    def _open_pdf(self):
        if not self._pdf_path or not os.path.exists(self._pdf_path):
            messagebox.showinfo("提示", "请先点“导出 PDF”生成文件。")
            return
        try:
            os.startfile(self._pdf_path)
        except Exception as e:
            messagebox.showerror("错误", f"无法打开 PDF：{e}")


# ---------------- 自检 ----------------
def selftest():
    print(f"=== {APP_NAME} {APP_VERSION} 自检 ===")
    outdir = tempfile.mkdtemp(prefix="zitie_selftest_")
    try:
        pages, fails = core.render_zitie("堂表兄弟姐妹擦", title="自检字帖")
        print(f"[OK] 渲染预览: {len(pages)} 页, 失败字={fails}")
        pdf = os.path.join(outdir, "selftest.pdf")
        core.pages_to_pdf(pages, pdf)
        print(f"[OK] 导出 PDF: 存在={os.path.exists(pdf)}")
    except Exception as e:
        print(f"[FAIL] 渲染/导出异常: {type(e).__name__}: {e}")
    try:
        img = Image.new("RGB", (800, 160), "white")
        d = ImageDraw.Draw(img)
        f = core.load_font(80)
        d.text((20, 40), "堂表兄", fill="black", font=f)
        src = os.path.join(outdir, "ocr_src.png")
        img.save(src)
        chars, lines = ocr.extract_hanzi(src, dedup=True)
        print(f"[OK] OCR 识别: 识别到 {len(chars)} 字 -> {''.join(chars)}")
    except Exception as e:
        print(f"[FAIL] OCR 异常: {type(e).__name__}: {e}")
    print("=== 自检完成 ===")


def main():
    root = tk.Tk()
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    ZitieApp(root)
    root.mainloop()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
        sys.exit(0)
    main()

