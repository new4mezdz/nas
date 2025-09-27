# ===== Standard Library =====
import os
import io
import json
import time
import secrets
import sqlite3
import threading
import subprocess
import mimetypes
from pathlib import Path
from functools import wraps
from datetime import datetime, timedelta
import hashlib
# ===== Third-Party =====
from flask import Flask, request, jsonify, send_file, send_from_directory, g
from flask_socketio import SocketIO
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import requests
from docx2pdf import convert as docx2pdf_convert  # 避免遮蔽 common.convert
from docx import Document
from utils import get_disk_info, _norm_abs
# ===== Project / Local =====
from common import (
    BASE_DIRS, get_db, get_available_drives,
    is_path_allowed, get_base_dir_for_path, convert, _is_ec_volume # <-- 添加 _is_ec_volume
)

from utils import get_disk_info

# RS 系统码引擎（存储型纠删码）
from ec_engine.rs_systematic import encode as rs_encode, decode as rs_decode

# 可能仍在其它路由里用到
from ec_engine.ec_error import ECError


# 可选：如果这些模块在你项目中存在就保留
from collaboration import CollaborationManager
from collaboration_v2 import CollaborationV2
from onlyoffice import OnlyOfficeManager
from encryption import EncryptionManager, NotUnlockedError
# ===== 配置 =====
app = Flask(__name__, static_folder="../static", static_url_path="/static")
app.config['SECRET_KEY'] = 'super-secret-key'  # 建议换成更随机的密钥

# 初始化SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# 初始化协作管理器
collaboration_manager = CollaborationManager(app, socketio)

# 初始化新协作系统
collaboration_v2 = CollaborationV2(app)

# 初始化OnlyOffice管理器
onlyoffice_manager = OnlyOfficeManager(app)
preview_sessions = {}
# 放在 import 之后、全局区域
# [修改] 将配置文件路径改为 app.py 所在的目录 (backend 目录)
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
EC_CFG_PATH = os.path.join(BACKEND_DIR, "ec_config.json")
EC_IDX_PATH = os.path.join(BACKEND_DIR, "ec_index.json")
ENCRYPTION_CFG_PATH = os.path.join(BACKEND_DIR, "encryption_config.json")
encryption_manager = EncryptionManager(config_path=ENCRYPTION_CFG_PATH)
def _load_json(path: str, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print("[EC] load json failed:", e)
    return default

def _save_json(path: str, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# 文件: app.py (替换原有的 _is_ec_volume)


# 文件: app.py (确保此函数存在于全局区域)

# app.py -> 找到并替换这个函数

# app.py -> 找到并替换这个函数

# V5 修正版 (正确的)
def _decode_from_dict(shard_dict: dict, meta: dict) -> bytes:
    """
    一个更健壮的解码器，可以处理索引中缺少 'shard_size' 和 'original_size' 的情况。
    """
    k, m = meta["k"], meta["m"]

    # 使用 .get() 并提供备用值
    # 如果 "original_size" 不存在，就使用 "size"
    original_size = meta.get("original_size") or meta.get("size")
    if original_size is None:
        raise ECError("文件元数据中缺少 'original_size' 或 'size' 键")

    # 如果 "shard_size" 不存在，就根据原始大小和k值进行计算
    shard_size = meta.get("shard_size")
    if shard_size is None:
        shard_size = (original_size + k - 1) // k

    shard_list = [None] * (k + m)
    # 使用 .items() 遍历字典
    for i_str, buf in shard_dict.items():
        i = int(i_str)
        if 0 <= i < k + m:
            shard_list[i] = buf

    # 依赖 rs_decode (来自 ec_engine.rs_systematic)
    return rs_decode(shard_list, k, m, shard_size, original_size)

def _capacity_estimate(disks: list, k: int):
    """基于最小盘估算卷容量，并输出每盘容量信息与不均衡比例"""
    info_map = {d["mount"]: d for d in get_disk_info()}
    sizes = []
    for d in disks:
        meta = info_map.get(d) or {}
        sizes.append({
            "mount": d,
            "total": int(meta.get("bytes_total") or 0),
            "free":  int(meta.get("bytes_free")  or 0),
        })
    min_total = min((s["total"] for s in sizes if s["total"] > 0), default=0)
    min_free  = min((s["free"]  for s in sizes if s["free"]  > 0), default=0)
    max_total = max((s["total"] for s in sizes), default=0)
    imbalance = (max_total / min_total) if (min_total > 0) else 0.0
    return {
        "min_disk_total": min_total,
        "min_disk_free":  min_free,
        "usable_total_bytes": min_total * max(k, 0),
        "usable_free_bytes":  min_free  * max(k, 0),
        "imbalance_ratio":    imbalance,     # >1.2 说明盘容量差异较大
        "disks": sizes
    }
@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        is_admin INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        registered_at TEXT NOT NULL,
        current_directory TEXT DEFAULT ''
    )''')
    # 保证有一个admin账号
    cur = db.execute("SELECT COUNT(*) FROM users WHERE is_admin=1", ())
    if cur.fetchone()[0] == 0:
        db.execute(
            "INSERT INTO users (username, password, is_admin, is_active, registered_at, current_directory) VALUES (?, ?, ?, ?, ?, ?)",
            ("admin", generate_password_hash("123"), 1, 1, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "")
        )
    db.commit()


with app.app_context():
    init_db()


def init_share_table():
    db = get_db()
    db.execute('''
        CREATE TABLE IF NOT EXISTS share_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            token TEXT UNIQUE NOT NULL,
            password TEXT,
            expire_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    db.commit()


with app.app_context():
    init_share_table()


# ========== 确保原有的token_required装饰器支持多种token传递方式 ==========
def token_required(f=None, admin_only=False):
    def decorator(func):
        @wraps(func)
        def decorated(*args, **kwargs):
            token = None

            # 方法1: 从Authorization header获取
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]

            # 方法2: 从URL参数获取
            if not token:
                token = request.args.get('token')

            # 方法3: 从form数据获取
            if not token and hasattr(request, 'form') and request.form:
                token = request.form.get('token')

            if not token:
                print(f"[DEBUG] Token缺失 - 路径: {request.path}")
                return jsonify({'error': '缺少Token'}), 401

            try:
                # 验证token
                data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
                user_id = data.get('id')

                if not user_id:
                    print(f"[DEBUG] Token中缺少用户ID")
                    return jsonify({'error': 'Token格式错误'}), 401

                # 检查用户是否存在且活跃
                db = get_db()
                user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

                if not user:
                    print(f"[DEBUG] 用户不存在: {user_id}")
                    return jsonify({'error': '用户不存在'}), 401

                if not user['is_active']:
                    print(f"[DEBUG] 用户已禁用: {user['username']}")
                    return jsonify({'error': '用户已禁用'}), 401

                # 检查管理员权限
                if admin_only and not user['is_admin']:
                    print(f"[DEBUG] 权限不足: {user['username']}")
                    return jsonify({'error': '管理员权限不足'}), 403

                g.user = user_id

            except jwt.ExpiredSignatureError:
                print("[DEBUG] Token已过期")
                return jsonify({'error': 'Token已过期'}), 401
            except jwt.InvalidTokenError as e:
                print(f"[DEBUG] Token无效: {e}")
                return jsonify({'error': 'Token无效'}), 401
            except Exception as e:
                print(f"[DEBUG] Token验证异常: {e}")
                return jsonify({'error': 'Token验证失败'}), 401

            return func(*args, **kwargs)

        return decorated

    if callable(f):
        return decorator(f)
    return decorator



# ===== 用户注册/登录 =====
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400
    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (username, password, is_admin, is_active, registered_at, current_directory) VALUES (?, ?, 0, 1, ?, ?)",
            (username, generate_password_hash(password), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "")
        )
        db.commit()
        return jsonify({'success': True, 'message': '注册成功'})
    except sqlite3.IntegrityError:
        return jsonify({'error': '用户名已存在'}), 400


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    db = get_db()
    cur = db.execute("SELECT * FROM users WHERE username=?", (username,))
    user = cur.fetchone()
    if not user or not check_password_hash(user['password'], password):
        return jsonify({'error': '用户名或密码错误'}), 401
    if not user['is_active']:
        return jsonify({'error': '账号已被禁用'}), 403
    token = jwt.encode(
        {'id': user['id'], 'exp': datetime.utcnow() + timedelta(hours=24)},
        app.config['SECRET_KEY'],
        algorithm="HS256"
    )
    return jsonify({'success': True, 'token': token, 'user': {
        'username': user['username'],
        'is_admin': bool(user['is_admin'])
    }})


# ===== 用户管理后台 =====
@app.route('/api/users', methods=['GET'])
@token_required(admin_only=True)
def get_users():
    db = get_db()
    users = db.execute("SELECT id, username, is_admin, is_active, registered_at FROM users ORDER BY id").fetchall()
    return jsonify([dict(u) for u in users])


@app.route('/api/users/<int:user_id>', methods=['PATCH'])
@token_required(admin_only=True)
def update_user(user_id):
    data = request.get_json()
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        return jsonify({"error": "用户不存在"}), 404
    # 防止管理员把自己禁用或降权
    if user['id'] == g.user:
        if 'is_active' in data and not data['is_active']:
            return jsonify({"error": "不能禁用自己"}), 400
        if 'is_admin' in data and not data['is_admin']:
            return jsonify({"error": "不能取消自己的管理员权限"}), 400
    # 只允许更新 is_admin / is_active
    fields = []
    params = []
    if 'is_admin' in data:
        fields.append("is_admin=?")
        params.append(1 if data['is_admin'] else 0)
    if 'is_active' in data:
        fields.append("is_active=?")
        params.append(1 if data['is_active'] else 0)
    if not fields:
        return jsonify({"error": "无可更新字段"}), 400
    params.append(user_id)
    db.execute(f"UPDATE users SET {', '.join(fields)} WHERE id=?", params)
    db.commit()
    return jsonify({"success": True})


# 更新用户当前目录
@app.route('/api/current-directory', methods=['POST'])
@token_required()
def update_current_directory():
    data = request.get_json()
    directory = data.get('directory', '').strip()

    # 验证目录路径是否在BASE_DIR下
    if directory:
        abs_path = os.path.abspath(os.path.join(BASE_DIRS[0], directory))
        if not abs_path.startswith(os.path.abspath(BASE_DIRS[0])):
            return jsonify({'error': '非法路径'}), 403
        if not os.path.exists(abs_path) or not os.path.isdir(abs_path):
            return jsonify({'error': '目录不存在'}), 404

    # 更新用户当前目录
    db = get_db()
    db.execute("UPDATE users SET current_directory=? WHERE id=?", (directory, g.user))
    db.commit()

    return jsonify({'success': True, 'current_directory': directory})


# 获取用户当前目录
@app.route('/api/current-directory', methods=['GET'])
@token_required()
def get_current_directory():
    db = get_db()
    cur = db.execute("SELECT current_directory FROM users WHERE id=?", (g.user,))
    user = cur.fetchone()
    return jsonify({'current_directory': user['current_directory'] or ''})


# ===== 系统/磁盘信息接口 =====
from utils import get_sys_info, get_disk_info
import shutil


@app.route('/api/system', methods=['GET'])
@token_required()
def api_system():
    return jsonify(get_sys_info())


# 文件: app.py

