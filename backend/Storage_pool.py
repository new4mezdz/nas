"""
空间池管理模块 - Storage Pool Manager
"""
import os
import json
import shutil
import time
from typing import Optional, Dict, List, Any

POOL_CONFIG_FILE = "storage_pool.json"
POOL_DIR_NAME = ".pool"  # 每个磁盘下的池目录


def get_config_path():
    """获取配置文件路径（和 ec_config.json 同级）"""
    # 根据你的项目调整这个路径
    return os.path.join(os.path.dirname(__file__), POOL_CONFIG_FILE)


def load_config() -> dict:
    """加载配置"""
    path = get_config_path()
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "pool": None,
        "volumes": {},
        "files": {},
        "round_robin_index": {}
    }


def save_config(config: dict):
    """保存配置"""
    path = get_config_path()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# ==================== 池管理 ====================

def create_pool(name: str, disks: List[str]) -> dict:
    """
    创建存储池
    :param name: 池名称
    :param disks: 磁盘列表 ["D:/", "E:/"]
    """
    config = load_config()

    if config.get("pool"):
        raise Exception("存储池已存在，请先删除现有池")

    # 验证磁盘
    valid_disks = []
    for disk in disks:
        disk = disk.upper().replace("\\", "/")
        if not disk.endswith("/"):
            disk += "/"
        if os.path.exists(disk):
            valid_disks.append(disk)
            # 创建 .pool 目录
            pool_dir = os.path.join(disk, POOL_DIR_NAME)
            os.makedirs(pool_dir, exist_ok=True)
        else:
            raise Exception(f"磁盘 {disk} 不存在")

    if len(valid_disks) < 1:
        raise Exception("至少需要选择1个磁盘")

    config["pool"] = {
        "name": name,
        "disks": valid_disks,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")
    }
    config["volumes"] = {}
    config["files"] = {}
    config["round_robin_index"] = {}

    save_config(config)
    return config["pool"]


def get_pool_status() -> dict:
    """获取池状态"""
    config = load_config()

    if not config.get("pool"):
        return {"is_configured": False}

    pool = config["pool"]
    volumes = config.get("volumes", {})
    files = config.get("files", {})

    # 计算各磁盘使用情况
    disk_stats = []
    total_size = 0
    total_free = 0

    for disk in pool["disks"]:
        try:
            usage = shutil.disk_usage(disk)
            disk_stats.append({
                "disk": disk,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "healthy": True
            })
            total_size += usage.total
            total_free += usage.free
        except:
            disk_stats.append({
                "disk": disk,
                "total": 0,
                "used": 0,
                "free": 0,
                "healthy": False,
                "error": "磁盘不可访问"
            })

    # 计算各卷使用情况
    volume_stats = {}
    for vol_name, vol_config in volumes.items():
        vol_size = sum(
            f.get("size", 0)
            for path, f in files.items()
            if path.startswith(vol_name + "/")
        )
        file_count = sum(
            1 for path in files.keys()
            if path.startswith(vol_name + "/")
        )
        volume_stats[vol_name] = {
            **vol_config,
            "used_bytes": vol_size,
            "file_count": file_count
        }

    return {
        "is_configured": True,
        "pool": pool,
        "disks": disk_stats,
        "volumes": volume_stats,
        "total_size": total_size,
        "total_free": total_free,
        "total_files": len(files)
    }


def remove_pool() -> dict:
    """删除存储池"""

    config = load_config()

    if not config.get("pool"):
        raise Exception("存储池不存在")

    # 删除各磁盘上的 .pool 目录
    for disk in config["pool"]["disks"]:
        pool_dir = os.path.join(disk, POOL_DIR_NAME)
        if os.path.exists(pool_dir):
            shutil.rmtree(pool_dir)

    # 清空配置
    config = {
        "pool": None,
        "volumes": {},
        "files": {},
        "round_robin_index": {}
    }
    save_config(config)

    return {"message": "存储池已删除"}


# ==================== 逻辑卷管理 ====================

