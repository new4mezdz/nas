# routes/encryption_routes.py
import os
import json
import hashlib
import threading
from flask import Blueprint, request, jsonify, current_app

from common import get_available_drives, get_actual_file_path, is_path_allowed
from utils import _norm_abs
from permission_decorator import permission_required

encryption_bp = Blueprint('encryption', __name__)

# 加密任务状态
encryption_tasks_status = {}

# 外部依赖
_ctx = {
    'encryption_manager': None,
    'NAS_SHARED_SECRET': None,
    'load_json': None,
    'save_json': None,
}


def init_encryption_routes(encryption_manager, shared_secret, load_json, save_json):
    _ctx['encryption_manager'] = encryption_manager
    _ctx['NAS_SHARED_SECRET'] = shared_secret
    _ctx['load_json'] = load_json
    _ctx['save_json'] = save_json


# ========== 文件级加密 ==========

@encryption_bp.route('/api/file/encrypt', methods=['POST'])
@permission_required('fullcontrol')
def encrypt_file_api():
    """加密单个文件或文件夹"""
    data = request.get_json()
    file_path = data.get('file_path', '').strip()
    password = data.get('password', '').strip()
    is_folder = data.get('is_folder', False)

    if not file_path or not password:
        return jsonify({'error': '文件路径和密码不能为空'}), 400

    try:
        actual_path = get_actual_file_path(file_path)

        if not actual_path or not os.path.exists(actual_path):
            return jsonify({'error': '文件或文件夹不存在'}), 404

        if not is_path_allowed(actual_path):
            return jsonify({'error': '路径不在允许的目录中'}), 403

        encryption_manager = _ctx['encryption_manager']

        if is_folder:
            results = encryption_manager.encrypt_folder_standalone(actual_path, password)
            return jsonify({
                'success': True,
                'message': f'文件夹加密完成: 成功 {results["success"]} 个，失败 {results["failed"]} 个',
                'details': results
            })
        else:
            success = encryption_manager.encrypt_file_standalone(actual_path, password)
            if success:
                return jsonify({
                    'success': True,
                    'message': f'文件加密成功: {os.path.basename(file_path)}'
                })
            else:
                return jsonify({'error': '文件加密失败'}), 500

    except Exception as e:
        return jsonify({'error': f'加密失败: {str(e)}'}), 500


@encryption_bp.route('/api/file/decrypt', methods=['POST'])
@permission_required('fullcontrol')
def decrypt_file_api():
    """解密单个文件或文件夹"""
    data = request.get_json()
    file_path = data.get('file_path', '').strip()
    password = data.get('password', '').strip()
    is_folder = data.get('is_folder', False)

    if not file_path or not password:
        return jsonify({'error': '文件路径和密码不能为空'}), 400

    try:
        actual_path = get_actual_file_path(file_path)

        if not actual_path or not os.path.exists(actual_path):
            return jsonify({'error': '文件或文件夹不存在'}), 404

        if not is_path_allowed(actual_path):
            return jsonify({'error': '路径不在允许的目录中'}), 403

        encryption_manager = _ctx['encryption_manager']

        if is_folder:
            results = encryption_manager.decrypt_folder_standalone(actual_path, password)
            return jsonify({
                'success': True,
                'message': f'文件夹解密完成: 成功 {results["success"]} 个，失败 {results["failed"]} 个',
                'details': results
            })
        else:
            success = encryption_manager.decrypt_file_standalone(actual_path, password)
            if success:
                return jsonify({
                    'success': True,
                    'message': f'文件解密成功: {os.path.basename(file_path)}'
                })
            else:
                return jsonify({'error': '文件解密失败，请检查密码'}), 500

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'解密失败: {str(e)}'}), 500


# ========== 磁盘级加密 ==========

@encryption_bp.route('/api/encryption/status', methods=['GET'])
@permission_required('fullcontrol')
def encryption_status():
    """获取所有物理磁盘及其加密/锁定状态"""
    encryption_manager = _ctx['encryption_manager']
    all_drives = get_available_drives()
    enc_status = encryption_manager.get_disk_status()

    response = []
    for drive_path in all_drives:
        norm_path = _norm_abs(drive_path)
        status = enc_status.get(norm_path, {
            "is_configured": False,
            "is_unlocked": False
        })
        response.append({
            "drive": drive_path,
            "is_configured": status["is_configured"],
            "is_unlocked": status["is_unlocked"]
        })
    return jsonify(response)


