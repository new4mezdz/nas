# 文件: backend/auth.py (完整修复版)

from flask import request, jsonify, session, g
from functools import wraps
import jwt
from datetime import datetime, timedelta

# ⚠️ 这个密钥必须与管理端完全一致
ACCESS_TOKEN_SECRET = 'your-access-token-secret-key'


def verify_access_token(token):
    """
    验证访问令牌
    返回: payload (dict) 或 None
    """
    try:
        payload = jwt.decode(token, ACCESS_TOKEN_SECRET, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        print("[AUTH] 令牌已过期")
        return None
    except jwt.InvalidTokenError as e:
        print(f"[AUTH] 令牌无效: {e}")
        return None
    except Exception as e:
        print(f"[AUTH] 验证令牌时出错: {e}")
        return None


def load_user():
    """
    在每个请求之前加载用户信息
    支持三种认证方式:
    1. Session (本地登录)
    2. URL参数中的token (管理端跳转)
    3. Authorization Header (API调用)
    """
    g.user = None

    # 方式1: 检查 session (本地登录)
    if 'user' in session:
        g.user = session['user']
        return

    # 方式2: 检查 URL 参数中的 token (管理端跳转)
    token = request.args.get('token')

    # 方式3: 检查 Authorization Header (API调用)
    if not token:
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header[7:]  # 移除 "Bearer " 前缀

    # 如果找到 token,验证它
    if token:
        payload = verify_access_token(token)

        if payload:
            # 从 payload 中提取用户信息
            g.user = payload.get('user_id')

            # 将用户信息存入 session (保持登录状态)
            session['user'] = g.user
            session['username'] = payload.get('username')
            session['file_permission'] = payload.get('file_permission', 'readonly')
            session['role'] = payload.get('role', 'user')


def login_required(f):
    """
    登录验证装饰器
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.user:
            return jsonify({'error': '未登录'}), 401
        return f(*args, **kwargs)

    return decorated_function


def init_auth(app):
    """
    初始化认证系统
    """
    # 注册请求前钩子
    app.before_request(load_user)

    # 注册登录路由
    @app.route('/api/login', methods=['POST'])
    def login():
        """本地登录接口"""
        from flask import current_app
        data = request.json
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return jsonify({'error': '用户名和密码不能为空'}), 400

        # 这里需要连接到你的用户数据库
        # 示例代码,需要根据实际情况修改
        from common import get_db
        db = get_db()

        user = db.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        if not user:
            return jsonify({'error': '用户不存在'}), 401

        # 验证密码 (假设你使用了 werkzeug 的密码哈希)
        from werkzeug.security import check_password_hash
        if not check_password_hash(user['password'], password):
            return jsonify({'error': '密码错误'}), 401

        # 登录成功,设置 session
        session['user'] = user['id']
        session['username'] = user['username']
        session['file_permission'] = user.get('file_permission', 'readonly')
        session['is_admin'] = bool(user.get('is_admin', 0))

        return jsonify({
            'success': True,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'file_permission': session['file_permission'],
                'is_admin': session['is_admin']
            }
        })

    @app.route('/api/logout', methods=['POST'])
    def logout():
        """登出接口"""
        session.clear()
        return jsonify({'success': True})

    @app.route('/api/current-user', methods=['GET'])
    def current_user():
        """获取当前登录用户"""
        if g.user:
            role = session.get('role', 'user')
            return jsonify({
                'user': {
                    'id': g.user,
                    'username': session.get('username'),
                    'file_permission': session.get('file_permission', 'readonly'),
                    'role': role,
                    'is_admin': (role == 'admin')
                }
            })
        return jsonify({'user': None}), 401

    print("[AUTH] 认证系统初始化完成")