def create_volume(name: str, display_name: str, icon: str = "📁",
                  strategy: str = "largest_free") -> dict:
    """
    创建逻辑卷
    :param name: 卷标识 (英文，如 movies)
    :param display_name: 显示名称 (如 "电影")
    :param icon: 图标
    :param strategy: 分配策略 largest_free/round_robin/balanced
    """
    config = load_config()

    if not config.get("pool"):
        raise Exception("请先创建存储池")

    if name in config["volumes"]:
        raise Exception(f"逻辑卷 {name} 已存在")

    # 验证名称（只允许英文、数字、下划线）
    if not name.replace("_", "").isalnum():
        raise Exception("卷名只能包含英文、数字和下划线")

    config["volumes"][name] = {
        "display_name": display_name,
        "icon": icon,
        "strategy": strategy,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")
    }

    # 在每个磁盘上创建对应目录
    for disk in config["pool"]["disks"]:
        vol_dir = os.path.join(disk, POOL_DIR_NAME, name)
        os.makedirs(vol_dir, exist_ok=True)

    # 初始化轮询索引
    config["round_robin_index"][name] = 0

    save_config(config)
    return config["volumes"][name]


def update_volume(name: str, display_name: str = None, icon: str = None,
                  strategy: str = None) -> dict:
    """更新逻辑卷配置"""
    config = load_config()

    if name not in config.get("volumes", {}):
        raise Exception(f"逻辑卷 {name} 不存在")

    vol = config["volumes"][name]
    if display_name:
        vol["display_name"] = display_name
    if icon:
        vol["icon"] = icon
    if strategy:
        vol["strategy"] = strategy

    save_config(config)
    return vol


def delete_volume(name: str, confirm: bool = False) -> dict:
    """删除逻辑卷"""
    config = load_config()

    if name not in config.get("volumes", {}):
        raise Exception(f"逻辑卷 {name} 不存在")

    # 检查是否有文件
    file_count = sum(1 for path in config["files"].keys() if path.startswith(name + "/"))
    if file_count > 0 and not confirm:
        raise Exception(f"逻辑卷 {name} 中有 {file_count} 个文件，请先确认删除")

    # 删除文件记录和物理文件
    files_to_delete = [path for path in config["files"].keys() if path.startswith(name + "/")]
    for vpath in files_to_delete:
        file_info = config["files"][vpath]
        real_full_path = os.path.join(file_info["disk"], file_info["real_path"])
        if os.path.exists(real_full_path):
            os.remove(real_full_path)
        del config["files"][vpath]

    # 删除目录
    for disk in config["pool"]["disks"]:
        vol_dir = os.path.join(disk, POOL_DIR_NAME, name)
        if os.path.exists(vol_dir):
            shutil.rmtree(vol_dir)

    del config["volumes"][name]
    if name in config["round_robin_index"]:
        del config["round_robin_index"][name]

    save_config(config)
    return {"message": f"逻辑卷 {name} 已删除，共删除 {len(files_to_delete)} 个文件"}


def list_volumes() -> dict:
    """列出所有逻辑卷"""
    config = load_config()
    return config.get("volumes", {})


# ==================== 磁盘选择策略 ====================
def select_disk(config: dict, volume_name: str, file_size: int = 0) -> str:
    """
    根据策略选择磁盘
    :param config: 配置字典 (传入引用，以便修改索引)
    :param volume_name: 逻辑卷名
    :param file_size: 文件大小（用于检查空间是否足够）
    :return: 磁盘路径
    """
    if not config.get("pool"):
        raise Exception("存储池未配置")

    if volume_name not in config.get("volumes", {}):
        raise Exception(f"逻辑卷 {volume_name} 不存在")

    vol = config["volumes"][volume_name]
    strategy = vol.get("strategy", "largest_free")
    disks = config["pool"]["disks"]

    # --- 1. 预处理：收集所有符合条件的磁盘信息 ---
    candidates = []
    reserved_space = 1073741824  # 保留 1GB 空间

    for disk in disks:
        try:
            usage = shutil.disk_usage(disk)
            # 只有当剩余空间 > 文件大小 + 保留空间时，才列入候选
            if usage.free > file_size + reserved_space:
                candidates.append({
                    "path": disk,
                    "free": usage.free,
                    "total": usage.total,
                    # 计算剩余率 (0.0 - 1.0)
                    "free_ratio": usage.free / usage.total if usage.total > 0 else 0
                })
        except Exception as e:
            # 忽略无法读取的磁盘
            print(f"警告: 无法读取磁盘 {disk}: {e}")
            continue

    if not candidates:
        raise Exception(f"没有足够空间的磁盘 (需要 {file_size} + 1GB)")

    # --- 2. 策略执行 ---

    if strategy == "largest_free":
        # 🟢 最大剩余空间优先
        # 按绝对剩余字节数 (free) 倒序排列
        candidates.sort(key=lambda x: x["free"], reverse=True)
        return candidates[0]["path"]

    elif strategy == "round_robin":
        # 🟢 轮询分配
        idx = config.get("round_robin_index", {}).get(volume_name, 0)

        # 既然 candidates 已经是经过空间筛选的，直接在这些可用盘里轮询
        selected = candidates[idx % len(candidates)]["path"]

        # 更新索引 (只修改内存，不保存)
        if "round_robin_index" not in config:
            config["round_robin_index"] = {}
        config["round_robin_index"][volume_name] = (idx + 1) % len(candidates)

        return selected

    elif strategy == "balanced":
        # 🟢 真正的平衡模式 (使用率均衡)
        # 按剩余百分比 (free_ratio) 倒序排列 -> 剩余率最高的排前面
        candidates.sort(key=lambda x: x["free_ratio"], reverse=True)

        # (可选) 打印调试信息，方便你在控制台看到它选了哪个
        best = candidates[0]
        # print(f"⚖️ 平衡模式: 选择 {best['path']} (剩余率: {best['free_ratio']*100:.1f}%)")

        return best["path"]

    else:
        # 默认回退到 largest_free
        candidates.sort(key=lambda x: x["free"], reverse=True)
        return candidates[0]["path"]


