# tasks/session_cleanup.py
# -*- coding: utf-8 -*-
"""
会话清理后台任务
- 定期清理过期的预览会话
"""

import time
import threading
from datetime import datetime

# 预览会话存储
# 注意：这个字典需要在 app.py 中也能访问到
# 可以通过依赖注入或全局变量的方式共享
preview_sessions = {}


def get_preview_sessions():
    """获取预览会话字典的引用"""
    return preview_sessions


def set_preview_sessions(sessions_dict):
    """设置预览会话字典（用于从外部注入）"""
    global preview_sessions
    preview_sessions = sessions_dict


def cleanup_expired_sessions():
    """清理过期的预览会话"""
    current_time = datetime.now()
    expired_sessions = []
    
    for session_id, session_data in preview_sessions.items():
        if current_time > session_data['expires_at']:
            expired_sessions.append(session_id)
    
    for session_id in expired_sessions:
        del preview_sessions[session_id]
        print(f"[DEBUG] 清理过期会话: {session_id}")
    
    if expired_sessions:
        print(f"[DEBUG] 清理了 {len(expired_sessions)} 个过期会话")
    
    print(f"[DEBUG] 当前活跃会话数: {len(preview_sessions)}")


def background_cleanup():
    """后台清理任务"""
    print("[DEBUG] 启动预览会话后台清理任务")
    while True:
        try:
            cleanup_expired_sessions()
            time.sleep(300)  # 每5分钟清理一次
        except Exception as e:
            print(f"[DEBUG] 后台清理任务异常: {e}")
            time.sleep(60)  # 出错后等待1分钟再重试


def start_cleanup_thread():
    """启动后台清理线程"""
    try:
        cleanup_thread = threading.Thread(target=background_cleanup, daemon=True)
        cleanup_thread.start()
        print("[DEBUG] 预览会话清理线程启动成功")
    except Exception as e:
        print(f"[DEBUG] 启动清理线程失败: {e}")
