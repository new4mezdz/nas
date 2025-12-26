# routes/share_routes.py
import os
import io
import json
import time
import secrets
import hashlib
from datetime import datetime, timedelta
from urllib.parse import quote
from flask import Blueprint, request, jsonify, g, send_file

from common import get_db, get_actual_file_path, is_path_allowed, _is_ec_volume
from permission_decorator import permission_required

share_bp = Blueprint('share', __name__)

# 外部依赖
_ctx = {
    'EC_CFG_PATH': None,
    'EC_IDX_PATH': None,
    'THIS_NODE_ID': None,
    'NAS_CENTER_PUBLIC_URL': None,
    'load_json': None,
    'save_json': None,
    'decode_from_dict': None,
    'encryption_manager': None,
    'Storage_pool': None,
    'rs_encode': None,
}


def init_share_routes(ec_cfg_path, ec_idx_path, this_node_id, center_public_url,
                      load_json, save_json, decode_from_dict, encryption_manager,
                      storage_pool, rs_encode):
    _ctx['EC_CFG_PATH'] = ec_cfg_path
    _ctx['EC_IDX_PATH'] = ec_idx_path
    _ctx['THIS_NODE_ID'] = this_node_id
    _ctx['NAS_CENTER_PUBLIC_URL'] = center_public_url
    _ctx['load_json'] = load_json
    _ctx['save_json'] = save_json
    _ctx['decode_from_dict'] = decode_from_dict
    _ctx['encryption_manager'] = encryption_manager
    _ctx['Storage_pool'] = storage_pool
    _ctx['rs_encode'] = rs_encode


def _is_pool_volume(path: str) -> bool:
    return path.startswith('pool://')


def _parse_pool_path(path: str):
    path = path.replace("pool://", "").strip("/")
    parts = path.split("/")
    if len(parts) == 1:
        return parts[0], "", ""
    elif len(parts) == 2:
        return parts[0], "", parts[1]
    else:
        return parts[0], "/".join(parts[1:-1]), parts[-1]


