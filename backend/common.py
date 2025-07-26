import os
import sqlite3
from functools import wraps
from flask import request, jsonify, g, current_app
import jwt
import subprocess

# ========= ✅ 不再依赖 app.py =========
DATABASE = os.path.join(os.path.dirname(__file__), 'nas.db')

# 支持多个盘符
BASE_DIRS = ['D:/', 'E:/', 'F:/', 'G:/', 'H:/', 'I:/', 'J:/', 'K:/', 'L:/', 'M:/', 'N:/', 'O:/', 'P:/', 'Q:/', 'R:/',
             'S:/', 'T:/', 'U:/', 'V:/', 'W:/', 'X:/', 'Y:/', 'Z:/']


def get_available_drives():
    """获取系统中可用的盘符"""
    available_drives = []
    for drive in BASE_DIRS:
        if os.path.exists(drive):
            available_drives.append(drive)
    return available_drives


def is_path_allowed(path):
    """检查路径是否在允许的盘符范围内"""
    # 标准化路径格式，处理不同的斜杠
    normalized_path = os.path.normpath(path)
    abs_path = os.path.abspath(normalized_path)

    for base_dir in BASE_DIRS:
        normalized_base = os.path.normpath(base_dir)
        abs_base = os.path.abspath(normalized_base)

        # 检查路径是否以base_dir开头
        if abs_path.startswith(abs_base):
            return True

    return False


def get_base_dir_for_path(path):
    """
    根据路径获取对应的BASE_DIR，支持多种路径格式
    增强版本，支持更多路径格式
    """
    print(f"[DEBUG] get_base_dir_for_path 输入路径: {path}")

    if not path:
        print("[DEBUG] 路径为空，返回第一个可用盘符")
        available = get_available_drives()
        return available[0] if available else None

    # 标准化路径格式，统一使用正斜杠
    normalized_path = os.path.normpath(path).replace('\\', '/')
    print(f"[DEBUG] 标准化后路径: {normalized_path}")

    # 方法1：检查路径是否已经包含完整的盘符前缀
    for base_dir in BASE_DIRS:
        base_normalized = base_dir.replace('\\', '/')
        if normalized_path.startswith(base_normalized):
            if os.path.exists(base_dir):
                print(f"[DEBUG] 方法1匹配: {base_dir}")
                return base_dir

    # 方法2：尝试在所有可用盘符中查找文件
    for base_dir in BASE_DIRS:
        if not os.path.exists(base_dir):
            continue

        # 移除路径开头的斜杠，构建测试路径
        test_relative = normalized_path.lstrip('/')
        test_path = os.path.join(base_dir, test_relative)
        test_path_normalized = os.path.normpath(test_path)

        print(f"[DEBUG] 方法2测试路径: {test_path_normalized}")

        if os.path.exists(test_path_normalized):
            print(f"[DEBUG] 方法2找到文件: {base_dir}")
            return base_dir

    # 方法3：智能路径匹配
    # 尝试从路径中提取可能的盘符信息
    path_parts = normalized_path.split('/')
    if path_parts:
        first_part = path_parts[0]

        # 检查是否是盘符格式 (如 "D:")
        if len(first_part) == 2 and first_part[1] == ':':
            potential_drive = first_part + '/'
            if potential_drive in BASE_DIRS and os.path.exists(potential_drive):
                print(f"[DEBUG] 方法3提取盘符: {potential_drive}")
                return potential_drive

        # 检查是否是带盘符的格式 (如 "D:")
        for part in path_parts:
            if len(part) == 2 and part[1] == ':':
                potential_drive = part + '/'
                if potential_drive in BASE_DIRS and os.path.exists(potential_drive):
                    print(f"[DEBUG] 方法3找到内嵌盘符: {potential_drive}")
                    return potential_drive

    # 方法4：模糊匹配，尝试在每个盘符下查找相似路径
    for base_dir in BASE_DIRS:
        if not os.path.exists(base_dir):
            continue

        # 尝试不同的路径组合
        test_paths = [
            os.path.join(base_dir, normalized_path.lstrip('/')),
            os.path.join(base_dir, path.lstrip('/\\')),
            os.path.join(base_dir, os.path.basename(normalized_path))
        ]

        for test_path in test_paths:
            if os.path.exists(test_path):
                print(f"[DEBUG] 方法4模糊匹配: {base_dir} -> {test_path}")
                return base_dir

    # 方法5：返回默认可用盘符
    available_drives = get_available_drives()
    if available_drives:
        default_drive = available_drives[0]
        print(f"[DEBUG] 使用默认盘符: {default_drive}")
        return default_drive

    print("[DEBUG] 无法找到合适的base_dir")
    return None


def get_actual_file_path(path):
    """
    获取文件的实际完整路径
    这个函数会尝试找到文件的真实位置
    """
    print(f"[DEBUG] get_actual_file_path 输入: {path}")

    # 如果路径已经存在，直接返回
    if os.path.exists(path):
        result = os.path.abspath(path)
        print(f"[DEBUG] 路径直接存在: {result}")
        return result

    # 获取base_dir并构建完整路径
    base_dir = get_base_dir_for_path(path)
    if not base_dir:
        print("[DEBUG] 无法获取base_dir")
        return None

    # 移除路径中的base_dir前缀（如果存在）
    clean_path = path
    base_normalized = base_dir.replace('\\', '/')
    path_normalized = path.replace('\\', '/')

    if path_normalized.startswith(base_normalized):
        clean_path = path_normalized[len(base_normalized):].lstrip('/')
    else:
        clean_path = path_normalized.lstrip('/')

    # 构建最终路径
    final_path = os.path.join(base_dir, clean_path)
    final_path = os.path.normpath(final_path)

    print(f"[DEBUG] 构建的最终路径: {final_path}")
    print(f"[DEBUG] 路径是否存在: {os.path.exists(final_path)}")

    return final_path


def convert(src_path, pdf_path):
    output_dir = os.path.dirname(pdf_path)
    os.makedirs(output_dir, exist_ok=True)

    result = subprocess.run([
        "libreoffice",  # Windows 用户可改成绝对路径
        "--headless",
        "--convert-to", "pdf",
        "--outdir", output_dir,
        src_path
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode != 0:
        raise Exception(result.stderr.decode('utf-8'))

    if not os.path.exists(pdf_path):
        raise Exception("PDF 文件未成功生成。")


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


def token_required(admin_only=False):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = None
            if 'Authorization' in request.headers:
                parts = request.headers['Authorization'].split()
                if len(parts) == 2 and parts[0] == 'Bearer':
                    token = parts[1]
            if not token:
                return jsonify({'error': '缺少Token'}), 401
            try:
                data = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=["HS256"])
                db = get_db()
                user = db.execute("SELECT * FROM users WHERE id=?", (data['id'],)).fetchone()
                if not user or not user['is_active']:
                    return jsonify({'error': '无效Token'}), 401
                if admin_only and not user['is_admin']:
                    return jsonify({'error': '管理员权限不足'}), 403
                g.user = user
            except Exception:
                return jsonify({'error': 'Token无效'}), 401
            return f(*args, **kwargs)

        return decorated

    return decorator