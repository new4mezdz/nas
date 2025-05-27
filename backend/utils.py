import platform, psutil, os
import shutil
import time
import json
from common import BASE_DIR  # 确保你有这个

def get_sys_info():
    boot_time = psutil.boot_time()
    now = time.time()
    uptime_seconds = int(now - boot_time)
    return {
        "hostname": platform.node(),
        "os": platform.platform(),
        "cpu_percent": psutil.cpu_percent(),
        "memory_total": psutil.virtual_memory().total,
        "memory_used": psutil.virtual_memory().used,
        "uptime": uptime_seconds
    }




def get_disk_info():
    disks = []
    ec_disks = set()
    ec_scheme = ''

    # 加载纠删码配置
    config_path = os.path.join(BASE_DIR, 'ec_config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                ec_disks = set(config.get('disks', []))
                ec_scheme = config.get('scheme', '')
        except Exception as e:
            print(f"加载纠删码配置失败: {e}")

    # 获取真实磁盘信息
    for part in psutil.disk_partitions():
        try:
            usage = shutil.disk_usage(part.mountpoint)
            disks.append({
                'mount': part.mountpoint,
                'fstype': part.fstype,
                'total': usage.total,
                'used': usage.used,
                'free': usage.free,
                'percent': round(usage.used / usage.total * 100, 1),
                'ec_scheme': ec_scheme if part.mountpoint in ec_disks else ''
            })
        except Exception as e:
            print(f"无法读取磁盘 {part.mountpoint}: {e}")
            continue

    # 添加模拟磁盘（如 sim_disk1 ~ sim_disk6）
    for i in range(1, 7):
        sim_path = os.path.join(BASE_DIR, f'sim_disk{i}')
        os.makedirs(sim_path, exist_ok=True)
        usage = shutil.disk_usage(BASE_DIR)  # 模拟盘共享同一物理盘
        disks.append({
            'mount': sim_path,
            'fstype': '-',
            'total': usage.total,
            'used': usage.used,
            'free': usage.free,
            'percent': round(usage.used / usage.total * 100, 1),
            'ec_scheme': ec_scheme if sim_path in ec_disks else ''
        })

    return disks



def restart_samba():
    # 模拟函数，真实情况下可执行系统命令
    return True
