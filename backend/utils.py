import platform, psutil, os
import shutil
import time
import json
from common import BASE_DIRS  # 确保你有这个
SIM_DISK_COUNT = 6

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
    config_path = os.path.join(BASE_DIRS[0], 'ec_config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                ec_disks = set(config.get('disks', []))
                ec_scheme = config.get('scheme', '')
        except Exception as e:
            print(f"[EC配置] 加载失败: {e}")

    # ========== 添加模拟盘（推荐） ==========
    for i in range(1, SIM_DISK_COUNT + 1):
        sim_path = os.path.join(BASE_DIRS[0], f"sim_disk{i}")
        os.makedirs(sim_path, exist_ok=True)
        usage = shutil.disk_usage(BASE_DIRS[0])  # 使用主盘容量信息
        disks.append({
            'mount': sim_path,
            'fstype': '-',
            'total': usage.total,
            'used': usage.used,
            'free': usage.free,
            'percent': round(usage.used / usage.total * 100, 1),
            'ec_scheme': ec_scheme if sim_path in ec_disks else ''
        })

    # ========== 可选：添加真实磁盘（排除系统盘） ==========
    for part in psutil.disk_partitions():
        mount = part.mountpoint

        # Windows 下排除系统盘（通常是 C:\）
        if os.name == 'nt' and mount.lower().startswith("c:\\"):
            continue

        # Linux 下排除 /
        if os.name == 'posix' and mount in ('/', '/boot', '/home'):
            continue

        try:
            usage = shutil.disk_usage(mount)
            disks.append({
                'mount': mount,
                'fstype': part.fstype,
                'total': usage.total,
                'used': usage.used,
                'free': usage.free,
                'percent': round(usage.used / usage.total * 100, 1),
                'ec_scheme': ec_scheme if mount in ec_disks else ''
            })
        except Exception as e:
            print(f"[磁盘] 读取失败 {mount}: {e}")
            continue

    return disks

def restart_samba():
    # 模拟函数，真实情况下可执行系统命令
    return True