def list_files(volume_name: str, subpath: str = "") -> List[dict]:
    """
    列出逻辑卷中的文件
    :param volume_name: 逻辑卷名
    :param subpath: 子路径
    """
    config = load_config()

    if volume_name not in config.get("volumes", {}):
        raise Exception(f"逻辑卷 {volume_name} 不存在")

    prefix = volume_name + "/"
    if subpath:
        subpath = subpath.strip("/")
        prefix = f"{volume_name}/{subpath}/"

    items = []
    seen_dirs = set()
    seen_files = set()

    # 1. 从索引读取文件
    for vpath, file_info in config.get("files", {}).items():
        if not vpath.startswith(prefix):
            continue

        relative = vpath[len(prefix):]
        if "/" in relative:
            # 这是子目录中的文件，显示目录
            dir_name = relative.split("/")[0]
            if dir_name not in seen_dirs:
                seen_dirs.add(dir_name)
                items.append({
                    "name": dir_name,
                    "is_dir": True,
                    "size": 0,
                    "mtime": 0
                })
        else:
            # 直接文件
            seen_files.add(relative)
            items.append({
                "name": relative,
                "is_dir": False,
                "size": file_info.get("size", 0),
                "mtime": file_info.get("mtime", 0),
                "disk": file_info.get("disk", "")
            })

    # 2. 扫描物理目录，找出空文件夹（索引中没有的）
    for disk in config["pool"]["disks"]:
        if subpath:
            scan_dir = os.path.join(disk, POOL_DIR_NAME, volume_name, subpath)
        else:
            scan_dir = os.path.join(disk, POOL_DIR_NAME, volume_name)

        if not os.path.exists(scan_dir):
            continue

        try:
            for entry in os.scandir(scan_dir):
                if entry.is_dir() and entry.name not in seen_dirs:
                    seen_dirs.add(entry.name)
                    items.append({
                        "name": entry.name,
                        "is_dir": True,
                        "size": 0,
                        "mtime": int(entry.stat().st_mtime)
                    })
        except:
            pass

    # 排序：目录在前
    items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    return items


def add_file(volume_name: str, subpath: str, filename: str,
             file_data: bytes) -> dict:
    """
    添加文件到逻辑卷（上传用）
    """
    # 1. 在最开始加载一次配置
    config = load_config()

    if volume_name not in config.get("volumes", {}):
        raise Exception(f"逻辑卷 {volume_name} 不存在")

    # 构建虚拟路径
    if subpath:
        subpath = subpath.strip("/")
        virtual_path = f"{volume_name}/{subpath}/{filename}"
    else:
        virtual_path = f"{volume_name}/{filename}"

    # 检查是否已存在
    if virtual_path in config.get("files", {}):
        raise Exception(f"文件 {virtual_path} 已存在")

    # 2. 调用 select_disk 时传入 config 对象
    #    这样 select_disk 修改的轮询索引会直接作用于这个 config 对象
    disk = select_disk(config, volume_name, len(file_data))

    # 构建物理路径
    if subpath:
        real_path = f"{POOL_DIR_NAME}/{volume_name}/{subpath}/{filename}"
    else:
        real_path = f"{POOL_DIR_NAME}/{volume_name}/{filename}"

    full_path = os.path.join(disk, real_path)

    # 确保目录存在
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    # 写入文件
    with open(full_path, 'wb') as f:
        f.write(file_data)

    # 记录索引
    config["files"][virtual_path] = {
        "disk": disk,
        "real_path": real_path,
        "size": len(file_data),
        "mtime": int(time.time())
    }

    # 3. 最后统一保存 (包含新文件记录 + 更新后的轮询索引)
    save_config(config)

    return {
        "virtual_path": virtual_path,
        "disk": disk,
        "real_path": real_path,
        "size": len(file_data)
    }