@app.route('/api/disk', methods=['GET'])
@token_required()
def api_disk():
    """
    获取磁盘信息，并排除系统盘（C:\ 或 /）
    """
    # 1. 获取基础磁盘信息
    disk_info = get_disk_info()

    # [✅ 新增/修改] 排除系统盘的逻辑
    filtered_disk_info = []

    for disk in disk_info:
        mount_point = disk.get("mount", "").upper().replace("\\", "/")

        # 排除逻辑：
        # - Windows 上的 C:\ 盘符
        # - Linux/macOS 上的 / 根目录 (通常是系统分区)
        # 注意：这里我们保留所有其他挂载点，即使是 /mnt/ 或 /media/
        if mount_point == "C:/" or mount_point == "/":
            print(f"[DEBUG] 排除系统盘: {disk.get('mount')}")
            continue

        filtered_disk_info.append(disk)

    # 2. 读取纠删码配置
    ec_cfg = _load_json(EC_CFG_PATH, {})
    ec_disks = set()
    ec_scheme_name = None

    if ec_cfg and ec_cfg.get("disks"):
        # 将配置中的磁盘路径也进行规范化，以便比较
        ec_disks = set(_norm_abs(d) for d in ec_cfg.get("disks", []))
        ec_scheme_name = ec_cfg.get("scheme", "rs").upper()

    # 3. 遍历【已过滤的】磁盘信息，为参与纠删码的硬盘添加标记
    for disk in filtered_disk_info:
        # 规范化当前磁盘的挂载点
        normalized_mount = _norm_abs(disk.get("mount", ""))
        if normalized_mount in ec_disks:
            disk['ec_scheme'] = ec_scheme_name
        else:
            disk['ec_scheme'] = None

    # 4. 返回过滤并处理后的列表
    return jsonify(filtered_disk_info)


# 获取可用盘符
@app.route('/api/drives', methods=['GET'])
@token_required()
def get_drives():
    """获取系统中可用的盘符"""
    available_drives = get_available_drives()
    drives_info = []

    for drive in available_drives:
        try:
            # 获取磁盘使用情况
            total, used, free = shutil.disk_usage(drive)
            drives_info.append({
                'drive': drive,
                'total': total,
                'used': used,
                'free': free,
                'percent': round((used / total) * 100, 1) if total > 0 else 0
            })
        except Exception as e:
            # 如果无法获取磁盘信息，仍然返回盘符
            drives_info.append({
                'drive': drive,
                'total': 0,
                'used': 0,
                'free': 0,
                'percent': 0
            })

    return jsonify(drives_info)




# ===== 静态页面路由 =====
@app.route("/")
def index():
    static_folder = app.static_folder or 'static'
    return send_from_directory(static_folder, "index.html")


# 修改密码（普通用户）
@app.route('/api/change_password', methods=['PATCH'])
@token_required()
def change_password():
    data = request.get_json()
    old = data.get('old_password', '')
    new = data.get('new_password', '')
    if not old or not new:
        return jsonify({"error": "缺少参数"}), 400
    db = get_db()
    cur = db.execute("SELECT * FROM users WHERE id=?", (g.user,))
    user = cur.fetchone()
    if not check_password_hash(user['password'], old):
        return jsonify({"error": "原密码错误"}), 400
    db.execute("UPDATE users SET password=? WHERE id=?", (generate_password_hash(new), g.user))
    db.commit()
    return jsonify({"success": True})


# 管理员重置其他用户密码
@app.route('/api/admin/reset_password', methods=['POST'])
@token_required(admin_only=True)
def admin_reset_password():
    data = request.get_json()
    username = data.get('username', '').strip()
    newpw = data.get('new_password', '').strip()
    if not username or not newpw:
        return jsonify({"error": "缺少参数"}), 400
    db = get_db()
    cur = db.execute("SELECT id FROM users WHERE username=?", (username,))
    user = cur.fetchone()
    if not user:
        return jsonify({"error": "用户不存在"}), 404
    db.execute("UPDATE users SET password=? WHERE id=?", (generate_password_hash(newpw), user['id']))
    db.commit()
    return jsonify({"success": True})


# 文件: app.py (添加一个新的删除路由，用于单文件删除)

# 文件: app.py (新增 /api/rename 路由)

# 文件: app.py (替换 @app.route('/api/rename') 路由)

@app.route('/api/rename', methods=['POST'])
@token_required()
# 💡 修改函数名为 api_rename_entry
def api_rename_entry():
    data = request.get_json()
    path = data.get('path')
    new_name = data.get('new_name')

    print(f"[DEBUG] 重命名请求 - 原始路径: {path}")

    if not path or not new_name:
        return jsonify({"error": "参数缺失"}), 400

    if '..' in new_name or '/' in new_name or '\\' in new_name:
        return jsonify({"error": "文件名包含非法字符"}), 400

    # 1. 优先处理 EC 卷
    if _is_ec_volume(path):
        # ⚠️ EC 卷重命名逻辑待实现
        return jsonify({"error": "EC卷重命名功能暂不支持"}), 501

    # 2. 物理盘重命名
    else:
        try:
            from common import get_actual_file_path, is_path_allowed
            actual_path = get_actual_file_path(path)

            if not actual_path or not os.path.exists(actual_path):
                return jsonify({"error": "源文件不存在"}), 404

            if not is_path_allowed(actual_path):
                return jsonify({"error": "路径不在允许的目录中"}), 403

            parent_dir = os.path.dirname(actual_path)
            new_actual_path = os.path.join(parent_dir, new_name)

            if os.path.exists(new_actual_path):
                return jsonify({"error": "目标文件名已存在"}), 400

            os.rename(actual_path, new_actual_path)
            return jsonify({"success": True})

        except Exception as e:
            return jsonify({"error": f"重命名失败: {str(e)}"}), 500

@app.route('/api/delete', methods=['POST'])
@token_required()
def delete_entry():
    data = request.get_json()
    path = data.get('path')
    if not path:
        return jsonify({'error': '缺少路径参数'}), 400

    # 1. 优先处理 EC 卷删除
    if _is_ec_volume(path):
        # EC 卷只允许删除文件，不允许删除目录
        if path.endswith('/'):  # 简单的目录判断
            return jsonify({"error": "EC卷暂不支持删除虚拟目录"}), 400

        # 从索引中删除文件
        idx = _load_json(EC_IDX_PATH, {"files": {}})
        logical_name = path.replace("\\", "/").strip("/")

        if logical_name in idx.get("files", {}):
            # 记录磁盘位置
            disks_to_clean = idx["files"][logical_name]["disks"]

            # 1. 从索引中移除
            del idx["files"][logical_name]
            _save_json(EC_IDX_PATH, idx)

            # 2. 移除物理分片
            base = os.path.basename(logical_name)
            for disk in disks_to_clean:
                enc_dir = os.path.join(disk, "encoded", os.path.dirname(logical_name))
                for file_ext in [f"{base}.blk_*", f"{base}.meta.json"]:
                    for f in glob.glob(os.path.join(enc_dir, file_ext)):
                        os.remove(f)

            return jsonify({"success": True, "message": "EC卷文件已删除"})
        else:
            return jsonify({"error": "EC卷文件不存在"}), 404

    # 2. 物理盘删除
    else:
        from common import get_actual_file_path, is_path_allowed
        actual_path = get_actual_file_path(path)

        if not actual_path:
            return jsonify({'error': '文件或目录不存在'}), 404

        if not is_path_allowed(actual_path):
            return jsonify({"error": "路径不在允许的目录中"}), 403

        try:
            if os.path.isdir(actual_path):
                shutil.rmtree(actual_path)
            else:
                os.remove(actual_path)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': f'删除失败: {str(e)}'}), 500
@app.route('/api/batch_delete', methods=['POST'])
@token_required(admin_only=True)  # 或普通用户，按你的需求改
def batch_delete():
    data = request.get_json()
    paths = data.get('paths', [])
    errors = []
    for path in paths:
        try:
            abspath = safe_join(BASE_DIRS[0], path.lstrip("/\\"))
            if not abspath.startswith(BASE_DIRS[0]):
                errors.append(path)
                continue
            if os.path.isdir(abspath):
                shutil.rmtree(abspath)
            else:
                os.remove(abspath)
        except Exception:
            errors.append(path)
    if errors:
        return jsonify({"success": False, "error": f"部分或全部删除失败: {errors}"}), 400
    return jsonify({"success": True})


# ========== 在 app.py 中修复预览API ==========

# 文件: app.py -> @app.route('/api/preview')

# 文件: app.py -> @app.route('/api/preview')

@app.route('/api/preview')
@token_required()
def preview_file():
    path = request.args.get('path', '').strip()
    if not path:
        return jsonify({'error': '未指定文件路径'}), 400

    print(f"[DEBUG] 预览请求 - 原始路径: {path}")

    # 1. 优先处理 EC 卷
    if _is_ec_volume(path):
        from common import get_actual_file_path

        logical_path = get_actual_file_path(path)
        index_key = logical_path.replace('ec_volume/', '', 1).strip('/')

        if not index_key:
            return jsonify({'error': 'EC 卷路径无效'}), 400

        # 从索引中获取文件元数据
        idx = _load_json(EC_IDX_PATH, {"files": {}})
        entry = idx.get("files", {}).get(index_key)

        print(f"[DEBUG] 查找 EC 索引键: {index_key}")

        if not entry:
            return jsonify({'error': 'EC 卷文件不存在'}), 404

        k, m, disks = entry["k"], entry["m"], entry["disks"]
        shard_dict, meta = {}, None
        base_filename = os.path.basename(index_key)

        # 读取分片和元数据
        for i, disk in enumerate(disks[:k + m]):
            enc_dir = os.path.join(disk, "encoded", os.path.dirname(index_key))
            blk = os.path.join(enc_dir, f"{base_filename}.blk_{i}")

            if os.path.exists(blk):
                with open(blk, "rb") as f:
                    shard_dict[i] = f.read()
            if not meta:
                mj = os.path.join(enc_dir, f"{base_filename}.meta.json")
                if os.path.exists(mj):
                    with open(mj, "r", encoding="utf-8") as mf:
                        meta = json.load(mf)

        # 检查是否可恢复
        if not meta or len(shard_dict) < k:
            return jsonify({'error': '可用分片不足，无法恢复'}), 409

        # 🚨 语法修正开始 🚨
        data = None  # 确保在 try 块外部初始化
        try:
            # 执行解码
            data = _decode_from_dict(shard_dict, meta)
        except Exception as e: # ⬅️ 确保 except 与 try 对齐
            import traceback
            traceback.print_exc()
            print(f"[ERROR] EC 预览解码失败: {e}")
            return jsonify({'error': f'EC 卷文件解码失败: {e}'}), 500

        # 确保 data 已赋值
        if data is None:
            return jsonify({'error': '文件解码失败或返回空数据'}), 500

        # 返回文件流
        mime = mimetypes.guess_type(index_key)[0] or 'application/octet-stream'
        return send_file(io.BytesIO(data), mimetype=mime)

    # 2. 处理物理硬盘 (物理盘逻辑保持不变)
    else:
        # ... (物理盘逻辑保持不变) ...
        try:
            from common import get_actual_file_path, is_path_allowed
            actual_path = get_actual_file_path(path)

            print(f"[DEBUG] 预览请求 - 解析后物理路径: {actual_path}")

            if not actual_path:
                return jsonify({'error': '文件不存在或路径无效'}), 404

            # 最终安全检查
            if not is_path_allowed(actual_path):
                print(f"[DEBUG] 预览失败 - 路径不允许: {actual_path}")
                return jsonify({'error': '路径不在允许的目录中'}), 403

            if not os.path.exists(actual_path) or not os.path.isfile(actual_path):
                return jsonify({'error': '文件不存在或不是文件'}), 404

            # ===== 文本类文件 =====
            ext = os.path.splitext(actual_path)[1].lower()
            if ext in ['.txt', '.log', '.md', '.py', '.js', '.html', '.json', '.css', '.csv']:
                # 假设文本读取逻辑已在外部定义
                try:
                    with open(actual_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    return content, 200, {'Content-Type': 'text/plain; charset=utf-8'}
                except Exception:
                    return jsonify({'error': '文本读取失败'}), 500

            # ===== PDF文件处理 =====
            elif ext == '.pdf':
                return jsonify({'error': '请使用inline=true参数'}), 400

            # ===== 其他文件类型 =====
            else:
                mime = mimetypes.guess_type(actual_path)[0] or 'application/octet-stream'
                return send_file(actual_path, mimetype=mime)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'预览处理失败: {str(e)}'}), 500
