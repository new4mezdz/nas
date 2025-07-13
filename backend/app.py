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
from common import BASE_DIRS, get_db, get_available_drives, is_path_allowed, get_base_dir_for_path
from common import convert
from filemanager import safe_join

import json
from ec_engine import encode, decode, ECError
from docx2pdf import convert

from reedsolo import RSCodec
from flask_socketio import SocketIO
from collaboration import CollaborationManager
from collaboration_v2 import CollaborationV2
from onlyoffice import OnlyOfficeManager
from docx import Document
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

# ===== JWT认证 =====
def token_required(admin_only=False):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = None

            # ✅ 优先从请求头中读取 token
            if 'Authorization' in request.headers:
                parts = request.headers['Authorization'].split()
                if len(parts) == 2 and parts[0] == 'Bearer':
                    token = parts[1]

            # ✅ 如果请求头没有，再从 URL 参数中读取
            if not token:
                token = request.args.get('token')

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
                print("❌ Token 验证失败:", e)  # 临时调试建议保留
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
    db.execute("UPDATE users SET current_directory=? WHERE id=?", (directory, g.user['id']))
    db.commit()
    
    return jsonify({'success': True, 'current_directory': directory})

# 获取用户当前目录
@app.route('/api/current-directory', methods=['GET'])
@token_required()
def get_current_directory():
    db = get_db()
    cur = db.execute("SELECT current_directory FROM users WHERE id=?", (g.user['id'],))
    user = cur.fetchone()
    return jsonify({'current_directory': user['current_directory'] or ''})

# ===== 系统/磁盘信息接口 =====
from utils import get_sys_info, get_disk_info
import shutil

@app.route('/api/system', methods=['GET'])
@token_required()
def api_system():
    return jsonify(get_sys_info())

@app.route('/api/disk', methods=['GET'])
@token_required()
def api_disk():
    return jsonify(get_disk_info())

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

