#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
存储池策略测试脚本
测试三种存储策略：largest_free, round_robin, balanced
"""

import os
import sys
import time
import random
import string
import shutil
from pathlib import Path
from typing import List, Dict

# 添加项目路径
# sys.path.insert(0, r'F:\python\nas\backend')  # 根据实际路径修改

import Storage_pool

# ==================== 配置 ====================
TEST_FILE_COUNT = 10  # 每个策略测试的文件数量
TEST_FILE_SIZE_MIN = 1024  # 最小文件大小 1KB
TEST_FILE_SIZE_MAX = 1024 * 1024  # 最大文件大小 1MB


# ==================== 工具函数 ====================

def generate_random_data(size: int) -> bytes:
    """生成随机数据"""
    return os.urandom(size)


def generate_random_filename() -> str:
    """生成随机文件名"""
    chars = string.ascii_lowercase + string.digits
    name = ''.join(random.choice(chars) for _ in range(8))
    return f"test_{name}.bin"


def format_bytes(size: int) -> str:
    """格式化字节数"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


def print_separator(title: str = ""):
    """打印分隔线"""
    if title:
        print(f"\n{'=' * 20} {title} {'=' * 20}")
    else:
        print("=" * 50)


# ==================== 测试类 ====================

class StrategyTester:
    def __init__(self):
        self.results = {}

    def check_pool_status(self) -> bool:
        """检查存储池状态"""
        print_separator("检查存储池状态")
        try:
            status = Storage_pool.get_pool_status()
            if not status.get("is_configured"):
                print("❌ 存储池未配置！请先创建存储池。")
                return False

            print(f"✅ 存储池已配置")
            print(f"   池名称: {status.get('pool', {}).get('name', 'N/A')}")
            print(f"   磁盘数: {len(status.get('disks', []))}")

            for disk in status.get("disks", []):
                print(f"   - {disk['disk']}: {format_bytes(disk['free'])} 可用 / {format_bytes(disk['total'])} 总计")

            return True
        except Exception as e:
            print(f"❌ 获取存储池状态失败: {e}")
            return False

    def create_test_volume(self, strategy: str) -> str:
        """创建测试用逻辑卷"""
        volume_name = f"test_{strategy}_{int(time.time())}"
        display_name = f"测试卷-{strategy}"

        try:
            result = Storage_pool.create_volume(
                name=volume_name,
                display_name=display_name,
                icon="🧪",
                strategy=strategy
            )
            print(f"✅ 创建逻辑卷: {volume_name} (策略: {strategy})")
            return volume_name
        except Exception as e:
            print(f"❌ 创建逻辑卷失败: {e}")
            return None

    def delete_test_volume(self, volume_name: str):
        """删除测试逻辑卷"""
        try:
            Storage_pool.delete_volume(volume_name, confirm=True)
            print(f"🗑️  已删除逻辑卷: {volume_name}")
        except Exception as e:
            print(f"⚠️  删除逻辑卷失败: {e}")

    def upload_test_files(self, volume_name: str, count: int) -> List[Dict]:
        """上传测试文件并记录分配情况"""
        files_info = []

        for i in range(count):
            # 生成随机文件
            file_size = random.randint(TEST_FILE_SIZE_MIN, TEST_FILE_SIZE_MAX)
            file_data = generate_random_data(file_size)
            filename = generate_random_filename()

            try:
                result = Storage_pool.add_file(
                    volume_name=volume_name,
                    subpath="",
                    filename=filename,
                    file_data=file_data
                )

                files_info.append({
                    "filename": filename,
                    "size": file_size,
                    "disk": result.get("disk", "unknown"),
                    "success": True
                })

                print(f"   [{i + 1}/{count}] {filename} ({format_bytes(file_size)}) → {result.get('disk', 'unknown')}")

            except Exception as e:
                files_info.append({
                    "filename": filename,
                    "size": file_size,
                    "disk": None,
                    "success": False,
                    "error": str(e)
                })
                print(f"   [{i + 1}/{count}] {filename} ❌ 失败: {e}")

        return files_info

    def analyze_distribution(self, files_info: List[Dict]) -> Dict:
        """分析文件分配情况"""
        disk_stats = {}

        for f in files_info:
            if f["success"] and f["disk"]:
                disk = f["disk"]
                if disk not in disk_stats:
                    disk_stats[disk] = {"count": 0, "total_size": 0}
                disk_stats[disk]["count"] += 1
                disk_stats[disk]["total_size"] += f["size"]

        return disk_stats

    def test_strategy(self, strategy: str) -> Dict:
        """测试单个策略"""
        print_separator(f"测试策略: {strategy}")

        result = {
            "strategy": strategy,
            "volume_name": None,
            "files": [],
            "distribution": {},
            "success": False
        }

        # 1. 创建测试卷
        volume_name = self.create_test_volume(strategy)
        if not volume_name:
            return result

        result["volume_name"] = volume_name

        try:
            # 2. 上传测试文件
            print(f"\n📤 上传 {TEST_FILE_COUNT} 个测试文件...")
            files_info = self.upload_test_files(volume_name, TEST_FILE_COUNT)
            result["files"] = files_info

            # 3. 分析分配情况
            distribution = self.analyze_distribution(files_info)
            result["distribution"] = distribution

            # 4. 打印分析结果
            print(f"\n📊 分配统计:")
            for disk, stats in distribution.items():
                print(f"   {disk}: {stats['count']} 个文件, {format_bytes(stats['total_size'])}")

            result["success"] = True

        except Exception as e:
            print(f"❌ 测试过程出错: {e}")

        finally:
            # 5. 清理：删除测试卷
            print(f"\n🧹 清理测试数据...")
            self.delete_test_volume(volume_name)

        return result

    def run_all_tests(self, cleanup: bool = True):
        """运行所有策略测试"""
        strategies = ["largest_free", "round_robin", "balanced"]

        print_separator("存储策略测试开始")
        print(f"测试配置:")
        print(f"  - 每策略文件数: {TEST_FILE_COUNT}")
        print(f"  - 文件大小范围: {format_bytes(TEST_FILE_SIZE_MIN)} ~ {format_bytes(TEST_FILE_SIZE_MAX)}")

        # 检查存储池
        if not self.check_pool_status():
            return

        # 测试各策略
        for strategy in strategies:
            result = self.test_strategy(strategy)
            self.results[strategy] = result

        # 打印总结报告
        self.print_summary()

    def print_summary(self):
        """打印测试总结"""
        print_separator("测试总结报告")

        for strategy, result in self.results.items():
            print(f"\n📋 策略: {strategy}")
            print(f"   状态: {'✅ 成功' if result['success'] else '❌ 失败'}")

            if result["distribution"]:
                print(f"   磁盘分配:")
                total_files = sum(d["count"] for d in result["distribution"].values())
                for disk, stats in result["distribution"].items():
                    pct = (stats["count"] / total_files * 100) if total_files > 0 else 0
                    print(f"     {disk}: {stats['count']} 文件 ({pct:.1f}%)")

        # 策略对比分析
        print_separator("策略对比分析")

        print("\n🔹 largest_free (最大剩余空间优先):")
        print("   特点: 优先使用剩余空间最大的磁盘")
        print("   适用: 希望充分利用大容量磁盘")
        if "largest_free" in self.results:
            dist = self.results["largest_free"]["distribution"]
            if dist:
                max_disk = max(dist.items(), key=lambda x: x[1]["count"])
                print(f"   结果: 主要分配到 {max_disk[0]} ({max_disk[1]['count']} 文件)")

        print("\n🔹 round_robin (轮询分配):")
        print("   特点: 依次轮流分配到各磁盘")
        print("   适用: 希望文件均匀分布到各磁盘")
        if "round_robin" in self.results:
            dist = self.results["round_robin"]["distribution"]
            if dist:
                counts = [d["count"] for d in dist.values()]
                if counts:
                    variance = max(counts) - min(counts)
                    print(f"   结果: 分配差异 {variance} 个文件 (理想值: 0-1)")

        print("\n🔹 balanced (平衡分配):")
        print("   特点: 考虑磁盘使用率，选择使用率最低的")
        print("   适用: 希望保持各磁盘使用率均衡")
        if "balanced" in self.results:
            dist = self.results["balanced"]["distribution"]
            if dist:
                max_disk = max(dist.items(), key=lambda x: x[1]["count"])
                print(f"   结果: 主要分配到 {max_disk[0]} ({max_disk[1]['count']} 文件)")

        print_separator("测试完成")


