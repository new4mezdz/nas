# routes/user_routes.py
from flask import Blueprint, request, jsonify, g
from datetime import datetime
from common import get_db

user_bp = Blueprint('user', __name__, url_prefix='/api')


# ========== 收藏夹 API ==========

@user_bp.route('/favorites', methods=['GET'])
def get_favorites():
    user_id = g.user
    if not user_id:
        return jsonify({'error': '未登录'}), 401

    db = get_db()
    rows = db.execute(
        "SELECT * FROM favorites WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    ).fetchall()

    items = []
    for r in rows:
        items.append({
            'name': r['name'],
            'path': r['path'],
            'is_dir': bool(r['is_dir']),
            'mtime': datetime.strptime(r['created_at'], '%Y-%m-%d %H:%M:%S').timestamp(),
            'size': 0
        })
    return jsonify({'items': items})


@user_bp.route('/favorites/add', methods=['POST'])
def add_favorite():
    user_id = g.user
    if not user_id:
        return jsonify({'error': '未登录'}), 401

    data = request.json
    path = data.get('path')
    name = data.get('name')
    is_dir = data.get('is_dir', False)

    if not path or not name:
        return jsonify({'error': '参数错误'}), 400

    try:
        db = get_db()
        db.execute(
            "INSERT OR IGNORE INTO favorites (user_id, path, name, is_dir) VALUES (?, ?, ?, ?)",
            (user_id, path, name, is_dir)
        )
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@user_bp.route('/favorites/remove', methods=['POST'])
def remove_favorite():
    user_id = g.user
    if not user_id:
        return jsonify({'error': '未登录'}), 401

    data = request.json
    path = data.get('path')

    try:
        db = get_db()
        db.execute("DELETE FROM favorites WHERE user_id = ? AND path = ?", (user_id, path))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@user_bp.route('/favorites/check', methods=['POST'])
def check_is_favorite():
    user_id = g.user
    if not user_id:
        return jsonify({'is_favorite': False})

    path = request.json.get('path')
    db = get_db()
    row = db.execute(
        "SELECT 1 FROM favorites WHERE user_id = ? AND path = ?",
        (user_id, path)
    ).fetchone()
    return jsonify({'is_favorite': bool(row)})


# ========== 最近访问 API ==========

@user_bp.route('/recent', methods=['GET'])
def get_recent():
    user_id = g.user
    if not user_id:
        return jsonify({'error': '未登录'}), 401

    db = get_db()
    rows = db.execute(
        "SELECT * FROM recent_files WHERE user_id = ? ORDER BY accessed_at DESC LIMIT 10",
        (user_id,)
    ).fetchall()

    items = []
    for r in rows:
        items.append({
            'name': r['name'],
            'path': r['path'],
            'is_dir': bool(r['is_dir']),
            'mtime': datetime.strptime(r['accessed_at'], '%Y-%m-%d %H:%M:%S').timestamp(),
            'size': 0
        })
    return jsonify({'items': items})


@user_bp.route('/recent/add', methods=['POST'])
def add_recent():
    user_id = g.user
    if not user_id:
        return jsonify({'error': '未登录'}), 401

    data = request.json
    path = data.get('path')
    name = data.get('name')
    is_dir = data.get('is_dir', False)

    if not path:
        return jsonify({'error': '参数错误'}), 400

    try:
        db = get_db()
        db.execute("DELETE FROM recent_files WHERE user_id = ? AND path = ?", (user_id, path))
        db.execute(
            "INSERT INTO recent_files (user_id, path, name, is_dir, accessed_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (user_id, path, name, is_dir)
        )
        db.execute("""
            DELETE FROM recent_files 
            WHERE id NOT IN (
                SELECT id FROM recent_files 
                WHERE user_id = ? 
                ORDER BY accessed_at DESC 
                LIMIT 10
            ) AND user_id = ?
        """, (user_id, user_id))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500