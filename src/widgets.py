from PySide6.QtWidgets import QWidget, QHBoxLayout, QDoubleSpinBox, QComboBox, QPushButton, QColorDialog
from PySide6.QtCore import Signal
from PySide6.QtGui import QColor

class UnitConverter:
    """单位换算器 - 支持km/m/AU/unit之间的转换"""
    
    # 现实定义
    KM_TO_M = 1000                    # 1 km = 1000 m
    REAL_AU_TO_KM = 1.496e8           # 1 AU = 1.496亿 km
    REAL_AU_TO_M = REAL_AU_TO_KM * KM_TO_M  # 1 AU = 1.496e11 m
    
    # SFS游戏定义：20 m = 1 unit
    # 注意：游戏内存储的半径、半长轴等都是以"米"为单位的！
    # 1 unit = 20 米，所以 1 米 = 0.05 unit
    M_TO_UNIT = 1.0 / 20.0            # 1 m = 0.05 unit
    UNIT_TO_M = 20.0                  # 1 unit = 20 m
    
    @classmethod
    def to_game_unit(cls, value: float, from_unit: str) -> float:
        """将各种单位的输入转换为游戏内单位（unit）
        注意：游戏内实际存储的是米，但最终显示为unit时需要除以20？
        实际上游戏JSON中的radius字段存储的是米！不是unit！
        验证：地球半径 6371 km = 6,371,000 m，模板中地球radius=314970？
        等等，314970 * 20 = 6,299,400 m ≈ 6299 km，接近地球半径。
        所以：游戏JSON中的radius是米，但缩放因子是20？不，应该是：
        实际米 = radius字段值 * 20？模板中314970 * 20 = 6,299,400 m = 6299 km，正确！
        结论：游戏JSON中的radius字段是【游戏单位unit】！因为乘以20才得到米。
        所以：1 unit = 20 米，半径字段存储的是unit。
        """
        # 先转换为米
        meters = cls._to_meters(value, from_unit)
        # 米转游戏单位（unit）：1米 = 0.05 unit
        return meters * cls.M_TO_UNIT
    
    @classmethod
    def _to_meters(cls, value: float, from_unit: str) -> float:
        """将各种单位的输入转换为米"""
        if from_unit == "m":
            return value
        elif from_unit == "km":
            return value * cls.KM_TO_M
        elif from_unit == "AU":
            return value * cls.REAL_AU_TO_M
        elif from_unit == "unit":
            # 如果输入是unit，转换为米：1 unit = 20 米
            return value * cls.UNIT_TO_M
        else:
            return value
    
    @classmethod
    def from_game_unit(cls, value: float, to_unit: str) -> float:
        """将游戏内单位（unit）转换为各种显示单位
        注意：游戏JSON中的radius字段是unit，需要先转换为米再转换到目标单位
        """
        # 游戏单位（unit）转换为米：1 unit = 20 米
        meters = value * cls.UNIT_TO_M
        if to_unit == "m":
            return meters
        elif to_unit == "km":
            return meters / cls.KM_TO_M
        elif to_unit == "AU":
            return meters / cls.REAL_AU_TO_M
        elif to_unit == "unit":
            return value
        else:
            return value