@encryption_bp.route('/api/encryption/unlock', methods=['POST'])
@permission_required('fullcontrol')
def encryption_unlock():
    """解锁单个磁盘"""
    data = request.get_json()
    drive = data.get('drive')
    password = data.get('password', '')

    if not drive or not password:
        return jsonify({'error': '需要提供磁盘和密码'}), 400

    encryption_manager = _ctx['encryption_manager']
    success = encryption_manager.unlock(drive, password)

    if success:
        return jsonify({'success': True, 'message': f'磁盘 {drive} 已解锁'})
    else:
        return jsonify({'error': '密码错误或磁盘未配置加密'}), 403


@encryption_bp.route('/api/encryption/lock', methods=['POST'])
@permission_required('fullcontrol')
def encryption_lock():
    """锁定单个磁盘"""
    data = request.get_json()
    drive = data.get('drive')

    if not drive:
        return jsonify({'error': '需要提供磁盘'}), 400

    encryption_manager = _ctx['encryption_manager']
    encryption_manager.lock(drive)
    return jsonify({'success': True, 'message': f'磁盘 {drive} 已锁定'})


@encryption_bp.route('/api/encryption/decrypt-disk', methods=['POST'])
@permission_required('fullcontrol')
def decrypt_disk_permanently_api():
    """永久解密磁盘"""
    global encryption_tasks_status

    data = request.get_json()
    drive = data.get('drive')
    password = data.get('password')

    if not drive or not password:
        return jsonify({'error': '需要提供磁盘和密码'}), 400

    norm_drive = _norm_abs(drive)
    encryption_manager = _ctx['encryption_manager']
    load_json = _ctx['load_json']
    save_json = _ctx['save_json']

    def update_status_callback(drive_key, message, percent):
        global encryption_tasks_status
        if percent == -1:
            encryption_tasks_status[drive_key] = {'message': message, 'percent': 0, 'status': 'error'}
        elif percent == 100:
            encryption_tasks_status[drive_key] = {'message': message, 'percent': 100, 'status': 'complete'}
        else:
            encryption_tasks_status[drive_key] = {'message': message, 'percent': percent, 'status': 'running'}

    def background_task(app, drive_path, drive_key, pwd):
        with app.app_context():
            try:
                result = encryption_manager.decrypt_disk_permanently(
                    drive_path, pwd,
                    status_callback=lambda d, m, p: update_status_callback(drive_key, m, p)
                )

                if not result.get("failed_files"):
                    config_path = encryption_manager.config_path
                    config = load_json(config_path, {"disks": {}})
                    if drive_key in config.get("disks", {}):
                        del config["disks"][drive_key]
                        save_json(config_path, config)
                        encryption_manager.load_config()
                        print(f"🎉 已从加密配置中移除磁盘 {drive_path}")

            except Exception as e:
                print(f"后台解密任务失败: {e}")
                update_status_callback(drive_key, f"❌ {drive_path}：解密失败: {e}", -1)

    thread = threading.Thread(target=background_task, args=(current_app._get_current_object(), drive, norm_drive, password))
    thread.start()

    return jsonify({'success': True, 'message': f'已开始在后台对磁盘 {drive} 进行永久解密。'})


@encryption_bp.route('/api/encryption/progress', methods=['GET'])
@permission_required('fullcontrol')
def encryption_progress():
    """获取当前所有加密/解密任务的进度"""
    return jsonify(encryption_tasks_status)


