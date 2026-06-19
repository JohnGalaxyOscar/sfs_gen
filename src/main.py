import sys
import os

def resource_path(relative_path):
    """获取资源的绝对路径，兼容开发环境和打包后的exe"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(__file__), relative_path)

sys.path.insert(0, os.path.dirname(__file__))
import shutil
import json
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QTabWidget, QLabel,
    QLineEdit, QDoubleSpinBox, QCheckBox, QGroupBox, QFormLayout, QPushButton,
    QTextEdit, QHBoxLayout, QComboBox, QSpinBox, QGridLayout, QColorDialog,
    QFileDialog, QMessageBox, QMenu, QInputDialog, QTreeView, QDialog, QTableWidget,
    QTableWidgetItem, QDialogButtonBox, QTreeWidget, QTreeWidgetItem, QSplitter,
    QProgressDialog, QFrame, QTextBrowser
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QStandardItemModel, QStandardItem, QColor, QBrush, QIcon
from models import Project, CelestialBody
from constants import BUILTIN_TEXTURES, PLANET_TEMPLATES
from widgets import UnitConverter, UnitSpinBox, ColorPickerButton
from dialogs import TextureManagerDialog
from terrain_preview import TerrainPreviewWidget
from utils import clean_float, get_mass_factor, compute_soi_radius, orbit_points, body_color

import matplotlib
matplotlib.use('Qt5Agg')  # 强制使用 Qt5 后端
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.patches import Circle, Polygon
import numpy as np
import matplotlib.pyplot as plt

import matplotlib.patheffects as path_effects

from terrain_formula_editor import TerrainFormulaEditor

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # 设置窗口图标（影响任务栏显示）
        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            from PySide6.QtGui import QIcon
            self.setWindowIcon(QIcon(icon_path))
        self.setWindowTitle("SFS行星包生成器 v2.03 beta")
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'WenQuanYi Micro Hei']  # 支持中文
        plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
        self.setGeometry(100, 100, 1000, 800)

        # 左侧树形视图 + 按钮栏
        self.tree_widget = QTreeView()
        self.tree_model = QStandardItemModel()
        self.tree_model.setHorizontalHeaderLabels(["天体名称", "半径", "半长轴"])
        self.tree_widget.setModel(self.tree_model)
        self.tree_widget.setEditTriggers(QTreeView.NoEditTriggers)
        self.tree_widget.setHeaderHidden(False)
        self.tree_widget.setColumnWidth(0, 200)
        self.tree_widget.setColumnWidth(1, 120)
        self.tree_widget.setColumnWidth(2, 120)
        self.tree_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self.show_tree_context_menu)
        self.tree_widget.clicked.connect(self.on_tree_item_clicked)
        self.tree_widget.viewport().installEventFilter(self)
        self.tree_widget.selectionModel().currentChanged.connect(self.on_tree_current_changed)

        self.btn_add_body = QPushButton("添加天体")
        self.btn_add_body.clicked.connect(self.on_add_body_clicked)
        self.btn_add_body.setEnabled(False)
        self.btn_delete_body = QPushButton("删除天体")
        self.btn_delete_body.clicked.connect(self.on_delete_body_clicked)
        self.btn_delete_body.setEnabled(False)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 使用水平分割器作为主布局
        main_splitter = QSplitter(Qt.Horizontal)
        central_widget.setLayout(QVBoxLayout())
        central_widget.layout().addWidget(main_splitter)
        
        # ========== 左栏：树形视图 + 按钮栏 ==========
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # 中心天体编辑栏
        center_bar = QWidget()
        center_layout = QHBoxLayout(center_bar)
        center_layout.setContentsMargins(5, 5, 5, 5)
        center_label = QLabel("系统中心:")
        self.center_name_label = QLabel("未设置")
        self.edit_center_btn = QPushButton("编辑")
        self.edit_center_btn.clicked.connect(self.edit_center_body)
        center_layout.addWidget(center_label)
        center_layout.addWidget(self.center_name_label)
        center_layout.addWidget(self.edit_center_btn)
        center_layout.addStretch()
        left_layout.addWidget(center_bar)
        
        # 树形视图（已在前面创建，直接添加）
        left_layout.addWidget(self.tree_widget)
        
        # 按钮栏
        button_widget = QWidget()
        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_add_body = QPushButton("添加天体")
        self.btn_add_body.clicked.connect(self.on_add_body_clicked)
        self.btn_add_body.setEnabled(False)
        self.btn_delete_body = QPushButton("删除天体")
        self.btn_delete_body.clicked.connect(self.on_delete_body_clicked)
        self.btn_delete_body.setEnabled(False)
        button_layout.addWidget(self.btn_add_body)
        button_layout.addWidget(self.btn_delete_body)
        button_layout.addStretch()
        left_layout.addWidget(button_widget)
        
        main_splitter.addWidget(left_widget)
        
        # ========== 中栏：标签页 ==========
        self.tab_widget = QTabWidget()
        main_splitter.addWidget(self.tab_widget)
        
        # ========== 右栏：垂直分割器（地形预览 + 轨道预览） ==========
        right_splitter = QSplitter(Qt.Vertical)
        self.terrain_preview = TerrainPreviewWidget()
        self.terrain_preview.btn_refresh.clicked.connect(self._on_refresh_terrain)
        right_splitter.addWidget(self.terrain_preview)
        
        # 轨道预览容器
        self.orbit_preview_widget = QWidget()
        orbit_preview_layout = QVBoxLayout(self.orbit_preview_widget)
        orbit_preview_layout.setContentsMargins(0, 0, 0, 0)
        
        # 添加标题
        orbit_title = QLabel("轨道预览")
        orbit_title.setStyleSheet("font-weight: bold; font-size: 12pt; margin-bottom: 5px;")
        orbit_preview_layout.addWidget(orbit_title)
        
        # 创建轨道视图的选项卡（原位于 setup_orbit_tab 中）
        self.orbit_view_tabs = QTabWidget()
        orbit_preview_layout.addWidget(self.orbit_view_tabs)

        # 创建子天体视图
        self.child_view_figure = Figure(figsize=(5, 4), dpi=100)
        self.child_view_canvas = FigureCanvas(self.child_view_figure)
        child_widget = QWidget()
        child_layout = QVBoxLayout(child_widget)
        btn_layout = QHBoxLayout()
        btn_zoom_in = QPushButton("缩小 -")
        btn_zoom_out = QPushButton("放大 +")
        btn_reset = QPushButton("重置视图")
        btn_layout.addWidget(btn_zoom_in)
        btn_layout.addWidget(btn_zoom_out)
        btn_layout.addWidget(btn_reset)
        child_layout.addLayout(btn_layout)
        child_layout.addWidget(self.child_view_canvas)
        btn_zoom_in.clicked.connect(lambda: self.zoom_child_view(1.2))
        btn_zoom_out.clicked.connect(lambda: self.zoom_child_view(0.8))
        btn_reset.clicked.connect(self.reset_child_view)
        self.orbit_view_tabs.addTab(child_widget, "子天体视图")

        # 创建父级视图
        self.parent_view_figure = Figure(figsize=(5, 4), dpi=100)
        self.parent_view_canvas = FigureCanvas(self.parent_view_figure)
        parent_widget = QWidget()
        parent_layout = QVBoxLayout(parent_widget)
        btn_layout = QHBoxLayout()
        btn_zoom_in = QPushButton("缩小 -")
        btn_zoom_out = QPushButton("放大 +")
        btn_reset = QPushButton("重置视图")
        btn_layout.addWidget(btn_zoom_in)
        btn_layout.addWidget(btn_zoom_out)
        btn_layout.addWidget(btn_reset)
        parent_layout.addLayout(btn_layout)
        parent_layout.addWidget(self.parent_view_canvas)
        btn_zoom_in.clicked.connect(lambda: self.zoom_parent_view(1.2))
        btn_zoom_out.clicked.connect(lambda: self.zoom_parent_view(0.8))
        btn_reset.clicked.connect(self.reset_parent_view)
        self.orbit_view_tabs.addTab(parent_widget, "父级视图")

        orbit_preview_layout.addWidget(self.orbit_view_tabs)
        right_splitter.addWidget(self.orbit_preview_widget)
        
        right_splitter.setSizes([300, 300])   # 地形预览和轨道预览各占一半
        main_splitter.addWidget(right_splitter)
        
        # 设置初始比例（左:中:右 = 1:3:1）
        main_splitter.setSizes([250, 600, 300])
        
        # 创建所有标签页
        self.setup_basic_tab()
        self.setup_atmo_physics_tab()
        self.setup_atmo_visuals_tab()
        self.setup_front_clouds_tab()
        self.setup_terrain_tab()
        self.setup_water_tab()
        self.setup_rings_tab()
        self.setup_post_processing_tab()
        self.setup_orbit_tab()
        self.setup_landmarks_tab()
        self.setup_export_tab()
        
        # 初始化项目数据
        self.current_project = Project()

        # 连接导出设置控件的信号，实时更新项目元数据
        self.export_pack_name.textChanged.connect(lambda t: setattr(self.current_project, 'export_pack_name', t))
        self.export_author.textChanged.connect(lambda t: setattr(self.current_project, 'export_author', t))
        self.export_version.textChanged.connect(lambda t: setattr(self.current_project, 'export_version', t))
        self.export_description.textChanged.connect(lambda: setattr(self.current_project, 'export_description', self.export_description.toPlainText()))
        self.space_center_address.textChanged.connect(lambda t: setattr(self.current_project, 'space_center_address', t))
        self.space_center_angle.valueChanged.connect(lambda v: setattr(self.current_project, 'space_center_angle', v))
        self.launchpad_horizontal.valueChanged.connect(lambda v: setattr(self.current_project, 'launchpad_horizontal', v))
        self.launchpad_height.valueChanged.connect(lambda v: setattr(self.current_project, 'launchpad_height', v))

        # 添加太阳（作为中心天体）
        sun_body = CelestialBody("Sun", "Star", template_name="Sun")
        sun_body.type = "Center"          # 改为中心天体
        sun_body.parent = None
        if "ORBIT_DATA" in sun_body.data:
            del sun_body.data["ORBIT_DATA"]   # 中心天体不应有轨道数据
        self.current_project.add_body(sun_body)
        # 添加地球（行星）
        earth_body = CelestialBody("Earth", "Planet", template_name="Earth")
        earth_body.parent = "Sun"
        if "ORBIT_DATA" not in earth_body.data:
            earth_body.data["ORBIT_DATA"] = {}
        earth_body.data["ORBIT_DATA"]["parent"] = "Sun"
        self.current_project.add_body(earth_body)
        self.current_body = earth_body

        self._refreshing = False

        # 轨道可视化相关（必须在 load_body_to_ui 之前定义）
        self._orbit_update_timer = QTimer()
        self._orbit_update_timer.setSingleShot(True)
        self._orbit_update_timer.timeout.connect(self.update_orbit_views)

        self.load_body_to_ui(self.current_body)
        self.refresh_tree()

        self._velocity_is_nan = False
        
        # 创建菜单栏
        menubar = self.menuBar()
        file_menu = menubar.addMenu("项目")
        new_action = file_menu.addAction("新建项目")
        new_action.triggered.connect(self.new_project)
        open_action = file_menu.addAction("打开项目")
        open_action.triggered.connect(self.open_project)
        save_action = file_menu.addAction("保存项目")
        save_action.triggered.connect(self.save_project)
        save_as_action = file_menu.addAction("另存为...")
        save_as_action.triggered.connect(self.save_project_as)
        import_pack_action = file_menu.addAction("导入行星包...")
        import_pack_action.triggered.connect(self.import_planet_pack)

        # 在创建 file_menu 之后，添加：
        tools_menu = menubar.addMenu("工具")
        texture_action = tools_menu.addAction("纹理管理")
        texture_action.triggered.connect(self.open_texture_manager)

        export_pack_action = tools_menu.addAction("导出行星包")
        export_pack_action.triggered.connect(self.export_pack)

        help_menu = menubar.addMenu("帮助")
        guide_action = help_menu.addAction("使用指南")
        guide_action.triggered.connect(self.show_guide)

        status_bar = self.statusBar()
        watermark_label = QLabel("本工具系Bilibili up主 约翰_加拉克西_奥斯卡 制作的免费工具，坚决抵制盗用收费行为。Bug汇报或游戏交流欢迎加入QQ群995473883！")
        watermark_label.setStyleSheet("color:#666; font-size:9pt; padding:0 5px;")
        status_bar.addPermanentWidget(watermark_label, 1)  # 1 表示拉伸因子，让水印居中

    def _get_template_names(self):
        """获取所有可用的模板名称（从 PLANET_TEMPLATES）"""
        from constants import PLANET_TEMPLATES
        return sorted(PLANET_TEMPLATES.keys())
    
    def _show_template_dialog(self, module_name, apply_func):
        """通用模板选择对话框，apply_func 接收模板数据"""
        from constants import PLANET_TEMPLATES
        names = self._get_template_names()
        if not names:
            QMessageBox.warning(self, "警告", "没有可用的模板数据，请检查 constants.py 中的 PLANET_TEMPLATES。")
            return
        name, ok = QInputDialog.getItem(self, f"导入{module_name}模板", "选择星球模板:", names, 0, False)
        if ok and name:
            template_data = PLANET_TEMPLATES.get(name, {})
            apply_func(template_data)

    def import_basic_from_template(self):
        def apply(template):
            base = template.get("BASE_DATA", {})
            if not base:
                QMessageBox.warning(self, "警告", "所选模板没有 BASE_DATA 数据。")
                return
            # 更新控件值（不触发信号）
            self.name_edit.blockSignals(True)
            self.name_edit.setText(template.get("name", self.current_body.name))
            self.name_edit.blockSignals(False)
            radius_game = base.get("radius", 0)
            self.radius_input.blockSignals(True)
            self.radius_input.set_game_value(radius_game)
            self.radius_input.blockSignals(False)
            self.gravity_spin.setValue(base.get("gravity", 0))
            self.timewarp_height.setValue(base.get("timewarpHeight", 0))
            vel_val = base.get("velocityArrowsHeight", 0)
            if isinstance(vel_val, str) and vel_val == "NaN":
                self.velocity_arrows_height.setValue(0.0)
                self._velocity_is_nan = True
            else:
                self.velocity_arrows_height.setValue(vel_val)
                self._velocity_is_nan = False
            mc = base.get("mapColor", {"r": 0.5, "g": 0.5, "b": 0.5, "a": 1.0})
            self.map_color_picker.set_color((mc["r"], mc["g"], mc["b"], mc["a"]))
            self.significant_check.setChecked(base.get("significant", True))
            self.rotate_camera_check.setChecked(base.get("rotateCamera", True))
            # 保存当前天体
            self.save_ui_to_body(self.current_body)
            self.refresh_tree()
            self.terrain_preview.schedule_update(self.current_body)
            self.schedule_orbit_update()
            QMessageBox.information(self, "成功", "基本参数已从模板导入。")
        self._show_template_dialog("基本参数", apply)

    def import_planet_pack(self):
        """导入一个现有的SFS行星包文件夹"""
        folder_path = QFileDialog.getExistingDirectory(self, "选择行星包文件夹")
        if not folder_path:
            return
        try:
            from models import Project
            proj = Project.import_from_pack(folder_path)
            self.current_project = proj
            self.current_project.file_path = None  # 导入的不是项目文件，所以没有路径
            # 同步界面显示
            if proj.bodies:
                self.current_body = proj.bodies[0]
                self.load_body_to_ui(self.current_body)
            else:
                QMessageBox.warning(self, "警告", "导入的行星包中没有找到任何天体。")
                return
            self.refresh_tree()
            # 同步导出设置到界面
            self._sync_ui_from_project()
            self.setWindowTitle(f"SFS行星包生成器 v2.03 beta - 导入: {os.path.basename(folder_path)}")
            QMessageBox.information(self, "成功", f"成功导入行星包: {folder_path}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导入行星包失败: {e}")

    def export_pack(self):
        """导出完整行星包到文件夹（符合 SFS 1.6 格式）"""
        dir_path = QFileDialog.getExistingDirectory(self, "选择导出目录")
        if not dir_path:
            return

        # ---------- 验证纹理是否存在 ----------
        # 收集所有自定义纹理（用户已添加的外部文件）
        custom_textures = set(self.current_project.texture_sources.keys())
        # 收集所有内置纹理（从 constants 中展开）
        builtin_textures = set()
        for category_list in BUILTIN_TEXTURES.values():
            builtin_textures.update(category_list)
        
        missing_textures = set()
        
        # 定义需要检查的纹理字段路径（点分隔）
        texture_fields = [
            ("ATMOSPHERE_VISUALS_DATA", "GRADIENT", "texture"),
            ("ATMOSPHERE_VISUALS_DATA", "CLOUDS", "texture"),
            ("FRONT_CLOUDS_DATA", "cloudsTexture"),
            ("TERRAIN_DATA", "TERRAIN_TEXTURE_DATA", "planetTexture"),
            ("TERRAIN_DATA", "TERRAIN_TEXTURE_DATA", "surfaceTexture_A"),
            ("TERRAIN_DATA", "TERRAIN_TEXTURE_DATA", "surfaceTexture_B"),
            ("TERRAIN_DATA", "TERRAIN_TEXTURE_DATA", "terrainTexture_C"),
            ("WATER_DATA", "oceanMaskTexture"),
            ("RINGS_DATA", "ringsTexture"),
        ]
        
        def get_nested(data, path):
            """按路径获取嵌套字典中的值，路径为可变参数，返回找到的字符串值或 None"""
            for key in path:
                if isinstance(data, dict):
                    data = data.get(key)
                else:
                    return None
            return data if isinstance(data, str) else None
        
        for body in self.current_project.bodies:
            data = body.data
            for field_path in texture_fields:
                tex = get_nested(data, field_path)
                if tex and tex not in ("None", ""):
                    # 排除特殊值 "None" 和空字符串
                    if tex not in builtin_textures and tex not in custom_textures:
                        missing_textures.add(f"{tex} (在天体 '{body.name}' 的 {'.'.join(field_path)} 中)")
        
        if missing_textures:
            msg = "以下纹理未在自定义贴图中找到且不是内置贴图，导出后游戏可能显示异常：\n" + "\n".join(sorted(missing_textures))
            reply = QMessageBox.question(self, "纹理缺失警告", msg + "\n\n是否继续导出？", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                return

        pack_name = self.current_project.export_pack_name
        author = self.current_project.export_author
        version = self.current_project.export_version
        description = self.current_project.export_description

        pack_dir = os.path.join(dir_path, pack_name)
        planet_data_dir = os.path.join(pack_dir, "Planet Data")
        texture_data_dir = os.path.join(pack_dir, "Texture Data")
        heightmap_data_dir = os.path.join(pack_dir, "Heightmap Data")
        
        try:
            # 创建必要目录
            os.makedirs(planet_data_dir, exist_ok=True)
            os.makedirs(texture_data_dir, exist_ok=True)
            os.makedirs(heightmap_data_dir, exist_ok=True)
            
            # ---------- 导出天体文件 ----------
            progress = QProgressDialog("正在导出天体...", "取消", 0, len(self.current_project.bodies), self)
            progress.setWindowTitle("导出进度")
            progress.setMinimumDuration(0)
            progress.setValue(0)
            
            for idx, body in enumerate(self.current_project.bodies):
                if progress.wasCanceled():
                    break
                progress.setLabelText(f"正在导出: {body.name}")
                if body == self.current_body:
                    self.save_ui_to_body(body)
                # 清理数据中的浮点数
                file_name = f"{body.name}.txt"
                file_path = os.path.join(planet_data_dir, file_name)
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(body.data, f, indent=2, ensure_ascii=False)
                progress.setValue(idx + 1)
            
            # ---------- 复制自定义纹理 ----------
            progress.setLabelText("正在复制纹理...")
            progress.setMaximum(len(self.current_project.texture_sources))
            progress.setValue(0)
            for idx, (tex_name, src_path) in enumerate(self.current_project.texture_sources.items()):
                if progress.wasCanceled():
                    break
                if not os.path.exists(src_path):
                    QMessageBox.warning(self, "警告", f"纹理文件不存在: {src_path}")
                    continue
                ext = os.path.splitext(src_path)[1]
                dst_name = tex_name + ext
                dst_path = os.path.join(texture_data_dir, dst_name)
                shutil.copy2(src_path, dst_path)
                progress.setValue(idx + 1)
            
            # ---------- 复制默认地形文件 ----------
            default_heightmap_dir = resource_path("Heightmap_Default")
            if os.path.exists(default_heightmap_dir):
                progress.setLabelText("正在复制地形文件...")
                # 复制整个文件夹内容
                for item in os.listdir(default_heightmap_dir):
                    src = os.path.join(default_heightmap_dir, item)
                    dst = os.path.join(heightmap_data_dir, item)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(src, dst)
            else:
                QMessageBox.warning(self, "警告", f"默认地形文件夹不存在，已跳过:\n{default_heightmap_dir}")
            
            # ---------- 生成 Import_Settings.txt ----------
            import_settings = {
                "includeDefaultPlanets": False,
                "includeDefaultHeightmaps": True,
                "includeDefaultTextures": True,
                "hideStarsInAtmosphere": True,
                "authorName": author,
                "version": version,
                "description": description
            }
            import_path = os.path.join(pack_dir, "Import_Settings.txt")
            with open(import_path, 'w', encoding='utf-8') as f:
                json.dump(import_settings, f, indent=2, ensure_ascii=False)
            
            # ---------- 生成 Space_Center_Data.txt （默认值）----------
            space_center = {
                "address": self.current_project.space_center_address,
                "angle": self.current_project.space_center_angle,
                "position_LaunchPad": {
                    "horizontalPosition": self.current_project.launchpad_horizontal,
                    "height": self.current_project.launchpad_height
                }
            }
            space_center_path = os.path.join(pack_dir, "Space_Center_Data.txt")
            with open(space_center_path, 'w', encoding='utf-8') as f:
                json.dump(space_center, f, indent=2, ensure_ascii=False)
            
            # ---------- 生成 Version.txt ----------
            version_path = os.path.join(pack_dir, "Version.txt")
            with open(version_path, 'w', encoding='utf-8') as f:
                f.write("1.6.00.16")
            
            progress.close()
            QMessageBox.information(self, "成功", f"行星包已导出到:\n{pack_dir}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {e}")

    def open_texture_manager(self):
        dialog = TextureManagerDialog(self.current_project.texture_sources, self)
        if dialog.exec() == QDialog.Accepted:
            # 可以刷新什么，或者不需要
            pass

    def select_texture(self, line_edit):
        """打开纹理选择对话框，并将选中的纹理名称设置到指定的 QLineEdit"""
        from models import load_templates  # 避免循环导入
        # 创建一个临时的纹理源字典（实际上纹理管理对话框需要 texture_sources 引用，我们直接传入当前项目的）
        dialog = TextureManagerDialog(self.current_project.texture_sources, self, select_mode=True)
        if dialog.exec() == QDialog.Accepted and dialog.selected_texture:
            line_edit.setText(dialog.selected_texture)

    def update_tabs_visibility(self, body_type):
        """根据天体类型显示/隐藏标签页（暂未实现）"""
        pass

    def refresh_tree(self):
        # 防止递归刷新
        if hasattr(self, '_refreshing') and self._refreshing:
            return
        self._refreshing = True
        try:
            # 先保存当前界面修改到 current_body，确保树显示最新数据
            # 注意：此保存操作可能导致递归刷新，暂时注释以调试
            # if hasattr(self, 'current_body') and self.current_body:
            #     self.save_ui_to_body(self.current_body)

            self.tree_model.clear()
            self.tree_model.setHorizontalHeaderLabels(["天体名称", "半径", "半长轴"])
            if not self.current_project.bodies:
                return

            # 找出中心天体（type == "Center"）
            center_body = None
            other_bodies = []
            for body in self.current_project.bodies:
                if body.type == "Center":
                    center_body = body
                else:
                    other_bodies.append(body)

            # 获取所有天体信息
            body_info = {}
            for body in self.current_project.bodies:
                radius_game = body.data.get("BASE_DATA", {}).get("radius", 0)
                radius_km = UnitConverter.from_game_unit(radius_game, "km")
                # 统一从数据模型获取半长轴，不再特殊处理当前天体
                sma_game = body.data.get("ORBIT_DATA", {}).get("semiMajorAxis", 0) if body.type != "Center" else 0
                sma_km = UnitConverter.from_game_unit(sma_game, "km") if sma_game else 0
                body_info[body.name] = {
                    "radius_km": radius_km,
                    "sma_km": sma_km,
                }

            def format_distance(km):
                if km <= 0:
                    return "0 m"
                if km >= 1e7:
                    au = km / UnitConverter.REAL_AU_TO_KM
                    return f"{au:.2f} AU"
                elif km >= 10000:
                    wan = km / 10000
                    return f"{wan:.1f} 万km"
                else:
                    return f"{km:.0f} km"

            # 创建节点（不包含中心天体），使用字典存储已处理的天体名称
            processed_names = set()
            items = {}
            for body in other_bodies:
                if body.name in processed_names:
                    # 跳过重复的同名天体（理论上不应发生）
                    continue
                processed_names.add(body.name)
                name_item = QStandardItem(body.name)
                name_item.setData(body.name, Qt.UserRole)
                radius_km = body_info[body.name]["radius_km"]
                sma_km = body_info[body.name]["sma_km"]
                radius_item = QStandardItem(format_distance(radius_km))
                sma_item = QStandardItem(format_distance(sma_km))
                items[body.name] = [name_item, radius_item, sma_item]

            # 构建父子关系映射（中心天体作为隐式根）
            children_map = {body.name: [] for body in other_bodies}
            for body in other_bodies:
                parent_name = body.parent
                # 如果父节点是中心天体，或者父节点不存在，则视为顶层节点
                if parent_name == (center_body.name if center_body else None) or not parent_name:
                    continue
                elif parent_name in items:
                    # 避免重复添加同一个子天体
                    if body.name not in children_map[parent_name]:
                        children_map[parent_name].append(body.name)
                else:
                    pass

            # 递归添加子节点，使用集合记录已添加的节点，防止重复
            added_nodes = set()
            def add_children(parent_item, parent_name):
                nonlocal added_nodes
                child_names = children_map.get(parent_name, [])
                child_names.sort(key=lambda name: body_info[name]["sma_km"])
                for child_name in child_names:
                    if child_name in added_nodes:
                        continue
                    added_nodes.add(child_name)
                    child_row = items[child_name]
                    parent_item.appendRow(child_row)
                    add_children(child_row[0], child_name)

            # 收集顶层天体：那些 parent 为中心天体或 parent 为 None 的天体
            top_bodies = []
            for body in other_bodies:
                parent_name = body.parent
                if parent_name == (center_body.name if center_body else None) or not parent_name:
                    top_bodies.append(body)
            # 按半长轴排序
            top_bodies.sort(key=lambda b: body_info[b.name]["sma_km"])

            # 构建顶层行
            added_nodes = set()  # 重新初始化
            for top in top_bodies:
                if top.name in added_nodes:
                    continue
                added_nodes.add(top.name)
                row = items[top.name]
                add_children(row[0], top.name)
                self.tree_model.appendRow(row)

            self.tree_widget.expandAll()
            self.tree_widget.update()

            # 更新中心天体名称显示
            center = self.get_center_body()
            if center:
                self.center_name_label.setText(center.name)
            else:
                self.center_name_label.setText("无")

            # 恢复选中
            if hasattr(self, 'current_body') and self.current_body:
                self._select_tree_item_by_name(self.current_body.name)
            self._update_buttons_state()
        finally:
            self._refreshing = False

    def _update_buttons_state(self):
        has_selection = self.tree_widget.currentIndex().isValid()
        # 添加按钮始终启用（未选中时添加顶层天体）
        self.btn_add_body.setEnabled(True)
        self.btn_delete_body.setEnabled(has_selection)

    def eventFilter(self, obj, event):
        if obj == self.tree_widget.viewport() and event.type() == event.Type.MouseButtonPress:
            pos = event.position().toPoint()
            index = self.tree_widget.indexAt(pos)
            if not index.isValid():
                # 点击空白区域，清除选中
                self.tree_widget.selectionModel().clear()
                self._update_buttons_state()
                return True
        return super().eventFilter(obj, event)

    def get_center_body(self):
        """获取项目中的中心天体"""
        for body in self.current_project.bodies:
            if body.type == "Center":
                return body
        return None

    def edit_center_body(self):
        """编辑中心天体"""
        center = self.get_center_body()
        if center:
            # 保存当前编辑的天体
            self.save_ui_to_body(self.current_body)
            # 切换到中心天体
            self.current_body = center
            self.load_body_to_ui(center)
            # 刷新树形图（中心天体已被隐藏，但需要更新按钮状态等）
            self.refresh_tree()
            # 直接更新轨道视图，不使用定时器
            self.update_child_orbit_view()
            self.update_parent_orbit_view()
        else:
            QMessageBox.warning(self, "提示", "当前项目中没有中心天体。")

    def _select_tree_item_by_name(self, name):
        """在树中选中指定名称的天体项（第一列）"""
        def recurse(parent_item):
            if parent_item is None:
                return False
            for i in range(parent_item.rowCount()):
                child = parent_item.child(i, 0)
                if child is None:
                    continue
                if child.data(Qt.UserRole) == name:
                    index = self.tree_model.indexFromItem(child)
                    self.tree_widget.setCurrentIndex(index)
                    self.tree_widget.scrollTo(index)
                    return True
                if recurse(child):
                    return True
            return False
        root = self.tree_model.invisibleRootItem()
        if root is None:
            return
        recurse(root)

    def show_tree_context_menu(self, position):
        index = self.tree_widget.indexAt(position)
        if index.isValid():
            item = self.tree_model.itemFromIndex(index.siblingAtColumn(0))
            body_name = item.data(Qt.UserRole)
            menu = QMenu()
            add_action = menu.addAction("添加子天体")
            add_action.triggered.connect(lambda: self.add_child_body(body_name))
            delete_action = menu.addAction("删除天体")
            delete_action.triggered.connect(lambda: self.delete_body(body_name))
            menu.exec_(self.tree_widget.viewport().mapToGlobal(position))
        else:
            # 空白处右键不添加任何菜单（或者可以显示提示，但直接忽略）
            pass

    def on_tree_current_changed(self, current, previous):
        self._update_buttons_state()

    def on_add_body_clicked(self):
        current_index = self.tree_widget.currentIndex()
        if current_index.isValid():
            item = self.tree_model.itemFromIndex(current_index.siblingAtColumn(0))
            parent_name = item.data(Qt.UserRole)
            self.add_child_body(parent_name)
        else:
            # 未选中任何天体，添加顶层天体（父节点为中心天体）
            center = self.get_center_body()
            if center:
                self.add_child_body(center.name)
            else:
                QMessageBox.warning(self, "提示", "项目中没有中心天体，无法添加顶层天体。")

    def on_delete_body_clicked(self):
        """点击删除天体按钮：删除当前选中的天体"""
        current_index = self.tree_widget.currentIndex()
        if not current_index.isValid():
            return
        item = self.tree_model.itemFromIndex(current_index.siblingAtColumn(0))
        body_name = item.data(Qt.UserRole)
        self.delete_body(body_name)

    def add_child_body(self, parent_name):
        from dialogs import AddBodyDialog
        dialog = AddBodyDialog(self, parent_name)
        if dialog.exec() != QDialog.Accepted:
            return
        result = dialog.get_result()
        if not result:
            return

        name = result["name"]
        template = result["template"]
        body_type = result["type"]

        # 检查名称是否已存在（包括当前所有天体）
        existing_names = [b.name for b in self.current_project.bodies]
        if name in existing_names:
            QMessageBox.warning(self, "警告", f"天体名称 '{name}' 已存在，请使用其他名称。")
            return

        # 创建新天体
        from models import CelestialBody
        if template == "空模板":
            new_body = CelestialBody(name, body_type)
        else:
            new_body = CelestialBody(name, body_type, template_name=template)

        new_body.parent = parent_name
        # 同步设置轨道数据的 parent 字段
        if "ORBIT_DATA" not in new_body.data:
            new_body.data["ORBIT_DATA"] = {}
        new_body.data["ORBIT_DATA"]["parent"] = parent_name

        # 添加到项目（只添加一次）
        self.current_project.add_body(new_body)

        # 立即刷新树形图（此时新天体已存在）
        self.refresh_tree()

        # 切换到新天体并加载数据（注意：这里不再调用 refresh_tree，避免重复）
        self.current_body = new_body
        self.load_body_to_ui(new_body)

        # 手动刷新轨道视图和地形预览（确保数据最新）
        self.update_child_orbit_view()
        self.update_parent_orbit_view()
        self.terrain_preview.schedule_update(self.current_body)

    def delete_body(self, body_name):
        # 确认删除
        ret = QMessageBox.question(self, "确认删除", f"确定要删除天体 '{body_name}' 及其所有子天体吗？",
                                    QMessageBox.Yes | QMessageBox.No)
        if ret == QMessageBox.Yes:
            # 递归删除所有子天体（需要先找出所有后代）
            to_delete = set()
            def collect_descendants(name):
                to_delete.add(name)
                for b in self.current_project.bodies:
                    if b.parent == name:
                        collect_descendants(b.name)
            collect_descendants(body_name)
            self.current_project.bodies = [b for b in self.current_project.bodies if b.name not in to_delete]
            self.refresh_tree()
            # 如果当前编辑的天体被删除，则切换到第一个剩余天体或清空界面
            if self.current_body.name in to_delete:
                if self.current_project.bodies:
                    self.current_body = self.current_project.bodies[0]
                    self.load_body_to_ui(self.current_body)
                else:
                    # 没有天体了，创建一个默认的
                    default = CelestialBody("NewPlanet", "Planet")
                    self.current_project.add_body(default)
                    self.current_body = default
                    self.load_body_to_ui(default)
                    self.refresh_tree()

    def on_tree_item_clicked(self, index):
        if not index.isValid():
            # 点击空白区域：清除树形图的选中状态，并更新按钮状态
            self.tree_widget.selectionModel().clear()
            self._update_buttons_state()
            return
        
        item = self.tree_model.itemFromIndex(index.siblingAtColumn(0))
        body_name = item.data(Qt.UserRole)
        body = self.current_project.get_body(body_name)
        if body:
            # 保存当前编辑的数据到当前天体
            self.save_ui_to_body(self.current_body)
            # 切换到新天体
            self.current_body = body
            self.load_body_to_ui(body)
            # 直接更新轨道视图，不使用定时器
            self.update_child_orbit_view()
            self.update_parent_orbit_view()
        self._update_buttons_state()

    def load_body_to_ui(self, body: CelestialBody):
        """将天体的数据加载到界面控件"""
        data = body.data
        base = data.get("BASE_DATA", {})
        
        # ========== 基本参数 ==========
        self.name_edit.blockSignals(True)
        self.name_edit.setText(body.name)
        self.name_edit.blockSignals(False)
        radius_game = base.get("radius", 314970.0)
        
        # 临时阻止半径输入框发射信号
        self.radius_input.blockSignals(True)
        self.radius_input.set_game_value(radius_game)
        self.radius_input.blockSignals(False)

        self.gravity_spin.setValue(base.get("gravity", 9.8))
        self.timewarp_height.setValue(base.get("timewarpHeight", 25000.0))
        vel_val = base.get("velocityArrowsHeight", 5000.0)
        if isinstance(vel_val, str) and vel_val == "NaN":
            self.velocity_arrows_height.setValue(0.0)
            self._velocity_is_nan = True   # 标记原始值为NaN
        else:
            self.velocity_arrows_height.setValue(vel_val)
            self._velocity_is_nan = False
        mc = base.get("mapColor", {"r": 0.45, "g": 0.68, "b": 1.0, "a": 1.0})
        self.map_color_picker.set_color((mc["r"], mc["g"], mc["b"], mc["a"]))
        self.significant_check.setChecked(base.get("significant", True))
        self.rotate_camera_check.setChecked(base.get("rotateCamera", True))

        # ========== 大气物理 ==========
        atmo_phys = data.get("ATMOSPHERE_PHYSICS_DATA", {})
        has_atmo = bool(atmo_phys)
        self.atmo_enable.setChecked(has_atmo)

        if has_atmo:
            self.atmo_height.setValue(atmo_phys.get("height", 30000.0) / 1000.0)
            self.atmo_density.setValue(atmo_phys.get("density", 0.005))
            self.atmo_curve.setValue(atmo_phys.get("curve", 10.0))
            self.parachute_mult.setValue(atmo_phys.get("parachuteMultiplier", 1.0))
            self.upper_atmo.setValue(atmo_phys.get("upperAtmosphere", 0.333))
            self.shockwave_intensity.setValue(atmo_phys.get("shockwaveIntensity", 1.0))
            self.min_heating_velocity.setValue(atmo_phys.get("minHeatingVelocityMultiplier", 1.0))
        else:
            # 设置默认值（控件会被禁用，不影响导出）
            self.atmo_height.setValue(30)
            self.atmo_density.setValue(0.005)
            self.atmo_curve.setValue(10.0)
            self.parachute_mult.setValue(1.0)
            self.upper_atmo.setValue(0.333)
            self.shockwave_intensity.setValue(1.0)
            self.min_heating_velocity.setValue(1.0)
        
        # ========== 大气视觉 ==========
        if has_atmo:
            atmo_vis = data.get("ATMOSPHERE_VISUALS_DATA", {})
            # 渐变
            grad = atmo_vis.get("GRADIENT", {})
            self.atmo_gradient_texture.setText(grad.get("texture", "Atmo_Earth"))
            self.atmo_gradient_height.setValue(grad.get("height", 45000.0))
            self.atmo_position_z.setValue(grad.get("positionZ", 4000))

            # 云层
            clouds = atmo_vis.get("CLOUDS", {})
            has_clouds = bool(clouds) and clouds.get("texture", "None") != "None"
            self.clouds_enable.setChecked(has_clouds)
            if has_clouds:
                self.cloud_texture.setText(clouds.get("texture", "Earth_Clouds"))
                self.cloud_start_height.setValue(clouds.get("startHeight", 1200.0))
                self.cloud_width.setValue(clouds.get("width", 40845.87))
                self.cloud_height.setValue(clouds.get("height", 36000.0))
                self.cloud_alpha.setValue(clouds.get("alpha", 0.1))
                self.cloud_velocity.setValue(clouds.get("velocity", 2.0))
            else:
                self.cloud_texture.setText("None")
                self.cloud_start_height.setValue(0)
                self.cloud_width.setValue(0)
                self.cloud_height.setValue(0)
                self.cloud_alpha.setValue(0)
                self.cloud_velocity.setValue(0)

            # 雾
            fog = atmo_vis.get("FOG", {})
            fog_keys = fog.get("keys", [])
            has_fog = len(fog_keys) > 0
            self.fog_enable.setChecked(has_fog)
            if has_fog:
                if len(fog_keys) >= 1:
                    self.fog_key0_dist.setValue(fog_keys[0].get("distance", 500))
                if len(fog_keys) >= 2:
                    self.fog_key1_dist.setValue(fog_keys[1].get("distance", 3000))
                if len(fog_keys) >= 3:
                    self.fog_key2_dist.setValue(fog_keys[2].get("distance", 30000))
            else:
                self.fog_key0_dist.setValue(500)
                self.fog_key1_dist.setValue(3000)
                self.fog_key2_dist.setValue(30000)
        else:
            # 无大气时，设置大气视觉控件的默认值（控件会被禁用）
            self.atmo_gradient_texture.setText("Atmo_Earth")
            self.atmo_gradient_height.setValue(45000)
            self.atmo_position_z.setValue(4000)
            self.clouds_enable.setChecked(False)
            self.cloud_texture.setText("None")
            self.cloud_start_height.setValue(0)
            self.cloud_width.setValue(0)
            self.cloud_height.setValue(0)
            self.cloud_alpha.setValue(0)
            self.cloud_velocity.setValue(0)
            self.fog_enable.setChecked(False)
            self.fog_key0_dist.setValue(500)
            self.fog_key1_dist.setValue(3000)
            self.fog_key2_dist.setValue(30000)
        
        # ========== 大气远景外观纹理 ==========
        if has_atmo:
            front = data.get("FRONT_CLOUDS_DATA", {})
            self.front_clouds_enable.setChecked(bool(front))
            self.front_clouds_texture.setText(front.get("cloudsTexture", "Earth_Clouds_Front"))
            self.front_clouds_cutout.setValue(front.get("cloudTextureCutout", 1.0))
            self.front_clouds_fade_height.setValue(front.get("fadeZoneHeight", 20000.0))
            self.front_clouds_height.setValue(front.get("height", 10000.0))
            self.front_clouds_pos_z.setValue(front.get("positionZ", -5000.0))
            self.front_clouds_sharpen.setChecked(front.get("sharpenAlpha", True))
        else:
            self.front_clouds_enable.setChecked(False)
            self.front_clouds_texture.setText("Earth_Clouds_Front")
            self.front_clouds_cutout.setValue(1.0)
            self.front_clouds_fade_height.setValue(20000.0)
            self.front_clouds_height.setValue(10000.0)
            self.front_clouds_pos_z.setValue(-5000.0)
            self.front_clouds_sharpen.setChecked(True)
        
        # 同步远景外观纹理控件的启用状态（根据其自身的复选框）
        enabled = self.front_clouds_enable.isChecked()
        self.front_clouds_texture.setEnabled(enabled)
        self.front_clouds_cutout.setEnabled(enabled)
        self.front_clouds_fade_height.setEnabled(enabled)
        self.front_clouds_height.setEnabled(enabled)
        self.front_clouds_pos_z.setEnabled(enabled)
        self.front_clouds_sharpen.setEnabled(enabled)
        
        # ========== 地形纹理 ==========
        terrain = data.get("TERRAIN_DATA", {})
        has_terrain = bool(terrain)  # 如果数据中有 TERRAIN_DATA 则启用
        self.terrain_enable.setChecked(has_terrain)

        if has_terrain:
            tex_data = terrain.get("TERRAIN_TEXTURE_DATA", {})
            self.planet_texture.setText(tex_data.get("planetTexture", "Earth_WithOceans"))
            self.planet_texture_cutout.setValue(tex_data.get("planetTextureCutout", 0.9947))
            self.planet_texture_rotation.setValue(tex_data.get("planetTextureRotation", 1.85))
            self.planet_texture_dont_distort.setChecked(tex_data.get("planetTextureDontDistort", True))

            # 构建除保留字段外的其他细节数据
            preserved_keys = ["planetTexture", "planetTextureCutout", "planetTextureRotation", "planetTextureDontDistort"]
            other_details = {k: v for k, v in tex_data.items() if k not in preserved_keys}
            self.terrain_details_json.setPlainText(json.dumps(other_details, indent=2))

            self.vertice_size.setValue(terrain.get("verticeSize", 2.0))
            self.collider_check.setChecked(terrain.get("collider", True))

            flat_zones = terrain.get("flatZones", [])
            self.flat_zones.setPlainText(json.dumps(flat_zones, indent=2) if flat_zones else "[]")
        else:
            # 清空或设置默认值（控件会被禁用，所以不影响导出）
            self.planet_texture.setText("Earth_WithOceans")
            self.planet_texture_cutout.setValue(0.9947)
            self.planet_texture_rotation.setValue(1.85)
            self.planet_texture_dont_distort.setChecked(True)
            self.terrain_details_json.setPlainText("{}")
            self.vertice_size.setValue(2.0)
            self.collider_check.setChecked(True)
            self.flat_zones.setPlainText("[]")
            # 清空地形公式编辑器（不保留任何条目）
            self.terrain_formula_editor.set_formulas([])

        # 加载地形公式（从 terrainFormulaDifficulties.Normal）
        formulas = terrain.get("terrainFormulaDifficulties", {})
        normal_formulas = formulas.get("Normal", [])
        self.terrain_formula_editor.set_formulas(normal_formulas)

        # 加载贴图公式
        texture_formula = terrain.get("textureFormula", [])
        self.texture_formula_edit.setPlainText("\n".join(texture_formula))

        # 加载岩石装饰
        rocks = terrain.get("rocks", {})
        has_rocks = bool(rocks)
        self.rocks_enable.setChecked(has_rocks)
        if has_rocks:
            self.rock_type.setCurrentText(rocks.get("rockType", "Rock Square"))
            self.rock_density.setValue(rocks.get("rockDensity", 0.7))
            self.rock_min_size.setValue(rocks.get("minSize", 0.2))
            self.rock_max_size.setValue(rocks.get("maxSize", 0.8))
            self.rock_power_curve.setValue(rocks.get("powerCurve", 2.0))
            self.rock_max_angle.setValue(rocks.get("maxAngle", 25.0))
        else:
            # 设置默认值，但控件会被禁用
            self.rock_type.setCurrentText("Rock Square")
            self.rock_density.setValue(0.7)
            self.rock_min_size.setValue(0.2)
            self.rock_max_size.setValue(0.8)
            self.rock_power_curve.setValue(2.0)
            self.rock_max_angle.setValue(25.0)

        # ========== 水体 ==========
        water = data.get("WATER_DATA", {})
        has_water = bool(water)
        self.water_enable.setChecked(has_water)
        self.ocean_mask_texture.setText(water.get("oceanMaskTexture", "Earth_OceanMask_V2"))
        self.ocean_depth.setValue(water.get("oceanDepth", 5000.0))
        # 根据启用标志禁用控件
        self.ocean_mask_texture.setEnabled(has_water)
        self.ocean_depth.setEnabled(has_water)
        
        # ========== 光环 ==========
        rings = data.get("RINGS_DATA", {})
        has_rings = bool(rings)
        self.rings_enable.setChecked(has_rings)
        self.rings_texture.setText(rings.get("ringsTexture", "Saturn_Rings"))
        if has_rings:
            start_radius_game = rings.get("startRadius", 3800000.0)
            end_radius_game = rings.get("endRadius", 6600000.0)
            self.rings_start_radius.set_game_value(start_radius_game)
            self.rings_end_radius.set_game_value(end_radius_game)
            self.rings_pos_z.setValue(rings.get("positionZ", 5000.0))
        self.rings_texture.setEnabled(has_rings)
        self.rings_start_radius.setEnabled(has_rings)
        self.rings_end_radius.setEnabled(has_rings)
        self.rings_pos_z.setEnabled(has_rings)
        
        # ========== 后期处理 ==========
        pp = data.get("POST_PROCESSING", {})
        pp_keys = pp.get("keys", [])
        self.pp_keys.setPlainText(json.dumps(pp_keys, indent=2) if pp_keys else "[]")
        
        # ========== 轨道 ==========
        orbit = data.get("ORBIT_DATA", {})

        self.orbit_parent.setText(orbit.get("parent", ""))
        sma_game = orbit.get("semiMajorAxis", 0)
        self.semi_major_input.blockSignals(True)
        self.semi_major_input.set_game_value(sma_game)
        self.semi_major_input.blockSignals(False)
        # 强制重新连接信号（防止新天体丢失连接）
        self.semi_major_input.unit_changed.disconnect()
        self.semi_major_input.unit_changed.connect(self.on_radius_or_semi_changed)
        self.eccentricity.setValue(orbit.get("eccentricity", 0))
        self.arg_of_periapsis.setValue(orbit.get("argumentOfPeriapsis", 0))
        dir_val = orbit.get("direction", 1)
        # 根据实际值查找对应的索引
        index = self.direction.findData(dir_val)
        if index >= 0:
            self.direction.setCurrentIndex(index)
        else:
            self.direction.setCurrentIndex(0)  # 默认顺行
        self.soi_multiplier.setValue(orbit.get("multiplierSOI", 2.5))
        
        # 根据天体类型控制轨道控件的可用性
        if body.type == "Center":
            self.orbit_parent.setEnabled(False)
            self.semi_major_input.setEnabled(False)
            self.eccentricity.setEnabled(False)
            self.arg_of_periapsis.setEnabled(False)
            self.direction.setEnabled(False)
            self.soi_multiplier.setEnabled(False)
            # 修改标签页标题，提示无轨道
            self.tab_widget.setTabText(8, "轨道 (无)")
        else:
            self.orbit_parent.setEnabled(True)
            self.semi_major_input.setEnabled(True)
            self.eccentricity.setEnabled(True)
            self.arg_of_periapsis.setEnabled(True)
            self.direction.setEnabled(True)
            self.soi_multiplier.setEnabled(True)
            self.tab_widget.setTabText(8, "轨道")

        # ========== 地标 ==========
        landmarks = data.get("LANDMARKS", [])
        self.landmarks_json.setPlainText(json.dumps(landmarks, indent=2) if landmarks else "[]")

        # 更新地形预览
        self.terrain_preview.reset_view()
        self.terrain_preview.schedule_update(self.current_body)

        # 更新轨道视图
        self.update_child_orbit_view()
        self.update_parent_orbit_view()

    def save_ui_to_body(self, body: CelestialBody):
        # 只允许保存当前正在编辑的天体
        if body != self.current_body:
            return
        data = body.data
        
        # ========== 基本参数 ==========
        new_base = {}
        new_base["radius"] = self.radius_input.get_game_value()
        new_base["radiusDifficultyScale"] = {}
        new_base["gravity"] = self.gravity_spin.value()
        # 重力难度缩放（空字典，不再使用）
        new_base["gravityDifficultyScale"] = {}
        new_base["timewarpHeight"] = self.timewarp_height.value()
        vel_val = self.velocity_arrows_height.value()
        if hasattr(self, '_velocity_is_nan') and self._velocity_is_nan and vel_val == 0.0:
            vel_val = "NaN"
        new_base["velocityArrowsHeight"] = vel_val
        new_base["mapColor"] = {
            "r": self.map_color_picker.get_color()[0],
            "g": self.map_color_picker.get_color()[1],
            "b": self.map_color_picker.get_color()[2],
            "a": self.map_color_picker.get_color()[3]
        }
        new_base["significant"] = self.significant_check.isChecked()
        new_base["rotateCamera"] = self.rotate_camera_check.isChecked()
        data["BASE_DATA"] = new_base

        # ========== 大气物理 ==========
        if self.atmo_enable.isChecked():
            data["ATMOSPHERE_PHYSICS_DATA"] = {
                "height": self.atmo_height.value() * 1000.0,
                "density": self.atmo_density.value(),
                "curve": self.atmo_curve.value(),
                "curveScale": {},
                "parachuteMultiplier": self.parachute_mult.value(),
                "upperAtmosphere": self.upper_atmo.value(),
                "heightDifficultyScale": {},
                "shockwaveIntensity": self.shockwave_intensity.value(),
                "minHeatingVelocityMultiplier": self.min_heating_velocity.value()
            }
        else:
            data.pop("ATMOSPHERE_PHYSICS_DATA", None)
        
        # ========== 大气视觉 ==========
        if self.atmo_enable.isChecked():
            gradient = {
                "positionZ": int(self.atmo_position_z.value()),
                "height": self.atmo_gradient_height.value(),
                "heightDifficultyScale": {},
                "texture": self.atmo_gradient_texture.text()
            }

            if self.clouds_enable.isChecked():
                clouds = {
                    "texture": self.cloud_texture.text(),
                    "startHeight": self.cloud_start_height.value(),
                    "width": self.cloud_width.value(),
                    "height": self.cloud_height.value(),
                    "alpha": self.cloud_alpha.value(),
                    "velocity": self.cloud_velocity.value()
                }
            else:
                clouds = {
                    "texture": "None",
                    "startHeight": 0.0,
                    "width": 0.0,
                    "height": 0.0,
                    "alpha": 0.0,
                    "velocity": 0.0
                }

            if self.fog_enable.isChecked():
                fog_keys = [
                    {
                        "color": {"r": 0.461872876, "g": 0.463235319, "b": 0.3644572, "a": 0.0},
                        "distance": self.fog_key0_dist.value()
                    },
                    {
                        "color": {"r": 0.647058845, "g": 0.848739564, "b": 0.891, "a": 0.117647059},
                        "distance": self.fog_key1_dist.value()
                    },
                    {
                        "color": {"r": 0.53, "g": 0.8, "b": 1.0, "a": 0.6},
                        "distance": self.fog_key2_dist.value()
                    }
                ]
                fog = {"keys": fog_keys}
            else:
                fog = {"keys": []}

            atmo_vis = {"GRADIENT": gradient, "CLOUDS": clouds, "FOG": fog}
            data["ATMOSPHERE_VISUALS_DATA"] = atmo_vis
        else:
            data.pop("ATMOSPHERE_VISUALS_DATA", None)
        
        # ========== 大气远景外观纹理 ==========
        if self.atmo_enable.isChecked() and self.front_clouds_enable.isChecked():
            data["FRONT_CLOUDS_DATA"] = {
                "cloudsTexture": self.front_clouds_texture.text(),
                "cloudTextureCutout": self.front_clouds_cutout.value(),
                "fadeZoneHeight": self.front_clouds_fade_height.value(),
                "height": self.front_clouds_height.value(),
                "positionZ": self.front_clouds_pos_z.value(),
                "sharpenAlpha": self.front_clouds_sharpen.isChecked()
            }
        else:
            data.pop("FRONT_CLOUDS_DATA", None)
        
        # ========== 地形纹理 ==========
        if self.terrain_enable.isChecked():
            # 解析 JSON 文本框中的细节数据
            try:
                other_details = json.loads(self.terrain_details_json.toPlainText())
            except:
                other_details = {}
                QMessageBox.warning(self, "JSON 错误", "地表细节 JSON 格式无效，已忽略。")

            # 构建完整的 TERRAIN_TEXTURE_DATA
            tex_data = {}
            tex_data["planetTexture"] = self.planet_texture.text()
            tex_data["planetTextureCutout"] = self.planet_texture_cutout.value()
            tex_data["planetTextureRotation"] = self.planet_texture_rotation.value()
            tex_data["planetTextureDontDistort"] = self.planet_texture_dont_distort.isChecked()
            tex_data.update(other_details)

            # 构建地形公式字典（仅 Normal 难度）
            normal_formulas = self.terrain_formula_editor.get_formulas()
            terrain_formulas = {"Normal": normal_formulas}

            terrain_data = {
                "TERRAIN_TEXTURE_DATA": tex_data,
                "terrainFormulaDifficulties": terrain_formulas,
                "textureFormula": [line for line in self.texture_formula_edit.toPlainText().split('\n') if line.strip()],
                "verticeSize": self.vertice_size.value(),
                "collider": self.collider_check.isChecked(),
                "flatZones": json.loads(self.flat_zones.toPlainText()),
                "flatZonesDifficulties": body.data.get("TERRAIN_DATA", {}).get("flatZonesDifficulties", {})
            }
            data["TERRAIN_DATA"] = terrain_data
            # 岩石装饰
            if self.rocks_enable.isChecked():
                terrain_data["rocks"] = {
                    "rockType": self.rock_type.currentText(),
                    "rockDensity": self.rock_density.value(),
                    "minSize": self.rock_min_size.value(),
                    "maxSize": self.rock_max_size.value(),
                    "powerCurve": self.rock_power_curve.value(),
                    "maxAngle": self.rock_max_angle.value()
                }
        else:
            # 如果未启用地形，则删除可能残留的 TERRAIN_DATA
            data.pop("TERRAIN_DATA", None)

        # ========== 水体 ==========
        if self.water_enable.isChecked():
            data["WATER_DATA"] = {
                "oceanMaskTexture": self.ocean_mask_texture.text(),
                "lowerTerrain": True,
                "oceanDepth": self.ocean_depth.value(),
                "sand": {"r": 0.9, "g": 0.86, "b": 0.81, "a": 1.0},
                "floor": {"r": 0.25, "g": 0.25, "b": 0.25, "a": 1.0},
                "shallow": {"r": 0.1, "g": 0.68, "b": 1.0, "a": 0.4},
                "deep": {"r": 0.1, "g": 0.15, "b": 0.55, "a": 1.0},
                "maskGradient_Water": {"must": 1000.0, "cannot": 700.0, "global": 2000.0},
                "waterGradientWidthMultiplier": 0.5,
                "maskGradient_Terrain": {"must": 25.0, "cannot": 25.0, "global": 50.0},
                "sandGradientWidthMultiplier": 2.0,
                "floorGradientWidthMultiplier": 10.0,
                "shoreNoiseSize": {"x": 3000.0, "y": 1000.0},
                "sandNoiseSize": {"x": 500.0, "y": 100.0},
                "wavesSize": {"x": 16.0, "y": 0.3},
                "opacity_Surface": 0.8,
                "opacity_Far": 1.0,
                "opacity_FullDarkness": 0.95,
                "surfaceVisibilityDistance": 1200.0,
                "fullDarknessDepth": 500.0,
                "fullDarknessVisibilityDistance": 300.0,
                "mapColor": {"r": 0.1, "g": 0.4, "b": 1.0, "a": 0.4}
            }
        else:
            data.pop("WATER_DATA", None)
        
        # ========== 光环 ==========
        if self.rings_enable.isChecked():
            data["RINGS_DATA"] = {
                "ringsTexture": self.rings_texture.text(),
                "startRadius": self.rings_start_radius.get_game_value(),
                "endRadius": self.rings_end_radius.get_game_value(),
                "positionZ": self.rings_pos_z.value(),
                "mapColor": {"r": 0.85, "g": 0.75, "b": 0.65, "a": 0.2}
            }
        else:
            data.pop("RINGS_DATA", None)
        
        # ========== 后期处理 ==========
        try:
            pp_keys = json.loads(self.pp_keys.toPlainText())
        except:
            pp_keys = []
        data["POST_PROCESSING"] = {"keys": pp_keys}
        
        # ========== 轨道 ==========
        if body.type != "Center":
            parent = self.orbit_parent.text()
            if parent == body.name:
                QMessageBox.warning(self, "警告", "中心天体不能设置为自身。")
                original_parent = body.data.get("ORBIT_DATA", {}).get("parent", "")
                self.orbit_parent.setText(original_parent)
                parent = original_parent
            sma_scale = {}  # 难度缩放不再使用
            # SOI难度缩放，目前未实现界面，保留空字典
            soi_scale = {}
            sma_value = self.semi_major_input.get_game_value()
            data["ORBIT_DATA"] = {
                "parent": parent,
                "semiMajorAxis": sma_value,
                "smaDifficultyScale": sma_scale,
                "eccentricity": self.eccentricity.value(),
                "argumentOfPeriapsis": self.arg_of_periapsis.value(),
                "direction": self.direction.currentData(),
                "multiplierSOI": self.soi_multiplier.value(),
                "soiDifficultyScale": soi_scale
            }
            body.parent = self.orbit_parent.text()
        else:
            data.pop("ORBIT_DATA", None)
            body.parent = None
        
        # ========== 地标 ==========
        try:
            landmarks = json.loads(self.landmarks_json.toPlainText())
        except:
            landmarks = []
        data["LANDMARKS"] = landmarks
        
        # 确保成就数据存在（保持默认，不覆盖）
        if "ACHIEVEMENT_DATA" not in data:
            data["ACHIEVEMENT_DATA"] = {
                "Landed": False,
                "Takeoff": True,
                "Atmosphere": True,
                "Orbit": True,
                "Crash": True
            }
        
        body.name = self.name_edit.text()

        # 重新排序字典，确保导出顺序符合游戏预期
        ordered = {}
        ordered["version"] = body.data.get("version", "1.5")
        ordered["BASE_DATA"] = body.data.get("BASE_DATA", {})
        if "ATMOSPHERE_PHYSICS_DATA" in body.data:
            ordered["ATMOSPHERE_PHYSICS_DATA"] = body.data["ATMOSPHERE_PHYSICS_DATA"]
        if "ATMOSPHERE_VISUALS_DATA" in body.data:
            ordered["ATMOSPHERE_VISUALS_DATA"] = body.data["ATMOSPHERE_VISUALS_DATA"]
        if "FRONT_CLOUDS_DATA" in body.data:
            ordered["FRONT_CLOUDS_DATA"] = body.data["FRONT_CLOUDS_DATA"]
        if "TERRAIN_DATA" in body.data:
            ordered["TERRAIN_DATA"] = body.data["TERRAIN_DATA"]
        if "WATER_DATA" in body.data:
            ordered["WATER_DATA"] = body.data["WATER_DATA"]
        if "RINGS_DATA" in body.data:
            ordered["RINGS_DATA"] = body.data["RINGS_DATA"]
        if "POST_PROCESSING" in body.data:
            ordered["POST_PROCESSING"] = body.data["POST_PROCESSING"]
        if "ORBIT_DATA" in body.data:
            ordered["ORBIT_DATA"] = body.data["ORBIT_DATA"]
        if "ACHIEVEMENT_DATA" in body.data:
            ordered["ACHIEVEMENT_DATA"] = body.data["ACHIEVEMENT_DATA"]
        if "LANDMARKS" in body.data:
            ordered["LANDMARKS"] = body.data["LANDMARKS"]
        body.data = ordered

        # 确保 POST_PROCESSING 至少有一个关键帧
        if "POST_PROCESSING" in data and not data["POST_PROCESSING"].get("keys"):
            data["POST_PROCESSING"]["keys"] = [
                {"height": 0.0, "shadowIntensity": 1.35, "starIntensity": 0.0, "hueShift": 0.0, 
                 "saturation": 0.95, "contrast": 1.2, "red": 1.03, "green": 1.02, "blue": 1.0}
            ]
        
        # 确保 terrainFormulaDifficulties.Normal 至少有一个空字符串？或者删除该键？
        if "TERRAIN_DATA" in data:
            formulas = data["TERRAIN_DATA"].get("terrainFormulaDifficulties", {})
            if not formulas.get("Normal"):
                formulas["Normal"] = ["OUTPUT = Add(0)"]

    def new_project(self):
        """新建项目"""
        self.current_project = Project()
        sun_body = CelestialBody("Sun", "Star", template_name="Sun")
        sun_body.type = "Center"
        sun_body.parent = None
        if "ORBIT_DATA" in sun_body.data:
            del sun_body.data["ORBIT_DATA"]
        self.current_project.add_body(sun_body)
        earth_body = CelestialBody("Earth", "Planet", template_name="Earth")
        earth_body.parent = "Sun"
        if "ORBIT_DATA" not in earth_body.data:
            earth_body.data["ORBIT_DATA"] = {}
        earth_body.data["ORBIT_DATA"]["parent"] = "Sun"
        self.current_project.add_body(earth_body)
        self.current_body = earth_body
        self.load_body_to_ui(self.current_body)
        self.current_project.file_path = None
        self.setWindowTitle("SFS行星包生成器 v2.03 beta - 未命名项目")
        self.schedule_orbit_update()
        self._sync_ui_from_project()
        self.terrain_preview.schedule_update(self.current_body)
        self.refresh_tree()

    def show_guide(self):
        """显示帮助对话框"""
        guide_path = resource_path("docs/guide.html")
        if not os.path.exists(guide_path):
            QMessageBox.warning(self, "警告", f"帮助文件不存在：{guide_path}")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("帮助")
        dialog.resize(800, 600)
        layout = QVBoxLayout(dialog)
        text_browser = QTextBrowser()
        text_browser.setOpenExternalLinks(True)  # 允许点击链接
        with open(guide_path, "r", encoding="utf-8") as f:
            text_browser.setHtml(f.read())
        layout.addWidget(text_browser)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)
        dialog.exec()

    def _sync_ui_from_project(self):
        """将当前项目的导出元数据同步到界面控件"""
        proj = self.current_project
        self.export_pack_name.setText(proj.export_pack_name)
        self.export_author.setText(proj.export_author)
        self.export_version.setText(proj.export_version)
        self.export_description.setPlainText(proj.export_description)
        self.space_center_address.setText(proj.space_center_address)
        self.space_center_angle.setValue(proj.space_center_angle)
        self.launchpad_horizontal.setValue(proj.launchpad_horizontal)
        self.launchpad_height.setValue(proj.launchpad_height)

    def _on_refresh_terrain(self):
        """刷新地形预览：先保存当前天体的数据，再强制预览更新"""
        if self.current_body:
            self.save_ui_to_body(self.current_body)
            self.terrain_preview.force_refresh()

    def open_project(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "打开项目文件", "", "SFS项目文件 (*.sfsproj)")
        if not file_path:
            return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            proj = Project.from_dict(data)
            self.current_project = proj
            self.current_project.file_path = file_path
            if proj.bodies:
                self.current_body = proj.bodies[0]
                self.load_body_to_ui(self.current_body)
            else:
                # 项目无天体，创建一个默认的
                self.new_project()
            self.setWindowTitle(f"SFS行星包生成器 v2.03 beta - {file_path}")
            self.schedule_orbit_update()
            self.refresh_tree()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"打开项目失败: {e}")
    
    def save_project(self):
        if self.current_project.file_path:
            self._save_to_file(self.current_project.file_path)
        else:
            self.save_project_as()
    
    def save_project_as(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "保存项目文件", "", "SFS项目文件 (*.sfsproj)")
        if file_path:
            self._save_to_file(file_path)
            self.current_project.file_path = file_path
            self.setWindowTitle(f"SFS行星包生成器 v2.03 beta - {file_path}")
    
    def _save_to_file(self, path: str):
        # 保存前将当前界面的数据同步到当前天体
        self.save_ui_to_body(self.current_body)
        data = self.current_project.to_dict()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        QMessageBox.information(self, "成功", f"项目已保存到 {path}")

    def _update_color_spinboxes(self):
        r, g, b, a = self.map_color_picker.get_color()
        self.color_r.blockSignals(True)
        self.color_g.blockSignals(True)
        self.color_b.blockSignals(True)
        self.color_a.blockSignals(True)
        self.color_r.setValue(r)
        self.color_g.setValue(g)
        self.color_b.setValue(b)
        self.color_a.setValue(a)
        self.color_r.blockSignals(False)
        self.color_g.blockSignals(False)
        self.color_b.blockSignals(False)
        self.color_a.blockSignals(False)

    def _update_color_from_spinboxes(self):
        r = self.color_r.value()
        g = self.color_g.value()
        b = self.color_b.value()
        a = self.color_a.value()
        # 暂时断开颜色按钮的信号，避免循环
        self.map_color_picker.color_changed.disconnect(self._update_color_spinboxes)
        self.map_color_picker.set_color((r, g, b, a))
        self.map_color_picker.color_changed.connect(self._update_color_spinboxes)

    def setup_basic_tab(self):
        # 之前的内容，可以增加更多字段如 timewarpHeight, velocityArrowsHeight, mapColor
        tab = QWidget()
        self.tab_widget.addTab(tab, "基本参数")
        layout = QFormLayout()
        tab.setLayout(layout)
        
        self.name_edit = QLineEdit("NewPlanet")
        self.name_edit.textChanged.connect(self.on_name_changed)   # 新增
        layout.addRow("行星名称:", self.name_edit)
        
        self.radius_input = UnitSpinBox(initial_value=6371, initial_unit="km", 
                                     min_val=0, max_val=1e50, decimals=12)

        layout.addRow("半径:", self.radius_input)

        self.gravity_spin = QDoubleSpinBox()
        self.gravity_spin.setRange(0, 1e30)
        self.gravity_spin.setDecimals(10)
        self.gravity_spin.setValue(9.8)
        self.gravity_spin.setSuffix(" m/s²")
        layout.addRow("表面重力:", self.gravity_spin)
        
        self.timewarp_height = QDoubleSpinBox()
        self.timewarp_height.setRange(0, 1e30)
        self.timewarp_height.setValue(25000)
        self.timewarp_height.setSuffix(" m")
        layout.addRow("时间加速高度:", self.timewarp_height)
        
        self.velocity_arrows_height = QDoubleSpinBox()
        self.velocity_arrows_height.setRange(-1e30, 1e30)
        self.velocity_arrows_height.setValue(5000)
        self.velocity_arrows_height.setSuffix(" m")
        layout.addRow("速度箭头高度:", self.velocity_arrows_height)

        color_group = QWidget()
        color_layout = QHBoxLayout(color_group)
        color_layout.setContentsMargins(0, 0, 0, 0)

        self.map_color_picker = ColorPickerButton((0.45, 0.68, 1.0, 1.0))
        self.map_color_picker.color_changed.connect(self._update_color_spinboxes)

        # 添加四个数值输入框（RGBA）
        self.color_r = QDoubleSpinBox()
        self.color_r.setRange(0, 1)
        self.color_r.setSingleStep(0.01)
        self.color_r.setValue(0.45)
        self.color_r.setPrefix("R: ")
        self.color_g = QDoubleSpinBox()
        self.color_g.setRange(0, 1)
        self.color_g.setSingleStep(0.01)
        self.color_g.setValue(0.68)
        self.color_g.setPrefix("G: ")
        self.color_b = QDoubleSpinBox()
        self.color_b.setRange(0, 1)
        self.color_b.setSingleStep(0.01)
        self.color_b.setValue(1.0)
        self.color_b.setPrefix("B: ")
        self.color_a = QDoubleSpinBox()
        self.color_a.setRange(0, 1)
        self.color_a.setSingleStep(0.01)
        self.color_a.setValue(1.0)
        self.color_a.setPrefix("A: ")

        # 连接数值框的值改变信号到更新颜色按钮
        self.color_r.valueChanged.connect(self._update_color_from_spinboxes)
        self.color_g.valueChanged.connect(self._update_color_from_spinboxes)
        self.color_b.valueChanged.connect(self._update_color_from_spinboxes)
        self.color_a.valueChanged.connect(self._update_color_from_spinboxes)

        color_layout.addWidget(QLabel("地图颜色:"))
        color_layout.addWidget(self.map_color_picker)
        color_layout.addWidget(self.color_r)
        color_layout.addWidget(self.color_g)
        color_layout.addWidget(self.color_b)
        color_layout.addWidget(self.color_a)
        color_layout.addStretch()

        layout.addRow(color_group)
        
        self.significant_check = QCheckBox("重要天体")
        self.significant_check.setChecked(True)
        layout.addRow("", self.significant_check)
        
        self.rotate_camera_check = QCheckBox("相机自动旋转")
        self.rotate_camera_check.setChecked(True)

        self.radius_input.unit_changed.connect(lambda: self.terrain_preview.schedule_update(self.current_body))
        layout.addRow("", self.rotate_camera_check)
        # 从模板导入基本参数按钮
        btn_import_basic = QPushButton("从模板导入基本参数")
        btn_import_basic.clicked.connect(self.import_basic_from_template)
        layout.addRow(btn_import_basic)


    def setup_atmo_physics_tab(self):
        tab = QWidget()
        self.tab_widget.addTab(tab, "大气物理")
        layout = QFormLayout()
        tab.setLayout(layout)

        self.atmo_enable = QCheckBox("启用大气（无大气天体请取消勾选）")
        self.atmo_enable.setChecked(True)
        self.atmo_enable.toggled.connect(self.on_atmo_enable_toggled)
        layout.addRow("", self.atmo_enable)

        self.atmo_physics_container = QWidget()
        container_layout = QFormLayout(self.atmo_physics_container)
        container_layout.setContentsMargins(20, 0, 0, 0)

        self.atmo_height = QDoubleSpinBox()
        self.atmo_height.setRange(0, 1e30)
        self.atmo_height.setValue(30)
        self.atmo_height.setSuffix(" km")
        container_layout.addRow("大气高度:", self.atmo_height)

        self.atmo_density = QDoubleSpinBox()
        self.atmo_density.setRange(0, 1e30)
        self.atmo_density.setValue(0.005)
        self.atmo_density.setSingleStep(0.001)
        container_layout.addRow("大气密度:", self.atmo_density)

        self.atmo_curve = QDoubleSpinBox()
        self.atmo_curve.setRange(0, 1e30)
        self.atmo_curve.setValue(10.0)
        container_layout.addRow("密度梯度曲率:", self.atmo_curve)

        self.parachute_mult = QDoubleSpinBox()
        self.parachute_mult.setRange(0, 1e30)
        self.parachute_mult.setValue(1.0)
        container_layout.addRow("降落伞倍数:", self.parachute_mult)

        self.upper_atmo = QDoubleSpinBox()
        self.upper_atmo.setRange(0, 1e30)
        self.upper_atmo.setValue(0.333)
        container_layout.addRow("高层大气比例:", self.upper_atmo)

        self.shockwave_intensity = QDoubleSpinBox()
        self.shockwave_intensity.setRange(0, 1e30)
        self.shockwave_intensity.setValue(1.0)
        container_layout.addRow("激波强度:", self.shockwave_intensity)

        self.min_heating_velocity = QDoubleSpinBox()
        self.min_heating_velocity.setRange(0, 1e30)
        self.min_heating_velocity.setValue(1.0)
        container_layout.addRow("最小加热速度倍数:", self.min_heating_velocity)

        self.atmo_height.setDecimals(5)
        self.atmo_density.setDecimals(5)
        self.atmo_curve.setDecimals(5)
        self.parachute_mult.setDecimals(5)
        self.upper_atmo.setDecimals(5)
        self.shockwave_intensity.setDecimals(5)
        self.min_heating_velocity.setDecimals(5)

        self.atmo_height.valueChanged.connect(lambda: self.terrain_preview.schedule_update(self.current_body))

        layout.addRow(self.atmo_physics_container)
        self.on_atmo_enable_toggled(self.atmo_enable.isChecked())

        btn_import_atmo_phys = QPushButton("从模板导入大气物理")
        btn_import_atmo_phys.clicked.connect(self.import_atmo_phys_from_template)
        layout.addRow(btn_import_atmo_phys)

    def import_atmo_phys_from_template(self):
        def apply(template):
            atmo = template.get("ATMOSPHERE_PHYSICS_DATA", {})
            if not atmo:
                QMessageBox.warning(self, "警告", "所选模板没有 ATMOSPHERE_PHYSICS_DATA 数据。")
                return
            self.atmo_height.setValue(atmo.get("height", 30000) / 1000.0)
            self.atmo_density.setValue(atmo.get("density", 0.005))
            self.atmo_curve.setValue(atmo.get("curve", 10.0))
            self.parachute_mult.setValue(atmo.get("parachuteMultiplier", 1.0))
            self.upper_atmo.setValue(atmo.get("upperAtmosphere", 0.333))
            self.shockwave_intensity.setValue(atmo.get("shockwaveIntensity", 1.0))
            self.min_heating_velocity.setValue(atmo.get("minHeatingVelocityMultiplier", 1.0))
            self.save_ui_to_body(self.current_body)
            self.terrain_preview.schedule_update(self.current_body)
            QMessageBox.information(self, "成功", "大气物理数据已从模板导入。")
        self._show_template_dialog("大气物理", apply)

    def on_atmo_enable_toggled(self, checked):
        self.atmo_physics_container.setEnabled(checked)
        # 同时控制大气视觉标签页和远景外观纹理标签页的控件启用状态
        if hasattr(self, 'atmo_visuals_container'):
            self.atmo_visuals_container.setEnabled(checked)
        if hasattr(self, 'front_clouds_container'):
            self.front_clouds_container.setEnabled(checked)

    def setup_atmo_visuals_tab(self):
        tab = QWidget()
        self.tab_widget.addTab(tab, "大气视觉")
        layout = QFormLayout()
        tab.setLayout(layout)

        # 创建容器，用于总开关控制
        self.atmo_visuals_container = QWidget()
        container_layout = QFormLayout(self.atmo_visuals_container)
        container_layout.setContentsMargins(0, 0, 0, 0)

        # ---------- 渐变 ----------
        atmo_texture_layout = QHBoxLayout()
        self.atmo_gradient_texture = QLineEdit("Atmo_Earth")
        btn_atmo_texture = QPushButton("选择")
        btn_atmo_texture.clicked.connect(lambda: self.select_texture(self.atmo_gradient_texture))
        atmo_texture_layout.addWidget(self.atmo_gradient_texture)
        atmo_texture_layout.addWidget(btn_atmo_texture)
        container_layout.addRow("大气纹理:", atmo_texture_layout)
        self.atmo_gradient_height = QDoubleSpinBox()
        self.atmo_gradient_height.setRange(0, 1e30)
        self.atmo_gradient_height.setValue(45000)
        self.atmo_gradient_height.setSuffix(" m")
        container_layout.addRow("渐变高度:", self.atmo_gradient_height)
        self.atmo_position_z = QDoubleSpinBox()
        self.atmo_position_z.setRange(-1e30, 1e30)
        self.atmo_position_z.setValue(4000)
        container_layout.addRow("Z轴偏移:", self.atmo_position_z)

        # ---------- 云层（带启用开关） ----------
        self.clouds_enable = QCheckBox("启用云层")
        self.clouds_enable.setChecked(True)
        self.clouds_enable.toggled.connect(self.on_clouds_enable_toggled)
        container_layout.addRow("", self.clouds_enable)

        cloud_group = QWidget()
        cloud_layout = QFormLayout(cloud_group)
        cloud_layout.setContentsMargins(20, 0, 0, 0)

        cloud_texture_layout = QHBoxLayout()
        self.cloud_texture = QLineEdit("Earth_Clouds")
        btn_cloud_texture = QPushButton("选择")
        btn_cloud_texture.clicked.connect(lambda: self.select_texture(self.cloud_texture))
        cloud_texture_layout.addWidget(self.cloud_texture)
        cloud_texture_layout.addWidget(btn_cloud_texture)
        cloud_layout.addRow("云层纹理:", cloud_texture_layout)
        self.cloud_start_height = QDoubleSpinBox()
        self.cloud_start_height.setRange(0, 1e30)
        self.cloud_start_height.setValue(1200)
        cloud_layout.addRow("起始高度(m):", self.cloud_start_height)
        self.cloud_width = QDoubleSpinBox()
        self.cloud_width.setRange(0, 1e30)
        self.cloud_width.setValue(40845.87)
        cloud_layout.addRow("宽度(m):", self.cloud_width)
        self.cloud_height = QDoubleSpinBox()
        self.cloud_height.setRange(0, 1e30)
        self.cloud_height.setValue(36000)
        cloud_layout.addRow("高度(m):", self.cloud_height)
        self.cloud_alpha = QDoubleSpinBox()
        self.cloud_alpha.setRange(0, 1)
        self.cloud_alpha.setValue(0.1)
        cloud_layout.addRow("透明度:", self.cloud_alpha)
        self.cloud_velocity = QDoubleSpinBox()
        self.cloud_velocity.setRange(0, 1e30)
        self.cloud_velocity.setValue(2.0)
        cloud_layout.addRow("速度:", self.cloud_velocity)

        container_layout.addRow(cloud_group)
        self.on_clouds_enable_toggled(self.clouds_enable.isChecked())

        # ---------- 雾（带启用开关） ----------
        self.fog_enable = QCheckBox("启用雾")
        self.fog_enable.setChecked(True)
        self.fog_enable.toggled.connect(self.on_fog_enable_toggled)
        container_layout.addRow("", self.fog_enable)

        fog_group = QWidget()
        fog_layout = QFormLayout(fog_group)
        fog_layout.setContentsMargins(20, 0, 0, 0)

        self.fog_key0_dist = QDoubleSpinBox()
        self.fog_key0_dist.setRange(0, 1e30)
        self.fog_key0_dist.setValue(500)
        fog_layout.addRow("雾距离1(m):", self.fog_key0_dist)
        self.fog_key1_dist = QDoubleSpinBox()
        self.fog_key1_dist.setRange(0, 1e30)
        self.fog_key1_dist.setValue(3000)
        fog_layout.addRow("雾距离2(m):", self.fog_key1_dist)
        self.fog_key2_dist = QDoubleSpinBox()
        self.fog_key2_dist.setRange(0, 1e30)
        self.fog_key2_dist.setValue(30000)
        fog_layout.addRow("雾距离3(m):", self.fog_key2_dist)

        container_layout.addRow(fog_group)
        self.on_fog_enable_toggled(self.fog_enable.isChecked())

        layout.addRow(self.atmo_visuals_container)
        # 初始状态由总开关控制，先设为禁用，等待 on_atmo_enable_toggled 启用
        self.atmo_visuals_container.setEnabled(False)

        btn_import_atmo_vis = QPushButton("从模板导入大气视觉")
        btn_import_atmo_vis.clicked.connect(self.import_atmo_vis_from_template)
        layout.addRow(btn_import_atmo_vis)

    def import_atmo_vis_from_template(self):
        def apply(template):
            atmo_vis = template.get("ATMOSPHERE_VISUALS_DATA", {})
            if not atmo_vis:
                QMessageBox.warning(self, "警告", "所选模板没有 ATMOSPHERE_VISUALS_DATA 数据。")
                return
            # 渐变
            grad = atmo_vis.get("GRADIENT", {})
            self.atmo_gradient_texture.setText(grad.get("texture", "Atmo_Earth"))
            self.atmo_gradient_height.setValue(grad.get("height", 45000))
            self.atmo_position_z.setValue(grad.get("positionZ", 4000))
            # 云层
            clouds = atmo_vis.get("CLOUDS", {})
            has_clouds = clouds.get("texture", "None") != "None"
            self.clouds_enable.setChecked(has_clouds)
            if has_clouds:
                self.cloud_texture.setText(clouds.get("texture", "Earth_Clouds"))
                self.cloud_start_height.setValue(clouds.get("startHeight", 1200))
                self.cloud_width.setValue(clouds.get("width", 40845.87))
                self.cloud_height.setValue(clouds.get("height", 36000))
                self.cloud_alpha.setValue(clouds.get("alpha", 0.1))
                self.cloud_velocity.setValue(clouds.get("velocity", 2.0))
            else:
                self.cloud_texture.setText("None")
                self.cloud_start_height.setValue(0)
                self.cloud_width.setValue(0)
                self.cloud_height.setValue(0)
                self.cloud_alpha.setValue(0)
                self.cloud_velocity.setValue(0)
            # 雾
            fog = atmo_vis.get("FOG", {})
            fog_keys = fog.get("keys", [])
            has_fog = len(fog_keys) > 0
            self.fog_enable.setChecked(has_fog)
            if has_fog:
                if len(fog_keys) >= 1:
                    self.fog_key0_dist.setValue(fog_keys[0].get("distance", 500))
                if len(fog_keys) >= 2:
                    self.fog_key1_dist.setValue(fog_keys[1].get("distance", 3000))
                if len(fog_keys) >= 3:
                    self.fog_key2_dist.setValue(fog_keys[2].get("distance", 30000))
            else:
                self.fog_key0_dist.setValue(500)
                self.fog_key1_dist.setValue(3000)
                self.fog_key2_dist.setValue(30000)
            self.save_ui_to_body(self.current_body)
            self.terrain_preview.schedule_update(self.current_body)
            QMessageBox.information(self, "成功", "大气视觉数据已从模板导入。")
        self._show_template_dialog("大气视觉", apply)

    def on_clouds_enable_toggled(self, checked):
        # 根据“启用云层”复选框状态，禁用/启用云层相关控件
        # 注意：这些控件都在 cloud_group 中，但为了方便，我们逐个设置
        self.cloud_texture.setEnabled(checked)
        self.cloud_start_height.setEnabled(checked)
        self.cloud_width.setEnabled(checked)
        self.cloud_height.setEnabled(checked)
        self.cloud_alpha.setEnabled(checked)
        self.cloud_velocity.setEnabled(checked)

    def on_fog_enable_toggled(self, checked):
        self.fog_key0_dist.setEnabled(checked)
        self.fog_key1_dist.setEnabled(checked)
        self.fog_key2_dist.setEnabled(checked)

    def setup_front_clouds_tab(self):
        tab = QWidget()
        self.tab_widget.addTab(tab, "大气远景外观纹理")
        layout = QFormLayout()
        tab.setLayout(layout)

        # 创建容器，用于总开关控制
        self.front_clouds_container = QWidget()
        container_layout = QFormLayout(self.front_clouds_container)
        container_layout.setContentsMargins(0, 0, 0, 0)

        self.front_clouds_enable = QCheckBox("启用大气远景外观纹理")
        self.front_clouds_enable.setChecked(False)
        self.front_clouds_enable.toggled.connect(self.on_front_clouds_enable_toggled)
        container_layout.addRow("", self.front_clouds_enable)

        front_clouds_layout = QHBoxLayout()
        self.front_clouds_texture = QLineEdit("Earth_Clouds_Front")
        btn_front_clouds = QPushButton("选择")
        btn_front_clouds.clicked.connect(lambda: self.select_texture(self.front_clouds_texture))
        front_clouds_layout.addWidget(self.front_clouds_texture)
        front_clouds_layout.addWidget(btn_front_clouds)
        container_layout.addRow("远景外观层纹理:", front_clouds_layout)
        self.front_clouds_cutout = QDoubleSpinBox()
        self.front_clouds_cutout.setRange(0, 1e30)
        self.front_clouds_cutout.setValue(1.0)
        container_layout.addRow("纹理裁剪:", self.front_clouds_cutout)
        self.front_clouds_fade_height = QDoubleSpinBox()
        self.front_clouds_fade_height.setRange(0, 1e30)
        self.front_clouds_fade_height.setValue(20000)
        container_layout.addRow("淡出高度(m):", self.front_clouds_fade_height)
        self.front_clouds_height = QDoubleSpinBox()
        self.front_clouds_height.setRange(0, 1e30)
        self.front_clouds_height.setValue(10000)
        container_layout.addRow("云层高度(m):", self.front_clouds_height)
        self.front_clouds_pos_z = QDoubleSpinBox()
        self.front_clouds_pos_z.setRange(-1e30, 1e30)
        self.front_clouds_pos_z.setValue(-5000)
        container_layout.addRow("Z轴偏移:", self.front_clouds_pos_z)
        self.front_clouds_sharpen = QCheckBox("锐化Alpha")
        self.front_clouds_sharpen.setChecked(True)
        container_layout.addRow("", self.front_clouds_sharpen)

        layout.addRow(self.front_clouds_container)
        self.front_clouds_container.setEnabled(False)

        btn_import_front = QPushButton("从模板导入远景外观纹理")
        btn_import_front.clicked.connect(self.import_front_from_template)
        layout.addRow(btn_import_front)

        # 根据复选框禁用控件（初始状态）
        self.front_clouds_texture.setEnabled(False)
        self.front_clouds_cutout.setEnabled(False)
        self.front_clouds_fade_height.setEnabled(False)
        self.front_clouds_height.setEnabled(False)
        self.front_clouds_pos_z.setEnabled(False)
        self.front_clouds_sharpen.setEnabled(False)

    def import_front_from_template(self):
        def apply(template):
            front = template.get("FRONT_CLOUDS_DATA", {})
            if not front:
                QMessageBox.warning(self, "警告", "所选模板没有 FRONT_CLOUDS_DATA 数据。")
                return
            self.front_clouds_enable.setChecked(True)
            self.front_clouds_texture.setText(front.get("cloudsTexture", "Earth_Clouds_Front"))
            self.front_clouds_cutout.setValue(front.get("cloudTextureCutout", 1.0))
            self.front_clouds_fade_height.setValue(front.get("fadeZoneHeight", 20000))
            self.front_clouds_height.setValue(front.get("height", 10000))
            self.front_clouds_pos_z.setValue(front.get("positionZ", -5000))
            self.front_clouds_sharpen.setChecked(front.get("sharpenAlpha", True))
            self.save_ui_to_body(self.current_body)
            self.terrain_preview.schedule_update(self.current_body)
            QMessageBox.information(self, "成功", "远景外观纹理数据已从模板导入。")
        self._show_template_dialog("远景外观纹理", apply)

    def on_front_clouds_enable_toggled(self, checked):
        self.front_clouds_texture.setEnabled(checked)
        self.front_clouds_cutout.setEnabled(checked)
        self.front_clouds_fade_height.setEnabled(checked)
        self.front_clouds_height.setEnabled(checked)
        self.front_clouds_pos_z.setEnabled(checked)
        self.front_clouds_sharpen.setEnabled(checked)

    def on_water_enable_toggled(self, checked):
        self.ocean_mask_texture.setEnabled(checked)
        self.ocean_depth.setEnabled(checked)

    def on_rings_enable_toggled(self, checked):
        self.rings_texture.setEnabled(checked)
        self.rings_start_radius.setEnabled(checked)
        self.rings_end_radius.setEnabled(checked)
        self.rings_pos_z.setEnabled(checked)

    def setup_terrain_tab(self):
        tab = QWidget()
        self.tab_widget.addTab(tab, "地形纹理")
        layout = QFormLayout()
        tab.setLayout(layout)

        # ---------- 启用固体表面复选框 ----------
        self.terrain_enable = QCheckBox("启用固体表面地形（气态巨行星请取消勾选）")
        self.terrain_enable.setChecked(True)
        self.terrain_enable.toggled.connect(self.on_terrain_enable_toggled)
        layout.addRow("", self.terrain_enable)

        # 创建一个容器，放置所有地形相关控件，以便统一启用/禁用
        self.terrain_container = QWidget()
        container_layout = QFormLayout(self.terrain_container)
        container_layout.setContentsMargins(20, 0, 0, 0)

        # 行星纹理
        planet_texture_layout = QHBoxLayout()
        self.planet_texture = QLineEdit("Earth_WithOceans")
        btn_planet_texture = QPushButton("选择")
        btn_planet_texture.clicked.connect(lambda: self.select_texture(self.planet_texture))
        planet_texture_layout.addWidget(self.planet_texture)
        planet_texture_layout.addWidget(btn_planet_texture)
        container_layout.addRow("行星纹理:", planet_texture_layout)
        self.planet_texture_cutout = QDoubleSpinBox()
        self.planet_texture_cutout.setRange(-1e30, 1e30)
        self.planet_texture_cutout.setValue(0.9947)
        self.planet_texture_cutout.setDecimals(5)
        container_layout.addRow("纹理裁剪:", self.planet_texture_cutout)
        self.planet_texture_rotation = QDoubleSpinBox()
        self.planet_texture_rotation.setRange(0, 1e30)
        self.planet_texture_rotation.setValue(1.85)
        container_layout.addRow("纹理旋转(rad):", self.planet_texture_rotation)
        self.planet_texture_dont_distort = QCheckBox("不扭曲纹理")
        self.planet_texture_dont_distort.setChecked(True)
        container_layout.addRow("", self.planet_texture_dont_distort)

        self.vertice_size = QDoubleSpinBox()
        self.vertice_size.setRange(-1e30, 1e30)
        self.vertice_size.setValue(2.0)
        container_layout.addRow("顶点大小:", self.vertice_size)

        self.collider_check = QCheckBox("启用碰撞体")
        self.collider_check.setChecked(True)
        container_layout.addRow("", self.collider_check)

        # 地形公式编辑器（结构化）
        self.terrain_formula_editor = TerrainFormulaEditor()
        # 设置地形函数下拉列表（从 constants 中获取 HEIGHTMAP_DATA 的键名）
        from constants import HEIGHTMAP_DATA
        heightmap_names = sorted(HEIGHTMAP_DATA.keys())
        self.terrain_formula_editor.set_heightmap_names(heightmap_names)
        # 连接公式变化信号到地形预览更新
        container_layout.addRow("地形公式:", self.terrain_formula_editor)

        # flatZones
        self.flat_zones = QTextEdit()
        self.flat_zones.setPlainText('[{"height": 48.0, "angle": 1.5707, "width": 900.0, "transition": 700.0}]')
        container_layout.addRow("平坦区(JSON):", self.flat_zones)
        btn_format_flat = QPushButton("格式化 JSON")
        btn_format_flat.clicked.connect(self.format_flat_zones)
        container_layout.addRow(btn_format_flat)

        # ---------- 贴图公式（textureFormula）----------
        self.texture_formula_label = QLabel("贴图公式 (textureFormula):")
        self.texture_formula_edit = QTextEdit()
        self.texture_formula_edit.setPlaceholderText("每行一条表达式，例如:\nOUTPUT = AddHeightMap(Perlin, 6793.69411338793, 1, Curve8)\nOUTPUT = ApplyCurve(Curve8)")
        container_layout.addRow(self.texture_formula_label, self.texture_formula_edit)

        # 贴图公式导入按钮
        btn_import_texture_formula = QPushButton("从模板导入贴图公式")
        btn_import_texture_formula.clicked.connect(self.import_texture_formula_from_template)
        container_layout.addRow(btn_import_texture_formula)

        # ---------- 岩石装饰（rocks）----------
        self.rocks_enable = QCheckBox("启用岩石装饰 (rocks)")
        self.rocks_enable.setChecked(False)
        self.rocks_enable.toggled.connect(self.on_rocks_enable_toggled)
        container_layout.addRow("", self.rocks_enable)

        self.rocks_container = QWidget()
        rocks_layout = QFormLayout(self.rocks_container)
        rocks_layout.setContentsMargins(20, 0, 0, 0)

        self.rock_type = QComboBox()
        self.rock_type.addItems(["Rock Square", "Rock Round", "Rock Sharp", "None"])
        rocks_layout.addRow("岩石类型 (rockType):", self.rock_type)

        self.rock_density = QDoubleSpinBox()
        self.rock_density.setRange(0, 1e30)
        self.rock_density.setValue(0.7)
        self.rock_density.setSingleStep(0.05)
        rocks_layout.addRow("密度 (rockDensity):", self.rock_density)

        self.rock_min_size = QDoubleSpinBox()
        self.rock_min_size.setRange(0, 1e30)
        self.rock_min_size.setValue(0.2)
        self.rock_min_size.setSingleStep(0.05)
        rocks_layout.addRow("最小尺寸 (minSize):", self.rock_min_size)

        self.rock_max_size = QDoubleSpinBox()
        self.rock_max_size.setRange(0, 1e30)
        self.rock_max_size.setValue(0.8)
        self.rock_max_size.setSingleStep(0.05)
        rocks_layout.addRow("最大尺寸 (maxSize):", self.rock_max_size)

        self.rock_power_curve = QDoubleSpinBox()
        self.rock_power_curve.setRange(0, 1e30)
        self.rock_power_curve.setValue(2.0)
        self.rock_power_curve.setSingleStep(0.1)
        rocks_layout.addRow("功率曲线 (powerCurve):", self.rock_power_curve)

        self.rock_max_angle = QDoubleSpinBox()
        self.rock_max_angle.setRange(0, 90)
        self.rock_max_angle.setValue(25.0)
        self.rock_max_angle.setSuffix("°")
        rocks_layout.addRow("最大角度 (maxAngle):", self.rock_max_angle)

        container_layout.addRow(self.rocks_container)
        self.on_rocks_enable_toggled(False)  # 初始禁用

        # 地表细节 JSON 编辑器
        group = QGroupBox("地表细节参数 (JSON)")
        group_layout = QVBoxLayout()
        group.setLayout(group_layout)
        self.terrain_details_json = QTextEdit()
        self.terrain_details_json.setPlaceholderText("{\n  \"surfaceTexture_A\": \"Blured02\",\n  \"surfaceTextureSize_A\": {\"x\": 20.0, \"y\": 8.0},\n  ...}")
        group_layout.addWidget(self.terrain_details_json)

        # 模板选择
        template_layout = QHBoxLayout()
        template_layout.addWidget(QLabel("地表细节模板:"))
        self.terrain_template_combo = QComboBox()
        template_layout.addWidget(self.terrain_template_combo)
        btn_apply = QPushButton("应用模板")
        btn_apply.clicked.connect(self.apply_terrain_template)
        template_layout.addWidget(btn_apply)
        group_layout.addLayout(template_layout)
        container_layout.addRow(group)

        btn_import_terrain = QPushButton("从模板导入地形纹理数据")
        btn_import_terrain.clicked.connect(self.import_terrain_from_template)
        container_layout.addRow(btn_import_terrain)

        layout.addRow(self.terrain_container)

        # 加载模板列表
        self.load_terrain_templates()

        # 初始根据复选框状态启用/禁用容器
        self.on_terrain_enable_toggled(self.terrain_enable.isChecked())

    def import_terrain_from_template(self):
        def apply(template):
            terrain = template.get("TERRAIN_DATA", {})
            if not terrain:
                QMessageBox.warning(self, "警告", "所选模板没有 TERRAIN_DATA 数据。")
                return
            tex_data = terrain.get("TERRAIN_TEXTURE_DATA", {})
            if tex_data:
                self.planet_texture.setText(tex_data.get("planetTexture", "Earth_WithOceans"))
                self.planet_texture_cutout.setValue(tex_data.get("planetTextureCutout", 0.9947))
                self.planet_texture_rotation.setValue(tex_data.get("planetTextureRotation", 1.85))
                self.planet_texture_dont_distort.setChecked(tex_data.get("planetTextureDontDistort", True))
                preserved_keys = ["planetTexture", "planetTextureCutout", "planetTextureRotation", "planetTextureDontDistort"]
                other_details = {k: v for k, v in tex_data.items() if k not in preserved_keys}
                self.terrain_details_json.setPlainText(json.dumps(other_details, indent=2))
            # 平坦区
            flat_zones = terrain.get("flatZones", [])
            self.flat_zones.setPlainText(json.dumps(flat_zones, indent=2) if flat_zones else "[]")
            # 岩石装饰
            rocks = terrain.get("rocks", {})
            if rocks:
                self.rocks_enable.setChecked(True)
                self.rock_type.setCurrentText(rocks.get("rockType", "Rock Square"))
                self.rock_density.setValue(rocks.get("rockDensity", 0.7))
                self.rock_min_size.setValue(rocks.get("minSize", 0.2))
                self.rock_max_size.setValue(rocks.get("maxSize", 0.8))
                self.rock_power_curve.setValue(rocks.get("powerCurve", 2.0))
                self.rock_max_angle.setValue(rocks.get("maxAngle", 25.0))
            else:
                self.rocks_enable.setChecked(False)
            # 注意：地形公式和贴图公式不自动导入，保留原样（避免覆盖用户自定义）
            self.save_ui_to_body(self.current_body)
            self.terrain_preview.schedule_update(self.current_body)
            QMessageBox.information(self, "成功", "地形纹理数据已从模板导入（不包括地形公式和贴图公式）。")
        self._show_template_dialog("地形纹理", apply)

    def import_texture_formula_from_template(self):
        """从模板导入贴图公式"""
        def apply(template):
            terrain = template.get("TERRAIN_DATA", {})
            texture_formula = terrain.get("textureFormula", [])
            if not texture_formula:
                QMessageBox.warning(self, "警告", "所选模板没有贴图公式数据。")
                return
            self.texture_formula_edit.setPlainText("\n".join(texture_formula))
            self.save_ui_to_body(self.current_body)
            self.terrain_preview.schedule_update(self.current_body)
            QMessageBox.information(self, "成功", "贴图公式已从模板导入。")
        self._show_template_dialog("贴图公式", apply)

    def on_rocks_enable_toggled(self, checked):
        self.rocks_container.setEnabled(checked)

    def on_terrain_enable_toggled(self, checked):
        """根据地形启用复选框，禁用/启用整个地形容器内的所有控件"""
        self.terrain_container.setEnabled(checked)

    def load_terrain_templates(self):
        """从外部 JSON 文件加载地形模板名称列表"""
        templates_file = resource_path("terrain_templates.json")
        if os.path.exists(templates_file):
            try:
                with open(templates_file, 'r', encoding='utf-8') as f:
                    self.terrain_templates_data = json.load(f)
                self.terrain_template_combo.clear()
                self.terrain_template_combo.addItem("自定义 (保持当前)")
                for name in self.terrain_templates_data.keys():
                    self.terrain_template_combo.addItem(name)
            except Exception as e:
                QMessageBox.warning(self, "警告", f"加载地形模板文件失败: {e}")
                self.terrain_templates_data = {}
        else:
            self.terrain_templates_data = {}
            self.terrain_template_combo.clear()
            self.terrain_template_combo.addItem("自定义 (保持当前)")

    def apply_terrain_template(self):
        """将选中的模板应用到 JSON 文本框"""
        selected = self.terrain_template_combo.currentText()
        if selected == "自定义 (保持当前)" or not self.terrain_templates_data:
            return
        if selected in self.terrain_templates_data:
            template = self.terrain_templates_data[selected]
            # 将模板内容格式化为 JSON 字符串并显示
            json_str = json.dumps(template, indent=2)
            self.terrain_details_json.setPlainText(json_str)
        else:
            QMessageBox.warning(self, "警告", f"未找到模板: {selected}")

    def setup_water_tab(self):
        tab = QWidget()
        self.tab_widget.addTab(tab, "水体")
        layout = QFormLayout()
        tab.setLayout(layout)
        
        self.water_enable = QCheckBox("启用水体")
        self.water_enable.setChecked(False)
        self.water_enable.toggled.connect(self.on_water_enable_toggled)
        layout.addRow("", self.water_enable)
        
        ocean_mask_layout = QHBoxLayout()
        self.ocean_mask_texture = QLineEdit("Earth_OceanMask_V2")
        btn_ocean_mask = QPushButton("选择")
        btn_ocean_mask.clicked.connect(lambda: self.select_texture(self.ocean_mask_texture))
        ocean_mask_layout.addWidget(self.ocean_mask_texture)
        ocean_mask_layout.addWidget(btn_ocean_mask)
        layout.addRow("海洋遮罩纹理:", ocean_mask_layout)
        self.ocean_depth = QDoubleSpinBox()
        self.ocean_depth.setRange(0, 1e30)
        self.ocean_depth.setValue(5000)
        layout.addRow("海洋深度(m):", self.ocean_depth)
        # 颜色简化，后续可用颜色选择器
        layout.addRow("注:", QLabel("颜色等参数将在导出时使用默认值，后续可扩展"))
        self.ocean_mask_texture.setEnabled(False)
        # 可根据启用复选框来启用/禁用

        btn_import_water = QPushButton("从模板导入水体数据")
        btn_import_water.clicked.connect(self.import_water_from_template)
        layout.addRow(btn_import_water)

    def import_water_from_template(self):
        def apply(template):
            water = template.get("WATER_DATA", {})
            if not water:
                QMessageBox.warning(self, "警告", "所选模板没有 WATER_DATA 数据。")
                return
            self.water_enable.setChecked(True)
            self.ocean_mask_texture.setText(water.get("oceanMaskTexture", "Earth_OceanMask_V2"))
            self.ocean_depth.setValue(water.get("oceanDepth", 5000))
            self.save_ui_to_body(self.current_body)
            self.terrain_preview.schedule_update(self.current_body)
            QMessageBox.information(self, "成功", "水体数据已从模板导入。")
        self._show_template_dialog("水体", apply)

    def setup_rings_tab(self):
        tab = QWidget()
        self.tab_widget.addTab(tab, "光环")
        layout = QFormLayout()
        tab.setLayout(layout)
    
        self.rings_enable = QCheckBox("启用光环")
        self.rings_enable.setChecked(False)
        self.rings_enable.toggled.connect(self.on_rings_enable_toggled)
        layout.addRow("", self.rings_enable)
    
        rings_texture_layout = QHBoxLayout()
        self.rings_texture = QLineEdit("Saturn_Rings")
        btn_rings_texture = QPushButton("选择")
        btn_rings_texture.clicked.connect(lambda: self.select_texture(self.rings_texture))
        rings_texture_layout.addWidget(self.rings_texture)
        rings_texture_layout.addWidget(btn_rings_texture)
        layout.addRow("光环纹理:", rings_texture_layout)
    
        # 替换为 UnitSpinBox（支持单位换算）
        self.rings_start_radius = UnitSpinBox(initial_value=3800000, initial_unit="m",
                                          min_val=0, max_val=1e50, decimals=12)
        layout.addRow("内半径:", self.rings_start_radius)
    
        self.rings_end_radius = UnitSpinBox(initial_value=6600000, initial_unit="m",
                                        min_val=0, max_val=1e50, decimals=12)
        layout.addRow("外半径:", self.rings_end_radius)
    
        self.rings_pos_z = QDoubleSpinBox()
        self.rings_pos_z.setRange(-1e30, 1e30)
        self.rings_pos_z.setValue(5000)
        layout.addRow("Z轴偏移:", self.rings_pos_z)

        self.rings_enable.toggled.connect(lambda: self.terrain_preview.schedule_update(self.current_body))
        self.rings_start_radius.unit_changed.connect(lambda: self.terrain_preview.schedule_update(self.current_body))
        self.rings_end_radius.unit_changed.connect(lambda: self.terrain_preview.schedule_update(self.current_body))

        self.rings_texture.setEnabled(False)

        btn_import_rings = QPushButton("从模板导入光环数据")
        btn_import_rings.clicked.connect(self.import_rings_from_template)
        layout.addRow(btn_import_rings)

    def import_rings_from_template(self):
        def apply(template):
            rings = template.get("RINGS_DATA", {})
            if not rings:
                QMessageBox.warning(self, "警告", "所选模板没有 RINGS_DATA 数据。")
                return
            self.rings_enable.setChecked(True)
            self.rings_texture.setText(rings.get("ringsTexture", "Saturn_Rings"))
            start_radius_game = rings.get("startRadius", 3800000.0)
            end_radius_game = rings.get("endRadius", 6600000.0)
            self.rings_start_radius.set_game_value(start_radius_game)
            self.rings_end_radius.set_game_value(end_radius_game)
            self.rings_pos_z.setValue(rings.get("positionZ", 5000))
            self.save_ui_to_body(self.current_body)
            self.terrain_preview.schedule_update(self.current_body)
            QMessageBox.information(self, "成功", "光环数据已从模板导入。")
        self._show_template_dialog("光环", apply)

    def setup_post_processing_tab(self):
        tab = QWidget()
        self.tab_widget.addTab(tab, "后期处理")
        layout = QFormLayout()
        tab.setLayout(layout)
        
        # 简化，提供一个多行编辑让用户输入JSON keys
        self.pp_keys = QTextEdit()
        self.pp_keys.setPlainText('''[
  {
    "height": 0.0,
    "shadowIntensity": 1.35,
    "starIntensity": 0.0,
    "hueShift": 0.0,
    "saturation": 0.95,
    "contrast": 1.2,
    "red": 1.03,
    "green": 1.02,
    "blue": 1.0
  },
  {
    "height": 7000.0,
    "shadowIntensity": 1.5,
    "starIntensity": 0.0,
    "hueShift": 0.0,
    "saturation": 0.95,
    "contrast": 1.2,
    "red": 1.0,
    "green": 1.0,
    "blue": 1.0
  }
]''')
        layout.addRow("后期处理关键帧(JSON):", self.pp_keys)
        btn_format_pp = QPushButton("格式化 JSON")
        btn_format_pp.clicked.connect(self.format_pp_keys)
        layout.addRow(btn_format_pp)

    def setup_orbit_tab(self):
        tab = QWidget()
        self.tab_widget.addTab(tab, "轨道")
        main_layout = QVBoxLayout(tab)

        param_widget = QWidget()
        layout = QFormLayout(param_widget)
        parent_layout = QHBoxLayout()
        self.orbit_parent = QLineEdit("Sun")
        btn_parent_select = QPushButton("选择")
        btn_parent_select.clicked.connect(self.select_orbit_parent)
        parent_layout.addWidget(self.orbit_parent)
        parent_layout.addWidget(btn_parent_select)
        layout.addRow("中心天体:", parent_layout)

        self.semi_major_input = UnitSpinBox(initial_value=7480000000, initial_unit="km",
                                            min_val=0, max_val=1e50, decimals=12)
        self.semi_major_input.unit_changed.connect(self.on_radius_or_semi_changed)
        layout.addRow("半长轴:", self.semi_major_input)

        self.eccentricity = QDoubleSpinBox()
        self.eccentricity.setRange(0, 1)
        self.eccentricity.setDecimals(10)
        self.eccentricity.setValue(0.0)
        layout.addRow("偏心率:", self.eccentricity)

        self.arg_of_periapsis = QDoubleSpinBox()
        self.arg_of_periapsis.setRange(0, 1e30)
        self.arg_of_periapsis.setValue(0.0)
        layout.addRow("近地点辐角(deg):", self.arg_of_periapsis)

        self.direction = QComboBox()
        self.direction.addItem("顺行 (1)", 1)
        self.direction.addItem("逆行 (-1)", -1)
        self.direction.addItem("静止 (0)", 0)
        layout.addRow("方向:", self.direction)
        self.direction.currentIndexChanged.connect(self.schedule_orbit_update)

        self.soi_multiplier = QDoubleSpinBox()
        self.soi_multiplier.setRange(1, 1e30)
        self.soi_multiplier.setValue(2.5)
        layout.addRow("SOI倍数:", self.soi_multiplier)

        main_layout.addWidget(param_widget)

        main_layout.addStretch()

        # 连接参数变化信号到轨道视图更新
        self.semi_major_input.unit_changed.connect(self.schedule_orbit_update)
        self.eccentricity.valueChanged.connect(self.schedule_orbit_update)
        self.arg_of_periapsis.valueChanged.connect(self.schedule_orbit_update)
        self.orbit_parent.textChanged.connect(self.schedule_orbit_update)
        self.soi_multiplier.valueChanged.connect(self.schedule_orbit_update)
        self.direction.currentIndexChanged.connect(self.schedule_orbit_update)

    def setup_landmarks_tab(self):
        tab = QWidget()
        self.tab_widget.addTab(tab, "地标")
        layout = QFormLayout()
        tab.setLayout(layout)
        
        self.landmarks_json = QTextEdit()
        self.landmarks_json.setPlainText('[\n  {\n    "name": "Space Center",\n    "startAngle": 85.0,\n    "endAngle": 95.0\n  }\n]')
        layout.addRow("地标(JSON数组):", self.landmarks_json)
        btn_format_land = QPushButton("格式化 JSON")
        btn_format_land.clicked.connect(self.format_landmarks)
        layout.addRow(btn_format_land)

    def setup_export_tab(self):
        tab = QWidget()
        self.tab_widget.addTab(tab, "导出")
        layout = QVBoxLayout()
        tab.setLayout(layout)

        # ========== 行星包导出设置 ==========
        export_group = QGroupBox("行星包导出设置")
        export_layout = QFormLayout(export_group)

        # 行星包名称
        self.export_pack_name = QLineEdit("MyPlanetPack")
        export_layout.addRow("行星包名称:", self.export_pack_name)

        # 作者
        self.export_author = QLineEdit("n/a")
        export_layout.addRow("作者:", self.export_author)

        # 版本
        self.export_version = QLineEdit("n/a")
        export_layout.addRow("版本:", self.export_version)

        # 描述（多行）
        self.export_description = QTextEdit()
        self.export_description.setPlaceholderText("行星包描述...")
        self.export_description.setMaximumHeight(80)
        export_layout.addRow("描述:", self.export_description)

        # 预留：发射台位置（Space_Center_Data）编辑（简化版）
        space_group = QGroupBox("发射台设置 (Space Center)")
        space_layout = QFormLayout(space_group)
        self.space_center_address = QLineEdit("Earth")
        space_layout.addRow("所在天体:", self.space_center_address)
        self.space_center_angle = QDoubleSpinBox()
        self.space_center_angle.setRange(0, 360)
        self.space_center_angle.setValue(90.0)
        self.space_center_angle.setSuffix("°")
        space_layout.addRow("角度:", self.space_center_angle)
        self.launchpad_horizontal = QDoubleSpinBox()
        self.launchpad_horizontal.setRange(0, 1e30)
        self.launchpad_horizontal.setValue(365.0)
        space_layout.addRow("发射台水平位置:", self.launchpad_horizontal)
        self.launchpad_height = QDoubleSpinBox()
        self.launchpad_height.setRange(0, 1e30)
        self.launchpad_height.setValue(56.2)
        space_layout.addRow("发射台高度:", self.launchpad_height)

        # 将发射台组放到导出组中（或者单独）
        export_layout.addRow(space_group)

        layout.addWidget(export_group)

        # ========== 导出按钮 ==========
        self.export_pack_btn = QPushButton("导出行星包")
        self.export_pack_btn.clicked.connect(self.export_pack)
        layout.addWidget(self.export_pack_btn)

        # ========== 分隔线 ==========
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        # ========== 单个行星文件导出 ==========
        single_export_group = QGroupBox("单个行星文件导出")
        single_layout = QVBoxLayout(single_export_group)
        self.export_btn = QPushButton("导出当前行星为 .txt 文件")
        self.export_btn.clicked.connect(self.export_planet)
        single_layout.addWidget(self.export_btn)

        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        single_layout.addWidget(QLabel("JSON预览:"))
        single_layout.addWidget(self.preview_text)

        self.update_preview_btn = QPushButton("更新预览")
        self.update_preview_btn.clicked.connect(self.update_preview)
        single_layout.addWidget(self.update_preview_btn)

        layout.addWidget(single_export_group)

    def on_name_changed(self):
        """当行星名称改变时，检查唯一性，保存当前天体并刷新树形图"""
        if not self.current_body:
            return
        new_name = self.name_edit.text()
        # 检查是否与其他天体重名（排除自身）
        if any(body.name == new_name and body != self.current_body for body in self.current_project.bodies):
            QMessageBox.warning(self, "警告", f"天体名称 '{new_name}' 已存在，已恢复原名。")
            # 恢复原名称
            self.name_edit.blockSignals(True)
            self.name_edit.setText(self.current_body.name)
            self.name_edit.blockSignals(False)
            return
        self.save_ui_to_body(self.current_body)
        self.refresh_tree()

    def on_radius_or_semi_changed(self):
        if hasattr(self, 'current_body') and self.current_body:
            self.save_ui_to_body(self.current_body)   # 保存当前数据
            self.refresh_tree()

    def select_orbit_parent(self):
        # 排除当前天体自身
        body_names = [body.name for body in self.current_project.bodies if body.name != self.current_body.name]
        if not body_names:
            QMessageBox.information(self, "提示", "没有其他天体可供选择。")
            return
        current_parent = self.orbit_parent.text()
        default_index = body_names.index(current_parent) if current_parent in body_names else 0
        parent_name, ok = QInputDialog.getItem(self, "选择中心天体", "选择母天体:", body_names, default_index, False)
        if ok and parent_name:
            self.orbit_parent.setText(parent_name)
            self.save_ui_to_body(self.current_body)
            self.refresh_tree()

    def schedule_orbit_update(self):
        """延迟 200ms 更新轨道视图，避免高频重绘"""
        if self.current_body:
            self.save_ui_to_body(self.current_body)   # 先保存当前天体的数据
        self._orbit_update_timer.start(200)

    def update_orbit_views(self):
        if not self.current_body:
            return
        self.update_child_orbit_view()
        self.update_parent_orbit_view()

    def zoom_child_view(self, factor):
        ax = self.child_view_figure.axes[0]
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        cx = (xlim[0] + xlim[1]) / 2
        cy = (ylim[0] + ylim[1]) / 2
        new_width = (xlim[1] - xlim[0]) * factor
        new_height = (ylim[1] - ylim[0]) * factor
        ax.set_xlim(cx - new_width/2, cx + new_width/2)
        ax.set_ylim(cy - new_height/2, cy + new_height/2)
        self.child_view_canvas.draw_idle()

    def reset_child_view(self):
        # 重新自动缩放
        self.update_child_orbit_view()

    def zoom_parent_view(self, factor):
        ax = self.parent_view_figure.axes[0]
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        cx = (xlim[0] + xlim[1]) / 2
        cy = (ylim[0] + ylim[1]) / 2
        new_width = (xlim[1] - xlim[0]) * factor
        new_height = (ylim[1] - ylim[0]) * factor
        ax.set_xlim(cx - new_width/2, cx + new_width/2)
        ax.set_ylim(cy - new_height/2, cy + new_height/2)
        self.parent_view_canvas.draw_idle()

    def reset_parent_view(self):
        self.update_parent_orbit_view()

    def update_child_orbit_view(self):
        """显示当前天体及其所有子天体的轨道（相对于当前天体）"""
        if not self.current_body:
            return
        fig = self.child_view_figure
        fig.clear()
        ax = fig.add_subplot(111)
        ax.set_aspect('equal')
        ax.grid(True, linestyle='--', alpha=0.5)
        ax.set_navigate(False)

        center_body = self.current_body
        center_color = body_color(center_body)

        # 获取当前天体的实际半径（米）
        center_radius_m = center_body.data.get("BASE_DATA", {}).get("radius", 0.0)

        # 收集所有子天体数据
        child_bodies = [b for b in self.current_project.bodies if b.parent == center_body.name]
        
        # 计算视图范围：基于子天体的最大轨道距离
        max_orbit = 0.0
        child_data = []
        for child in child_bodies:
            orbit_data = child.data.get("ORBIT_DATA", {})
            a = orbit_data.get("semiMajorAxis", 0.0)
            e = orbit_data.get("eccentricity", 0.0)
            omega = orbit_data.get("argumentOfPeriapsis", 0.0)
            if a == 0:
                continue
            max_orbit = max(max_orbit, a * (1 + e))
            r0 = a * (1 - e**2) / (1 + e)
            x0 = r0 * np.cos(np.radians(omega))
            y0 = r0 * np.sin(np.radians(omega))
            child_data.append({
                'body': child,
                'a': a, 'e': e, 'omega': omega,
                'x0': x0, 'y0': y0,
                'radius': child.data.get("BASE_DATA", {}).get("radius", 0.0),
                'soi': compute_soi_radius(child, center_body) if center_body else 0.0,
                'direction': child.data.get("ORBIT_DATA", {}).get("direction", 1)
            })

        # 确定视图范围
        if max_orbit > 0:
            view_range = max_orbit * 1.2
        else:
            # 没有子天体，使用天体半径的100倍作为视图范围
            view_range = max(center_radius_m * 100, 1e6)
        
        # 中心天体半径圆 - 填充颜色 + 黑色描边
        if center_radius_m > 0:
            circle = Circle((0, 0), center_radius_m, facecolor=center_color, edgecolor='gray', alpha=0.5, linewidth=0.5)
            ax.add_patch(circle)

        # 绘制中心天体的光环（如果存在）
        rings_data = center_body.data.get("RINGS_DATA", {})
        if rings_data:
            start_radius = rings_data.get("startRadius", 0)
            end_radius = rings_data.get("endRadius", 0)
            if start_radius > 0 and end_radius > start_radius:
                self._add_ring_patch(ax, 0, 0, start_radius, end_radius, center_color, alpha=0.3)

        # 中心天体标签 - 添加黑色描边
        center_label = f"{center_body.name}\nR: {UnitConverter.from_game_unit(center_radius_m, 'km'):.0f} km"
        # 标签偏移量直接使用实际半径
        label_offset = center_radius_m * 1.2
        text = ax.text(0, label_offset, center_label, ha='center', va='bottom',
                fontsize=9, color=center_color)
        text.set_path_effects([path_effects.withStroke(linewidth=0.5, foreground='gray', alpha=0.7)])

        # 如果没有子天体，显示提示
        if not child_data:
            ax.text(0.5, 0.5, "", ha='center', va='center',
                    transform=ax.transAxes, fontsize=12)
            ax.set_xlim(-view_range, view_range)
            ax.set_ylim(-view_range, view_range)
            ax.set_title(f"子天体视图")
            ax.set_xlabel("距离 (km)")
            ax.set_ylabel("距离 (km)")
            def km_formatter(x, pos):
                return f"{x/1000:.0f}" if abs(x) < 1e7 else f"{x/1e6:.1f}M"
            ax.xaxis.set_major_formatter(plt.FuncFormatter(km_formatter))
            ax.yaxis.set_major_formatter(plt.FuncFormatter(km_formatter))
            self.child_view_canvas.draw()
            return

        # 绘制子天体轨道、圆、SOI
        for d in child_data:
            color = body_color(d['body'])
            # 轨道线 - 先绘制黑色背景线（增加对比度），再绘制颜色线（仅当方向非0时绘制）
            if d['direction'] != 0:
                x, y = orbit_points(d['a'], d['e'], d['omega'], num=200)
                ax.plot(x, y, color='gray', linewidth=1.2, alpha=0.6, zorder=1)
                ax.plot(x, y, color=color, linewidth=1.5, label=d['body'].name, zorder=2)
            # 天体位置点
            ax.plot(d['x0'], d['y0'], 'o', color=color, markersize=2.5)
            # 子天体半径圆 - 填充颜色 + 黑色描边
            if d['radius'] > 0:
                child_circle = Circle((d['x0'], d['y0']), d['radius'], facecolor=color, edgecolor='gray', alpha=0.5, linewidth=0.5)
                ax.add_patch(child_circle)
            # SOI 虚线圆（如果可见）
            if d['soi'] > 0 and d['soi'] <= view_range * 0.9:
                soi_circle = Circle((d['x0'], d['y0']), d['soi'], fill=False, linestyle='--', color=color, linewidth=0.8)
                ax.add_patch(soi_circle)
            # 标签 - 添加黑色描边
            label_text = f"{d['body'].name}\nR: {UnitConverter.from_game_unit(d['radius'], 'km'):.0f} km\nA: {UnitConverter.from_game_unit(d['a'], 'km'):.0f} km"
            text = ax.annotate(label_text, xy=(d['x0'], d['y0']), xytext=(5, 5), textcoords='offset points',
                        fontsize=8, color=color)
            text.set_path_effects([path_effects.withStroke(linewidth=0.5, foreground='gray', alpha=0.7)])

        # 计算并绘制中心天体的 SOI 虚线圆（可选，如果不想显示可以注释）
        parent_of_center = None
        if center_body.type != "Center" and center_body.parent:
            parent_of_center = self.current_project.get_body(center_body.parent)
        if parent_of_center:
            center_soi = compute_soi_radius(center_body, parent_of_center)
            if center_soi > 0 and center_soi <= view_range * 0.9:
                center_soi_circle = Circle((0, 0), center_soi, fill=False, linestyle='--', color=center_color, linewidth=1, label=f"{center_body.name} SOI")
                ax.add_patch(center_soi_circle)

        ax.set_xlim(-view_range, view_range)
        ax.set_ylim(-view_range, view_range)
        ax.set_title(f"子天体视图")
        ax.set_xlabel("距离 (km)")
        ax.set_ylabel("距离 (km)")

        def km_formatter(x, pos):
            return f"{x/1000:.0f}" if abs(x) < 1e7 else f"{x/1e6:.1f}M"
        ax.xaxis.set_major_formatter(plt.FuncFormatter(km_formatter))
        ax.yaxis.set_major_formatter(plt.FuncFormatter(km_formatter))
        self.child_view_canvas.draw()
        
    def update_parent_orbit_view(self):
        """显示当前天体、其母天体、以及所有与当前天体同级别的天体（兄弟）"""
        if not self.current_body:
            return
        
        fig = self.parent_view_figure
        fig.clear()
        ax = fig.add_subplot(111)
        
        # 如果当前天体是中心天体，显示提示信息
        if self.current_body.type == "Center":
            ax.text(0.5, 0.5, "当前天体是系统中心，无父级天体\n请切换到子天体视图", 
                    ha='center', va='center', transform=ax.transAxes, fontsize=12)
            ax.set_xlim(-1, 1)
            ax.set_ylim(-1, 1)
            ax.axis('off')
            self.parent_view_canvas.draw()
            return
        
        ax.set_aspect('equal')
        ax.grid(True, linestyle='--', alpha=0.5)
        ax.set_navigate(False)

        center_body = self.current_body

        # 获取母天体
        parent_body = None
        if center_body.type != "Center" and center_body.parent:
            parent_body = self.current_project.get_body(center_body.parent)
        
        # 如果没有母天体（理论上不应发生，因为已排除Center），显示提示
        if parent_body is None:
            ax.text(0.5, 0.5, f"天体 {center_body.name} 没有母天体", 
                    ha='center', va='center', transform=ax.transAxes, fontsize=12)
            ax.set_xlim(-1, 1)
            ax.set_ylim(-1, 1)
            ax.axis('off')
            self.parent_view_canvas.draw()
            return

        # 获取所有兄弟天体（包括自己）
        siblings = [b for b in self.current_project.bodies if b.parent == parent_body.name]
        # 计算显示范围
        center_soi = compute_soi_radius(center_body, parent_body)
        parent_soi = compute_soi_radius(parent_body, self.current_project.get_body(parent_body.parent) if parent_body.parent else None)
        max_orbit = max([b.data.get("ORBIT_DATA", {}).get("semiMajorAxis", 0.0) for b in siblings])
        # 默认视图基于兄弟天体的最大轨道距离，而不是SOI
        if max_orbit > 0:
            view_max = max_orbit * 1.2
        else:
            # 没有兄弟天体时，使用母天体半径的100倍作为视图范围
            parent_radius = parent_body.data.get("BASE_DATA", {}).get("radius", 0.0)
            view_max = parent_radius * 100
        view_min = center_soi * 0.5

        # 绘制母天体（位于原点）
        parent_radius = parent_body.data.get("BASE_DATA", {}).get("radius", 0.0)
        parent_display_radius = parent_radius
        # 母天体半径圆 - 填充颜色 + 黑色描边
        parent_circle = Circle((0, 0), parent_display_radius, facecolor=body_color(parent_body), edgecolor='gray', alpha=0.5, linewidth=0.5)
        ax.add_patch(parent_circle)
        # 绘制母天体的光环（如果存在）
        parent_rings = parent_body.data.get("RINGS_DATA", {})
        if parent_rings:
            start_radius = parent_rings.get("startRadius", 0)
            end_radius = parent_rings.get("endRadius", 0)
            if start_radius > 0 and end_radius > start_radius:
                self._add_ring_patch(ax, 0, 0, start_radius, end_radius, body_color(parent_body), alpha=0.3)

        # 母天体标签 - 添加黑色描边
        parent_label = f"{parent_body.name}\nR: {UnitConverter.from_game_unit(parent_radius, 'km'):.0f} km"
        parent_label_offset = parent_display_radius * 1.2
        text = ax.text(0, parent_label_offset, parent_label, ha='center', va='bottom',
                fontsize=9, color=body_color(parent_body))
        text.set_path_effects([path_effects.withStroke(linewidth=0.5, foreground='gray', alpha=0.7)])

        # 收集兄弟天体数据（包括当前天体）
        sibling_data = []
        for sibling in siblings:
            orbit_data = sibling.data.get("ORBIT_DATA", {})
            a = orbit_data.get("semiMajorAxis", 0.0)
            if a == 0:
                continue
            e = orbit_data.get("eccentricity", 0.0)
            omega = orbit_data.get("argumentOfPeriapsis", 0.0)
            r0 = a * (1 - e**2) / (1 + e)
            x0 = r0 * np.cos(np.radians(omega))
            y0 = r0 * np.sin(np.radians(omega))
            
            # 判断是否为当前编辑的天体，若是则使用界面下拉框的方向值
            if sibling == center_body:
                direction = self.direction.currentData()
            else:
                direction = sibling.data.get("ORBIT_DATA", {}).get("direction", 1)
            
            sibling_data.append({
                'body': sibling,
                'a': a, 'e': e, 'omega': omega,
                'x0': x0, 'y0': y0,
                'radius': sibling.data.get("BASE_DATA", {}).get("radius", 0.0),
                'soi': compute_soi_radius(sibling, parent_body) if parent_body else 0.0,
                'direction': direction
            })
        # 绘制兄弟天体的轨道、圆、SOI
        for d in sibling_data:
            color = body_color(d['body'])
            # 轨道线 - 先绘制黑色背景线（增加对比度），再绘制颜色线（仅当方向非0时绘制）
            if d['direction'] != 0:
                x, y = orbit_points(d['a'], d['e'], d['omega'], num=200)
                ax.plot(x, y, color='gray', linewidth=1.2, alpha=0.6, zorder=1)
                ax.plot(x, y, color=color, linewidth=1.5, label=d['body'].name, zorder=2)
            # 天体位置点
            ax.plot(d['x0'], d['y0'], 'o', color=color, markersize=2.5)
            # 半径圆 - 填充颜色 + 黑色描边
            if d['radius'] > 0:
                sibling_circle = Circle((d['x0'], d['y0']), d['radius'], facecolor=color, edgecolor='gray', alpha=0.5, linewidth=0.5)
                ax.add_patch(sibling_circle)
            # 绘制兄弟天体的光环（如果存在）
            sibling_rings = d['body'].data.get("RINGS_DATA", {})
            if sibling_rings:
                start_radius = sibling_rings.get("startRadius", 0)
                end_radius = sibling_rings.get("endRadius", 0)
                if start_radius > 0 and end_radius > start_radius:
                    self._add_ring_patch(ax, d['x0'], d['y0'], start_radius, end_radius, color, alpha=0.3)

            # SOI 虚线圆
            if d['soi'] > 0 and d['soi'] <= view_max * 0.9:
                soi_circle = Circle((d['x0'], d['y0']), d['soi'], fill=False, linestyle='--', color=color, linewidth=0.8)
                ax.add_patch(soi_circle)
            # 标签 - 添加黑色描边
            label_text = f"{d['body'].name}\nR: {UnitConverter.from_game_unit(d['radius'], 'km'):.0f} km\nA: {UnitConverter.from_game_unit(d['a'], 'km'):.0f} km"
            text = ax.annotate(label_text, xy=(d['x0'], d['y0']), xytext=(5, 5), textcoords='offset points',
                        fontsize=8, color=color)
            text.set_path_effects([path_effects.withStroke(linewidth=0.5, foreground='gray', alpha=0.7)])
            pass

        # 绘制当前天体的 SOI 虚线圆（绘制在当前天体轨道位置上，而不是原点）
        if view_min <= center_soi <= view_max:
            # 获取当前天体的轨道位置（近地点）
            orbit_data = center_body.data.get("ORBIT_DATA", {})
            a = orbit_data.get("semiMajorAxis", 0.0)
            e = orbit_data.get("eccentricity", 0.0)
            omega = orbit_data.get("argumentOfPeriapsis", 0.0)
            if a > 0:
                r0 = a * (1 - e**2) / (1 + e)
                x0 = r0 * np.cos(np.radians(omega))
                y0 = r0 * np.sin(np.radians(omega))
                center_soi_circle = Circle((x0, y0), center_soi, fill=False, linestyle='--', 
                                            color=body_color(center_body), linewidth=1, 
                                            label=f"{center_body.name} SOI")
                ax.add_patch(center_soi_circle)

        ax.set_xlim(-view_max, view_max)
        ax.set_ylim(-view_max, view_max)
        ax.set_title(f"父级视图")
        ax.set_xlabel("距离 (km)")
        ax.set_ylabel("距离 (km)")

        def km_formatter(x, pos):
            return f"{x/1000:.0f}" if abs(x) < 1e7 else f"{x/1e6:.1f}M"
        ax.xaxis.set_major_formatter(plt.FuncFormatter(km_formatter))
        ax.yaxis.set_major_formatter(plt.FuncFormatter(km_formatter))
        self.parent_view_canvas.draw()

    def _add_ring_patch(self, ax, center_x, center_y, r_inner, r_outer, color, alpha=0.3):
        """在指定位置添加环形 Patch"""
        if r_inner >= r_outer or r_inner <= 0:
            return
        # 生成环形多边形
        num_points = 100
        angles = np.linspace(0, 2 * np.pi, num_points)
        outer_x = center_x + r_outer * np.cos(angles)
        outer_y = center_y + r_outer * np.sin(angles)
        inner_x = center_x + r_inner * np.cos(angles[::-1])
        inner_y = center_y + r_inner * np.sin(angles[::-1])
        x = np.concatenate([outer_x, inner_x])
        y = np.concatenate([outer_y, inner_y])
        poly = np.column_stack([x, y])
        ring = Polygon(poly, facecolor=color, edgecolor='none', alpha=alpha)
        ax.add_patch(ring)

    def build_json(self):
        """收集当前界面的数据并构建行星JSON"""
        self.save_ui_to_body(self.current_body)
        return self.current_body.data

    def update_preview(self):
        try:
            data = self.build_json()
            self.preview_text.setPlainText(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception as e:
            self.preview_text.setPlainText(f"JSON生成错误: {e}")
    
    def export_planet(self):
        try:
            data = self.build_json()
            name = self.name_edit.text()
            # 弹出保存对话框
            file_path, _ = QFileDialog.getSaveFileName(self, "保存行星文件", f"{name}.txt", "文本文件 (*.txt)")
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                QMessageBox.information(self, "成功", f"文件已保存到 {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {e}")

    def select_texture(self, line_edit):
        """打开纹理选择对话框，并将选中的纹理名称设置到指定的 QLineEdit"""
        dialog = TextureManagerDialog(self.current_project.texture_sources, self, select_mode=True)
        if dialog.exec() == QDialog.Accepted and dialog.selected_texture:
            line_edit.setText(dialog.selected_texture)

    def format_flat_zones(self):
        try:
            data = json.loads(self.flat_zones.toPlainText())
            self.flat_zones.setPlainText(json.dumps(data, indent=2))
        except Exception as e:
            QMessageBox.warning(self, "JSON 格式错误", f"解析失败：{e}")

    def format_pp_keys(self):
        try:
            data = json.loads(self.pp_keys.toPlainText())
            self.pp_keys.setPlainText(json.dumps(data, indent=2))
        except Exception as e:
            QMessageBox.warning(self, "JSON 格式错误", f"解析失败：{e}")

    def format_landmarks(self):
        try:
            data = json.loads(self.landmarks_json.toPlainText())
            self.landmarks_json.setPlainText(json.dumps(data, indent=2))
        except Exception as e:
            QMessageBox.warning(self, "JSON 格式错误", f"解析失败：{e}")

if __name__ == "__main__":
    from models import ensure_templates_dir
    ensure_templates_dir()
    app = QApplication(sys.argv)
    # 设置应用程序图标（影响任务栏和窗口）
    icon_path = resource_path("icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())