# ===== [最终修复 2/3] 重写 mkdir 函数 =====
@app.route('/api/mkdir', methods=['POST'])
@token_required()
def mkdir():
    data = request.get_json()
    parent = data.get('parent', '')
    name = data.get('name', '').strip()
    if not name: return jsonify({'error': '文件夹名不能为空'}), 400
    if not parent: return jsonify({'error': '父路径不能为空'}), 400

    # --- 分支 1: 处理纠删码卷 (虚拟创建) ---
    if _is_ec_volume(parent):
        return jsonify({'success': True, 'message': '虚拟目录将在上传文件后自动体现'})

    # --- 分支 2: 处理物理硬盘 ---
    else:
        try:
            parent_abs_path = os.path.abspath(parent)
            new_dir_abs_path = os.path.join(parent_abs_path, name)
            allowed = False
            for base_dir in get_available_drives():
                if parent_abs_path.upper().startswith(os.path.abspath(base_dir).upper()):
                    allowed = True
                    break
            if not allowed:
                return jsonify({'error': '路径非法或不允许访问的磁盘'}), 403
            os.makedirs(new_dir_abs_path, exist_ok=False)
            return jsonify({'success': True})
        except FileExistsError:
            return jsonify({'error': '文件夹已存在'}), 400
        except Exception as e:
            return jsonify({'error': '创建失败: ' + str(e)}), 500

# app.py -> 替换 @app.route('/api/share', methods=['POST'])

@app.route('/api/ec_status', methods=['GET'])
@token_required(admin_only=True)
def get_ec_status():
    """
    获取纠删码卷的健康状况.
    """
    cfg = _load_json(EC_CFG_PATH, {})
    if not cfg:
        return jsonify({"is_configured": False})

    k = cfg.get("k", 0)
    m = cfg.get("m", 0)
    config_disks = set(cfg.get("disks", []))

    # 获取当前系统中所有可用的、非系统盘的挂载点
    from utils import get_disk_info
    available_disks = set()
    for disk in get_disk_info():
        mount_point = disk.get("mount", "").upper().replace("\\", "/")
        if not (mount_point == "C:/" or mount_point == "/"):
            available_disks.add(_norm_abs(disk.get("mount")))

    lost_disks = [d for d in config_disks if _norm_abs(d) not in available_disks]

    is_healthy = not bool(lost_disks)
    can_rebuild = 0 < len(lost_disks) <= m

    return jsonify({
        "is_configured": True,
        "is_healthy": is_healthy,
        "k": k,
        "m": m,
        "config_disks": list(config_disks),
        "lost_disks": lost_disks,
        "can_rebuild": can_rebuild,
        # "available_new_disks" 列出可用于替换的、未被EC卷占用的新硬盘
        "available_new_disks": [d for d in available_disks if d not in config_disks]
    })




# V5 测试版 (正确的)
@app.route('/api/ec_recover', methods=['POST'])
@token_required
def ec_recover_disk():
    # =================================================================
    # V5 - 最终返回值测试版
    # =================================================================
    print("\n\n" + "=" * 50)
    print("==> V5 RECOVERY FUNCTION IS RUNNING! <==")
    print(f"==> Time: {datetime.now()} <==")
    print("=" * 50 + "\n")

    data = request.get_json()
    lost_disk_raw = data.get('lost_disk', '')
    new_disk_raw = data.get('new_disk', '')
    lost_disk_path = _norm_abs(lost_disk_raw)
    new_disk_path = _norm_abs(new_disk_raw)

    cfg = _load_json(EC_CFG_PATH, {})
    if not cfg: return jsonify({"error": "未配置纠删码"}), 400

    config_disks_raw = cfg.get("disks", [])
    config_disks_normalized = [_norm_abs(d) for d in config_disks_raw]
    if lost_disk_path not in config_disks_normalized:
        return jsonify({"error": "丢失的硬盘不在全局配置中"}), 400
    new_config_disks_raw = [new_disk_raw if _norm_abs(d) == lost_disk_path else d for d in config_disks_raw]
    cfg["disks"] = new_config_disks_raw
    _save_json(EC_CFG_PATH, cfg)

    idx = _load_json(EC_IDX_PATH, {"files": {}})
    files_to_rebuild = list(idx.get("files", {}).items())
    rebuilt_count = 0
    failed_files = []

    for name, meta in files_to_rebuild:
        k, m = meta["k"], meta["m"]
        file_disks_raw = meta.get("disks", [])
        if not file_disks_raw:
            failed_files.append(name)
            continue
        file_disks_normalized = [_norm_abs(d) for d in file_disks_raw]

        try:
            lost_shard_index = file_disks_normalized.index(lost_disk_path)
        except ValueError:
            continue

        shard_dict = {}
        for i, disk_raw in enumerate(file_disks_raw):
            if _norm_abs(disk_raw) == lost_disk_path: continue
            enc_dir = os.path.join(disk_raw, "encoded", os.path.dirname(name))
            blk_path = os.path.join(enc_dir, f"{os.path.basename(name)}.blk_{i}")
            if os.path.exists(blk_path):
                with open(blk_path, "rb") as f: shard_dict[i] = f.read()

        if len(shard_dict) < k:
            failed_files.append(name)
            continue

        try:
            reconstructed_data = _decode_from_dict(shard_dict, meta)
            all_new_shards = rs_encode(reconstructed_data, k, m)
            shard_to_write = all_new_shards[lost_shard_index]
            new_shard_dir = os.path.join(new_disk_raw, "encoded", os.path.dirname(name))
            os.makedirs(new_shard_dir, exist_ok=True)
            new_shard_path = os.path.join(new_shard_dir, f"{os.path.basename(name)}.blk_{lost_shard_index}")
            with open(new_shard_path, "wb") as f:
                f.write(shard_to_write)

            idx["files"][name]["disks"] = new_config_disks_raw
            rebuilt_count += 1
        except Exception as e:
            print(f"ERROR: Exception during recovery for {name}: {e}")
            failed_files.append(name)
            continue

    _save_json(EC_IDX_PATH, idx)

    final_message = f"V5-FINAL-TEST :: 恢复完成。共重建 {rebuilt_count} 个文件。"
    print("\n" + "=" * 50)
    print(f"SENDING RESPONSE TO FRONTEND: '{final_message}'")
    print("=" * 50 + "\n")

    return jsonify({
        "success": True,
        "message": final_message,
        "failed_files": failed_files
    })

@app.route('/api/share', methods=['POST'])
@token_required()
def create_share():
    data = request.get_json()
    file_path = data.get('file_path', '')
    expire_hours = int(data.get('expire_hours', 24))
    password = data.get('password', '')

    # [✅ 核心修正区域]
    file_exists = False
    # --- 分支 1: 检查纠删码卷文件是否存在 ---
    if _is_ec_volume(file_path):
        # 从 "ec_volume/path/to/file.jpg" 提取 "path/to/file.jpg"
        logical_name = file_path.replace("\\", "/").strip("/").split("/", 1)[-1]
        if logical_name:
            idx = _load_json(EC_IDX_PATH, {"files": {}})
            # 在索引中检查文件是否存在
            if logical_name in idx.get("files", {}):
                file_exists = True

    # --- 分支 2: 检查物理硬盘文件是否存在 ---
    else:
        # 使用我们已有的、更可靠的函数来获取和验证物理路径
        from common import get_actual_file_path, is_path_allowed
        actual_path = get_actual_file_path(file_path)
        if actual_path and is_path_allowed(actual_path) and os.path.exists(actual_path):
            file_exists = True

    # --- 统一处理 ---
    if not file_exists:
        return jsonify({'error': '文件不存在'}), 404

    # 文件验证通过，继续创建分享链接
    token = secrets.token_urlsafe(16)
    expire_at = datetime.now() + timedelta(hours=expire_hours)
    db = get_db()
    db.execute(
        "INSERT INTO share_links (file_path, token, password, expire_at) VALUES (?, ?, ?, ?)",
        (file_path, token, password, expire_at.strftime('%Y-%m-%d %H:%M:%S'))
    )
    db.commit()

    # 返回外链地址
    # 注意：ngrok_url_global 需要在您的代码中正确设置
    return jsonify({
        'success': True,
        'share_url': f'/share/{token}',
        'full_url': f'{ngrok_url_global}/share/{token}' if 'ngrok_url_global' in globals() and ngrok_url_global else None
    })
# ===== PWA 支持路由 =====
# 将以下代码添加到您的 app.py 文件中，放在其他 @app.route 附近
# 在 backend/app.py 中添加或修改这些PWA路由

# ===== 完整的PWA路由（放在backend/app.py中）=====

