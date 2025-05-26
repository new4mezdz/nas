import os
import sqlite3
from flask import Flask, request, jsonify, send_from_directory, g
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from functools import wraps
from datetime import datetime, timedelta
import  mimetypes
from flask import send_file
import secrets
import subprocess
import time
import requests
import os
from common import BASE_DIR, get_db
# ===== 配置 =====
app = Flask(__name__, static_folder="../static", static_url_path="/static")
app.config['SECRET_KEY'] = 'super-secret-key'  # 建议换成更随机的密钥



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
        registered_at TEXT NOT NULL
    )''')
    # 保证有一个admin账号
    cur = db.execute("SELECT COUNT(*) FROM users WHERE is_admin=1", ())
    if cur.fetchone()[0] == 0:
        db.execute(
            "INSERT INTO users (username, password, is_admin, is_active, registered_at) VALUES (?, ?, ?, ?, ?)",
            ("admin", generate_password_hash("admin123"), 1, 1, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
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

# ===== JWT认证 =====
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
                data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
                db = get_db()
                cur = db.execute("SELECT * FROM users WHERE id=?", (data['id'],))
                user = cur.fetchone()
                if not user or not user['is_active']:
                    return jsonify({'error': '无效Token'}), 401
                if admin_only and not user['is_admin']:
                    return jsonify({'error': '管理员权限不足'}), 403
                g.user = user
            except Exception as e:
                return jsonify({'error': 'Token无效'}), 401
            return f(*args, **kwargs)
        return decorated
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
            "INSERT INTO users (username, password, is_admin, is_active, registered_at) VALUES (?, ?, 0, 1, ?)",
            (username, generate_password_hash(password), datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
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
    if user['id'] == g.user['id']:
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

# ===== 系统/磁盘信息接口 =====
from utils import get_sys_info, get_disk_info

@app.route('/api/system', methods=['GET'])
@token_required()
def api_system():
    return jsonify(get_sys_info())

@app.route('/api/disk', methods=['GET'])
@token_required()
def api_disk():
    return jsonify(get_disk_info())

# ===== 注册文件管理蓝图 =====
from filemanager import file_bp
app.register_blueprint(file_bp)

# ===== 静态页面路由 =====
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

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
    cur = db.execute("SELECT * FROM users WHERE id=?", (g.user['id'],))
    user = cur.fetchone()
    if not check_password_hash(user['password'], old):
        return jsonify({"error": "原密码错误"}), 400
    db.execute("UPDATE users SET password=? WHERE id=?", (generate_password_hash(new), g.user['id']))
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

@app.route('/api/batch_delete', methods=['POST'])
@token_required(admin_only=True)   # 或普通用户，按你的需求改
def batch_delete():
    data = request.get_json()
    paths = data.get('paths', [])
    errors = []
    for path in paths:
        try:
            abspath = safe_join(BASE_DIR, path.lstrip("/\\"))
            if not abspath.startswith(BASE_DIR):
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
def preview_file():
    path = request.args.get('path', '').lstrip('/\\')
    abs_path = os.path.abspath(os.path.join(BASE_DIR, path))
    if not abs_path.startswith(BASE_DIR) or not os.path.exists(abs_path):
        return jsonify({'error': '文件不存在'}), 404
    mime = mimetypes.guess_type(abs_path)[0] or 'application/octet-stream'
    return send_file(abs_path, mimetype=mime)


@app.route('/api/mkdir', methods=['POST'])
@token_required()
def mkdir():
    data = request.get_json()
    parent = data.get('parent', '/')
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': '文件夹名不能为空'}), 400
    # 拼接路径并校验
    safe_parent = parent.lstrip('/\\')
    abs_path = os.path.abspath(os.path.join(BASE_DIR, safe_parent, name))
    if not abs_path.startswith(BASE_DIR):
        return jsonify({'error': '路径非法'}), 400
    try:
        os.makedirs(abs_path, exist_ok=False)
        return jsonify({'success': True})
    except FileExistsError:
        return jsonify({'error': '文件夹已存在'}), 400
    except Exception as e:
        return jsonify({'error': '创建失败: ' + str(e)}), 500


@app.route('/api/share', methods=['POST'])
@token_required()
def create_share():
    data = request.get_json()
    file_path = data.get('file_path', '')
    expire_hours = int(data.get('expire_hours', 24))
    password = data.get('password', '')

    abs_path = os.path.abspath(os.path.join(BASE_DIR, file_path.lstrip('/\\')))
    if not abs_path.startswith(BASE_DIR) or not os.path.exists(abs_path):
        return jsonify({'error': '文件不存在'}), 404

    token = secrets.token_urlsafe(16)
    expire_at = datetime.now() + timedelta(hours=expire_hours)
    db = get_db()
    db.execute(
        "INSERT INTO share_links (file_path, token, password, expire_at) VALUES (?, ?, ?, ?)",
        (file_path, token, password, expire_at.strftime('%Y-%m-%d %H:%M:%S'))
    )
    db.commit()

    # 返回外链地址（相对地址 + ngrok 公网完整地址）
    return jsonify({
        'success': True,
        'share_url': f'/share/{token}',  # 相对地址
        'full_url': f'{ngrok_url_global}/share/{token}' if ngrok_url_global else None  # 公网地址
    })


@app.route('/share/<token>', methods=['GET', 'POST'])
def access_share(token):
    db = get_db()
    row = db.execute("SELECT * FROM share_links WHERE token=?", (token,)).fetchone()
    if not row:
        return "链接无效或已删除", 404

    # 检查过期
    if row['expire_at'] and datetime.strptime(row['expire_at'], '%Y-%m-%d %H:%M:%S') < datetime.now():
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
                <form method="post">
                  请输入分享密码：<input name="password" type="password"/>
                  <button type="submit">提交</button>
                </form>
            '''
    # 密码通过，返回文件
    abs_path = os.path.abspath(os.path.join(BASE_DIR, row['file_path'].lstrip('/\\')))
    if not abs_path.startswith(BASE_DIR) or not os.path.exists(abs_path):
        return "文件不存在", 404
    return send_file(abs_path, as_attachment=True)

