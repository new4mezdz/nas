#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
存储池高级测试脚本
包含：策略对比、性能测试、并发测试、压力测试
"""

import os
import sys
import time
import random
import string
import shutil
import threading
import concurrent.futures
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass, field
from datetime import datetime

# sys.path.insert(0, r'F:\python\nas\backend')  # 根据实际路径修改

import Storage_pool


# ==================== 数据类 ====================

@dataclass
class TestResult:
    """测试结果"""
    name: str
    success: bool
    duration: float  # 秒
    files_count: int = 0
    total_size: int = 0
    throughput: float = 0  # MB/s
    errors: List[str] = field(default_factory=list)
    details: Dict = field(default_factory=dict)


@dataclass
class FileInfo:
    """文件信息"""
    filename: str
    size: int
    disk: str = ""
    upload_time: float = 0
    success: bool = True
    error: str = ""


# ==================== 工具函数 ====================

def format_bytes(size: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


def format_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.1f} ms"
    elif seconds < 60:
        return f"{seconds:.2f} s"
    else:
        return f"{seconds / 60:.1f} min"


def generate_data(size: int) -> bytes:
    return os.urandom(size)


def generate_filename(prefix: str = "test") -> str:
    chars = string.ascii_lowercase + string.digits
    name = ''.join(random.choice(chars) for _ in range(8))
    return f"{prefix}_{name}.bin"


def log(msg: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    symbols = {"INFO": "ℹ️", "OK": "✅", "WARN": "⚠️", "ERROR": "❌", "TEST": "🧪"}
    print(f"[{timestamp}] {symbols.get(level, '•')} {msg}")


# ==================== 测试类 ====================

class StoragePoolTester:
    """存储池测试器"""

    def __init__(self):
        self.results: List[TestResult] = []
        self.test_volumes: List[str] = []

    def setup(self) -> bool:
        """测试前准备"""
        log("检查存储池状态...", "INFO")
        try:
            status = Storage_pool.get_pool_status()
            if not status.get("is_configured"):
                log("存储池未配置！", "ERROR")
                return False

            disks = status.get("disks", [])
            log(f"存储池已就绪，共 {len(disks)} 个磁盘", "OK")
            for d in disks:
                log(f"  {d['disk']}: {format_bytes(d['free'])} 可用", "INFO")
            return True
        except Exception as e:
            log(f"检查失败: {e}", "ERROR")
            return False

    def cleanup(self):
        """清理测试数据"""
        log("清理测试卷...", "INFO")
        for vol in self.test_volumes:
            try:
                Storage_pool.delete_volume(vol, confirm=True)
                log(f"  删除: {vol}", "OK")
            except Exception as e:
                log(f"  删除失败 {vol}: {e}", "WARN")
        self.test_volumes.clear()

    def create_test_volume(self, strategy: str, name_suffix: str = "") -> str:
        """创建测试卷"""
        vol_name = f"test_{strategy}_{name_suffix}_{int(time.time())}"
        try:
            Storage_pool.create_volume(
                name=vol_name,
                display_name=f"Test-{strategy}",
                icon="🧪",
                strategy=strategy
            )
            self.test_volumes.append(vol_name)
            return vol_name
        except Exception as e:
            log(f"创建卷失败: {e}", "ERROR")
            return None

    # ==================== 基础策略测试 ====================

    def test_strategy_distribution(self, strategy: str, file_count: int = 20,
                                   file_size: int = 1024 * 100) -> TestResult:
        """测试策略的文件分配分布"""
        log(f"测试策略分布: {strategy}", "TEST")

        result = TestResult(
            name=f"distribution_{strategy}",
            success=False,
            duration=0,
            files_count=file_count
        )

        vol_name = self.create_test_volume(strategy, "dist")
        if not vol_name:
            result.errors.append("创建卷失败")
            return result

        start_time = time.time()
        files: List[FileInfo] = []
        disk_counts: Dict[str, int] = {}

        try:
            for i in range(file_count):
                filename = generate_filename(f"dist{i:03d}")
                data = generate_data(file_size)

                t0 = time.time()
                res = Storage_pool.add_file(vol_name, "", filename, data)
                t1 = time.time()

                disk = res.get("disk", "unknown")
                disk_counts[disk] = disk_counts.get(disk, 0) + 1

                files.append(FileInfo(
                    filename=filename,
                    size=file_size,
                    disk=disk,
                    upload_time=t1 - t0
                ))

            result.success = True
            result.duration = time.time() - start_time
            result.total_size = file_count * file_size
            result.throughput = (result.total_size / 1024 / 1024) / result.duration
            result.details = {
                "disk_distribution": disk_counts,
                "files": [{"name": f.filename, "disk": f.disk} for f in files[:5]]  # 只保留前5个
            }

            log(f"  完成! 耗时 {format_duration(result.duration)}", "OK")
            log(f"  分布: {disk_counts}", "INFO")

        except Exception as e:
            result.errors.append(str(e))
            log(f"  失败: {e}", "ERROR")

        self.results.append(result)
        return result

    # ==================== 性能测试 ====================

    def test_upload_performance(self, file_sizes: List[int] = None) -> TestResult:
        """测试不同文件大小的上传性能"""
        if file_sizes is None:
            file_sizes = [
                1024,  # 1 KB
                1024 * 10,  # 10 KB
                1024 * 100,  # 100 KB
                1024 * 1024,  # 1 MB
                1024 * 1024 * 5  # 5 MB
            ]

        log("测试上传性能...", "TEST")

        result = TestResult(
            name="upload_performance",
            success=False,
            duration=0
        )

        vol_name = self.create_test_volume("round_robin", "perf")
        if not vol_name:
            result.errors.append("创建卷失败")
            return result

        start_time = time.time()
        perf_data = []

        try:
            for size in file_sizes:
                times = []
                for i in range(3):  # 每个大小测3次
                    filename = generate_filename(f"perf_{size}")
                    data = generate_data(size)

                    t0 = time.time()
                    Storage_pool.add_file(vol_name, "", filename, data)
                    t1 = time.time()

                    times.append(t1 - t0)

                avg_time = sum(times) / len(times)
                throughput = (size / 1024 / 1024) / avg_time if avg_time > 0 else 0

                perf_data.append({
                    "size": size,
                    "size_str": format_bytes(size),
                    "avg_time": avg_time,
                    "throughput_mbps": throughput
                })

                log(f"  {format_bytes(size):>10}: {format_duration(avg_time)} ({throughput:.2f} MB/s)", "INFO")

            result.success = True
            result.duration = time.time() - start_time
            result.details["performance"] = perf_data

        except Exception as e:
            result.errors.append(str(e))
            log(f"  失败: {e}", "ERROR")

        self.results.append(result)
        return result

    # ==================== 并发测试 ====================

    def test_concurrent_upload(self, workers: int = 4, files_per_worker: int = 5,
                               file_size: int = 1024 * 50) -> TestResult:
        """测试并发上传"""
        log(f"测试并发上传: {workers} 线程, 每线程 {files_per_worker} 文件", "TEST")

        result = TestResult(
            name="concurrent_upload",
            success=False,
            duration=0,
            files_count=workers * files_per_worker
        )

        vol_name = self.create_test_volume("round_robin", "conc")
        if not vol_name:
            result.errors.append("创建卷失败")
            return result

        results_lock = threading.Lock()
        upload_results: List[FileInfo] = []
        errors: List[str] = []

        def worker_upload(worker_id: int):
            for i in range(files_per_worker):
                filename = generate_filename(f"w{worker_id}_f{i}")
                data = generate_data(file_size)

                try:
                    t0 = time.time()
                    res = Storage_pool.add_file(vol_name, "", filename, data)
                    t1 = time.time()

                    with results_lock:
                        upload_results.append(FileInfo(
                            filename=filename,
                            size=file_size,
                            disk=res.get("disk", ""),
                            upload_time=t1 - t0
                        ))
                except Exception as e:
                    with results_lock:
                        errors.append(f"Worker {worker_id}: {e}")

        start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(worker_upload, i) for i in range(workers)]
            concurrent.futures.wait(futures)

        result.duration = time.time() - start_time
        result.files_count = len(upload_results)
        result.total_size = sum(f.size for f in upload_results)
        result.throughput = (result.total_size / 1024 / 1024) / result.duration if result.duration > 0 else 0
        result.errors = errors
        result.success = len(errors) == 0

        # 统计分布
        disk_counts = {}
        for f in upload_results:
            disk_counts[f.disk] = disk_counts.get(f.disk, 0) + 1

        result.details = {
            "workers": workers,
            "files_per_worker": files_per_worker,
            "disk_distribution": disk_counts,
            "avg_upload_time": sum(f.upload_time for f in upload_results) / len(upload_results) if upload_results else 0
        }

        log(f"  完成! {len(upload_results)} 文件, 耗时 {format_duration(result.duration)}", "OK")
        log(f"  吞吐量: {result.throughput:.2f} MB/s", "INFO")
        log(f"  分布: {disk_counts}", "INFO")
        if errors:
            log(f"  错误: {len(errors)} 个", "WARN")

        self.results.append(result)
        return result

    # ==================== 压力测试 ====================

    def test_stress(self, duration_seconds: int = 30, file_size: int = 1024 * 10) -> TestResult:
        """压力测试：持续上传指定时间"""
        log(f"压力测试: 持续 {duration_seconds} 秒", "TEST")

        result = TestResult(
            name="stress_test",
            success=False,
            duration=duration_seconds
        )

        vol_name = self.create_test_volume("round_robin", "stress")
        if not vol_name:
            result.errors.append("创建卷失败")
            return result

        start_time = time.time()
        end_time = start_time + duration_seconds
        files_uploaded = 0
        total_bytes = 0
        errors = []

        try:
            while time.time() < end_time:
                filename = generate_filename(f"stress{files_uploaded}")
                data = generate_data(file_size)

                try:
                    Storage_pool.add_file(vol_name, "", filename, data)
                    files_uploaded += 1
                    total_bytes += file_size
                except Exception as e:
                    errors.append(str(e))

                # 每秒打印进度
                if files_uploaded % 50 == 0:
                    elapsed = time.time() - start_time
                    rate = files_uploaded / elapsed
                    log(f"  进度: {files_uploaded} 文件, {rate:.1f} 文件/秒", "INFO")

            actual_duration = time.time() - start_time
            result.success = True
            result.duration = actual_duration
            result.files_count = files_uploaded
            result.total_size = total_bytes
            result.throughput = (total_bytes / 1024 / 1024) / actual_duration
            result.errors = errors
            result.details = {
                "files_per_second": files_uploaded / actual_duration,
                "error_count": len(errors)
            }

            log(f"  完成! {files_uploaded} 文件, {result.throughput:.2f} MB/s", "OK")

        except Exception as e:
            result.errors.append(str(e))
            log(f"  失败: {e}", "ERROR")

        self.results.append(result)
        return result

    # ==================== 完整测试套件 ====================

    def run_full_test(self):
        """运行完整测试套件"""
        print("\n" + "=" * 60)
        print("       存储池完整测试套件")
        print("=" * 60 + "\n")

        if not self.setup():
            return

        try:
            # 1. 策略分布测试
            print("\n" + "-" * 40)
            print("【1/4】策略分布测试")
            print("-" * 40)
            for strategy in ["largest_free", "round_robin", "balanced"]:
                self.test_strategy_distribution(strategy, file_count=15, file_size=1024 * 50)

            # 2. 性能测试
            print("\n" + "-" * 40)
            print("【2/4】上传性能测试")
            print("-" * 40)
            self.test_upload_performance()

            # 3. 并发测试
            print("\n" + "-" * 40)
            print("【3/4】并发上传测试")
            print("-" * 40)
            self.test_concurrent_upload(workers=4, files_per_worker=10)

            # 4. 压力测试（短时）
            print("\n" + "-" * 40)
            print("【4/4】压力测试 (10秒)")
            print("-" * 40)
            self.test_stress(duration_seconds=10)

        finally:
            # 清理
            print("\n" + "-" * 40)
            print("清理测试数据")
            print("-" * 40)
            self.cleanup()

        # 打印报告
        self.print_report()

    def print_report(self):
        """打印测试报告"""
        print("\n" + "=" * 60)
        print("       测试报告")
        print("=" * 60)

        for r in self.results:
            status = "✅ PASS" if r.success else "❌ FAIL"
            print(f"\n📊 {r.name}")
            print(f"   状态: {status}")
            print(f"   耗时: {format_duration(r.duration)}")
            if r.files_count:
                print(f"   文件: {r.files_count} 个")
            if r.total_size:
                print(f"   数据: {format_bytes(r.total_size)}")
            if r.throughput:
                print(f"   吞吐: {r.throughput:.2f} MB/s")
            if r.errors:
                print(f"   错误: {len(r.errors)} 个")
            if "disk_distribution" in r.details:
                print(f"   分布: {r.details['disk_distribution']}")

        # 汇总
        total = len(self.results)
        passed = sum(1 for r in self.results if r.success)
        print("\n" + "-" * 40)
        print(f"总计: {passed}/{total} 测试通过")
        print("=" * 60 + "\n")


# ==================== 快速测试函数 ====================

def quick_test():
    """快速测试（仅测试基本功能）"""
    tester = StoragePoolTester()
    if not tester.setup():
        return

    try:
        tester.test_strategy_distribution("round_robin", file_count=5)
    finally:
        tester.cleanup()

    tester.print_report()


def benchmark():
    """性能基准测试"""
    tester = StoragePoolTester()
    if not tester.setup():
        return

    try:
        tester.test_upload_performance()
        tester.test_concurrent_upload(workers=4, files_per_worker=10)
    finally:
        tester.cleanup()

    tester.print_report()


# ==================== 主程序 ====================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="存储池高级测试工具")
    parser.add_argument("--full", action="store_true", help="运行完整测试套件")
    parser.add_argument("--quick", action="store_true", help="快速测试")
    parser.add_argument("--benchmark", action="store_true", help="性能基准测试")
    parser.add_argument("--stress", type=int, metavar="SECONDS", help="压力测试(指定秒数)")
    parser.add_argument("--concurrent", type=int, default=4, help="并发测试线程数")

    args = parser.parse_args()

    if args.full:
        tester = StoragePoolTester()
        tester.run_full_test()
    elif args.quick:
        quick_test()
    elif args.benchmark:
        benchmark()
    elif args.stress:
        tester = StoragePoolTester()
        if tester.setup():
            try:
                tester.test_stress(duration_seconds=args.stress)
            finally:
                tester.cleanup()
            tester.print_report()
    else:
        print("存储池高级测试工具")
        print("\n用法:")
        print("  python test_storage_advanced.py --full       # 完整测试")
        print("  python test_storage_advanced.py --quick      # 快速测试")
        print("  python test_storage_advanced.py --benchmark  # 性能测试")
        print("  python test_storage_advanced.py --stress 60  # 压力测试60秒")
        print("\n运行快速测试...")
        quick_test()