# ===== 注册文件管理蓝图 =====
from filemanager import file_bp
app.register_blueprint(file_bp)

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
@token_required()
def preview_file():
    path = request.args.get('path', '').lstrip('/\\')
    print(f"[DEBUG] 预览请求路径: {path}")
    
    # 使用新的多盘符支持逻辑
    base_dir = get_base_dir_for_path(path)
    print(f"[DEBUG] 匹配的base_dir: {base_dir}")
    
    if not base_dir:
        return jsonify({'error': '路径不在允许的目录中'}), 400
    
    # 修复路径处理逻辑
    if path.startswith(base_dir):
        # 如果path已经包含base_dir，直接使用
        abs_path = os.path.abspath(path)
    else:
        # 否则拼接路径
        abs_path = os.path.abspath(os.path.join(base_dir, path.lstrip('/')))
    
    print(f"[DEBUG] 最终绝对路径: {abs_path}")
    print(f"[DEBUG] 文件是否存在: {os.path.exists(abs_path)}")
    
    if not os.path.exists(abs_path):
        return jsonify({'error': '文件不存在'}), 404

    ext = os.path.splitext(abs_path)[1].lower()

    # ===== 1. DOCX: 直接返回原文件 =====
    if ext == '.docx':
        return send_file(abs_path, mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')

    # ===== 2. 文本类文件（纯文本返回） =====
    elif ext in ['.txt', '.log', '.md', '.py', '.js', '.html', '.json', '.css', '.csv']:
        try:
            # 首先读取文件的二进制内容
            with open(abs_path, 'rb') as f:
                raw_content = f.read()
            
            print(f"[DEBUG] 文件大小: {len(raw_content)} 字节")
            print(f"[DEBUG] 文件前20字节: {raw_content[:20]}")
            
            # 首先检测BOM（字节顺序标记）
            content = None
            used_encoding = None
            
            # 检查UTF-16 LE BOM
            if raw_content.startswith(b'\xff\xfe'):
                try:
                    content = raw_content.decode('utf-16-le')
                    used_encoding = 'utf-16-le (BOM detected)'
                    print(f"[DEBUG] 检测到UTF-16 LE BOM，成功解码")
                except UnicodeDecodeError as e:
                    print(f"[DEBUG] UTF-16 LE BOM解码失败: {e}")
            
            # 检查UTF-16 BE BOM
            elif raw_content.startswith(b'\xfe\xff'):
                try:
                    content = raw_content.decode('utf-16-be')
                    used_encoding = 'utf-16-be (BOM detected)'
                    print(f"[DEBUG] 检测到UTF-16 BE BOM，成功解码")
                except UnicodeDecodeError as e:
                    print(f"[DEBUG] UTF-16 BE BOM解码失败: {e}")
            
            # 检查UTF-8 BOM
            elif raw_content.startswith(b'\xef\xbb\xbf'):
                try:
                    content = raw_content.decode('utf-8-sig')
                    used_encoding = 'utf-8-sig (BOM detected)'
                    print(f"[DEBUG] 检测到UTF-8 BOM，成功解码")
                except UnicodeDecodeError as e:
                    print(f"[DEBUG] UTF-8 BOM解码失败: {e}")
            
            # 如果没有BOM，尝试多种编码方式
            if content is None:
                encodings = ['utf-8', 'utf-16-le', 'utf-16-be', 'gbk', 'gb2312', 'big5', 'latin-1']
                
                for encoding in encodings:
                    try:
                        content = raw_content.decode(encoding)
                        used_encoding = encoding
                        print(f"[DEBUG] 成功使用编码: {encoding}")
                        break
                    except UnicodeDecodeError as e:
                        print(f"[DEBUG] 编码 {encoding} 失败: {e}")
                        continue
            
            if content is None:
                # 如果所有编码都失败，使用替换字符模式
                print(f"[DEBUG] 所有编码都失败，使用替换模式")
                content = raw_content.decode('utf-8', errors='replace')
                used_encoding = 'utf-8 (with replacement)'
            
            # 检查内容是否包含乱码字符（更宽松的检测）
            def has_garbled_text(text):
                # 检查是否包含大量不可打印字符或控制字符
                control_chars = sum(1 for c in text if ord(c) < 32 and c not in '\n\r\t')
                total_chars = len(text)
                if total_chars > 0 and control_chars / total_chars > 0.1:
                    return True
                
                # 检查是否包含大量乱码字符（连续的不可读字符）
                garbled_sequences = 0
                for i in range(len(text) - 1):
                    if ord(text[i]) > 127 and ord(text[i+1]) > 127:
                        # 检查是否是常见的中文字符范围
                        if not (0x4e00 <= ord(text[i]) <= 0x9fff or 0x3400 <= ord(text[i]) <= 0x4dbf):
                            garbled_sequences += 1
                
                return garbled_sequences > len(text) * 0.1
            
            if has_garbled_text(content):
                print(f"[DEBUG] 检测到可能的乱码，尝试重新解码")
                # 尝试使用不同的错误处理策略
                for encoding in ['utf-8', 'gbk', 'latin-1']:
                    try:
                        test_content = raw_content.decode(encoding, errors='ignore')
                        if len(test_content.strip()) > 0 and not has_garbled_text(test_content):
                            content = test_content
                            used_encoding = f"{encoding} (ignore errors)"
                            print(f"[DEBUG] 使用 {encoding} (ignore) 成功")
                            break
                    except:
                        continue
            
            print(f"[DEBUG] 最终编码: {used_encoding}, 内容长度: {len(content)}")
            print(f"[DEBUG] 内容预览: {repr(content[:100])}")
            
            return content, 200, {'Content-Type': 'text/plain; charset=utf-8'}
        except Exception as e:
            print(f"[DEBUG] 读取文本文件失败: {str(e)}")
            return jsonify({'error': f'无法读取文本内容: {str(e)}'}), 500

    # ===== 3. PDF文件：返回内嵌预览 =====
    elif ext == '.pdf':
        # 检查是否是内嵌预览请求
        if request.args.get('inline') == 'true':
            # 直接返回PDF文件内容，设置正确的响应头防止下载
            mime = 'application/pdf'
            response = send_file(abs_path, mimetype=mime)
            response.headers['Content-Disposition'] = 'inline'
            return response
        else:
            # 返回HTML页面来内嵌显示PDF
            # 从URL参数中获取token并传递给iframe
            token = request.args.get('token', '')
            pdf_url = f'/api/preview?path={path}&inline=true'
            if token:
                pdf_url += f'&token={token}'
            
            html_content = f'''
            <!DOCTYPE html>
            <html>
            <head>
                <title>PDF预览 - {os.path.basename(abs_path)}</title>
                <style>
                    body {{ margin: 0; padding: 0; height: 100vh; }}
                    iframe {{ width: 100%; height: 100%; border: none; }}
                </style>
            </head>
            <body>
                <iframe src="{pdf_url}" type="application/pdf"></iframe>
            </body>
            </html>
            '''
            return html_content, 200, {'Content-Type': 'text/html; charset=utf-8'}
    
    # ===== 4. 其他格式（图片、音视频等）原样返回 =====
    else:
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
    abs_path = os.path.abspath(os.path.join(BASE_DIRS[0], safe_parent, name))
    if not abs_path.startswith(BASE_DIRS[0]):
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

    abs_path = os.path.abspath(os.path.join(BASE_DIRS[0], file_path.lstrip('/\\')))
    if not abs_path.startswith(BASE_DIRS[0]) or not os.path.exists(abs_path):
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
    abs_path = os.path.abspath(os.path.join(BASE_DIRS[0], row['file_path'].lstrip('/\\')))
    if not abs_path.startswith(BASE_DIRS[0]) or not os.path.exists(abs_path):
        return "文件不存在", 404
    return send_file(abs_path, as_attachment=True)

@app.route('/api/ngrok-url')
def api_ngrok_url():
    if ngrok_url_global:
        return jsonify({'url': ngrok_url_global})
    return jsonify({'error': 'ngrok 地址暂不可用'}), 503




@app.route('/api/ec_config', methods=['POST'])
@token_required(admin_only=True)
def ec_config():
    data = request.get_json()
    scheme = data.get('scheme', '')  # 默认为空
    disks = data.get('disks', [])

    if scheme:  # 启用了某种纠删码
        try:
            k = int(data.get('k'))
            m = int(data.get('m'))
        except (ValueError, TypeError):
            return jsonify({'error': 'k和m必须为整数'}), 400
        if k <= 0 or m <= 0:
            return jsonify({'error': 'k和m必须为正整数'}), 400
    else:
        # 如果不使用纠删码，可以清空 k/m
        k = 0
        m = 0

    config_path = os.path.join(BASE_DIRS[0], 'ec_config.json')
    with open(config_path, 'w') as f:
        json.dump({
            'scheme': scheme,
            'k': k,
            'm': m,
            'disks': disks,
            'timestamp': datetime.now().isoformat()
        }, f)

    return jsonify({'success': True, 'message': '纠删码配置已保存（%s）' % (scheme or '未启用')})

@app.route('/api/encode', methods=['POST'])
@token_required(admin_only=True)
def api_encode():
    data = request.get_json()
    try:
        encode(
            scheme=data['scheme'],
            file_path=os.path.join(BASE_DIRS[0], data['file_path']),
            k=data['k'],
            m=data['m'],
            output_paths=data['disks']
        )
        return jsonify({'success': True, 'message': '编码成功'})
    except ECError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'内部错误: {str(e)}'}), 500
