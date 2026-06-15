import json
import copy
import os
import sys

def resource_path(relative_path):
    """获取资源的绝对路径，兼容开发环境和打包后的exe"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(__file__), relative_path)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = resource_path("templates")

from typing import List, Optional, Dict, Any

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

def ensure_templates_dir():
    """确保模板文件夹存在，如果不存在则创建空文件夹并提示用户"""
    if not os.path.exists(TEMPLATES_DIR):
        os.makedirs(TEMPLATES_DIR)
        print(f"警告: 模板文件夹 '{TEMPLATES_DIR}' 已创建，但未包含任何模板文件。")
        print("请手动将模板 JSON 文件放入该文件夹，或使用「从文件导入」功能添加模板。")

def load_templates() -> Dict[str, dict]:
    """从 templates 文件夹加载所有模板，返回 {模板名: 数据}"""
    ensure_templates_dir()
    templates = {}
    for file in os.listdir(TEMPLATES_DIR):
        if file.endswith(".json"):
            name = file[:-5]
            try:
                with open(os.path.join(TEMPLATES_DIR, file), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    templates[name] = data
            except Exception as e:
                print(f"加载模板 {file} 失败: {e}")
    return templates

def import_template_from_file(file_path: str) -> str:
    """导入外部 JSON 文件作为模板，返回模板名（即文件名不含扩展名）"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # 使用原文件名（不含扩展名）作为模板名
    base_name = os.path.basename(file_path)
    if base_name.endswith(".json"):
        template_name = base_name[:-5]
    else:
        template_name = base_name
    # 保存到 templates 文件夹
    dest_path = os.path.join(TEMPLATES_DIR, base_name)
    with open(dest_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return template_name

# ==================== 天体模型 ====================
class CelestialBody:
    def __init__(self, name: str = "NewBody", body_type: str = "Planet", template_name: str = None, data: dict = None):
        self.name = name
        self.type = body_type
        self.parent = None
        if data is not None:
            self.data = copy.deepcopy(data)
        else:
            templates = load_templates()
            if template_name and template_name in templates:
                self.data = copy.deepcopy(templates[template_name])
            else:
                self.data = self._get_default_data_for_type(body_type)

    def _get_default_data_for_type(self, body_type: str) -> Dict[str, Any]:
        if body_type == "Center":
            return {
                "version": "1.5",
                "BASE_DATA": {
                    "radius": 34817000.0,
                    "gravity": 247.0,
                    "timewarpHeight": 500000.0,
                    "velocityArrowsHeight": "NaN",
                    "mapColor": {"r": 2.0, "g": 2.0, "b": 2.0, "a": 1.0},
                    "significant": True,
                    "rotateCamera": True
                },
                # 没有 ORBIT_DATA
                "ACHIEVEMENT_DATA": {"Landed": False, "Takeoff": False, "Atmosphere": False, "Orbit": True, "Crash": False}
            }
        if body_type == "Star":
            return {
                "version": "1.5",
                "BASE_DATA": {
                    "radius": 34817000.0,
                    "gravity": 247.0,
                    "timewarpHeight": 500000.0,
                    "velocityArrowsHeight": "NaN",
                    "mapColor": {"r": 2.0, "g": 2.0, "b": 2.0, "a": 1.0},
                    "significant": True,
                    "rotateCamera": True
                },
                "ORBIT_DATA": {"parent": "", "semiMajorAxis": 0, "eccentricity": 0, "argumentOfPeriapsis": 0, "direction": 1, "multiplierSOI": 2.5},
                "ACHIEVEMENT_DATA": {"Landed": False, "Takeoff": False, "Atmosphere": False, "Orbit": True, "Crash": False}
            }
        else:
            return {
                "version": "1.5",
                "BASE_DATA": {
                    "radius": 314970.0,
                    "gravity": 9.8,
                    "timewarpHeight": 25000.0,
                    "velocityArrowsHeight": 5000.0,
                    "mapColor": {"r": 0.45, "g": 0.68, "b": 1.0, "a": 1.0},
                    "significant": True,
                    "rotateCamera": True
                },
                "ORBIT_DATA": {"parent": "", "semiMajorAxis": 0, "eccentricity": 0, "argumentOfPeriapsis": 0, "direction": 1, "multiplierSOI": 2.5},
                "ACHIEVEMENT_DATA": {"Landed": False, "Takeoff": True, "Atmosphere": True, "Orbit": True, "Crash": True}
            }

# ==================== 项目模型 ====================
class Project:
    def __init__(self):
        self.file_path: Optional[str] = None
        self.bodies: List[CelestialBody] = []
        self.texture_sources: Dict[str, str] = {}
        # 新增：导出包元数据
        self.export_pack_name: str = "MyPlanetPack"
        self.export_author: str = "n/a"
        self.export_version: str = "n/a"
        self.export_description: str = "n/a"
        # 预留：发射台数据（未来扩展）
        self.space_center_address: str = "Earth"
        self.space_center_angle: float = 90.0
        self.launchpad_horizontal: float = 365.0
        self.launchpad_height: float = 56.2
    
    def add_body(self, body: CelestialBody):
        self.bodies.append(body)
    
    def remove_body(self, name: str):
        self.bodies = [b for b in self.bodies if b.name != name]
    
    def get_body(self, name: str) -> Optional[CelestialBody]:
        for b in self.bodies:
            if b.name == name:
                return b
        return None
    
    def to_dict(self) -> dict:
        return {
            "version": "1.0",
            "bodies": [
                {
                    "name": b.name,
                    "type": b.type,
                    "parent": b.parent,
                    "data": b.data
                } for b in self.bodies
            ],
            "texture_sources": self.texture_sources,
            "export_metadata": {
                "pack_name": self.export_pack_name,
                "author": self.export_author,
                "version": self.export_version,
                "description": self.export_description,
                "space_center": {
                    "address": self.space_center_address,
                    "angle": self.space_center_angle,
                    "launchpad_horizontal": self.launchpad_horizontal,
                    "launchpad_height": self.launchpad_height
                }
            }
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        proj = cls()
        for body_data in data.get("bodies", []):
            body = CelestialBody(body_data["name"], body_data["type"])
            body.parent = body_data.get("parent")
            body.data = body_data["data"]
            proj.bodies.append(body)
        proj.texture_sources = data.get("texture_sources", {})
        # 读取导出元数据
        meta = data.get("export_metadata", {})
        proj.export_pack_name = meta.get("pack_name", "MyPlanetPack")
        proj.export_author = meta.get("author", "n/a")
        proj.export_version = meta.get("version", "n/a")
        proj.export_description = meta.get("description", "n/a")
        sc = meta.get("space_center", {})
        proj.space_center_address = sc.get("address", "Earth")
        proj.space_center_angle = sc.get("angle", 90.0)
        proj.launchpad_horizontal = sc.get("launchpad_horizontal", 365.0)
        proj.launchpad_height = sc.get("launchpad_height", 56.2)
        return proj
    
    @classmethod
    def import_from_pack(cls, pack_folder: str) -> "Project":
        """从SFS行星包文件夹导入项目"""
        import os
        import json
        
        proj = cls()
        
        # 1. 读取 Planet Data 文件夹
        planet_data_dir = os.path.join(pack_folder, "Planet Data")
        if not os.path.exists(planet_data_dir):
            raise FileNotFoundError(f"找不到 Planet Data 文件夹: {planet_data_dir}")
        
        bodies = []
        for filename in os.listdir(planet_data_dir):
            if filename.endswith(".txt"):
                filepath = os.path.join(planet_data_dir, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # 提取天体名称（文件名去掉.txt）
                name = filename[:-4]
                # 根据是否有 ORBIT_DATA 判断类型
                if "ORBIT_DATA" not in data:
                    body_type = "Center"
                else:
                    body_type = "Planet"  # 默认，后续可手动调整
                # 创建天体对象，直接使用数据
                body = CelestialBody(name, body_type)
                body.data = data
                body.parent = data.get("ORBIT_DATA", {}).get("parent") if "ORBIT_DATA" in data else None
                bodies.append(body)
        
        # 如果没有找到任何天体，则抛出异常
        if not bodies:
            raise ValueError("行星包中没有找到任何天体文件（.txt）")
        
        # 确保有且只有一个中心天体（type == "Center" 或没有轨道数据的天体）
        center_candidates = [b for b in bodies if b.type == "Center" or b.parent is None]
        if not center_candidates:
            # 如果没有中心天体，创建默认太阳
            sun = CelestialBody("Sun", "Center")
            sun.parent = None
            bodies.append(sun)
            center_body = sun
        else:
            # 取第一个候选作为中心天体，并将其余的 parent 为 None 的修正
            center_body = center_candidates[0]
            for body in bodies:
                if body.parent is None and body != center_body:
                    body.parent = center_body.name
        
        proj.bodies = bodies
        
        # 2. 读取 Texture Data 文件夹，建立纹理映射
        texture_data_dir = os.path.join(pack_folder, "Texture Data")
        proj.texture_sources = {}
        if os.path.exists(texture_data_dir):
            for filename in os.listdir(texture_data_dir):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    tex_name = os.path.splitext(filename)[0]
                    proj.texture_sources[tex_name] = os.path.join(texture_data_dir, filename)
        
        # 3. 读取 Import_Settings.txt
        import_settings_path = os.path.join(pack_folder, "Import_Settings.txt")
        if os.path.exists(import_settings_path):
            with open(import_settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            proj.export_author = settings.get("authorName", "n/a")
            proj.export_version = settings.get("version", "n/a")
            proj.export_description = settings.get("description", "n/a")
            proj.export_pack_name = os.path.basename(pack_folder)  # 使用文件夹名作为包名
        
        # 4. 读取 Space_Center_Data.txt
        space_center_path = os.path.join(pack_folder, "Space_Center_Data.txt")
        if os.path.exists(space_center_path):
            with open(space_center_path, 'r', encoding='utf-8') as f:
                sc_data = json.load(f)
            proj.space_center_address = sc_data.get("address", "Earth")
            proj.space_center_angle = sc_data.get("angle", 90.0)
            launchpad = sc_data.get("position_LaunchPad", {})
            proj.launchpad_horizontal = launchpad.get("horizontalPosition", 365.0)
            proj.launchpad_height = launchpad.get("height", 56.2)
        
        # 5. 读取 Version.txt 可做版本检查（可选）
        version_path = os.path.join(pack_folder, "Version.txt")
        if os.path.exists(version_path):
            with open(version_path, 'r', encoding='utf-8') as f:
                version_str = f.read().strip()
            if version_str != "1.6.00.16":
                print(f"警告: 行星包版本 {version_str} 可能与当前生成器不兼容")
        
        return proj