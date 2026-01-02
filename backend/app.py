# app.py
# -*- coding: utf-8 -*-
"""
NAS 客户端主程序 (精简重构版)
路由已拆分到 routes/ 目录
"""

# ===== 标准库 =====
import os
import sys
import json
import time
import glob
import subprocess
import tempfile
import threading
from pathlib import Path
from datetime import datetime, timedelta

# ===== 第三方库 =====
import requests
from flask import (
    Flask, request, jsonify, send_file, send_from_directory,
    g, make_response, session
)
from flask_socketio import SocketIO

# ===== 项目模块 =====
from common import get_db, get_available_drives, _is_ec_volume
from auth import init_auth
from permission_decorator import permission_required

# EC 纠删码
from ec_engine.rs_systematic import encode as rs_encode

# 存储池 & 加密
import Storage_pool
from encryption import EncryptionManager

# ===== 新模块导入 =====
from config import (
    BACKEND_DIR, EC_CFG_PATH, EC_IDX_PATH, ENCRYPTION_CFG_PATH,
    NODE_CONFIG_PATH, FLASK_PORT, OHM_PORT, FlaskConfig,
    runtime_config, SOFFICE_PATH
)
from services import load_json, save_json, decode_from_dict
from sockets import init_collaboration_events
from tasks import (
    register_to_master, fetch_nas_center_config,
    update_nas_center_url_periodically, start_cleanup_thread
)
from tasks.node_reporter import load_node_config, save_node_config


# ==================== Flask 应用初始化 ====================
app = Flask(__name__, static_folder="../static", static_url_path="/static")
app.config.from_object(FlaskConfig)

# 初始化认证
init_auth(app)

# 初始化 SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# 注册 WebSocket 事件
init_collaboration_events(socketio)

# 初始化加密管理器
encryption_manager = EncryptionManager(config_path=ENCRYPTION_CFG_PATH)

# 预览会话存储
preview_sessions = {}


# ==================== 数据库初始化 ====================
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


def init_collab_share_table():
    db = get_db()
    db.execute('''
        CREATE TABLE IF NOT EXISTS collab_shares (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            share_id TEXT UNIQUE NOT NULL,
            file_path TEXT NOT NULL,
            guest_prefix TEXT DEFAULT '访客',
            expire_at DATETIME,
            created_by TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    db.commit()


def init_user_data_tables():
    db = get_db()
    db.execute('''
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            path TEXT NOT NULL,
            name TEXT NOT NULL,
            is_dir BOOLEAN,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, path)
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS recent_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            path TEXT NOT NULL,
            name TEXT NOT NULL,
            is_dir BOOLEAN,
            accessed_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    db.commit()


# 初始化数据库表
with app.app_context():
    init_share_table()
    init_user_data_tables()
    init_collab_share_table()


# ==================== 注册路由蓝图 ====================
from routes import (
    user_bp, init_user_routes,
    system_bp, init_system_routes,
    setup_bp, init_setup_routes,
    auth_bp, init_auth_routes,
    admin_bp, init_admin_routes,
    share_bp, init_share_routes,
    encryption_bp, init_encryption_routes,
    pool_bp, init_pool_routes,
    ec_bp, init_ec_routes,
    file_bp, init_file_routes,
)

# 初始化各路由模块的依赖
init_system_routes(
    load_json=load_json,
    ec_cfg_path=EC_CFG_PATH,
    load_node_config=load_node_config,
    this_node_id=runtime_config.this_node_id,
    center_public_url=runtime_config.nas_center_public_url,
    center_api_url=runtime_config.nas_center_api_url,
    encryption_manager=encryption_manager  # 添加这行
)

init_setup_routes(
    save_node_config=save_node_config,
    load_node_config=load_node_config,
    flask_port=FLASK_PORT
)

init_auth_routes(
    this_node_id=runtime_config.this_node_id,
    center_api_url=runtime_config.nas_center_api_url,
    shared_secret=runtime_config.nas_shared_secret
)