@app.route('/static/pwa/manifest.json')
def pwa_manifest():
    """PWA应用清单 - 确保正确的HTTP头"""
    try:
        # 方法1：直接返回JSON数据（推荐）
        manifest_data = {
            "name": "NAS控制面板",
            "short_name": "NAS",
            "description": "个人网络存储系统管理界面",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#f7fafc",
            "theme_color": "#2c3e50",
            "lang": "zh-CN",
            "scope": "/",
            "icons": [
                {
                    "src": "/static/pwa/icons/icon-192.png",
                    "sizes": "192x192",
                    "type": "image/png",
                    "purpose": "any maskable"
                },
                {
                    "src": "/static/pwa/icons/icon-512.png",
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any maskable"
                }
            ]
        }

        # 创建响应，确保正确的Content-Type
        response = jsonify(manifest_data)
        response.headers['Content-Type'] = 'application/manifest+json'
        response.headers['Cache-Control'] = 'public, max-age=86400'  # 缓存24小时
        response.headers['Access-Control-Allow-Origin'] = '*'

        return response

    except Exception as e:
        print(f"[ERROR] Manifest路由错误: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/static/pwa/sw.js')
def pwa_service_worker():
    """PWA Service Worker"""
    response = send_from_directory('../client/pwa', 'sw.js', mimetype='application/javascript')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/favicon.ico')
def favicon():
    """网站图标 - 使用PWA图标作为favicon"""
    return send_from_directory('../static/pwa/icons', 'icon-192.png', mimetype='image/png')

# 可选：更新测试路由以验证路径
@app.route('/test-pwa')
def test_pwa():
    import os

    # 获取当前工作目录 (backend目录)
    cwd = os.getcwd()

    result = {
        'message': 'PWA路径测试 (从backend目录)',
        'current_working_directory': cwd,
        'files': {
            '../client/pwa/manifest.json': os.path.exists('../client/pwa/manifest.json'),
            '../client/pwa/sw.js': os.path.exists('../client/pwa/sw.js'),
            '../static/pwa/icons/icon-192.png': os.path.exists('../static/pwa/icons/icon-192.png'),
            '../static/pwa/icons/icon-512.png': os.path.exists('../static/pwa/icons/icon-512.png'),
            '../static/index.html': os.path.exists('../static/index.html'),
            '../static/app.js': os.path.exists('../static/app.js')
        }
    }

    return jsonify(result)

# app.py

@app.route('/share/<token>', methods=['GET', 'POST'])
def access_share(token):
    db = get_db()
    row = db.execute("SELECT * FROM share_links WHERE token=?", (token,)).fetchone()
    if not row:
        return "链接无效或已删除", 404

    # 检查过期
    if row['expire_at'] and datetime.strptime(row['expire_at'], '%Y-%m-%d %H:%M:%S') < datetime.now():
        db.execute("DELETE FROM share_links WHERE token=?", (token,))
        db.commit()
        return "链接已过期", 403

    # 校验密码
    if row['password']:
        if request.method == 'POST':
            pwd = request.form.get('password', '')
            if pwd != row['password']:
                return "密码错误", 403
        else:
            # GET: 显示密码输入表单
            return '''
                <style>body { font-family: sans-serif; text-align: center; padding-top: 50px; }</style>
                <form method="post">
                  <h3>请输入分享密码</h3>
                  <input name="password" type="password" style="padding: 8px;"/>
                  <button type="submit" style="padding: 8px 12px;">提交</button>
                </form>
            '''

    # [✅ 核心修正区域]
    # 密码通过后，根据文件路径类型（EC卷或物理盘）返回文件
    file_path = row['file_path']

    # --- 分支 1: 处理纠删码卷文件 ---
    if _is_ec_volume(file_path):
        name = file_path.replace("\\", "/").strip("/").split("/", 1)[-1]
        if not name:
            return "无效的逻辑盘文件路径", 400

        idx = _load_json(EC_IDX_PATH, {"files": {}}).get("files", {})
        entry = idx.get(name)
        if not entry:
            return "分享的文件已在逻辑盘中被删除或移动", 404

        k, m, disks = entry["k"], entry["m"], entry["disks"]
        shard_dict, meta = {}, None

        # 从各磁盘读取分片和元数据
        for i, disk in enumerate(disks[:k + m]):
            enc_dir = os.path.join(disk, "encoded", os.path.dirname(name))
            blk = os.path.join(enc_dir, f"{os.path.basename(name)}.blk_{i}")
            if os.path.exists(blk):
                with open(blk, "rb") as f:
                    shard_dict[i] = f.read()
            if not meta:
                mj = os.path.join(enc_dir, f"{os.path.basename(name)}.meta.json")
                if os.path.exists(mj):
                    with open(mj, "r", encoding="utf-8") as mf:
                        meta = json.load(mf)

        if not meta or len(shard_dict) < k:
            return "文件分片损坏或不足，暂时无法访问", 409

        try:
            # 解码重组文件
            data = _decode_from_dict(shard_dict, meta)
        except Exception as e:
            print(f"[ERROR] Share link decode failed for {name}: {e}")
            return "文件解码失败，请检查后台日志", 500

        # （可选）完整性校验
        if meta.get("sha256") and hashlib.sha256(data).hexdigest() != meta.get("sha256"):
            return "文件完整性校验失败，文件可能已损坏", 500

        # 将解码后的文件内容作为内存中的字节流发送出去
        return send_file(io.BytesIO(data), as_attachment=True, download_name=os.path.basename(name))

    # --- 分支 2: 处理物理硬盘文件 (保持并优化原有逻辑) ---
    else:
        from common import get_actual_file_path, is_path_allowed
        actual_path = get_actual_file_path(file_path)

        if not actual_path or not is_path_allowed(actual_path) or not os.path.exists(actual_path):
            return "分享的文件不存在或已被移动", 404

        return send_file(actual_path, as_attachment=True)

@app.route('/api/ngrok-url')
def api_ngrok_url():
    if ngrok_url_global:
        return jsonify({'url': ngrok_url_global})
    return jsonify({'error': 'ngrok 地址暂不可用'}), 503


# ====== /api/ec_config：支持 GET（查看）与 POST（保存）======
# ===== /api/ec_config：保存时对 disks 做 _norm_abs 归一化 =====
# ===== /api/ec_config：支持 GET（查看）、POST（保存）和 DELETE（删除）=====
@app.route("/api/ec_config", methods=["GET", "POST", "DELETE"])
@token_required()
def api_ec_config():
    """
    GET    返回当前纠删码配置与容量评估
    POST   保存纠删码配置（scheme=rs, k, m, disks），归一化 disks，创建各盘 encoded/ 目录，并返回容量评估
    DELETE 删除纠删码配置，清空设置
    """
    # 新增：处理DELETE请求
    if request.method == "DELETE":
        try:
            # 删除配置文件
            if os.path.exists(EC_CFG_PATH):
                os.remove(EC_CFG_PATH)
            # 删除索引文件
            if os.path.exists(EC_IDX_PATH):
                os.remove(EC_IDX_PATH)
            return jsonify({"success": True, "message": "纠删码配置已成功删除"})
        except Exception as e:
            return jsonify({"error": f"删除配置失败: {str(e)}"}), 500

    # ----- 原有的GET和POST逻辑保持不变 -----
    def _capacity_estimate(disks_norm: list, k: int):
        info = get_disk_info()
        info_map = { _norm_abs(d["mount"]): d for d in info if "mount" in d }
        sizes = []
        for d in disks_norm:
            di = info_map.get(_norm_abs(d))
            if di:
                total = int(di.get("bytes_total") or di.get("total") or 0)
                free  = int(di.get("bytes_free")  or di.get("free")  or 0)
            else:
                try:
                    import shutil
                    du = shutil.disk_usage(d)
                    total, free = int(du.total), int(du.free)
                except Exception:
                    total, free = 0, 0
            sizes.append({"mount": d, "total": total, "free": free})

        min_total = min((s["total"] for s in sizes if s["total"] > 0), default=0)
        min_free  = min((s["free"]  for s in sizes if s["free"]  > 0), default=0)
        max_total = max((s["total"] for s in sizes), default=0)
        imbalance = (max_total / min_total) if (min_total > 0) else 0.0
        return {
            "min_disk_total": min_total,
            "min_disk_free":  min_free,
            "usable_total_bytes": min_total * max(k, 0),
            "usable_free_bytes":  min_free  * max(k, 0),
            "imbalance_ratio":    imbalance,
            "disks": sizes
        }

    if request.method == "GET":
        cfg = _load_json(EC_CFG_PATH, {})
        if not cfg:
            return jsonify({"success": True, "config": None})
        k = int(cfg.get("k") or 0)
        capacity = _capacity_estimate(cfg.get("disks", []), k) if cfg.get("disks") else None
        return jsonify({"success": True, "config": cfg, "capacity": capacity})

    # ---- POST 保存配置（含归一化）----
    data = request.get_json(force=True, silent=False)
    scheme = (data.get("scheme") or "rs").lower()
    k = int(data.get("k") or 0)
    m = int(data.get("m") or 0)
    raw_disks = data.get("disks") or []

    if scheme != "rs":
        return jsonify({"error": "仅支持 scheme='rs'"}), 400
    if k <= 0 or m <= 0:
        return jsonify({"error": "k 和 m 必须为正整数"}), 400

    seen = set()
    disks_norm = []
    for d in raw_disks:
        p = _norm_abs(d)
        if p not in seen:
            disks_norm.append(p)
            seen.add(p)

    if len(disks_norm) < k + m:
        return jsonify({"error": f"磁盘数量不足，需要 ≥ k+m = {k+m}"}), 400

    mounts = { _norm_abs(d["mount"]) for d in get_disk_info() }
    invalid = [orig for orig in raw_disks if _norm_abs(orig) not in mounts]
    if invalid:
        return jsonify({"error": "存在无效磁盘", "invalid": invalid}), 400

    try:
        for d in disks_norm:
            os.makedirs(os.path.join(d, "encoded"), exist_ok=True)
    except Exception as e:
        return jsonify({"error": f"无法创建 encoded 目录：{e}"}), 500

    cfg = {"scheme": scheme, "k": k, "m": m, "disks": disks_norm}
    _save_json(EC_CFG_PATH, cfg)

    if not os.path.exists(EC_IDX_PATH):
        _save_json(EC_IDX_PATH, {"files": {}})

    capacity = _capacity_estimate(disks_norm, k)

    return jsonify({
        "success": True,
        "config": cfg,
        "capacity": capacity
    })


@app.route('/api/encode', methods=['POST'])
@token_required(admin_only=True)
def api_encode():
    """
    兼容旧接口：接受 {scheme,k,m,disks,file_path}，
    用系统码RS编码并写入各盘 encoded/，同时更新 ec_index.json。
    file_path 相对 BASE_DIRS[0]。
    """
    data = request.get_json(force=True)
    scheme = (data.get('scheme') or 'rs').lower()
    k = int(data.get('k') or 0)
    m = int(data.get('m') or 0)
    disks = [os.path.abspath(d) for d in (data.get('disks') or [])]
    rel = (data.get('file_path') or '').lstrip('/\\')
    src = os.path.abspath(os.path.join(BASE_DIRS[0], rel))

    if scheme != 'rs':
        return jsonify({'error': "仅支持 scheme='rs'"}), 400
    if k <= 0 or m <= 0:
        return jsonify({'error': 'k 和 m 必须为正整数'}), 400
    if len(disks) < k + m:
        return jsonify({'error': f'磁盘数量不足（需要≥{k+m}）'}), 400
    if not os.path.exists(src) or not os.path.isfile(src):
        return jsonify({'error': '源文件不存在'}), 404

    try:
        with open(src, 'rb') as f:
            data_bytes = f.read()
        shards = rs_encode(data_bytes, k, m)
        shard_size = len(shards[0]) if shards else 0
        file_sha = hashlib.sha256(data_bytes).hexdigest()
        logical_name = os.path.basename(src)

        meta = {
            'k': k, 'm': m,
            'shard_size': shard_size,
            'original_size': len(data_bytes),
            'sha256': file_sha
        }

        # 写分片 + meta（等长分片风格，与 /api/upload 保持一致）
        for i, disk in enumerate(disks[:k+m]):
            enc_dir = os.path.join(disk, 'encoded')
            os.makedirs(enc_dir, exist_ok=True)
            with open(os.path.join(enc_dir, f'{logical_name}.blk_{i}'), 'wb') as wf:
                wf.write(shards[i])
            with open(os.path.join(enc_dir, f'{logical_name}.meta.json'), 'w', encoding='utf-8') as mf:
                json.dump(meta, mf, ensure_ascii=False)

        # 更新索引
        idx = _load_json(EC_IDX_PATH, {'files': {}})
        idx['files'][logical_name] = {
            'size': len(data_bytes), 'k': k, 'm': m, 'sha256': file_sha,
            'disks': disks, 'ctime': int(time.time())
        }
        _save_json(EC_IDX_PATH, idx)

        return jsonify({'success': True, 'message': '编码成功（系统码RS）', 'name': logical_name})
    except ECError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'内部错误: {e}'}), 500


# 文件: app.py

