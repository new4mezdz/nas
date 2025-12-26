# 文件: backend/permission_decorator.py (完整修复版)

from functools import wraps
from flask import session, jsonify, request, g
import requests

# 定义权限级别
PERM_READONLY = 1
PERM_READWRITE = 2
PERM_FULLCONTROL = 3

PERMISSION_MAP = {
    'readonly': PERM_READONLY,
    'readwrite': PERM_READWRITE,
    'fullcontrol': PERM_FULLCONTROL
}

# 这些配置应该与 app.py 中的配置一致
NAS_CENTER_API_URL = "http://127.0.0.1:8080"
NAS_SHARED_SECRET = "your-shared-secret-key"


def check_permission_level(user_permission, required_permission):
    """
    检查用户权限是否满足要求
    user_permission: 'readonly', 'readwrite', 'fullcontrol'
    required_permission: 'readonly', 'readwrite', 'fullcontrol'
    """
    user_level = PERMISSION_MAP.get(user_permission, 0)
    required_level = PERMISSION_MAP.get(required_permission, 0)
    return user_level >= required_level


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


def permission_required(required_permission):
    """
    权限检查装饰器
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # ✅ 方案1: 来自管理端的请求，直接信任
            secret = request.headers.get('X-NAS-Secret')
            if secret == NAS_SHARED_SECRET:
                # 管理端已验证过用户登录和权限，直接放行
                return f(*args, **kwargs)

            # ✅ 方案2: 检查本地 session (本地登录用户)
            if 'user' in g and hasattr(g, 'user'):
                user_permission = session.get('file_permission', 'readonly')

                if check_permission_level(user_permission, required_permission):
                    return f(*args, **kwargs)
                else:
                    return jsonify({'error': '权限不足'}), 403

            # ✅ 方案3: 检查 Header 中的用户名并向管理端验证
            username = request.headers.get('X-NAS-Username')
            if username:
                perm_data = verify_user_permission_from_center(username)
                if perm_data and check_permission_level(perm_data['file_permission'], required_permission):
                    return f(*args, **kwargs)
                else:
                    return jsonify({'error': '权限不足或验证失败'}), 403

            # 如果都不满足，返回未授权
            return jsonify({'error': '未登录或未授权'}), 401

        return decorated_function

    return decorator