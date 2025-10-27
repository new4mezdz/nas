# ===== Standard Library =====
import os
import io
import json
import time
import secrets
import psutil, requests, threading, time
import subprocess
import mimetypes
from pathlib import Path
from functools import wraps
from datetime import datetime, timedelta
import hashlib
import ctypes  # 添加这行
import sys     # 添加这行（如果已有就不用添加）
# ===== Third-Party =====
from flask import Flask, request, jsonify, send_file, send_from_directory, g, make_response
# ... (在 import hashlib 之后)
from flask import session             # 导入 Flask session
from auth import init_auth          # 导入我们新的 auth.py
from permission_decorator import permission_required # 导入我们新的权限装饰器
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
init_auth(app)  # 注册来自 auth.py 的 /api/login, /api/logout 路由

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

# ===== 管理端配置 =====
NAS_CENTER_API_URL = "http://127.0.0.1:8080"  # 管理端地址
NAS_SHARED_SECRET = "your-shared-secret-key"   # 共享密钥(需与管理端一致)

# [✅ 新增] 管理端公网URL和本节点ID (请根据您的实际情况修改)
NAS_CENTER_PUBLIC_URL = None # ‼️ 将在启动时从管理端动态获取
THIS_NODE_ID = "node-5"                     # ‼️ 替换为本节点的唯一ID

# backend/app.py (客户端)

import jwt

# 在文件开头添加 (与管理端保持一致)
ACCESS_TOKEN_SECRET = 'your-access-token-secret-key'