@app.route('/api/upload', methods=['POST'])
@token_required()
def upload_file_with_ec():
    uploaded_files = request.files.getlist('file')
    upload_path = request.form.get('path', '/')
    print(f"[DEBUG] 上传请求接收路径: {upload_path}")
    if not uploaded_files or not all(f.filename for f in uploaded_files):
        return jsonify({'error': '未提供文件'}), 400

    # 逻辑盘：自动 RS
    if _is_ec_volume(upload_path):
        ec_cfg = _load_json(EC_CFG_PATH, {})
        if not ec_cfg or ec_cfg.get("scheme", "").lower() != "rs":
            return jsonify({'error': '未配置或未启用RS纠删码'}), 400

        k = int(ec_cfg.get("k", 0))
        m = int(ec_cfg.get("m", 0))
        disks = ec_cfg.get("disks", [])

        if k <= 0: return jsonify({'error': 'RS参数无效：k值必须大于0'}), 400
        if m <= 0: return jsonify({'error': 'RS参数无效：m值必须大于0'}), 400
        if len(disks) < k + m: return jsonify(
            {'error': f'RS参数无效：磁盘数量 ({len(disks)}) 不足，需要至少 k+m ({k + m}) 个'}), 400

        for uploaded_file in uploaded_files:
            data = uploaded_file.read()
            try:
                shards = rs_encode(data, k, m)
            except Exception as e:
                return jsonify({'error': f'文件 {uploaded_file.filename} 纠删码编码失败: {e}'}), 500

            shard_size = len(shards[0]) if shards else 0
            file_sha = hashlib.sha256(data).hexdigest()

            # --- ✅ 关键修复区域开始 ---
            norm_path = upload_path.replace("\\", "/").strip("/")

            # 获取文件在EC卷中的相对路径（如：dirA/dirB）
            if norm_path == 'ec_volume':
                rel_in_volume_dir = ''  # 根目录
            else:
                rel_in_volume_dir = norm_path[len('ec_volume/'):]  # 子目录

            # 文件的逻辑全名 (例如: dirA/dirB/fileName.ext)
            logical_name = os.path.join(rel_in_volume_dir, uploaded_file.filename).replace("\\", "/")
            # --- 关键修复区域结束 ---

            meta = {"k": k, "m": m, "shard_size": shard_size, "original_size": len(data), "sha256": file_sha}

            try:
                for i, disk in enumerate(disks[:k + m]):
                    # 拼接各盘下的 encoded/ + 相对路径 (rel_in_volume_dir)
                    enc_dir = os.path.join(disk, "encoded", rel_in_volume_dir)
                    os.makedirs(enc_dir, exist_ok=True)

                    # 分片名只使用文件名（不含EC卷内的目录结构）
                    base_filename = os.path.basename(uploaded_file.filename)

                    with open(os.path.join(enc_dir, f"{base_filename}.blk_{i}"), "wb") as f:
                        f.write(shards[i])

                    with open(os.path.join(enc_dir, f"{base_filename}.meta.json"), "w",
                              encoding="utf-8") as mf:
                        json.dump(meta, mf, ensure_ascii=False)
            except Exception as e:
                return jsonify({'error': f'写入分片失败: {e}'}), 500

            idx = _load_json(EC_IDX_PATH, {"files": {}})
            # 索引中存储的是 logical_name (EC卷内相对全路径)
            idx["files"][logical_name] = {"size": len(data), "k": k, "m": m, "sha256": file_sha, "disks": disks,
                                          "ctime": int(time.time())}
            _save_json(EC_IDX_PATH, idx)

        return jsonify({'success': True, 'message': f'{len(uploaded_files)}个文件已写入逻辑盘并完成RS编码'})

    # 普通目录：原样保存 (此部分逻辑在前端修正后已正确)
    else:
        try:
            # 1. 验证路径中是否包含盘符
            drive, _ = os.path.splitdrive(upload_path)
            if not drive:
                return jsonify({'error': '上传路径格式错误，缺少盘符'}), 400

            drive = drive.upper().replace('\\', '/')
            if not os.path.exists(drive):
                return jsonify({'error': f'磁盘 {drive} 不存在'}), 404

            # 2. 将前端路径直接转换为绝对路径，作为目标目录
            target_dir = os.path.abspath(upload_path)

            # 3. 安全检查：确保目标目录在我们期望的盘符下
            if not target_dir.upper().startswith(drive):
                return jsonify({'error': f'非法上传路径: {target_dir}'}), 403

            # 4. 创建目标目录
            os.makedirs(target_dir, exist_ok=True)

            for uploaded_file in uploaded_files:
                filename = uploaded_file.filename
                target_path = os.path.join(target_dir, filename)

                # 最终的安全检查
                if not os.path.abspath(target_path).upper().startswith(drive):
                    return jsonify({'error': f'非法的最终文件路径: {target_path}'}), 403

                uploaded_file.save(target_path)

            return jsonify({'success': True, 'message': f'{len(uploaded_files)}个文件上传成功'})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'处理上传时发生严重错误: {e}'}), 500


# ===== [最终修复 1/3] 重写 list_files 函数 =====
# ===== [最终修复 1/3] 重写 list_files 函数 =====
@app.route('/api/list', methods=['GET'])
@token_required()
def list_files():
    full_path_from_request = request.args.get('path', '/')
    keyword = request.args.get('q', '').strip().lower()

    # --- 分支 1: 处理纠删码卷 (此部分逻辑正确，无需修改) ---
    if _is_ec_volume(full_path_from_request):
        idx = _load_json(EC_IDX_PATH, {"files": {}})
        items, now_ts = [], int(time.time())

        norm_req_path = full_path_from_request.replace("\\", "/").strip("/")

        if norm_req_path == 'ec_volume':
            current_dir_prefix = ''
        else:
            current_dir_prefix = norm_req_path[len('ec_volume/'):] + '/'

        sub_items = set()
        for name, meta in idx.get("files", {}).items():
            if not name.startswith(current_dir_prefix):
                continue

            relative_to_current = name[len(current_dir_prefix):]
            parts = relative_to_current.split('/')

            if len(parts) == 1:
                items.append({
                    "name": parts[0], "is_dir": False, "size": meta.get("size", 0),
                    "mtime": meta.get("ctime", now_ts), "path": name
                })
            else:
                sub_items.add(parts[0])

        for dir_name in sub_items:
             items.append({
                "name": dir_name, "is_dir": True, "size": None,
                "mtime": now_ts, "path": current_dir_prefix + dir_name
            })

        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return jsonify({"success": True, "items": items})

    # --- 分支 2: 处理物理硬盘 (重构此部分逻辑) ---
    else:
        try:
            full_path = os.path.abspath(full_path_from_request)
            allowed = False
            drive_prefix = None
            for base_dir in get_available_drives():
                if full_path.upper().startswith(os.path.abspath(base_dir).upper()):
                    allowed = True
                    drive_prefix = base_dir
                    break
            if not allowed:
                return jsonify({'error': '非法路径或不允许访问的磁盘'}), 403
            if not os.path.exists(full_path) or not os.path.isdir(full_path):
                return jsonify({'error': f'路径不存在或不是文件夹: {full_path}'}), 404

            items = []
            # [关键修正] 计算相对于盘符根目录的路径
            relative_path_root = os.path.relpath(full_path, drive_prefix)
            if relative_path_root == '.':
                relative_path_root = ''

            for name in os.listdir(full_path):
                if keyword and keyword not in name.lower(): continue
                entry_full_path = os.path.join(full_path, name)
                stat = os.stat(entry_full_path)
                # [关键修正] 返回相对于盘符根目录的路径
                relative_path = os.path.join(relative_path_root, name).replace('\\', '/')
                items.append({
                    'name': name, 'is_dir': os.path.isdir(entry_full_path),
                    'size': stat.st_size if os.path.isfile(entry_full_path) else None,
                    'mtime': stat.st_mtime, 'path': relative_path
                })

            items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
            return jsonify({'success': True, 'items': items})
        except Exception as e:
            return jsonify({'error': f'读取目录失败: {str(e)}'}), 500

@app.route('/api/search')
@token_required()
def api_search():
    keyword = request.args.get('keyword', '').strip()
    scope = request.args.get('scope', 'current')
    base_path = request.args.get('path', '')

    if not keyword:
        return jsonify({'success': False, 'error': '关键词不能为空'}), 400

    results = []

    # 决定搜索路径
    try:
        if scope == 'all':
            from utils import get_disk_info
            search_dirs = [d['mount'] for d in get_disk_info()]
        else:
            if os.path.exists(base_path):
                search_dirs = [base_path]
            else:
                from common import BASE_DIRS
                search_dirs = [os.path.join(BASE_DIRS[0], base_path.strip('/'))]
    except Exception as e:
        return jsonify({'success': False, 'error': '目录解析失败'}), 500

    # 执行搜索
    try:
        for directory in search_dirs:
            if not os.path.exists(directory):
                continue
            for root, dirs, files in os.walk(directory):
                for fname in files:
                    if keyword.lower() in fname.lower():
                        full_path = os.path.join(root, fname)
                        results.append({
                            'name': fname,
                            'path': full_path,
                            'directory': os.path.dirname(full_path)
                        })
        return jsonify({'success': True, 'results': results})
    except Exception as e:
        return jsonify({'success': False, 'error': f'搜索失败: {str(e)}'}), 500


# 文件: app.py -> @app.route("/api/download", methods=["GET"])

@app.route("/api/download", methods=["GET"])
@token_required()
def api_download():
    file_path = request.args.get("path", "").strip()
    if not file_path:
        return jsonify({"error": "缺少 path 参数"}), 400

    # 1. 优先处理 EC 卷
    if _is_ec_volume(file_path):
        name = file_path.replace("\\", "/").strip("/").split("/", 1)[-1]
        if not name: return jsonify({"error": "无效的逻辑盘文件路径"}), 400
        idx = _load_json(EC_IDX_PATH, {"files": {}}).get("files", {})
        entry = idx.get(name)
        if not entry: return jsonify({"error": "文件不在逻辑盘索引中"}), 404
        k, m, disks = entry["k"], entry["m"], entry["disks"]
        shard_dict, meta = {}, None
        # ... (EC 逻辑保持不变) ...
        for i, disk in enumerate(disks[:k + m]):
            enc_dir = os.path.join(disk, "encoded", os.path.dirname(name))
            blk = os.path.join(enc_dir, f"{os.path.basename(name)}.blk_{i}")
            if os.path.exists(blk):
                with open(blk, "rb") as f: shard_dict[i] = f.read()
            if not meta:
                mj = os.path.join(enc_dir, f"{os.path.basename(name)}.meta.json")
                if os.path.exists(mj): meta = json.load(open(mj, "r", encoding="utf-8"))
        if not meta or len(shard_dict) < k: return jsonify({"error": "可用分片不足，无法恢复"}), 409
        try:
            data = _decode_from_dict(shard_dict, meta)
        except Exception as e:
            return jsonify({"error": f"解码失败: {e}"}), 500
        if hashlib.sha256(data).hexdigest() != meta.get("sha256"):
            return jsonify({"error": "数据完整性校验失败"}), 500
        return send_file(io.BytesIO(data), as_attachment=True, download_name=os.path.basename(name))

    # 2. 处理物理硬盘 (✅ 修复：使用 get_actual_file_path 统一路径解析和安全检查)
    else:
        try:
            from common import get_actual_file_path

            # 使用 get_actual_file_path 获取绝对路径。
            # 此函数会尝试在可用盘符中找到文件，并返回绝对路径。
            actual_path = get_actual_file_path(file_path)

            if not actual_path:
                return jsonify({"error": "文件不存在或路径无效"}), 404

            # 再次进行最终的安全检查，确保路径在 BASE_DIRS 范围内。
            from common import is_path_allowed
            if not is_path_allowed(actual_path):
                return jsonify({"error": "不允许访问该路径"}), 403

            if not os.path.exists(actual_path) or not os.path.isfile(actual_path):
                return jsonify({"error": "文件不存在或不是一个文件"}), 404

            return send_file(actual_path, as_attachment=True, download_name=os.path.basename(actual_path))
        except Exception as e:
            return jsonify({'error': f'下载文件时出错: {e}'}), 500

