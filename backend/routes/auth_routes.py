# routes/auth_routes.py
import secrets
import requests
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session, g, make_response, send_from_directory, redirect, current_app
import jwt
import os
import shutil
import time
import tarfile
import io
from common import get_db

auth_bp = Blueprint('auth', __name__)

# 外部依赖
_ctx = {
    'THIS_NODE_ID': None,
    'NAS_CENTER_API_URL': None,
    'NAS_SHARED_SECRET': None,
}


def init_auth_routes(this_node_id, center_api_url, shared_secret):
    _ctx['THIS_NODE_ID'] = this_node_id
    _ctx['NAS_CENTER_API_URL'] = center_api_url
    _ctx['NAS_SHARED_SECRET'] = shared_secret


@auth_bp.route('/desktop')
def desktop_page():
    """管理端跳转入口 - 显示桌面页面"""
    if not hasattr(g, 'user') or not g.user:
        print("❌ 未登录或 session 已失效")
        return redirect(f'http://127.0.0.1:8080/login?redirect=client&node_id={_ctx["THIS_NODE_ID"]}')

    static_folder = current_app.static_folder or 'static'
    response = make_response(send_from_directory(static_folder, "desktop.html"))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@auth_bp.route('/api/check-session', methods=['GET'])
def check_session():
    """检查当前 session 是否有效"""
    if session.get('authenticated') and 'user_id' in session:
        return jsonify({
            "authenticated": True,
            "username": session.get('username'),
            "role": session.get('role'),
            "file_permission": session.get('file_permission')
        })
    else:
        return jsonify({"authenticated": False}), 401


@auth_bp.route('/api/current-user', methods=['GET'])
def get_current_user():
    """获取当前登录用户信息"""
    try:
        user_id = g.get('user')

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


@auth_bp.route('/api/sso-login', methods=['POST'])
def sso_login():
    """使用SSO令牌登录"""
    data = request.json
    sso_token = data.get('sso_token')

    try:
        payload = jwt.decode(sso_token, current_app.config['SECRET_KEY'], algorithms=['HS256'])

        if payload.get('type') != 'sso_access':
            return jsonify({'error': '无效的令牌类型'}), 401

        username = payload.get('username')

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

        if not user:
            # 自动创建用户
            random_password = secrets.token_urlsafe(32)
            from werkzeug.security import generate_password_hash
            hashed = generate_password_hash(random_password)
            db.execute(
                "INSERT INTO users (username, password, is_admin) VALUES (?, ?, 0)",
                (username, hashed)
            )
            db.commit()
            user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

        regular_token = jwt.encode({
            'user_id': user['id'],
            'username': user['username'],
            'exp': datetime.utcnow() + timedelta(hours=24)
        }, current_app.config['SECRET_KEY'], algorithm='HS256')

        return jsonify({
            'user': {
                'username': user['username'],
                'is_admin': bool(user['is_admin']),
                'file_permission': user.get('file_permission', 'readonly')
            },
            'token': regular_token
        })

    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'SSO令牌已过期'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': '无效的SSO令牌'}), 401


@auth_bp.route('/api/verify-access-token', methods=['POST'])
def verify_access_token_proxy():
    """转发令牌验证请求到管理端"""
    try:
        response = requests.post(
            f"{_ctx['NAS_CENTER_API_URL']}/api/verify-access-token",
            json=request.json,
            timeout=10
        )
        return jsonify(response.json()), response.status_code
    except Exception as e:
        print(f"[ERROR] 转发失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============ 客户端同步接口 ============
import os
import tarfile
import io
import shutil
import time

# 需要排除的文件/目录（不参与同步）
# 需要排除的文件/目录（不参与同步）
EXCLUDE_PATTERNS = [
    '__pycache__',
    '.git',
    '*.pyc',
    '*.db',
    '*.json',
    'logs',
    'backup_*',
    '*.log',
]


def should_exclude(name):
    """检查文件是否应该排除"""
    import fnmatch
    for pattern in EXCLUDE_PATTERNS:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


@auth_bp.route('/api/client-files', methods=['GET'])
def list_client_files():
    """列出客户端目录下的文件（供管理端选择性同步使用）"""
    if request.headers.get('X-NAS-Secret') != _ctx['NAS_SHARED_SECRET']:
        return jsonify({'error': '认证失败'}), 401

    try:
        # 获取客户端根目录
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        files = []
        for item in os.listdir(backend_dir):
            if should_exclude(item):
                continue

            item_path = os.path.join(backend_dir, item)
            files.append({
                'name': item,
                'path': item,
                'isDir': os.path.isdir(item_path),
                'size': os.path.getsize(item_path) if os.path.isfile(item_path) else 0
            })

        # 按类型和名称排序
        files.sort(key=lambda x: (not x['isDir'], x['name'].lower()))

        return jsonify({'success': True, 'files': files})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/api/export-client', methods=['GET'])
def export_client():
    """导出客户端代码包（供管理端拉取）"""
    if request.headers.get('X-NAS-Secret') != _ctx['NAS_SHARED_SECRET']:
        return jsonify({'error': '认证失败'}), 401

    try:
        from flask import send_file

        # 获取客户端根目录
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # 检查是否选择性同步
        selected_files = request.args.get('files', '')
        selected_list = [f.strip() for f in selected_files.split(',') if f.strip()] if selected_files else []

        # 创建 tar.gz 包
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as tar:
            for item in os.listdir(backend_dir):
                # 排除不需要同步的文件
                if should_exclude(item):
                    continue

                # 如果指定了文件列表，只打包选中的
                if selected_list and item not in selected_list:
                    continue

                item_path = os.path.join(backend_dir, item)
                tar.add(item_path, arcname=item)

        buf.seek(0)
        return send_file(
            buf,
            mimetype='application/gzip',
            as_attachment=True,
            download_name='client.tar.gz'
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/api/receive-update', methods=['POST'])
def receive_update():
    """接收并应用客户端更新"""
    if request.headers.get('X-NAS-Secret') != _ctx['NAS_SHARED_SECRET']:
        return jsonify({'error': '认证失败'}), 401

    try:
        pkg = request.files.get('package')
        if not pkg:
            return jsonify({'error': '没有收到更新包'}), 400

        do_backup = request.form.get('backup', '1') == '1'

        # 获取客户端根目录
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # 备份当前版本
        if do_backup:
            backup_dir = os.path.join(backend_dir, f'backup_{int(time.time())}')
            os.makedirs(backup_dir, exist_ok=True)

            for item in os.listdir(backend_dir):
                if should_exclude(item) or item.startswith('backup_'):
                    continue
                src = os.path.join(backend_dir, item)
                dst = os.path.join(backup_dir, item)
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)

            print(f"[UPDATE] 已备份到 {backup_dir}")

        # 解压覆盖
        with tarfile.open(fileobj=pkg.stream, mode='r:gz') as tar:
            # 安全检查：防止路径遍历攻击
            for member in tar.getmembers():
                if member.name.startswith('/') or '..' in member.name:
                    return jsonify({'error': '非法的文件路径'}), 400

            tar.extractall(backend_dir)

        print(f"[UPDATE] 客户端更新完成")

        return jsonify({
            'success': True,
            'message': '更新完成，请重启服务生效',
            'backup': backup_dir if do_backup else None
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