def get_file_path(virtual_path: str) -> str:
    """
    获取文件的物理路径（下载用）
    :param virtual_path: 虚拟路径 "movies/阿凡达.mkv"
    :return: 物理完整路径
    """
    config = load_config()

    if virtual_path not in config.get("files", {}):
        raise Exception(f"文件 {virtual_path} 不存在")

    file_info = config["files"][virtual_path]
    return os.path.join(file_info["disk"], file_info["real_path"])


def delete_file(virtual_path: str) -> dict:
    """删除文件"""
    config = load_config()

    if virtual_path not in config.get("files", {}):
        raise Exception(f"文件 {virtual_path} 不存在")

    file_info = config["files"][virtual_path]
    full_path = os.path.join(file_info["disk"], file_info["real_path"])

    # 删除物理文件
    if os.path.exists(full_path):
        os.remove(full_path)

    # 删除记录
    del config["files"][virtual_path]
    save_config(config)

    return {"message": f"文件 {virtual_path} 已删除"}


def move_file(virtual_path: str, new_volume: str, new_subpath: str = "") -> dict:
    """移动文件到另一个逻辑卷"""
    config = load_config()

    if virtual_path not in config.get("files", {}):
        raise Exception(f"文件 {virtual_path} 不存在")

    if new_volume not in config.get("volumes", {}):
        raise Exception(f"逻辑卷 {new_volume} 不存在")

    file_info = config["files"][virtual_path]
    old_full_path = os.path.join(file_info["disk"], file_info["real_path"])

    # 读取文件
    with open(old_full_path, 'rb') as f:
        file_data = f.read()

    # 获取文件名
    filename = os.path.basename(virtual_path)

    # 添加到新位置
    result = add_file(new_volume, new_subpath, filename, file_data)

    # 删除旧文件
    os.remove(old_full_path)
    del config["files"][virtual_path]
    save_config(config)

    return result


def create_folder(volume_name: str, subpath: str, folder_name: str) -> dict:
    """在逻辑卷中创建文件夹"""
    config = load_config()

    if volume_name not in config.get("volumes", {}):
        raise Exception(f"逻辑卷 {volume_name} 不存在")

    # 在所有磁盘上创建文件夹
    for disk in config["pool"]["disks"]:
        if subpath:
            folder_path = os.path.join(disk, POOL_DIR_NAME, volume_name, subpath.strip("/"), folder_name)
        else:
            folder_path = os.path.join(disk, POOL_DIR_NAME, volume_name, folder_name)
        os.makedirs(folder_path, exist_ok=True)

    return {"message": f"文件夹 {folder_name} 创建成功"}


# ==================== 工具函数 ====================

def get_volume_path_info(path: str) -> tuple:
    """
    解析池路径
    :param path: "pool://movies/子目录/文件.mp4" 或 "movies/子目录"
    :return: (volume_name, subpath, filename)
    """
    path = path.replace("pool://", "").strip("/")
    parts = path.split("/")

    if len(parts) == 1:
        return parts[0], "", ""
    elif len(parts) == 2:
        return parts[0], "", parts[1]
    else:
        return parts[0], "/".join(parts[1:-1]), parts[-1]


