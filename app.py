from __future__ import annotations

import json
import os
import sys
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk


APP_NAME = "FluoroLayout"
CHANNELS = ("blue", "green", "red", "brightfield")


@dataclass
class Group:
    name: str = "实验组"
    blue: str = ""
    green: str = ""
    red: str = ""
    brightfield: str = ""
    included_channels: dict[str, bool] = field(default_factory=lambda: {
        "blue": True, "green": True, "red": True, "brightfield": True
    })
    # Relative coordinates (x0, y0, x1, y1), independent of source resolution.
    roi: list[float] = field(default_factory=lambda: [0.55, 0.10, 0.92, 0.47])


@dataclass
class Settings:
    low_percentile: float = 0.2
    high_percentile: float = 99.8
    gamma: float = 1.0
    panel_width: int = 700
    gap: int = 30
    row_gap: int = 46
    font_size: int = 70
    group_label_width: int = 250
    dpi: int = 600
    draw_roi: bool = False
    roi_color: str = "white"
    roi_line_width: int = 5
    roi_shape: str = "custom"  # custom | square
    square_size_fraction: float = 0.35  # fraction of the image's shorter side
    square_size_px: int = 0  # exact source-image pixels; 0 uses square_size_fraction
    show_scale_bar: bool = False
    calibration_mode: str = "mpp"  # mpp | field_width
    microns_per_pixel: float = 0.325
    field_width_microns: float = 0.0
    scale_bar_microns: float = 20.0
    max_projection: bool = True
    transparent_background: bool = False
    channel_order: list[str] = field(default_factory=lambda: ["green", "red", "blue", "brightfield", "merge"])
    enabled_channels: dict[str, bool] = field(default_factory=lambda: {
        "green": True, "red": True, "blue": True, "brightfield": False, "merge": True
    })
    channel_names: dict[str, str] = field(default_factory=lambda: {
        "green": "Green", "red": "Red", "blue": "Blue",
        "brightfield": "Brightfield", "merge": "Merge"
    })
    zoom_mode: str = "none"  # none | merge | all
    zoom_placement: str = "separate"  # separate | top_right | bottom_right | top_left | bottom_left
    inset_fraction: float = 0.38
    layout_orientation: str = "horizontal"  # horizontal | vertical


def read_tiff(path: str, max_projection: bool = True) -> np.ndarray:
    """Read grayscale TIFF (8/16/32 bit), optionally max-projecting all frames."""
    if not path:
        raise ValueError("缺少通道文件")
    with Image.open(path) as im:
        frames: list[np.ndarray] = []
        n = getattr(im, "n_frames", 1)
        indices = range(n) if max_projection else range(1)
        for i in indices:
            im.seek(i)
            arr = np.asarray(im)
            if arr.ndim == 3:
                arr = arr[..., :3].astype(np.float32).mean(axis=2)
            frames.append(arr.astype(np.float32))
        if not frames:
            raise ValueError(f"无法读取图像：{path}")
        if len(frames) == 1:
            return frames[0]
        shape = frames[0].shape
        if any(x.shape != shape for x in frames):
            raise ValueError("多页 TIFF 中各帧尺寸不一致")
        return np.maximum.reduce(frames)


def normalize_channel(arr: np.ndarray, low: float, high: float, gamma: float) -> np.ndarray:
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return np.zeros(arr.shape, dtype=np.uint8)
    lo, hi = np.percentile(finite, [low, high])
    if hi <= lo:
        hi = lo + 1.0
    x = np.clip((arr - lo) / (hi - lo), 0.0, 1.0)
    if gamma > 0 and gamma != 1.0:
        x = np.power(x, 1.0 / gamma)
    return np.round(x * 255).astype(np.uint8)


