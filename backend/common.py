import os
import sqlite3
from functools import wraps
from flask import request, jsonify, g, current_app
import jwt

# ========= ✅ 不再依赖 app.py =========
DATABASE = os.path.join(os.path.dirname(__file__), 'nas.db')
BASE_DIR = r"D:\nas_data"

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