@app.route("/api/volume/rebuild/scan", methods=["POST"])
@token_required()
def ec_scan():
        cfg = _load_json(EC_CFG_PATH, {})
        if not cfg:
            return jsonify({"error": "未配置纠删码"}), 400
        idx = _load_json(EC_IDX_PATH, {"files": {}})
        detail, missing_total = {}, 0

        for name, meta in idx.get("files", {}).items():
            miss = []
            for i, disk in enumerate(meta["disks"][:meta["k"] + meta["m"]]):
                enc_dir = os.path.join(disk, "encoded", os.path.dirname(name))
                blk = os.path.join(enc_dir, f"{os.path.basename(name)}.blk_{i}")
                if not os.path.exists(blk):
                    miss.append(i)
            if miss:
                detail[name] = miss
                missing_total += len(miss)

        return jsonify({"success": True, "missing_total": missing_total, "detail": detail})

@app.route("/api/volume/rebuild/start", methods=["POST"])
@token_required()
def ec_rebuild():
            cfg = _load_json(EC_CFG_PATH, {})
            if not cfg:
                return jsonify({"error": "未配置纠删码"}), 400
            idx = _load_json(EC_IDX_PATH, {"files": {}})

            fixed = 0
            for name, meta in idx.get("files", {}).items():
                shard_dict, meta_j = {}, None
                for i, disk in enumerate(meta["disks"][:meta["k"] + meta["m"]]):
                    enc = os.path.join(disk, "encoded", os.path.dirname(name))
                    blk = os.path.join(enc, f"{os.path.basename(name)}.blk_{i}")
                    if os.path.exists(blk):
                        with open(blk, "rb") as f:
                            shard_dict[i] = f.read()
                    if not meta_j:
                        mj = os.path.join(enc, f"{os.path.basename(name)}.meta.json")
                        if os.path.exists(mj):
                            meta_j = json.load(open(mj, "r", encoding="utf-8"))
                if not meta_j or len(shard_dict) < meta["k"]:
                    continue

                try:
                    data = _decode_from_dict(shard_dict, meta_j)
                    new_shards = rs_encode(data, meta["k"], meta["m"])
                except Exception as e:
                    print(f"[EC] rebuild {name} failed:", e)
                    continue

                for i, disk in enumerate(meta["disks"][:meta["k"] + meta["m"]]):
                    enc = os.path.join(disk, "encoded", os.path.dirname(name))
                    blk = os.path.join(enc, f"{os.path.basename(name)}.blk_{i}")
                    if not os.path.exists(blk):
                        os.makedirs(enc, exist_ok=True)
                        with open(blk, "wb") as f:
                            f.write(new_shards[i])
                        with open(os.path.join(enc, f"{os.path.basename(name)}.meta.json"), "w",
                                  encoding="utf-8") as mf:
                            json.dump(meta_j, mf, ensure_ascii=False)
                        fixed += 1

            return jsonify({"success": True, "fixed": fixed})
        # ===== NGROK 配置 =====


NGROK_PATH = str(Path(__file__).with_name('ngrok.exe'))
FLASK_PORT = 5000

ngrok_url_global = None  # 👈 全局变量保存公网地址


