import platform, psutil, os
import time

def get_sys_info():
    boot_time = psutil.boot_time()
    now = time.time()
    uptime_seconds = int(now - boot_time)   # 这才是“已运行的秒数”
    return {
        "hostname": platform.node(),
        "os": platform.platform(),
        "cpu_percent": psutil.cpu_percent(),
        "memory_total": psutil.virtual_memory().total,
        "memory_used": psutil.virtual_memory().used,
        "uptime": uptime_seconds    # 这里返回“已运行秒数”！
    }


def get_disk_info():
    info = []
    for p in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(p.mountpoint)
            info.append({
                "mountpoint": p.mountpoint,
                "fstype": p.fstype,
                "total": usage.total,
                "used": usage.used,
                "percent": usage.percent
            })
        except:
            continue
    return info

def restart_samba():
    # 这里只做模拟
    return True