def rebuild_index() -> dict:
    """重建文件索引（扫描物理文件）"""
    config = load_config()

    if not config.get("pool"):
        raise Exception("存储池未配置")

    new_files = {}
    volumes = config.get("volumes", {})

    for disk in config["pool"]["disks"]:
        pool_dir = os.path.join(disk, POOL_DIR_NAME)
        if not os.path.exists(pool_dir):
            continue

        for vol_name in volumes.keys():
            vol_dir = os.path.join(pool_dir, vol_name)
            if not os.path.exists(vol_dir):
                continue

            for root, dirs, files in os.walk(vol_dir):
                for filename in files:
                    full_path = os.path.join(root, filename)
                    relative = os.path.relpath(full_path, pool_dir)
                    virtual_path = relative.replace("\\", "/")

                    stat = os.stat(full_path)
                    new_files[virtual_path] = {
                        "disk": disk,
                        "real_path": os.path.join(POOL_DIR_NAME, relative).replace("\\", "/"),
                        "size": stat.st_size,
                        "mtime": int(stat.st_mtime)
                    }

    config["files"] = new_files
    save_config(config)

    return {"message": f"索引重建完成，共 {len(new_files)} 个文件"}


# ==================== 磁盘健康管理 ====================

def check_disk_health() -> dict:
    """
    检查所有池成员磁盘的健康状态
    返回: { "healthy": [...], "offline": [...], "warnings": [...] }
    """
    config = load_config()

    if not config.get("pool"):
        return {"error": "存储池未配置"}

    healthy = []
    offline = []
    warnings = []

    for disk in config["pool"]["disks"]:
        disk_status = {
            "disk": disk,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S")
        }

        # 检查磁盘是否可访问
        if not os.path.exists(disk):
            disk_status["status"] = "offline"
            disk_status["error"] = "磁盘不可访问"
            offline.append(disk_status)
            continue

        # 检查 .pool 目录是否存在
        pool_dir = os.path.join(disk, POOL_DIR_NAME)
        if not os.path.exists(pool_dir):
            disk_status["status"] = "warning"
            disk_status["error"] = ".pool 目录丢失"
            warnings.append(disk_status)
            continue

        # 检查磁盘空间
        try:
            usage = shutil.disk_usage(disk)
            disk_status["total"] = usage.total
            disk_status["used"] = usage.used
            disk_status["free"] = usage.free
            disk_status["usage_percent"] = round(usage.used / usage.total * 100, 1)

            # 空间不足警告 (< 10%)
            if usage.free / usage.total < 0.1:
                disk_status["status"] = "warning"
                disk_status["warning"] = "磁盘空间不足 (< 10%)"
                warnings.append(disk_status)
            else:
                disk_status["status"] = "healthy"
                healthy.append(disk_status)
        except Exception as e:
            disk_status["status"] = "error"
            disk_status["error"] = str(e)
            offline.append(disk_status)

    # 统计受影响的文件
    affected_files = []
    for vpath, file_info in config.get("files", {}).items():
        if file_info["disk"] in [d["disk"] for d in offline]:
            affected_files.append({
                "path": vpath,
                "disk": file_info["disk"],
                "size": file_info.get("size", 0)
            })

    return {
        "healthy": healthy,
        "offline": offline,
        "warnings": warnings,
        "affected_files": affected_files,
        "total_disks": len(config["pool"]["disks"]),
        "healthy_count": len(healthy),
        "offline_count": len(offline)
    }


def add_disk_to_pool(disk: str) -> dict:
    """
    向现有池添加新磁盘
    :param disk: 磁盘路径 "D:/"
    """
    config = load_config()

    if not config.get("pool"):
        raise Exception("存储池未配置")

    # 标准化磁盘路径
    disk = disk.upper().replace("\\", "/")
    if not disk.endswith("/"):
        disk += "/"

    # 检查磁盘是否存在
    if not os.path.exists(disk):
        raise Exception(f"磁盘 {disk} 不存在或不可访问")

    # 检查是否已在池中
    if disk in config["pool"]["disks"]:
        raise Exception(f"磁盘 {disk} 已在池中")

    # 创建 .pool 目录
    pool_dir = os.path.join(disk, POOL_DIR_NAME)
    os.makedirs(pool_dir, exist_ok=True)

    # 为每个逻辑卷创建目录
    for vol_name in config.get("volumes", {}).keys():
        vol_dir = os.path.join(pool_dir, vol_name)
        os.makedirs(vol_dir, exist_ok=True)

    # 添加到配置
    config["pool"]["disks"].append(disk)
    save_config(config)

    return {
        "message": f"磁盘 {disk} 已添加到池",
        "total_disks": len(config["pool"]["disks"])
    }
