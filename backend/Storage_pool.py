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
                "free": usage.free
            })
            total_size += usage.total
            total_free += usage.free
        except:
            disk_stats.append({
                "disk": disk,
                "total": 0,
                "used": 0,
                "free": 0,
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


def remove_pool(confirm_text: str) -> dict:
    """删除存储池"""
    if confirm_text != "DELETE POOL":
        raise Exception("确认文本不正确")

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

def select_disk(volume_name: str, file_size: int = 0) -> str:
    """
    根据策略选择磁盘
    :param volume_name: 逻辑卷名
    :param file_size: 文件大小（用于检查空间是否足够）
    :return: 磁盘路径
    """
    config = load_config()

    if not config.get("pool"):
        raise Exception("存储池未配置")

    if volume_name not in config.get("volumes", {}):
        raise Exception(f"逻辑卷 {volume_name} 不存在")

    vol = config["volumes"][volume_name]
    strategy = vol.get("strategy", "largest_free")
    disks = config["pool"]["disks"]

    # 获取各磁盘可用空间
    disk_free = []
    for disk in disks:
        try:
            usage = shutil.disk_usage(disk)
            if usage.free > file_size + 1073741824:  # 保留 1GB
                disk_free.append((disk, usage.free))
        except:
            continue

    if not disk_free:
        raise Exception("没有足够空间的磁盘")

    if strategy == "largest_free":
        # 选择剩余空间最大的
        disk_free.sort(key=lambda x: x[1], reverse=True)
        return disk_free[0][0]

    elif strategy == "round_robin":
        # 轮询
        idx = config.get("round_robin_index", {}).get(volume_name, 0)
        available_disks = [d[0] for d in disk_free]
        if not available_disks:
            raise Exception("没有可用磁盘")
        selected = available_disks[idx % len(available_disks)]
        config["round_robin_index"][volume_name] = (idx + 1) % len(available_disks)
        save_config(config)
        return selected

    elif strategy == "balanced":
        # 按剩余空间比例加权选择（简化：选使用率最低的）
        disk_free.sort(key=lambda x: x[1], reverse=True)
        return disk_free[0][0]

    else:
        # 默认用最大剩余空间
        disk_free.sort(key=lambda x: x[1], reverse=True)
        return disk_free[0][0]


# ==================== 文件操作 ====================

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
            items.append({
                "name": relative,
                "is_dir": False,
                "size": file_info.get("size", 0),
                "mtime": file_info.get("mtime", 0),
                "disk": file_info.get("disk", "")
            })

    # 排序：目录在前
    items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    return items


def add_file(volume_name: str, subpath: str, filename: str,
             file_data: bytes) -> dict:
    """
    添加文件到逻辑卷（上传用）
    :param volume_name: 逻辑卷名
    :param subpath: 子路径（可为空）
    :param filename: 文件名
    :param file_data: 文件内容
    """
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

    # 选择磁盘
    disk = select_disk(volume_name, len(file_data))

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