def start_ngrok():
    """
    一个更健壮的 ngrok 启动函数。
    它会清理旧进程、轮询API状态，并在失败时提供调试信息。
    """
    global ngrok_url_global
    print("⚙️ 正在启动 ngrok...")

    # 确保 ngrok.exe 存在
    if not os.path.exists(NGROK_PATH):
        print(f"❌ ngrok.exe 未找到，路径: {NGROK_PATH}")
        print("💡 提示：ngrok 不是必需的，程序将在本地模式下运行")
        return None, None

    # 尝试终止已有的 ngrok 进程，避免冲突
    try:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/F', '/IM', 'ngrok.exe'], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(['killall', 'ngrok'], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("🧹 已清理旧的 ngrok 进程。")
    except Exception:
        pass # 忽略错误，因为可能没有旧进程在运行

    ngrok_proc = None
    try:
        # 启动 ngrok 进程
        ngrok_proc = subprocess.Popen(
            [NGROK_PATH, 'http', str(FLASK_PORT)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        ngrok_url = None
        # 等待 ngrok API 可用 (最多等待约15秒)
        for i in range(15):
            time.sleep(1)
            try:
                # 检查 ngrok 进程是否意外退出
                if ngrok_proc.poll() is not None:
                    print("❌ ngrok 进程意外终止。")
                    break

                # 尝试连接 ngrok 的本地 API
                r = requests.get('http://127.0.0.1:4040/api/tunnels', timeout=2)
                r.raise_for_status()
                data = r.json()

                # 解析 HTTPS 隧道地址
                for tunnel in data.get('tunnels', []):
                    if tunnel.get('proto') == 'https' and tunnel.get('public_url'):
                        ngrok_url = tunnel['public_url']
                        break
                if ngrok_url:
                    break
            except requests.exceptions.RequestException:
                if i < 14:
                    print(f"⏳ ngrok API 尚未就绪，正在重试... ({i+1}/15)")
                continue # API 还未就绪，继续等待
            except Exception as e:
                print(f"❌ 获取 ngrok 地址时出错: {e}")
                break

        if ngrok_url:
            print(f"✅ ngrok 公网地址: {ngrok_url}")
            ngrok_url_global = ngrok_url
            return ngrok_url, ngrok_proc
        else:
            print('❌ ngrok 启动失败，无法获取公网地址。')
            if ngrok_proc:
                print("--- ngrok 输出日志 ---")
                ngrok_proc.terminate() # 终止进程以释放资源
                try:
                    # 等待并获取所有输出
                    stdout, _ = ngrok_proc.communicate(timeout=5)
                    print(stdout if stdout else "(无输出)")
                except subprocess.TimeoutExpired:
                    print("(读取输出超时)")
                print("--------------------")
            return None, None

    except FileNotFoundError:
        print(f"❌ ngrok 启动失败: 未找到 ngrok.exe。请确保它位于 '{NGROK_PATH}'")
        return None, None
    except Exception as e:
        print(f'❌ ngrok 启动时发生严重错误: {e}')
        if ngrok_proc:
            ngrok_proc.terminate()
        return None, None
# ========== 你的 Flask 路由、逻辑在这里 ==========


# ===== 文档协作API =====
@app.route('/api/documents', methods=['GET'])
@token_required()
def get_documents():
    """获取用户可访问的文档列表"""
    db = get_db()
    user_id = g.user

    # 获取用户创建的文档
    created_docs = db.execute(
        "SELECT id, title, created_at, updated_at FROM collaborative_documents WHERE created_by = ? AND is_active = 1",
        (user_id,)
    ).fetchall()

    # 获取用户有权限的文档
    shared_docs = db.execute('''
        SELECT cd.id, cd.title, cd.created_at, cd.updated_at, dp.permission_type
        FROM collaborative_documents cd
        JOIN document_permissions dp ON cd.id = dp.document_id
        WHERE dp.user_id = ? AND cd.is_active = 1
    ''', (user_id,)).fetchall()

    documents = []
    for doc in created_docs:
        documents.append({
            'id': doc['id'],
            'title': doc['title'],
            'created_at': doc['created_at'],
            'updated_at': doc['updated_at'],
            'permission': 'owner'
        })

    for doc in shared_docs:
        documents.append({
            'id': doc['id'],
            'title': doc['title'],
            'created_at': doc['created_at'],
            'updated_at': doc['updated_at'],
            'permission': doc['permission_type']
        })

    return jsonify(documents)


@app.route("/api/volume/import", methods=["POST"])
@token_required()
def ec_import():
    """
    body:
    {
      "sources": ["/D:/data/foo.txt", "/D:/photos"],  # 文件或目录，支持多个
      "delete_source": false                          # 导入成功后是否删除源文件
    }
    """
    payload = request.get_json(force=True)
    sources = payload.get("sources") or []
    delete_src = bool(payload.get("delete_source", False))

    cfg = _load_json(EC_CFG_PATH, {})
    if not cfg or cfg.get("scheme") != "rs":
        return jsonify({"error": "未配置RS纠删码"}), 400
    k, m, disks = cfg["k"], cfg["m"], cfg["disks"]
    if len(disks) < k + m:
        return jsonify({"error": f"磁盘数量不足（需要≥{k+m}）"}), 400

    imported, skipped, failed = [], [], []
    idx = _load_json(EC_IDX_PATH, {"files": {}})

    def _import_one(file_abs: str, logical_rel: str):
        try:
            with open(file_abs, "rb") as f:
                data = f.read()
            shards = rs_encode(data, k, m)
            shard_size = len(shards[0]) if shards else 0
            meta = {
                "k": k, "m": m,
                "shard_size": shard_size,
                "original_size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            # 写分片
            for i, disk in enumerate(disks[:k+m]):
                enc_dir = os.path.join(disk, "encoded", os.path.dirname(logical_rel))
                os.makedirs(enc_dir, exist_ok=True)
                base = os.path.basename(logical_rel)
                with open(os.path.join(enc_dir, f"{base}.blk_{i}"), "wb") as wf:
                    wf.write(shards[i])
                with open(os.path.join(enc_dir, f"{base}.meta.json"), "w", encoding="utf-8") as mf:
                    json.dump(meta, mf, ensure_ascii=False)
            # 更新索引
            idx["files"][logical_rel.replace("\\", "/")] = {
                "size": len(data), "k": k, "m": m, "sha256": meta["sha256"],
                "disks": disks, "ctime": int(time.time())
            }
            imported.append(logical_rel)
            if delete_src:
                try: os.remove(file_abs)
                except Exception: pass
        except Exception as e:
            failed.append({"path": file_abs, "error": str(e)})

    for src in sources:
        src = os.path.abspath(src)
        if not os.path.exists(src):
            failed.append({"path": src, "error": "不存在"})
            continue
        if os.path.isdir(src):
            # 目录：递归导入
            root = src
            for root_dir, _, files in os.walk(root):
                for fn in files:
                    absf = os.path.join(root_dir, fn)
                    # 逻辑盘内的相对路径 = 以目录根为前缀的相对路径
                    rel = os.path.relpath(absf, root)
                    _import_one(absf, rel)
            if delete_src:
                try: os.removedirs(root)
                except Exception: pass
        else:
            # 文件：逻辑盘路径用文件名
            _import_one(src, os.path.basename(src))

    _save_json(EC_IDX_PATH, idx)
    return jsonify({"success": True, "imported": imported, "failed": failed, "skipped": skipped})


# app.py (添加新的路由)

# ======================================================
#                 加密驱动器 API
# ======================================================
@app.route('/api/encryption/status', methods=['GET'])
@token_required(admin_only=True)
def encryption_status():
    """获取加密驱动器的状态"""
    return jsonify({
        'is_configured': bool(encryption_manager.encrypted_drives),
        'is_unlocked': encryption_manager.is_unlocked,
        'encrypted_drives': list(encryption_manager.encrypted_drives)
    })


@app.route('/api/encryption/unlock', methods=['POST'])
@token_required(admin_only=True)
def encryption_unlock():
    """使用密码解锁加密驱动器"""
    data = request.get_json()
    password = data.get('password', '')
    if not password:
        return jsonify({'error': '需要提供密码'}), 400

    success = encryption_manager.unlock(password)
    if success:
        return jsonify({'success': True, 'message': '加密驱动器已解锁'})
    else:
        return jsonify({'error': '密码错误，解锁失败'}), 403


@app.route('/api/encryption/lock', methods=['POST'])
@token_required(admin_only=True)
def encryption_lock():
    """手动锁定加密驱动器"""
    encryption_manager.lock()
    return jsonify({'success': True, 'message': '加密驱动器已锁定'})


@app.route('/api/documents', methods=['POST'])
@token_required()
def create_document():
    """创建新文档"""
    data = request.get_json()
    title = data.get('title', '').strip()
    content = data.get('content', '')

    if not title:
        return jsonify({'error': '文档标题不能为空'}), 400

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO collaborative_documents (title, content, created_by) VALUES (?, ?, ?)",
            (title, content, g.user)
        )
        db.commit()

        doc_id = cur.lastrowid
        return jsonify({
            'success': True,
            'document_id': doc_id,
            'message': '文档创建成功'
        })
    except Exception as e:
        return jsonify({'error': f'创建文档失败: {str(e)}'}), 500


@app.route('/api/documents/<int:doc_id>', methods=['GET'])
@token_required()
def get_document(doc_id):
    """获取文档详情"""
    db = get_db()

    # 检查权限
    if not collaboration_manager.check_document_permission(doc_id, g.user, 'read'):
        return jsonify({'error': '没有访问权限'}), 403

    # 获取文档信息
    doc = db.execute(
        "SELECT * FROM collaborative_documents WHERE id = ? AND is_active = 1",
        (doc_id,)
    ).fetchone()

    if not doc:
        return jsonify({'error': '文档不存在'}), 404

    # 获取版本历史
    versions = db.execute(
        "SELECT * FROM document_versions WHERE document_id = ? ORDER BY version_number DESC LIMIT 10",
        (doc_id,)
    ).fetchall()

    return jsonify({
        'document': dict(doc),
        'versions': [dict(v) for v in versions]
    })


@app.route('/api/documents/<int:doc_id>/permissions', methods=['POST'])
@token_required()
def share_document(doc_id):
    """分享文档给其他用户"""
    data = request.get_json()
    username = data.get('username', '').strip()
    permission_type = data.get('permission_type', 'read')

    if not username:
        return jsonify({'error': '用户名不能为空'}), 400

    if permission_type not in ['read', 'write', 'admin']:
        return jsonify({'error': '无效的权限类型'}), 400

    db = get_db()

    # 检查是否是文档所有者
    doc = db.execute(
        "SELECT created_by FROM collaborative_documents WHERE id = ?",
        (doc_id,)
    ).fetchone()

    if not doc or doc['created_by'] != g.user:
        return jsonify({'error': '没有权限分享此文档'}), 403

    # 查找用户
    user = db.execute(
        "SELECT id FROM users WHERE username = ? AND is_active = 1",
        (username,)
    ).fetchone()

    if not user:
        return jsonify({'error': '用户不存在'}), 404

    # 添加权限
    try:
        db.execute(
            "INSERT OR REPLACE INTO document_permissions (document_id, user_id, permission_type) VALUES (?, ?, ?)",
            (doc_id, user['id'], permission_type)
        )
        db.commit()
        return jsonify({'success': True, 'message': '分享成功'})
    except Exception as e:
        return jsonify({'error': f'分享失败: {str(e)}'}), 500


@app.route('/api/documents/<int:doc_id>/versions', methods=['GET'])
@token_required()
def get_document_versions(doc_id):
    """获取文档版本历史"""
    db = get_db()

    # 检查权限
    if not collaboration_manager.check_document_permission(doc_id, g.user, 'read'):
        return jsonify({'error': '没有访问权限'}), 403

    versions = db.execute('''
        SELECT dv.*, u.username as author_name
        FROM document_versions dv
        JOIN users u ON dv.created_by = u.id
        WHERE dv.document_id = ?
        ORDER BY dv.version_number DESC
    ''', (doc_id,)).fetchall()

    return jsonify([dict(v) for v in versions])


@app.route('/api/documents/<int:doc_id>/versions/<int:version_id>', methods=['GET'])
@token_required()
def get_document_version(doc_id, version_id):
    """获取特定版本的文档内容"""
    db = get_db()

    # 检查权限
    if not collaboration_manager.check_document_permission(doc_id, g.user, 'read'):
        return jsonify({'error': '没有访问权限'}), 403

    version = db.execute(
        "SELECT * FROM document_versions WHERE document_id = ? AND id = ?",
        (doc_id, version_id)
    ).fetchone()

    if not version:
        return jsonify({'error': '版本不存在'}), 404

    return jsonify(dict(version))


# ===== 协作编辑API =====
import os


@app.route('/api/collab/load')
def collab_load():
    file = request.args.get('file', '').strip()
    path = request.args.get('path', '').strip()
    # 修正 path 为根目录时的情况
    if path in ('', '/'): path = ''
    if not file:
        return jsonify({'success': False, 'error': '缺少文件名'}), 400
    # 只允许在BASE_DIRS[0]及其子目录下操作
    full_path = os.path.abspath(os.path.join(BASE_DIRS[0], path, file))
    if not full_path.startswith(os.path.abspath(BASE_DIRS[0])):
        return jsonify({'success': False, 'error': '非法路径'}), 403
    if not os.path.exists(full_path):
        return jsonify({'success': False, 'error': '文件不存在'}), 404
    try:
        if file.lower().endswith('.docx'):
            doc = Document(full_path)
            content = '\n'.join([p.text for p in doc.paragraphs])
        else:
            # 尝试多种编码方式读取文件
            encodings = ['utf-8', 'utf-16', 'utf-16le', 'utf-16be', 'gbk', 'gb2312', 'latin1']
            content = None

            for encoding in encodings:
                try:
                    with open(full_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
                except Exception as e:
                    continue

            if content is None:
                # 如果所有编码都失败，尝试二进制读取并解码
                try:
                    with open(full_path, 'rb') as f:
                        raw_content = f.read()

                    # 尝试检测UTF-16 BOM
                    if raw_content.startswith(b'\xff\xfe'):
                        content = raw_content.decode('utf-16le')
                    elif raw_content.startswith(b'\xfe\xff'):
                        content = raw_content.decode('utf-16be')
                    elif raw_content.startswith(b'\xef\xbb\xbf'):
                        content = raw_content.decode('utf-8')
                    else:
                        # 最后尝试用 latin1 编码（不会抛出异常）
                        content = raw_content.decode('latin1')
                except Exception as e:
                    return jsonify({'success': False, 'error': f'无法读取文件，编码问题: {str(e)}'}), 500

        # 检查内容长度，如果太长则截断
        max_length = 1024 * 1024  # 1MB
        if len(content) > max_length:
            content = content[:max_length] + f'\n\n... (文件过长，已截断，总长度: {len(content)} 字符)'

        return jsonify({'success': True, 'content': content})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/collab/save', methods=['POST'])
@token_required()
def collab_save():
    data = request.get_json()
    file = data.get('file', '').strip()
    path = data.get('path', '').strip()
    content = data.get('content', '')
    if not file:
        return jsonify({'success': False, 'error': '缺少文件名'}), 400
    full_path = os.path.abspath(os.path.join(BASE_DIRS[0], path, file))
    if not full_path.startswith(os.path.abspath(BASE_DIRS[0])):
        return jsonify({'success': False, 'error': '非法路径'}), 403
    try:
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# 协作分享链接表（可用sqlite或内存，先用内存实现）
collab_shares = {}


@app.route('/api/collab/share', methods=['POST'])
def collab_share():
    data = request.get_json()
    file = data.get('file', '').strip()
    path = data.get('path', '').strip()
    password = data.get('password', '').strip()
    expire_hours = int(data.get('expire', 24))
    if not file:
        return jsonify({'success': False, 'error': '缺少文件名'}), 400
    token = secrets.token_urlsafe(16)
    expire_at = datetime.utcnow() + timedelta(hours=expire_hours)
    collab_shares[token] = {
        'file': file,
        'path': path,
        'password': password,
        'expire_at': expire_at
    }
    share_url = f'/collab-edit.html?token={token}'
    return jsonify({'success': True, 'token': token, 'share_url': share_url, 'expire_at': expire_at.isoformat()})


@app.route('/api/collab/validate', methods=['POST'])
def collab_validate():
    data = request.get_json()
    token = data.get('token', '').strip()
    password = data.get('password', '').strip()
    info = collab_shares.get(token)
    if not info:
        return jsonify({'success': False, 'error': '无效token'}), 400
    if info['expire_at'] < datetime.utcnow():
        return jsonify({'success': False, 'error': '链接已过期'}), 403
    if info['password'] and info['password'] != password:
        return jsonify({'success': False, 'error': '密码错误'}), 403
    return jsonify({'success': True, 'file': info['file'], 'path': info['path']})


@app.route('/collab-edit.html')
def collab_edit_page():
    return app.send_static_file('collab-edit.html')


# ===== OnlyOffice API =====
@app.route('/api/onlyoffice/documents', methods=['GET'])
@token_required()
def get_onlyoffice_documents():
    """获取OnlyOffice文档列表"""
    documents = onlyoffice_manager.get_user_documents(g.user)
    return jsonify(documents)


@app.route('/api/onlyoffice/documents', methods=['POST'])
@token_required()
def create_onlyoffice_document():
    """创建OnlyOffice文档"""
    data = request.get_json()
    file_name = data.get('file_name', '').strip()
    file_type = data.get('file_type', '').strip()
    file_path = data.get('file_path', '').strip()  # 新增：支持从现有文件路径创建

    if not file_name or not file_type:
        return jsonify({'error': '文件名和类型不能为空'}), 400

    # 如果提供了文件路径，使用现有文件；否则创建新文件
    if file_path:
        # 检查文件是否存在
        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 404

        # 复制文件到 OnlyOffice 存储目录
        import shutil
        import time
        timestamp = int(time.time())
        new_file_path = f"{timestamp}_{file_name}"
        onlyoffice_file_path = os.path.join(onlyoffice_manager.storage_path, new_file_path)

        try:
            shutil.copy2(file_path, onlyoffice_file_path)
        except Exception as e:
            return jsonify({'error': f'复制文件失败: {str(e)}'}), 500

        # 创建文档记录
        doc_id = onlyoffice_manager.create_document(file_name, new_file_path, file_type, g.user)
    else:
        # 生成新文件路径
        file_path = f"{int(time.time())}_{file_name}"
        # 创建文档记录
        doc_id = onlyoffice_manager.create_document(file_name, file_path, file_type, g.user)

    if doc_id:
        return jsonify({'success': True, 'document': {'id': doc_id}})
    else:
        return jsonify({'error': '创建文档失败'}), 500


@app.route('/api/onlyoffice/upload', methods=['POST'])
@token_required()
def upload_onlyoffice_document():
    """上传文档到OnlyOffice"""
    if 'file' not in request.files:
        return jsonify({"error": "没有检测到上传文件"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "未选择文件"}), 400

    success, result = onlyoffice_manager.upload_document(file, g.user)
    if not success:
        return jsonify({"error": result}), 400

    # 当success为True时，result是一个字典
    if isinstance(result, dict):
        return jsonify({"success": True, "doc_id": result.get("doc_id"), "filename": result.get("filename")})
    else:
        return jsonify({"error": "上传结果格式错误"}), 500


@app.route('/api/onlyoffice/formats', methods=['GET'])
@token_required()
def get_supported_formats():
    """获取支持的文件格式"""
    formats = onlyoffice_manager.get_supported_formats()
    return jsonify(formats)


@app.route('/api/onlyoffice/documents/<int:doc_id>/config', methods=['GET'])
@token_required()
def get_onlyoffice_config(doc_id):
    """获取OnlyOffice编辑器配置"""
    action = request.args.get('action', 'edit')
    config = onlyoffice_manager.get_document_config(doc_id, g.user, action)

    if config:
        return jsonify(config)
    else:
        return jsonify({'error': '获取配置失败'}), 404


@app.route('/api/onlyoffice/documents/<int:doc_id>/share', methods=['POST'])
@token_required()
def share_onlyoffice_document(doc_id):
    """分享OnlyOffice文档"""
    data = request.get_json()
    username = data.get('username', '').strip()
    permission_type = data.get('permission_type', 'read')

    if not username:
        return jsonify({'error': '用户名不能为空'}), 400

    success, message = onlyoffice_manager.share_document(doc_id, username, permission_type)

    if success:
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'error': message}), 400


@app.route('/api/onlyoffice/download/<int:doc_id>')
@token_required()
def download_onlyoffice_document(doc_id):
    """下载OnlyOffice文档"""
    db = get_db()
    cur = db.execute("SELECT file_path FROM onlyoffice_documents WHERE id=?", (doc_id,))
    doc = cur.fetchone()

    if not doc:
        return jsonify({'error': '文档不存在'}), 404

    # 检查权限
    if not onlyoffice_manager.check_document_permission(doc_id, g.user, 'read'):
        return jsonify({'error': '没有访问权限'}), 403

    file_path = os.path.join(onlyoffice_manager.storage_path, doc['file_path'])

    if not os.path.exists(file_path):
        return jsonify({'error': '文件不存在'}), 404

    return send_file(file_path, as_attachment=True)


@app.route('/api/onlyoffice/callback', methods=['POST'])
def onlyoffice_callback():
    """OnlyOffice回调处理"""
    data = request.get_json()

    if not data:
        return jsonify({'error': '无效的请求数据'}), 400

    status = data.get('status')
    url = data.get('url')
    key = data.get('key')

    if status == 2:  # 文档已保存
        # 从key中提取文档ID
        # 这里需要根据你的key生成规则来解析
        doc_id = int(key.split('_')[1]) if '_' in key else None

        if doc_id and url:
            success = onlyoffice_manager.save_document(doc_id, url)
            if success:
                return jsonify({'error': 0})
            else:
                return jsonify({'error': 1})

    return jsonify({'error': 0})


@app.route('/onlyoffice-edit.html')
def onlyoffice_edit_page():
    return app.send_static_file('onlyoffice-edit.html')


# ===== 新协作系统 API =====
@app.route('/api/collaboration/create', methods=['POST'])
@token_required()
def create_collaboration_session():
    """创建协作会话"""
    data = request.get_json()
    file_path = data.get('file_path', '').strip()
    file_name = data.get('file_name', '').strip()
    expire_hours = data.get('expire_hours', 24)

    if not file_path or not file_name:
        return jsonify({'error': '文件路径和文件名不能为空'}), 400

    result = collaboration_v2.create_collaboration_session(
        file_path, file_name, g.user, expire_hours
    )

    if result:
        return jsonify({'success': True, 'session': result})
    else:
        return jsonify({'error': '创建协作会话失败'}), 500


@app.route('/api/collaboration/sessions', methods=['GET'])
@token_required()
def get_collaboration_sessions():
    """获取用户的协作会话"""
    created_sessions = collaboration_v2.get_user_sessions(g.user)
    participating_sessions = collaboration_v2.get_participating_sessions(g.user)

    return jsonify({
        'created': created_sessions,
        'participating': participating_sessions
    })


@app.route('/api/collaboration/join', methods=['POST'])
@token_required()
def join_collaboration_session():
    data = request.get_json()
    session_token = data.get('session_token', '').strip()
    if not session_token:
        return jsonify({'error': '会话令牌不能为空'}), 400

    # 关键修正：查询用户名
    db = get_db()
    row = db.execute("SELECT username FROM users WHERE id=?", (g.user,)).fetchone()
    username = row['username'] if row else str(g.user)

    success, message = collaboration_v2.join_session(session_token, g.user, username)
    return jsonify({'success': True, 'message': message}) if success else (jsonify({'error': message}), 400)



@app.route('/api/collaboration/session/<token>', methods=['GET'])
def get_session_info(token):
    """获取会话信息（无需登录）"""
    session_info = collaboration_v2.get_session_info(token)

    if session_info:
        return jsonify({'success': True, 'session': session_info})
    else:
        return jsonify({'error': '会话不存在或已过期'}), 404


@app.route('/api/collaboration/close/<int:session_id>', methods=['POST'])
@token_required()
def close_collaboration_session(session_id):
    """关闭协作会话"""
    success, message = collaboration_v2.close_session(session_id, g.user)

    if success:
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'error': message}), 400


