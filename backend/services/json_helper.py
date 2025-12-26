# services/json_helper.py
# -*- coding: utf-8 -*-
"""
JSON 文件操作辅助函数
"""

import os
import json


def load_json(path: str, default=None):
    """
    加载 JSON 文件
    
    Args:
        path: 文件路径
        default: 加载失败时返回的默认值
    
    Returns:
        解析后的 JSON 对象，或默认值
    """
    if default is None:
        default = {}
    
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[JSON] 加载失败 {path}: {e}")
    
    return default


def save_json(path: str, obj):
    """
    保存 JSON 文件
    
    Args:
        path: 文件路径
        obj: 要保存的对象
    """
    # 确保目录存在
    dir_path = os.path.dirname(path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