init_admin_routes(
    center_api_url=runtime_config.nas_center_api_url,
    shared_secret=runtime_config.nas_shared_secret
)

init_share_routes(
    ec_cfg_path=EC_CFG_PATH,
    ec_idx_path=EC_IDX_PATH,
    this_node_id=runtime_config.this_node_id,
    center_public_url=runtime_config.nas_center_public_url,
    load_json=load_json,
    save_json=save_json,
    decode_from_dict=decode_from_dict,
    encryption_manager=encryption_manager,
    storage_pool=Storage_pool,
    rs_encode=rs_encode
)

init_encryption_routes(
    encryption_manager=encryption_manager,
    shared_secret=runtime_config.nas_shared_secret,
    load_json=load_json,
    save_json=save_json
)

init_pool_routes(
    storage_pool=Storage_pool,
    encryption_manager=encryption_manager
)

init_ec_routes(
    ec_cfg_path=EC_CFG_PATH,
    ec_idx_path=EC_IDX_PATH,
    shared_secret=runtime_config.nas_shared_secret,
    load_json=load_json,
    save_json=save_json,
    decode_from_dict=decode_from_dict,
    rs_encode=rs_encode
)

init_file_routes(
    ec_cfg_path=EC_CFG_PATH,
    ec_idx_path=EC_IDX_PATH,
    load_json=load_json,
    save_json=save_json,
    decode_from_dict=decode_from_dict,
    rs_encode=rs_encode,
    encryption_manager=encryption_manager,
    storage_pool=Storage_pool
)


# ==================== 代理前缀处理 ====================
# ==================== 代理前缀处理 ====================
@app.before_request
def strip_proxy_prefix():
    """移除代理前缀，使路由正常工作"""
    import re
    path = request.path
    print(f"[DEBUG] 原始请求路径: {path}")  # 添加调试
    # 匹配 /proxy/node/xxx/ 前缀
    match = re.match(r'^/proxy/node/[^/]+(/.*)', path)
    if match:
        new_path = match.group(1)
        print(f"[DEBUG] 重写路径为: {new_path}")  # 添加调试
        request.environ['PATH_INFO'] = new_path
# 注册蓝图
app.register_blueprint(user_bp)
app.register_blueprint(system_bp)
app.register_blueprint(setup_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(share_bp)
app.register_blueprint(encryption_bp)
app.register_blueprint(pool_bp)
app.register_blueprint(ec_bp)
app.register_blueprint(file_bp)

# 兼容旧的文件管理蓝图
from filemanager import file_bp as filemanager_bp
app.register_blueprint(filemanager_bp)


# ==================== 特殊路由（无法移动到蓝图的） ====================

@app.route('/static/pwa/manifest.json')
def pwa_manifest():
    """PWA应用清单"""
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
            {"src": "/static/pwa/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/static/pwa/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}
        ]
    }
    response = jsonify(manifest_data)
    response.headers['Content-Type'] = 'application/manifest+json'
    response.headers['Cache-Control'] = 'public, max-age=86400'
    return response


@app.route('/static/pwa/sw.js')
def pwa_service_worker():
    """PWA Service Worker"""
    response = send_from_directory('../client/pwa', 'sw.js', mimetype='application/javascript')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@app.route('/favicon.ico')
def favicon():
    """网站图标"""
    return send_from_directory('../static/pwa/icons', 'icon-192.png', mimetype='image/png')