@app.route('/collaboration.html')
def collaboration_page():
    return app.send_static_file('collaboration.html')


# ========== 创建预览会话API ==========
@app.route('/api/create-preview-session', methods=['POST'])
@token_required()
def create_preview_session():
    try:
        data = request.get_json()
        print(f"[DEBUG] 创建预览会话请求: {data}")

        file_path = data.get('file_path')
        file_type = data.get('file_type', 'pdf')

        if not file_path:
            return jsonify({'error': '缺少文件路径'}), 400

        print(f"[DEBUG] 处理文件: {file_path}, 类型: {file_type}, 用户: {g.user}")

        # 验证文件存在
        from common import get_actual_file_path
        actual_path = get_actual_file_path(file_path)

        print(f"[DEBUG] 解析后的实际路径: {actual_path}")

        if not actual_path or not os.path.exists(actual_path):
            print(f"[DEBUG] 文件不存在: {actual_path}")
            return jsonify({'error': '文件不存在'}), 404

        if not os.path.isfile(actual_path):
            print(f"[DEBUG] 不是文件: {actual_path}")
            return jsonify({'error': '不是文件'}), 400

        # 检查文件类型
        if file_type == 'pdf':
            ext = os.path.splitext(actual_path)[1].lower()
            if ext != '.pdf':
                print(f"[DEBUG] 文件类型不匹配: {ext}")
                return jsonify({'error': '文件类型不是PDF'}), 400

        # 创建临时会话
        session_id = secrets.token_urlsafe(32)
        session_data = {
            'file_path': actual_path,
            'file_type': file_type,
            'user_id': g.user,
            'created_at': datetime.now(),
            'expires_at': datetime.now() + timedelta(hours=2),  # 2小时过期
            'access_count': 0,
            'max_access': 100  # 最多访问100次
        }

        preview_sessions[session_id] = session_data

        print(f"[DEBUG] 创建预览会话成功: {session_id}")
        print(f"[DEBUG] 会话数据: 文件={actual_path}, 过期时间={session_data['expires_at']}")

        return jsonify({
            'success': True,
            'session_id': session_id,
            'expires_at': session_data['expires_at'].isoformat(),
            'message': f'预览会话创建成功，文件: {os.path.basename(actual_path)}'
        })

    except Exception as e:
        print(f"[DEBUG] 创建预览会话异常: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'创建预览会话失败: {str(e)}'}), 500


# ========== 预览会话访问API ==========
@app.route('/api/preview-session/<session_id>')
def access_preview_session(session_id):
    print(f"[DEBUG] 访问预览会话: {session_id}")

    # 检查会话是否存在
    if session_id not in preview_sessions:
        print(f"[DEBUG] 预览会话不存在: {session_id}")
        print(f"[DEBUG] 当前存在的会话: {list(preview_sessions.keys())}")
        return jsonify({'error': '预览会话不存在或已过期'}), 404

    session_data = preview_sessions[session_id]

    # 检查是否过期
    if datetime.now() > session_data['expires_at']:
        print(f"[DEBUG] 预览会话已过期: {session_id}, 过期时间: {session_data['expires_at']}")
        del preview_sessions[session_id]
        return jsonify({'error': '预览会话已过期'}), 403

    # 检查访问次数限制
    if session_data['access_count'] >= session_data['max_access']:
        print(f"[DEBUG] 预览会话访问次数超限: {session_id}, 当前访问次数: {session_data['access_count']}")
        return jsonify({'error': '访问次数已达上限'}), 403

    # 更新访问次数
    session_data['access_count'] += 1

    file_path = session_data['file_path']

    print(f"[DEBUG] 预览会话访问: {session_id}, 文件: {file_path}, 第{session_data['access_count']}次访问")

    try:
        # 返回PDF文件
        if session_data['file_type'] == 'pdf':
            if not os.path.exists(file_path):
                print(f"[DEBUG] 会话文件不存在: {file_path}")
                return jsonify({'error': '文件不存在'}), 404

            response = send_file(file_path, mimetype='application/pdf')
            response.headers['Content-Disposition'] = 'inline'

            # 添加缓存和CORS头
            response.headers['Cache-Control'] = 'public, max-age=3600'
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET'
            response.headers['Access-Control-Allow-Headers'] = 'Authorization'

            print(f"[DEBUG] 预览会话文件发送成功: {session_id}")
            return response
        else:
            print(f"[DEBUG] 不支持的文件类型: {session_data['file_type']}")
            return jsonify({'error': '不支持的文件类型'}), 400

    except Exception as e:
        print(f"[DEBUG] 预览会话文件访问失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': '文件访问失败'}), 500


# ========== 定期清理过期会话 ==========
def cleanup_expired_sessions():
    """清理过期的预览会话"""
    current_time = datetime.now()
    expired_sessions = []

    for session_id, session_data in preview_sessions.items():
        if current_time > session_data['expires_at']:
            expired_sessions.append(session_id)

    for session_id in expired_sessions:
        del preview_sessions[session_id]
        print(f"[DEBUG] 清理过期会话: {session_id}")

    if expired_sessions:
        print(f"[DEBUG] 清理了 {len(expired_sessions)} 个过期会话")

    print(f"[DEBUG] 当前活跃会话数: {len(preview_sessions)}")


# ========== 后台清理任务 ==========
def background_cleanup():
    """后台清理任务"""
    print("[DEBUG] 启动预览会话后台清理任务")
    while True:
        try:
            cleanup_expired_sessions()
            time.sleep(300)  # 每5分钟清理一次
        except Exception as e:
            print(f"[DEBUG] 后台清理任务异常: {e}")
            time.sleep(60)  # 出错后等待1分钟再重试


# ========== 启动后台清理线程 ==========
def start_cleanup_thread():
    """启动后台清理线程"""
    try:
        cleanup_thread = threading.Thread(target=background_cleanup, daemon=True)
        cleanup_thread.start()
        print("[DEBUG] 预览会话清理线程启动成功")
    except Exception as e:
        print(f"[DEBUG] 启动清理线程失败: {e}")


# 在应用启动时调用
start_cleanup_thread()
# ===== 注册文件管理蓝图 =====
from filemanager import file_bp

app.register_blueprint(file_bp)

# ===== 主启动入口 =====
if __name__ == '__main__':
    # 数据库初始化已在文件顶部完成，无需再次调用
    print("✅ 数据库初始化完成。") # 只是打印信息，实际初始化已完成

    print("🚀 正在启动文件管理系统...")

    ngrok_url, ngrok_proc = None, None  # Initialize ngrok variables
    try:
        # 启动 ngrok（如果启用）
        ngrok_url, ngrok_proc = start_ngrok() # 假设 start_ngrok() 函数已定义并返回 ngrok_url, ngrok_proc

        print(f"📍 Flask 服务器启动在端口: {FLASK_PORT}")
        print("=" * 50)
        if ngrok_url:
            print(f"🌐 外网访问地址: {ngrok_url}")
        print(f"🏠 本地访问地址: http://localhost:{FLASK_PORT}")
        # 注意: 局域网访问地址需要用户手动替换 '您的IP地址'
        print(f"🔗 局域网访问地址: http://您的IP地址:{FLASK_PORT}")
        print("=" * 50)

        # 启动 SocketIO 服务器
        socketio.run(app, host='0.0.0.0', port=FLASK_PORT, debug=False)

    except KeyboardInterrupt:
        print("\n👋 程序正在退出...")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
    finally:
        if ngrok_proc:
            print("🛑 正在关闭 ngrok...")
            ngrok_proc.terminate()
            print("✅ ngrok 已关闭。")
        print("✅ 程序已退出。")