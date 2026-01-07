# routes/file_routes.py
# -*- coding: utf-8 -*-
import os
import io
import json
import time
import glob
import shutil
import hashlib
import mimetypes
from flask import Blueprint, request, jsonify, send_file

from common import (
    get_db, get_available_drives, get_actual_file_path,
    is_path_allowed, get_base_dir_for_path, _is_ec_volume
)
from permission_decorator import permission_required

file_bp = Blueprint('file', __name__)

# 外部依赖
_ctx = {
    'EC_CFG_PATH': None,
    'EC_IDX_PATH': None,
    'load_json': None,
    'save_json': None,
    'decode_from_dict': None,
    'rs_encode': None,
    'encryption_manager': None,
    'Storage_pool': None,
}


def init_file_routes(ec_cfg_path, ec_idx_path, load_json, save_json,
                     decode_from_dict, rs_encode, encryption_manager, storage_pool):
    _ctx['EC_CFG_PATH'] = ec_cfg_path
    _ctx['EC_IDX_PATH'] = ec_idx_path
    _ctx['load_json'] = load_json
    _ctx['save_json'] = save_json
    _ctx['decode_from_dict'] = decode_from_dict
    _ctx['rs_encode'] = rs_encode
    _ctx['encryption_manager'] = encryption_manager
    _ctx['Storage_pool'] = storage_pool


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


# ==================== 列表 ====================
@file_bp.route('/api/list', methods=['GET'])
@permission_required('readonly')
def list_files():
    """列出目录内容"""
    full_path_from_request = request.args.get('path', '/')
    load_json = _ctx['load_json']
    encryption_manager = _ctx['encryption_manager']
    Storage_pool = _ctx['Storage_pool']

    # 分支 1: 纠删码卷
    if _is_ec_volume(full_path_from_request):
        idx = load_json(_ctx['EC_IDX_PATH'], {"files": {}})
        items, now_ts = [], int(time.time())
        norm_req_path = full_path_from_request.replace("\\", "/").strip("/")

        if norm_req_path == 'ec_volume':
            current_dir_prefix = ''
        else:
            current_dir_prefix = norm_req_path[len('ec_volume/'):] + '/'

        sub_items = set()
        for name, meta in idx.get("files", {}).items():
            if not name.startswith(current_dir_prefix):
                continue
            relative_to_current = name[len(current_dir_prefix):]
            parts = relative_to_current.split('/')
            if len(parts) == 1:
                items.append({
                    "name": parts[0], "is_dir": False, "size": meta.get("size", 0),
                    "mtime": meta.get("ctime", now_ts), "path": name
                })
            else:
                sub_items.add(parts[0])

        for dir_name in sub_items:
            items.append({
                "name": dir_name, "is_dir": True, "size": None,
                "mtime": now_ts, "path": current_dir_prefix + dir_name
            })

        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return jsonify({"success": True, "items": items})


    # 分支 2: 空间池卷
    elif full_path_from_request.startswith('pool://'):
        try:
            pool_path = full_path_from_request[7:]
            parts = pool_path.split('/', 1)
            volume = parts[0]
            subpath = parts[1] if len(parts) > 1 else ''

            if not volume:
                return jsonify({'error': '无效的存储池路径'}), 400

            # 检查加密锁定状态
            pool_key = "pool:main"
            volume_key = f"volume:{volume}"

            if volume_key in encryption_manager.disk_configs:
                if volume_key not in encryption_manager.unlocked_keys:
                    return jsonify({
                        'error': f'逻辑卷 {volume} 已锁定，请先解锁',
                        'error_type': 'pool_locked',
                        'volume': volume
                    }), 403
            elif pool_key in encryption_manager.disk_configs:
                if pool_key not in encryption_manager.unlocked_keys:
                    return jsonify({
                        'error': '存储池已锁定，请先解锁',
                        'error_type': 'pool_locked',
                        'volume': volume
                    }), 403

            items = Storage_pool.list_files(volume, subpath)
            return jsonify({'success': True, 'items': items})
        except Exception as e:
            return jsonify({'error': f'读取存储池失败: {str(e)}'}), 500

    # 分支 3: 物理硬盘
    else:
        try:
            full_path = os.path.abspath(full_path_from_request)
            if not is_path_allowed(full_path):
                return jsonify({'error': '非法路径或不允许访问的磁盘'}), 403

            if encryption_manager.is_path_encrypted(full_path):
                drive = encryption_manager._get_drive_for_path(full_path)
                if drive and drive not in encryption_manager.unlocked_keys:
                    return jsonify({
                        'error': f'磁盘 {drive} 已锁定,无法访问',
                        'error_type': 'disk_locked',
                        'drive': drive
                    }), 403

            if not os.path.exists(full_path) or not os.path.isdir(full_path):
                return jsonify({'error': f'路径不存在或不是文件夹'}), 404

            items = []
            for name in os.listdir(full_path):
                entry_full_path = os.path.join(full_path, name)
                stat = os.stat(entry_full_path)
                items.append({
                    'name': name,
                    'is_dir': os.path.isdir(entry_full_path),
                    'size': stat.st_size if os.path.isfile(entry_full_path) else None,
                    'mtime': stat.st_mtime,
                })
            items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
            return jsonify({'success': True, 'items': items})

        except Exception as e:
            return jsonify({'error': f'读取目录失败: {str(e)}'}), 500


# ==================== 上传 ====================
@file_bp.route('/api/upload', methods=['POST'])
@permission_required('readwrite')
def upload_file_with_ec():
    """上传文件"""
    uploaded_files = request.files.getlist('file')
    upload_path = request.form.get('path', '/')

    load_json = _ctx['load_json']
    save_json = _ctx['save_json']
    rs_encode = _ctx['rs_encode']
    encryption_manager = _ctx['encryption_manager']
    Storage_pool = _ctx['Storage_pool']

    if not uploaded_files or not all(f.filename for f in uploaded_files):
        return jsonify({'error': '未提供文件'}), 400

    # 分支 1: EC卷
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
    elif upload_path.startswith('pool://'):
        try:
            path_part = upload_path[7:]
            parts = path_part.split('/', 1)
            volume = parts[0]
            subpath = parts[1] if len(parts) > 1 else ''

            # 检查加密锁定状态
            pool_key = "pool:main"
            volume_key = f"volume:{volume}"
            encrypt_key = None

            if volume_key in encryption_manager.disk_configs:
                if volume_key not in encryption_manager.unlocked_keys:
                    return jsonify({'error': f'逻辑卷 {volume} 已锁定，请先解锁', 'locked': True}), 403
                encrypt_key = encryption_manager.unlocked_keys[volume_key]
            elif pool_key in encryption_manager.disk_configs:
                if pool_key not in encryption_manager.unlocked_keys:
                    return jsonify({'error': '存储池已锁定，请先解锁', 'locked': True}), 403
                encrypt_key = encryption_manager.unlocked_keys[pool_key]

            for uploaded_file in uploaded_files:
                file_data = uploaded_file.read()

                # 如果有加密密钥，加密文件内容
                if encrypt_key:
                    from encryption import xor_cipher
                    file_data = xor_cipher(file_data, encrypt_key)

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