def check_remove_disk(disk: str, force: bool = False) -> dict:
    """
    移除磁盘前的预检查
    :param disk: 磁盘路径
    :param force: 是否强制（用于处理离线磁盘）
    :return: 检查结果
    """
    config = load_config()

    if not config.get("pool"):
        raise Exception("存储池未配置")

    # 标准化传入的路径
    input_disk = disk.upper().replace("\\", "/")
    if not input_disk.endswith("/"):
        input_disk += "/"

    # 在配置的磁盘列表中查找匹配项
    matched_disk = None
    for d in config["pool"]["disks"]:
        normalized_d = d.upper().replace("\\", "/")
        if not normalized_d.endswith("/"):
            normalized_d += "/"
        if normalized_d == input_disk:
            matched_disk = d
            break

    if not matched_disk:
        raise Exception(f"磁盘 {disk} 不在池中")

    disk = matched_disk

    # 检查磁盘是否在线
    disk_online = os.path.exists(disk)

    # 查找该磁盘上的文件
    files_on_disk = []
    disk_used = 0
    for vpath, info in config.get("files", {}).items():
        if info.get("disk") == disk:
            files_on_disk.append(vpath)
            disk_used += info.get("size", 0)

    # 计算其他磁盘的剩余空间
    other_disks = [d for d in config["pool"]["disks"] if d != disk]
    other_free = 0
    for d in other_disks:
        try:
            usage = shutil.disk_usage(d)
            other_free += usage.free
        except:
            pass

    # 判断是否可以迁移（保留1GB余量）
    reserved = 1073741824  # 1GB
    can_migrate = disk_online and other_free > (disk_used + reserved)
    shortage = (disk_used + reserved) - other_free if not can_migrate else 0

    return {
        "disk": disk,
        "disk_online": disk_online,
        "file_count": len(files_on_disk),
        "used_bytes": disk_used,
        "other_free_bytes": other_free,
        "can_migrate": can_migrate,
        "shortage_bytes": max(0, shortage),
        "other_disk_count": len(other_disks)
    }

def remove_disk_from_pool(disk: str, migrate: bool = True) -> dict:
    """
    从池中移除磁盘
    :param disk: 磁盘路径
    :param migrate: 是否迁移数据到其他磁盘
    """
    config = load_config()

    if not config.get("pool"):
        raise Exception("存储池未配置")

    # 标准化
    disk = disk.upper().replace("\\", "/")
    if not disk.endswith("/"):
        disk += "/"

    if disk not in config["pool"]["disks"]:
        raise Exception(f"磁盘 {disk} 不在池中")

    if len(config["pool"]["disks"]) <= 1:
        raise Exception("无法移除最后一个磁盘，请删除整个池")

    # 查找该磁盘上的文件
    files_on_disk = {
        vpath: info for vpath, info in config.get("files", {}).items()
        if info["disk"] == disk
    }

    migrated_count = 0
    failed_files = []

    if migrate and files_on_disk:
        # 迁移文件到其他磁盘
        other_disks = [d for d in config["pool"]["disks"] if d != disk]

        for vpath, file_info in files_on_disk.items():
            old_full_path = os.path.join(file_info["disk"], file_info["real_path"])

            # 检查源文件是否存在
            if not os.path.exists(old_full_path):
                # 文件已丢失，直接删除记录
                del config["files"][vpath]
                failed_files.append({"path": vpath, "error": "源文件不存在"})
                continue

            try:
                # 选择目标磁盘（最大剩余空间）
                target_disk = None
                max_free = 0
                for d in other_disks:
                    try:
                        usage = shutil.disk_usage(d)
                        if usage.free > max_free and usage.free > file_info.get("size", 0):
                            max_free = usage.free
                            target_disk = d
                    except:
                        continue

                if not target_disk:
                    failed_files.append({"path": vpath, "error": "没有足够空间的目标磁盘"})
                    continue

                # 构建新路径
                new_full_path = os.path.join(target_disk, file_info["real_path"])
                os.makedirs(os.path.dirname(new_full_path), exist_ok=True)

                # 复制文件
                shutil.copy2(old_full_path, new_full_path)

                # 更新索引
                config["files"][vpath]["disk"] = target_disk

                # 删除原文件
                os.remove(old_full_path)
                migrated_count += 1

            except Exception as e:
                failed_files.append({"path": vpath, "error": str(e)})

    elif not migrate and files_on_disk:
        # 不迁移，直接删除文件记录（文件将丢失！）
        for vpath in files_on_disk.keys():
            del config["files"][vpath]

    # 从池中移除磁盘
    config["pool"]["disks"].remove(disk)
    save_config(config)

    return {
        "message": f"磁盘 {disk} 已从池中移除",
        "migrated_count": migrated_count,
        "failed_files": failed_files,
        "remaining_disks": len(config["pool"]["disks"])
    }


