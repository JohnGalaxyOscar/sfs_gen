# utils.py
import numpy as np
from widgets import UnitConverter  # 可能需要导入

def clean_float(value):
    """递归清理数据中的浮点数，将整数值转为 int"""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    elif isinstance(value, dict):
        return {k: clean_float(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [clean_float(v) for v in value]
    else:
        return value

def get_mass_factor(body):
    """返回质量因子 (g * R^2)，用于质量比计算。"""
    base = body.data.get("BASE_DATA", {})
    g = base.get("gravity", 0.0)
    r = base.get("radius", 0.0)
    return g * (r * r) if r > 0 else 0.0

def compute_soi_radius(body, parent, project=None):  # project 可选
    """计算 body 相对于 parent 的 SOI 半径（米）。公式: a * (m_body / m_parent) ** 0.4"""
    orbit = body.data.get("ORBIT_DATA", {})
    a = orbit.get("semiMajorAxis", 0.0)
    if a == 0:
        return 0.0
    m_body = get_mass_factor(body)
    m_parent = get_mass_factor(parent)
    if m_parent == 0:
        return a * 1.0
    ratio = m_body / m_parent
    soi = a * (ratio ** 0.4)
    multiplier = orbit.get("multiplierSOI", 2.5)
    return soi * multiplier

def orbit_points(a, e, omega_deg, num=360):
    """返回椭圆轨道的 x, y 坐标数组（米），中心在原点，omega 为近地点辐角（度）"""
    theta = np.linspace(0, 2 * np.pi, num)
    r = a * (1 - e**2) / (1 + e * np.cos(theta))
    x = r * np.cos(theta)
    y = r * np.sin(theta)
    if omega_deg != 0:
        omega_rad = np.radians(omega_deg)
        c, s = np.cos(omega_rad), np.sin(omega_rad)
        x_rot = x * c - y * s
        y_rot = x * s + y * c
        return x_rot, y_rot
    return x, y

def body_color(body):
    base = body.data.get("BASE_DATA", {})
    mc = base.get("mapColor", {"r": 0.5, "g": 0.5, "b": 0.5, "a": 1.0})
    r = max(0.0, min(1.0, mc.get("r", 0.5)))
    g = max(0.0, min(1.0, mc.get("g", 0.5)))
    b = max(0.0, min(1.0, mc.get("b", 0.5)))
    a = max(0.0, min(1.0, mc.get("a", 1.0)))
    return (r, g, b, a)