class UnitSpinBox(QWidget):
    """带单位选择器的数值输入控件（支持单位切换自动换算）"""
    unit_changed = Signal()
    
    def __init__(self, initial_value: float = 0.0, initial_unit: str = "km",
                 min_val: float = 0.0, max_val: float = 1e50, decimals: int = 12):
        super().__init__()
        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)
        
        self.spinbox = QDoubleSpinBox()
        self.spinbox.setRange(min_val, max_val)
        self.spinbox.setDecimals(decimals)
        self.spinbox.setValue(initial_value)
        
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["km", "m", "AU", "unit"])
        self.unit_combo.setCurrentText(initial_unit)
        
        self.layout.addWidget(self.spinbox, 1)
        self.layout.addWidget(self.unit_combo)
        
        # 记录当前单位（用于切换时换算）
        self._current_unit = initial_unit
        
        # 信号连接
        self.spinbox.valueChanged.connect(self._on_value_changed)
        self.unit_combo.currentTextChanged.connect(self._on_unit_changed)
    
    def _on_value_changed(self):
        self.unit_changed.emit()
    
    def _on_unit_changed(self, new_unit):
        old_unit = self._current_unit
        if old_unit == new_unit:
            return
        
        old_value = self.spinbox.value()
        meters = UnitConverter._to_meters(old_value, old_unit)
        # 新单位下的数值 = 米数 / 新单位对应的米数
        new_value = meters / UnitConverter._to_meters(1.0, new_unit)
        
        self.spinbox.blockSignals(True)
        self.spinbox.setValue(new_value)
        self.spinbox.blockSignals(False)
        
        # 动态调整小数位数
        if new_unit == "AU":
            self.spinbox.setDecimals(12)
        elif new_unit == "unit":
            self.spinbox.setDecimals(6)
        else:
            self.spinbox.setDecimals(3)
        
        self._current_unit = new_unit
        self.unit_changed.emit()
    
    def get_value_in_unit(self, target_unit: str) -> float:
        """获取指定单位下的数值"""
        raw_value = self.spinbox.value()
        current_unit = self._current_unit
        meters = UnitConverter._to_meters(raw_value, current_unit)
        if target_unit == "m":
            return meters
        elif target_unit == "km":
            return meters / UnitConverter.KM_TO_M
        elif target_unit == "AU":
            return meters / UnitConverter.REAL_AU_TO_M
        elif target_unit == "unit":
            return meters * UnitConverter.M_TO_UNIT
        return raw_value
    
    def get_game_value(self) -> float:
        """直接获取游戏内单位值（unit）"""
        raw_value = self.spinbox.value()
        current_unit = self._current_unit
        # 先将当前显示值转换为米，再转换为游戏单位
        meters = UnitConverter._to_meters(raw_value, current_unit)
        return meters * UnitConverter.M_TO_UNIT
    
    def set_value_in_game_unit(self, game_value: float, display_unit: str = None):
        """根据游戏单位值设置显示值和单位"""
        if display_unit is None:
            display_unit = self._current_unit
        # 游戏单位 -> 米 -> 显示单位
        meters = game_value * UnitConverter.UNIT_TO_M
        display_value = meters / UnitConverter._to_meters(1.0, display_unit)
        self.spinbox.blockSignals(True)
        self.spinbox.setValue(display_value)
        self.spinbox.blockSignals(False)
        if display_unit != self._current_unit:
            self.unit_combo.setCurrentText(display_unit)
            self._current_unit = display_unit
    
    def set_game_value(self, game_value: float):
        """直接设置游戏单位值，使用当前显示单位"""
        current_unit = self._current_unit
        # 游戏单位 -> 米 -> 显示单位
        meters = game_value * UnitConverter.UNIT_TO_M
        display_value = meters / UnitConverter._to_meters(1.0, current_unit)
        self.spinbox.blockSignals(True)
        self.spinbox.setValue(display_value)
        self.spinbox.blockSignals(False)
    
    def value(self) -> float:
        """返回当前显示值（不推荐使用）"""
        return self.spinbox.value()
    
    def unit(self) -> str:
        return self._current_unit

class ColorPickerButton(QPushButton):
    """带颜色预览的颜色选择按钮"""
    color_changed = Signal()
    
    def __init__(self, initial_color: tuple = (0.45, 0.68, 1.0, 1.0)):
        super().__init__()
        self._color = initial_color
        self.setFixedSize(50, 25)
        self.clicked.connect(self._pick_color)
        self._update_style()
    
    def _pick_color(self):
        # 将0-1范围转换为0-255范围
        initial_rgba = (
            max(0, min(255, int(self._color[0] * 255))),
            max(0, min(255, int(self._color[1] * 255))),
            max(0, min(255, int(self._color[2] * 255))),
            max(0, min(255, int(self._color[3] * 255)))
        )
        color = QColorDialog.getColor(
            QColor(initial_rgba[0], initial_rgba[1], initial_rgba[2], initial_rgba[3]),
            self,
            "选择颜色",
            QColorDialog.ShowAlphaChannel
        )
        if color.isValid():
            self._color = (
                color.red() / 255.0,
                color.green() / 255.0,
                color.blue() / 255.0,
                color.alpha() / 255.0
            )
            self._update_style()
            self.color_changed.emit()
    
    def _update_style(self):
        r, g, b, a = self._color
        r_val = max(0, min(255, int(r * 255)))
        g_val = max(0, min(255, int(g * 255)))
        b_val = max(0, min(255, int(b * 255)))
        rgba_str = f"rgba({r_val}, {g_val}, {b_val}, {a})"
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {rgba_str};
                border: 1px solid #888;
                border-radius: 3px;
            }}
        """)
    
    def get_color(self) -> tuple:
        return self._color
    
    def set_color(self, color: tuple):
        self._color = color
        self._update_style()
        self.color_changed.emit()