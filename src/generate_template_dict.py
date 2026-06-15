import json
import os

TEMPLATES_DIR = "templates"
CONSTANTS_FILE = "constants.py"

def generate_template_dict():
    # 读取所有模板文件
    templates = {}
    if not os.path.isdir(TEMPLATES_DIR):
        print(f"错误：找不到 {TEMPLATES_DIR} 文件夹")
        return

    for filename in os.listdir(TEMPLATES_DIR):
        if filename.endswith(".json"):
            name = filename[:-5]  # 去掉 .json
            filepath = os.path.join(TEMPLATES_DIR, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                templates[name] = data
                print(f"已加载: {name}")
            except Exception as e:
                print(f"加载 {filename} 失败: {e}")

    if not templates:
        print("没有找到任何模板文件")
        return

    # 将字典格式化为 Python 代码
    dict_str = "PLANET_TEMPLATES = " + json.dumps(templates, indent=2, ensure_ascii=False)

    # 追加到 constants.py
    try:
        with open(CONSTANTS_FILE, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        content = ""

    # 检查是否已经存在 PLANET_TEMPLATES 定义
    if "PLANET_TEMPLATES" in content:
        print("警告：constants.py 中已经存在 PLANET_TEMPLATES 定义，跳过写入。")
        return

    # 追加写入
    with open(CONSTANTS_FILE, "a", encoding="utf-8") as f:
        # 如果文件非空且末尾不是换行，先加换行
        if content and not content.endswith("\n"):
            f.write("\n")
        f.write("\n\n# 以下为自动生成的原版星球模板数据\n")
        f.write(dict_str)
        f.write("\n")

    print(f"成功将 {len(templates)} 个模板写入 {CONSTANTS_FILE}")

if __name__ == "__main__":
    generate_template_dict()