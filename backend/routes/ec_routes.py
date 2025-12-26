# routes/ec_routes.py
# -*- coding: utf-8 -*-
import os
import json
import time
import shutil
import hashlib
from datetime import datetime
from functools import wraps
from flask import Blueprint, request, jsonify

from common import get_available_drives, BASE_DIRS
from utils import get_disk_info
from permission_decorator import permission_required

ec_bp = Blueprint('ec', __name__)

# 外部依赖
_ctx = {
    'EC_CFG_PATH': None,
    'EC_IDX_PATH': None,
    'NAS_SHARED_SECRET': None,
    'load_json': None,
    'save_json': None,
    'decode_from_dict': None,
    'rs_encode': None,
}


def _norm_abs(path: str) -> str:
    """绝对化 + 规范化路径"""
    return os.path.normcase(os.path.abspath(os.path.normpath(path or "")))


def init_ec_routes(ec_cfg_path, ec_idx_path, shared_secret, load_json, save_json, decode_from_dict, rs_encode):
    _ctx['EC_CFG_PATH'] = ec_cfg_path
    _ctx['EC_IDX_PATH'] = ec_idx_path
    _ctx['NAS_SHARED_SECRET'] = shared_secret
    _ctx['load_json'] = load_json
    _ctx['save_json'] = save_json
    _ctx['decode_from_dict'] = decode_from_dict
    _ctx['rs_encode'] = rs_encode