@encryption_bp.route('/api/encryption/set-password', methods=['POST'])
@permission_required('fullcontrol')
def set_encryption_password():
    """为单个或多个磁盘设定/变更密码"""
    global encryption_tasks_status

    data = request.get_json()
    drives = data.get('drives', [])
    old_password = data.get('old_password')
    new_password = data.get('new_password')

    if not drives or not new_password:
        return jsonify({'error': '需要提供磁盘列表和新密码'}), 400

    encryption_manager = _ctx['encryption_manager']
    load_json = _ctx['load_json']
    save_json = _ctx['save_json']

    config = load_json(encryption_manager.config_path, {"disks": {}})
    if "disks" not in config or not isinstance(config.get("disks"), dict):
        config["disks"] = {}

    keys_for_encryption = {}

    for drive_path in drives:
        norm_drive = _norm_abs(drive_path)
        is_new_encryption = True

        if norm_drive in config["disks"] and config["disks"][norm_drive].get("password_hash"):
            is_new_encryption = False
            if not old_password:
                return jsonify({'error': f'磁盘 {drive_path} 已有密码，需要提供旧密码才能变更'}), 403

            from encryption import EncryptionManager
            temp_manager = EncryptionManager(encryption_manager.config_path)
            if not temp_manager.unlock(drive_path, old_password):
                return jsonify({'error': f'磁盘 {drive_path} 的旧密码不正确'}), 403

        new_salt = os.urandom(16)
        new_hash = hashlib.pbkdf2_hmac('sha256', new_password.encode('utf-8'), new_salt, 100000)

        config["disks"][norm_drive] = {
            "password_salt": new_salt.hex(),
            "password_hash": new_hash.hex()
        }

        if is_new_encryption:
            derived_key = hashlib.pbkdf2_hmac(
                'sha256', new_password.encode('utf-8'), new_salt, 100000, dklen=32
            )
            keys_for_encryption[norm_drive] = (drive_path, derived_key)

    save_json(encryption_manager.config_path, config)
    encryption_manager.load_config()

    if keys_for_encryption:
        def update_status_callback(drive_key, message, percent):
            global encryption_tasks_status
            if percent == -1:
                encryption_tasks_status[drive_key] = {'message': message, 'percent': 0, 'status': 'error'}
            elif percent == 100:
                encryption_tasks_status[drive_key] = {'message': message, 'percent': 100, 'status': 'complete'}
            else:
                encryption_tasks_status[drive_key] = {'message': message, 'percent': percent, 'status': 'running'}

        def background_task(app_context, drives_to_encrypt):
            with app_context:
                for norm_drive, (original_drive_path, key) in drives_to_encrypt.items():
                    try:
                        encryption_manager.encrypt_disk_permanently(
                            original_drive_path, key,
                            status_callback=lambda d, m, p: update_status_callback(norm_drive, m, p)
                        )
                    except Exception as e:
                        update_status_callback(norm_drive, f"❌ {original_drive_path}：加密失败: {e}", -1)

        thread_app_context = current_app.app_context()
        thread = threading.Thread(target=background_task, args=(thread_app_context, keys_for_encryption))
        thread.start()

        return jsonify({'success': True, 'message': '密码设置成功，后台加密任务已启动'})
    else:
        return jsonify({'success': True, 'message': '密码变更成功'})


@encryption_bp.route('/api/encryption/add-drive', methods=['POST'])
@permission_required('fullcontrol')
def add_encrypted_drive():
    """添加磁盘到加密列表"""
    data = request.get_json()
    drive_path = data.get('drive')

    if not drive_path:
        return jsonify({'error': '缺少磁盘路径'}), 400

    encryption_manager = _ctx['encryption_manager']
    load_json = _ctx['load_json']

    config = load_json(encryption_manager.config_path, {})
    encrypted_drives = config.get("encrypted_drives", [])
    normalized_drive = _norm_abs(drive_path)

    if normalized_drive not in encrypted_drives:
        encrypted_drives.append(normalized_drive)
        config["encrypted_drives"] = encrypted_drives

        with open(encryption_manager.config_path, "w") as f:
            json.dump(config, f, indent=2)

        encryption_manager.load_config()
        return jsonify({'success': True, 'message': f'磁盘 {drive_path} 已添加到加密列表'})
    else:
        return jsonify({'error': '该磁盘已在加密列表中'}), 409


# ========== 管理端内部调用接口 ==========

