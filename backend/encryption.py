# backend/encryption.py (V2 - Per-Disk Encryption)

import os
import json
import hashlib
from utils import _norm_abs


# ... (自定义异常类保持不变) ...
class EncryptionError(Exception): pass


class NotUnlockedError(EncryptionError): pass


class DecryptionError(EncryptionError): pass


def xor_cipher(data: bytes, key: bytes) -> bytes:
    # ... (xor_cipher 函数保持不变) ...
    key_len = len(key)
    if key_len == 0: return data
    data_array = bytearray(data)
    for i in range(len(data_array)):
        data_array[i] ^= key[i % key_len]
    return bytes(data_array)


class EncryptionManager:
    def __init__(self, config_path: str):
        self.config_path = config_path
        # [V2 核心改动]
        self.disk_configs = {}  # 存储每个盘的盐和哈希
        self.unlocked_keys = {}  # 存储已解锁的盘及其内存中的密钥
        self.load_config()

    def _load_json(self, path: str, default):
        # ... (_load_json 方法保持不变) ...
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f: return json.load(f)
        except Exception:
            pass
        return default

    def load_config(self):
        """加载每个磁盘的加密配置"""
        config = self._load_json(self.config_path, {})
        self.disk_configs = config.get("disks", {})
        print(f"🔒 加密管理器已加载，受保护的驱动器: {list(self.disk_configs.keys()) or '无'}")

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
            self.unlocked_keys[norm_drive] = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000,
                                                                 dklen=32)
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
            raise NotUnlockedError(f"磁盘 {drive} 已锁定，无法读取。")

        with open(file_path, "rb") as f:
            encrypted_data = f.read()
        return xor_cipher(encrypted_data, key)

    def decrypt_disk_permanently(self, drive_path: str, password: str) -> dict:
        """
        永久解密一个磁盘上的所有文件。这是一个耗时且危险的操作。
        返回一个包含处理结果的字典。
        """
        norm_drive = _norm_abs(drive_path)

        # 1. 验证密码并获取密钥
        if not self.unlock(norm_drive, password):
            # 如果密码错误，顺便把可能因其他会话解锁的盘锁上，确保安全
            self.lock(norm_drive)
            raise ValueError("密码错误")

        key = self.unlocked_keys.get(norm_drive)
        if not key:
            # 理论上 unlock 成功后这里不会触发
            raise EncryptionError("无法获取密钥，即使密码正确")

        print(f"⚠️ 开始对磁盘 {norm_drive} 进行永久解密操作...")

        processed_files = 0
        failed_files = []

        # 2. 遍历磁盘上的所有文件
        for root, dirs, files in os.walk(norm_drive):
            for filename in files:
                file_path = os.path.join(root, filename)
                try:
                    # a. 读取加密内容
                    with open(file_path, "rb") as f:
                        encrypted_data = f.read()

                    # b. 在内存中解密
                    decrypted_data = xor_cipher(encrypted_data, key)

                    # c. 将解密后的明文写回原文件，覆盖加密内容
                    with open(file_path, "wb") as f:
                        f.write(decrypted_data)

                    processed_files += 1
                    print(f"  ✅ 已解密: {file_path}")

                except Exception as e:
                    print(f"  ❌ 解密失败: {file_path}, 错误: {e}")
                    failed_files.append(file_path)

        # 3. 操作完成后，立即将密钥从内存中移除
        self.lock(norm_drive)

        print(f"✅ 磁盘 {norm_drive} 解密完成。")
        return {
            "processed_files": processed_files,
            "failed_files": failed_files
        }
    def write_encrypted_file(self, file_path: str, data: bytes):
        """加密并写入文件"""
        drive = self._get_drive_for_path(file_path)
        if not drive:
            raise EncryptionError("文件不位于加密盘上")

        key = self.unlocked_keys.get(drive)
        if not key:
            raise NotUnlockedError(f"磁盘 {drive} 已锁定，无法写入。")

        encrypted_data = xor_cipher(data, key)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(encrypted_data)