@app.route('/api/office/convert-pdf', methods=['GET'])
@permission_required('readonly')
def api_convert_to_pdf():
    """将 Office 文件转换为 PDF 预览"""
    file_path = request.args.get('path', '')
    if not file_path:
        return jsonify({"error": "缺少 path 参数"}), 400

    # 处理池路径
    if file_path.startswith('pool://'):
        try:
            path_part = file_path[7:]
            parts = path_part.split('/', 1)
            volume = parts[0]
            subpath = parts[1] if len(parts) > 1 else ''
            filename = subpath.split('/')[-1] if '/' in subpath else subpath
            virtual_path = f"{volume}/{subpath}" if subpath else volume
            actual_path = Storage_pool.get_file_path(virtual_path)
        except Exception as e:
            return jsonify({"error": str(e)}), 404
    else:
        actual_path = file_path

    if not os.path.exists(actual_path):
        return jsonify({"error": "文件不存在"}), 404

    temp_dir = tempfile.mkdtemp()
    try:
        cmd = [SOFFICE_PATH, '--headless', '--convert-to', 'pdf', '--outdir', temp_dir, actual_path]
        result = subprocess.run(cmd, capture_output=True, timeout=120)

        if result.returncode != 0:
            return jsonify({"error": "转换失败", "detail": result.stderr.decode('utf-8', errors='ignore')}), 500

        pdf_files = glob.glob(os.path.join(temp_dir, '*.pdf'))
        if not pdf_files:
            return jsonify({"error": "未生成 PDF 文件"}), 500

        with open(pdf_files[0], 'rb') as f:
            pdf_data = f.read()

        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

        response = make_response(pdf_data)
        response.headers['Content-Type'] = 'application/pdf'
        return response

    except subprocess.TimeoutExpired:
        return jsonify({"error": "转换超时"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== 硬件监控启动 ====================
PROJECT_ROOT = Path(__file__).parent
OHM_PATH = str(PROJECT_ROOT / 'LibreHardwareMonitor-net472' / 'LibreHardwareMonitor.exe')
LO_LAUNCHER_PATH = os.path.join(BACKEND_DIR, 'tool', 'LibreOfficePortable', 'LibreOfficePortable.exe')


def is_admin():
    """检查是否以管理员权限运行"""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def run_as_admin(script_path):
    """请求管理员权限并重新启动脚本"""
    try:
        import ctypes
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, script_path, None, 1
        )
        return result > 32
    except Exception as e:
        print(f"请求管理员权限失败: {e}")
        return False


def start_librehardwaremonitor():
    """启动 LibreHardwareMonitor，自动处理权限问题"""
    print("🌡️  正在启动 LibreHardwareMonitor...")

    # 检查是否已在运行
    try:
        response = requests.get(f'http://localhost:{OHM_PORT}/data.json', timeout=2)
        if response.status_code == 200:
            print("✅  LibreHardwareMonitor 已在运行！")
            return "already_running"
    except:
        pass

    if not os.path.exists(OHM_PATH):
        print(f"⚠️  LibreHardwareMonitor.exe 未找到: {OHM_PATH}")
        return None

    # 清理旧进程
    try:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/F', '/IM', 'LibreHardwareMonitor.exe'],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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

        # 等待服务就绪
        for i in range(15):
            time.sleep(1)
            try:
                response = requests.get(f'http://localhost:{OHM_PORT}/data.json', timeout=2)
                if response.status_code == 200:
                    print(f"✅  LibreHardwareMonitor 已就绪")
                    return ohm_proc
            except:
                continue

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
                    return None

        print(f'❌  LibreHardwareMonitor 启动失败: {e}')
        return None


def start_libreoffice_service():
    """启动 LibreOffice Portable"""
    print("📄  正在启动 LibreOffice Portable...")

    if not os.path.exists(LO_LAUNCHER_PATH):
        print(f"⚠️  LibreOffice Portable 未找到: {LO_LAUNCHER_PATH}")
        return None

    try:
        if os.name == 'nt':
            DETACHED_PROCESS = 0x00000008
            CREATE_NO_WINDOW = 0x08000000
            flags = DETACHED_PROCESS | CREATE_NO_WINDOW
        else:
            flags = 0

        lo_proc = subprocess.Popen(
            [LO_LAUNCHER_PATH],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=flags if os.name == 'nt' else 0
        )
        print("✅  LibreOffice Portable 已启动")
        return lo_proc
    except Exception as e:
        print(f"⚠️  LibreOffice 启动失败: {e}")
        return None


def verify_master_connection(config):
    """验证管理端连接"""
    try:
        resp = requests.post(
            f"{config['master_url']}/api/nodes/verify-secret",
            json={"node_id": config.get('node_id'), "secret": config.get('shared_secret')},
            timeout=5
        )
        if resp.status_code == 200:
            return True
        elif resp.status_code in [401, 403]:
            return False
        return None
    except:
        return None


# ==================== 主程序入口 ====================
if __name__ == '__main__':
    print("✅  数据库初始化完成")
    print("🚀  正在启动文件管理系统...")

    # 启动会话清理线程
    start_cleanup_thread()

    # 加载节点配置
    node_config = load_node_config()
    need_setup = False

    if not node_config:
        print("🔧  未找到配置文件，进入首次配置模式...")
        need_setup = True
    else:
        print("🔍  正在验证管理端连接密钥...")
        check_result = verify_master_connection(node_config)
        if check_result is False:
            print("🚫  密钥验证失败！进入配置模式。")
            need_setup = True

    if need_setup:
        # ========== 配置向导模式 ==========
        app.config['SETUP_MODE'] = True
        try:
            print(f"🔧  配置服务启动在端口: {FLASK_PORT}")
            print("=" * 50)
            print(f"🏠  请访问: http://localhost:{FLASK_PORT} 进行配置")
            print("=" * 50)
            socketio.run(app, host='0.0.0.0', port=FLASK_PORT, debug=False)
        except KeyboardInterrupt:
            print("\n👋  程序正在退出...")
        except Exception as e:
            print(f"❌  启动失败: {e}")

    else:
        # ========== 正常启动模式 ==========
        # 加载运行时配置
        runtime_config.load_from_node_config(node_config)

        print(f"📡  管理端地址: {runtime_config.nas_center_api_url}")
        print(f"🆔  节点ID: {runtime_config.this_node_id}")

        ohm_proc = None
        lo_proc = None

        # 注册到管理端
        register_to_master()

        try:
            # 启动硬件监控
            ohm_proc = start_librehardwaremonitor()

            # 启动 LibreOffice
            lo_proc = start_libreoffice_service()

            # 获取公网配置
            fetch_nas_center_config()

            # 启动定期更新线程
            update_thread = threading.Thread(target=update_nas_center_url_periodically, daemon=True)
            update_thread.start()
            print("✅  已启动公网地址定期更新任务")

            # 打印启动信息
            print(f"🔧  Flask 服务器启动在端口: {FLASK_PORT}")
            print("=" * 50)
            print(f"🏠  本地访问: http://localhost:{FLASK_PORT}")
            print(f"🔗  局域网访问: http://您的IP:{FLASK_PORT}")
            if ohm_proc:
                print(f"🌡️  硬件监控: http://localhost:{OHM_PORT}")
            if lo_proc:
                print(f"📄  文档预览: LibreOffice 已就绪")
            print("=" * 50)

            # 启动服务器
            socketio.run(app, host='0.0.0.0', port=FLASK_PORT, debug=False)

        except KeyboardInterrupt:
            print("\n👋  程序正在退出...")
        except Exception as e:
            print(f"❌  启动失败: {e}")
        finally:
            print("\n🛑  正在清理...")

            if ohm_proc and ohm_proc != "already_running":
                try:
                    ohm_proc.terminate()
                    ohm_proc.wait(timeout=5)
                    print("   ✅  LibreHardwareMonitor 已关闭")
                except:
                    pass

            if lo_proc and lo_proc != "already_running":
                try:
                    lo_proc.terminate()
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/F', '/IM', 'soffice.bin'],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    print("   ✅  LibreOffice 已关闭")
                except:
                    pass

            print("✅  清理完成")