@encryption_bp.route('/api/internal/encryption/encrypt-disk', methods=['POST'])
def internal_encrypt_disk():
    """供管理端调用：启用磁盘加密"""
    secret = request.headers.get('X-NAS-Secret')
    if secret != _ctx['NAS_SHARED_SECRET']:
        return jsonify({"error": "权限不足"}), 403

    data = request.get_json()
    drive = data.get('drive')
    password = data.get('password')

    if not drive or not password:
        return jsonify({"error": "缺少参数"}), 400

    try:
        encryption_manager = _ctx['encryption_manager']
        result = encryption_manager.encrypt_drive(drive, password)
        if result.get("success"):
            return jsonify({"success": True, "message": f"磁盘 {drive} 已启用加密"})
        else:
            return jsonify({"error": result.get("error", "加密失败")}), 500
    except Exception as e:
        return jsonify({"error": f"执行加密失败: {str(e)}"}), 500


@encryption_bp.route('/api/internal/encryption/unlock-disk', methods=['POST'])
def internal_unlock_disk():
    """供管理端调用：远程解锁磁盘"""
    secret = request.headers.get('X-NAS-Secret')
    if secret != _ctx['NAS_SHARED_SECRET']:
        return jsonify({"error": "权限不足"}), 403

    data = request.get_json()
    drive = data.get('drive')
    password = data.get('password')

    if not drive or not password:
        return jsonify({"error": "缺少参数"}), 400

    encryption_manager = _ctx['encryption_manager']
    success = encryption_manager.unlock(drive, password)

    if success:
        return jsonify({"success": True, "message": f"磁盘 {drive} 已解锁"})
    else:
        return jsonify({"error": f"磁盘 {drive} 解锁失败"}), 403


@encryption_bp.route('/api/internal/encryption/decrypt-disk', methods=['POST'])
def internal_decrypt_disk():
    """供管理端调用：永久解密磁盘"""
    secret = request.headers.get('X-NAS-Secret')
    if secret != _ctx['NAS_SHARED_SECRET']:
        return jsonify({"error": "权限不足"}), 403

    data = request.get_json()
    drive = data.get('drive')
    password = data.get('password')

    if not drive or not password:
        return jsonify({"error": "缺少参数 drive 或 password"}), 400

    try:
        encryption_manager = _ctx['encryption_manager']
        result = encryption_manager.decrypt_disk_permanently(drive, password)

        processed = result.get('processed_files', 0)
        failed = len(result.get('failed_files', []))

        return jsonify({
            "success": True,
            "message": f"磁盘 {drive} 已永久解密",
            "details": {"processed": processed, "failed": failed}
        })

    except ValueError:
        return jsonify({"success": False, "error": "密码错误"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@encryption_bp.route('/api/internal/encryption/lock-disk', methods=['POST'])
def internal_lock_disk():
    """供管理端调用：锁定磁盘"""
    secret = request.headers.get('X-NAS-Secret')
    if secret != _ctx['NAS_SHARED_SECRET']:
        return jsonify({"error": "权限不足"}), 403

    data = request.get_json()
    drive = data.get('drive')

    if not drive:
        return jsonify({"error": "缺少参数 drive"}), 400

    try:
        encryption_manager = _ctx['encryption_manager']
        success = encryption_manager.lock(drive)
        if success:
            return jsonify({"success": True, "message": f"磁盘 {drive} 已锁定"})
        else:
            return jsonify({"error": f"磁盘 {drive} 锁定失败"}), 500
    except Exception as e:
        return jsonify({"error": f"执行锁定失败: {e}"}), 500


@encryption_bp.route('/api/internal/encryption/change-password', methods=['POST'])
def internal_change_password():
    """供管理端调用：修改磁盘加密密码"""
    secret = request.headers.get('X-NAS-Secret')
    if secret != _ctx['NAS_SHARED_SECRET']:
        return jsonify({"error": "权限不足"}), 403

    data = request.get_json()
    drive = data.get('drive')
    new_password = data.get('new_password')

    if not (drive and new_password):
        return jsonify({"error": "缺少参数 drive 或 new_password"}), 400

    try:
        encryption_manager = _ctx['encryption_manager']
        result = encryption_manager.set_password(drive, new_password)
        if result.get("success"):
            return jsonify({"success": True, "message": f"磁盘 {drive} 密码已更新"})
        else:
            return jsonify({"error": result.get("error", "修改密码失败")}), 500
    except Exception as e:
        return jsonify({"error": f"修改密码异常: {e}"}), 500