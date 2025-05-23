from flask import Blueprint, request, jsonify, current_app, g
import jwt
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

auth_bp = Blueprint('auth', __name__, url_prefix='/api')

# 简易用户“数据库”：字典结构保存用户密码哈希和管理员标识
# 格式: users = { username: {"password_hash": "...", "is_admin": bool}, ... }
users = {}

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({"error": "缺少用户名或密码"}), 400
    username = data['username']
    password = data['password']
    if username in users:
        return jsonify({"error": "用户已存在"}), 400
    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400
    # （可选）可以在此检查 password_confirmation 等字段

    # 使用 Werkzeug 提供的函数生成密码哈希
    password_hash = generate_password_hash(password)
    # 简单规则：用户名为 "admin" 的用户设为管理员
    is_admin = True if username == 'admin' else False
    users[username] = {"password_hash": password_hash, "is_admin": is_admin}
    return jsonify({"message": "注册成功"}), 200

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({"error": "缺少用户名或密码"}), 400
    username = data['username']
    password = data['password']
    user = users.get(username)
    # 校验用户存在且密码正确
    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({"error": "用户名或密码不正确"}), 401
    # 生成 JWT Token，载荷包含用户名和是否管理员标识
    token = jwt.encode({"username": username, "is_admin": user["is_admin"]},
                       current_app.config['SECRET_KEY'], algorithm="HS256")
    # 某些 PyJWT 版本可能返回字节类型，确保转换为字符串
    if isinstance(token, bytes):
        token = token.decode('utf-8')
    return jsonify({
        "message": "登录成功",
        "token": token,
        "user": {
            "username": username,
            "is_admin": user["is_admin"]
        }
    }), 200

# 装饰器：保护路由，验证 JWT Token
def token_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # 从请求头获取 Authorization: Bearer <token>
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "认证令牌缺失"}), 401
        token = auth_header.split(None, 1)[1]  # 提取空格后的 token 部分
        try:
            data = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "认证令牌已过期"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "认证令牌无效"}), 401
        # Token 验证通过，在全局上下文 g 中记录用户信息
        g.username = data.get('username')
        g.is_admin = data.get('is_admin', False)
        return func(*args, **kwargs)
    return wrapper