def load_group_images(group: Group, settings: Settings) -> dict[str, Image.Image]:
    arrays: dict[str, np.ndarray] = {}
    base_shape: Optional[tuple[int, int]] = None
    for channel in CHANNELS:
        path = getattr(group, channel)
        if not path or not group.included_channels.get(channel, True):
            continue
        arr = read_tiff(path, settings.max_projection)
        if base_shape is None:
            base_shape = arr.shape
        elif arr.shape != base_shape:
            raise ValueError(f"{group.name} 的三个通道尺寸不一致：{arr.shape} vs {base_shape}")
        arrays[channel] = normalize_channel(
            arr, settings.low_percentile, settings.high_percentile, settings.gamma
        )
    if base_shape is None:
        raise ValueError(f"{group.name} 没有导入任何图像")
    h, w = base_shape
    zero = np.zeros((h, w), dtype=np.uint8)
    blue = arrays.get("blue", zero)
    green = arrays.get("green", zero)
    red = arrays.get("red", zero)
    brightfield = arrays.get("brightfield", zero)
    # Merge only channels explicitly enabled in the layout settings.
    merge = np.dstack([
        red if settings.enabled_channels.get("red", False) else zero,
        green if settings.enabled_channels.get("green", False) else zero,
        blue if settings.enabled_channels.get("blue", False) else zero,
    ])
    available = {c: c in arrays for c in CHANNELS}
    available["merge"] = any(c in arrays and settings.enabled_channels.get(c, False)
                             for c in ("red", "green", "blue"))
    return {
        "blue": Image.fromarray(np.dstack([zero, zero, blue]), "RGB"),
        "green": Image.fromarray(np.dstack([zero, green, zero]), "RGB"),
        "red": Image.fromarray(np.dstack([red, zero, zero]), "RGB"),
        "brightfield": Image.fromarray(np.dstack([brightfield, brightfield, brightfield]), "RGB"),
        "merge": Image.fromarray(merge, "RGB"),
        "_available": available,
    }


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def fit_panel(image: Image.Image, width: int, height: int) -> Image.Image:
    # Preserve the full field; black padding is preferable to scientific distortion/cropping.
    out = Image.new("RGB", (width, height), "black")
    copy = image.copy()
    copy.thumbnail((width, height), Image.Resampling.LANCZOS)
    out.paste(copy, ((width - copy.width) // 2, (height - copy.height) // 2))
    return out


def crop_roi(image: Image.Image, roi: list[float]) -> Image.Image:
    x0, y0, x1, y1 = roi
    x0, x1 = sorted((max(0.0, min(1.0, x0)), max(0.0, min(1.0, x1))))
    y0, y1 = sorted((max(0.0, min(1.0, y0)), max(0.0, min(1.0, y1))))
    if x1 - x0 < 0.01 or y1 - y0 < 0.01:
        raise ValueError("放大框太小，请重新框选")
    box = (round(x0 * image.width), round(y0 * image.height),
           round(x1 * image.width), round(y1 * image.height))
    return image.crop(box)


def effective_roi(group: Group, image: Image.Image, settings: Settings) -> list[float]:
    """Return the actual ROI, enforcing a pixel-square when square mode is active."""
    if settings.roi_shape != "square":
        return list(group.roi)
    cx = (group.roi[0] + group.roi[2]) / 2
    cy = (group.roi[1] + group.roi[3]) / 2
    if settings.square_size_px > 0:
        side_px = max(4.0, min(float(settings.square_size_px), image.width, image.height))
    else:
        side_px = max(4.0, min(image.width, image.height) *
                      max(0.05, min(0.95, settings.square_size_fraction)))
    half_x = side_px / (2 * image.width)
    half_y = side_px / (2 * image.height)
    cx = min(max(cx, half_x), 1.0 - half_x)
    cy = min(max(cy, half_y), 1.0 - half_y)
    return [cx - half_x, cy - half_y, cx + half_x, cy + half_y]


def draw_scale_bar(panel: Image.Image, settings: Settings, source_width: int,
                   crop_fraction: float = 1.0) -> None:
    if settings.calibration_mode == "field_width":
        microns_per_pixel = settings.field_width_microns / source_width
    else:
        microns_per_pixel = settings.microns_per_pixel
    if not settings.show_scale_bar or microns_per_pixel <= 0:
        return
    # source px represented by one output px after crop and resizing
    represented_source_width = source_width * crop_fraction
    output_px = settings.scale_bar_microns / microns_per_pixel
    output_px *= panel.width / represented_source_width
    length = max(2, min(panel.width * 0.6, round(output_px)))
    margin = max(12, panel.width // 35)
    thickness = max(4, panel.width // 110)
    y = panel.height - margin
    x1 = panel.width - margin
    x0 = round(x1 - length)
    d = ImageDraw.Draw(panel)
    d.line((x0, y, x1, y), fill="white", width=thickness)
    label = f"{settings.scale_bar_microns:g} μm"
    f = font(max(16, panel.width // 35), bold=True)
    box = d.textbbox((0, 0), label, font=f)
    tw = box[2] - box[0]
    d.text((x0 + (length - tw) / 2, y - (box[3] - box[1]) - thickness - 5),
           label, font=f, fill="white", stroke_width=2, stroke_fill="black")


def build_figure(groups: list[Group], settings: Settings) -> Image.Image:
    if not groups:
        raise ValueError("请至少添加一个实验组")
    if settings.show_scale_bar:
        if settings.scale_bar_microns <= 0:
            raise ValueError("要显示的比例尺长度必须大于 0 μm。")
        if settings.calibration_mode == "field_width" and settings.field_width_microns <= 0:
            raise ValueError("当前选择“整图视野宽度 μm”标定，请输入大于 0 的视野宽度。")
        if settings.calibration_mode != "field_width" and settings.microns_per_pixel <= 0:
            raise ValueError("当前选择“μm/px”标定，请输入大于 0 的 μm/px。")
    loaded = [load_group_images(g, settings) for g in groups]
    ratios = [imgs["merge"].height / imgs["merge"].width for imgs in loaded]
    panel_w = settings.panel_width
    panel_h = max(100, round(panel_w * float(np.median(ratios))))
    supported = ("green", "red", "blue", "brightfield", "merge")
    valid_channels = [c for c in settings.channel_order
                      if c in supported and settings.enabled_channels.get(c, False)]
    for c in supported:
        if settings.enabled_channels.get(c, False) and c not in valid_channels:
            valid_channels.append(c)
    if not valid_channels:
        raise ValueError("请至少启用一个通道")
    default_names = {"green": "Green", "red": "Red", "blue": "Blue",
                     "brightfield": "Brightfield", "merge": "Merge"}
    names = {c: str(settings.channel_names.get(c, default_names[c])).strip() or default_names[c]
             for c in default_names}
    title_colors = {"green": (0, 150, 45), "red": (220, 25, 35),
                    "blue": (25, 90, 225), "brightfield": (105, 90, 65),
                    "merge": (35, 35, 35)}
    # Each entry is (source channel or composite marker, displayed title, is zoom panel).
    entries: list[tuple[str, str, bool]] = [(c, names[c], False) for c in valid_channels]
    if settings.zoom_mode == "all":
        zoom_channels = list(valid_channels)
    elif settings.zoom_mode == "merge" and "merge" in valid_channels:
        zoom_channels = ["merge"]
    else:
        zoom_channels = []
    if settings.zoom_placement == "separate" and zoom_channels:
        zoom_title = "Zoom" if settings.zoom_mode == "all" else f"{names['merge']} Zoom"
        entries.append(("zoom_grid", zoom_title, True))
    top = settings.font_size * 2 + settings.gap
    left = settings.group_label_width
    if settings.layout_orientation == "vertical":
        width = left + len(groups) * panel_w + (len(groups) - 1) * settings.gap
        height = top + len(entries) * panel_h + (len(entries) - 1) * settings.row_gap
    else:
        width = left + len(entries) * panel_w + (len(entries) - 1) * settings.gap
        height = top + len(groups) * panel_h + (len(groups) - 1) * settings.row_gap
    if settings.transparent_background:
        canvas = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    else:
        canvas = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(canvas)
    hf = font(settings.font_size, bold=True)
    gf = font(settings.font_size, bold=True)

    def centered_text(label: str, cx: float, cy: float, fill, use_font=hf,
                      max_width: float | None = None) -> None:
        actual_font = use_font
        box = d.textbbox((0, 0), label, font=actual_font)
        if max_width and box[2] - box[0] > max_width:
            base_size = getattr(use_font, "size", settings.font_size)
            fitted_size = max(12, int(base_size * max_width / (box[2] - box[0])))
            actual_font = font(fitted_size, bold=True)
            box = d.textbbox((0, 0), label, font=actual_font)
        d.text((cx - (box[2] - box[0]) / 2, cy - (box[3] - box[1]) / 2),
               label, fill=fill, font=actual_font)

    def paste_corner_inset(panel: Image.Image, zoom: Image.Image) -> None:
        fraction = max(0.15, min(0.65, settings.inset_fraction))
        max_w, max_h = round(panel.width * fraction), round(panel.height * fraction)
        inset = zoom.copy()
        inset.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
        border = max(2, panel.width // 180)
        framed = ImageOps.expand(inset, border=border, fill="white")
        margin = max(5, panel.width // 100)
        positions = {
            "top_left": (margin, margin),
            "top_right": (panel.width - framed.width - margin, margin),
            "bottom_left": (margin, panel.height - framed.height - margin),
            "bottom_right": (panel.width - framed.width - margin,
                             panel.height - framed.height - margin),
        }
        panel.paste(framed, positions.get(settings.zoom_placement, positions["top_right"]))

    def blank_panel() -> Image.Image:
        if settings.transparent_background:
            return Image.new("RGBA", (panel_w, panel_h), (255, 255, 255, 0))
        return Image.new("RGB", (panel_w, panel_h), "white")

    def make_zoom_grid(group: Group, imgs: dict[str, Image.Image]) -> Image.Image:
        roi = effective_roi(group, imgs["merge"], settings)
        if settings.zoom_mode != "all":
            if not imgs["_available"].get("merge", False):
                return blank_panel()
            crop = crop_roi(imgs["merge"], roi)
            panel = fit_panel(crop, panel_w, panel_h)
            draw_scale_bar(panel, settings, imgs["merge"].width, abs(roi[2] - roi[0]))
            return panel
        panel = Image.new("RGB", (panel_w, panel_h), "black")
        count = max(1, len(zoom_channels))
        cols = 1 if count == 1 else 2 if count <= 4 else 3
        rows = (count + cols - 1) // cols
        tile_gap = max(4, panel_w // 100)
        tile_w = (panel_w - (cols - 1) * tile_gap) // cols
        tile_h = (panel_h - (rows - 1) * tile_gap) // rows
        label_font = font(max(14, min(settings.font_size, panel_w // 24)), bold=True)
        for i, channel in enumerate(zoom_channels):
            if imgs["_available"].get(channel, False):
                tile = fit_panel(crop_roi(imgs[channel], roi), tile_w, tile_h)
            else:
                tile = Image.new("RGB", (tile_w, tile_h), "white")
            td = ImageDraw.Draw(tile)
            label = names[channel]
            td.text((max(4, tile_w // 40), max(2, tile_h // 50)), label,
                    fill=title_colors[channel], font=label_font,
                    stroke_width=max(1, tile_w // 250),
                    stroke_fill="white" if channel == "merge" else "black")
            x = (i % cols) * (tile_w + tile_gap)
            y = (i // cols) * (tile_h + tile_gap)
            panel.paste(tile, (x, y))
        return panel

    def make_panel(group: Group, imgs: dict[str, Image.Image], channel: str, is_zoom: bool) -> Image.Image:
        if channel == "zoom_grid":
            return make_zoom_grid(group, imgs)
        if not imgs["_available"].get(channel, False):
            return blank_panel()
        im = imgs[channel].copy()
        roi = effective_roi(group, imgs["merge"], settings)
        if settings.draw_roi:
            md = ImageDraw.Draw(im)
            x0, y0, x1, y1 = roi
            md.rectangle((round(x0 * im.width), round(y0 * im.height),
                          round(x1 * im.width), round(y1 * im.height)),
                         outline=settings.roi_color, width=settings.roi_line_width)
        panel = fit_panel(im, panel_w, panel_h)
        if channel == "merge":
            draw_scale_bar(panel, settings, imgs["merge"].width, 1.0)
        if settings.zoom_placement != "separate" and channel in zoom_channels:
            paste_corner_inset(panel, crop_roi(imgs[channel], roi))
        return panel

    if settings.layout_orientation == "vertical":
        # Experiment groups are columns; channels and zoom panels are rows.
        for gi, group in enumerate(groups):
            x = left + gi * (panel_w + settings.gap)
            centered_text(group.name, x + panel_w / 2, top / 2, "black", gf, panel_w - 12)
        for ei, (channel, label, is_zoom) in enumerate(entries):
            y = top + ei * (panel_h + settings.row_gap)
            label_color = title_colors.get(channel, (35, 35, 35))
            centered_text(label, left / 2, y + panel_h / 2, label_color, hf, left - 12)
            for gi, (group, imgs) in enumerate(zip(groups, loaded)):
                x = left + gi * (panel_w + settings.gap)
                canvas.paste(make_panel(group, imgs, channel, is_zoom), (x, y))
    else:
        # Experiment groups are rows; channels and zoom panels are columns.
        for ei, (channel, label, _is_zoom) in enumerate(entries):
            x = left + ei * (panel_w + settings.gap)
            label_color = title_colors.get(channel, (35, 35, 35))
            centered_text(label, x + panel_w / 2, top / 2, label_color, hf, panel_w - 12)
        for gi, (group, imgs) in enumerate(zip(groups, loaded)):
            y = top + gi * (panel_h + settings.row_gap)
            centered_text(group.name, left / 2, y + panel_h / 2, "black", gf, left - 12)
            for ei, (channel, _label, is_zoom) in enumerate(entries):
                x = left + ei * (panel_w + settings.gap)
                canvas.paste(make_panel(group, imgs, channel, is_zoom), (x, y))
    return canvas


class GroupDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, group: Optional[Group] = None):
        super().__init__(parent)
        self.title("添加/编辑实验组")
        self.resizable(True, False)
        self.result: Optional[Group] = None
        self.transient(parent)
        self.grab_set()
        self.vars = {
            "name": tk.StringVar(value=group.name if group else f"实验组"),
            **{c: tk.StringVar(value=getattr(group, c) if group else "") for c in CHANNELS},
        }
        frame = ttk.Frame(self, padding=14)
        frame.grid(sticky="nsew")
        ttk.Label(frame, text="组名").grid(row=0, column=0, sticky="w", padx=4, pady=6)
        ttk.Entry(frame, textvariable=self.vars["name"], width=56).grid(
            row=0, column=1, sticky="ew", padx=4, pady=6)
        names = {"blue": "蓝色 / DAPI", "green": "绿色通道", "red": "红色通道",
                 "brightfield": "明场通道"}
        for row, c in enumerate(CHANNELS, 1):
            ttk.Label(frame, text=names[c]).grid(row=row, column=0, sticky="w", padx=4, pady=6)
            ttk.Entry(frame, textvariable=self.vars[c], width=56).grid(
                row=row, column=1, sticky="ew", padx=4, pady=6)
            ttk.Button(frame, text="选择…", command=lambda ch=c: self.pick(ch)).grid(
                row=row, column=2, padx=4, pady=6)
        buttons = ttk.Frame(frame)
        buttons.grid(row=5, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="取消", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(buttons, text="确定", command=self.ok).pack(side="right", padx=4)
        frame.columnconfigure(1, weight=1)
        self.bind("<Return>", lambda _e: self.ok())
        self.bind("<Escape>", lambda _e: self.destroy())

    def pick(self, channel: str) -> None:
        path = filedialog.askopenfilename(
            parent=self, title=f"选择{channel}通道 TIFF",
            filetypes=[("TIFF images", "*.tif *.tiff"), ("Images", "*.tif *.tiff *.png *.jpg *.jpeg")])
        if path:
            self.vars[channel].set(path)

    def ok(self) -> None:
        name = self.vars["name"].get().strip()
        if not name:
            messagebox.showwarning(APP_NAME, "请填写实验组名称", parent=self)
            return
        paths = {c: self.vars[c].get().strip() for c in CHANNELS}
        if not any(paths.values()):
            messagebox.showwarning(APP_NAME, "请至少选择一个通道文件", parent=self)
            return
        missing = [p for p in paths.values() if p and not os.path.isfile(p)]
        if missing:
            messagebox.showwarning(APP_NAME, f"文件不存在：\n{missing[0]}", parent=self)
            return
        self.result = Group(name=name, **paths)
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1320x820")
        self.minsize(1020, 680)
        self.groups: list[Group] = []
        self.settings = Settings()
        self.preview_image: Optional[Image.Image] = None
        self.preview_tk: Optional[ImageTk.PhotoImage] = None
        self.preview_box: Optional[tuple[float, float, float, float]] = None
        self.drag_start: Optional[tuple[float, float]] = None
        self.roi_rect: Optional[int] = None
        self.status = tk.StringVar(value="添加实验组后即可开始")
        self.vars: dict[str, tk.Variable] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        self.option_add("*Font", ("Microsoft YaHei UI", 10))
        toolbar = ttk.Frame(self, padding=(8, 6))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="新建", command=self.new_project).pack(side="left", padx=3)
        ttk.Button(toolbar, text="打开项目", command=self.open_project).pack(side="left", padx=3)
        ttk.Button(toolbar, text="保存项目", command=self.save_project).pack(side="left", padx=3)
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(toolbar, text="生成整版预览", command=self.preview_figure).pack(side="left", padx=3)
        ttk.Button(toolbar, text="导出论文图片…", command=self.export_figure).pack(side="left", padx=3)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        left = ttk.Frame(body, padding=6)
        center = ttk.Frame(body, padding=6)
        right = ttk.Frame(body, padding=6)
        body.add(left, weight=3)
        body.add(center, weight=6)
        body.add(right, weight=3)

        ttk.Label(left, text="实验组", font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
        self.tree = ttk.Treeview(left, columns=("b", "g", "r", "roi"), show="tree headings", height=14)
        self.tree.heading("#0", text="组名")
        self.tree.heading("b", text="蓝")
        self.tree.heading("g", text="绿")
        self.tree.heading("r", text="红")
        self.tree.heading("roi", text="放大框")
        self.tree.column("#0", width=125)
        for c in ("b", "g", "r"):
            self.tree.column(c, width=34, anchor="center", stretch=False)
        self.tree.column("roi", width=58, anchor="center", stretch=False)
        self.tree.pack(fill="both", expand=True, pady=6)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.show_selected())
        self.tree.bind("<Double-1>", lambda _e: self.edit_group())
        btns = ttk.Frame(left)
        btns.pack(fill="x")
        for text_, cmd in [("添加", self.add_group), ("编辑", self.edit_group), ("删除", self.remove_group),
                           ("上移", lambda: self.move_group(-1)), ("下移", lambda: self.move_group(1))]:
            ttk.Button(btns, text=text_, command=cmd).pack(side="left", padx=2, pady=2)

        ttk.Label(center, text="合并图预览（拖动鼠标框选局部放大区域）",
                  font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
        self.canvas = tk.Canvas(center, bg="#202124", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True, pady=6)
        self.canvas.bind("<Configure>", lambda _e: self._render_preview())
        self.canvas.bind("<ButtonPress-1>", self.roi_start)
        self.canvas.bind("<B1-Motion>", self.roi_drag)
        self.canvas.bind("<ButtonRelease-1>", self.roi_end)
        ttk.Label(center, text="提示：白框会画在 Merge 图上，框内内容会作为右侧 Zoom 面板。",
                  foreground="#555").pack(anchor="w")

        ttk.Label(right, text="版式与图像设置", font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
        form = ttk.Frame(right)
        form.pack(fill="both", expand=True, pady=6)
        entries = [
            ("low_percentile", "黑场百分位", self.settings.low_percentile),
            ("high_percentile", "白场百分位", self.settings.high_percentile),
            ("gamma", "Gamma", self.settings.gamma),
            ("panel_width", "单面板宽度 px", self.settings.panel_width),
            ("gap", "列间距 px", self.settings.gap),
            ("row_gap", "行间距 px", self.settings.row_gap),
            ("font_size", "字号 px", self.settings.font_size),
            ("group_label_width", "组名栏宽度 px", self.settings.group_label_width),
            ("dpi", "导出 DPI", self.settings.dpi),
            ("roi_line_width", "放大框线宽 px", self.settings.roi_line_width),
            ("microns_per_pixel", "标定 μm/px", self.settings.microns_per_pixel),
            ("scale_bar_microns", "比例尺长度 μm", self.settings.scale_bar_microns),
        ]
        for row, (key, label, value) in enumerate(entries):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=str(value))
            self.vars[key] = var
            ttk.Entry(form, textvariable=var, width=12).grid(row=row, column=1, sticky="ew", pady=4)
        row = len(entries)
        for key, label, value in [
            ("draw_roi", "在 Merge 图标出白框", self.settings.draw_roi),
            ("show_scale_bar", "在 Merge/Zoom 添加比例尺", self.settings.show_scale_bar),
            ("max_projection", "多页 TIFF 做最大投影", self.settings.max_projection),
        ]:
            var = tk.BooleanVar(value=value)
            self.vars[key] = var
            ttk.Checkbutton(form, text=label, variable=var).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=4)
            row += 1
        ttk.Button(form, text="应用设置并刷新", command=self.apply_and_refresh).grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=(12, 4))
        form.columnconfigure(1, weight=1)

        statusbar = ttk.Label(self, textvariable=self.status, relief="sunken", anchor="w", padding=(6, 3))
        statusbar.pack(fill="x", side="bottom")

    def sync_settings(self) -> None:
        float_keys = {"low_percentile", "high_percentile", "gamma", "microns_per_pixel", "scale_bar_microns"}
        int_keys = {"panel_width", "gap", "row_gap", "font_size", "group_label_width", "dpi", "roi_line_width"}
        bool_keys = {"draw_roi", "show_scale_bar", "max_projection"}
        try:
            for key in float_keys:
                setattr(self.settings, key, float(self.vars[key].get()))
            for key in int_keys:
                setattr(self.settings, key, int(float(self.vars[key].get())))
            for key in bool_keys:
                setattr(self.settings, key, bool(self.vars[key].get()))
        except ValueError as e:
            raise ValueError("设置中含有无效数字") from e
        if not 0 <= self.settings.low_percentile < self.settings.high_percentile <= 100:
            raise ValueError("黑/白场百分位需满足 0 ≤ 黑场 < 白场 ≤ 100")
        if self.settings.gamma <= 0 or self.settings.panel_width < 100 or self.settings.dpi < 72:
            raise ValueError("Gamma 必须大于 0，面板宽度至少 100 px，DPI 至少 72")

    def refresh_tree(self, select: Optional[int] = None) -> None:
        self.tree.delete(*self.tree.get_children())
        for i, g in enumerate(self.groups):
            item = self.tree.insert("", "end", iid=str(i), text=g.name,
                                    values=tuple("✓" if getattr(g, c) else "—" for c in CHANNELS) + ("✓",))
            if select == i:
                self.tree.selection_set(item)
                self.tree.focus(item)

    def selected_index(self) -> Optional[int]:
        selected = self.tree.selection()
        return int(selected[0]) if selected else None

    def add_group(self) -> None:
        dlg = GroupDialog(self)
        self.wait_window(dlg)
        if dlg.result:
            self.groups.append(dlg.result)
            self.refresh_tree(len(self.groups) - 1)
            self.show_selected()

    def edit_group(self) -> None:
        idx = self.selected_index()
        if idx is None:
            return
        old_roi = self.groups[idx].roi
        dlg = GroupDialog(self, self.groups[idx])
        self.wait_window(dlg)
        if dlg.result:
            dlg.result.roi = old_roi
            self.groups[idx] = dlg.result
            self.refresh_tree(idx)
            self.show_selected()

    def remove_group(self) -> None:
        idx = self.selected_index()
        if idx is not None and messagebox.askyesno(APP_NAME, f"删除“{self.groups[idx].name}”？"):
            self.groups.pop(idx)
            self.refresh_tree(min(idx, len(self.groups) - 1) if self.groups else None)
            self.show_selected()

    def move_group(self, delta: int) -> None:
        idx = self.selected_index()
        if idx is None:
            return
        new = idx + delta
        if 0 <= new < len(self.groups):
            self.groups[idx], self.groups[new] = self.groups[new], self.groups[idx]
            self.refresh_tree(new)

    def show_selected(self) -> None:
        idx = self.selected_index()
        self.preview_image = None
        if idx is None:
            self.canvas.delete("all")
            return
        try:
            self.sync_settings()
            self.status.set(f"正在读取：{self.groups[idx].name}")
            self.update_idletasks()
            self.preview_image = load_group_images(self.groups[idx], self.settings)["merge"]
            self._render_preview()
            self.status.set(f"已加载 {self.groups[idx].name}：{self.preview_image.width} × {self.preview_image.height} px")
        except Exception as e:
            self.status.set("读取失败")
            messagebox.showerror(APP_NAME, str(e))

    def _render_preview(self) -> None:
        if self.preview_image is None:
            return
        cw, ch = max(2, self.canvas.winfo_width()), max(2, self.canvas.winfo_height())
        scale = min(cw / self.preview_image.width, ch / self.preview_image.height)
        w, h = max(1, round(self.preview_image.width * scale)), max(1, round(self.preview_image.height * scale))
        shown = self.preview_image.resize((w, h), Image.Resampling.LANCZOS)
        self.preview_tk = ImageTk.PhotoImage(shown)
        x, y = (cw - w) / 2, (ch - h) / 2
        self.preview_box = (x, y, x + w, y + h)
        self.canvas.delete("all")
        self.canvas.create_image(x, y, anchor="nw", image=self.preview_tk)
        idx = self.selected_index()
        if idx is not None:
            r = self.groups[idx].roi
            self.roi_rect = self.canvas.create_rectangle(
                x + r[0] * w, y + r[1] * h, x + r[2] * w, y + r[3] * h,
                outline="white", width=2)

    def roi_start(self, event: tk.Event) -> None:
        if self.preview_box and self.selected_index() is not None:
            x0, y0, x1, y1 = self.preview_box
            self.drag_start = (min(max(event.x, x0), x1), min(max(event.y, y0), y1))

    def roi_drag(self, event: tk.Event) -> None:
        if not self.drag_start or not self.preview_box:
            return
        x0, y0, x1, y1 = self.preview_box
        x, y = min(max(event.x, x0), x1), min(max(event.y, y0), y1)
        if self.roi_rect:
            self.canvas.coords(self.roi_rect, self.drag_start[0], self.drag_start[1], x, y)

    def roi_end(self, event: tk.Event) -> None:
        idx = self.selected_index()
        if idx is None or not self.drag_start or not self.preview_box:
            return
        bx0, by0, bx1, by1 = self.preview_box
        x = min(max(event.x, bx0), bx1)
        y = min(max(event.y, by0), by1)
        sx, sy = self.drag_start
        rx0, rx1 = sorted(((sx - bx0) / (bx1 - bx0), (x - bx0) / (bx1 - bx0)))
        ry0, ry1 = sorted(((sy - by0) / (by1 - by0), (y - by0) / (by1 - by0)))
        self.drag_start = None
        if rx1 - rx0 < 0.01 or ry1 - ry0 < 0.01:
            self._render_preview()
            return
        self.groups[idx].roi = [rx0, ry0, rx1, ry1]
        self.status.set(f"{self.groups[idx].name} 放大区域已更新")
        self.refresh_tree(idx)
        self._render_preview()

    def apply_and_refresh(self) -> None:
        try:
            self.sync_settings()
            self.show_selected()
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e))

    def make_figure(self) -> Image.Image:
        self.sync_settings()
        self.status.set("正在生成整版图片…")
        self.update_idletasks()
        figure = build_figure(self.groups, self.settings)
        self.status.set(f"整版图片已生成：{figure.width} × {figure.height} px")
        return figure

    def preview_figure(self) -> None:
        try:
            figure = self.make_figure()
            win = tk.Toplevel(self)
            win.title("整版预览")
            win.geometry("1100x760")
            canvas = tk.Canvas(win, bg="#777")
            canvas.pack(fill="both", expand=True)
            state: dict[str, object] = {"image": figure, "photo": None}

            def redraw(_event=None):
                cw, ch = max(10, canvas.winfo_width()), max(10, canvas.winfo_height())
                ratio = min(cw / figure.width, ch / figure.height)
                shown = figure.resize((max(1, round(figure.width * ratio)), max(1, round(figure.height * ratio))),
                                      Image.Resampling.LANCZOS)
                state["photo"] = ImageTk.PhotoImage(shown)
                canvas.delete("all")
                canvas.create_image(cw / 2, ch / 2, image=state["photo"], anchor="center")
            canvas.bind("<Configure>", redraw)
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e))

    def export_figure(self) -> None:
        try:
            figure = self.make_figure()
            path = filedialog.asksaveasfilename(
                parent=self, title="导出论文图片", defaultextension=".tif",
                filetypes=[("TIFF（推荐）", "*.tif"), ("PNG", "*.png"), ("JPEG", "*.jpg")])
            if not path:
                return
            ext = Path(path).suffix.lower()
            kwargs = {"dpi": (self.settings.dpi, self.settings.dpi)}
            if ext in (".tif", ".tiff"):
                kwargs["compression"] = "tiff_lzw"
            elif ext in (".jpg", ".jpeg"):
                kwargs["quality"] = 95
            figure.save(path, **kwargs)
            self.status.set(f"已导出：{path}")
            messagebox.showinfo(APP_NAME, f"导出完成\n{figure.width} × {figure.height} px\n{self.settings.dpi} DPI\n\n{path}")
        except Exception as e:
            messagebox.showerror(APP_NAME, f"导出失败：{e}")

    def new_project(self) -> None:
        if self.groups and not messagebox.askyesno(APP_NAME, "清空当前项目并新建？"):
            return
        self.groups = []
        self.settings = Settings()
        for key, var in self.vars.items():
            var.set(getattr(self.settings, key))
        self.refresh_tree()
        self.canvas.delete("all")
        self.status.set("新项目")

    def save_project(self) -> None:
        try:
            self.sync_settings()
            path = filedialog.asksaveasfilename(parent=self, defaultextension=".ifp",
                                                filetypes=[("免疫荧光排版项目", "*.ifp"), ("JSON", "*.json")])
            if path:
                payload = {"version": 1, "groups": [asdict(g) for g in self.groups],
                           "settings": asdict(self.settings)}
                Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                self.status.set(f"项目已保存：{path}")
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e))

    def open_project(self) -> None:
        path = filedialog.askopenfilename(parent=self,
                                          filetypes=[("免疫荧光排版项目", "*.ifp *.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self.groups = [Group(**g) for g in data.get("groups", [])]
            self.settings = Settings(**data.get("settings", {}))
            for key, var in self.vars.items():
                var.set(getattr(self.settings, key))
            self.refresh_tree(0 if self.groups else None)
            self.show_selected()
            self.status.set(f"项目已打开：{path}")
        except Exception as e:
            messagebox.showerror(APP_NAME, f"打开项目失败：{e}")


def main() -> None:
    try:
        app = App()
        app.mainloop()
    except Exception:
        traceback.print_exc()
        messagebox.showerror(APP_NAME, "程序发生错误，请查看终端输出。")


if __name__ == "__main__":
    main()