@app.route('/api/upload', methods=['POST'])
@token_required()
def upload_file_with_ec():
    uploaded_file = request.files.get('file')
    rel_path = request.form.get('path', '/')
    if not uploaded_file or not uploaded_file.filename:
        return jsonify({'error': '未提供文件'}), 400

    filename = uploaded_file.filename
    target_path = os.path.join(BASE_DIRS[0], rel_path.lstrip('/\\'), filename)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    uploaded_file.save(target_path)

    # 判断是否启用纠删码
    ec_config_path = os.path.join(BASE_DIRS[0], 'ec_config.json')
    if os.path.exists(ec_config_path):
        with open(ec_config_path, 'r') as f:
            ec_cfg = json.load(f)

        if ec_cfg.get('scheme') and ec_cfg.get('k') and ec_cfg.get('m'):
            try:
                encode(
                    scheme=ec_cfg['scheme'],
                    file_path=target_path,
                    k=ec_cfg['k'],
                    m=ec_cfg['m'],
                    output_paths=ec_cfg['disks']
                )
                os.remove(target_path)  # 删除原始文件，仅保留编码块
                return jsonify({'success': True, 'message': '文件上传并编码成功'})
            except ECError as e:
                return jsonify({'error': f'纠删码编码失败: {str(e)}'}), 500

    return jsonify({'success': True, 'message': '文件上传成功（未使用纠删码）'})