@share_bp.route('/api/share', methods=['POST'])
@permission_required('readonly')
def create_share():
    """创建文件分享链接"""
    try:
        data = request.get_json()
        file_path = data.get('file_path', '')
        expire_hours = int(data.get('expire_hours', 24))
        password = data.get('password', '')

        print(f"[DEBUG] 分享请求: file_path={file_path}")

        file_exists = False
        load_json = _ctx['load_json']

        # 分支 1: 纠删码卷
        if _is_ec_volume(file_path):
            logical_name = file_path.replace("\\", "/").strip("/").split("/", 1)[-1]
            if logical_name:
                idx = load_json(_ctx['EC_IDX_PATH'], {"files": {}})
                if logical_name in idx.get("files", {}):
                    file_exists = True

        # 分支 2: 空间池卷
        elif _is_pool_volume(file_path):
            try:
                Storage_pool = _ctx['Storage_pool']
                volume, subpath, filename = _parse_pool_path(file_path)
                virtual_path = f"{volume}/{subpath}/{filename}" if subpath else f"{volume}/{filename}"
                actual_path = Storage_pool.get_file_path(virtual_path)
                print(f"[DEBUG] 池路径解析: volume={volume}, subpath={subpath}, filename={filename}, actual={actual_path}")
                if actual_path and os.path.exists(actual_path):
                    file_exists = True
            except Exception as e:
                print(f"[DEBUG] 池路径解析失败: {e}")

        # 分支 3: 物理磁盘
        else:
            actual_path = get_actual_file_path(file_path)
            if actual_path and is_path_allowed(actual_path) and os.path.exists(actual_path):
                file_exists = True

        if not file_exists:
            return jsonify({'error': '文件不存在'}), 404

        # 创建分享链接
        token = secrets.token_urlsafe(16)
        expire_at = datetime.now() + timedelta(hours=expire_hours)
        db = get_db()
        db.execute(
            "INSERT INTO share_links (file_path, token, password, expire_at) VALUES (?, ?, ?, ?)",
            (file_path, token, password, expire_at.strftime('%Y-%m-%d %H:%M:%S'))
        )
        db.commit()

        # 动态获取公网地址和节点ID
        from config import runtime_config
        center_public_url = runtime_config.nas_center_public_url or _ctx['NAS_CENTER_PUBLIC_URL']
        this_node_id = runtime_config.this_node_id or _ctx['THIS_NODE_ID']

        print(f"[DEBUG] center_public_url={center_public_url}, this_node_id={this_node_id}")

        # 如果没有公网地址或节点ID，返回本地链接
        if not center_public_url or not this_node_id:
            print(f"[DEBUG] 公网地址或节点ID未配置，返回本地链接")
            return jsonify({
                'success': True,
                'share_url': f'/share/{token}',
                'full_url': None
            })

        public_share_url = f"{center_public_url}/share/{this_node_id}/{token}"

        return jsonify({
            'success': True,
            'share_url': f'/share/{token}',
            'full_url': public_share_url
        })

    except Exception as e:
        import traceback
        print(f"[ERROR] 分享失败: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@share_bp.route('/api/collab_share', methods=['POST'])
@permission_required('readonly')
def create_collab_share():
    """创建协作编辑分享链接"""
    data = request.get_json()
    file_path = data.get('file_path', '')
    guest_prefix = data.get('guest_prefix', '访客')
    expire_hours = int(data.get('expire_hours', 24))

    share_id = secrets.token_urlsafe(16)
    expire_at = datetime.now() + timedelta(hours=expire_hours)
    created_by = getattr(g, 'current_user', {}).get('username', 'unknown')

    db = get_db()
    db.execute(
        "INSERT INTO collab_shares (share_id, file_path, guest_prefix, expire_at, created_by) VALUES (?, ?, ?, ?, ?)",
        (share_id, file_path, guest_prefix, expire_at.strftime('%Y-%m-%d %H:%M:%S'), created_by)
    )
    db.commit()

    guest_name = f"{guest_prefix}_{secrets.token_hex(3)}"
    proxy_base = f"/proxy/node/{_ctx['THIS_NODE_ID']}" if _ctx['THIS_NODE_ID'] else ""

    if _ctx['NAS_CENTER_PUBLIC_URL']:
        base = _ctx['NAS_CENTER_PUBLIC_URL']
    else:
        base = request.host_url.rstrip('/')

    share_url = f"{base}{proxy_base}/static/univer.html?path={quote(file_path)}&token={share_id}&baseUrl={proxy_base}&guest=1&guestName={quote(guest_name)}"

    return jsonify({
        'success': True,
        'share_url': share_url,
        'share_id': share_id
    })


@share_bp.route('/api/collab_verify', methods=['POST'])
def verify_collab_token():
    """验证协作分享token"""
    data = request.get_json()
    share_id = data.get('token', '')

    db = get_db()
    row = db.execute("SELECT * FROM collab_shares WHERE share_id=?", (share_id,)).fetchone()

    if not row:
        return jsonify({'valid': False, 'error': '链接不存在'}), 404

    expire_at = datetime.strptime(row['expire_at'], '%Y-%m-%d %H:%M:%S')
    if datetime.now() > expire_at:
        db.execute("DELETE FROM collab_shares WHERE share_id=?", (share_id,))
        db.commit()
        return jsonify({'valid': False, 'error': '链接已过期'}), 410

    return jsonify({
        'valid': True,
        'file_path': row['file_path'],
        'guest_prefix': row['guest_prefix']
    })


@share_bp.route('/share/<token>', methods=['GET', 'POST'])
def access_share(token):
    """访问分享链接"""
    db = get_db()
    row = db.execute("SELECT * FROM share_links WHERE token=?", (token,)).fetchone()
    if not row:
        return "链接无效或已删除", 404

    if row['expire_at'] and datetime.strptime(row['expire_at'], '%Y-%m-%d %H:%M:%S') < datetime.now():
        db.execute("DELETE FROM share_links WHERE token=?", (token,))
        db.commit()
        return "链接已过期", 403

    # 密码验证
    if row['password']:
        if request.method == 'POST':
            pwd = request.form.get('password', '')
            if pwd != row['password']:
                return "密码错误", 403
        else:
            return '''
                <style>body { font-family: sans-serif; text-align: center; padding-top: 50px; }</style>
                <form method="post">
                  <h3>请输入分享密码</h3>
                  <input name="password" type="password" style="padding: 8px;"/>
                  <button type="submit" style="padding: 8px 12px;">提交</button>
                </form>
            '''

    file_path = row['file_path']
    load_json = _ctx['load_json']
    decode_from_dict = _ctx['decode_from_dict']
    encryption_manager = _ctx['encryption_manager']
    Storage_pool = _ctx['Storage_pool']

    # 分支 1: 纠删码卷
    if _is_ec_volume(file_path):
        name = file_path.replace("\\", "/").strip("/").split("/", 1)[-1]
        if not name:
            return "无效的逻辑盘文件路径", 400

        idx = load_json(_ctx['EC_IDX_PATH'], {"files": {}}).get("files", {})
        entry = idx.get(name)
        if not entry:
            return "分享的文件已在逻辑盘中被删除或移动", 404

        k, m, disks = entry["k"], entry["m"], entry["disks"]
        shard_dict, meta = {}, None

        for i, disk in enumerate(disks[:k + m]):
            enc_dir = os.path.join(disk, "encoded", os.path.dirname(name))
            blk = os.path.join(enc_dir, f"{os.path.basename(name)}.blk_{i}")
            if os.path.exists(blk):
                with open(blk, "rb") as f:
                    shard_dict[i] = f.read()
            if not meta:
                mj = os.path.join(enc_dir, f"{os.path.basename(name)}.meta.json")
                if os.path.exists(mj):
                    with open(mj, "r", encoding="utf-8") as mf:
                        meta = json.load(mf)

        if not meta or len(shard_dict) < k:
            return "文件分片损坏或不足，暂时无法访问", 409

        try:
            data = decode_from_dict(shard_dict, meta)
        except Exception as e:
            print(f"[ERROR] Share link decode failed for {name}: {e}")
            return "文件解码失败，请检查后台日志", 500

        if meta.get("sha256") and hashlib.sha256(data).hexdigest() != meta.get("sha256"):
            return "文件完整性校验失败，文件可能已损坏", 500

        return send_file(io.BytesIO(data), as_attachment=True, download_name=os.path.basename(name))

    # 分支 2: 空间池卷
    elif _is_pool_volume(file_path):
        try:
            volume, subpath, filename = _parse_pool_path(file_path)
            virtual_path = f"{volume}/{subpath}/{filename}" if subpath else f"{volume}/{filename}"
            actual_path = Storage_pool.get_file_path(virtual_path)

            if not actual_path or not os.path.exists(actual_path):
                return "分享的文件不存在或已被移动", 404

            return send_file(actual_path, as_attachment=True, download_name=filename)
        except Exception as e:
            print(f"[ERROR] 空间池分享失败: {e}")
            return "文件访问失败", 500

    # 分支 3: 物理磁盘
    else:
        actual_path = get_actual_file_path(file_path)

        if not actual_path or not is_path_allowed(actual_path) or not os.path.exists(actual_path):
            return "分享的文件不存在或已被移动", 404

        if encryption_manager.is_path_encrypted(actual_path):
            try:
                decrypted_data = encryption_manager.read_encrypted_file(actual_path)
                return send_file(io.BytesIO(decrypted_data), as_attachment=True,
                                 download_name=os.path.basename(actual_path))
            except Exception as e:
                if 'NotUnlockedError' in str(type(e)):
                    return "磁盘已锁定，暂时无法访问分享内容", 503
                return "分享文件解密失败", 500
        else:
            return send_file(actual_path, as_attachment=True)


@share_bp.route('/api/collab_download', methods=['GET'])
def collab_download():
    """访客协作下载"""
    file_path = request.args.get("path", "").strip()
    share_token = request.args.get("token", "").strip()

    if not file_path or not share_token:
        return jsonify({"error": "缺少参数"}), 400

    db = get_db()
    row = db.execute("SELECT * FROM collab_shares WHERE share_id=?", (share_token,)).fetchone()
    if not row:
        return jsonify({"error": "无效的协作链接"}), 403

    expire_at = datetime.strptime(row['expire_at'], '%Y-%m-%d %H:%M:%S')
    if datetime.now() > expire_at:
        db.execute("DELETE FROM collab_shares WHERE share_id=?", (share_token,))
        db.commit()
        return jsonify({"error": "协作链接已过期"}), 410

    if row['file_path'] != file_path:
        return jsonify({"error": "无权访问该文件"}), 403

    load_json = _ctx['load_json']
    decode_from_dict = _ctx['decode_from_dict']
    encryption_manager = _ctx['encryption_manager']
    Storage_pool = _ctx['Storage_pool']

    # 分支 1: 纠删码卷
    if _is_ec_volume(file_path):
        name = file_path.replace("\\", "/").strip("/").split("/", 1)[-1]
        if not name:
            return jsonify({"error": "无效路径"}), 400
        idx = load_json(_ctx['EC_IDX_PATH'], {"files": {}}).get("files", {})
        entry = idx.get(name)
        if not entry:
            return jsonify({"error": "文件不存在"}), 404

        k, m, disks = entry["k"], entry["m"], entry["disks"]
        shard_dict, meta = {}, None
        for i, disk in enumerate(disks[:k + m]):
            enc_dir = os.path.join(disk, "encoded", os.path.dirname(name))
            blk = os.path.join(enc_dir, f"{os.path.basename(name)}.blk_{i}")
            if os.path.exists(blk):
                with open(blk, "rb") as f:
                    shard_dict[i] = f.read()
            if not meta:
                mj = os.path.join(enc_dir, f"{os.path.basename(name)}.meta.json")
                if os.path.exists(mj):
                    meta = json.load(open(mj, "r", encoding="utf-8"))

        if not meta or len(shard_dict) < k:
            return jsonify({"error": "分片不足"}), 409
        try:
            data = decode_from_dict(shard_dict, meta)
        except Exception as e:
            return jsonify({"error": f"解码失败: {e}"}), 500
        return send_file(io.BytesIO(data), as_attachment=True, download_name=os.path.basename(name))

    # 分支 2: 空间池卷
    elif _is_pool_volume(file_path):
        try:
            volume, subpath, filename = _parse_pool_path(file_path)
            virtual_path = f"{volume}/{subpath}/{filename}" if subpath else f"{volume}/{filename}"
            actual_path = Storage_pool.get_file_path(virtual_path)
            if not actual_path or not os.path.exists(actual_path):
                return jsonify({"error": "文件不存在"}), 404
            return send_file(actual_path, as_attachment=True, download_name=os.path.basename(actual_path))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # 分支 3: 物理磁盘
    else:
        actual_path = get_actual_file_path(file_path)
        if not actual_path or not os.path.exists(actual_path):
            return jsonify({"error": "文件不存在"}), 404
        if not is_path_allowed(actual_path):
            return jsonify({"error": "禁止访问"}), 403
        if encryption_manager.is_path_encrypted(actual_path):
            try:
                decrypted_data = encryption_manager.read_encrypted_file(actual_path)
                return send_file(io.BytesIO(decrypted_data), as_attachment=True,
                                 download_name=os.path.basename(actual_path))
            except Exception as e:
                return jsonify({'error': str(e)}), 403
        return send_file(actual_path, as_attachment=True, download_name=os.path.basename(actual_path))


@share_bp.route('/api/collab_upload', methods=['POST'])
def collab_upload():
    """访客协作上传"""
    share_token = request.form.get('token', '').strip()
    upload_path = request.form.get('path', '/')
    uploaded_files = request.files.getlist('file')

    if not share_token:
        return jsonify({'error': '缺少协作token'}), 400

    db = get_db()
    row = db.execute("SELECT * FROM collab_shares WHERE share_id=?", (share_token,)).fetchone()
    if not row:
        return jsonify({'error': '无效的协作链接'}), 403

    expire_at = datetime.strptime(row['expire_at'], '%Y-%m-%d %H:%M:%S')
    if datetime.now() > expire_at:
        db.execute("DELETE FROM collab_shares WHERE share_id=?", (share_token,))
        db.commit()
        return jsonify({'error': '协作链接已过期'}), 410

    shared_file_dir = os.path.dirname(row['file_path'])
    if not upload_path.startswith(shared_file_dir):
        return jsonify({'error': '无权上传到该目录'}), 403

    if not uploaded_files or not all(f.filename for f in uploaded_files):
        return jsonify({'error': '未提供文件'}), 400

    load_json = _ctx['load_json']
    save_json = _ctx['save_json']
    rs_encode = _ctx['rs_encode']
    encryption_manager = _ctx['encryption_manager']
    Storage_pool = _ctx['Storage_pool']

    # 分支 1: 纠删码卷
    if _is_ec_volume(upload_path):
        ec_cfg = load_json(_ctx['EC_CFG_PATH'], {})
        if not ec_cfg or ec_cfg.get("scheme", "").lower() != "rs":
            return jsonify({'error': '未配置或未启用RS纠删码'}), 400

        k, m, disks = int(ec_cfg.get("k", 0)), int(ec_cfg.get("m", 0)), ec_cfg.get("disks", [])
        if k <= 0 or m <= 0 or len(disks) < k + m:
            return jsonify({'error': 'RS参数无效或磁盘数量不足'}), 400

        for uploaded_file in uploaded_files:
            data = uploaded_file.read()
            shards = rs_encode(data, k, m)
            shard_size = len(shards[0]) if shards else 0
            file_sha = hashlib.sha256(data).hexdigest()
            norm_path = upload_path.replace("\\", "/").strip("/")
            rel_in_volume_dir = '' if norm_path == 'ec_volume' else norm_path[len('ec_volume/'):]
            logical_name = os.path.join(rel_in_volume_dir, uploaded_file.filename).replace("\\", "/")
            meta = {"k": k, "m": m, "shard_size": shard_size, "original_size": len(data), "sha256": file_sha}

            try:
                for i, disk in enumerate(disks[:k + m]):
                    enc_dir = os.path.join(disk, "encoded", rel_in_volume_dir)
                    os.makedirs(enc_dir, exist_ok=True)
                    base_filename = os.path.basename(uploaded_file.filename)
                    with open(os.path.join(enc_dir, f"{base_filename}.blk_{i}"), "wb") as f:
                        f.write(shards[i])
                    with open(os.path.join(enc_dir, f"{base_filename}.meta.json"), "w", encoding="utf-8") as mf:
                        json.dump(meta, mf, ensure_ascii=False)
            except Exception as e:
                return jsonify({'error': f'写入分片失败: {e}'}), 500

            idx = load_json(_ctx['EC_IDX_PATH'], {"files": {}})
            idx["files"][logical_name] = {
                "size": len(data), "k": k, "m": m, "sha256": file_sha,
                "disks": disks, "ctime": int(time.time())
            }
            save_json(_ctx['EC_IDX_PATH'], idx)

        return jsonify({'success': True, 'message': f'{len(uploaded_files)}个文件已写入逻辑盘并完成RS编码'})

    # 分支 2: 空间池卷
    elif _is_pool_volume(upload_path):
        try:
            path_part = upload_path[7:]
            parts = path_part.split('/', 1)
            volume = parts[0]
            subpath = parts[1] if len(parts) > 1 else ''

            for uploaded_file in uploaded_files:
                file_data = uploaded_file.read()
                Storage_pool.add_file(volume, subpath, uploaded_file.filename, file_data)

            return jsonify({'success': True, 'message': f'{len(uploaded_files)}个文件已上传到池卷'})
        except Exception as e:
            return jsonify({'error': f'池卷上传失败: {e}'}), 500

    # 分支 3: 物理磁盘
    else:
        try:
            drive, _ = os.path.splitdrive(upload_path)
            if not drive:
                return jsonify({'error': '上传路径格式错误，缺少盘符'}), 400
            drive = drive.upper().replace('\\', '/')
            if not os.path.exists(drive):
                return jsonify({'error': f'磁盘 {drive} 不存在'}), 404

            target_dir = os.path.abspath(upload_path)
            os.makedirs(target_dir, exist_ok=True)

            for uploaded_file in uploaded_files:
                filename = uploaded_file.filename
                target_path = os.path.join(target_dir, filename)
                data_bytes = uploaded_file.read()

                if encryption_manager.is_path_encrypted(target_path):
                    encryption_manager.write_encrypted_file(target_path, data_bytes)
                else:
                    with open(target_path, "wb") as f:
                        f.write(data_bytes)

            return jsonify({'success': True, 'message': f'{len(uploaded_files)}个文件上传成功'})
        except Exception as e:
            return jsonify({'error': f'上传失败: {e}'}), 500