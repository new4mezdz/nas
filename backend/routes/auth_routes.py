# routes/auth_routes.py
import secrets
import requests
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session, g, make_response, send_from_directory, redirect, current_app
import jwt

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


