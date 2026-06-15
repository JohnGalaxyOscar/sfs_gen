# terrain_preview.py
import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Qt, QTimer
import json

from utils import clean_float, get_mass_factor, compute_soi_radius, orbit_points, body_color


class TerrainPreviewWidget(QWidget):
    """地形预览控件，极坐标显示星球地形及大气/光环标记，支持鼠标拖拽平移和滚轮缩放"""
    # 类级别缓存地形函数数据
    _heightmap_cache = {}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_body = None
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._do_update)

        self._setup_ui()
        self._setup_interaction()

        # 交互状态
        self._pan_start = None
        self._pan_start_data = None
        self._view_xlim = None   # 当前视图X范围 (left, right)
        self._view_ylim = None   # 当前视图Y范围 (bottom, top)

        # 地形数据
        self._theta_deg = None
        self._elevations = None

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)   # 增加边距，防止标题紧贴边缘

        # 标题
        title_label = QLabel("地形预览")
        title_label.setStyleSheet("font-weight: bold; font-size: 12pt; margin-bottom: 5px;")
        layout.addWidget(title_label)

        # 按钮栏
        btn_layout = QHBoxLayout()
        self.btn_zoom_in = QPushButton("缩小 -")
        self.btn_zoom_out = QPushButton("放大 +")
        self.btn_reset = QPushButton("重置视图")
        self.btn_refresh = QPushButton("刷新地形")
        btn_layout.addWidget(self.btn_zoom_in)
        btn_layout.addWidget(self.btn_zoom_out)
        btn_layout.addWidget(self.btn_reset)
        btn_layout.addWidget(self.btn_refresh)
        layout.addLayout(btn_layout)

        # 画布
        self.figure = Figure(figsize=(5, 4), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

        self.ax = None

        self.btn_zoom_in.clicked.connect(self._zoom_in)
        self.btn_zoom_out.clicked.connect(self._zoom_out)
        self.btn_reset.clicked.connect(self.reset_view)

    def _setup_interaction(self):
        self.canvas.mpl_connect('scroll_event', self._on_scroll)
        self.canvas.mpl_connect('button_press_event', self._on_press)
        self.canvas.mpl_connect('button_release_event', self._on_release)
        self.canvas.mpl_connect('motion_notify_event', self._on_motion)

    def _on_scroll(self, event):
        if self.ax is None or event.inaxes != self.ax:
            return
        scale_factor = 1.2 if event.step > 0 else 0.8
        xdata, ydata = event.xdata, event.ydata
        if xdata is None or ydata is None:
            return
        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()
        new_xlim = [xdata - (xdata - xlim[0]) * scale_factor,
                    xdata + (xlim[1] - xdata) * scale_factor]
        new_ylim = [ydata - (ydata - ylim[0]) * scale_factor,
                    ydata + (ylim[1] - ydata) * scale_factor]
        self._view_xlim = tuple(new_xlim)
        self._view_ylim = tuple(new_ylim)
        self._schedule_update(redraw_only=True)

    def _on_press(self, event):
        if self.ax is None or event.inaxes != self.ax:
            return
        self._pan_start = (event.x, event.y)
        self._pan_start_data = (event.xdata, event.ydata)   # 新增

    def _on_release(self, event):
        self._pan_start = None

    def _on_motion(self, event):
        if self._pan_start is None or self.ax is None or event.inaxes != self.ax:
            return
        xdata_now = event.xdata
        ydata_now = event.ydata
        if xdata_now is None or ydata_now is None:
            return
        xdata_start, ydata_start = self._pan_start_data
        dx = xdata_start - xdata_now
        dy = ydata_start - ydata_now
        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()
        self._view_xlim = (xlim[0] + dx, xlim[1] + dx)
        self._view_ylim = (ylim[0] + dy, ylim[1] + dy)
        self._schedule_update(redraw_only=True)

    def _zoom_in(self):
        self._zoom(1.2)

    def _zoom_out(self):
        self._zoom(0.8)

    def _zoom(self, factor):
        if self.ax is None:
            return
        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()
        cx = (xlim[0] + xlim[1]) / 2
        cy = (ylim[0] + ylim[1]) / 2
        new_width = (xlim[1] - xlim[0]) * factor
        new_height = (ylim[1] - ylim[0]) * factor
        self._view_xlim = (cx - new_width/2, cx + new_width/2)
        self._view_ylim = (cy - new_height/2, cy + new_height/2)
        self._schedule_update(redraw_only=True)

    def reset_view(self):
        if self.current_body:
            radius = self.current_body.data.get("BASE_DATA", {}).get("radius", 0.0)
            limit = radius * 2.0
            self._view_xlim = (-limit, limit)
            self._view_ylim = (-limit, limit)
            self._schedule_update(redraw_only=True)

    def force_refresh(self):
        """强制刷新地形预览，重新计算地形并重绘"""
        if self.current_body is None:
            return
        self._compute_terrain()   # 重新解析公式并计算海拔
        self._draw()              # 重绘

    def schedule_update(self, body=None):
        if body is not None:
            self.current_body = body
        self._update_timer.start(50)

    def _schedule_update(self, redraw_only=False):
        if redraw_only:
            self._do_update(redraw_only=True)
        else:
            self._update_timer.start(50)

    def _do_update(self, redraw_only=False):
        if self.current_body is None:
            return
        if not redraw_only:
            self._compute_terrain()
        self._draw()

    def _compute_terrain(self):
        """根据当前天体的地形公式计算每个经度的海拔（米）"""
        body = self.current_body
        terrain_data = body.data.get("TERRAIN_DATA", {})
        formulas = terrain_data.get("terrainFormulaDifficulties", {}).get("Normal", [])
        radius = body.data.get("BASE_DATA", {}).get("radius", 0.0)
        if radius == 0:
            self._elevations = np.zeros(360)
            self._theta_deg = np.linspace(0, 360, 360, endpoint=False)
            return

        # 解析公式
        operations = []
        for line in formulas:
            line = line.strip()
            if not line:
                continue
            if line.startswith("OUTPUT = AddHeightMap("):
                # 提取括号内的内容
                start = line.find('(') + 1
                end = line.rfind(')')
                if start > 0 and end > start:
                    inner = line[start:end]
                    parts = [p.strip() for p in inner.split(',')]
                    if len(parts) >= 3:
                        func_name = parts[0].strip()
                        try:
                            length_m = float(parts[1])
                            height_m = float(parts[2])
                            operations.append(('AddHeightMap', func_name, length_m, height_m))
                        except ValueError:
                            continue
            elif line.startswith("OUTPUT = Add("):
                start = line.find('(') + 1
                end = line.rfind(')')
                if start > 0 and end > start:
                    inner = line[start:end]
                    try:
                        height_m = float(inner)
                        operations.append(('Add', height_m))
                    except ValueError:
                        continue

        # 确定采样点数（根据当前视图范围的最大半径）
        if self._view_xlim is not None and self._view_ylim is not None:
            max_abs = max(abs(self._view_xlim[0]), abs(self._view_xlim[1]),
                          abs(self._view_ylim[0]), abs(self._view_ylim[1]))
        else:
            max_abs = radius * 2.0
        scale = max_abs / radius if radius > 0 else 1
        num_points = max(360, int(360 * scale))
        num_points = min(num_points, 7200)

        self._theta_deg = np.linspace(0, 360, num_points, endpoint=False)
        self._elevations = np.zeros(num_points)

        # 加载地形函数缓存（如果还没有）
        self._ensure_heightmap_cache()

        for op in operations:
            if op[0] == 'AddHeightMap':
                _, func_name, length_m, height_m = op
                points = self._heightmap_cache.get(func_name)
                if points is None:
                    continue
                # 添加这行：确认函数已找到
                num_pts = len(points)
                period_angle_rad = length_m / radius if radius > 0 else 2 * np.pi
                # 对每个经度累加贡献
                for i, deg in enumerate(self._theta_deg):
                    rad = np.radians(-deg)
                    phase_rad = rad % period_angle_rad
                    t = phase_rad / period_angle_rad
                    idx = t * (num_pts - 1)
                    idx0 = int(np.floor(idx))
                    idx1 = min(idx0 + 1, num_pts - 1)
                    if idx0 == idx1:
                        val = points[idx0]
                    else:
                        frac = idx - idx0
                        val = points[idx0] * (1 - frac) + points[idx1] * frac
                    self._elevations[i] += val * height_m
            elif op[0] == 'Add':
                _, height_m = op
                self._elevations += height_m

        # 应用平坦区（flatZones）
        #flat_zones = terrain_data.get("flatZones", [])
        #if flat_zones:
        #    fz = flat_zones[0]
        #    h_flat = fz.get("height", 0.0)
        #    angle_center_rad = fz.get("angle", 0.0)
        #    width_m = fz.get("width", 0.0)
        #    transition_m = fz.get("transition", 0.0)
        #    angle_center_deg = -np.degrees(angle_center_rad)
        #    half_width_deg = np.degrees(width_m / radius) if radius > 0 else 0
        #    transition_deg = np.degrees(transition_m / radius) if radius > 0 else 0
        #    for i, deg in enumerate(self._theta_deg):
        #        dist = abs(deg - angle_center_deg)
        #       if dist <= half_width_deg:
        #            self._elevations[i] = h_flat
        #        elif dist <= half_width_deg + transition_deg:
        #            t = (dist - half_width_deg) / transition_deg
        #            orig = self._elevations[i]
        #            self._elevations[i] = orig * (1 - t) + h_flat * t
        pass

    def _ensure_heightmap_cache(self):
        """从 Heightmap_Default 文件夹读取所有地形函数数据并缓存"""
        if self._heightmap_cache:
            return
        heightmap_dir = os.path.join(os.path.dirname(__file__), "Heightmap_Default")
        if not os.path.isdir(heightmap_dir):
            print(f"警告: 地形文件夹不存在: {heightmap_dir}")
            return
        for filename in os.listdir(heightmap_dir):
            if filename.endswith('.txt'):
                filepath = os.path.join(heightmap_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        points = data.get("points", [])
                        if points:
                            name = os.path.splitext(filename)[0]
                            self._heightmap_cache[name] = points
                except Exception as e:
                    print(f"加载地形文件 {filename} 失败: {e}")

    def _draw(self):
        """绘制当前视图（笛卡尔坐标）"""
        if self.current_body is None:
            return
        body = self.current_body
        radius = body.data.get("BASE_DATA", {}).get("radius", 0.0)
        if radius == 0 or self._elevations is None:
            return

        self.figure.clear()
        self.ax = self.figure.add_subplot(111)
        self.ax.set_aspect('equal')
        self.ax.grid(True, alpha=0.3)

        # 计算所有点的直角坐标
        theta_rad = np.radians(self._theta_deg)
        r_radial = radius + self._elevations
        x = r_radial * np.cos(theta_rad)
        y = r_radial * np.sin(theta_rad)

        color = body_color(body)

        # 画出地形轮廓并填充（多边形）
        # 为了提高性能和避免填充混乱，我们按顺时针/逆时针顺序排序 theta
        # 确保多边形首尾闭合
        points = np.column_stack((x, y))
        # 使用 Polygon 填充
        from matplotlib.patches import Polygon
        poly = Polygon(points, closed=True, facecolor=color, edgecolor='black', alpha=0.4, linewidth=0.5)
        self.ax.add_patch(poly)

        # 大气标记（圆）
        atmo_phys = body.data.get("ATMOSPHERE_PHYSICS_DATA", {})
        has_atmo = bool(atmo_phys)
        if has_atmo:
            atmo_height = atmo_phys.get("height", 0.0)
            if atmo_height > 0:
                atmo_radius = radius + atmo_height
                circle = plt.Circle((0, 0), atmo_radius, fill=False, linestyle='-', color='gray', linewidth=0.5, alpha=0.7, label='Atmosphere')
                self.ax.add_patch(circle)

        # 时间加速高度（圆）
        base_data = body.data.get("BASE_DATA", {})
        tw_height = base_data.get("timewarpHeight", 0.0)
        if tw_height > 0 and (not has_atmo or tw_height != atmo_height):
            tw_radius = radius + tw_height
            circle = plt.Circle((0, 0), tw_radius, fill=False, linestyle='--', color='gray', linewidth=0.5, alpha=0.7, label='Timewarp')
            self.ax.add_patch(circle)

        # 光环标记（环形）
        rings_data = body.data.get("RINGS_DATA", {})
        if rings_data:
            start_r = rings_data.get("startRadius", 0.0)
            end_r = rings_data.get("endRadius", 0.0)
            if start_r > 0 and end_r > start_r:
                ring_color = rings_data.get("mapColor", {"r": 0.85, "g": 0.75, "b": 0.65, "a": 0.2})
                ring_rgba = (ring_color["r"], ring_color["g"], ring_color["b"], ring_color["a"])
                # 环形使用 Wedge 或透明填充，使用 Patch 环形
                from matplotlib.patches import Wedge
                # 创建多个扇形环来近似（更简单：画两个同心圆，填充中间区域）
                wedge = Wedge((0, 0), end_r, 0, 360, width=end_r - start_r, facecolor=ring_rgba, alpha=0.3, edgecolor='none')
                self.ax.add_patch(wedge)
                # 外边界线（虚点线）
                outer_circle = plt.Circle((0, 0), end_r, fill=False, linestyle='-.', color='gray', linewidth=0.5, alpha=0.7, label='Rings')
                inner_circle = plt.Circle((0, 0), start_r, fill=False, linestyle='-.', color='gray', linewidth=0.5, alpha=0.7)
                self.ax.add_patch(outer_circle)
                self.ax.add_patch(inner_circle)
        # 应用保存的视图范围
        if self._view_xlim is None or self._view_ylim is None:
            limit = radius * 2.0
            self._view_xlim = (-limit, limit)
            self._view_ylim = (-limit, limit)
        self.ax.set_xlim(self._view_xlim)
        self.ax.set_ylim(self._view_ylim)

        # 图例（需要从 patches 中获取 label，但 Circle 没有自动添加，手动处理）
        # 简单起见，可以只显示大气和光环的图例
        handles = []
        labels = []
        # 从 ax.patches 中筛选有 label 的
        for patch in self.ax.patches:
            if patch.get_label():
                handles.append(patch)
                labels.append(patch.get_label())
        if handles:
            self.ax.legend(handles, labels, loc='upper right', fontsize=8)

        self.canvas.draw()