@app.route('/api/ngrok-url')
def api_ngrok_url():
    if ngrok_url_global:
        return jsonify({'url': ngrok_url_global})
    return jsonify({'error': 'ngrok 地址暂不可用'}), 503

# ===== NGROK 配置 =====
NGROK_PATH = r'D:\nas_data\ngrok.exe'
FLASK_PORT = 5000

ngrok_url_global = None  # 👈 全局变量保存公网地址

def start_ngrok():
    global ngrok_url_global
    print("⚙️ 正在启动 ngrok...")
    ngrok_proc = subprocess.Popen(
        [NGROK_PATH, 'http', str(FLASK_PORT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    time.sleep(2)
    ngrok_url = None

    for i in range(10):
        try:
            print(f"⌛ 尝试获取 ngrok 地址（第 {i+1} 次）")
            r = requests.get(
                'http://127.0.0.1:4040/api/tunnels',
                headers={"Accept": "application/json"},  # ✅ 加上这个
                timeout=2
            ).json()
            for t in r.get('tunnels', []):
                if t['proto'] == 'https':
                    ngrok_url = t['public_url']
                    break
            if ngrok_url:
                break
        except Exception as e:
            print("❌ 获取地址时异常:", e)
            time.sleep(1)

    if ngrok_url:
        print('✅ ngrok 公网地址:', ngrok_url)
        ngrok_url_global = ngrok_url  # ✅ 保存下来
    else:
        print('❌ ngrok 启动成功但未获取到公网地址，请手动访问 http://127.0.0.1:4040')

    return ngrok_url, ngrok_proc

# ========== 你的 Flask 路由、逻辑在这里 ==========


# ===== 主启动入口 =====
if __name__ == '__main__':
    ngrok_url, ngrok_proc = start_ngrok()
    try:
        app.run(host='0.0.0.0', port=FLASK_PORT, debug=False)
    finally:
        ngrok_proc.terminate()
