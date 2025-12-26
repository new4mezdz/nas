# routes/system_routes.py
import time
import shutil
from datetime import datetime
from flask import Blueprint, jsonify

from common import get_available_drives
from utils import get_sys_info, get_disk_info, _norm_abs
from hardware_monitor import hardware_monitor
from permission_decorator import permission_required

system_bp = Blueprint('system', __name__, url_prefix='/api')

# 这些变量需要从 app.py 传入，在 init 时设置
_app_context = {
    'load_json': None,
    'EC_CFG_PATH': None,
    'load_node_config': None,
    'THIS_NODE_ID': None,
    'NAS_CENTER_PUBLIC_URL': None,
    'NAS_CENTER_API_URL': None,
}


def init_system_routes(load_json, ec_cfg_path, load_node_config, this_node_id, center_public_url, center_api_url):
    """初始化系统路由所需的外部依赖"""
    _app_context['load_json'] = load_json
    _app_context['EC_CFG_PATH'] = ec_cfg_path
    _app_context['load_node_config'] = load_node_config
    _app_context['THIS_NODE_ID'] = this_node_id
    _app_context['NAS_CENTER_PUBLIC_URL'] = center_public_url
    _app_context['NAS_CENTER_API_URL'] = center_api_url


@system_bp.route('/system-stats', methods=['GET'])
def get_system_stats():
    """返回系统统计信息 - 供 NAS Center 调用"""
    try:
        import psutil

        sys_info = get_sys_info()
        disk_info = get_disk_info()

        # 计算磁盘总量和使用量
        total_gb = 0
        used_gb = 0
        for disk in disk_info:
            if disk.get('mount', '').upper() not in ['C:/', 'D:/', '/']:
                total = disk.get('bytes_total', 0) or disk.get('total', 0)
                used = disk.get('bytes_used', 0) or disk.get('used', 0)
                total_gb += total / (1024 ** 3)
                used_gb += used / (1024 ** 3)
        disk_percent = round((used_gb / total_gb * 100) if total_gb > 0 else 0, 2)

        # 获取硬件数据
        cpu_temp = 0
        cpu_freq = 0
        cpu_power = 0
        network_download = 0
        network_upload = 0

        try:
            hw_data = hardware_monitor.get_hardware_data() or {}

            if hw_data and 'temperatures' in hw_data:
                for temp_sensor in hw_data['temperatures']:
                    if temp_sensor.get('name') == 'CPU Package':
                        cpu_temp = temp_sensor.get('value', 0)
                        break

            if hw_data and 'powers' in hw_data:
                for power in hw_data['powers']:
                    if power.get('name') == 'CPU Package':
                        cpu_power = round(power.get('value', 0), 1)
                        break

            if hw_data and 'clocks' in hw_data:
                for clock in hw_data['clocks']:
                    if 'CPU Core #1' in clock.get('name', ''):
                        cpu_freq = round(clock['value'] / 1000, 2)
                        break

            net_io_start = psutil.net_io_counters()
            time.sleep(0.5)
            net_io_end = psutil.net_io_counters()
            network_download = round((net_io_end.bytes_recv - net_io_start.bytes_recv) / 1024 / 1024 / 0.5, 2)
            network_upload = round((net_io_end.bytes_sent - net_io_start.bytes_sent) / 1024 / 1024 / 0.5, 2)

        except Exception as hw_error:
            print(f"[WARNING] 获取硬件信息失败: {hw_error}")

        return jsonify({
            'cpu_percent': sys_info.get('cpu_percent', 0),
            'memory_percent': sys_info.get('mem_percent', 0),
            'disk_percent': disk_percent,
            'disk_total_gb': round(total_gb, 2),
            'disk_used_gb': round(used_gb, 2),
            'disk_free_gb': round(total_gb - used_gb, 2),
            'cpu_temp_celsius': cpu_temp,
            'cpu_freq': cpu_freq,
            'cpu_power': cpu_power,
            'network_download': network_download,
            'network_upload': network_upload,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        print(f"[ERROR] 获取系统统计失败: {e}")
        return jsonify({'error': str(e)}), 500


@system_bp.route('/hardware-data', methods=['GET'])
def get_hardware_data():
    """返回硬件监控详细数据"""
    try:
        hw_data = hardware_monitor.get_hardware_data() or {}
        return jsonify(hw_data)
    except Exception as e:
        print(f"[ERROR] 获取硬件数据失败: {e}")
        return jsonify({'error': str(e)}), 500


@system_bp.route('/disks', methods=['GET'])
def get_disks_info():
    """返回详细磁盘信息 - 供 NAS Center 调用"""
    try:
        all_disks = get_disk_info()

        formatted_disks = []
        for disk in all_disks:
            mount = disk.get('mount', '').upper().replace('\\', '/')
            if mount in ['C:/', 'D:/', '/']:
                continue

            total = disk.get('bytes_total', 0) or disk.get('total', 0)
            used = disk.get('bytes_used', 0) or disk.get('used', 0)
            free = disk.get('bytes_free', 0) or disk.get('free', 0)

            formatted_disks.append({
                'mount': disk.get('mount', ''),
                'total_gb': round(total / (1024 ** 3), 2),
                'used_gb': round(used / (1024 ** 3), 2),
                'free_gb': round(free / (1024 ** 3), 2),
                'usage_percent': round((used / total * 100) if total > 0 else 0, 2),
                'filesystem': disk.get('fstype', 'unknown'),
                'device': disk.get('device', 'unknown')
            })

        return jsonify(formatted_disks)

    except Exception as e:
        print(f"[ERROR] 获取磁盘信息失败: {e}")
        return jsonify({'error': str(e)}), 500


@system_bp.route('/system', methods=['GET'])
@permission_required('readonly')
def get_system():
    """返回系统信息 (供前端调用)"""
    try:
        import psutil

        sys_info = get_sys_info()
        hw_data = hardware_monitor.get_hardware_data()

        cpu_power = 0
        for power in hw_data.get('powers', []):
            if 'package' in power['name'].lower() or 'cpu' in power['name'].lower():
                cpu_power = round(power['value'], 1)
                break

        cpu_freq_ghz = 0
        for clock in hw_data.get('clocks', []):
            if 'core' in clock['name'].lower() and '#1' in clock['name']:
                cpu_freq_ghz = round(clock['value'] / 1000, 2)
                break
        if cpu_freq_ghz == 0:
            cpu_freq = psutil.cpu_freq()
            cpu_freq_ghz = round(cpu_freq.current / 1000, 2) if cpu_freq else 0

        net_io_start = psutil.net_io_counters()
        time.sleep(0.5)
        net_io_end = psutil.net_io_counters()
        download_speed = round((net_io_end.bytes_recv - net_io_start.bytes_recv) / 1024 / 1024 / 0.5, 2)
        upload_speed = round((net_io_end.bytes_sent - net_io_start.bytes_sent) / 1024 / 1024 / 0.5, 2)

        for power in hw_data.get('powers', []):
            if power['name'] == 'CPU Package':
                cpu_power = round(power['value'], 1)
                break

        combined = {**sys_info, **hw_data}
        combined['cpu_freq'] = cpu_freq_ghz
        combined['cpu_power'] = cpu_power
        combined['network_download'] = download_speed
        combined['network_upload'] = upload_speed

        return jsonify(combined)
    except Exception as e:
        print(f"[ERROR] 获取系统信息失败: {e}")
        return jsonify({"error": str(e)}), 500


@system_bp.route('/disk', methods=['GET'])
@permission_required('readonly')
def api_disk():
    """获取磁盘信息，并排除系统盘"""
    disk_info = get_disk_info()

    filtered_disk_info = []
    for disk in disk_info:
        mount_point = disk.get("mount", "").upper().replace("\\", "/")
        if mount_point in ["C:/", "D:/", "/"]:
            continue
        filtered_disk_info.append(disk)

    # 读取纠删码配置
    load_json = _app_context['load_json']
    ec_cfg_path = _app_context['EC_CFG_PATH']

    ec_cfg = load_json(ec_cfg_path, {}) if load_json else {}
    ec_disks = set()
    ec_scheme_name = None

    if ec_cfg and ec_cfg.get("disks"):
        ec_disks = set(_norm_abs(d) for d in ec_cfg.get("disks", []))
        ec_scheme_name = ec_cfg.get("scheme", "rs").upper()

    for disk in filtered_disk_info:
        normalized_mount = _norm_abs(disk.get("mount", ""))
        if normalized_mount in ec_disks:
            disk['ec_scheme'] = ec_scheme_name
        else:
            disk['ec_scheme'] = None

    return jsonify(filtered_disk_info)


@system_bp.route('/drives', methods=['GET'])
@permission_required('readonly')
def get_drives():
    """获取系统中可用的盘符"""
    available_drives = get_available_drives()
    drives_info = []

    for drive in available_drives:
        try:
            total, used, free = shutil.disk_usage(drive)
            drives_info.append({
                'drive': drive,
                'total': total,
                'used': used,
                'free': free,
                'percent': round((used / total) * 100, 1) if total > 0 else 0
            })
        except Exception:
            drives_info.append({
                'drive': drive,
                'total': 0,
                'used': 0,
                'free': 0,
                'percent': 0
            })

    return jsonify(drives_info)


@system_bp.route('/node-info', methods=['GET'])
def get_node_info():
    """返回当前节点的信息"""
    load_node_config = _app_context['load_node_config']
    node_config = load_node_config() if load_node_config else None

    return jsonify({
        'node_id': node_config.get('node_id') if node_config else _app_context['THIS_NODE_ID'],
        'center_url': _app_context['NAS_CENTER_PUBLIC_URL'] or _app_context['NAS_CENTER_API_URL']
    })


@system_bp.route('/initialize', methods=['POST'])  # 注意：去掉 /api 前缀，因为 blueprint 已有 url_prefix='/api'
def initialize():
    """客户端接收主控发来的身份信息"""
    import threading
    from flask import request

    data = request.json
    node_id = data.get("node_id")
    master_ip = data.get("master_ip")
    master_port = data.get("master_port")

    # 更新上下文
    _app_context['THIS_NODE_ID'] = node_id
    master_url = f"http://{master_ip}:{master_port}"
    _app_context['NAS_CENTER_API_URL'] = master_url

    print(f"[节点] 已初始化身份: {node_id}")
    print(f"[节点] 主控中心: {master_url}")

    return jsonify({"success": True, "node_id": node_id})