def rebalance_pool(dry_run: bool = True) -> dict:
    """
    重新平衡池中各磁盘的数据分布
    :param dry_run: 是否只预览不实际执行
    """
    config = load_config()

    if not config.get("pool"):
        raise Exception("存储池未配置")

    disks = config["pool"]["disks"]
    if len(disks) < 2:
        raise Exception("至少需要2个磁盘才能进行平衡")

    # 计算当前各磁盘使用情况
    disk_usage = {}
    for disk in disks:
        try:
            usage = shutil.disk_usage(disk)
            disk_usage[disk] = {
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "pool_used": 0,  # 池内文件占用
                "files": []
            }
        except:
            continue

    # 统计各磁盘上的池文件
    for vpath, file_info in config.get("files", {}).items():
        disk = file_info["disk"]
        if disk in disk_usage:
            disk_usage[disk]["pool_used"] += file_info.get("size", 0)
            disk_usage[disk]["files"].append({
                "path": vpath,
                "size": file_info.get("size", 0)
            })

    # 计算平均使用率
    total_pool_used = sum(d["pool_used"] for d in disk_usage.values())
    total_capacity = sum(d["total"] for d in disk_usage.values())
    target_ratio = total_pool_used / total_capacity if total_capacity > 0 else 0

    # 找出需要迁移的文件
    moves = []
    for disk, info in disk_usage.items():
        current_ratio = info["pool_used"] / info["total"] if info["total"] > 0 else 0
        # 如果使用率超过平均值 5% 以上，考虑迁出
        if current_ratio > target_ratio + 0.05:
            excess_bytes = int((current_ratio - target_ratio) * info["total"])
            # 按文件大小排序，迁移大文件
            sorted_files = sorted(info["files"], key=lambda x: x["size"], reverse=True)
            moved_bytes = 0
            for f in sorted_files:
                if moved_bytes >= excess_bytes:
                    break
                moves.append({
                    "file": f["path"],
                    "size": f["size"],
                    "from": disk
                })
                moved_bytes += f["size"]

    # 为每个要迁移的文件选择目标磁盘
    for move in moves:
        # 选择使用率最低的磁盘
        best_target = None
        lowest_ratio = 1.0
        for disk, info in disk_usage.items():
            if disk == move["from"]:
                continue
            ratio = info["pool_used"] / info["total"] if info["total"] > 0 else 0
            if ratio < lowest_ratio and info["free"] > move["size"]:
                lowest_ratio = ratio
                best_target = disk
        move["to"] = best_target

    # 过滤掉无法迁移的
    moves = [m for m in moves if m.get("to")]

    result = {
        "dry_run": dry_run,
        "current_distribution": {
            disk: {
                "pool_used": info["pool_used"],
                "usage_percent": round(info["pool_used"] / info["total"] * 100, 1) if info["total"] > 0 else 0
            }
            for disk, info in disk_usage.items()
        },
        "target_ratio": round(target_ratio * 100, 1),
        "planned_moves": moves,
        "total_bytes_to_move": sum(m["size"] for m in moves)
    }

    if not dry_run and moves:
        # 实际执行迁移
        success_count = 0
        for move in moves:
            try:
                file_info = config["files"][move["file"]]
                old_path = os.path.join(file_info["disk"], file_info["real_path"])
                new_path = os.path.join(move["to"], file_info["real_path"])

                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                shutil.copy2(old_path, new_path)
                os.remove(old_path)

                config["files"][move["file"]]["disk"] = move["to"]
                success_count += 1
            except Exception as e:
                move["error"] = str(e)

        save_config(config)
        result["executed"] = True
        result["success_count"] = success_count

    return result


