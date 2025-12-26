# config.py
# -*- coding: utf-8 -*-
"""
配置集中管理模块
所有配置项统一在此定义，避免散落在各处
"""

import os
from datetime import timedelta


# ==================== 路径配置 ====================
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))

# 纠删码配置文件路径
EC_CFG_PATH = os.path.join(BACKEND_DIR, "ec_config.json")
EC_IDX_PATH = os.path.join(BACKEND_DIR, "ec_index.json")

# 加密配置文件路径
ENCRYPTION_CFG_PATH = os.path.join(BACKEND_DIR, "encryption_config.json")

# 节点配置文件路径
NODE_CONFIG_PATH = os.path.join(BACKEND_DIR, "node_config.json")


# ==================== 服务端口配置 ====================
FLASK_PORT = 5000
OHM_PORT = 8085  # LibreHardwareMonitor 端口


# ==================== 密钥配置 ====================
SECRET_KEY = 'super-secret-key'  # Flask 会话密钥，生产环境请更换
ACCESS_TOKEN_SECRET = 'your-access-token-secret-key'  # JWT 令牌密钥，需与管理端一致


# ==================== 管理端配置 ====================
# 这些值会在运行时从 node_config.json 加载，这里只是默认值
NAS_CENTER_API_URL = "http://127.0.0.1:8080"  # 管理端地址
NAS_SHARED_SECRET = "your-shared-secret-key"  # 共享密钥(需与管理端一致)
NAS_CENTER_PUBLIC_URL = None  # 管理端公网URL，启动时动态获取
THIS_NODE_ID = None  # 本节点ID，启动时从配置加载


# ==================== Flask 配置类 ====================
class FlaskConfig:
    """Flask 应用配置"""
    SECRET_KEY = SECRET_KEY
    
    # Session 配置
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = False  # 开发环境用 False，生产环境改为 True
    SESSION_COOKIE_PATH = '/'
    SESSION_COOKIE_NAME = 'client_session'  # 客户端使用不同的 session 名
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)  # 7天有效期


# ==================== LibreOffice 配置 ====================
def get_soffice_path():
    """获取 LibreOffice 可执行文件路径"""
    if os.name == 'nt':  # Windows
        portable_path = os.path.join(
            BACKEND_DIR, 'tool', 'LibreOfficePortable', 
            'App', 'libreoffice', 'program', 'soffice.exe'
        )
    else:  # Linux
        portable_path = os.path.join(
            BACKEND_DIR, 'tool', 'LibreOfficePortable', 
            'App', 'libreoffice', 'program', 'soffice'
        )
    
    if os.path.exists(portable_path):
        print(f"[INFO] 使用便携版 LibreOffice: {portable_path}")
        return portable_path
    
    # 回退到系统安装版本
    print("[INFO] 使用系统 LibreOffice")
    return 'soffice'


SOFFICE_PATH = get_soffice_path()


# ==================== 运行时配置管理 ====================
class RuntimeConfig:
    """
    运行时配置管理器
    用于存储启动后动态加载的配置（如从node_config.json读取的值）
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_defaults()
        return cls._instance
    
    def _init_defaults(self):
        """初始化默认值"""
        self.nas_center_api_url = NAS_CENTER_API_URL
        self.nas_shared_secret = NAS_SHARED_SECRET
        self.nas_center_public_url = NAS_CENTER_PUBLIC_URL
        self.this_node_id = THIS_NODE_ID
    
    def load_from_node_config(self, config: dict):
        """从节点配置加载运行时配置"""
        if config:
            self.nas_center_api_url = config.get('master_url', self.nas_center_api_url)
            self.nas_shared_secret = config.get('shared_secret', self.nas_shared_secret)
            self.this_node_id = config.get('node_id', self.this_node_id)
            print(f"[CONFIG] 已加载节点配置: node_id={self.this_node_id}")


# 全局运行时配置实例
runtime_config = RuntimeConfig()
