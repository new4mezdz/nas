# routes/pool_routes.py
import os
from flask import Blueprint, request, jsonify, send_file

from permission_decorator import permission_required

pool_bp = Blueprint('pool', __name__, url_prefix='/api/pool')

# 外部依赖
_ctx = {
    'Storage_pool': None,
    'encryption_manager': None,
}


def init_pool_routes(storage_pool, encryption_manager):
    _ctx['Storage_pool'] = storage_pool
    _ctx['encryption_manager'] = encryption_manager


# ========== 存储池管理 ==========

@pool_bp.route('/status', methods=['GET'])
@permission_required('readonly')
def api_pool_status():
    """获取存储池状态"""
    try:
        Storage_pool = _ctx['Storage_pool']
        status = Storage_pool.get_pool_status()
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@pool_bp.route('/create', methods=['POST'])
@permission_required('fullcontrol')
def api_pool_create():
    """创建存储池"""
    try:
        Storage_pool = _ctx['Storage_pool']
        data = request.json
        name = data.get('name', '主存储池')
        disks = data.get('disks', [])

        if not disks:
            return jsonify({"error": "请选择至少一个磁盘"}), 400

        result = Storage_pool.create_pool(name, disks)
        return jsonify({"message": "存储池创建成功", "pool": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@pool_bp.route('/remove', methods=['POST'])
@permission_required('fullcontrol')
def api_pool_remove():
    """删除存储池"""
    try:
        Storage_pool = _ctx['Storage_pool']
        data = request.json
        confirm_text = data.get('confirm_text', '')
        result = Storage_pool.remove_pool(confirm_text)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@pool_bp.route('/health', methods=['GET'])
@permission_required('readonly')
def api_pool_health():
    """检查池磁盘健康状态"""
    try:
        Storage_pool = _ctx['Storage_pool']
        result = Storage_pool.check_disk_health()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@pool_bp.route('/available-disks', methods=['GET'])
@permission_required('fullcontrol')
def api_pool_available_disks():
    """获取可添加到池的磁盘列表"""
    try:
        Storage_pool = _ctx['Storage_pool']
        result = Storage_pool.get_available_disks()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@pool_bp.route('/rebalance', methods=['POST'])
@permission_required('fullcontrol')
def api_pool_rebalance():
    """重新平衡池数据分布"""
    try:
        Storage_pool = _ctx['Storage_pool']
        data = request.get_json() or {}
        dry_run = data.get('dry_run', True)
        result = Storage_pool.rebalance_pool(dry_run)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@pool_bp.route('/rebuild', methods=['POST'])
@permission_required('fullcontrol')
def api_pool_rebuild():
    """重建索引"""
    try:
        Storage_pool = _ctx['Storage_pool']
        result = Storage_pool.rebuild_index()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ========== 磁盘管理 ==========

@pool_bp.route('/disk/add', methods=['POST'])
@permission_required('fullcontrol')
def api_pool_add_disk():
    """向池添加新磁盘"""
    try:
        Storage_pool = _ctx['Storage_pool']
        data = request.get_json()
        disk = data.get('disk')

        if not disk:
            return jsonify({"error": "请指定磁盘路径"}), 400

        result = Storage_pool.add_disk_to_pool(disk)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@pool_bp.route('/disk/remove-check', methods=['POST'])
@permission_required('fullcontrol')
def api_pool_remove_disk_check():
    """移除磁盘前的预检查"""
    try:
        Storage_pool = _ctx['Storage_pool']
        data = request.get_json() or {}
        disk = data.get('disk')

        if not disk:
            return jsonify({"error": "请指定磁盘路径"}), 400

        force = data.get('force', False)
        result = Storage_pool.check_remove_disk(disk, force)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
@pool_bp.route('/disk/remove', methods=['POST'])
@permission_required('fullcontrol')
def api_pool_remove_disk():
    """从池移除磁盘"""
    try:
        Storage_pool = _ctx['Storage_pool']
        data = request.get_json()
        disk = data.get('disk')
        migrate = data.get('migrate', True)

        if not disk:
            return jsonify({"error": "请指定磁盘路径"}), 400

        result = Storage_pool.remove_disk_from_pool(disk, migrate)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ========== 逻辑卷管理 ==========

@pool_bp.route('/volumes', methods=['GET'])
@permission_required('readonly')
def api_pool_volumes():
    """列出所有逻辑卷"""
    try:
        Storage_pool = _ctx['Storage_pool']
        volumes_dict = Storage_pool.list_volumes()
        volumes_list = [
            {"name": name, **vol_data}
            for name, vol_data in volumes_dict.items()
        ]
        return jsonify(volumes_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@pool_bp.route('/volume/create', methods=['POST'])
@permission_required('fullcontrol')
def api_pool_volume_create():
    """创建逻辑卷"""
    try:
        Storage_pool = _ctx['Storage_pool']
        data = request.json
        name = data.get('name')
        display_name = data.get('display_name')
        icon = data.get('icon', '📁')
        strategy = data.get('strategy', 'largest_free')

        if not name or not display_name:
            return jsonify({"error": "请填写卷名和显示名称"}), 400

        result = Storage_pool.create_volume(name, display_name, icon, strategy)
        return jsonify({"message": "逻辑卷创建成功", "volume": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@pool_bp.route('/volume/<name>', methods=['PATCH'])
@permission_required('fullcontrol')
def api_pool_volume_update(name):
    """更新逻辑卷配置"""
    try:
        Storage_pool = _ctx['Storage_pool']
        data = request.json
        result = Storage_pool.update_volume(
            name,
            display_name=data.get('display_name'),
            icon=data.get('icon'),
            strategy=data.get('strategy')
        )
        return jsonify({"message": "更新成功", "volume": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@pool_bp.route('/volume/<name>', methods=['DELETE'])
@permission_required('fullcontrol')
def api_pool_volume_delete(name):
    """删除逻辑卷"""
    try:
        Storage_pool = _ctx['Storage_pool']
        confirm = request.args.get('confirm', 'false').lower() == 'true'
        result = Storage_pool.delete_volume(name, confirm)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ========== 文件操作 ==========

@pool_bp.route('/list', methods=['GET'])
@permission_required('readonly')
def api_pool_list():
    """列出逻辑卷中的文件"""
    try:
        Storage_pool = _ctx['Storage_pool']
        volume = request.args.get('volume')
        subpath = request.args.get('subpath', '')

        if not volume:
            return jsonify({"error": "请指定逻辑卷"}), 400

        items = Storage_pool.list_files(volume, subpath)
        return jsonify({"items": items, "volume": volume, "subpath": subpath})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@pool_bp.route('/upload', methods=['POST'])
@permission_required('readwrite')
def api_pool_upload():
    """上传文件到逻辑卷"""
    try:
        Storage_pool = _ctx['Storage_pool']
        volume = request.form.get('volume')
        subpath = request.form.get('subpath', '')

        if not volume:
            return jsonify({"error": "请指定逻辑卷"}), 400

        if 'file' not in request.files:
            return jsonify({"error": "没有文件"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "未选择文件"}), 400

        file_data = file.read()
        result = Storage_pool.add_file(volume, subpath, file.filename, file_data)

        return jsonify({"message": "上传成功", "file": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@pool_bp.route('/download', methods=['GET'])
@permission_required('readonly')
def api_pool_download():
    """下载文件"""
    try:
        Storage_pool = _ctx['Storage_pool']
        virtual_path = request.args.get('path')

        if not virtual_path:
            return jsonify({"error": "请指定文件路径"}), 400

        full_path = Storage_pool.get_file_path(virtual_path)

        if not os.path.exists(full_path):
            return jsonify({"error": "文件不存在"}), 404

        return send_file(full_path, as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@pool_bp.route('/delete', methods=['POST'])
@permission_required('readwrite')
def api_pool_delete_file():
    """删除文件"""
    try:
        Storage_pool = _ctx['Storage_pool']
        data = request.json
        virtual_path = data.get('path')

        if not virtual_path:
            return jsonify({"error": "请指定文件路径"}), 400

        result = Storage_pool.delete_file(virtual_path)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@pool_bp.route('/mkdir', methods=['POST'])
@permission_required('readwrite')
def api_pool_mkdir():
    """创建文件夹"""
    try:
        Storage_pool = _ctx['Storage_pool']
        data = request.json
        volume = data.get('volume')
        subpath = data.get('subpath', '')
        folder_name = data.get('folder_name')

        if not volume or not folder_name:
            return jsonify({"error": "请指定逻辑卷和文件夹名"}), 400

        result = Storage_pool.create_folder(volume, subpath, folder_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ========== 加密相关 ==========

@pool_bp.route('/encryption/status', methods=['GET'])
@permission_required('readonly')
def get_pool_encryption_status():
    """获取空间池加密状态"""
    try:
        encryption_manager = _ctx['encryption_manager']

        pool_status = {}
        for key, config in encryption_manager.disk_configs.items():
            if key.startswith('pool:'):
                pool_name = key.replace('pool:', '')
                pool_status[pool_name] = {
                    'is_encrypted': True,
                    'is_unlocked': key in encryption_manager.unlocked_keys,
                    'type': config.get('type', 'pool')
                }

        if not pool_status:
            return jsonify({'is_configured': False, 'pools': {}})

        return jsonify({'is_configured': True, 'pools': pool_status})
    except Exception as e:
        return jsonify({'is_configured': False, 'pools': {}, 'error': str(e)})


@pool_bp.route('/encrypt', methods=['POST'])
def api_pool_encrypt():
    """加密整个容量池"""
    Storage_pool = _ctx['Storage_pool']
    encryption_manager = _ctx['encryption_manager']

    data = request.get_json()
    pool_name = data.get('pool_name')
    password = data.get('password')

    config = Storage_pool.load_config()
    pool_config = config.get('volumes', {}).get(pool_name)

    if not pool_config:
        return jsonify({"success": False, "error": "池不存在"}), 404

    result = encryption_manager.encrypt_pool(pool_name, password, pool_config)
    return jsonify(result)


@pool_bp.route('/unlock', methods=['POST'])
def api_pool_unlock():
    """解锁容量池"""
    encryption_manager = _ctx['encryption_manager']

    data = request.get_json()
    pool_name = data.get('pool_name')
    password = data.get('password')

    pool_key = f"pool:{pool_name}"
    success = encryption_manager.unlock(pool_key, password)
    return jsonify({"success": success})