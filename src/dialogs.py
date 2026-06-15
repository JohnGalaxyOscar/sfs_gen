from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QSplitter, QWidget,
    QHBoxLayout, QLineEdit, QTableWidget, QTableWidgetItem, QPushButton,
    QTreeWidget, QTreeWidgetItem, QDialogButtonBox, QFileDialog, QInputDialog,
    QMessageBox, QApplication, QFormLayout, QComboBox)
from PySide6.QtCore import Qt
from constants import BUILTIN_TEXTURES
import os

from models import load_templates, import_template_from_file

class TextureManagerDialog(QDialog):
    def __init__(self, texture_sources, parent=None, select_mode=False):
        super().__init__(parent)
        self.setWindowTitle("纹理管理")
        self.setMinimumSize(800, 500)
        self.texture_sources = texture_sources
        self.select_mode = select_mode
        self.selected_texture = None
        self.init_ui()
        self.load_data()
        self.load_builtin_tree()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        info_label = QLabel("自定义贴图：需要指定外部文件，导出时自动复制。内置贴图：双击复制名称，无需文件。")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)
        
        # ========== 左侧：自定义贴图 ==========
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        left_label = QLabel("自定义贴图（外部文件）")
        left_layout.addWidget(left_label)
        
        # 搜索框
        self.search_custom = QLineEdit()
        self.search_custom.setPlaceholderText("搜索自定义贴图...")
        self.search_custom.textChanged.connect(self.filter_custom_table)
        left_layout.addWidget(self.search_custom)
        
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["纹理名称", "源文件路径"])
        self.table.horizontalHeader().setStretchLastSection(True)
        left_layout.addWidget(self.table)
        
        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("添加")
        self.btn_add.clicked.connect(self.add_mapping)
        self.btn_delete = QPushButton("删除")
        self.btn_delete.clicked.connect(self.delete_mapping)
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addStretch()
        left_layout.addLayout(btn_layout)
        
        if self.select_mode:
            self.btn_select_custom = QPushButton("选择选中的自定义贴图")
            self.btn_select_custom.clicked.connect(self.select_custom)
            left_layout.addWidget(self.btn_select_custom)
        
        splitter.addWidget(left_widget)
        
        # ========== 右侧：内置贴图 ==========
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        right_label = QLabel("游戏内置贴图")
        right_layout.addWidget(right_label)
        
        # 搜索框
        self.search_builtin = QLineEdit()
        self.search_builtin.setPlaceholderText("搜索内置贴图...")
        self.search_builtin.textChanged.connect(self.filter_builtin_tree)
        right_layout.addWidget(self.search_builtin)
        
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("内置贴图")
        self.tree.setIndentation(10)
        self.tree.itemDoubleClicked.connect(self.copy_builtin_name if not self.select_mode else self.select_builtin)
        right_layout.addWidget(self.tree)
        
        if self.select_mode:
            self.btn_select_builtin = QPushButton("选择选中的内置贴图")
            self.btn_select_builtin.clicked.connect(self.select_builtin_current)
            right_layout.addWidget(self.btn_select_builtin)
        
        hint_label = QLabel("提示：双击任意贴图名称即可复制，然后粘贴到行星参数的纹理输入框中。" if not self.select_mode else "双击或点击按钮选择纹理。")
        hint_label.setWordWrap(True)
        hint_label.setStyleSheet("color: gray; font-size: 10pt;")
        right_layout.addWidget(hint_label)
        
        splitter.addWidget(right_widget)
        splitter.setSizes([350, 350])
        
        if not self.select_mode:
            button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            button_box.accepted.connect(self.accept)
            button_box.rejected.connect(self.reject)
            layout.addWidget(button_box)
        else:
            cancel_btn = QPushButton("取消")
            cancel_btn.clicked.connect(self.reject)
            layout.addWidget(cancel_btn)
    
    def load_builtin_tree(self):
        self.tree.clear()
        self.all_builtin_items = []  # 存储所有叶子节点，用于搜索
        for category, textures in BUILTIN_TEXTURES.items():
            cat_item = QTreeWidgetItem([category])
            cat_item.setFlags(cat_item.flags() & ~Qt.ItemIsSelectable)
            self.tree.addTopLevelItem(cat_item)
            for tex in textures:
                item = QTreeWidgetItem([tex])
                item.setData(0, Qt.UserRole, tex)
                cat_item.addChild(item)
                self.all_builtin_items.append(item)
        self.tree.expandAll()
    
    def filter_builtin_tree(self):
        keyword = self.search_builtin.text().strip().lower()
        for item in self.all_builtin_items:
            parent = item.parent()
            if keyword == "":
                item.setHidden(False)
                if parent:
                    parent.setHidden(False)
            else:
                match = keyword in item.text(0).lower()
                item.setHidden(not match)
                if parent:
                    # 如果父节点下有任何可见子节点，父节点就显示
                    has_visible = any(not child.isHidden() for child in parent.childItems())
                    parent.setHidden(not has_visible)
        # 处理根节点：如果某个根节点下没有可见子节点，则隐藏根节点
        for i in range(self.tree.topLevelItemCount()):
            cat_item = self.tree.topLevelItem(i)
            has_visible = any(not child.isHidden() for child in cat_item.childItems())
            cat_item.setHidden(not has_visible)
    
    def filter_custom_table(self):
        keyword = self.search_custom.text().strip().lower()
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            hide = keyword not in name_item.text().lower()
            self.table.setRowHidden(row, hide)
    
    def load_data(self):
        self.table.setRowCount(len(self.texture_sources))
        for row, (name, path) in enumerate(self.texture_sources.items()):
            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem(path))
        self.filter_custom_table()  # 应用当前搜索过滤
    
    def add_mapping(self):
        name, ok = QInputDialog.getText(self, "添加纹理", "纹理名称:")
        if not ok or not name:
            return
        if name in self.texture_sources:
            QMessageBox.warning(self, "警告", f"纹理 '{name}' 已存在，请修改或删除后再添加。")
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "选择纹理文件", "", "图片文件 (*.png *.jpg *.jpeg)")
        if not file_path:
            return
        self.texture_sources[name] = file_path
        self.load_data()
    
    def delete_mapping(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            return
        name = self.table.item(current_row, 0).text()
        del self.texture_sources[name]
        self.load_data()
    
    def select_custom(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先在左侧表格中选择一个自定义贴图。")
            return
        tex_name = self.table.item(current_row, 0).text()
        self.selected_texture = tex_name
        self.accept()
    
    def select_builtin(self, item, column):
        if item.childCount() == 0:
            self.selected_texture = item.text(0)
            self.accept()
    
    def select_builtin_current(self):
        current_item = self.tree.currentItem()
        if current_item and current_item.childCount() == 0:
            self.selected_texture = current_item.text(0)
            self.accept()
        else:
            QMessageBox.warning(self, "提示", "请先在右侧树形列表中选择一个内置贴图。")
    
    def copy_builtin_name(self, item, column):
        if item.childCount() == 0:
            tex_name = item.text(0)
            clipboard = QApplication.clipboard()
            clipboard.setText(tex_name)
            QMessageBox.information(self, "已复制", f"已复制 '{tex_name}' 到剪贴板，可粘贴到纹理输入框。")
    
    def accept(self):
        super().accept()

class AddBodyDialog(QDialog):
    def __init__(self, parent=None, parent_name=""):
        super().__init__(parent)
        self.setWindowTitle(f"添加子天体 - 父天体: {parent_name}" if parent_name else "添加天体")
        self.setMinimumWidth(400)
        self.parent_name = parent_name
        self.result_data = None
        self.init_ui()
        self.load_templates()

    def init_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()

        # 天体名称
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("输入天体名称")
        form.addRow("天体名称:", self.name_edit)

        # 模板选择
        self.template_combo = QComboBox()
        self.template_combo.setEditable(False)
        self.template_combo.currentTextChanged.connect(self.on_template_changed)
        form.addRow("模板:", self.template_combo)

        # 类型选择（仅当选择“空模板”时显示）
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Planet", "Moon", "Star"])
        self.type_combo.setVisible(False)
        form.addRow("天体类型:", self.type_combo)

        layout.addLayout(form)

        # 提示信息
        info_label = QLabel("提示：选择“空模板”后需手动选择天体类型。")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(info_label)

        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.on_accepted)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def load_templates(self):
        templates = load_templates()
        self.template_names = list(templates.keys())
        self.template_names.insert(0, "空模板")
        self.template_names.append("从文件导入...")
        self.template_combo.addItems(self.template_names)

    def on_template_changed(self, text):
        # 控制类型选择框的可见性
        self.type_combo.setVisible(text == "空模板")

    def on_accepted(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "警告", "天体名称不能为空。")
            return

        template = self.template_combo.currentText()
        body_type = None

        if template == "空模板":
            body_type = self.type_combo.currentText()
            if not body_type:
                QMessageBox.warning(self, "警告", "请选择天体类型。")
                return
        elif template == "从文件导入...":
            # 打开文件对话框
            from PySide6.QtWidgets import QFileDialog
            file_path, _ = QFileDialog.getOpenFileName(self, "导入行星模板", "", "JSON文件 (*.json)")
            if not file_path:
                return  # 用户取消，不关闭对话框
            try:
                template_name = import_template_from_file(file_path)
                # 导入后，模板会出现在 templates 文件夹中，下次可用
                # 但此处需要将 template_name 保存，但用户可能还要选择类型
                # 简单处理：让用户再选择类型
                from PySide6.QtWidgets import QInputDialog
                types = ["Planet", "Moon", "Star"]
                type_str, ok = QInputDialog.getItem(self, "选择类型", "该天体类型:", types, 0, False)
                if not ok:
                    return
                body_type = type_str
                template = template_name  # 使用导入的模板
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导入模板失败: {e}")
                return
        else:
            # 从已有模板创建，自动推断类型（可根据模板名包含关键词）
            if "恒星" in template or "Sun" in template:
                body_type = "Star"
            elif "Moon" in template:
                body_type = "Moon"
            else:
                body_type = "Planet"

        self.result_data = {
            "name": name,
            "template": template,
            "type": body_type
        }
        self.accept()

    def get_result(self):
        return self.result_data