# ==================== 下载 ====================
@file_bp.route('/api/download', methods=['GET'])
@permission_required('readonly')
def api_download():
    """下载文件"""
    file_path = request.args.get("path", "").strip()
    if not file_path:
        return jsonify({"error": "缺少 path 参数"}), 400

    load_json = _ctx['load_json']
    decode_from_dict = _ctx['decode_from_dict']
    encryption_manager = _ctx['encryption_manager']
    Storage_pool = _ctx['Storage_pool']

    # 分支 1: EC卷
    if _is_ec_volume(file_path):
        name = file_path.replace("\\", "/").strip("/").split("/", 1)[-1]
        if not name:
            return jsonify({"error": "无效的逻辑盘文件路径"}), 400

        idx = load_json(_ctx['EC_IDX_PATH'], {"files": {}}).get("files", {})
        entry = idx.get(name)
        if not entry:
            return jsonify({"error": "文件不在逻辑盘索引中"}), 404

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
            return jsonify({"error": "可用分片不足，无法恢复"}), 409

        try:
            data = decode_from_dict(shard_dict, meta)
        except Exception as e:
            return jsonify({"error": f"解码失败: {e}"}), 500

        if hashlib.sha256(data).hexdigest() != meta.get("sha256"):
            return jsonify({"error": "数据完整性校验失败"}), 500

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
            return jsonify({"error": f"下载失败: {e}"}), 500

    # 分支 3: 物理磁盘
    else:
        try:
            actual_path = get_actual_file_path(file_path)

            if not actual_path or not os.path.exists(actual_path):
                return jsonify({"error": "文件不存在或路径无效"}), 404
            if not is_path_allowed(actual_path):
                return jsonify({"error": "不允许访问该路径"}), 403

            # 新增：判断是否为预览模式
            preview = request.args.get('preview', '').lower() == 'true'

            if encryption_manager.is_path_encrypted(actual_path):
                decrypted_data = encryption_manager.read_encrypted_file(actual_path)
                return send_file(io.BytesIO(decrypted_data),
                                 as_attachment=not preview,
                                 download_name=os.path.basename(actual_path))
            else:
                return send_file(actual_path,
                                 as_attachment=not preview,
                                 download_name=os.path.basename(actual_path))

        except Exception as e:
            return jsonify({'error': f'下载文件时出错: {e}'}), 500


# ==================== 重命名 ====================
@file_bp.route('/api/rename', methods=['POST'])
@permission_required('readwrite')
def api_rename_entry():
    """重命名文件或文件夹"""
    data = request.get_json()
    path = data.get('path')
    new_name = data.get('new_name')

    if not path or not new_name:
        return jsonify({"error": "参数缺失"}), 400

    if '..' in new_name or '/' in new_name or '\\' in new_name:
        return jsonify({"error": "文件名包含非法字符"}), 400

    load_json = _ctx['load_json']
    save_json = _ctx['save_json']
    Storage_pool = _ctx['Storage_pool']

    # 1. EC 卷重命名
    if _is_ec_volume(path):
        try:
            logical_name = path.replace("\\", "/").strip("/")
            if logical_name.startswith("ec_volume/"):
                logical_name = logical_name[len("ec_volume/"):]

            idx = load_json(_ctx['EC_IDX_PATH'], {"files": {}})

            if logical_name not in idx.get("files", {}):
                return jsonify({"error": "EC卷文件不存在"}), 404

            parent_dir = os.path.dirname(logical_name)
            new_logical_name = os.path.join(parent_dir, new_name).replace("\\", "/")

            if new_logical_name in idx.get("files", {}):
                return jsonify({"error": "目标文件名已存在"}), 400

            file_meta = idx["files"][logical_name]
            disks = file_meta.get("disks", [])
            base_old_name = os.path.basename(logical_name)

            for i, disk in enumerate(disks[:file_meta["k"] + file_meta["m"]]):
                enc_dir = os.path.join(disk, "encoded", os.path.dirname(logical_name))

                old_blk = os.path.join(enc_dir, f"{base_old_name}.blk_{i}")
                new_blk = os.path.join(enc_dir, f"{new_name}.blk_{i}")
                if os.path.exists(old_blk):
                    os.rename(old_blk, new_blk)

                old_meta = os.path.join(enc_dir, f"{base_old_name}.meta.json")
                new_meta = os.path.join(enc_dir, f"{new_name}.meta.json")
                if os.path.exists(old_meta):
                    os.rename(old_meta, new_meta)

            idx["files"][new_logical_name] = idx["files"].pop(logical_name)
            save_json(_ctx['EC_IDX_PATH'], idx)

            return jsonify({"success": True, "message": "EC卷文件重命名成功"})

        except Exception as e:
            return jsonify({"error": f"EC卷重命名失败: {str(e)}"}), 500

    # 2. 空间池卷重命名
    elif _is_pool_volume(path):
        try:
            volume, subpath, filename = _parse_pool_path(path)
            virtual_path = f"{volume}/{subpath}/{filename}" if subpath else f"{volume}/{filename}"

            config = Storage_pool.load_config()

            if virtual_path not in config.get("files", {}):
                return jsonify({"error": "池卷文件不存在"}), 404

            new_virtual_path = f"{volume}/{subpath}/{new_name}" if subpath else f"{volume}/{new_name}"

            if new_virtual_path in config.get("files", {}):
                return jsonify({"error": "目标文件名已存在"}), 400

            file_info = config["files"][virtual_path]
            old_full_path = os.path.join(file_info["disk"], file_info["real_path"])
            new_real_path = os.path.join(os.path.dirname(file_info["real_path"]), new_name)
            new_full_path = os.path.join(file_info["disk"], new_real_path)

            os.rename(old_full_path, new_full_path)

            config["files"][new_virtual_path] = config["files"].pop(virtual_path)
            config["files"][new_virtual_path]["real_path"] = new_real_path
            Storage_pool.save_config(config)

            return jsonify({"success": True, "message": "池卷文件重命名成功"})

        except Exception as e:
            return jsonify({"error": f"池卷重命名失败: {str(e)}"}), 500

    # 3. 物理盘重命名
    else:
        try:
            actual_path = get_actual_file_path(path)

            if not actual_path or not os.path.exists(actual_path):
                return jsonify({"error": "源文件不存在"}), 404

            if not is_path_allowed(actual_path):
                return jsonify({"error": "路径不在允许的目录中"}), 403

            parent_dir = os.path.dirname(actual_path)
            new_actual_path = os.path.join(parent_dir, new_name)

            if os.path.exists(new_actual_path):
                return jsonify({"error": "目标文件名已存在"}), 400

            os.rename(actual_path, new_actual_path)
            return jsonify({"success": True})

        except Exception as e:
            return jsonify({"error": f"重命名失败: {str(e)}"}), 500


