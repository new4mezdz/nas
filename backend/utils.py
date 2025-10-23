# utils.py
# -*- coding: utf-8 -*-

import os
import platform
import psutil
import shutil
import time
import json
import glob
import string
from typing import List, Dict

from common import BASE_DIRS  # 你的项目已有


# 可按需调整：最多自动发现多少个 sim_disk 目录
SIM_DISK_COUNT = 0


def _norm_abs(path: str) -> str:
    """绝对化 + 规范化 + （Windows）大小写无关比较"""
    return os.path.normcase(os.path.abspath(os.path.normpath(path or "")))


def _discover_sim_disks() -> List[str]:
    """
    发现“目录式模拟盘”，优先级：
      1) 环境变量 EC_SIM_DISKS（; 或 , 分隔，显式目录列表）
      2) 环境变量 EC_SIM_PATTERN（glob，如 D:\\sim_disk* 或 /mnt/sim_disk*）
      3) BASE_DIRS[0]/sim_disk1..N
      4) Windows 各盘根：X:\\sim_disk1..N
      5) Linux 常见挂载点：/mnt|/media|/data/sim_disk1..N
    返回绝对路径的有序列表。
    """
    sim: set[str] = set()

    # 1) 显式列表
    env_list = os.environ.get("EC_SIM_DISKS", "")
    if env_list:
        for token in env_list.replace(";", ",").split(","):
            p = token.strip()
            if not p:
                continue
            p_abs = _norm_abs(p)
            if os.path.isdir(p_abs):
                sim.add(p_abs)

    # 2) glob 模式
    env_pat = os.environ.get("EC_SIM_PATTERN", "").strip()
    if env_pat:
        for p in glob.glob(env_pat):
            p_abs = _norm_abs(p)
            if os.path.isdir(p_abs):
                sim.add(p_abs)

    # 3) BASE_DIRS[0]/sim_disk{i}
    base0 = BASE_DIRS[0] if BASE_DIRS else os.getcwd()
    for i in range(1, SIM_DISK_COUNT + 1):
        p_abs = _norm_abs(os.path.join(base0, f"sim_disk{i}"))
        if os.path.isdir(p_abs):
            sim.add(p_abs)

    # 4) Windows：扫描各盘根
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            if os.path.exists(root):
                for i in range(1, SIM_DISK_COUNT + 1):
                    p_abs = _norm_abs(os.path.join(root, f"sim_disk{i}"))
                    if os.path.isdir(p_abs):
                        sim.add(p_abs)
    else:
        # 5) Linux 常见挂载点
        for prefix in ("/mnt", "/media", "/data"):
            for i in range(1, SIM_DISK_COUNT + 1):
                p_abs = _norm_abs(os.path.join(prefix, f"sim_disk{i}"))
                if os.path.isdir(p_abs):
                    sim.add(p_abs)

    return sorted(sim)


def get_sys_info() -> Dict:
    """基础系统信息"""
    try:
        boot_time = psutil.boot_time()
    except Exception:
        boot_time = time.time()
    now = time.time()
    uptime_seconds = int(max(0, now - boot_time))
    vm = psutil.virtual_memory()
    return {
        "hostname": platform.node(),
        "os": platform.platform(),
        "cpu_percent": psutil.cpu_percent(interval=None),
        "memory_total": int(vm.total),
        "memory_used": int(vm.used),
        "memory_free": int(vm.available),
        "mem_percent": round(vm.percent, 1),
        "uptime_seconds": uptime_seconds,
    }


def get_disk_info() -> List[Dict]:
    """
    汇总可用磁盘/目录（真实盘 + 模拟盘目录），并对在 ec_config.json 中的盘
    正确标注 ec_scheme（如 'rs'），供前端聚合显示“纠删码卷”。

    返回的每个条目包含兼容字段：
      - mount, fstype
      - total/free/used/percent
      - bytes_total/bytes_free/bytes_used（与部分接口兼容）
      - ec_scheme: 'rs' 或 ''
    """
    disks: List[Dict] = []

    # 读取纠删码配置并做路径归一化（保证匹配稳定）
    ec_disks: set[str] = set()
    ec_scheme = ""
    try:
        cfg_path = os.path.join(BASE_DIRS[0], "ec_config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            ec_scheme = (cfg.get("scheme") or "").lower()
            for d in (cfg.get("disks") or []):
                ec_disks.add(_norm_abs(d))
    except Exception as e:
        print(f"[EC配置] 读取失败: {e}")

    # (A) 模拟盘目录
    for p_abs in _discover_sim_disks():
        try:
            usage = shutil.disk_usage(p_abs)  # 用底层卷的容量
            # mount 给原始样式；比较用 _norm_abs
            mount_display = p_abs
            total = int(usage.total)
            used = int(usage.used)
            free = int(usage.free)
            percent = round(used / total * 100, 1) if total else 0.0
            disks.append({
                "mount": mount_display,
                "fstype": "sim",
                "total": total, "free": free, "used": used, "percent": percent,
                "bytes_total": total, "bytes_free": free, "bytes_used": used,
                "ec_scheme": ec_scheme if _norm_abs(p_abs) in ec_disks else ""
            })
        except Exception as e:
            print(f"[模拟盘] 读取失败 {p_abs}: {e}")

    # (B) 真实磁盘分区
    try:
        parts = psutil.disk_partitions(all=False)
    except Exception as e:
        print(f"[分区] 获取失败: {e}")
        parts = []

    for part in parts:
        mount = part.mountpoint
        mount_norm = _norm_abs(mount)
        try:
            usage = shutil.disk_usage(mount)
            total = int(usage.total)
            used = int(usage.used)
            free = int(usage.free)
            percent = round(used / total * 100, 1) if total else 0.0
            disks.append({
                "mount": mount,
                "fstype": part.fstype or "-",
                "total": total, "free": free, "used": used, "percent": percent,
                "bytes_total": total, "bytes_free": free, "bytes_used": used,
                "ec_scheme": ec_scheme if mount_norm in ec_disks else ""
            })
        except Exception as e:
            print(f"[磁盘] 读取失败 {mount}: {e}")

    return disks
