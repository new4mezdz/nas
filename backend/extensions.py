# extensions.py
# -*- coding: utf-8 -*-
"""
Flask 扩展初始化模块
所有 Flask 扩展在此统一初始化，避免循环导入
"""

from flask_socketio import SocketIO

# ==================== SocketIO 扩展 ====================
# 先创建实例，不绑定 app
# 在 app.py 中调用 socketio.init_app(app) 完成绑定
socketio = SocketIO(cors_allowed_origins="*", async_mode='eventlet')


# ==================== 数据库连接管理 ====================
# 注意：当前项目使用 common.py 中的 get_db()
# 如果后续需要统一管理，可以在这里添加


def init_extensions(app):
    """
    初始化所有扩展
    在 create_app() 或 app.py 中调用
    """
    socketio.init_app(app)
    print("[EXTENSIONS] SocketIO 初始化完成")
