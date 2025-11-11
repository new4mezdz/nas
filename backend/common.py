import os
import sqlite3
from functools import wraps
from flask import request, jsonify, g, current_app
import jwt
import subprocess

# ========= ✅ 不再依赖 app.py =========
DATABASE = os.path.join(os.path.dirname(__file__), 'nas.db')

# 支持多个盘符
BASE_DIRS = ['E:/', 'F:/', 'G:/', 'H:/', 'I:/', 'J:/', 'K:/', 'L:/', 'M:/', 'N:/', 'O:/', 'P:/', 'Q:/', 'R:/',
             'S:/', 'T:/', 'U:/', 'V:/', 'W:/', 'X:/', 'Y:/', 'Z:/']

# 辅助函数（safe_join 必须保留在此处或移到 common.py/utils.py）
def safe_join(base, *paths):
    final_path = os.path.abspath(os.path.join(base, *paths))
    if not final_path.startswith(os.path.abspath(base)):
        raise ValueError("不允许访问此路径")
    return final_path
def get_available_drives():
    """获取系统中可用的盘符"""
    available_drives = []
    for drive in BASE_DIRS:
        if os.path.exists(drive):
            available_drives.append(drive)
    return available_drives

def _is_ec_volume(p: str) -> bool:
    """检查路径是否是 EC 卷的根目录 ('ec_volume') 或其子目录 ('ec_volume/...')"""
    if not p:
        return False

    # 统一路径分隔符并移除首尾斜杠
    q = p.replace("\\", "/").strip("/")

    # 强制检查是否是 EC 卷的根目录或子目录
    return q == "ec_volume" or q.startswith("ec_volume/")

# 文件: common.py (替换 is_path_allowed)

def is_path_allowed(path):
    """检查路径是否在允许的盘符范围内，并豁免 EC 卷路径。"""
    # 【✅ 关键修复：豁免EC卷路径】
    # 标准化路径进行检查
    normalized_path_check = path.replace("\\", "/").strip("/")
    if normalized_path_check == "ec_volume" or normalized_path_check.startswith("ec_volume/"):
        # EC 卷是一个虚拟路径，永远允许
        return True

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


# 文件: common.py (替换 get_base_dir_for_path)

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

    # 【✅ 关键修复：排除EC卷路径】
    # 如果路径是 EC 卷的根目录或子目录，它不是物理盘符，应立即返回 None
    normalized_path_check = path.replace("\\", "/").strip("/")
    if normalized_path_check == "ec_volume" or normalized_path_check.startswith("ec_volume/"):
        print("[DEBUG] 路径识别为 EC 卷，跳过物理盘查找。")
        return None  # 返回 None，由调用者（app.py中的路由）处理 EC 逻辑

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
    # ... (后续的方法2、方法3、方法4、方法5保持不变)

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

    # ... (后续的方法3、方法4保持不变)

    # 方法5：返回默认可用盘符
    available_drives = get_available_drives()
    if available_drives:
        default_drive = available_drives[0]
        print(f"[DEBUG] 使用默认盘符: {default_drive}")
        return default_drive

    print("[DEBUG] 无法找到合适的base_dir")
    return None


# 文件: common.py (替换 get_actual_file_path)

def get_actual_file_path(path):
    """
    获取文件的实际完整路径
    这个函数会尝试找到文件的真实位置
    """
    print(f"[DEBUG] get_actual_file_path 输入: {path}")

    # 【✅ 关键修复：EC 卷判断】
    # 如果是 EC 卷路径，则将其视为一个逻辑路径，返回原路径，由 app.py 处理
    normalized_path_check = path.replace("\\", "/").strip("/")
    if normalized_path_check == "ec_volume" or normalized_path_check.startswith("ec_volume/"):
        print("[DEBUG] 路径识别为 EC 卷逻辑路径。")
        # 返回一个规范化的 EC 路径，由 app.py 路由处理其虚拟文件系统
        return normalized_path_check

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