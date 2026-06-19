# terrain_formula_editor.py
import sys
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QScrollArea,
    QPushButton, QComboBox, QDoubleSpinBox, QCheckBox, QLineEdit,
    QGroupBox, QLabel, QMessageBox, QApplication
)
from PySide6.QtCore import Qt, Signal

# 预设变量名列表（用户可编辑）
DEFAULT_VARIABLES = ["OUTPUT", "PLAINS", "M", "M2", "TEMP"]


class FormulaEntry(QWidget):
    """单个地形公式条目"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self._on_function_type_changed()   # 初始化控件可见性

    def init_ui(self):
        # 使用 QGridLayout 将控件分布到多行，避免水平滚动条
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 5)
        layout.setHorizontalSpacing(5)

        # 第一行：变量、等号、函数类型、函数名（AddHeightMap专用）、Add高度（Add专用）
        # 变量名
        self.variable_combo = QComboBox()
        self.variable_combo.setEditable(True)
        self.variable_combo.addItems(DEFAULT_VARIABLES)
        self.variable_combo.setMinimumWidth(80)
        layout.addWidget(self.variable_combo, 0, 0)

        layout.addWidget(QLabel(" = "), 0, 1)

        self.func_type = QComboBox()
        self.func_type.addItems(["AddHeightMap", "Add"])
        self.func_type.currentTextChanged.connect(self._on_function_type_changed)
        layout.addWidget(self.func_type, 0, 2)

        # AddHeightMap 专用控件（函数名下拉框）
        self.func_name_combo = QComboBox()
        self.func_name_combo.setEditable(True)
        self.func_name_combo.setMinimumWidth(120)
        layout.addWidget(self.func_name_combo, 0, 3)

        # Add 专用控件（高度输入框） - 与函数名位置重叠，通过可见性切换
        self.add_height_spin = QDoubleSpinBox()
        self.add_height_spin.setRange(-1e30, 1e30)
        self.add_height_spin.setDecimals(6)
        self.add_height_spin.setValue(30.0)
        layout.addWidget(self.add_height_spin, 0, 3)
        self.add_height_spin.setVisible(False)

        # 第二行：长度（标签+输入框）、高度（标签+输入框）、额外参数、按钮
        layout.addWidget(QLabel("长度:"), 1, 0)
        self.length_spin = QDoubleSpinBox()
        self.length_spin.setRange(0, 1e30)
        self.length_spin.setDecimals(6)
        self.length_spin.setValue(1000.0)
        layout.addWidget(self.length_spin, 1, 1)

        layout.addWidget(QLabel("高度:"), 1, 2)
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(-1e30, 1e30)
        self.height_spin.setDecimals(6)
        self.height_spin.setValue(10.0)
        layout.addWidget(self.height_spin, 1, 3)

        self.extra_enable = QCheckBox("额外参数")
        self.extra_enable.toggled.connect(self._on_extra_toggled)
        layout.addWidget(self.extra_enable, 1, 4)

        self.extra_text = QLineEdit()
        self.extra_text.setPlaceholderText("例如: Curve1, PLAINS")
        self.extra_text.setEnabled(False)
        self.extra_text.setMinimumWidth(150)
        layout.addWidget(self.extra_text, 1, 5)

        # 按钮组（放在第二行右侧）
        btn_widget = QWidget()
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(2)
        self.btn_up = QPushButton("↑")
        self.btn_up.setFixedWidth(30)
        self.btn_down = QPushButton("↓")
        self.btn_down.setFixedWidth(30)
        self.btn_delete = QPushButton("✕")
        self.btn_delete.setFixedWidth(30)
        btn_layout.addWidget(self.btn_up)
        btn_layout.addWidget(self.btn_down)
        btn_layout.addWidget(self.btn_delete)
        layout.addWidget(btn_widget, 1, 6)

        # 设置列拉伸比例，使额外参数输入框可伸缩
        layout.setColumnStretch(5, 1)
        # 其他列不拉伸

    def _on_function_type_changed(self):
        is_addheightmap = self.func_type.currentText() == "AddHeightMap"
        # AddHeightMap 专用控件
        self.func_name_combo.setVisible(is_addheightmap)
        self.length_spin.setVisible(is_addheightmap)
        self.height_spin.setVisible(is_addheightmap)   # 新增：隐藏 Add 类型的高度输入框
        self.extra_enable.setVisible(is_addheightmap)
        self.extra_text.setVisible(is_addheightmap)
        # Add 专用控件
        self.add_height_spin.setVisible(not is_addheightmap)
        # 额外参数复选框回调
        if is_addheightmap:
            self._on_extra_toggled(self.extra_enable.isChecked())

    def _on_extra_toggled(self, checked):
        self.extra_text.setEnabled(checked)

    def get_entry_data(self):
        """返回条目的数据字典"""
        func_type = self.func_type.currentText()
        variable = self.variable_combo.currentText().strip()
        if not variable:
            variable = "OUTPUT"
        data = {
            "variable": variable,
            "type": func_type,
        }
        if func_type == "AddHeightMap":
            # 清理函数名：去除首尾空格、前导左括号、尾随右括号
            func_name = self.func_name_combo.currentText().strip()
            func_name = func_name.lstrip('(').rstrip(')').strip()
            data["func_name"] = func_name
            data["length"] = self.length_spin.value()
            data["height"] = self.height_spin.value()
            if self.extra_enable.isChecked() and self.extra_text.text().strip():
                data["extra"] = self.extra_text.text().strip()
            else:
                data["extra"] = ""
        else:
            data["height"] = self.add_height_spin.value()
        return data

    def set_entry_data(self, data):
        """根据数据字典设置控件值"""
        self.variable_combo.setCurrentText(data.get("variable", "OUTPUT"))
        func_type = data.get("type", "AddHeightMap")
        idx = self.func_type.findText(func_type)
        if idx >= 0:
            self.func_type.setCurrentIndex(idx)
        if func_type == "AddHeightMap":
            self.func_name_combo.setCurrentText(data.get("func_name", "Perlin"))
            self.length_spin.setValue(data.get("length", 1000.0))
            self.height_spin.setValue(data.get("height", 10.0))
            extra = data.get("extra", "")
            if extra:
                self.extra_enable.setChecked(True)
                self.extra_text.setText(extra)
            else:
                self.extra_enable.setChecked(False)
                self.extra_text.clear()
        else:
            self.add_height_spin.setValue(data.get("height", 30.0))


class TerrainFormulaEditor(QWidget):
    """地形公式编辑器，包含增删、上下移动条目"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries = []   # 保存 FormulaEntry 控件列表
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # 可滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self.scroll_content)
        self.main_layout.addWidget(scroll)

        # 底部按钮
        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("+ 添加新公式")
        self.btn_add.clicked.connect(self.add_empty_entry)
        btn_layout.addWidget(self.btn_add)
        btn_layout.addStretch()
        self.main_layout.addLayout(btn_layout)

        # 连接内置地形函数列表的信号（稍后由外部设置）
        self.heightmap_names = []   # 将从 constants 中加载

    def set_heightmap_names(self, names):
        """设置内置地形函数名称列表，用于下拉框自动补全"""
        self.heightmap_names = names
        # 更新现有条目
        for entry in self.entries:
            entry.func_name_combo.clear()
            entry.func_name_combo.addItems(names)
            entry.func_name_combo.setEditable(True)

    def add_empty_entry(self):
        entry = FormulaEntry()
        # 设置地形函数下拉列表
        entry.func_name_combo.clear()
        entry.func_name_combo.addItems(self.heightmap_names)
        entry.func_name_combo.setEditable(True)
        # 连接移动和删除信号
        entry.btn_up.clicked.connect(lambda: self.move_entry_up(entry))
        entry.btn_down.clicked.connect(lambda: self.move_entry_down(entry))
        entry.btn_delete.clicked.connect(lambda: self.delete_entry(entry))
        self.entries.append(entry)
        self.scroll_layout.addWidget(entry)
        # 自动滚动到底部
        self.scroll_content.adjustSize()

    def move_entry_up(self, entry):
        idx = self.entries.index(entry)
        if idx > 0:
            self.entries[idx], self.entries[idx-1] = self.entries[idx-1], self.entries[idx]
            # 重新排列布局中的控件顺序
            self._reorder_layout()

    def move_entry_down(self, entry):
        idx = self.entries.index(entry)
        if idx < len(self.entries) - 1:
            self.entries[idx], self.entries[idx+1] = self.entries[idx+1], self.entries[idx]
            self._reorder_layout()

    def delete_entry(self, entry):
        if len(self.entries) == 1:
            # 至少保留一个条目
            QMessageBox.information(self, "提示", "至少需要一个地形公式。")
            return
        idx = self.entries.index(entry)
        self.entries.pop(idx)
        entry.deleteLater()
        self._reorder_layout()

    def _reorder_layout(self):
        """根据 self.entries 顺序重新调整布局中的控件顺序"""
        for i in reversed(range(self.scroll_layout.count())):
            item = self.scroll_layout.itemAt(i)
            if item.widget():
                item.widget().setParent(None)
        for entry in self.entries:
            self.scroll_layout.addWidget(entry)

    def get_formulas(self):
        """返回字符串列表，符合 SFS 地形公式格式"""
        lines = []
        for entry in self.entries:
            data = entry.get_entry_data()
            variable = data["variable"]
            if data["type"] == "AddHeightMap":
                base = f"{variable} = AddHeightMap({data['func_name']}, {data['length']}, {data['height']}"
                if data.get("extra"):
                    base += f", {data['extra']}"
                base += ")"
                lines.append(base)
            else:
                lines.append(f"{variable} = Add({data['height']})")
        return lines

    def set_formulas(self, formula_lines):
        """从字符串列表加载公式"""
        # 清空现有条目（同步移除）
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.entries.clear()
        # 强制更新布局
        self.scroll_layout.update()
        self.scroll_content.adjustSize()

        if not formula_lines:
            return

        for line in formula_lines:
            if "=" not in line:
                continue
            left, right = line.split("=", 1)
            variable = left.strip()
            right = right.strip()
            
            # 使用正则匹配 AddHeightMap(...)
            import re
            m = re.match(r'AddHeightMap\((.*)\)$', right)
            if m:
                inner = m.group(1)
                # 按逗号分割，但注意参数中可能包含括号或逗号，简单分割足够
                parts = [p.strip() for p in inner.split(',')]
                if len(parts) >= 3:
                    func_name = parts[0]
                    # 清理函数名：去除首尾空格和首尾括号（可能有多余）
                    func_name = func_name.lstrip('(').rstrip(')').strip()
                    try:
                        length = float(parts[1])
                        height = float(parts[2])
                    except:
                        length = 1000.0
                        height = 10.0
                    extra_parts = parts[3:] if len(parts) > 3 else []
                    extra = ", ".join(extra_parts) if extra_parts else ""
                    
                    entry = FormulaEntry()
                    entry.variable_combo.setCurrentText(variable)
                    entry.func_type.setCurrentText("AddHeightMap")
                    entry.func_name_combo.setCurrentText(func_name)
                    entry.length_spin.setValue(length)
                    entry.height_spin.setValue(height)
                    if extra:
                        entry.extra_enable.setChecked(True)
                        entry.extra_text.setText(extra)
                    else:
                        entry.extra_enable.setChecked(False)
                    self.entries.append(entry)
                    self.scroll_layout.addWidget(entry)
            elif right.startswith("Add(") and right.endswith(")"):
                inner = right[4:-1]
                try:
                    height = float(inner)
                except:
                    height = 30.0
                entry = FormulaEntry()
                entry.variable_combo.setCurrentText(variable)
                entry.func_type.setCurrentText("Add")
                entry.add_height_spin.setValue(height)
                self.entries.append(entry)
                self.scroll_layout.addWidget(entry)
            # 忽略其他无法解析的行

        # 连接所有新条目的信号
        for entry in self.entries:
            entry.btn_up.clicked.connect(lambda e=entry: self.move_entry_up(e))
            entry.btn_down.clicked.connect(lambda e=entry: self.move_entry_down(e))
            entry.btn_delete.clicked.connect(lambda e=entry: self.delete_entry(e))

        # 如果没有成功解析任何条目，添加一个默认
        if not self.entries:
            self.add_empty_entry()