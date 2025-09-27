# backend/encryption.py

import os
import json
from utils import _norm_abs  # 假设 _norm_abs 在 utils.py 中


# ======================================================
#                自定义加密异常
# ======================================================
class EncryptionError(Exception):
    """加密模块的基础异常类"""
    pass


class NotUnlockedError(EncryptionError):
    """当尝试操作一个锁定的加密驱动器时抛出"""
    pass


class DecryptionError(EncryptionError):
    """当数据解密失败时抛出"""
    pass


# ======================================================
#          XOR 置乱原型 (仅供学习和测试)
# ======================================================
def xor_cipher(data: bytes, key: bytes) -> bytes:
    """使用重复密鑰对数据进行XOR操作。"""
    key_len = len(key)
    if key_len == 0:
        return data
    data_array = bytearray(data)
    for i in range(len(data_array)):
        data_array[i] ^= key[i % key_len]
    return bytes(data_array)


# ======================================================
#               加密管理器类
# ======================================================
class EncryptionManager:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.encrypted_drives = set()
        self.is_unlocked = False
        # 在真实场景中，这个密鑰需要从用户输入的主密码安全地派生而来
        self._key_in_memory = "a_very_simple_and_insecure_key".encode('utf-8')

        self.load_config()

    def _load_json(self, path: str, default):
        """一个局部的 JSON 加载器，让模块更独立"""
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return default

    def load_config(self):
        """从 JSON 文件加载加密配置"""
        config = self._load_json(self.config_path, {})
        raw_drives = config.get("encrypted_drives", [])
        self.encrypted_drives = {_norm_abs(d) for d in raw_drives}
        print(f"🔒 加密管理器已加载，受保护的驱动器: {self.encrypted_drives or '无'}")

    def is_path_encrypted(self, file_path: str) -> bool:
        """检查给定路径是否位于加密磁碟上。"""
        norm_path = _norm_abs(file_path)
        for drive in self.encrypted_drives:
            if norm_path.startswith(drive):
                return True
        return False

    def unlock(self, password: str) -> bool:
        """
        解鎖磁碟。原型简化了验证，真实场景需要验证密码并派生密鑰。
        """
        if password == "123456":  # 假设我们的原型主密码是 "123456"
            self.is_unlocked = True
            print("🔓 加密驱动器已解锁。")
            return True
        print("🔑 错误的解锁密码。")
        return False

    def lock(self):
        """锁定驱动器，从内存中清除敏感信息（虽然原型中是固定的）"""
        self.is_unlocked = False
        print("🔒 加密驱动器已锁定。")

    def read_encrypted_file(self, file_path: str) -> bytes:
        """读取并解密文件。"""
        if not self.is_unlocked:
            raise NotUnlockedError("磁碟已锁定，无法读取。")

        with open(file_path, "rb") as f:
            encrypted_data = f.read()

        # 使用XOR解密
        return xor_cipher(encrypted_data, self._key_in_memory)

    def write_encrypted_file(self, file_path: str, data: bytes):
        """加密並寫入文件。"""
        if not self.is_unlocked:
            raise NotUnlockedError("磁碟已锁定，无法写入。")

        # 使用XOR加密
        encrypted_data = xor_cipher(data, self._key_in_memory)

        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(encrypted_data)