# ===== 权限检查函数 =====
def is_admin():
    """检查是否有管理员权限"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin(script_path):
    """以管理员权限重启程序"""
    try:
        if sys.platform == 'win32':
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, script_path, None, 1
            )
            return True
    except:
        return False
    return False

@app.route('/api/verify-access-token', methods=['POST'])
def verify_access_token():
    """验证来自管理端的访问令牌"""
    print("[DEBUG] ========== 开始验证访问令牌 ==========")

    try:
        # 1. 获取请求数据
        data = request.json
        print(f"[DEBUG] 请求数据: {data}")

        token = data.get('token') if data else None
        print(f"[DEBUG] Token: {token[:50] if token else 'None'}...")

        if not token:
            print("[DEBUG] ❌ 错误: 缺少令牌")
            return jsonify({'success': False, 'error': '缺少令牌'}), 400

        # 2. 使用 ACCESS_TOKEN_SECRET 解码令牌 (管理端生成的)
        print(f"[DEBUG] 使用密钥解码令牌: ACCESS_TOKEN_SECRET")
        payload = jwt.decode(token, ACCESS_TOKEN_SECRET, algorithms=['HS256'])
        print(f"[DEBUG] ✅ 解码成功! Payload: {payload}")

        # 3. 提取用户信息
        user_id = payload.get('user_id')
        username = payload.get('username')
        role = payload.get('role', 'user')
        file_permission = payload.get('file_permission', 'readonly')

        print(f"[DEBUG] 用户信息: ID={user_id}, 用户名={username}, 角色={role}, 权限={file_permission}")

        if not username:
            print("[DEBUG] ❌ 错误: 令牌中缺少用户信息")
            return jsonify({'success': False, 'error': '令牌中缺少用户信息'}), 401

        # ✅ 将 role 转换为 is_admin (兼容前端)
        is_admin = (role == 'admin')

        # 4. 生成新的长期 token (用于客户端本地存储)
        print("[DEBUG] 生成新的长期 token...")
        new_token = jwt.encode({
            'user_id': user_id,
            'username': username,
            'role': role,
            'file_permission': file_permission,
            'is_admin': is_admin,  # ✅ 添加 is_admin 字段
            'exp': datetime.utcnow() + timedelta(days=7)
        }, app.config['SECRET_KEY'], algorithm='HS256')
        print(f"[DEBUG] ✅ 新 token 生成成功: {new_token[:50]}...")

        # 5. 返回结果
        result = {
            'success': True,
            'user': {
                'id': user_id,
                'username': username,
                'role': role,
                'file_permission': file_permission,
                'is_admin': is_admin  # ✅ 前端需要这个字段
            },
            'token': new_token
        }
        print(f"[DEBUG] ✅ 验证成功! 返回结果: {result}")
        print("[DEBUG] ========== 验证完成 ==========")
        return jsonify(result)

    except jwt.ExpiredSignatureError:
        print("[DEBUG] ❌ 错误: Token 已过期")
        return jsonify({'success': False, 'error': 'Token 已过期'}), 401
    except jwt.InvalidTokenError as e:
        print(f"[DEBUG] ❌ 错误: 令牌无效 - {str(e)}")
        return jsonify({'success': False, 'error': f'令牌无效: {str(e)}'}), 401
    except Exception as e:
        print(f"[DEBUG] ❌ 异常: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'验证失败: {str(e)}'}), 400


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


def verify_user_permission_from_center(username):
    """
    向管理端查询用户权限
    返回: {'file_permission': 'readonly', 'role': 'user'} 或 None
    """
    try:
        response = requests.post(
            f"{NAS_CENTER_API_URL}/api/internal/get-user-permission",
            json={'username': username},
            headers={'X-NAS-Secret': NAS_SHARED_SECRET},
            timeout=3
        )

        if response.status_code == 200:
            data = response.json()
            return {
                'file_permission': data.get('file_permission', 'readonly'),
                'role': data.get('role', 'user')
            }
        return None
    except Exception as e:
        print(f"[ERROR] 向管理端查询权限失败: {e}")
        return None



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



# ===== 静态页面路由 =====
@app.route("/")
def index():
    static_folder = app.static_folder or 'static'
    # [✅ 修改] 创建响应对象
    response = make_response(send_from_directory(static_folder, "desktop.html"))
    # [✅ 新增] 添加禁止缓存的头部
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route("/desktop")
def desktop_page():
    """管理端跳转入口 - 显示桌面页面"""
    static_folder = app.static_folder or 'static'
    # [✅ 修改] 创建响应对象
    response = make_response(send_from_directory(static_folder, "desktop.html"))
    # [✅ 新增] 添加禁止缓存的头部
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


# 在文件末尾 if __name__ == '__main__': 之前添加

# ========== NAS Center 集成接口 ==========

@app.route('/api/node-info', methods=['GET'])
def get_node_info():
    """返回节点基本信息 - 供 NAS Center 调用"""
    return jsonify({
        'id': 'node-5',
        'name': '我的本地节点',
        'ip': '127.0.0.1',
        'port': 5000,
        'status': 'online',
        'version': '1.0.0'
    })


@app.route('/api/sso-login', methods=['POST'])
def sso_login():
    """使用SSO令牌登录"""
    data = request.json
    sso_token = data.get('sso_token')

    try:
        # 验证SSO令牌
        payload = jwt.decode(sso_token, app.config['SECRET_KEY'], algorithms=['HS256'])

        if payload.get('type') != 'sso_access':
            return jsonify({'error': '无效的令牌类型'}), 401

        username = payload.get('username')

        # 查找或创建用户
        user = User.query.filter_by(username=username).first()
        if not user:
            # 如果用户不存在,可以选择:
            # 1. 自动创建用户(推荐)
            user = User(username=username, is_admin=False)
            user.set_password(secrets.token_urlsafe(32))  # 随机密码
            db.session.add(user)
            db.session.commit()
            # 2. 或者返回错误
            # return jsonify({'error': '用户不存在'}), 404

        # 生成正式token
        regular_token = jwt.encode({
            'user_id': user.id,
            'username': user.username,
            'exp': datetime.utcnow() + timedelta(hours=24)
        }, app.config['SECRET_KEY'], algorithm='HS256')

        return jsonify({
            'user': {
                'username': user.username,
                'is_admin': user.is_admin,
                'file_permission': user.file_permission
            },
            'token': regular_token
        })

    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'SSO令牌已过期'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': '无效的SSO令牌'}), 401


@app.route('/api/system-stats', methods=['GET'])
def get_system_stats():
    """返回系统统计信息 - 供 NAS Center 调用"""
    try:
        from utils import get_sys_info, get_disk_info
        import psutil

        # 获取系统信息
        sys_info = get_sys_info()
        disk_info = get_disk_info()

        # 计算磁盘总量和使用量
        total_gb = 0
        used_gb = 0
        for disk in disk_info:
            if disk.get('mount', '').upper() not in ['C:/', '/']:
                total = disk.get('bytes_total', 0) or disk.get('total', 0)
                used = disk.get('bytes_used', 0) or disk.get('used', 0)
                total_gb += total / (1024 ** 3)
                used_gb += used / (1024 ** 3)
        disk_percent = round((used_gb / total_gb * 100) if total_gb > 0 else 0, 2)

        # 获取硬件数据
        cpu_temp = 0
        cpu_freq = 0
        cpu_power = 0
        network_download = 0
        network_upload = 0

        try:
            hw_data = hardware_monitor.get_hardware_data()

            # CPU温度 - 找 CPU Package
            if hw_data and 'temperatures' in hw_data:
                for temp_sensor in hw_data['temperatures']:
                    if temp_sensor.get('name') == 'CPU Package':
                        cpu_temp = temp_sensor.get('value', 0)
                        break

            # CPU功耗
            if hw_data and 'powers' in hw_data:
                for power in hw_data['powers']:
                    if power.get('name') == 'CPU Package':
                        cpu_power = round(power.get('value', 0), 1)
                        break

            # CPU频率 - 从 clocks 获取第一个核心频率
            if hw_data and 'clocks' in hw_data:
                for clock in hw_data['clocks']:
                    if 'CPU Core #1' in clock.get('name', ''):
                        cpu_freq = round(clock['value'] / 1000, 2)  # MHz 转 GHz
                        break

            # 网络带宽
            net_io_start = psutil.net_io_counters()
            time.sleep(0.5)
            net_io_end = psutil.net_io_counters()
            network_download = round((net_io_end.bytes_recv - net_io_start.bytes_recv) / 1024 / 1024 / 0.5, 2)
            network_upload = round((net_io_end.bytes_sent - net_io_start.bytes_sent) / 1024 / 1024 / 0.5, 2)

        except Exception as hw_error:
            print(f"[WARNING] 获取硬件信息失败: {hw_error}")

        return jsonify({
            'cpu_percent': sys_info.get('cpu_percent', 0),
            'memory_percent': sys_info.get('mem_percent', 0),
            'disk_percent': disk_percent,
            'disk_total_gb': round(total_gb, 2),
            'disk_used_gb': round(used_gb, 2),
            'disk_free_gb': round(total_gb - used_gb, 2),
            'cpu_temp_celsius': cpu_temp,
            'cpu_freq': cpu_freq,
            'cpu_power': cpu_power,
            'network_download': network_download,
            'network_upload': network_upload,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        print(f"[ERROR] 获取系统统计失败: {e}")
        return jsonify({
            'cpu_percent': 0,
            'memory_percent': 0,
            'disk_percent': 0,
            'disk_total_gb': 0,
            'disk_used_gb': 0,
            'disk_free_gb': 0,
            'cpu_temp_celsius': 0,
            'cpu_freq': 0,
            'cpu_power': 0,
            'network_download': 0,
            'network_upload': 0,
            'error': str(e)
        }), 500



@app.route('/api/hardware-data', methods=['GET'])
def get_hardware_data():
    """返回硬件监控详细数据"""
    try:
        hw_data = hardware_monitor.get_hardware_data()
        return jsonify(hw_data)
    except Exception as e:
        print(f"[ERROR] 获取硬件数据失败: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/disks', methods=['GET'])
def get_disks_info():
    """返回详细磁盘信息 - 供 NAS Center 调用"""
    try:
        from utils import get_disk_info

        # 获取所有磁盘信息
        all_disks = get_disk_info()

        # 过滤并格式化数据
        formatted_disks = []
        for disk in all_disks:
            mount = disk.get('mount', '').upper().replace('\\', '/')

            # 排除系统盘
            if mount in ['C:/', '/']:
                continue

            total = disk.get('bytes_total', 0) or disk.get('total', 0)
            used = disk.get('bytes_used', 0) or disk.get('used', 0)
            free = disk.get('bytes_free', 0) or disk.get('free', 0)

            formatted_disks.append({
                'mount': disk.get('mount', ''),
                'total_gb': round(total / (1024 ** 3), 2),
                'used_gb': round(used / (1024 ** 3), 2),
                'free_gb': round(free / (1024 ** 3), 2),
                'usage_percent': round((used / total * 100) if total > 0 else 0, 2),
                'filesystem': disk.get('fstype', 'unknown'),
                'device': disk.get('device', 'unknown')
            })

        return jsonify(formatted_disks)

    except Exception as e:
        print(f"[ERROR] 获取磁盘信息失败: {e}")
        return jsonify({'error': str(e)}), 500




# [新增] EC容量预估接口
@app.route("/api/ec_estimate", methods=["POST"])
@permission_required('fullcontrol')
def api_ec_estimate():
    """根据传入的k值和磁盘列表，实时估算可用容量"""
    data = request.get_json()
    k = int(data.get("k", 0))
    disks = data.get("disks", [])

    if k <= 0 or not disks:
        return jsonify({"error": "缺少 k 或 disks 参数"}), 400

    try:
        # 复用已有的 _capacity_estimate 帮助函数
        estimate = _capacity_estimate(disks, k)
        return jsonify(estimate)
    except Exception as e:
        return jsonify({"error": f"计算容量失败: {str(e)}"}), 500









# ===== 系统/磁盘信息接口 =====
from utils import get_sys_info, get_disk_info
import shutil

# 在文件顶部添加导入
from hardware_monitor import hardware_monitor


# 修改 /api/system 路由
# 文件: 客户端 app.py

@app.route('/api/system', methods=['GET'])
@permission_required('readonly')
def get_system():
    """返回系统信息 (供前端调用)"""
    try:
        import psutil

        sys_info = get_sys_info()
        hw_data = hardware_monitor.get_hardware_data()

        # CPU功耗 - 从powers列表获取
        cpu_power = 0
        for power in hw_data.get('powers', []):
            if 'package' in power['name'].lower() or 'cpu' in power['name'].lower():
                cpu_power = round(power['value'], 1)
                break

        # CPU频率 - 优先从clocks获取实时频率,没有则用psutil
        cpu_freq_ghz = 0
        for clock in hw_data.get('clocks', []):
            if 'core' in clock['name'].lower() and '#1' in clock['name']:  # 取第一个核心频率
                cpu_freq_ghz = round(clock['value'] / 1000, 2)
                break
        if cpu_freq_ghz == 0:  # 如果没找到,用psutil
            cpu_freq = psutil.cpu_freq()
            cpu_freq_ghz = round(cpu_freq.current / 1000, 2) if cpu_freq else 0
        # 网络带宽
        net_io_start = psutil.net_io_counters()
        time.sleep(0.5)
        net_io_end = psutil.net_io_counters()
        download_speed = round((net_io_end.bytes_recv - net_io_start.bytes_recv) / 1024 / 1024 / 0.5, 2)
        upload_speed = round((net_io_end.bytes_sent - net_io_start.bytes_sent) / 1024 / 1024 / 0.5, 2)

        # CPU功耗
        cpu_power = 0
        for power in hw_data.get('powers', []):
            if power['name'] == 'CPU Package':  # 精确匹配
                cpu_power = round(power['value'], 1)
                break

        combined = {**sys_info, **hw_data}
        combined['cpu_freq'] = cpu_freq_ghz
        combined['cpu_power'] = cpu_power
        combined['network_download'] = download_speed
        combined['network_upload'] = upload_speed

        return jsonify(combined)
    except Exception as e:
        print(f"[ERROR] 获取系统信息失败: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/disk', methods=['GET'])
@permission_required('readonly')
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
@permission_required('readonly')
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










# app.py - 添加以下路由（和之前一样，不需要修改）

@app.route('/api/file/encrypt', methods=['POST'])
@permission_required('fullcontrol')
def encrypt_file_api():
    """加密单个文件或文件夹"""
    data = request.get_json()
    file_path = data.get('file_path', '').strip()
    password = data.get('password', '').strip()
    is_folder = data.get('is_folder', False)

    if not file_path or not password:
        return jsonify({'error': '文件路径和密码不能为空'}), 400

    try:
        from common import get_actual_file_path, is_path_allowed
        actual_path = get_actual_file_path(file_path)

        if not actual_path or not os.path.exists(actual_path):
            return jsonify({'error': '文件或文件夹不存在'}), 404

        if not is_path_allowed(actual_path):
            return jsonify({'error': '路径不在允许的目录中'}), 403

        # 文件夹加密
        if is_folder:
            results = encryption_manager.encrypt_folder_standalone(actual_path, password)
            return jsonify({
                'success': True,
                'message': f'文件夹加密完成: 成功 {results["success"]} 个，失败 {results["failed"]} 个',
                'details': results
            })

        # 单文件加密
        else:
            success = encryption_manager.encrypt_file_standalone(actual_path, password)
            if success:
                return jsonify({
                    'success': True,
                    'message': f'文件加密成功: {os.path.basename(file_path)}'
                })
            else:
                return jsonify({'error': '文件加密失败'}), 500

    except Exception as e:
        return jsonify({'error': f'加密失败: {str(e)}'}), 500


@app.route('/api/file/decrypt', methods=['POST'])
@permission_required('fullcontrol')
def decrypt_file_api():
    """解密单个文件或文件夹"""
    data = request.get_json()
    file_path = data.get('file_path', '').strip()
    password = data.get('password', '').strip()
    is_folder = data.get('is_folder', False)

    if not file_path or not password:
        return jsonify({'error': '文件路径和密码不能为空'}), 400

    try:
        from common import get_actual_file_path, is_path_allowed
        actual_path = get_actual_file_path(file_path)

        if not actual_path or not os.path.exists(actual_path):
            return jsonify({'error': '文件或文件夹不存在'}), 404

        if not is_path_allowed(actual_path):
            return jsonify({'error': '路径不在允许的目录中'}), 403

        # 文件夹解密
        if is_folder:
            results = encryption_manager.decrypt_folder_standalone(actual_path, password)
            return jsonify({
                'success': True,
                'message': f'文件夹解密完成: 成功 {results["success"]} 个，失败 {results["failed"]} 个',
                'details': results
            })

        # 单文件解密
        else:
            success = encryption_manager.decrypt_file_standalone(actual_path, password)
            if success:
                return jsonify({
                    'success': True,
                    'message': f'文件解密成功: {os.path.basename(file_path)}'
                })
            else:
                return jsonify({'error': '文件解密失败，请检查密码'}), 500

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'解密失败: {str(e)}'}), 500
# 文件: app.py (添加一个新的删除路由，用于单文件删除)
@app.route('/api/ec_health_check', methods=['GET'])
@permission_required('fullcontrol')
def ec_health_check():
    """
    全面的EC卷健康检查
    """
    cfg = _load_json(EC_CFG_PATH, {})
    if not cfg:
        return jsonify({"is_configured": False})

    idx = _load_json(EC_IDX_PATH, {"files": {}})
    k, m = cfg.get("k", 0), cfg.get("m", 0)
    config_disks = cfg.get("disks", [])

    # 检查每个文件的健康状况
    health_report = {
        "total_files": len(idx.get("files", {})),
        "healthy_files": 0,
        "at_risk_files": 0,  # 丢失分片数 <= m 但 > 0
        "corrupted_files": 0,  # 丢失分片数 > m
        "file_details": []
    }

    for name, meta in idx.get("files", {}).items():
        missing_shards = []
        available_shards = []

        for i, disk in enumerate(meta["disks"][:meta["k"] + meta["m"]]):
            enc_dir = os.path.join(disk, "encoded", os.path.dirname(name))
            blk = os.path.join(enc_dir, f"{os.path.basename(name)}.blk_{i}")

            if os.path.exists(blk):
                available_shards.append(i)
            else:
                missing_shards.append(i)

        missing_count = len(missing_shards)

        if missing_count == 0:
            health_report["healthy_files"] += 1
            status = "healthy"
        elif missing_count <= m:
            health_report["at_risk_files"] += 1
            status = "at_risk"
        else:
            health_report["corrupted_files"] += 1
            status = "corrupted"

        health_report["file_details"].append({
            "name": name,
            "status": status,
            "missing_count": missing_count,
            "available_count": len(available_shards),
            "missing_shards": missing_shards,
            "can_recover": missing_count <= m
        })

    return jsonify(health_report)
# 文件: app.py (新增 /api/rename 路由)

@app.route('/api/ec_batch_recover', methods=['POST'])
@permission_required('fullcontrol')
def ec_batch_recover():
    """
    批量恢复所有可恢复的文件
    """
    data = request.get_json()
    auto_rebuild = data.get('auto_rebuild', True)

    cfg = _load_json(EC_CFG_PATH, {})
    if not cfg:
        return jsonify({"error": "未配置纠删码"}), 400

    idx = _load_json(EC_IDX_PATH, {"files": {}})

    recovery_report = {
        "total_processed": 0,
        "successfully_recovered": 0,
        "failed_recoveries": [],
        "skipped_files": []
    }

    for name, meta in idx.get("files", {}).items():
        k, m = meta["k"], meta["m"]
        disks = meta["disks"]

        # 检查缺失的分片
        missing_indices = []
        shard_dict = {}
        meta_obj = None

        for i, disk in enumerate(disks[:k + m]):
            enc_dir = os.path.join(disk, "encoded", os.path.dirname(name))
            blk = os.path.join(enc_dir, f"{os.path.basename(name)}.blk_{i}")

            if os.path.exists(blk):
                with open(blk, "rb") as f:
                    shard_dict[i] = f.read()
            else:
                missing_indices.append(i)

            if not meta_obj:
                mj = os.path.join(enc_dir, f"{os.path.basename(name)}.meta.json")
                if os.path.exists(mj):
                    with open(mj, "r", encoding="utf-8") as mf:
                        meta_obj = json.load(mf)

        recovery_report["total_processed"] += 1

        # 如果没有缺失,跳过
        if not missing_indices:
            recovery_report["skipped_files"].append({
                "name": name,
                "reason": "no_missing_shards"
            })
            continue

        # 如果缺失过多,无法恢复
        if len(missing_indices) > m:
            recovery_report["failed_recoveries"].append({
                "name": name,
                "reason": "too_many_missing_shards",
                "missing_count": len(missing_indices)
            })
            continue

        # 如果可用分片不足
        if len(shard_dict) < k or not meta_obj:
            recovery_report["failed_recoveries"].append({
                "name": name,
                "reason": "insufficient_shards",
                "available_count": len(shard_dict)
            })
            continue

        # 执行恢复
        try:
            # 解码重建原始数据
            data_bytes = _decode_from_dict(shard_dict, meta_obj)

            # 重新编码生成所有分片
            all_shards = rs_encode(data_bytes, k, m)

            # 只写入缺失的分片
            for missing_idx in missing_indices:
                disk = disks[missing_idx]
                enc_dir = os.path.join(disk, "encoded", os.path.dirname(name))
                os.makedirs(enc_dir, exist_ok=True)

                blk_path = os.path.join(enc_dir, f"{os.path.basename(name)}.blk_{missing_idx}")
                with open(blk_path, "wb") as f:
                    f.write(all_shards[missing_idx])

                # 同时更新meta文件
                meta_path = os.path.join(enc_dir, f"{os.path.basename(name)}.meta.json")
                with open(meta_path, "w", encoding="utf-8") as mf:
                    json.dump(meta_obj, mf, ensure_ascii=False)

            recovery_report["successfully_recovered"] += 1

        except Exception as e:
            recovery_report["failed_recoveries"].append({
                "name": name,
                "reason": "recovery_exception",
                "error": str(e)
            })

    return jsonify({
        "success": True,
        "report": recovery_report
    })

@app.route('/api/rename', methods=['POST'])
@permission_required('readwrite')
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
    # ✅ EC 卷重命名逻辑
    if _is_ec_volume(path):
        try:
            # 从路径中提取逻辑文件名
            logical_name = path.replace("\\", "/").strip("/")
            if logical_name.startswith("ec_volume/"):
                logical_name = logical_name[len("ec_volume/"):]

            # 读取索引
            idx = _load_json(EC_IDX_PATH, {"files": {}})

            if logical_name not in idx.get("files", {}):
                return jsonify({"error": "EC卷文件不存在"}), 404

            # 构建新的逻辑路径
            parent_dir = os.path.dirname(logical_name)
            new_logical_name = os.path.join(parent_dir, new_name).replace("\\", "/")

            if new_logical_name in idx.get("files", {}):
                return jsonify({"error": "目标文件名已存在"}), 400

            # 获取文件元数据
            file_meta = idx["files"][logical_name]
            disks = file_meta.get("disks", [])
            base_old_name = os.path.basename(logical_name)

            # 在每个磁盘上重命名分片文件
            for i, disk in enumerate(disks[:file_meta["k"] + file_meta["m"]]):
                enc_dir = os.path.join(disk, "encoded", os.path.dirname(logical_name))

                # 重命名 .blk_X 文件
                old_blk = os.path.join(enc_dir, f"{base_old_name}.blk_{i}")
                new_blk = os.path.join(enc_dir, f"{new_name}.blk_{i}")

                if os.path.exists(old_blk):
                    os.rename(old_blk, new_blk)

                # 重命名 .meta.json 文件
                old_meta = os.path.join(enc_dir, f"{base_old_name}.meta.json")
                new_meta = os.path.join(enc_dir, f"{new_name}.meta.json")

                if os.path.exists(old_meta):
                    os.rename(old_meta, new_meta)

            # 更新索引
            idx["files"][new_logical_name] = idx["files"].pop(logical_name)
            _save_json(EC_IDX_PATH, idx)

            return jsonify({"success": True, "message": "EC卷文件重命名成功"})

        except Exception as e:
            return jsonify({"error": f"EC卷重命名失败: {str(e)}"}), 500

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
@permission_required('fullcontrol')
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
@permission_required('fullcontrol')
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






@app.route('/api/preview')
@permission_required('readonly')
def preview_file():
    path = request.args.get('path', '').strip()
    if not path:
        return jsonify({'error': '未指定文件路徑'}), 400

    print(f"[DEBUG] 預覽請求 - 原始路徑: {path}")

    # --- 分支 1: 處理糾刪碼卷 (邏輯保持不變) ---
    if _is_ec_volume(path):
        from common import get_actual_file_path
        logical_path = get_actual_file_path(path)
        index_key = logical_path.replace('ec_volume/', '', 1).strip('/')
        if not index_key: return jsonify({'error': 'EC 卷路徑無效'}), 400
        idx = _load_json(EC_IDX_PATH, {"files": {}})
        entry = idx.get("files", {}).get(index_key)
        if not entry: return jsonify({'error': 'EC 卷文件不存在'}), 404
        k, m, disks = entry["k"], entry["m"], entry["disks"]
        shard_dict, meta = {}, None
        base_filename = os.path.basename(index_key)
        for i, disk in enumerate(disks[:k + m]):
            enc_dir = os.path.join(disk, "encoded", os.path.dirname(index_key))
            blk = os.path.join(enc_dir, f"{base_filename}.blk_{i}")
            if os.path.exists(blk):
                with open(blk, "rb") as f: shard_dict[i] = f.read()
            if not meta:
                mj = os.path.join(enc_dir, f"{base_filename}.meta.json")
                if os.path.exists(mj):
                    with open(mj, "r", encoding="utf-8") as mf: meta = json.load(mf)
        if not meta or len(shard_dict) < k: return jsonify({'error': '可用分片不足，無法恢復'}), 409
        try:
            data = _decode_from_dict(shard_dict, meta)
        except Exception as e:
            print(f"[ERROR] EC 預覽解碼失敗: {e}")
            return jsonify({'error': f'EC 卷文件解碼失敗: {e}'}), 500
        mime = mimetypes.guess_type(index_key)[0] or 'application/octet-stream'
        return send_file(io.BytesIO(data), mimetype=mime)

    # --- 分支 2: 處理物理磁碟 (✅ 整合加密邏輯) ---
    else:
        try:
            from common import get_actual_file_path, is_path_allowed
            actual_path = get_actual_file_path(path)

            if not actual_path or not os.path.exists(actual_path):
                return jsonify({'error': '文件不存在或路徑無效'}), 404
            if not is_path_allowed(actual_path):
                return jsonify({'error': '路徑不在允許的目錄中'}), 403

            # [✅ 加密邏輯整合]
            decrypted_data = None
            if encryption_manager.is_path_encrypted(actual_path):
                try:
                    # 如果是加密盤，則讀取並解密文件內容
                    decrypted_data = encryption_manager.read_encrypted_file(actual_path)
                except NotUnlockedError as e:
                    return jsonify({'error': str(e)}), 403
                except Exception as e:
                    return jsonify({'error': f'文件解密失敗: {e}'}), 500

            # 根據是否解密來決定後續的數據來源
            ext = os.path.splitext(actual_path)[1].lower()
            text_exts = ['.txt', '.log', '.md', '.py', '.js', '.html', '.json', '.css']

            if ext in text_exts:
                # 如果是文本文件
                if decrypted_data is not None:
                    # 使用解密後的數據
                    content = decrypted_data.decode('utf-8', errors='ignore')
                else:
                    # 直接從硬碟讀取
                    with open(actual_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                return content, 200, {'Content-Type': 'text/plain; charset=utf-8'}
            else:
                # 如果是二進制文件 (圖片、影片等)
                if decrypted_data is not None:
                    # 使用解密後的數據創建一個內存中的文件流
                    data_source = io.BytesIO(decrypted_data)
                else:
                    # 直接使用硬碟上的文件路徑
                    data_source = actual_path

                mime = mimetypes.guess_type(actual_path)[0] or 'application/octet-stream'
                return send_file(data_source, mimetype=mime)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'預覽處理失敗: {str(e)}'}), 500

# ===== [最终修复 2/3] 重写 mkdir 函数 =====
@app.route('/api/mkdir', methods=['POST'])
@permission_required('readwrite')
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
@permission_required('fullcontrol')
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


@app.route('/api/current-user', methods=['GET'])
def get_current_user():
    """获取当前登录用户信息"""
    try:
        # 从 session 或 JWT 中获取用户信息
        user_id = g.get('user')  # 假设你的 auth.py 已经设置了 g.user

        if not user_id:
            return jsonify({'user': None}), 401

        db = get_db()
        user = db.execute(
            "SELECT id, username, is_admin FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()

        if user:
            return jsonify({
                'user': {
                    'id': user['id'],
                    'username': user['username'],
                    'is_admin': bool(user['is_admin'])
                }
            })
        else:
            return jsonify({'user': None}), 401

    except Exception as e:
        print(f"获取用户信息错误: {e}")
        return jsonify({'user': None}), 401


# ========== 来自管理端的访问申请处理 ==========

# 存储待处理的访问申请（实际应用中应该用数据库）
pending_requests = {}


@app.route('/api/internal/access-request', methods=['POST'])
def receive_access_request():
    """
    [新增] 接收来自管理端的访问申请
    管理端会调用这个 API 来通知客户端有新的访问请求
    """
    data = request.json

    # 验证请求来源（简单验证，实际应用中应该用更安全的方式）
    secret = request.headers.get('X-NAS-Secret')
    if secret != "your-shared-secret-key":  # 应该在配置文件中设置
        return jsonify({"success": False, "message": "未授权的请求"}), 403

    request_id = data.get('request_id')
    username = data.get('username')
    requested_permission = data.get('permission')
    node_id = data.get('node_id')

    if not all([request_id, username, requested_permission, node_id]):
        return jsonify({"success": False, "message": "缺少必要参数"}), 400

    # 存储访问申请
    pending_requests[request_id] = {
        'username': username,
        'permission': requested_permission,
        'node_id': node_id,
        'status': 'pending',
        'created_at': datetime.now().isoformat()
    }

    print(f"[访问申请] 收到用户 {username} 的访问申请 (权限: {requested_permission})")

    return jsonify({
        "success": True,
        "message": "访问申请已接收",
        "request_id": request_id
    })


@app.route('/api/admin/access-requests', methods=['GET'])
@permission_required('fullcontrol')
def get_pending_requests():
    """
    [新增] 管理员查看待处理的访问申请
    """
    return jsonify({
        "success": True,
        "requests": [
            {
                "request_id": req_id,
                **req_data
            }
            for req_id, req_data in pending_requests.items()
            if req_data['status'] == 'pending'
        ]
    })


@app.route('/api/admin/access-requests/<request_id>/approve', methods=['POST'])
@permission_required('fullcontrol')
def approve_access_request(request_id):
    """
    [新增] 管理员批准访问申请
    """
    if request_id not in pending_requests:
        return jsonify({"success": False, "message": "申请不存在"}), 404

    request_data = pending_requests[request_id]

    # 更新申请状态
    request_data['status'] = 'approved'
    request_data['approved_at'] = datetime.now().isoformat()

    # 通知管理端申请已被批准
    try:
        response = requests.post(
            f"{NAS_CENTER_API_URL}/api/internal/access-approved",
            json={
                "request_id": request_id,
                "username": request_data['username'],
                "node_id": request_data['node_id']
            },
            headers={"X-NAS-Secret": "your-shared-secret-key"},
            timeout=5
        )

        if response.status_code == 200:
            print(f"[访问申请] 已通知管理端：用户 {request_data['username']} 的申请已批准")
            return jsonify({"success": True, "message": "申请已批准"})
        else:
            return jsonify({"success": False, "message": "通知管理端失败"}), 500

    except Exception as e:
        print(f"[错误] 通知管理端失败: {e}")
        return jsonify({"success": False, "message": f"通知失败: {str(e)}"}), 500


@app.route('/api/admin/access-requests/<request_id>/reject', methods=['POST'])
@permission_required('fullcontrol')
def reject_access_request(request_id):
    """
    [新增] 管理员拒绝访问申请
    """
    if request_id not in pending_requests:
        return jsonify({"success": False, "message": "申请不存在"}), 404

    request_data = pending_requests[request_id]
    reason = request.json.get('reason', '管理员拒绝')

    # 更新申请状态
    request_data['status'] = 'rejected'
    request_data['rejected_at'] = datetime.now().isoformat()
    request_data['reject_reason'] = reason

    # 通知管理端申请已被拒绝
    try:
        response = requests.post(
            f"{NAS_CENTER_API_URL}/api/internal/access-rejected",
            json={
                "request_id": request_id,
                "username": request_data['username'],
                "node_id": request_data['node_id'],
                "reason": reason
            },
            headers={"X-NAS-Secret": "your-shared-secret-key"},
            timeout=5
        )

        if response.status_code == 200:
            print(f"[访问申请] 已通知管理端：用户 {request_data['username']} 的申请已拒绝")
            return jsonify({"success": True, "message": "申请已拒绝"})
        else:
            return jsonify({"success": False, "message": "通知管理端失败"}), 500

    except Exception as e:
        print(f"[错误] 通知管理端失败: {e}")
        return jsonify({"success": False, "message": f"通知失败: {str(e)}"}), 500
# V5 测试版 (正确的)
@app.route('/api/ec_recover', methods=['POST'])
@permission_required('fullcontrol')
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
@permission_required('readonly')
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

    # [✅ 修改后的代码]

    # 检查公网URL是否已获取
    if not NAS_CENTER_PUBLIC_URL:
        return jsonify({
            'success': False,
            'error': '无法生成公网分享链接，管理端公网地址未配置或获取失败。'
        }), 503

    # 使用新的配置变量拼接一个指向管理端的公网URL
    # 格式为: [管理端公网URL]/share/[节点ID]/[本地Token]
    public_share_url = f"{NAS_CENTER_PUBLIC_URL}/share/{THIS_NODE_ID}/{token}"

    return jsonify({
        'success': True,
        'share_url': f'/share/{token}',  # 本地路径(主要用于调试)
        'full_url': public_share_url  # [✅ 关键] 这是返回给用户的公网分享链接
    })


@app.route('/api/initialize', methods=['POST'])
def initialize():
    """
    客户端接收主控发来的身份信息
    """
    global NODE_ID, MASTER_URL
    data = request.json
    NODE_ID = data.get("node_id")
    master_ip = data.get("master_ip")
    master_port = data.get("master_port")

    MASTER_URL = f"http://{master_ip}:{master_port}/api/nodes/update-disks"

    print(f"[节点] 已初始化身份: {NODE_ID}")
    print(f"[节点] 主控中心: {MASTER_URL}")

    # 启动上报线程
    threading.Thread(target=report_disks, daemon=True).start()

    return jsonify({"success": True, "node_id": NODE_ID})

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

        # --- 分支 2: 處理物理硬碟文件 (✅ 整合加密邏輯) ---
    else:
        from common import get_actual_file_path, is_path_allowed
        actual_path = get_actual_file_path(file_path)

        if not actual_path or not is_path_allowed(actual_path) or not os.path.exists(actual_path):
            return "分享的文件不存在或已被移動", 404

        # [✅ 加密邏輯整合]
        if encryption_manager.is_path_encrypted(actual_path):
            try:
                decrypted_data = encryption_manager.read_encrypted_file(actual_path)
                return send_file(io.BytesIO(decrypted_data), as_attachment=True,
                                 download_name=os.path.basename(actual_path))
            except NotUnlockedError:
                return "磁碟已鎖定，暫時無法訪問分享內容", 503
            except Exception:
                return "分享文件解密失敗", 500
        else:
            # 非加密盤，正常下載
            return send_file(actual_path, as_attachment=True)



# ===== /api/ec_config：保存时对 disks 做 _norm_abs 归一化 =====
# ===== /api/ec_config：支持 GET（查看）、POST（保存）和 DELETE（删除）=====
@app.route("/api/ec_config", methods=["GET", "POST", "DELETE"])
@permission_required('fullcontrol')
def api_ec_config():
    """
    GET    返回当前纠删码配置与容量评估
    POST   保存纠删码配置（scheme=rs, k, m, disks），归一化 disks，创建各盘 encoded/ 目录，并返回容量评估
    DELETE 删除纠删码配置，清空设置
    """
    # 新增：处理DELETE请求
    if request.method == "DELETE":
        try:
            # ✅ 1. 读取配置以获取磁盘列表
            cfg = _load_json(EC_CFG_PATH, {})
            disks = cfg.get("disks", [])

            # ✅ 2. 清理各磁盘上的 encoded 目录
            cleaned_disks = []
            failed_disks = []
            for disk in disks:
                try:
                    encoded_dir = os.path.join(disk, "encoded")
                    if os.path.exists(encoded_dir):
                        import shutil
                        shutil.rmtree(encoded_dir)
                        cleaned_disks.append(disk)
                        print(f"✅ 已清理磁盘 {disk} 的 encoded 目录")
                except Exception as e:
                    failed_disks.append({"disk": disk, "error": str(e)})
                    print(f"⚠️ 清理磁盘 {disk} 失败: {e}")

            # ✅ 3. 删除配置文件
            if os.path.exists(EC_CFG_PATH):
                os.remove(EC_CFG_PATH)

            # ✅ 4. 删除索引文件
            if os.path.exists(EC_IDX_PATH):
                os.remove(EC_IDX_PATH)

            # ✅ 5. 返回详细结果
            return jsonify({
                "success": True,
                "message": "纠删码配置已成功删除",
                "cleaned_disks": cleaned_disks,
                "failed_disks": failed_disks,
                "total_cleaned": len(cleaned_disks)
            })

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
@permission_required('fullcontrol')
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

# app.py -> 完整替換 @app.route('/api/upload', ...)

# app.py -> 完整替換 @app.route('/api/upload', ...)

@app.route('/api/upload', methods=['POST'])
@permission_required('readwrite')
def upload_file_with_ec():
    uploaded_files = request.files.getlist('file')
    upload_path = request.form.get('path', '/')
    print(f"[DEBUG] 上傳請求接收路徑: {upload_path}")
    if not uploaded_files or not all(f.filename for f in uploaded_files):
        return jsonify({'error': '未提供文件'}), 400

    # 分支 1: 邏輯盤：自動 RS (保持不變)
    if _is_ec_volume(upload_path):
        # ... (這部分的 EC 邏輯和您原來的一樣，無需改動) ...
        # ... (為節省篇幅，此處省略，請保留您原有的EC上傳程式碼) ...
        ec_cfg = _load_json(EC_CFG_PATH, {})
        if not ec_cfg or ec_cfg.get("scheme", "").lower() != "rs": return jsonify(
            {'error': '未配置或未啟用RS糾刪碼'}), 400
        k, m, disks = int(ec_cfg.get("k", 0)), int(ec_cfg.get("m", 0)), ec_cfg.get("disks", [])
        if k <= 0 or m <= 0 or len(disks) < k + m: return jsonify({'error': 'RS參數無效或磁碟數量不足'}), 400
        for uploaded_file in uploaded_files:
            data = uploaded_file.read()
            shards = rs_encode(data, k, m)
            shard_size = len(shards[0]) if shards else 0
            file_sha = hashlib.sha256(data).hexdigest()
            norm_path = upload_path.replace("\\", "/").strip("/")
            rel_in_volume_dir = '' if norm_path == 'ec_volume' else norm_path[len('ec_volume/'):]
            logical_name = os.path.join(rel_in_volume_dir, uploaded_file.filename).replace("\\", "/")
            meta = {"k": k, "m": m, "shard_size": shard_size, "original_size": len(data), "sha256": file_sha}
            try:
                for i, disk in enumerate(disks[:k + m]):
                    enc_dir = os.path.join(disk, "encoded", rel_in_volume_dir)
                    os.makedirs(enc_dir, exist_ok=True)
                    base_filename = os.path.basename(uploaded_file.filename)
                    with open(os.path.join(enc_dir, f"{base_filename}.blk_{i}"), "wb") as f: f.write(shards[i])
                    with open(os.path.join(enc_dir, f"{base_filename}.meta.json"), "w",
                              encoding="utf-8") as mf: json.dump(meta, mf, ensure_ascii=False)
            except Exception as e:
                return jsonify({'error': f'寫入分片失敗: {e}'}), 500
            idx = _load_json(EC_IDX_PATH, {"files": {}})
            idx["files"][logical_name] = {"size": len(data), "k": k, "m": m, "sha256": file_sha, "disks": disks,
                                          "ctime": int(time.time())}
            _save_json(EC_IDX_PATH, idx)
        return jsonify({'success': True, 'message': f'{len(uploaded_files)}個文件已寫入邏輯盤並完成RS編碼'})

    # 分支 2: 物理磁碟：整合加密邏輯
    else:
        try:
            drive, _ = os.path.splitdrive(upload_path)
            if not drive: return jsonify({'error': '上傳路徑格式錯誤，缺少盤符'}), 400
            drive = drive.upper().replace('\\', '/')
            if not os.path.exists(drive): return jsonify({'error': f'磁碟 {drive} 不存在'}), 404

            target_dir = os.path.abspath(upload_path)
            if not target_dir.upper().startswith(drive): return jsonify({'error': f'非法上傳路徑: {target_dir}'}), 403

            os.makedirs(target_dir, exist_ok=True)

            for uploaded_file in uploaded_files:
                filename = uploaded_file.filename
                target_path = os.path.join(target_dir, filename)

                if not os.path.abspath(target_path).upper().startswith(drive):
                    return jsonify({'error': f'非法的最終文件路徑: {target_path}'}), 403

                # [✅ 核心修正]
                # 1. 先將文件完整讀入記憶體
                data_bytes = uploaded_file.read()

                # 2. 判斷是否需要加密
                if encryption_manager.is_path_encrypted(target_path):
                    try:
                        # 如果是加密盤，則通過加密管理器寫入
                        encryption_manager.write_encrypted_file(target_path, data_bytes)
                        print(f"DEBUG: 已將 {filename} 加密寫入到 {target_path}")
                    except NotUnlockedError as e:
                        # 捕獲“未解鎖”的特定異常
                        return jsonify({'error': str(e)}), 403
                else:
                    # 如果不是加密盤，則正常寫入
                    with open(target_path, "wb") as f:
                        f.write(data_bytes)

            return jsonify({'success': True, 'message': f'{len(uploaded_files)}個文件上傳成功'})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'處理上傳時發生嚴重錯誤: {e}'}), 500

# ===== [最终修复 1/3] 重写 list_files 函数 =====
@app.route('/api/list', methods=['GET'])
@permission_required('readonly')
def list_files():
    full_path_from_request = request.args.get('path', '/')
    keyword = request.args.get('q', '').strip().lower()

    # --- 分支 1: 处理纠删码卷 (保持不变) ---
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

    # --- 分支 2: 处理物理硬盘 (✅ 关键修复) ---
    else:
        try:
            full_path = os.path.abspath(full_path_from_request)
            if not is_path_allowed(full_path):
                return jsonify({'error': '非法路径或不允许访问的磁盘'}), 403

            # ✅ 关键修复: 优先检查加密状态
            if encryption_manager.is_path_encrypted(full_path):
                drive = encryption_manager._get_drive_for_path(full_path)
                if drive and drive not in encryption_manager.unlocked_keys:
                    return jsonify({
                        'error': f'磁盘 {drive} 已锁定,无法访问',
                        'error_type': 'disk_locked',
                        'drive': drive
                    }), 403

            if not os.path.exists(full_path) or not os.path.isdir(full_path):
                return jsonify({'error': f'路径不存在或不是文件夹'}), 404

            items = []
            for name in os.listdir(full_path):
                entry_full_path = os.path.join(full_path, name)
                stat = os.stat(entry_full_path)
                items.append({
                    'name': name,
                    'is_dir': os.path.isdir(entry_full_path),
                    'size': stat.st_size if os.path.isfile(entry_full_path) else None,
                    'mtime': stat.st_mtime,
                })
            items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
            return jsonify({'success': True, 'items': items})

        except Exception as e:
            return jsonify({'error': f'读取目录失败: {str(e)}'}), 500

@app.route('/api/search')
@permission_required('readonly')
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

# app.py -> 完整替換 @app.route("/api/download", ...)

@app.route("/api/download", methods=["GET"])
@permission_required('readonly')
def api_download():
    file_path = request.args.get("path", "").strip()
    if not file_path:
        return jsonify({"error": "缺少 path 參數"}), 400

    # --- 分支 1: 處理糾刪碼卷 (邏輯保持不變) ---
    if _is_ec_volume(file_path):
        name = file_path.replace("\\", "/").strip("/").split("/", 1)[-1]
        if not name: return jsonify({"error": "無效的邏輯盤文件路徑"}), 400
        idx = _load_json(EC_IDX_PATH, {"files": {}}).get("files", {})
        entry = idx.get(name)
        if not entry: return jsonify({"error": "文件不在邏輯盤索引中"}), 404
        k, m, disks = entry["k"], entry["m"], entry["disks"]
        shard_dict, meta = {}, None
        for i, disk in enumerate(disks[:k + m]):
            enc_dir = os.path.join(disk, "encoded", os.path.dirname(name))
            blk = os.path.join(enc_dir, f"{os.path.basename(name)}.blk_{i}")
            if os.path.exists(blk):
                with open(blk, "rb") as f: shard_dict[i] = f.read()
            if not meta:
                mj = os.path.join(enc_dir, f"{os.path.basename(name)}.meta.json")
                if os.path.exists(mj): meta = json.load(open(mj, "r", encoding="utf-8"))
        if not meta or len(shard_dict) < k: return jsonify({"error": "可用分片不足，無法恢復"}), 409
        try:
            data = _decode_from_dict(shard_dict, meta)
        except Exception as e:
            return jsonify({"error": f"解碼失敗: {e}"}), 500
        if hashlib.sha256(data).hexdigest() != meta.get("sha256"):
            return jsonify({"error": "數據完整性校驗失敗"}), 500
        return send_file(io.BytesIO(data), as_attachment=True, download_name=os.path.basename(name))

    # --- 分支 2: 處理物理磁碟 (✅ 整合加密邏輯) ---
    else:
        try:
            from common import get_actual_file_path, is_path_allowed
            actual_path = get_actual_file_path(file_path)

            if not actual_path or not os.path.exists(actual_path):
                return jsonify({"error": "文件不存在或路徑無效"}), 404
            if not is_path_allowed(actual_path):
                return jsonify({"error": "不允許訪問該路徑"}), 403

            # [✅ 加密邏輯整合]
            if encryption_manager.is_path_encrypted(actual_path):
                try:
                    # 從加密層讀取並解密文件
                    decrypted_data = encryption_manager.read_encrypted_file(actual_path)
                    # 將解密後的數據作為內存文件發送
                    return send_file(io.BytesIO(decrypted_data), as_attachment=True,
                                     download_name=os.path.basename(actual_path))
                except NotUnlockedError as e:
                    return jsonify({'error': str(e)}), 403
                except Exception as e:
                    return jsonify({'error': f'文件解密失敗: {e}'}), 500
            else:
                # 非加密盤，沿用舊邏輯，正常下載
                return send_file(actual_path, as_attachment=True, download_name=os.path.basename(actual_path))

        except Exception as e:
            return jsonify({'error': f'下載文件時出錯: {e}'}), 500

@app.route("/api/volume/rebuild/scan", methods=["POST"])
@permission_required('fullcontrol')
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
@permission_required('fullcontrol')
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



FLASK_PORT = 5000
PROJECT_ROOT = Path(__file__).parent # <-- 注意，这里只有一个 .parent
OHM_PATH = str(PROJECT_ROOT / 'LibreHardwareMonitor-net472' / 'LibreHardwareMonitor.exe')

OHM_PORT = 8085

ohm_process = None


def start_librehardwaremonitor():
    """启动 LibreHardwareMonitor，自动处理权限问题"""
    global ohm_process
    print("🌡️  正在启动 LibreHardwareMonitor (后台隐藏模式)...")

    # 检查是否已在运行
    try:
        response = requests.get(f'http://localhost:{OHM_PORT}/data.json', timeout=2)
        if response.status_code == 200:
            print("✅  LibreHardwareMonitor 已在运行！")
            return "already_running"
    except requests.exceptions.ConnectionError:
        pass

    if not os.path.exists(OHM_PATH):
        print(f"⚠️  LibreHardwareMonitor.exe 未找到, 路径: {OHM_PATH}")
        return None

    # 清理旧进程
    try:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/F', '/IM', 'LibreHardwareMonitor.exe'],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("🧹  已清理旧的 LibreHardwareMonitor 进程。")
    except:
        pass

    # 尝试启动
    try:
        DETACHED_PROCESS = 0x00000008
        CREATE_NO_WINDOW = 0x08000000
        flags = DETACHED_PROCESS | CREATE_NO_WINDOW

        ohm_proc = subprocess.Popen(
            [OHM_PATH], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            cwd=os.path.dirname(OHM_PATH), creationflags=flags
        )
        print("   - 已在后台发送启动指令。")
        print("⏳  正在等待 LibreHardwareMonitor HTTP 服务就绪...")

        for i in range(15):
            time.sleep(1)
            try:
                response = requests.get(f'http://localhost:{OHM_PORT}/data.json', timeout=2)
                if response.status_code == 200:
                    print(f"✅  LibreHardwareMonitor HTTP 服务已就绪。")
                    return ohm_proc
            except requests.exceptions.ConnectionError:
                continue

        print("⚠️  LibreHardwareMonitor 已启动, 但无法确认其 Web 服务。")
        return ohm_proc

    except Exception as e:
        error_code = getattr(e, 'winerror', None)

        # 如果是权限错误，自动请求管理员权限
        if error_code == 740 or isinstance(e, PermissionError):
            print(f'❌  LibreHardwareMonitor 需要管理员权限！')

            if not is_admin():
                print('🔐  正在请求管理员权限，请在 UAC 对话框中点击"是"...')

                if run_as_admin(' '.join(sys.argv)):
                    print('✅  程序即将以管理员权限重启...')
                    time.sleep(2)
                    sys.exit(0)
                else:
                    print('❌  无法获取管理员权限')
                    print('请右键 app.py -> "以管理员身份运行"')
                    input('按 Enter 退出...')
                    sys.exit(1)

        print(f'❌  LibreHardwareMonitor 启动时发生严重错误: {e}')
        return None


def fetch_nas_center_config():
    """
    [新增] 启动时从管理端获取配置 (如公网URL)
    """
    global NAS_CENTER_PUBLIC_URL

    # 目标URL是管理端的局域网API
    target_url = f"{NAS_CENTER_API_URL}/api/ngrok-url"

    print(f"🔗  正在从管理端 {NAS_CENTER_API_URL} 获取公网地址...")

    max_retries = 30  # 最多重试30次 (约5分钟)
    for i in range(max_retries):
        try:
            response = requests.get(target_url, timeout=5)

            if response.status_code == 200:
                data = response.json()
                if data.get('url'):
                    NAS_CENTER_PUBLIC_URL = data['url']
                    print(f"✅  成功获取公网地址: {NAS_CENTER_PUBLIC_URL}")
                    return True
                else:
                    print(f"⚠️  管理端返回了数据，但缺少 'url' 字段。")

            else:
                print(f"⚠️  管理端返回状态 {response.status_code}。")

        except requests.ConnectionError:
            print(f"🔌  无法连接到管理端... ({i + 1}/{max_retries})")
        except Exception as e:
            print(f"❌  获取配置时发生错误: {e}")

        if i < max_retries - 1:
            print(f"   将在 10 秒后重试...")
            time.sleep(10)  # 等待10秒重试

    print("❌  获取管理端配置失败。公网分享功能将不可用。")
    return False


@app.route('/api/move', methods=['POST'])
@permission_required('readwrite') # 'cut' 是一种写入操作
def move_entry():
    """[新增] 移动文件或文件夹 (剪切-粘贴)"""
    data = request.get_json()
    source_full_path = data.get('source_path')
    target_full_path = data.get('target_path') # 包含新文件名的完整目标路径

    if not source_full_path or not target_full_path:
        return jsonify({"error": "参数缺失"}), 400

    # --- 分支 1: EC 卷移动 (逻辑重命名) ---
    if _is_ec_volume(source_full_path):
        try:
            # 提取逻辑路径
            source_logical = source_full_path.replace("\\", "/").strip("/").split("/", 1)[-1]
            target_logical = target_full_path.replace("\\", "/").strip("/").split("/", 1)[-1]

            if not source_logical or not target_logical:
                 return jsonify({"error": "EC 逻辑路径无效"}), 400

            idx = _load_json(EC_IDX_PATH, {"files": {}})
            if source_logical not in idx.get("files", {}):
                return jsonify({"error": "EC源文件不存在"}), 404
            if target_logical in idx.get("files", {}):
                return jsonify({"error": "EC目标文件已存在"}), 400

            file_meta = idx["files"][source_logical]
            disks = file_meta.get("disks", [])
            base_old_name = os.path.basename(source_logical)
            base_new_name = os.path.basename(target_logical)

            # 在所有物理磁盘上移动(重命名)分片
            for i, disk in enumerate(disks[:file_meta["k"] + file_meta["m"]]):
                old_enc_dir = os.path.join(disk, "encoded", os.path.dirname(source_logical))
                new_enc_dir = os.path.join(disk, "encoded", os.path.dirname(target_logical))
                os.makedirs(new_enc_dir, exist_ok=True) # 确保目标目录存在

                # 移动 .blk 文件
                old_blk = os.path.join(old_enc_dir, f"{base_old_name}.blk_{i}")
                new_blk = os.path.join(new_enc_dir, f"{base_new_name}.blk_{i}")
                if os.path.exists(old_blk):
                    os.rename(old_blk, new_blk)

                # 移动 .meta 文件
                old_meta = os.path.join(old_enc_dir, f"{base_old_name}.meta.json")
                new_meta = os.path.join(new_enc_dir, f"{base_new_name}.meta.json")
                if os.path.exists(old_meta):
                    os.rename(old_meta, new_meta)

            # 更新索引
            idx["files"][target_logical] = idx["files"].pop(source_logical)
            _save_json(EC_IDX_PATH, idx)

            return jsonify({"success": True, "message": "EC文件移动成功"})
        except Exception as e:
            return jsonify({"error": f"EC文件移动失败: {str(e)}"}), 500

    # --- 分支 2: 物理磁盘移动 ---
    else:
        try:
            from common import get_actual_file_path, is_path_allowed, get_base_dir_for_path
            source_actual = get_actual_file_path(source_full_path)

            # 安全地构建目标路径
            target_drive = os.path.splitdrive(target_full_path)[0]
            target_base_dir = get_base_dir_for_path(target_drive) # 获取 D:/
            if not target_base_dir:
                 return jsonify({"error": "目标路径无效"}), 403

            target_rel_path = target_full_path.replace(target_drive, "").lstrip("/\\")
            target_actual = os.path.join(target_base_dir, target_rel_path)


            if not source_actual or not os.path.exists(source_actual):
                return jsonify({"error": "源文件不存在"}), 404
            if not is_path_allowed(source_actual) or not is_path_allowed(target_actual):
                return jsonify({"error": "路径不在允许的目录中"}), 403
            if os.path.exists(target_actual):
                return jsonify({"error": "目标文件已存在"}), 400

            os.rename(source_actual, target_actual) # os.rename 在同盘符是重命名，跨盘符是移动
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": f"移动失败: {str(e)}"}), 500


@app.route('/api/copy', methods=['POST'])
@permission_required('readwrite') # 'copy' 是一种写入操作
def copy_entry():
    """[新增] 复制文件或文件夹 (复制-粘贴)"""
    data = request.get_json()
    source_full_path = data.get('source_path')
    target_full_path = data.get('target_path')

    if not source_full_path or not target_full_path:
        return jsonify({"error": "参数缺失"}), 400

    # --- 分支 1: EC 卷复制 (复制分片和索引) ---
    if _is_ec_volume(source_full_path):
        # 简化版：假设在同一EC卷内复制，我们只复制分片和索引
        try:
            source_logical = source_full_path.replace("\\", "/").strip("/").split("/", 1)[-1]
            target_logical = target_full_path.replace("\\", "/").strip("/").split("/", 1)[-1]

            if not source_logical or not target_logical:
                 return jsonify({"error": "EC 逻辑路径无效"}), 400

            idx = _load_json(EC_IDX_PATH, {"files": {}})
            if source_logical not in idx.get("files", {}):
                return jsonify({"error": "EC源文件不存在"}), 404
            if target_logical in idx.get("files", {}):
                return jsonify({"error": "EC目标文件已存在"}), 400

            file_meta = idx["files"][source_logical].copy() # 复制元数据
            disks = file_meta.get("disks", [])
            base_old_name = os.path.basename(source_logical)
            base_new_name = os.path.basename(target_logical)

            # 复制所有物理分片
            for i, disk in enumerate(disks[:file_meta["k"] + file_meta["m"]]):
                old_enc_dir = os.path.join(disk, "encoded", os.path.dirname(source_logical))
                new_enc_dir = os.path.join(disk, "encoded", os.path.dirname(target_logical))
                os.makedirs(new_enc_dir, exist_ok=True)

                old_blk = os.path.join(old_enc_dir, f"{base_old_name}.blk_{i}")
                new_blk = os.path.join(new_enc_dir, f"{base_new_name}.blk_{i}")
                if os.path.exists(old_blk):
                    shutil.copy2(old_blk, new_blk)

                old_meta = os.path.join(old_enc_dir, f"{base_old_name}.meta.json")
                new_meta = os.path.join(new_enc_dir, f"{base_new_name}.meta.json")
                if os.path.exists(old_meta):
                    shutil.copy2(old_meta, new_meta)

            # 更新索引
            file_meta['ctime'] = int(time.time()) # 更新创建时间
            idx["files"][target_logical] = file_meta
            _save_json(EC_IDX_PATH, idx)

            return jsonify({"success": True, "message": "EC文件复制成功"})
        except Exception as e:
            return jsonify({"error": f"EC文件复制失败: {str(e)}"}), 500

    # --- 分支 2: 物理磁盘复制 ---
    else:
        try:
            from common import get_actual_file_path, is_path_allowed, get_base_dir_for_path
            source_actual = get_actual_file_path(source_full_path)

            target_drive = os.path.splitdrive(target_full_path)[0]
            target_base_dir = get_base_dir_for_path(target_drive)
            if not target_base_dir:
                 return jsonify({"error": "目标路径无效"}), 403

            target_rel_path = target_full_path.replace(target_drive, "").lstrip("/\\")
            target_actual = os.path.join(target_base_dir, target_rel_path)


            if not source_actual or not os.path.exists(source_actual):
                return jsonify({"error": "源文件不存在"}), 404
            if not is_path_allowed(source_actual) or not is_path_allowed(target_actual):
                return jsonify({"error": "路径不在允许的目录中"}), 403
            if os.path.exists(target_actual):
                return jsonify({"error": "目标文件已存在"}), 400

            # 使用 shutil.copy2 (文件) 或 shutil.copytree (目录)
            if os.path.isdir(source_actual):
                shutil.copytree(source_actual, target_actual)
            else:
                shutil.copy2(source_actual, target_actual)

            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": f"复制失败: {str(e)}"}), 500



@app.route('/api/documents', methods=['GET'])
@permission_required('readonly')
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
@permission_required('fullcontrol')
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




@app.route('/api/encryption/status', methods=['GET'])
@permission_required('fullcontrol')
def encryption_status():
    """获取所有物理磁盘及其加密/锁定状态"""
    all_drives = get_available_drives()
    enc_status = encryption_manager.get_disk_status()

    response = []
    for drive_path in all_drives:
        norm_path = _norm_abs(drive_path)
        status = enc_status.get(norm_path, {
            "is_configured": False,
            "is_unlocked": False
        })
        response.append({
            "drive": drive_path,
            "is_configured": status["is_configured"],
            "is_unlocked": status["is_unlocked"]
        })
    return jsonify(response)


@app.route('/api/encryption/unlock', methods=['POST'])
@permission_required('fullcontrol')
def encryption_unlock():
    """解锁单个磁盘"""
    data = request.get_json()
    drive = data.get('drive')
    password = data.get('password', '')
    if not drive or not password:
        return jsonify({'error': '需要提供磁盘和密码'}), 400

    success = encryption_manager.unlock(drive, password)
    if success:
        return jsonify({'success': True, 'message': f'磁盘 {drive} 已解锁'})
    else:
        return jsonify({'error': '密码错误或磁盘未配置加密'}), 403


@app.route('/api/encryption/lock', methods=['POST'])
@permission_required('fullcontrol')
def encryption_lock():
    """锁定单个磁盘"""
    data = request.get_json()
    drive = data.get('drive')
    if not drive:
        return jsonify({'error': '需要提供磁盘'}), 400
    encryption_manager.lock(drive)
    return jsonify({'success': True, 'message': f'磁盘 {drive} 已锁定'})



import threading  # 确保在文件顶部导入 threading 模块



@app.route('/api/encryption/decrypt-disk', methods=['POST'])
@permission_required('fullcontrol')
def decrypt_disk_permanently_api():
    data = request.get_json()
    drive = data.get('drive')
    password = data.get('password')

    if not drive or not password:
        return jsonify({'error': '需要提供磁盘和密码'}), 400

    def background_task(app, drive_path, pwd):
        with app.app_context():
            try:
                result = encryption_manager.decrypt_disk_permanently(drive_path, pwd)

                # 解密成功后，从配置文件中移除该磁盘的加密设置
                if not result.get("failed_files"):
                    config_path = encryption_manager.config_path
                    config = _load_json(config_path, {"disks": {}})
                    norm_drive = _norm_abs(drive_path)
                    if norm_drive in config.get("disks", {}):
                        del config["disks"][norm_drive]
                        _save_json(config_path, config)
                        # 重新加载配置以更新服务器状态
                        encryption_manager.load_config()
                        print(f"🎉 已从加密配置中移除磁盘 {drive_path}")

            except ValueError as e:  # 捕获密码错误
                print(f"后台解密任务失败: {e}")
            except Exception as e:
                print(f"后台解密任务发生严重错误: {e}")

    # 在后台线程中运行解密任务
    thread = threading.Thread(target=background_task, args=(app, drive, password))
    thread.start()

    return jsonify(
        {'success': True, 'message': f'已开始在后台对磁盘 {drive} 进行永久解密，请通过服务器后台日志查看进度。'})



@app.route('/api/encryption/set-password', methods=['POST'])
@permission_required('fullcontrol')
def set_encryption_password():
    """为单个或多个磁盘设定/变更密码"""
    data = request.get_json()
    drives = data.get('drives', [])
    old_password = data.get('old_password')
    new_password = data.get('new_password')

    if not drives or not new_password:
        return jsonify({'error': '需要提供磁盘列表和新密码'}), 400

    config = _load_json(encryption_manager.config_path, {"disks": {}})

    # [✅ 关键修复] 在循环之前，就确保 'disks' 键一定存在且是一个字典。
    # 这样可以安全地处理空的或格式不完整的配置文件。
    if "disks" not in config or not isinstance(config.get("disks"), dict):
        config["disks"] = {}

    for drive_path in drives:
        norm_drive = _norm_abs(drive_path)

        # 经过上面的修复，现在这一行是绝对安全的了
        if norm_drive in config["disks"] and config["disks"][norm_drive].get("password_hash"):
            if not old_password:
                return jsonify({'error': f'磁盘 {drive_path} 已有密码，需要提供旧密码才能变更'}), 403

            temp_manager = EncryptionManager(encryption_manager.config_path)
            if not temp_manager.unlock(drive_path, old_password):
                return jsonify({'error': f'磁盘 {drive_path} 的旧密码不正确'}), 403

        new_salt = os.urandom(16)
        new_hash = hashlib.pbkdf2_hmac('sha256', new_password.encode('utf-8'), new_salt, 100000)

        config["disks"][norm_drive] = {
            "password_salt": new_salt.hex(),
            "password_hash": new_hash.hex()
        }

    _save_json(encryption_manager.config_path, config)
    encryption_manager.load_config()

    return jsonify({'success': True, 'message': '密码设定成功'})

@app.route('/api/documents', methods=['POST'])
@permission_required('readwrite')
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
@permission_required('readonly')
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
@permission_required('fullcontrol')
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
@permission_required('readonly')
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
@permission_required('readonly')
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


# app.py -> 完整替換 @app.route('/api/collab/load')

@app.route('/api/collab/load')
def collab_load():
    file = request.args.get('file', '').strip()
    path = request.args.get('path', '').strip()
    if path in ('', '/'): path = ''
    if not file:
        return jsonify({'success': False, 'error': '缺少文件名'}), 400

    full_path = os.path.abspath(os.path.join(BASE_DIRS[0], path, file))
    if not full_path.startswith(os.path.abspath(BASE_DIRS[0])):
        return jsonify({'success': False, 'error': '非法路徑'}), 403
    if not os.path.exists(full_path):
        return jsonify({'success': False, 'error': '文件不存在'}), 404

    try:
        content_bytes = None

        # [✅ 核心加密邏輯整合]
        if encryption_manager.is_path_encrypted(full_path):
            try:
                # 如果是加密盤，讀取解密後的二進制數據
                content_bytes = encryption_manager.read_encrypted_file(full_path)
            except NotUnlockedError as e:
                return jsonify({'success': False, 'error': str(e)}), 403
            except Exception as e:
                return jsonify({'success': False, 'error': f'文件解密失敗: {e}'}), 500
        else:
            # 如果不是加密盤，正常讀取二進制數據
            with open(full_path, 'rb') as f:
                content_bytes = f.read()

        # 後續處理 (DOCX 或 普通文本)
        content = ''
        if file.lower().endswith('.docx'):
            # 將二進制數據放入內存流中，讓 docx 庫讀取
            doc_stream = io.BytesIO(content_bytes)
            doc = Document(doc_stream)
            content = '\n'.join([p.text for p in doc.paragraphs])
        else:
            # 嘗試多種編碼方式將二進制數據解碼為文本
            encodings = ['utf-8', 'gbk', 'latin1']
            decoded = False
            for encoding in encodings:
                try:
                    content = content_bytes.decode(encoding)
                    decoded = True
                    break
                except UnicodeDecodeError:
                    continue
            if not decoded:
                return jsonify({'success': False, 'error': '無法識別的文件編碼'}), 500

        # 截斷過長文件
        max_length = 1024 * 1024  # 1MB
        if len(content) > max_length:
            content = content[:max_length] + f'\n\n... (文件過長，已截斷)'

        return jsonify({'success': True, 'content': content})

    except Exception as e:
        return jsonify({'success': False, 'error': f'加載協作文件時出錯: {str(e)}'})


# app.py -> 完整替換 @app.route('/api/collab/save', ...)

@app.route('/api/collab/save', methods=['POST'])
@permission_required('readwrite')
def collab_save():
    data = request.get_json()
    file = data.get('file', '').strip()
    path = data.get('path', '').strip()
    content = data.get('content', '')
    if not file:
        return jsonify({'success': False, 'error': '缺少文件名'}), 400

    full_path = os.path.abspath(os.path.join(BASE_DIRS[0], path, file))
    if not full_path.startswith(os.path.abspath(BASE_DIRS[0])):
        return jsonify({'success': False, 'error': '非法路徑'}), 403

    try:
        # [✅ 核心加密邏輯整合]
        if encryption_manager.is_path_encrypted(full_path):
            try:
                # 如果是加密盤，將文本轉為bytes，再進行加密寫入
                content_bytes = content.encode('utf-8')
                encryption_manager.write_encrypted_file(full_path, content_bytes)
            except NotUnlockedError as e:
                return jsonify({'success': False, 'error': str(e)}), 403
            except Exception as e:
                return jsonify({'success': False, 'error': f'文件加密保存失敗: {e}'}), 500
        else:
            # 如果不是加密盤，正常寫入文本
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': f'保存協作文件時出錯: {str(e)}'})

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




# ========== 管理端远程控制加密接口 ==========
@app.route('/api/internal/encryption/encrypt-disk', methods=['POST'])
def internal_encrypt_disk():
    """
    [新增] 供管理端调用：启用磁盘加密
    需在Header中携带 X-NAS-Secret 验证
    """
    secret = request.headers.get('X-NAS-Secret')
    if secret != NAS_SHARED_SECRET:
        return jsonify({"error": "权限不足"}), 403

    data = request.get_json()
    drive = data.get('drive')
    password = data.get('password')

    if not drive or not password:
        return jsonify({"error": "缺少参数"}), 400

    try:
        result = encryption_manager.encrypt_drive(drive, password)
        if result.get("success"):
            return jsonify({"success": True, "message": f"磁盘 {drive} 已启用加密"})
        else:
            return jsonify({"error": result.get("error", "加密失败")}), 500
    except Exception as e:
        return jsonify({"error": f"执行加密失败: {str(e)}"}), 500


@app.route('/api/internal/encryption/unlock-disk', methods=['POST'])
def internal_unlock_disk():
    """
    [新增] 供管理端调用：远程解锁磁盘
    """
    secret = request.headers.get('X-NAS-Secret')
    if secret != NAS_SHARED_SECRET:
        return jsonify({"error": "权限不足"}), 403

    data = request.get_json()
    drive = data.get('drive')
    password = data.get('password')

    if not drive or not password:
        return jsonify({"error": "缺少参数"}), 400

    success = encryption_manager.unlock(drive, password)
    if success:
        return jsonify({"success": True, "message": f"磁盘 {drive} 已解锁"})
    else:
        return jsonify({"error": f"磁盘 {drive} 解锁失败"}), 403


@app.route('/api/internal/encryption/decrypt-disk', methods=['POST'])
def internal_decrypt_disk():
    """
    供管理端调用：永久解密磁盘
    """
    secret = request.headers.get('X-NAS-Secret')
    if secret != NAS_SHARED_SECRET:
        return jsonify({"error": "权限不足"}), 403

    data = request.get_json()
    drive = data.get('drive')
    password = data.get('password')   # ✅ 补上密码参数

    if not drive or not password:
        return jsonify({"error": "缺少参数 drive 或 password"}), 400

    def background_task():
        try:
            result = encryption_manager.decrypt_disk_permanently(drive, password)
            print(f"[远程解密完成] {drive}: {result}")
        except Exception as e:
            print(f"[远程解密错误] {drive}: {e}")

    threading.Thread(target=background_task, daemon=True).start()
    return jsonify({"success": True, "message": f"已开始远程永久解密 {drive}。"})

# ==============================================================
# 🔒 供管理端远程调用：锁定磁盘
# ==============================================================
@app.route('/api/internal/encryption/lock-disk', methods=['POST'])
def internal_lock_disk():
    """[新增] 供管理端调用：锁定磁盘"""
    secret = request.headers.get('X-NAS-Secret')
    if secret != NAS_SHARED_SECRET:
        return jsonify({"error": "权限不足"}), 403

    data = request.get_json()
    drive = data.get('drive')
    if not drive:
        return jsonify({"error": "缺少参数 drive"}), 400

    try:
        success = encryption_manager.lock(drive)
        if success:
            print(f"[节点] 已锁定磁盘: {drive}")
            return jsonify({"success": True, "message": f"磁盘 {drive} 已锁定"})
        else:
            return jsonify({"error": f"磁盘 {drive} 锁定失败"}), 500
    except Exception as e:
        print(f"[节点] 锁定磁盘错误: {e}")
        return jsonify({"error": f"执行锁定失败: {e}"}), 500


# ==============================================================
# 🔑 供管理端远程调用：修改加密密码
# ==============================================================
@app.route('/api/internal/encryption/change-password', methods=['POST'])
def internal_change_password():
    """[新增] 供管理端调用：修改磁盘加密密码"""
    secret = request.headers.get('X-NAS-Secret')
    if secret != NAS_SHARED_SECRET:
        return jsonify({"error": "权限不足"}), 403

    data = request.get_json()
    drive = data.get('drive')
    new_password = data.get('new_password')

    if not (drive and new_password):
        return jsonify({"error": "缺少参数 drive 或 new_password"}), 400

    try:
        result = encryption_manager.set_password(drive, new_password)
        if result.get("success"):
            print(f"[节点] 磁盘 {drive} 密码修改成功")
            return jsonify({"success": True, "message": f"磁盘 {drive} 密码已更新"})
        else:
            return jsonify({"error": result.get("error", "修改密码失败")}), 500
    except Exception as e:
        print(f"[节点] 修改密码错误: {e}")
        return jsonify({"error": f"修改密码异常: {e}"}), 500




@app.route('/api/encryption/add-drive', methods=['POST'])
@permission_required('fullcontrol')
def add_encrypted_drive():
    data = request.get_json()
    drive_path = data.get('drive')
    if not drive_path:
        return jsonify({'error': '缺少磁碟路徑'}), 400

    config = encryption_manager._load_json(encryption_manager.config_path, {})

    encrypted_drives = config.get("encrypted_drives", [])
    normalized_drive = _norm_abs(drive_path)

    if normalized_drive not in encrypted_drives:
        encrypted_drives.append(normalized_drive)
        config["encrypted_drives"] = encrypted_drives

        with open(encryption_manager.config_path, "w") as f:
            json.dump(config, f, indent=2)

        # 重新加載配置
        encryption_manager.load_config()
        return jsonify({'success': True, 'message': f'磁碟 {drive_path} 已添加到加密列表'})
    else:
        return jsonify({'error': '該磁碟已在加密列表中'}), 409
@app.route('/collab-edit.html')
def collab_edit_page():
    return app.send_static_file('collab-edit.html')


# ===== OnlyOffice API =====
@app.route('/api/onlyoffice/documents', methods=['GET'])
@permission_required('readonly')
def get_onlyoffice_documents():
    """获取OnlyOffice文档列表"""
    documents = onlyoffice_manager.get_user_documents(g.user)
    return jsonify(documents)


@app.route('/api/onlyoffice/documents', methods=['POST'])
@permission_required('readwrite')
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
@permission_required('readwrite')
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
@permission_required('readonly')
def get_supported_formats():
    """获取支持的文件格式"""
    formats = onlyoffice_manager.get_supported_formats()
    return jsonify(formats)


@app.route('/api/onlyoffice/documents/<int:doc_id>/config', methods=['GET'])
@permission_required('readonly')
def get_onlyoffice_config(doc_id):
    """获取OnlyOffice编辑器配置"""
    action = request.args.get('action', 'edit')
    config = onlyoffice_manager.get_document_config(doc_id, g.user, action)

    if config:
        return jsonify(config)
    else:
        return jsonify({'error': '获取配置失败'}), 404


@app.route('/api/onlyoffice/documents/<int:doc_id>/share', methods=['POST'])
@permission_required('fullcontrol')
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
@permission_required('readonly')
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
@permission_required('readwrite')
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
@permission_required('readonly')
def get_collaboration_sessions():
    """获取用户的协作会话"""
    created_sessions = collaboration_v2.get_user_sessions(g.user)
    participating_sessions = collaboration_v2.get_participating_sessions(g.user)

    return jsonify({
        'created': created_sessions,
        'participating': participating_sessions
    })


@app.route('/api/collaboration/join', methods=['POST'])
@permission_required('readonly')
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
@permission_required('readwrite')
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
@permission_required('readonly')
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

def collect_disks():
    disks = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "mount": part.mountpoint,
                "status": "online",
                "capacity_gb": round(usage.total / (1024**3), 2),
                "is_encrypted": 0,
                "is_locked": 0
            })
        except Exception:
            continue
    return disks
def register_to_master():
    """客户端启动时主动向主控端注册"""
    global NODE_ID, MASTER_URL
    try:
        data = {
            "ip": "127.0.0.1",
            "port": 5000
        }
        res = requests.post(f"{NAS_CENTER_API_URL}/api/nodes/register", json=data, timeout=5)
        if res.status_code == 200:
            resp_json = res.json()
            NODE_ID = resp_json.get("node_id")
            MASTER_URL = f"{NAS_CENTER_API_URL}/api/nodes/update-disks"
            print(f"[注册成功] 节点ID={NODE_ID} 主控={MASTER_URL}")
            threading.Thread(target=report_disks, daemon=True).start()
        else:
            print(f"[注册失败] 管理端返回状态 {res.status_code}: {res.text}")
    except Exception as e:
        print(f"[注册异常] 无法连接管理端: {e}")

def report_disks():
    """每隔 60 秒上报一次磁盘信息"""
    while True:
        try:
            payload = {"node_id": NODE_ID, "disks": collect_disks()}
            res = requests.post(MASTER_URL, json=payload, timeout=5)
            print(f"[节点上报] {NODE_ID}: {res.status_code}")
        except Exception as e:
            print(f"[节点上报失败] {e}")
        time.sleep(60)

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

# 文件: 客户端 app.py (最末尾)

if __name__ == '__main__':
    print("✅  数据库初始化完成。")
    print("🚀  正在启动文件管理系统...")

    ohm_proc = None
    register_to_master()
    try:
        # 1. 启动 LibreHardwareMonitor
        # 👇 [核心修改] 调用新的函数名
        ohm_proc = start_librehardwaremonitor()
        fetch_nas_center_config()
        # 2. (ngrok 启动逻辑已移除)

        # 3. 打印启动信息
        print(f"🔧  Flask 服务器启动在端口: {FLASK_PORT}")
        print("=" * 50)
        print(f"🏠  本地访问地址: http://localhost:{FLASK_PORT}")
        print(f"🔗  局域网访问地址: http://您的IP地址:{FLASK_PORT}")
        if ohm_proc:
            print(f"🌡️   硬件监控服务: http://localhost:{OHM_PORT} (由程序自动管理)")
        else:
            print("⚠️   硬件监控服务启动失败，相关功能将不可用。")
        print("=" * 50)

        # 4. 启动 SocketIO 服务器
        socketio.run(app, host='0.0.0.0', port=FLASK_PORT, debug=False)

    except KeyboardInterrupt:
        print("\n👋  程序正在退出...")
    except Exception as e:
        print(f"❌  启动失败: {e}")
    finally:
        print("\n🛑  正在执行清理程序...")

        # 5. 关闭 LibreHardwareMonitor
        if ohm_proc:
            # 👇 [核心修改] 更新这里的日志信息
            print("   - 正在关闭 LibreHardwareMonitor...")
            try:
                ohm_proc.terminate()
                ohm_proc.wait(timeout=5)
                print("   ✅  LibreHardwareMonitor 已关闭。")
            except subprocess.TimeoutExpired:
                ohm_proc.kill()
                print("   ✅  LibreHardwareMonitor 已强制关闭。")
            except Exception as e:
                print(f"   ⚠️  关闭 LibreHardwareMonitor 时出错: {e}")

        # 6. (ngrok 关闭逻辑已移除)

        print("✅  清理完成, 程序已退出。")