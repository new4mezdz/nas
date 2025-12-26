# services/ec_service.py
# -*- coding: utf-8 -*-
"""
纠删码业务逻辑
"""

from ec_engine.rs_systematic import decode as rs_decode
from ec_engine.ec_error import ECError


def decode_from_dict(shard_dict: dict, meta: dict) -> bytes:
    """
    从分片字典解码还原原始数据
    
    一个更健壮的解码器，可以处理索引中缺少 'shard_size' 和 'original_size' 的情况。
    
    Args:
        shard_dict: {分片索引: 分片数据} 字典
        meta: 文件元数据，包含 k, m, original_size/size, shard_size 等
    
    Returns:
        解码后的原始数据 bytes
    
    Raises:
        ECError: 元数据缺失必要字段时抛出
    """
    k, m = meta["k"], meta["m"]
    
    # 使用 .get() 并提供备用值
    # 如果 "original_size" 不存在，就使用 "size"
    original_size = meta.get("original_size") or meta.get("size")
    if original_size is None:
        raise ECError("文件元数据中缺少 'original_size' 或 'size' 键")
    
    # 如果 "shard_size" 不存在，就根据原始大小和k值进行计算
    shard_size = meta.get("shard_size")
    if shard_size is None:
        shard_size = (original_size + k - 1) // k
    
    shard_list = [None] * (k + m)
    # 使用 .items() 遍历字典
    for i_str, buf in shard_dict.items():
        i = int(i_str)
        if 0 <= i < k + m:
            shard_list[i] = buf
    
    # 依赖 rs_decode (来自 ec_engine.rs_systematic)
    return rs_decode(shard_list, k, m, shard_size, original_size)


def capacity_estimate(disks: list, k: int) -> dict:
    """
    基于最小盘估算卷容量
    
    Args:
        disks: 磁盘路径列表
        k: 数据分片数量
    
    Returns:
        容量估算信息字典
    """
    from utils import get_disk_info
    
    info_map = {d["mount"]: d for d in get_disk_info()}
    sizes = []
    
    for d in disks:
        meta = info_map.get(d) or {}
        sizes.append({
            "mount": d,
            "total": int(meta.get("bytes_total") or 0),
            "free": int(meta.get("bytes_free") or 0),
        })
    
    min_total = min((s["total"] for s in sizes if s["total"] > 0), default=0)
    min_free = min((s["free"] for s in sizes if s["free"] > 0), default=0)
    max_total = max((s["total"] for s in sizes), default=0)
    imbalance = (max_total / min_total) if (min_total > 0) else 0.0
    
    return {
        "min_disk_total": min_total,
        "min_disk_free": min_free,
        "usable_total_bytes": min_total * max(k, 0),
        "usable_free_bytes": min_free * max(k, 0),
        "imbalance_ratio": imbalance,  # >1.2 说明盘容量差异较大
        "disks": sizes
    }