def get_pool_actual_path(pool_path):
    """
    将 pool://volume_name/subpath 转换为实际文件系统路径
    """
    config = load_config()
    pool_cfg = config.get("pool")
    if not pool_cfg or not pool_cfg.get("is_configured"):
        return None

    # 解析 pool://volume_name/subpath
    # 去掉 pool:// 前缀
    path_part = pool_path.replace('pool://', '')
    parts = path_part.split('/', 1)
    volume_name = parts[0]
    sub_path = parts[1] if len(parts) > 1 else ''

    # 获取卷信息
    volumes = pool_cfg.get("volumes", [])
    for vol in volumes:
        if vol.get("name") == volume_name:
            # 获取卷的实际挂载路径
            mount_disk = vol.get("disk")  # 卷所在的磁盘
            mount_path = vol.get("path", "")  # 卷的相对路径

            if mount_disk:
                actual_base = os.path.join(mount_disk, mount_path.lstrip('/\\'))
                if sub_path:
                    return os.path.join(actual_base, sub_path.replace('/', os.sep))
                return actual_base

    # 如果没找到对应卷，尝试用第一个磁盘
    disks = pool_cfg.get("disks", [])
    if disks:
        first_disk = disks[0]
        base_path = os.path.join(first_disk, ".pool_data", volume_name)
        if sub_path:
            return os.path.join(base_path, sub_path.replace('/', os.sep))
        return base_path

    return None


def search_in_pool(pool_path, keyword):
    """在空间池中搜索文件"""
    results = []
    keyword_lower = keyword.lower()
    max_results = 200

    try:
        config = load_config()

        if not config.get("pool"):
            return {'success': False, 'error': '空间池未配置', 'items': [], 'count': 0}

        # 解析 pool://volume_name/subpath
        path_part = pool_path.replace('pool://', '')
        parts = path_part.split('/', 1)
        volume_name = parts[0]
        sub_path = parts[1] if len(parts) > 1 else ''

        # 构建搜索前缀
        if sub_path:
            search_prefix = f"{volume_name}/{sub_path.strip('/')}/"
        else:
            search_prefix = f"{volume_name}/"

        # 用于记录已添加的目录，避免重复
        seen_dirs = set()

        # 从配置中的 files 字典搜索
        for vpath, file_info in config.get("files", {}).items():
            # 只搜索指定卷/路径下的文件
            if not vpath.startswith(search_prefix) and not vpath.startswith(volume_name + "/"):
                continue

            # 如果指定了子路径，确保文件在该子路径下
            if sub_path and not vpath.startswith(search_prefix):
                continue

            # 获取文件名
            filename = vpath.split('/')[-1]

            # 模糊匹配
            if keyword_lower in filename.lower():
                results.append({
                    'name': filename,
                    'path': f"pool://{vpath}",
                    'is_dir': False,
                    'size': file_info.get('size', 0),
                    'mtime': file_info.get('mtime', 0)
                })

                if len(results) >= max_results:
                    break

            # 同时检查路径中的目录名是否匹配
            path_parts = vpath.split('/')
            for i, part in enumerate(path_parts[:-1]):  # 排除最后的文件名
                if keyword_lower in part.lower():
                    dir_path = '/'.join(path_parts[:i + 1])
                    if dir_path not in seen_dirs:
                        seen_dirs.add(dir_path)
                        results.append({
                            'name': part,
                            'path': f"pool://{dir_path}",
                            'is_dir': True,
                            'size': 0,
                            'mtime': 0
                        })

                        if len(results) >= max_results:
                            break

        # 按目录优先、名称排序
        results.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))

        return {
            'success': True,
            'keyword': keyword,
            'count': len(results),
            'items': results
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': str(e), 'items': [], 'count': 0}


def get_available_disks() -> List[dict]:
    """
    获取可添加到池的可用磁盘列表
    """
    config = load_config()
    current_disks = config.get("pool", {}).get("disks", []) if config.get("pool") else []

    available = []

    # Windows 盘符检测
    if os.name == 'nt':
        import string
        for letter in string.ascii_uppercase:
            drive = f"{letter}:/"
            if os.path.exists(drive):
                # 排除已在池中的磁盘
                if drive not in current_disks:
                    try:
                        usage = shutil.disk_usage(drive)
                        available.append({
                            "drive": drive,
                            "total": usage.total,
                            "free": usage.free,
                            "in_pool": False
                        })
                    except:
                        pass
    else:
        # Linux: 检测 /mnt 和 /media 下的挂载点
        for mount_base in ['/mnt', '/media']:
            if os.path.exists(mount_base):
                for name in os.listdir(mount_base):
                    mount_path = os.path.join(mount_base, name)
                    if os.path.ismount(mount_path):
                        if mount_path not in current_disks:
                            try:
                                usage = shutil.disk_usage(mount_path)
                                available.append({
                                    "drive": mount_path,
                                    "total": usage.total,
                                    "free": usage.free,
                                    "in_pool": False
                                })
                            except:
                                pass

    return available