@app.route('/api/list', methods=['GET'])
@token_required()
def list_files():
    requested_path = request.args.get('path', '/').lstrip('/\\')
    keyword = request.args.get('q', '').strip().lower()

    # 检查是否包含盘符前缀（如 D:/path 或 D:\path）
    drive_prefix = None
    if ':' in requested_path:
        # 提取盘符前缀
        parts = requested_path.replace('\\', '/').split('/')
        if parts[0] and ':' in parts[0]:
            drive_prefix = parts[0] + '/'
            # 移除盘符前缀，获取相对路径
            requested_path = '/'.join(parts[1:]) if len(parts) > 1 else ''
    
    # 如果没有盘符前缀，使用默认盘符（第一个可用盘符）
    if not drive_prefix:
        available_drives = get_available_drives()
        if not available_drives:
            return jsonify({'error': '没有可用的盘符'}), 500
        drive_prefix = available_drives[0]
    
    # 检查盘符是否在允许列表中
    if drive_prefix not in BASE_DIRS:
        return jsonify({'error': '不支持的盘符'}), 403
    
    full_path = os.path.abspath(os.path.join(drive_prefix, requested_path))

    # 加载纠删码配置
    ec_cfg = {}
    ec_cfg_path = os.path.join(drive_prefix, 'ec_config.json')
    if os.path.exists(ec_cfg_path):
        with open(ec_cfg_path, 'r') as f:
            ec_cfg = json.load(f)

    # 如果请求路径是逻辑卷入口
    if requested_path == 'ec_volume' and ec_cfg.get('disks'):
        full_path = os.path.abspath(ec_cfg['disks'][0])  # 映射为第一个纠删码磁盘路径

    allowed_paths = [drive_prefix] + ec_cfg.get('disks', []) + [d['mount'] for d in get_disk_info()]
    if not any(full_path.startswith(os.path.abspath(p)) for p in allowed_paths):
        return jsonify({'error': '非法路径'}), 403

    if not os.path.exists(full_path) or not os.path.isdir(full_path):
        return jsonify({'error': '路径不存在或不是文件夹'}), 404

    try:
        items = []
        for name in os.listdir(full_path):
            if keyword and keyword not in name.lower():
                continue
            path = os.path.join(full_path, name)
            stat = os.stat(path)
            items.append({
                'name': name,
                'is_dir': os.path.isdir(path),
                'size': stat.st_size if os.path.isfile(path) else None,
                'mtime': stat.st_mtime,
                'path': os.path.join(requested_path, name) if requested_path else name
            })
        
        # 按文件夹在前，文件在后的顺序排序
        items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        
        return jsonify({
            'success': True,
            'current_path': requested_path,
            'drive_prefix': drive_prefix,
            'items': items
        })
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
        print(f"[搜索] 获取搜索目录出错: {e}")
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
        print(f"[搜索] 遍历目录失败: {e}")
        return jsonify({'success': False, 'error': f'搜索失败: {str(e)}'}), 500