def internal_or_permission(permission_level):
    """允许内部请求或有权限的用户访问"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            secret = request.headers.get('X-NAS-Secret')
            if secret == _ctx['NAS_SHARED_SECRET']:
                return f(*args, **kwargs)
            return permission_required(permission_level)(f)(*args, **kwargs)
        return decorated_function
    return decorator


# ==================== EC状态 ====================
@ec_bp.route('/api/ec_status', methods=['GET'])
@permission_required('fullcontrol')
def get_ec_status():
    """获取纠删码卷的健康状况"""
    load_json = _ctx['load_json']
    cfg = load_json(_ctx['EC_CFG_PATH'], {})

    if not cfg:
        return jsonify({"is_configured": False})

    k = cfg.get("k", 0)
    m = cfg.get("m", 0)
    config_disks = set(cfg.get("disks", []))

    # 获取可用磁盘
    available_disks = set()
    for disk in get_disk_info():
        mount_point = disk.get("mount", "").upper().replace("\\", "/")
        if mount_point not in ["C:/", "D:/", "/"]:
            available_disks.add(_norm_abs(disk.get("mount")))

    lost_disks = [d for d in config_disks if _norm_abs(d) not in available_disks]
    is_healthy = not bool(lost_disks)
    can_rebuild = 0 < len(lost_disks) <= m

    # 计算可用容量
    usable_bytes = 0
    if config_disks:
        min_free = float('inf')
        for disk in get_disk_info():
            mount_point = _norm_abs(disk.get("mount"))
            if mount_point in config_disks:
                free = disk.get("bytes_free", 0)
                if free < min_free:
                    min_free = free
        if min_free != float('inf'):
            usable_bytes = min_free * k

    return jsonify({
        "is_configured": True,
        "is_healthy": is_healthy,
        "k": k,
        "m": m,
        "config_disks": list(config_disks),
        "lost_disks": lost_disks,
        "can_rebuild": can_rebuild,
        "usable_bytes": usable_bytes,
        "available_new_disks": [d for d in available_disks if d not in config_disks]
    })


# ==================== EC健康检查 ====================
@ec_bp.route('/api/ec_health_check', methods=['GET'])
@permission_required('fullcontrol')
def ec_health_check():
    """全面的EC卷健康检查"""
    load_json = _ctx['load_json']
    cfg = load_json(_ctx['EC_CFG_PATH'], {})

    if not cfg:
        return jsonify({"is_configured": False})

    idx = load_json(_ctx['EC_IDX_PATH'], {"files": {}})
    m = cfg.get("m", 0)

    health_report = {
        "total_files": len(idx.get("files", {})),
        "healthy_files": 0,
        "at_risk_files": 0,
        "corrupted_files": 0,
        "file_details": []
    }

    for name, meta in idx.get("files", {}).items():
        missing_shards = []
        available_shards = []

        for i, disk in enumerate(meta["disks"][:meta["k"] + meta["m"]]):
            enc_dir = os.path.join(disk, "encoded", os.path.dirname(name))
            blk = os.path.join(enc_dir, f"{os.path.basename(name)}.blk_{i}")

            if os.path.exists(blk):
                available_shards.append(i)
            else:
                missing_shards.append(i)

        missing_count = len(missing_shards)

        if missing_count == 0:
            health_report["healthy_files"] += 1
            status = "healthy"
        elif missing_count <= m:
            health_report["at_risk_files"] += 1
            status = "at_risk"
        else:
            health_report["corrupted_files"] += 1
            status = "corrupted"

        health_report["file_details"].append({
            "name": name,
            "status": status,
            "missing_count": missing_count,
            "available_count": len(available_shards),
            "missing_shards": missing_shards,
            "can_recover": missing_count <= m
        })

    return jsonify(health_report)


# ==================== EC批量恢复 ====================
@ec_bp.route('/api/ec_batch_recover', methods=['POST'])
@permission_required('fullcontrol')
def ec_batch_recover():
    """批量恢复所有可恢复的文件"""
    load_json = _ctx['load_json']
    decode_from_dict = _ctx['decode_from_dict']
    rs_encode = _ctx['rs_encode']

    cfg = load_json(_ctx['EC_CFG_PATH'], {})
    if not cfg:
        return jsonify({"error": "未配置纠删码"}), 400

    idx = load_json(_ctx['EC_IDX_PATH'], {"files": {}})

    recovery_report = {
        "total_processed": 0,
        "successfully_recovered": 0,
        "failed_recoveries": [],
        "skipped_files": []
    }

    for name, meta in idx.get("files", {}).items():
        k, m = meta["k"], meta["m"]
        disks = meta["disks"]

        missing_indices = []
        shard_dict = {}
        meta_obj = None

        for i, disk in enumerate(disks[:k + m]):
            enc_dir = os.path.join(disk, "encoded", os.path.dirname(name))
            blk = os.path.join(enc_dir, f"{os.path.basename(name)}.blk_{i}")

            if os.path.exists(blk):
                with open(blk, "rb") as f:
                    shard_dict[i] = f.read()
            else:
                missing_indices.append(i)

            if not meta_obj:
                mj = os.path.join(enc_dir, f"{os.path.basename(name)}.meta.json")
                if os.path.exists(mj):
                    with open(mj, "r", encoding="utf-8") as mf:
                        meta_obj = json.load(mf)

        recovery_report["total_processed"] += 1

        if not missing_indices:
            recovery_report["skipped_files"].append({"name": name, "reason": "no_missing_shards"})
            continue

        if len(missing_indices) > m:
            recovery_report["failed_recoveries"].append({
                "name": name, "reason": "too_many_missing_shards", "missing_count": len(missing_indices)
            })
            continue

        if len(shard_dict) < k or not meta_obj:
            recovery_report["failed_recoveries"].append({
                "name": name, "reason": "insufficient_shards", "available_count": len(shard_dict)
            })
            continue

        try:
            data_bytes = decode_from_dict(shard_dict, meta_obj)
            all_shards = rs_encode(data_bytes, k, m)

            for missing_idx in missing_indices:
                disk = disks[missing_idx]
                enc_dir = os.path.join(disk, "encoded", os.path.dirname(name))
                os.makedirs(enc_dir, exist_ok=True)

                blk_path = os.path.join(enc_dir, f"{os.path.basename(name)}.blk_{missing_idx}")
                with open(blk_path, "wb") as f:
                    f.write(all_shards[missing_idx])

                meta_path = os.path.join(enc_dir, f"{os.path.basename(name)}.meta.json")
                with open(meta_path, "w", encoding="utf-8") as mf:
                    json.dump(meta_obj, mf, ensure_ascii=False)

            recovery_report["successfully_recovered"] += 1

        except Exception as e:
            recovery_report["failed_recoveries"].append({
                "name": name, "reason": "recovery_exception", "error": str(e)
            })

    return jsonify({"success": True, "report": recovery_report})


# ==================== EC磁盘恢复 ====================
@ec_bp.route('/api/ec_recover', methods=['POST'])
@permission_required('fullcontrol')
def ec_recover_disk():
    """恢复丢失的磁盘"""
    load_json = _ctx['load_json']
    save_json = _ctx['save_json']
    decode_from_dict = _ctx['decode_from_dict']
    rs_encode = _ctx['rs_encode']

    data = request.get_json()
    lost_disk_raw = data.get('lost_disk', '')
    new_disk_raw = data.get('new_disk', '')
    lost_disk_path = _norm_abs(lost_disk_raw)
    new_disk_path = _norm_abs(new_disk_raw)

    cfg = load_json(_ctx['EC_CFG_PATH'], {})
    if not cfg:
        return jsonify({"error": "未配置纠删码"}), 400

    config_disks_raw = cfg.get("disks", [])
    config_disks_normalized = [_norm_abs(d) for d in config_disks_raw]

    if lost_disk_path not in config_disks_normalized:
        return jsonify({"error": "丢失的硬盘不在全局配置中"}), 400

    new_config_disks_raw = [new_disk_raw if _norm_abs(d) == lost_disk_path else d for d in config_disks_raw]
    cfg["disks"] = new_config_disks_raw
    save_json(_ctx['EC_CFG_PATH'], cfg)

    idx = load_json(_ctx['EC_IDX_PATH'], {"files": {}})
    files_to_rebuild = list(idx.get("files", {}).items())
    rebuilt_count = 0
    failed_files = []

    for name, meta in files_to_rebuild:
        k, m = meta["k"], meta["m"]
        file_disks_raw = meta.get("disks", [])
        if not file_disks_raw:
            failed_files.append(name)
            continue

        file_disks_normalized = [_norm_abs(d) for d in file_disks_raw]

        try:
            lost_shard_index = file_disks_normalized.index(lost_disk_path)
        except ValueError:
            continue

        shard_dict = {}
        for i, disk_raw in enumerate(file_disks_raw):
            if _norm_abs(disk_raw) == lost_disk_path:
                continue
            enc_dir = os.path.join(disk_raw, "encoded", os.path.dirname(name))
            blk_path = os.path.join(enc_dir, f"{os.path.basename(name)}.blk_{i}")
            if os.path.exists(blk_path):
                with open(blk_path, "rb") as f:
                    shard_dict[i] = f.read()

        if len(shard_dict) < k:
            failed_files.append(name)
            continue

        try:
            reconstructed_data = decode_from_dict(shard_dict, meta)
            all_new_shards = rs_encode(reconstructed_data, k, m)
            shard_to_write = all_new_shards[lost_shard_index]

            new_shard_dir = os.path.join(new_disk_raw, "encoded", os.path.dirname(name))
            os.makedirs(new_shard_dir, exist_ok=True)

            new_shard_path = os.path.join(new_shard_dir, f"{os.path.basename(name)}.blk_{lost_shard_index}")
            with open(new_shard_path, "wb") as f:
                f.write(shard_to_write)

            idx["files"][name]["disks"] = new_config_disks_raw
            rebuilt_count += 1
        except Exception as e:
            print(f"ERROR: Exception during recovery for {name}: {e}")
            failed_files.append(name)

    save_json(_ctx['EC_IDX_PATH'], idx)

    return jsonify({
        "success": True,
        "message": f"恢复完成。共重建 {rebuilt_count} 个文件。",
        "failed_files": failed_files
    })


# ==================== EC配置管理 ====================
@ec_bp.route('/api/ec_config', methods=['GET', 'POST', 'DELETE'])
@internal_or_permission('fullcontrol')
def api_ec_config():
    """EC配置管理"""
    load_json = _ctx['load_json']
    save_json = _ctx['save_json']

    # 容量估算辅助函数
    def _capacity_estimate(disks_norm: list, k: int):
        info = get_disk_info()
        info_map = {_norm_abs(d["mount"]): d for d in info if "mount" in d}
        sizes = []
        for d in disks_norm:
            di = info_map.get(_norm_abs(d))
            if di:
                total = int(di.get("bytes_total") or di.get("total") or 0)
                free = int(di.get("bytes_free") or di.get("free") or 0)
            else:
                try:
                    du = shutil.disk_usage(d)
                    total, free = int(du.total), int(du.free)
                except Exception:
                    total, free = 0, 0
            sizes.append({"mount": d, "total": total, "free": free})

        min_total = min((s["total"] for s in sizes if s["total"] > 0), default=0)
        min_free = min((s["free"] for s in sizes if s["free"] > 0), default=0)
        max_total = max((s["total"] for s in sizes), default=0)
        imbalance = (max_total / min_total) if (min_total > 0) else 0.0
        return {
            "min_disk_total": min_total,
            "min_disk_free": min_free,
            "usable_total_bytes": min_total * max(k, 0),
            "usable_free_bytes": min_free * max(k, 0),
            "imbalance_ratio": imbalance,
            "disks": sizes
        }

    # DELETE - 删除配置
    if request.method == "DELETE":
        try:
            cfg = load_json(_ctx['EC_CFG_PATH'], {})
            disks = cfg.get("disks", [])

            cleaned_disks = []
            failed_disks = []
            for disk in disks:
                try:
                    encoded_dir = os.path.join(disk, "encoded")
                    if os.path.exists(encoded_dir):
                        shutil.rmtree(encoded_dir)
                        cleaned_disks.append(disk)
                        print(f"✅ 已清理磁盘 {disk} 的 encoded 目录")
                except Exception as e:
                    failed_disks.append({"disk": disk, "error": str(e)})
                    print(f"⚠️ 清理磁盘 {disk} 失败: {e}")

            if os.path.exists(_ctx['EC_CFG_PATH']):
                os.remove(_ctx['EC_CFG_PATH'])
            if os.path.exists(_ctx['EC_IDX_PATH']):
                os.remove(_ctx['EC_IDX_PATH'])

            return jsonify({
                "success": True,
                "message": "纠删码配置已成功删除",
                "cleaned_disks": cleaned_disks,
                "failed_disks": failed_disks,
                "total_cleaned": len(cleaned_disks)
            })
        except Exception as e:
            return jsonify({"error": f"删除配置失败: {str(e)}"}), 500

    # GET - 获取配置
    if request.method == "GET":
        cfg = load_json(_ctx['EC_CFG_PATH'], {})
        if not cfg:
            return jsonify({"success": True, "config": None})
        k = int(cfg.get("k") or 0)
        capacity = _capacity_estimate(cfg.get("disks", []), k) if cfg.get("disks") else None
        return jsonify({"success": True, "config": cfg, "capacity": capacity})

    # POST - 保存配置
    data = request.get_json(force=True)
    scheme = (data.get("scheme") or "rs").lower()
    k = int(data.get("k") or 0)
    m = int(data.get("m") or 0)
    raw_disks = data.get("disks") or []

    if scheme != "rs":
        return jsonify({"error": "仅支持 scheme='rs'"}), 400
    if k <= 0 or m <= 0:
        return jsonify({"error": "k 和 m 必须为正整数"}), 400

    seen = set()
    disks_norm = []
    for d in raw_disks:
        p = _norm_abs(d)
        if p not in seen:
            disks_norm.append(p)
            seen.add(p)

    if len(disks_norm) < k + m:
        return jsonify({"error": f"磁盘数量不足，需要 ≥ k+m = {k+m}"}), 400

    mounts = {_norm_abs(d["mount"]) for d in get_disk_info()}
    invalid = [orig for orig in raw_disks if _norm_abs(orig) not in mounts]
    if invalid:
        return jsonify({"error": "存在无效磁盘", "invalid": invalid}), 400

    try:
        for d in disks_norm:
            os.makedirs(os.path.join(d, "encoded"), exist_ok=True)
    except Exception as e:
        return jsonify({"error": f"无法创建 encoded 目录：{e}"}), 500

    cfg = {"scheme": scheme, "k": k, "m": m, "disks": disks_norm}
    save_json(_ctx['EC_CFG_PATH'], cfg)

    if not os.path.exists(_ctx['EC_IDX_PATH']):
        save_json(_ctx['EC_IDX_PATH'], {"files": {}})

    capacity = _capacity_estimate(disks_norm, k)

    return jsonify({
        "success": True,
        "config": cfg,
        "capacity": capacity
    })


# ==================== EC删除配置（危险） ====================
@ec_bp.route('/api/ec_remove', methods=['POST'])
@permission_required('fullcontrol')
def remove_ec_config():
    """删除EC配置（危险操作）"""
    load_json = _ctx['load_json']

    data = request.get_json()
    confirm_text = data.get('confirm_text', '')

    if confirm_text != "DELETE EC":
        return jsonify({"error": "确认文本不正确"}), 400

    try:
        cfg = load_json(_ctx['EC_CFG_PATH'], {})
        if not cfg:
            return jsonify({"error": "未配置纠删码"}), 400

        disks = cfg.get("disks", [])
        idx = load_json(_ctx['EC_IDX_PATH'], {"files": {}})
        files = idx.get("files", {})

        deleted_dirs = []
        failed_dirs = []

        for disk in disks:
            encoded_dir = os.path.join(disk, "encoded")
            if os.path.exists(encoded_dir):
                try:
                    shutil.rmtree(encoded_dir)
                    deleted_dirs.append(encoded_dir)
                    print(f"[EC_REMOVE] 已删除: {encoded_dir}")
                except Exception as e:
                    failed_dirs.append({"path": encoded_dir, "error": str(e)})
                    print(f"[EC_REMOVE] 删除失败: {encoded_dir}, 错误: {e}")

        backup_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_cfg_path = None
        backup_idx_path = None

        if os.path.exists(_ctx['EC_CFG_PATH']):
            backup_cfg_path = _ctx['EC_CFG_PATH'].replace(".json", f"_backup_{backup_time}.json")
            shutil.copy2(_ctx['EC_CFG_PATH'], backup_cfg_path)
            print(f"[EC_REMOVE] 配置文件已备份到: {backup_cfg_path}")
            os.remove(_ctx['EC_CFG_PATH'])
            print(f"[EC_REMOVE] 已删除配置文件: {_ctx['EC_CFG_PATH']}")

        if os.path.exists(_ctx['EC_IDX_PATH']):
            backup_idx_path = _ctx['EC_IDX_PATH'].replace(".json", f"_backup_{backup_time}.json")
            shutil.copy2(_ctx['EC_IDX_PATH'], backup_idx_path)
            print(f"[EC_REMOVE] 索引文件已备份到: {backup_idx_path}")
            os.remove(_ctx['EC_IDX_PATH'])
            print(f"[EC_REMOVE] 已删除索引文件: {_ctx['EC_IDX_PATH']}")

        return jsonify({
            "success": True,
            "message": f"纠删码配置已删除。删除了 {len(deleted_dirs)} 个目录，{len(files)} 个文件的索引记录。",
            "deleted_dirs": deleted_dirs,
            "failed_dirs": failed_dirs,
            "deleted_file_count": len(files),
            "backup_config": backup_cfg_path,
            "backup_index": backup_idx_path
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"删除纠删码配置失败: {str(e)}"}), 500


# ==================== EC导出所有文件 ====================
@ec_bp.route('/api/ec_export_all', methods=['POST'])
@permission_required('fullcontrol')
def export_all_ec_files():
    """批量导出EC文件"""
    load_json = _ctx['load_json']
    decode_from_dict = _ctx['decode_from_dict']

    data = request.get_json()
    target_disk = data.get('target_disk', '')

    if not target_disk:
        return jsonify({"error": "请指定目标磁盘"}), 400

    from common import get_base_dir_for_path
    target_base_dir = get_base_dir_for_path(target_disk)
    if not target_base_dir or not os.path.exists(target_base_dir):
        return jsonify({"error": "目标磁盘不存在"}), 400

    try:
        cfg = load_json(_ctx['EC_CFG_PATH'], {})
        if not cfg:
            return jsonify({"error": "未配置纠删码"}), 400

        idx = load_json(_ctx['EC_IDX_PATH'], {"files": {}})
        files = idx.get("files", {})

        if not files:
            return jsonify({"error": "纠删码卷中没有文件"}), 400

        k = cfg.get("k", 0)
        m = cfg.get("m", 0)

        export_root = os.path.join(target_base_dir, "ec_export", datetime.now().strftime("%Y%m%d_%H%M%S"))
        os.makedirs(export_root, exist_ok=True)

        total_files = len(files)
        exported_count = 0
        failed_files = []

        print(f"\n[EC_EXPORT] 开始导出 {total_files} 个文件到 {export_root}")

        for file_name, meta in files.items():
            try:
                print(f"[EC_EXPORT] 正在导出: {file_name}")

                file_k = meta.get("k", k)
                file_m = meta.get("m", m)
                disks = meta.get("disks", [])

                shard_dict = {}
                for i, disk in enumerate(disks[:file_k + file_m]):
                    enc_dir = os.path.join(disk, "encoded", os.path.dirname(file_name))
                    blk_path = os.path.join(enc_dir, f"{os.path.basename(file_name)}.blk_{i}")
                    if os.path.exists(blk_path):
                        with open(blk_path, "rb") as f:
                            shard_dict[i] = f.read()

                if len(shard_dict) < file_k:
                    failed_files.append({
                        "file": file_name,
                        "reason": f"分片不足 (需要{file_k}个，实际{len(shard_dict)}个)"
                    })
                    print(f"[EC_EXPORT] 失败: {file_name} - 分片不足")
                    continue

                decoded_data = decode_from_dict(shard_dict, meta)

                target_file_path = os.path.join(export_root, file_name)
                os.makedirs(os.path.dirname(target_file_path), exist_ok=True)

                with open(target_file_path, "wb") as f:
                    f.write(decoded_data)

                exported_count += 1
                print(f"[EC_EXPORT] 成功: {file_name}")

            except Exception as e:
                failed_files.append({
                    "file": file_name,
                    "reason": str(e)
                })
                print(f"[EC_EXPORT] 失败: {file_name} - {e}")

        # 创建导出报告
        report_path = os.path.join(export_root, "_export_report.txt")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"纠删码文件导出报告\n")
            f.write(f"=" * 50 + "\n")
            f.write(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"目标磁盘: {target_disk}\n")
            f.write(f"导出目录: {export_root}\n")
            f.write(f"总文件数: {total_files}\n")
            f.write(f"成功导出: {exported_count}\n")
            f.write(f"失败文件: {len(failed_files)}\n")
            f.write(f"\n")

            if failed_files:
                f.write(f"失败详情:\n")
                f.write(f"-" * 50 + "\n")
                for fail in failed_files:
                    f.write(f"文件: {fail['file']}\n")
                    f.write(f"原因: {fail['reason']}\n")
                    f.write(f"\n")

        print(f"[EC_EXPORT] 导出完成: 成功 {exported_count}/{total_files}")

        return jsonify({
            "success": True,
            "message": f"导出完成。成功 {exported_count} 个，失败 {len(failed_files)} 个。",
            "export_path": export_root,
            "total_files": total_files,
            "exported_count": exported_count,
            "failed_count": len(failed_files),
            "failed_files": failed_files,
            "report_path": report_path
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"导出失败: {str(e)}"}), 500


# ==================== EC扫描缺失分片 ====================
@ec_bp.route('/api/volume/rebuild/scan', methods=['POST'])
@permission_required('fullcontrol')
def ec_scan():
    """扫描缺失分片"""
    load_json = _ctx['load_json']
    cfg = load_json(_ctx['EC_CFG_PATH'], {})

    if not cfg:
        return jsonify({"error": "未配置纠删码"}), 400

    idx = load_json(_ctx['EC_IDX_PATH'], {"files": {}})
    detail, missing_total = {}, 0

    for name, meta in idx.get("files", {}).items():
        miss = []
        for i, disk in enumerate(meta["disks"][:meta["k"] + meta["m"]]):
            enc_dir = os.path.join(disk, "encoded", os.path.dirname(name))
            blk = os.path.join(enc_dir, f"{os.path.basename(name)}.blk_{i}")
            if not os.path.exists(blk):
                miss.append(i)
        if miss:
            detail[name] = miss
            missing_total += len(miss)

    return jsonify({"success": True, "missing_total": missing_total, "detail": detail})


# ==================== EC重建缺失分片 ====================
@ec_bp.route('/api/volume/rebuild/start', methods=['POST'])
@permission_required('fullcontrol')
def ec_rebuild():
    """重建缺失分片"""
    load_json = _ctx['load_json']
    decode_from_dict = _ctx['decode_from_dict']
    rs_encode = _ctx['rs_encode']

    cfg = load_json(_ctx['EC_CFG_PATH'], {})
    if not cfg:
        return jsonify({"error": "未配置纠删码"}), 400

    idx = load_json(_ctx['EC_IDX_PATH'], {"files": {}})
    fixed = 0

    for name, meta in idx.get("files", {}).items():
        shard_dict, meta_j = {}, None

        for i, disk in enumerate(meta["disks"][:meta["k"] + meta["m"]]):
            enc = os.path.join(disk, "encoded", os.path.dirname(name))
            blk = os.path.join(enc, f"{os.path.basename(name)}.blk_{i}")

            if os.path.exists(blk):
                with open(blk, "rb") as f:
                    shard_dict[i] = f.read()

            if not meta_j:
                mj = os.path.join(enc, f"{os.path.basename(name)}.meta.json")
                if os.path.exists(mj):
                    with open(mj, "r", encoding="utf-8") as mf:
                        meta_j = json.load(mf)

        if not meta_j or len(shard_dict) < meta["k"]:
            continue

        try:
            data = decode_from_dict(shard_dict, meta_j)
            new_shards = rs_encode(data, meta["k"], meta["m"])
        except Exception as e:
            print(f"[EC] rebuild {name} failed:", e)
            continue

        for i, disk in enumerate(meta["disks"][:meta["k"] + meta["m"]]):
            enc = os.path.join(disk, "encoded", os.path.dirname(name))
            blk = os.path.join(enc, f"{os.path.basename(name)}.blk_{i}")

            if not os.path.exists(blk):
                os.makedirs(enc, exist_ok=True)
                with open(blk, "wb") as f:
                    f.write(new_shards[i])
                with open(os.path.join(enc, f"{os.path.basename(name)}.meta.json"), "w", encoding="utf-8") as mf:
                    json.dump(meta_j, mf, ensure_ascii=False)
                fixed += 1

    return jsonify({"success": True, "fixed": fixed})


# ==================== EC导入文件 ====================
@ec_bp.route('/api/volume/import', methods=['POST'])
@permission_required('fullcontrol')
def ec_import():
    """导入文件到EC卷"""
    load_json = _ctx['load_json']
    save_json = _ctx['save_json']
    rs_encode = _ctx['rs_encode']

    payload = request.get_json(force=True)
    sources = payload.get("sources") or []
    delete_src = bool(payload.get("delete_source", False))

    cfg = load_json(_ctx['EC_CFG_PATH'], {})
    if not cfg or cfg.get("scheme") != "rs":
        return jsonify({"error": "未配置RS纠删码"}), 400

    k, m, disks = cfg["k"], cfg["m"], cfg["disks"]
    if len(disks) < k + m:
        return jsonify({"error": f"磁盘数量不足（需要≥{k+m}）"}), 400

    imported, skipped, failed = [], [], []
    idx = load_json(_ctx['EC_IDX_PATH'], {"files": {}})

    def _import_one(file_abs: str, logical_rel: str):
        try:
            with open(file_abs, "rb") as f:
                data = f.read()
            shards = rs_encode(data, k, m)
            shard_size = len(shards[0]) if shards else 0
            meta = {
                "k": k, "m": m,
                "shard_size": shard_size,
                "original_size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            # 写分片
            for i, disk in enumerate(disks[:k + m]):
                enc_dir = os.path.join(disk, "encoded", os.path.dirname(logical_rel))
                os.makedirs(enc_dir, exist_ok=True)
                base = os.path.basename(logical_rel)
                with open(os.path.join(enc_dir, f"{base}.blk_{i}"), "wb") as wf:
                    wf.write(shards[i])
                with open(os.path.join(enc_dir, f"{base}.meta.json"), "w", encoding="utf-8") as mf:
                    json.dump(meta, mf, ensure_ascii=False)
            # 更新索引
            idx["files"][logical_rel.replace("\\", "/")] = {
                "size": len(data), "k": k, "m": m, "sha256": meta["sha256"],
                "disks": disks, "ctime": int(time.time())
            }
            imported.append(logical_rel)
            if delete_src:
                try:
                    os.remove(file_abs)
                except Exception:
                    pass
        except Exception as e:
            failed.append({"path": file_abs, "error": str(e)})

    for src in sources:
        src = os.path.abspath(src)
        if not os.path.exists(src):
            failed.append({"path": src, "error": "不存在"})
            continue
        if os.path.isdir(src):
            root = src
            for root_dir, _, files in os.walk(root):
                for fn in files:
                    absf = os.path.join(root_dir, fn)
                    rel = os.path.relpath(absf, root)
                    _import_one(absf, rel)
            if delete_src:
                try:
                    os.removedirs(root)
                except Exception:
                    pass
        else:
            _import_one(src, os.path.basename(src))

    save_json(_ctx['EC_IDX_PATH'], idx)
    return jsonify({"success": True, "imported": imported, "failed": failed, "skipped": skipped})

@ec_bp.route('/api/encode', methods=['POST'])
@permission_required('fullcontrol')
def api_encode():
    """
    兼容旧接口：接受 {scheme,k,m,disks,file_path}，
    用系统码RS编码并写入各盘 encoded/，同时更新 ec_index.json。
    file_path 相对 BASE_DIRS[0]。
    """
    data = request.get_json(force=True)
    scheme = (data.get('scheme') or 'rs').lower()
    k = int(data.get('k') or 0)
    m = int(data.get('m') or 0)
    disks = [os.path.abspath(d) for d in (data.get('disks') or [])]
    rel = (data.get('file_path') or '').lstrip('/\\')
    src = os.path.abspath(os.path.join(BASE_DIRS[0], rel))

    if scheme != 'rs':
        return jsonify({'error': "仅支持 scheme='rs'"}), 400
    if k <= 0 or m <= 0:
        return jsonify({'error': 'k 和 m 必须为正整数'}), 400
    if len(disks) < k + m:
        return jsonify({'error': f'磁盘数量不足（需要≥{k+m}）'}), 400
    if not os.path.exists(src) or not os.path.isfile(src):
        return jsonify({'error': '源文件不存在'}), 404

    try:
        with open(src, 'rb') as f:
            data_bytes = f.read()
        shards = _ctx['rs_encode'](data_bytes, k, m)
        shard_size = len(shards[0]) if shards else 0
        file_sha = hashlib.sha256(data_bytes).hexdigest()
        logical_name = os.path.basename(src)

        meta = {
            'k': k, 'm': m,
            'shard_size': shard_size,
            'original_size': len(data_bytes),
            'sha256': file_sha
        }

        # 写分片 + meta（等长分片风格，与 /api/upload 保持一致）
        for i, disk in enumerate(disks[:k + m]):
            enc_dir = os.path.join(disk, 'encoded')
            os.makedirs(enc_dir, exist_ok=True)
            with open(os.path.join(enc_dir, f'{logical_name}.blk_{i}'), 'wb') as wf:
                wf.write(shards[i])
            with open(os.path.join(enc_dir, f'{logical_name}.meta.json'), 'w', encoding='utf-8') as mf:
                json.dump(meta, mf, ensure_ascii=False)

        # 更新索引
        idx = _ctx['load_json'](_ctx['EC_IDX_PATH'], {'files': {}})
        idx['files'][logical_name] = {
            'size': len(data_bytes), 'k': k, 'm': m, 'sha256': file_sha,
            'disks': disks, 'ctime': int(time.time())
        }
        _ctx['save_json'](_ctx['EC_IDX_PATH'], idx)

        return jsonify({'success': True, 'message': '编码成功（系统码RS）', 'name': logical_name})

    except Exception as e:
        return jsonify({'error': f'内部错误: {e}'}), 500

def _capacity_estimate(disks, k):
    """估算EC卷可用容量"""
    import shutil
    min_free = float('inf')
    for disk in disks:
        if os.path.exists(disk):
            usage = shutil.disk_usage(disk)
            if usage.free < min_free:
                min_free = usage.free
    if min_free == float('inf'):
        min_free = 0
    usable = min_free * k
    return {
        "min_disk_free": min_free,
        "usable_capacity": usable,
        "k": k
    }

# [新增] EC容量预估接口
@ec_bp.route('/api/ec_estimate', methods=['POST'])
@permission_required('fullcontrol')
def api_ec_estimate():
    """根据传入的k值和磁盘列表，实时估算可用容量"""
    data = request.get_json()
    k = int(data.get("k", 0))
    disks = data.get("disks", [])

    if k <= 0 or not disks:
        return jsonify({"error": "缺少 k 或 disks 参数"}), 400

    try:
        # 复用已有的 _capacity_estimate 帮助函数
        estimate = _capacity_estimate(disks, k)
        return jsonify(estimate)
    except Exception as e:
        return jsonify({"error": f"计算容量失败: {str(e)}"}), 500