# ==================== 删除 ====================
@file_bp.route('/api/delete', methods=['POST'])
@permission_required('fullcontrol')
def delete_entry():
    """删除文件或文件夹"""
    data = request.get_json()
    path = data.get('path')

    if not path:
        return jsonify({'error': '缺少路径参数'}), 400

    load_json = _ctx['load_json']
    save_json = _ctx['save_json']
    Storage_pool = _ctx['Storage_pool']

    # 1. EC 卷删除
    if _is_ec_volume(path):
        if path.endswith('/'):
            return jsonify({"error": "EC卷暂不支持删除虚拟目录"}), 400

        idx = load_json(_ctx['EC_IDX_PATH'], {"files": {}})
        logical_name = path.replace("\\", "/").strip("/")
        if logical_name.startswith("ec_volume/"):
            logical_name = logical_name[len("ec_volume/"):]

        if logical_name in idx.get("files", {}):
            disks_to_clean = idx["files"][logical_name]["disks"]
            del idx["files"][logical_name]
            save_json(_ctx['EC_IDX_PATH'], idx)

            base = os.path.basename(logical_name)
            for disk in disks_to_clean:
                enc_dir = os.path.join(disk, "encoded", os.path.dirname(logical_name))
                for file_ext in [f"{base}.blk_*", f"{base}.meta.json"]:
                    for f in glob.glob(os.path.join(enc_dir, file_ext)):
                        os.remove(f)

            return jsonify({"success": True, "message": "EC卷文件已删除"})
        else:
            return jsonify({"error": "EC卷文件不存在"}), 404

    # 2. 空间池卷删除
    elif _is_pool_volume(path):
        try:
            volume, subpath, filename = _parse_pool_path(path)
            virtual_path = f"{volume}/{subpath}/{filename}" if subpath else f"{volume}/{filename}"
            Storage_pool.delete_file(virtual_path)
            return jsonify({"success": True, "message": "池卷文件已删除"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # 3. 物理盘删除
    else:
        actual_path = get_actual_file_path(path)

        if not actual_path:
            return jsonify({'error': '文件或目录不存在'}), 404

        if not is_path_allowed(actual_path):
            return jsonify({"error": "路径不在允许的目录中"}), 403

        try:
            if os.path.isdir(actual_path):
                shutil.rmtree(actual_path)
            else:
                os.remove(actual_path)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': f'删除失败: {str(e)}'}), 500


# ==================== 批量删除 ====================
@file_bp.route('/api/batch_delete', methods=['POST'])
@permission_required('fullcontrol')
def batch_delete():
    """批量删除"""
    data = request.get_json()
    paths = data.get('paths', [])
    errors = []

    load_json = _ctx['load_json']
    save_json = _ctx['save_json']
    Storage_pool = _ctx['Storage_pool']

    for path in paths:
        try:
            # 1. EC卷
            if _is_ec_volume(path):
                if path.endswith('/'):
                    errors.append(f"{path}: EC卷不支持删除目录")
                    continue

                idx = load_json(_ctx['EC_IDX_PATH'], {"files": {}})
                logical_name = path.replace("\\", "/").strip("/")
                if logical_name.startswith("ec_volume/"):
                    logical_name = logical_name[len("ec_volume/"):]

                if logical_name in idx.get("files", {}):
                    disks_to_clean = idx["files"][logical_name]["disks"]
                    del idx["files"][logical_name]
                    save_json(_ctx['EC_IDX_PATH'], idx)

                    base = os.path.basename(logical_name)
                    for disk in disks_to_clean:
                        enc_dir = os.path.join(disk, "encoded", os.path.dirname(logical_name))
                        for file_ext in [f"{base}.blk_*", f"{base}.meta.json"]:
                            for f in glob.glob(os.path.join(enc_dir, file_ext)):
                                os.remove(f)
                else:
                    errors.append(f"{path}: EC卷文件不存在")

            # 2. 空间池卷
            elif _is_pool_volume(path):
                volume, subpath, filename = _parse_pool_path(path)
                virtual_path = f"{volume}/{subpath}/{filename}" if subpath else f"{volume}/{filename}"
                Storage_pool.delete_file(virtual_path)

            # 3. 物理盘
            else:
                actual_path = path.replace('/', '\\') if os.name == 'nt' else path
                if os.path.isfile(actual_path):
                    os.remove(actual_path)
                elif os.path.isdir(actual_path):
                    shutil.rmtree(actual_path)
                else:
                    errors.append(f"{path}: 文件不存在")

        except Exception as e:
            errors.append(f"{path}: {str(e)}")

    if errors:
        return jsonify({"success": False, "errors": errors}), 400
    return jsonify({"success": True})


# ==================== 创建文件夹 ====================
@file_bp.route('/api/mkdir', methods=['POST'])
@permission_required('readwrite')
def mkdir():
    """创建文件夹"""
    data = request.get_json()
    path = data.get('path', '')
    parent = data.get('parent', '')
    name = data.get('name', '').strip()
    Storage_pool = _ctx['Storage_pool']

    if path and not parent:
        path = path.replace("\\", "/").rstrip("/")
        parent = os.path.dirname(path)
        name = os.path.basename(path)

    if not name:
        return jsonify({'error': '文件夹名不能为空'}), 400

    # 1. EC卷
    if _is_ec_volume(parent) or _is_ec_volume(path):
        return jsonify({'success': True, 'message': '虚拟目录将在上传文件后自动体现'})

    # 2. 空间池卷
    elif _is_pool_volume(parent) or _is_pool_volume(path):
        try:
            full_path = path if path else f"{parent}/{name}"
            volume, subpath, folder_name = _parse_pool_path(full_path)

            if not folder_name:
                folder_name = subpath
                subpath = ""

            Storage_pool.create_folder(volume, subpath, folder_name)
            return jsonify({'success': True, 'message': '文件夹创建成功'})
        except Exception as e:
            return jsonify({'error': f'创建失败: {str(e)}'}), 500

    # 3. 物理硬盘
    else:
        try:
            if path:
                new_dir_abs_path = os.path.abspath(path)
            else:
                parent_abs_path = os.path.abspath(parent)
                new_dir_abs_path = os.path.join(parent_abs_path, name)

            allowed = False
            for base_dir in get_available_drives():
                if new_dir_abs_path.upper().startswith(os.path.abspath(base_dir).upper()):
                    allowed = True
                    break

            if not allowed:
                return jsonify({'error': '路径非法或不允许访问的磁盘'}), 403

            os.makedirs(new_dir_abs_path, exist_ok=False)
            return jsonify({'success': True})
        except FileExistsError:
            return jsonify({'error': '文件夹已存在'}), 400
        except Exception as e:
            return jsonify({'error': '创建失败: ' + str(e)}), 500


# ==================== 移动 ====================
@file_bp.route('/api/move', methods=['POST'])
@permission_required('readwrite')
def move_entry():
    """移动文件或文件夹"""
    data = request.get_json()
    source_full_path = data.get('source_path')
    target_full_path = data.get('target_path')

    if not source_full_path or not target_full_path:
        return jsonify({"error": "参数缺失"}), 400

    load_json = _ctx['load_json']
    save_json = _ctx['save_json']
    Storage_pool = _ctx['Storage_pool']

    source_is_ec = _is_ec_volume(source_full_path)
    source_is_pool = _is_pool_volume(source_full_path)
    target_is_ec = _is_ec_volume(target_full_path)
    target_is_pool = _is_pool_volume(target_full_path)

    # 1. EC 卷内部移动
    if source_is_ec and target_is_ec:
        try:
            source_logical = source_full_path.replace("\\", "/").strip("/").split("/", 1)[-1]
            target_logical = target_full_path.replace("\\", "/").strip("/").split("/", 1)[-1]

            idx = load_json(_ctx['EC_IDX_PATH'], {"files": {}})
            if source_logical not in idx.get("files", {}):
                return jsonify({"error": "EC源文件不存在"}), 404
            if target_logical in idx.get("files", {}):
                return jsonify({"error": "EC目标文件已存在"}), 400

            file_meta = idx["files"][source_logical]
            disks = file_meta.get("disks", [])
            base_old_name = os.path.basename(source_logical)
            base_new_name = os.path.basename(target_logical)

            for i, disk in enumerate(disks[:file_meta["k"] + file_meta["m"]]):
                old_enc_dir = os.path.join(disk, "encoded", os.path.dirname(source_logical))
                new_enc_dir = os.path.join(disk, "encoded", os.path.dirname(target_logical))
                os.makedirs(new_enc_dir, exist_ok=True)

                old_blk = os.path.join(old_enc_dir, f"{base_old_name}.blk_{i}")
                new_blk = os.path.join(new_enc_dir, f"{base_new_name}.blk_{i}")
                if os.path.exists(old_blk):
                    os.rename(old_blk, new_blk)

                old_meta = os.path.join(old_enc_dir, f"{base_old_name}.meta.json")
                new_meta = os.path.join(new_enc_dir, f"{base_new_name}.meta.json")
                if os.path.exists(old_meta):
                    os.rename(old_meta, new_meta)

            idx["files"][target_logical] = idx["files"].pop(source_logical)
            save_json(_ctx['EC_IDX_PATH'], idx)

            return jsonify({"success": True, "message": "EC文件移动成功"})
        except Exception as e:
            return jsonify({"error": f"EC文件移动失败: {str(e)}"}), 500

    # 2. 空间池卷内部移动
    elif source_is_pool and target_is_pool:
        try:
            src_volume, src_subpath, src_filename = _parse_pool_path(source_full_path)
            tgt_volume, tgt_subpath, tgt_filename = _parse_pool_path(target_full_path)

            src_virtual = f"{src_volume}/{src_subpath}/{src_filename}" if src_subpath else f"{src_volume}/{src_filename}"
            tgt_virtual = f"{tgt_volume}/{tgt_subpath}/{tgt_filename}" if tgt_subpath else f"{tgt_volume}/{tgt_filename}"

            config = Storage_pool.load_config()

            if src_virtual not in config.get("files", {}):
                return jsonify({"error": "源文件不存在"}), 404
            if tgt_virtual in config.get("files", {}):
                return jsonify({"error": "目标文件已存在"}), 400

            file_info = config["files"][src_virtual]
            old_full_path = os.path.join(file_info["disk"], file_info["real_path"])

            new_real_path = f".pool/{tgt_volume}/{tgt_subpath}/{tgt_filename}" if tgt_subpath else f".pool/{tgt_volume}/{tgt_filename}"
            new_full_path = os.path.join(file_info["disk"], new_real_path)

            os.makedirs(os.path.dirname(new_full_path), exist_ok=True)
            os.rename(old_full_path, new_full_path)

            config["files"][tgt_virtual] = {
                "disk": file_info["disk"],
                "real_path": new_real_path,
                "size": file_info["size"],
                "mtime": int(time.time())
            }
            del config["files"][src_virtual]
            Storage_pool.save_config(config)

            return jsonify({"success": True, "message": "池卷文件移动成功"})
        except Exception as e:
            return jsonify({"error": f"池卷文件移动失败: {str(e)}"}), 500

    # 3. 跨卷移动暂不支持
    elif source_is_ec or target_is_ec or source_is_pool or target_is_pool:
        return jsonify({"error": "暂不支持跨卷类型移动，请使用复制后删除"}), 400

    # 4. 物理磁盘移动
    else:
        try:
            source_actual = get_actual_file_path(source_full_path)

            target_drive = os.path.splitdrive(target_full_path)[0]
            target_base_dir = get_base_dir_for_path(target_drive)
            if not target_base_dir:
                return jsonify({"error": "目标路径无效"}), 403

            target_rel_path = target_full_path.replace(target_drive, "").lstrip("/\\")
            target_actual = os.path.join(target_base_dir, target_rel_path)

            if not source_actual or not os.path.exists(source_actual):
                return jsonify({"error": "源文件不存在"}), 404
            if not is_path_allowed(source_actual) or not is_path_allowed(target_actual):
                return jsonify({"error": "路径不在允许的目录中"}), 403
            if os.path.exists(target_actual):
                return jsonify({"error": "目标文件已存在"}), 400

            os.makedirs(os.path.dirname(target_actual), exist_ok=True)
            os.rename(source_actual, target_actual)
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": f"移动失败: {str(e)}"}), 500


# ==================== 复制 ====================
@file_bp.route('/api/copy', methods=['POST'])
@permission_required('readwrite')
def copy_entry():
    """复制文件或文件夹"""
    data = request.get_json()
    source_full_path = data.get('source_path')
    target_full_path = data.get('target_path')

    if not source_full_path or not target_full_path:
        return jsonify({"error": "参数缺失"}), 400

    load_json = _ctx['load_json']
    save_json = _ctx['save_json']
    decode_from_dict = _ctx['decode_from_dict']
    rs_encode = _ctx['rs_encode']
    encryption_manager = _ctx['encryption_manager']
    Storage_pool = _ctx['Storage_pool']

    source_is_ec = _is_ec_volume(source_full_path)
    source_is_pool = _is_pool_volume(source_full_path)
    target_is_ec = _is_ec_volume(target_full_path)
    target_is_pool = _is_pool_volume(target_full_path)

    # 辅助函数：读取源文件
    def read_source_data():
        if source_is_ec:
            source_logical = source_full_path.replace("\\", "/").strip("/").split("/", 1)[-1]
            idx = load_json(_ctx['EC_IDX_PATH'], {"files": {}})

            if source_logical not in idx.get("files", {}):
                raise Exception("EC源文件不存在")

            meta = idx["files"][source_logical]
            k, m = meta["k"], meta["m"]
            disks = meta.get("disks", [])

            shard_dict = {}
            for i, disk in enumerate(disks[:k + m]):
                enc_dir = os.path.join(disk, "encoded", os.path.dirname(source_logical))
                blk_path = os.path.join(enc_dir, f"{os.path.basename(source_logical)}.blk_{i}")
                if os.path.exists(blk_path):
                    with open(blk_path, "rb") as f:
                        shard_dict[i] = f.read()

            if len(shard_dict) < k:
                raise Exception("分片不足，无法恢复文件")

            return decode_from_dict(shard_dict, meta), os.path.basename(source_logical)

        elif source_is_pool:
            src_volume, src_subpath, src_filename = _parse_pool_path(source_full_path)
            src_virtual = f"{src_volume}/{src_subpath}/{src_filename}" if src_subpath else f"{src_volume}/{src_filename}"
            actual_path = Storage_pool.get_file_path(src_virtual)

            if not actual_path or not os.path.exists(actual_path):
                raise Exception("池卷源文件不存在")

            with open(actual_path, "rb") as f:
                return f.read(), src_filename

        else:
            source_actual = get_actual_file_path(source_full_path)

            if not source_actual or not os.path.exists(source_actual):
                raise Exception("源文件不存在")
            if not is_path_allowed(source_actual):
                raise Exception("源路径不在允许的目录中")
            if os.path.isdir(source_actual):
                raise Exception("暂不支持复制文件夹到其他卷类型")

            if encryption_manager.is_path_encrypted(source_actual):
                return encryption_manager.read_encrypted_file(source_actual), os.path.basename(source_actual)
            else:
                with open(source_actual, "rb") as f:
                    return f.read(), os.path.basename(source_actual)

    # 辅助函数：写入目标
    def write_to_ec(file_data, target_path):
        target_logical = target_path.replace("\\", "/").strip("/").split("/", 1)[-1]

        idx = load_json(_ctx['EC_IDX_PATH'], {"files": {}})
        if target_logical in idx.get("files", {}):
            raise Exception("EC目标文件已存在")

        cfg = load_json(_ctx['EC_CFG_PATH'], {})
        if not cfg:
            raise Exception("纠删码未配置")

        k, m = cfg.get("k", 0), cfg.get("m", 0)
        disks = cfg.get("disks", [])

        shards = rs_encode(file_data, k, m)
        file_sha = hashlib.sha256(file_data).hexdigest()

        for i, disk in enumerate(disks[:k + m]):
            enc_dir = os.path.join(disk, "encoded", os.path.dirname(target_logical))
            os.makedirs(enc_dir, exist_ok=True)
            with open(os.path.join(enc_dir, f"{os.path.basename(target_logical)}.blk_{i}"), "wb") as f:
                f.write(shards[i])
            meta_data = {"k": k, "m": m, "size": len(file_data), "original_size": len(file_data),
                         "shard_size": (len(file_data) + k - 1) // k, "sha256": file_sha}
            with open(os.path.join(enc_dir, f"{os.path.basename(target_logical)}.meta.json"), "w", encoding="utf-8") as mf:
                json.dump(meta_data, mf)

        idx["files"][target_logical] = {
            "k": k, "m": m, "size": len(file_data), "sha256": file_sha,
            "disks": disks[:k + m], "ctime": int(time.time())
        }
        save_json(_ctx['EC_IDX_PATH'], idx)

    def write_to_pool(file_data, target_path):
        tgt_volume, tgt_subpath, tgt_filename = _parse_pool_path(target_path)
        Storage_pool.add_file(tgt_volume, tgt_subpath, tgt_filename, file_data)

    def write_to_physical(file_data, target_path):
        target_drive = os.path.splitdrive(target_path)[0]
        target_base_dir = get_base_dir_for_path(target_drive)
        if not target_base_dir:
            raise Exception("目标路径无效")

        target_rel_path = target_path.replace(target_drive, "").lstrip("/\\")
        target_actual = os.path.join(target_base_dir, target_rel_path)

        if not is_path_allowed(target_actual):
            raise Exception("目标路径不在允许的目录中")
        if os.path.exists(target_actual):
            raise Exception("目标文件已存在")

        os.makedirs(os.path.dirname(target_actual), exist_ok=True)

        if encryption_manager.is_path_encrypted(target_actual):
            encryption_manager.write_encrypted_file(target_actual, file_data)
        else:
            with open(target_actual, "wb") as f:
                f.write(file_data)

    # 跨卷复制
    source_type = 'ec' if source_is_ec else ('pool' if source_is_pool else 'physical')
    target_type = 'ec' if target_is_ec else ('pool' if target_is_pool else 'physical')

    if source_type != target_type:
        try:
            file_data, filename = read_source_data()

            if target_is_ec:
                write_to_ec(file_data, target_full_path)
                return jsonify({"success": True, "message": "文件已复制到EC卷"})
            elif target_is_pool:
                write_to_pool(file_data, target_full_path)
                return jsonify({"success": True, "message": "文件已复制到池卷"})
            else:
                write_to_physical(file_data, target_full_path)
                return jsonify({"success": True, "message": "文件已复制到物理磁盘"})

        except Exception as e:
            return jsonify({"error": f"跨卷复制失败: {str(e)}"}), 500

    # 同类型卷内部复制
    if source_is_ec:
        try:
            source_logical = source_full_path.replace("\\", "/").strip("/").split("/", 1)[-1]
            target_logical = target_full_path.replace("\\", "/").strip("/").split("/", 1)[-1]

            idx = load_json(_ctx['EC_IDX_PATH'], {"files": {}})
            if source_logical not in idx.get("files", {}):
                return jsonify({"error": "EC源文件不存在"}), 404
            if target_logical in idx.get("files", {}):
                return jsonify({"error": "EC目标文件已存在"}), 400

            file_meta = idx["files"][source_logical].copy()
            disks = file_meta.get("disks", [])

            for i, disk in enumerate(disks[:file_meta["k"] + file_meta["m"]]):
                old_enc_dir = os.path.join(disk, "encoded", os.path.dirname(source_logical))
                new_enc_dir = os.path.join(disk, "encoded", os.path.dirname(target_logical))
                os.makedirs(new_enc_dir, exist_ok=True)

                old_blk = os.path.join(old_enc_dir, f"{os.path.basename(source_logical)}.blk_{i}")
                new_blk = os.path.join(new_enc_dir, f"{os.path.basename(target_logical)}.blk_{i}")
                if os.path.exists(old_blk):
                    shutil.copy2(old_blk, new_blk)

                old_meta = os.path.join(old_enc_dir, f"{os.path.basename(source_logical)}.meta.json")
                new_meta = os.path.join(new_enc_dir, f"{os.path.basename(target_logical)}.meta.json")
                if os.path.exists(old_meta):
                    shutil.copy2(old_meta, new_meta)

            file_meta['ctime'] = int(time.time())
            idx["files"][target_logical] = file_meta
            save_json(_ctx['EC_IDX_PATH'], idx)

            return jsonify({"success": True, "message": "EC文件复制成功"})
        except Exception as e:
            return jsonify({"error": f"EC文件复制失败: {str(e)}"}), 500

    elif source_is_pool:
        try:
            src_volume, src_subpath, src_filename = _parse_pool_path(source_full_path)
            tgt_volume, tgt_subpath, tgt_filename = _parse_pool_path(target_full_path)

            src_virtual = f"{src_volume}/{src_subpath}/{src_filename}" if src_subpath else f"{src_volume}/{src_filename}"
            tgt_virtual = f"{tgt_volume}/{tgt_subpath}/{tgt_filename}" if tgt_subpath else f"{tgt_volume}/{tgt_filename}"

            config = Storage_pool.load_config()

            if src_virtual not in config.get("files", {}):
                return jsonify({"error": "池卷源文件不存在"}), 404
            if tgt_virtual in config.get("files", {}):
                return jsonify({"error": "池卷目标文件已存在"}), 400

            src_info = config["files"][src_virtual]
            src_full_path = os.path.join(src_info["disk"], src_info["real_path"])

            with open(src_full_path, "rb") as f:
                file_data = f.read()

            Storage_pool.add_file(tgt_volume, tgt_subpath, tgt_filename, file_data)

            return jsonify({"success": True, "message": "池卷文件复制成功"})
        except Exception as e:
            return jsonify({"error": f"池卷文件复制失败: {str(e)}"}), 500

    else:
        try:
            source_actual = get_actual_file_path(source_full_path)

            target_drive = os.path.splitdrive(target_full_path)[0]
            target_base_dir = get_base_dir_for_path(target_drive)
            if not target_base_dir:
                return jsonify({"error": "目标路径无效"}), 403

            target_rel_path = target_full_path.replace(target_drive, "").lstrip("/\\")
            target_actual = os.path.join(target_base_dir, target_rel_path)

            if not source_actual or not os.path.exists(source_actual):
                return jsonify({"error": "源文件不存在"}), 404
            if not is_path_allowed(source_actual) or not is_path_allowed(target_actual):
                return jsonify({"error": "路径不在允许的目录中"}), 403
            if os.path.exists(target_actual):
                return jsonify({"error": "目标文件已存在"}), 400

            if os.path.isdir(source_actual):
                shutil.copytree(source_actual, target_actual)
            else:
                os.makedirs(os.path.dirname(target_actual), exist_ok=True)
                shutil.copy2(source_actual, target_actual)

            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": f"复制失败: {str(e)}"}), 500


# ==================== 预览 ====================
@file_bp.route('/api/preview')
@permission_required('readonly')
def preview_file():
    """预览文件"""
    path = request.args.get('path', '').strip()
    if not path:
        return jsonify({'error': '未指定文件路径'}), 400

    load_json = _ctx['load_json']
    decode_from_dict = _ctx['decode_from_dict']
    encryption_manager = _ctx['encryption_manager']

    # EC卷预览
    if _is_ec_volume(path):
        logical_path = get_actual_file_path(path)
        index_key = logical_path.replace('ec_volume/', '', 1).strip('/')

        if not index_key:
            return jsonify({'error': 'EC 卷路径无效'}), 400

        idx = load_json(_ctx['EC_IDX_PATH'], {"files": {}})
        entry = idx.get("files", {}).get(index_key)

        if not entry:
            return jsonify({'error': 'EC 卷文件不存在'}), 404

        k, m, disks = entry["k"], entry["m"], entry["disks"]
        shard_dict, meta = {}, None
        base_filename = os.path.basename(index_key)

        for i, disk in enumerate(disks[:k + m]):
            enc_dir = os.path.join(disk, "encoded", os.path.dirname(index_key))
            blk = os.path.join(enc_dir, f"{base_filename}.blk_{i}")
            if os.path.exists(blk):
                with open(blk, "rb") as f:
                    shard_dict[i] = f.read()
            if not meta:
                mj = os.path.join(enc_dir, f"{base_filename}.meta.json")
                if os.path.exists(mj):
                    with open(mj, "r", encoding="utf-8") as mf:
                        meta = json.load(mf)

        if not meta or len(shard_dict) < k:
            return jsonify({'error': '可用分片不足，无法恢复'}), 409

        try:
            data = decode_from_dict(shard_dict, meta)
        except Exception as e:
            return jsonify({'error': f'EC 卷文件解码失败: {e}'}), 500

        mime = mimetypes.guess_type(index_key)[0] or 'application/octet-stream'
        return send_file(io.BytesIO(data), mimetype=mime)

    # 物理磁盘预览
    else:
        try:
            actual_path = get_actual_file_path(path)

            if not actual_path or not os.path.exists(actual_path):
                return jsonify({'error': '文件不存在或路径无效'}), 404
            if not is_path_allowed(actual_path):
                return jsonify({'error': '路径不在允许的目录中'}), 403

            decrypted_data = None
            if encryption_manager.is_path_encrypted(actual_path):
                decrypted_data = encryption_manager.read_encrypted_file(actual_path)

            mime = mimetypes.guess_type(actual_path)[0] or 'application/octet-stream'

            if decrypted_data is not None:
                return send_file(io.BytesIO(decrypted_data), mimetype=mime)
            else:
                return send_file(actual_path, mimetype=mime)

        except Exception as e:
            return jsonify({'error': f'预览失败: {e}'}), 500


# ==================== 搜索 ====================
@file_bp.route('/api/search_global', methods=['GET'])
@permission_required('readonly')
def search_files_global():
    """全局搜索"""
    keyword = request.args.get('keyword', '').strip()
    max_results = int(request.args.get('limit', 200))

    if not keyword:
        return jsonify({'error': '请输入搜索关键词'}), 400

    load_json = _ctx['load_json']
    results = []
    keyword_lower = keyword.lower()

    try:
        # 1. 搜索EC卷
        ec_idx = load_json(_ctx['EC_IDX_PATH'], {})
        for file_key, meta in ec_idx.items():
            file_name = file_key.split('/')[-1]
            if keyword_lower in file_name.lower():
                results.append({
                    'name': file_name,
                    'path': 'ec_volume/' + file_key,
                    'full_path': 'ec_volume/' + file_key,
                    'source': '容错存储',
                    'is_dir': False,
                    'size': meta.get('size', 0),
                    'mtime': meta.get('mtime', 0)
                })
                if len(results) >= max_results:
                    break

        # 2. 搜索物理磁盘
        available_drives = get_available_drives()
        for drive in available_drives:
            if len(results) >= max_results:
                break
            try:
                for root, dirs, files in os.walk(drive):
                    if any(skip in root.lower() for skip in ['windows', 'program files', '$recycle', 'system volume']):
                        continue

                    for d in dirs:
                        if keyword_lower in d.lower():
                            full_path = os.path.join(root, d)
                            try:
                                stat = os.stat(full_path)
                                results.append({
                                    'name': d,
                                    'path': full_path.replace('\\', '/'),
                                    'full_path': full_path.replace('\\', '/'),
                                    'source': drive.replace(':/', '').replace('/', '') + '盘',
                                    'is_dir': True,
                                    'size': 0,
                                    'mtime': stat.st_mtime
                                })
                            except:
                                pass
                            if len(results) >= max_results:
                                break

                    for f in files:
                        if keyword_lower in f.lower():
                            full_path = os.path.join(root, f)
                            try:
                                stat = os.stat(full_path)
                                results.append({
                                    'name': f,
                                    'path': full_path.replace('\\', '/'),
                                    'full_path': full_path.replace('\\', '/'),
                                    'source': drive.replace(':/', '').replace('/', '') + '盘',
                                    'is_dir': False,
                                    'size': stat.st_size,
                                    'mtime': stat.st_mtime
                                })
                            except:
                                pass
                            if len(results) >= max_results:
                                break

                    if len(results) >= max_results:
                        break
            except Exception as e:
                continue

        return jsonify({
            'success': True,
            'keyword': keyword,
            'count': len(results),
            'items': results
        })

    except Exception as e:
        return jsonify({'error': f'搜索失败: {str(e)}'}), 500
# ==================== 预览会话管理 ====================
import secrets
import tempfile
from datetime import datetime, timedelta

# 预览会话存储
preview_sessions = {}

@file_bp.route('/api/create-preview-session', methods=['POST'])
@permission_required('readonly')
def create_preview_session():
    """创建预览会话"""
    try:
        data = request.get_json()
        file_path = data.get('file_path')
        file_type = data.get('file_type', 'pdf')

        if not file_path:
            return jsonify({'error': '缺少文件路径'}), 400

        print(f"[DEBUG] 创建预览会话请求: {file_path}")

        load_json = _ctx['load_json']
        decode_from_dict = _ctx['decode_from_dict']
        encryption_manager = _ctx['encryption_manager']
        Storage_pool = _ctx['Storage_pool']

        real_path_for_preview = None
        is_temp = False

        # 1. 处理纠删码卷 (EC)
        if _is_ec_volume(file_path):
            try:
                name = file_path.replace("\\", "/").strip("/").split("/", 1)[-1]
                idx = load_json(_ctx['EC_IDX_PATH'], {"files": {}}).get("files", {})
                entry = idx.get(name)

                if not entry:
                    return jsonify({'error': 'EC文件索引不存在'}), 404

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
                    return jsonify({'error': 'EC分片不足，无法预览'}), 409

                file_data = decode_from_dict(shard_dict, meta)

                temp_dir = tempfile.gettempdir()
                temp_filename = f"preview_ec_{secrets.token_hex(8)}.pdf"
                temp_path = os.path.join(temp_dir, temp_filename)

                with open(temp_path, 'wb') as f:
                    f.write(file_data)

                real_path_for_preview = temp_path
                is_temp = True

            except Exception as e:
                print(f"[ERROR] EC预览还原失败: {e}")
                return jsonify({'error': f'EC文件解析失败: {str(e)}'}), 500

        # 2. 处理空间池卷 (Pool)
        elif _is_pool_volume(file_path):
            try:
                volume, subpath, filename = _parse_pool_path(file_path)
                virtual_path = f"{volume}/{subpath}/{filename}" if subpath else f"{volume}/{filename}"
                real_path_for_preview = Storage_pool.get_file_path(virtual_path)

                if not real_path_for_preview or not os.path.exists(real_path_for_preview):
                    return jsonify({'error': '池卷文件物理路径不存在'}), 404

            except Exception as e:
                return jsonify({'error': f'池卷解析失败: {str(e)}'}), 500

        # 3. 处理普通物理磁盘
        else:
            real_path_for_preview = get_actual_file_path(file_path)

            if not real_path_for_preview or not os.path.exists(real_path_for_preview):
                return jsonify({'error': '文件不存在'}), 404

            if encryption_manager and encryption_manager.is_path_encrypted(real_path_for_preview):
                try:
                    decrypted_data = encryption_manager.read_encrypted_file(real_path_for_preview)

                    temp_dir = tempfile.gettempdir()
                    temp_filename = f"preview_enc_{secrets.token_hex(8)}.pdf"
                    temp_path = os.path.join(temp_dir, temp_filename)

                    with open(temp_path, 'wb') as f:
                        f.write(decrypted_data)

                    real_path_for_preview = temp_path
                    is_temp = True
                except Exception as e:
                    return jsonify({'error': f'解密预览失败: {e}'}), 500

        if not real_path_for_preview or not os.path.exists(real_path_for_preview):
            return jsonify({'error': '无法获取有效的文件路径'}), 404

        session_id = secrets.token_urlsafe(32)
        session_data = {
            'file_path': real_path_for_preview,
            'file_type': file_type,
            'created_at': datetime.now(),
            'expires_at': datetime.now() + timedelta(hours=2),
            'access_count': 0,
            'max_access': 100,
            'is_temp': is_temp
        }

        preview_sessions[session_id] = session_data

        return jsonify({
            'success': True,
            'session_id': session_id,
            'expires_at': session_data['expires_at'].isoformat(),
            'message': '预览会话创建成功'
        })

    except Exception as e:
        print(f"[DEBUG] 创建预览会话异常: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'创建预览会话失败: {str(e)}'}), 500


@file_bp.route('/api/preview-session/<session_id>')
def access_preview_session(session_id):
    """访问预览会话"""
    print(f"[DEBUG] 访问预览会话: {session_id}")

    if session_id not in preview_sessions:
        return jsonify({'error': '预览会话不存在或已过期'}), 404

    session_data = preview_sessions[session_id]

    if datetime.now() > session_data['expires_at']:
        del preview_sessions[session_id]
        return jsonify({'error': '预览会话已过期'}), 403

    if session_data['access_count'] >= session_data['max_access']:
        return jsonify({'error': '访问次数已达上限'}), 403

    session_data['access_count'] += 1
    file_path = session_data['file_path']

    try:
        if session_data['file_type'] == 'pdf':
            if not os.path.exists(file_path):
                return jsonify({'error': '文件不存在'}), 404

            response = send_file(file_path, mimetype='application/pdf')
            response.headers['Content-Disposition'] = 'inline'
            response.headers['Cache-Control'] = 'public, max-age=3600'
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response
        else:
            return jsonify({'error': '不支持的文件类型'}), 400

    except ConnectionAbortedError:
        # 客户端主动断开连接，忽略此错误
        print(f"[DEBUG] 预览会话客户端断开连接: {session_id}")
        return '', 499  # 499 是 nginx 用的客户端关闭连接状态码
    except (BrokenPipeError, ConnectionResetError) as e:
        print(f"[DEBUG] 预览连接异常: {e}")
        return '', 499
    except Exception as e:
        print(f"[DEBUG] 预览会话文件访问失败: {e}")
        return jsonify({'error': '文件访问失败'}), 500



# ==================== 内部接口（供管理端调用）====================
from config import NAS_SHARED_SECRET

@file_bp.route('/api/internal/upload', methods=['POST'])
def internal_upload():
    """内部上传接口 - 供管理端跨节点池使用"""
    # 验证密钥
    secret = request.headers.get('X-NAS-Secret')
    if secret != NAS_SHARED_SECRET:
        return jsonify({'error': '权限不足'}), 403

    uploaded_files = request.files.getlist('file')
    upload_path = request.form.get('path', '')

    if not uploaded_files or not upload_path:
        return jsonify({'error': '缺少文件或路径'}), 400

    try:
        # 创建目录
        os.makedirs(upload_path, exist_ok=True)

        saved = []
        for f in uploaded_files:
            if f.filename:
                target = os.path.join(upload_path, f.filename)
                f.save(target)
                saved.append(f.filename)

        return jsonify({'success': True, 'files': saved})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@file_bp.route('/api/internal/download', methods=['GET'])
def internal_download():
    """内部下载接口 - 供管理端跨节点池使用"""
    secret = request.headers.get('X-NAS-Secret')
    if secret != NAS_SHARED_SECRET:
        return jsonify({'error': '权限不足'}), 403

    path = request.args.get('path')
    if not path or not os.path.exists(path):
        return jsonify({'error': '文件不存在'}), 404

    return send_file(path, as_attachment=True)


@file_bp.route('/api/internal/delete', methods=['POST'])
def internal_delete():
    """内部删除接口 - 供管理端跨节点池使用"""
    secret = request.headers.get('X-NAS-Secret')
    if secret != NAS_SHARED_SECRET:
        return jsonify({'error': '权限不足'}), 403

    data = request.get_json()
    path = data.get('path')

    if not path:
        return jsonify({'error': '缺少路径'}), 400

    try:
        if os.path.exists(path):
            if os.path.isfile(path):
                os.remove(path)
            else:
                shutil.rmtree(path)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@file_bp.route('/api/disk-info', methods=['GET'])
def api_disk_info():
    """获取指定磁盘的空间信息（供管理端调用）"""
    from config import NAS_SHARED_SECRET

    secret = request.headers.get('X-NAS-Secret')
    if secret != NAS_SHARED_SECRET:
        return jsonify({'error': '权限不足'}), 403

    path = request.args.get('path', '')
    if not path:
        return jsonify({'error': '缺少路径'}), 400

    try:
        # 处理 Windows 路径
        check_path = path.rstrip('\\').rstrip('/')
        if os.name == 'nt' and len(check_path) == 2 and check_path[1] == ':':
            check_path = check_path + '\\'

        total, used, free = shutil.disk_usage(check_path)
        return jsonify({
            'total': total,
            'used': used,
            'free': free,
            'path': path
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@file_bp.route('/api/internal/scan-dir', methods=['GET'])
def internal_scan_dir():
    """内部接口 - 扫描目录下的所有文件（用于跨节点池重建索引）"""
    from config import NAS_SHARED_SECRET

    secret = request.headers.get('X-NAS-Secret')
    if secret != NAS_SHARED_SECRET:
        return jsonify({'error': '无权访问'}), 403

    path = request.args.get('path')
    if not path:
        return jsonify({'error': '缺少 path 参数'}), 400

    # 规范化路径
    path = path.replace('/', os.sep).replace('\\', os.sep)

    if not os.path.exists(path):
        return jsonify({'error': '目录不存在'}), 404

    if not os.path.isdir(path):
        return jsonify({'error': '路径不是目录'}), 400

    files = []
    try:
        for root, dirs, filenames in os.walk(path):
            for filename in filenames:
                full_path = os.path.join(root, filename)
                # 统一使用正斜杠
                full_path_normalized = full_path.replace('\\', '/')
                try:
                    stat = os.stat(full_path)
                    files.append({
                        'name': filename,
                        'path': full_path_normalized,
                        'size': stat.st_size,
                        'mtime': stat.st_mtime,
                        'is_dir': False
                    })
                except Exception as e:
                    # 跳过无法访问的文件
                    pass
    except Exception as e:
        return jsonify({'error': f'扫描失败: {str(e)}'}), 500

    return jsonify({'files': files, 'count': len(files)})


@file_bp.route('/api/internal/delete-dir', methods=['POST'])
def internal_delete_dir():
    """内部接口 - 删除目录（用于跨节点池清理）"""
    from config import NAS_SHARED_SECRET
    import shutil

    secret = request.headers.get('X-NAS-Secret')
    if secret != NAS_SHARED_SECRET:
        return jsonify({'error': '无权访问'}), 403

    data = request.json or {}
    path = data.get('path')

    if not path:
        return jsonify({'error': '缺少 path 参数'}), 400

    # 规范化路径
    path = path.replace('/', os.sep).replace('\\', os.sep)

    if not os.path.exists(path):
        return jsonify({'success': True, 'message': '目录不存在，无需删除'})

    if not os.path.isdir(path):
        return jsonify({'error': '路径不是目录'}), 400

    try:
        shutil.rmtree(path)
        return jsonify({'success': True, 'message': f'已删除目录: {path}'})
    except Exception as e:
        return jsonify({'error': f'删除失败: {str(e)}'}), 500

