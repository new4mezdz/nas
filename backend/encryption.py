# backend/encryption.py (V2 - Per-Disk Encryption)

import os
import json
import hashlib
from utils import _norm_abs
import os, hashlib, json
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


# ===== 异常类 =====
class EncryptionError(Exception):
    pass


class NotUnlockedError(EncryptionError):
    pass


class DecryptionError(EncryptionError):
    pass


# ===== 全局加密函数 =====
def xor_cipher(data: bytes, key: bytes) -> bytes:
    """XOR 加密/解密(对称操作)"""
    key_len = len(key)
    if key_len == 0:
        return data
    data_array = bytearray(data)
    for i in range(len(data_array)):
        data_array[i] ^= key[i % key_len]
    return bytes(data_array)


# ===== 加密管理器类 =====
class EncryptionManager:

    # ===== 1. 初始化方法(必须在最前面) =====
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.disk_configs = {}  # 存储每个盘的盐和哈希
        self.unlocked_keys = {}  # 存储已解锁的盘及其内存中的密钥
        self.load_config()

    # ===== 2. 工具方法 =====
    def _load_json(self, path: str, default):
        """加载 JSON 配置文件"""
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return default

    def _save_config(self):
        """保存配置到文件"""
        try:
            config = {"disks": self.disk_configs}
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ 保存加密配置失败: {e}")

    def load_config(self):
        """加载每个磁盘的加密配置"""
        config = self._load_json(self.config_path, {})
        self.disk_configs = config.get("disks", {})
        print(f"🔒 加密管理器已加载,受保护的驱动器: {list(self.disk_configs.keys()) or '无'}")

    # ===== 3. 磁盘级加密方法 =====
    def get_disk_status(self):
        """获取所有已配置磁盘及其锁定状态"""
        status = {}
        for drive_path in self.disk_configs.keys():
            status[drive_path] = {
                "is_configured": True,
                "is_unlocked": drive_path in self.unlocked_keys
            }
        return status

    def is_path_encrypted(self, file_path: str) -> bool:
        """检查路径是否位于任何一个已配置的加密磁盘上"""
        norm_path = _norm_abs(file_path)
        for drive in self.disk_configs.keys():
            if norm_path.startswith(drive):
                return True
        return False

    def _get_drive_for_path(self, file_path: str) -> str | None:
        """根据文件路径找到它所属的加密盘符"""
        norm_path = _norm_abs(file_path)
        for drive in self.disk_configs.keys():
            if norm_path.startswith(drive):
                return drive
        return None

    def unlock(self, drive_path: str, password: str) -> bool:
        """使用密码解锁单个磁盘"""
        norm_drive = _norm_abs(drive_path)
        config = self.disk_configs.get(norm_drive)
        if not config:
            return False  # 该盘未配置加密

        salt = bytes.fromhex(config.get("password_salt", ''))
        stored_hash = bytes.fromhex(config.get("password_hash", ''))

        # 验证密码
        new_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        if new_hash == stored_hash:
            # 派生密钥并存入内存
            self.unlocked_keys[norm_drive] = hashlib.pbkdf2_hmac(
                'sha256', password.encode('utf-8'), salt, 100000, dklen=32
            )
            print(f"🔓 磁盘 {norm_drive} 已解锁。")
            return True
        print(f"🔑 磁盘 {norm_drive} 的解锁密码错误。")
        return False

    def lock(self, drive_path: str):
        """锁定单个磁盘"""
        norm_drive = _norm_abs(drive_path)
        if norm_drive in self.unlocked_keys:
            del self.unlocked_keys[norm_drive]
            print(f"🔒 磁盘 {norm_drive} 已锁定。")

    def read_encrypted_file(self, file_path: str) -> bytes:
        """读取并解密文件"""
        drive = self._get_drive_for_path(file_path)
        if not drive:
            raise EncryptionError("文件不位于加密盘上")

        key = self.unlocked_keys.get(drive)
        if not key:
            raise NotUnlockedError(f"磁盘 {drive} 已锁定,无法读取。")

        with open(file_path, "rb") as f:
            encrypted_data = f.read()
        return xor_cipher(encrypted_data, key)

    def write_encrypted_file(self, file_path: str, data: bytes):
        """加密并写入文件"""
        drive = self._get_drive_for_path(file_path)
        if not drive:
            raise EncryptionError("文件不位于加密盘上")

        key = self.unlocked_keys.get(drive)
        if not key:
            raise NotUnlockedError(f"磁盘 {drive} 已锁定,无法写入。")

        encrypted_data = xor_cipher(data, key)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(encrypted_data)

    # ===== 4. 独立文件加密方法(不依赖磁盘配置) =====
    def encrypt_file_standalone(self, file_path: str, password: str) -> bool:
        """
        对单个文件进行独立加密(使用 XOR)
        加密后文件名添加 .encrypted 后缀
        """
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"文件不存在: {file_path}")

            if file_path.endswith('.encrypted'):
                raise ValueError("文件已加密")

            # 生成加密密钥
            salt = os.urandom(16)
            key_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000, dklen=32)

            # 读取原文件
            with open(file_path, 'rb') as f:
                plaintext = f.read()

            # 使用全局函数 xor_cipher
            encrypted_data = xor_cipher(plaintext, key_hash)

            # 写入加密文件(添加 .encrypted 后缀)
            encrypted_path = file_path + '.encrypted'
            with open(encrypted_path, 'wb') as f:
                f.write(salt)  # 前16字节是salt
                f.write(encrypted_data)  # 后面是加密数据

            # 删除原文件
            os.remove(file_path)

            print(f"✅ 文件加密成功: {file_path} -> {encrypted_path}")
            return True

        except Exception as e:
            print(f"❌ 文件加密失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def decrypt_file_standalone(self, encrypted_path: str, password: str) -> bool:
        """
        解密单个加密文件(使用 XOR)
        解密后移除 .encrypted 后缀
        """
        try:
            if not os.path.exists(encrypted_path):
                raise FileNotFoundError(f"文件不存在: {encrypted_path}")

            if not encrypted_path.endswith('.encrypted'):
                raise ValueError("文件未加密")

            # 读取加密文件
            with open(encrypted_path, 'rb') as f:
                salt = f.read(16)  # 前16字节是salt
                encrypted_data = f.read()  # 剩余是加密数据

            # 生成解密密钥
            key_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000, dklen=32)

            # 使用全局函数 xor_cipher
            plaintext = xor_cipher(encrypted_data, key_hash)

            # 写入解密文件(移除 .encrypted 后缀)
            decrypted_path = encrypted_path[:-10]  # 移除 '.encrypted'
            with open(decrypted_path, 'wb') as f:
                f.write(plaintext)

            # 删除加密文件
            os.remove(encrypted_path)

            print(f"✅ 文件解密成功: {encrypted_path} -> {decrypted_path}")
            return True

        except Exception as e:
            print(f"❌ 文件解密失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def encrypt_folder_standalone(self, folder_path: str, password: str) -> dict:
        """
        递归加密整个文件夹
        返回 {'success': int, 'failed': int, 'errors': []}
        """
        results = {'success': 0, 'failed': 0, 'errors': []}

        try:
            for root, dirs, files in os.walk(folder_path):
                for filename in files:
                    if filename.endswith('.encrypted'):
                        continue  # 跳过已加密文件

                    file_path = os.path.join(root, filename)
                    try:
                        if self.encrypt_file_standalone(file_path, password):
                            results['success'] += 1
                        else:
                            results['failed'] += 1
                            results['errors'].append(f"加密失败: {filename}")
                    except Exception as e:
                        results['failed'] += 1
                        results['errors'].append(f"{filename}: {str(e)}")

            return results

        except Exception as e:
            results['errors'].append(f"遍历文件夹失败: {str(e)}")
            return results

    def decrypt_folder_standalone(self, folder_path: str, password: str) -> dict:
        """
        递归解密整个文件夹
        返回 {'success': int, 'failed': int, 'errors': []}
        """
        results = {'success': 0, 'failed': 0, 'errors': []}

        try:
            for root, dirs, files in os.walk(folder_path):
                for filename in files:
                    if not filename.endswith('.encrypted'):
                        continue  # 跳过非加密文件

                    file_path = os.path.join(root, filename)
                    try:
                        if self.decrypt_file_standalone(file_path, password):
                            results['success'] += 1
                        else:
                            results['failed'] += 1
                            results['errors'].append(f"解密失败: {filename}")
                    except Exception as e:
                        results['failed'] += 1
                        results['errors'].append(f"{filename}: {str(e)}")

            return results

        except Exception as e:
            results['errors'].append(f"遍历文件夹失败: {str(e)}")
            return results

    # ===== 5. 磁盘加密(供管理端调用) =====
    def encrypt_drive(self, drive_path: str, password: str, status_callback=None) -> dict:
        """
        为磁盘启用加密(供管理端调用的包装方法)

        Args:
            drive_path: 磁盘路径,如 'D:\\'
            password: 用户密码(字符串)
            status_callback: 进度回调函数

        Returns:
            dict: {"success": bool, "message": str, "details": {...}}
        """
        try:
            norm_drive = _norm_abs(drive_path)

            # 1. 检查是否已经配置过加密
            if norm_drive in self.disk_configs:
                return {
                    "success": False,
                    "error": f"磁盘 {norm_drive} 已启用加密"
                }

            # 2. 生成盐和哈希
            salt = os.urandom(32)
            key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000, dklen=32)
            password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)

            # 3. 保存配置
            self.disk_configs[norm_drive] = {
                "password_salt": salt.hex(),
                "password_hash": password_hash.hex()
            }
            self._save_config()
            # ✅ 重新加载配置,确保内存和文件同步
            self.load_config()
            print(f"✅ 已为磁盘 {norm_drive} 配置加密")

            # 4. 解锁磁盘(将密钥存入内存)
            self.unlocked_keys[norm_drive] = key

            # 5. 执行加密
            result = self.encrypt_disk_permanently(norm_drive, key, status_callback)

            return {
                "success": True,
                "message": f"磁盘 {norm_drive} 加密完成",
                "details": {
                    "total": result.get("processed_files", 0),
                    "success": result.get("processed_files", 0),
                    "failed": len(result.get("failed_files", []))
                }
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"加密失败: {str(e)}"
            }

    def encrypt_disk_permanently(self, drive_path: str, key: bytes, status_callback=None) -> dict:
        """
        永久加密一个磁盘上的所有明文文件。
        (✅ 新增 status_callback 参数用于报告进度)
        """
        norm_drive = _norm_abs(drive_path)
        if not key:
            raise EncryptionError("必须提供有效的加密密钥")

        if status_callback:
            status_callback(norm_drive, f"🚀 磁盘 {norm_drive}：开始加密...", 0)

        processed_files = 0
        failed_files = []
        total_files_to_scan = 0  # 粗略估计

        # 为了提供粗略的百分比，我们先快速统计一下文件总数
        # (这会消耗一些时间，但对于进度条是必要的)
        try:
            for root, dirs, files in os.walk(norm_drive):
                dirs[:] = [d for d in dirs if
                           not d.startswith('.') and d not in ('node_modules', '__pycache__', '$RECYCLE.BIN')]
                total_files_to_scan += len([f for f in files if not f.endswith('.encrypted')])
            if status_callback:
                status_callback(norm_drive, f"🚀 磁盘 {norm_drive}：扫描到 {total_files_to_scan} 个文件，开始加密...",
                                0)
        except Exception as e:
            print(f"扫描文件总数失败: {e}")
            total_files_to_scan = 0  # 如果扫描失败，则不显示百分比

        # 2. 遍历磁盘上的所有文件
        for root, dirs, files in os.walk(norm_drive):
            dirs[:] = [d for d in dirs if
                       not d.startswith('.') and d not in ('node_modules', '__pycache__', '$RECYCLE.BIN')]

            for filename in files:
                if filename.endswith('.encrypted'):
                    continue

                file_path = os.path.join(root, filename)

                try:
                    with open(file_path, "rb") as f:
                        plaintext_data = f.read()
                    if not plaintext_data:
                        continue

                    encrypted_data = xor_cipher(plaintext_data, key)

                    with open(file_path, "wb") as f:
                        f.write(encrypted_data)

                    processed_files += 1

                    # 报告进度
                    if status_callback and processed_files % 20 == 0:  # 每处理20个文件报告一次
                        percent = (processed_files / total_files_to_scan * 100) if total_files_to_scan > 0 else 0
                        status_callback(norm_drive,
                                        f"🔄 磁盘 {norm_drive}：正在加密... ({processed_files} / {total_files_to_scan})",
                                        percent)

                except Exception as e:
                    print(f"  ❌ 加密失败: {file_path}, 错误: {e}")
                    failed_files.append({"path": file_path, "error": str(e)})

        if status_callback:
            status_callback(norm_drive, f"✅ 磁盘 {norm_drive}：加密完成。共处理 {processed_files} 个文件", 100)

        print(f"✅ 磁盘 {norm_drive} 加密完成。")
        return {
            "processed_files": processed_files,
            "failed_files": failed_files
        }

    # ===== 6. 永久解密磁盘 =====
    def decrypt_disk_permanently(self, drive_path: str, password: str, status_callback=None) -> dict:
        """
        永久解密一个磁盘上的所有文件。
        (✅ 新增 status_callback 参数用于报告进度)
        """
        norm_drive = _norm_abs(drive_path)

        # 1. 验证密码并获取密钥
        if not self.unlock(norm_drive, password):
            self.lock(norm_drive)  # 确保锁上
            if status_callback:
                status_callback(norm_drive, f"❌ 磁盘 {norm_drive}：密码错误", -1)
            raise ValueError("密码错误")

        key = self.unlocked_keys.get(norm_drive)
        if not key:
            if status_callback:
                status_callback(norm_drive, f"❌ 磁盘 {norm_drive}：无法获取密钥", -1)
            raise EncryptionError("无法获取密钥,即使密码正确")

        if status_callback:
            status_callback(norm_drive, f"🚀 磁盘 {norm_drive}：开始解密...", 0)

        processed_files = 0
        failed_files = []
        total_files_to_scan = 0

        # 同样，先扫描总文件数
        try:
            for root, dirs, files in os.walk(norm_drive):
                dirs[:] = [d for d in dirs if
                           not d.startswith('.') and d not in ('node_modules', '__pycache__', '$RECYCLE.BIN')]
                total_files_to_scan += len([f for f in files if not f.endswith('.encrypted')])
            if status_callback:
                status_callback(norm_drive, f"🚀 磁盘 {norm_drive}：扫描到 {total_files_to_scan} 个文件，开始解密...",
                                0)
        except Exception as e:
            print(f"扫描文件总数失败: {e}")
            total_files_to_scan = 0

        # 2. 遍历磁盘上的所有文件
        for root, dirs, files in os.walk(norm_drive):
            dirs[:] = [d for d in dirs if
                       not d.startswith('.') and d not in ('node_modules', '__pycache__', '$RECYCLE.BIN')]

            for filename in files:
                if filename.endswith('.encrypted'):
                    continue

                file_path = os.path.join(root, filename)
                try:
                    with open(file_path, "rb") as f:
                        encrypted_data = f.read()

                    decrypted_data = xor_cipher(encrypted_data, key)

                    with open(file_path, "wb") as f:
                        f.write(decrypted_data)

                    processed_files += 1

                    # 报告进度
                    if status_callback and processed_files % 20 == 0:
                        percent = (processed_files / total_files_to_scan * 100) if total_files_to_scan > 0 else 0
                        status_callback(norm_drive,
                                        f"🔄 磁盘 {norm_drive}：正在解密... ({processed_files} / {total_files_to_scan})",
                                        percent)

                except Exception as e:
                    print(f"  ❌ 解密失败: {file_path}, 错误: {e}")
                    failed_files.append(file_path)

        # 3. 操作完成后,立即将密钥从内存中移除
        self.lock(norm_drive)

        # 4. ✅ 删除加密配置(完全移除加密)
        if norm_drive in self.disk_configs:
            del self.disk_configs[norm_drive]
            self._save_config()
            print(f"🗑️  已删除磁盘 {norm_drive} 的加密配置")
            # ✅ 重新加载配置,确保内存和文件同步
            self.load_config()

        if status_callback:
            status_callback(norm_drive, f"✅ 磁盘 {norm_drive}：解密完成。共处理 {processed_files} 个文件", 100)

        print(f"✅ 磁盘 {norm_drive} 解密完成。")
        return {
            "processed_files": processed_files,
            "failed_files": failed_files
        }