# ==================== 单独测试函数 ====================

def test_single_strategy(strategy: str, file_count: int = 5):
    """单独测试某个策略（不删除测试卷，方便检查）"""
    global TEST_FILE_COUNT
    TEST_FILE_COUNT = file_count

    tester = StrategyTester()

    if not tester.check_pool_status():
        return

    result = tester.test_strategy(strategy)

    print("\n💡 提示: 测试卷已删除。如需保留测试数据，请修改代码。")

    return result


def quick_distribution_check():
    """快速检查当前文件分配情况"""
    print_separator("当前文件分配情况")

    try:
        status = Storage_pool.get_pool_status()

        if not status.get("is_configured"):
            print("❌ 存储池未配置")
            return

        config = Storage_pool.load_config()
        files = config.get("files", {})

        # 统计各磁盘文件数
        disk_stats = {}
        for path, info in files.items():
            disk = info.get("disk", "unknown")
            if disk not in disk_stats:
                disk_stats[disk] = {"count": 0, "size": 0}
            disk_stats[disk]["count"] += 1
            disk_stats[disk]["size"] += info.get("size", 0)

        print(f"\n总文件数: {len(files)}")
        print(f"\n各磁盘分配情况:")
        for disk, stats in sorted(disk_stats.items()):
            print(f"  {disk}: {stats['count']} 个文件, {format_bytes(stats['size'])}")

        # 各逻辑卷统计
        volumes = config.get("volumes", {})
        print(f"\n各逻辑卷统计:")
        for vol_name, vol_config in volumes.items():
            vol_files = [f for f in files.keys() if f.startswith(vol_name + "/")]
            print(f"  {vol_name} (策略: {vol_config.get('strategy', 'default')}): {len(vol_files)} 个文件")

    except Exception as e:
        print(f"❌ 检查失败: {e}")


# ==================== 主程序 ====================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="存储池策略测试工具")
    parser.add_argument("--all", action="store_true", help="运行所有策略测试")
    parser.add_argument("--strategy", "-s", choices=["largest_free", "round_robin", "balanced"],
                        help="测试指定策略")
    parser.add_argument("--count", "-n", type=int, default=10, help="测试文件数量")
    parser.add_argument("--check", "-c", action="store_true", help="检查当前分配情况")

    args = parser.parse_args()

    if args.check:
        quick_distribution_check()
    elif args.strategy:
        test_single_strategy(args.strategy, args.count)
    elif args.all:
        TEST_FILE_COUNT = args.count
        tester = StrategyTester()
        tester.run_all_tests()
    else:
        # 默认：运行所有测试
        print("使用方法:")
        print("  python test_storage_strategy.py --all          # 测试所有策略")
        print("  python test_storage_strategy.py -s round_robin # 测试指定策略")
        print("  python test_storage_strategy.py -c             # 检查当前分配")
        print("  python test_storage_strategy.py -n 20 --all    # 每策略测试20个文件")
        print("\n运行默认测试...")
        TEST_FILE_COUNT = 5
        tester = StrategyTester()
        tester.run_all_tests()