@app.route('/api/download', methods=['GET'])
@token_required()
def download_file():
    rel_path = request.args.get('path', '').lstrip('/\\')
    original_path = os.path.join(BASE_DIRS[0], rel_path)

    # 检查是否存在原始文件（未启用EC）
    if os.path.exists(original_path):
        return send_file(original_path, as_attachment=True)

    # 尝试读取元数据并恢复
    ec_config_path = os.path.join(BASE_DIRS[0], 'ec_config.json')
    if not os.path.exists(ec_config_path):
        return jsonify({'error': '文件不存在'}), 404

    with open(ec_config_path, 'r') as f:
        ec_cfg = json.load(f)

    filename = os.path.basename(original_path)
    block_paths = []
    for i, disk in enumerate(ec_cfg['disks']):
        block_path = os.path.join(disk, 'encoded', f'{filename}.block_{i}')
        if os.path.exists(block_path):
            block_paths.append(block_path)

    if len(block_paths) < ec_cfg['k']:
        return jsonify({'error': '可用数据块不足，无法解码'}), 500

    # 解码还原
    from ec_engine import decode  # 你需要实现这个方法
    restored_path = os.path.join(BASE_DIRS[0], 'tmp', filename)
    os.makedirs(os.path.dirname(restored_path), exist_ok=True)
    try:
        decode('rs', block_paths[:ec_cfg['k']], restored_path, k=ec_cfg['k'], m=ec_cfg['m'])
        return send_file(restored_path, as_attachment=True)
    except Exception as e:
        return jsonify({'error': f'解码失败: {str(e)}'}), 500


        # ===== NGROK 配置 =====
NGROK_PATH = r'D:\nas_data\ngrok.exe'
FLASK_PORT = 5000

ngrok_url_global = None  # 👈 全局变量保存公网地址

