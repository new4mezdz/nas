# routes/__init__.py
# -*- coding: utf-8 -*-
"""
路由模块包
将所有 Blueprint 和初始化函数统一导出
"""

from .user_routes import user_bp  # ← 删掉 init_user_routes
from .system_routes import system_bp, init_system_routes
from .setup_routes import setup_bp, init_setup_routes
from .auth_routes import auth_bp, init_auth_routes
from .admin_routes import admin_bp, init_admin_routes
from .share_routes import share_bp, init_share_routes
from .encryption_routes import encryption_bp, init_encryption_routes
from .pool_routes import pool_bp, init_pool_routes
from .ec_routes import ec_bp, init_ec_routes
from .file_routes import file_bp, init_file_routes


# 本地定义 init_user_routes
def init_user_routes():
    """用户路由初始化（当前无需特殊配置）"""
    pass


__all__ = [
    # Blueprints
    'user_bp',
    'system_bp',
    'setup_bp',
    'auth_bp',
    'admin_bp',
    'share_bp',
    'encryption_bp',
    'pool_bp',
    'ec_bp',
    'file_bp',
    # Init functions
    'init_user_routes',
    'init_system_routes',
    'init_setup_routes',
    'init_auth_routes',
    'init_admin_routes',
    'init_share_routes',
    'init_encryption_routes',
    'init_pool_routes',
    'init_ec_routes',
    'init_file_routes',
]