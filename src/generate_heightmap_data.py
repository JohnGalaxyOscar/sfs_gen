#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
读取 Heightmap_Default 文件夹中的所有地形函数文件，
生成 constants.py 中的 HEIGHTMAP_DATA 字典。
"""

import os
import json
import re

def read_heightmap_files(heightmap_dir="Heightmap_Default"):
    """读取文件夹中的所有 .txt 文件，返回 {文件名: points数组} 字典"""
    heightmap_data = {}
    
    if not os.path.exists(heightmap_dir):
        print(f"错误: 文件夹 '{heightmap_dir}' 不存在！")
        return None
    
    # 获取所有 .txt 文件
    txt_files = [f for f in os.listdir(heightmap_dir) if f.endswith('.txt')]
    
    if not txt_files:
        print(f"警告: 在 '{heightmap_dir}' 中没有找到 .txt 文件")
        return {}
    
    for filename in txt_files:
        filepath = os.path.join(heightmap_dir, filename)
        name = filename[:-4]  # 去掉 .txt 后缀
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                points = data.get("points", [])
                if points:
                    heightmap_data[name] = points
                    print(f"✓ 已读取: {name} ({len(points)} 个点)")
                else:
                    print(f"⚠ 警告: {name} 中没有 'points' 字段或为空")
                    heightmap_data[name] = []
        except json.JSONDecodeError as e:
            print(f"✗ 解析失败: {filename} - {e}")
            heightmap_data[name] = []
        except Exception as e:
            print(f"✗ 读取失败: {filename} - {e}")
            heightmap_data[name] = []
    
    return heightmap_data

def format_points_array(points):
    """将点数组格式化为可读的 Python 列表字符串"""
    if not points:
        return "[]"
    
    # 每行放 6 个数值，保持可读性
    lines = []
    for i in range(0, len(points), 6):
        chunk = points[i:i+6]
        line = "        " + ", ".join(f"{v:.12f}" for v in chunk)
        lines.append(line)
    
    return "[\n" + ",\n".join(lines) + "\n    ]"

def generate_constants(heightmap_data, output_file="constants.py"):
    """生成新的 constants.py 文件"""
    
    # 读取原始的 constants.py（如果存在）
    original_content = ""
    if os.path.exists(output_file):
        with open(output_file, 'r', encoding='utf-8') as f:
            original_content = f.read()
    
    # 提取 BUILTIN_TEXTURES 部分（假设它在文件开头，到 HEIGHTMAP_DATA 之前）
    # 方法：查找 HEIGHTMAP_DATA 标记，如果不存在则保留全部
    builtin_textures_match = re.search(
        r'(BUILTIN_TEXTURES\s*=\s*\{[^}]+\})', 
        original_content, 
        re.DOTALL
    )
    
    if builtin_textures_match:
        builtin_textures = builtin_textures_match.group(1)
    else:
        # 如果没有找到，使用默认的空字典
        builtin_textures = "BUILTIN_TEXTURES = {}"
    
    # 生成新的 HEIGHTMAP_DATA 字符串
    heightmap_lines = ["HEIGHTMAP_DATA = {"]
    
    for name, points in sorted(heightmap_data.items()):
        points_str = format_points_array(points)
        heightmap_lines.append(f'    "{name}": {points_str},')
    
    heightmap_lines.append("}")
    heightmap_data_str = "\n".join(heightmap_lines)
    
    # 合并内容
    new_content = f"""{builtin_textures}

{heightmap_data_str}
"""
    
    # 写入文件
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"\n✅ 已生成 {output_file}")
    print(f"   共包含 {len(heightmap_data)} 个地形函数")

def main():
    print("=" * 50)
    print("SFS 地形函数数据生成器")
    print("=" * 50)
    
    # 读取 Heightmap_Default 文件夹
    heightmap_dir = "Heightmap_Default"
    print(f"\n正在读取文件夹: {heightmap_dir}")
    
    heightmap_data = read_heightmap_files(heightmap_dir)
    
    if heightmap_data is None:
        print("\n❌ 读取失败，请确保 Heightmap_Default 文件夹存在")
        return
    
    if not heightmap_data:
        print("\n⚠ 没有读取到任何地形数据，将生成空字典")
    
    # 生成 constants.py
    generate_constants(heightmap_data)
    
    print("\n" + "=" * 50)
    print("完成！")
    print("请检查生成的 constants.py 文件")
    print("=" * 50)

if __name__ == "__main__":
    main()