def start_ngrok():
    global ngrok_url_global
    print("⚙️ 正在启动 ngrok...")
    
    # 检查ngrok是否可用
    try:
        ngrok_proc = subprocess.Popen(
            [NGROK_PATH, 'http', str(FLASK_PORT)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        time.sleep(2)
        ngrok_url = None

        for i in range(5):  # 减少重试次数
            try:
                print(f"⌛ 尝试获取 ngrok 地址（第 {i+1} 次）")
                r = requests.get(
                    'http://127.0.0.1:4040/api/tunnels',
                    headers={"Accept": "application/json"},
                    timeout=3  # 增加超时时间
                ).json()
                for t in r.get('tunnels', []):
                    if t['proto'] == 'https':
                        ngrok_url = t['public_url']
                        break
                if ngrok_url:
                    break
            except Exception as e:
                print(f"❌ 获取地址时异常（第 {i+1} 次）: {e}")
                time.sleep(2)

        if ngrok_url:
            print('✅ ngrok 公网地址:', ngrok_url)
            ngrok_url_global = ngrok_url
            return ngrok_url, ngrok_proc
        else:
            print('❌ ngrok 启动失败，将使用本地模式运行')
            ngrok_proc.terminate()
            return None, None
            
    except Exception as e:
        print(f'❌ ngrok 启动失败: {e}')
        print('💡 提示：ngrok 不是必需的，程序将在本地模式下运行')
        return None, None

# ========== 你的 Flask 路由、逻辑在这里 ==========


# ===== 文档协作API =====
@app.route('/api/documents', methods=['GET'])
@token_required()
def get_documents():
    """获取用户可访问的文档列表"""
    db = get_db()
    user_id = g.user['id']
    
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
            (title, content, g.user['id'])
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
    if not collaboration_manager.check_document_permission(doc_id, g.user['id'], 'read'):
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
    
    if not doc or doc['created_by'] != g.user['id']:
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
    if not collaboration_manager.check_document_permission(doc_id, g.user['id'], 'read'):
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
    if not collaboration_manager.check_document_permission(doc_id, g.user['id'], 'read'):
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
    print('collab_load:', 'file=', file, 'path=', path)
    if not file:
        return jsonify({'success': False, 'error': '缺少文件名'}), 400
    # 只允许在BASE_DIRS[0]及其子目录下操作
    full_path = os.path.abspath(os.path.join(BASE_DIRS[0], path, file))
    print('collab_load:', 'full_path=', full_path)
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
                    print(f'collab_load: 成功使用 {encoding} 编码读取文件')
                    break
                except UnicodeDecodeError:
                    print(f'collab_load: {encoding} 编码失败，尝试下一个')
                    continue
                except Exception as e:
                    print(f'collab_load: {encoding} 编码读取异常: {e}')
                    continue
            
            if content is None:
                # 如果所有编码都失败，尝试二进制读取并解码
                try:
                    with open(full_path, 'rb') as f:
                        raw_content = f.read()
                    
                    # 尝试检测UTF-16 BOM
                    if raw_content.startswith(b'\xff\xfe'):
                        content = raw_content.decode('utf-16le')
                        print('collab_load: 检测到UTF-16 LE BOM')
                    elif raw_content.startswith(b'\xfe\xff'):
                        content = raw_content.decode('utf-16be')
                        print('collab_load: 检测到UTF-16 BE BOM')
                    elif raw_content.startswith(b'\xef\xbb\xbf'):
                        content = raw_content.decode('utf-8')
                        print('collab_load: 检测到UTF-8 BOM')
                    else:
                        # 最后尝试用 latin1 编码（不会抛出异常）
                        content = raw_content.decode('latin1')
                        print('collab_load: 使用 latin1 编码作为最后手段')
                except Exception as e:
                    print(f'collab_load: 二进制读取失败: {e}')
                    return jsonify({'success': False, 'error': f'无法读取文件，编码问题: {str(e)}'}), 500
        
        # 检查内容长度，如果太长则截断
        max_length = 1024 * 1024  # 1MB
        if len(content) > max_length:
            content = content[:max_length] + f'\n\n... (文件过长，已截断，总长度: {len(content)} 字符)'
            print(f'collab_load: 文件内容过长，已截断到 {max_length} 字符')
        
        print(f'collab_load: 文件内容长度: {len(content)} 字符')
        return jsonify({'success': True, 'content': content})
    except Exception as e:
        print(f'collab_load: 异常: {e}')
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
    documents = onlyoffice_manager.get_user_documents(g.user['id'])
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
        doc_id = onlyoffice_manager.create_document(file_name, new_file_path, file_type, g.user['id'])
    else:
        # 生成新文件路径
        file_path = f"{int(time.time())}_{file_name}"
        # 创建文档记录
        doc_id = onlyoffice_manager.create_document(file_name, file_path, file_type, g.user['id'])
    
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
    
    success, result = onlyoffice_manager.upload_document(file, g.user['id'])
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
    config = onlyoffice_manager.get_document_config(doc_id, g.user['id'], action)
    
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
    if not onlyoffice_manager.check_document_permission(doc_id, g.user['id'], 'read'):
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
        file_path, file_name, g.user['id'], expire_hours
    )
    
    if result:
        return jsonify({'success': True, 'session': result})
    else:
        return jsonify({'error': '创建协作会话失败'}), 500

@app.route('/api/collaboration/sessions', methods=['GET'])
@token_required()
def get_collaboration_sessions():
    """获取用户的协作会话"""
    created_sessions = collaboration_v2.get_user_sessions(g.user['id'])
    participating_sessions = collaboration_v2.get_participating_sessions(g.user['id'])
    
    return jsonify({
        'created': created_sessions,
        'participating': participating_sessions
    })

@app.route('/api/collaboration/join', methods=['POST'])
@token_required()
def join_collaboration_session():
    """加入协作会话"""
    data = request.get_json()
    session_token = data.get('session_token', '').strip()
    
    if not session_token:
        return jsonify({'error': '会话令牌不能为空'}), 400
    
    success, message = collaboration_v2.join_session(
        session_token, g.user['id'], g.user['username']
    )
    
    if success:
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'error': message}), 400

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
    success, message = collaboration_v2.close_session(session_id, g.user['id'])
    
    if success:
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'error': message}), 400

@app.route('/collaboration.html')
def collaboration_page():
    return app.send_static_file('collaboration.html')

# ===== 主启动入口 =====
if __name__ == '__main__':
    ngrok_url, ngrok_proc = start_ngrok()
    try:
        socketio.run(app, host='0.0.0.0', port=FLASK_PORT, debug=False)
    finally:
        if ngrok_proc:
            ngrok_proc.terminate()
