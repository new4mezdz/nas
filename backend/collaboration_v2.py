import os
import json
import secrets
import hashlib
from datetime import datetime, timedelta
from flask import request, jsonify, g
from common import get_db, BASE_DIRS
import jwt

class CollaborationV2:
    def __init__(self, app):
        self.app = app
        self.storage_path = os.path.join(BASE_DIRS[0], "collaboration")
        os.makedirs(self.storage_path, exist_ok=True)
        
        # 初始化数据库表
        self.init_collaboration_tables()
    
    def init_collaboration_tables(self):
        """初始化协作相关的数据库表"""
        with self.app.app_context():
            db = get_db()
            
            # 协作会话表
            db.execute('''
                CREATE TABLE IF NOT EXISTS collaboration_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    session_token TEXT UNIQUE NOT NULL,
                    created_by INTEGER NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME,
                    is_active INTEGER DEFAULT 1,
                    max_participants INTEGER DEFAULT 10,
                    current_participants INTEGER DEFAULT 0,
                    FOREIGN KEY (created_by) REFERENCES users (id)
                )
            ''')
            
            # 参与者表
            db.execute('''
                CREATE TABLE IF NOT EXISTS collaboration_participants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    user_id INTEGER,
                    username TEXT NOT NULL,
                    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_active DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_online INTEGER DEFAULT 0,
                    FOREIGN KEY (session_id) REFERENCES collaboration_sessions (id),
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            # 文档变更记录表
            db.execute('''
                CREATE TABLE IF NOT EXISTS collaboration_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    user_id INTEGER,
                    username TEXT NOT NULL,
                    change_type TEXT NOT NULL, -- 'insert', 'delete', 'format'
                    position INTEGER,
                    content TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES collaboration_sessions (id),
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            db.commit()
    
    def create_collaboration_session(self, file_path, file_name, user_id, expire_hours=24):
        """创建协作会话"""
        try:
            db = get_db()
            
            # 验证文件路径并尝试找到实际文件位置
            actual_file_path = self._find_actual_file_path(file_path, file_name)
            if not actual_file_path:
                return None
            
            # 生成唯一会话令牌
            session_token = secrets.token_urlsafe(16)
            
            # 设置过期时间
            expires_at = datetime.now() + timedelta(hours=expire_hours)
            
            # 创建会话记录
            db.execute('''
                INSERT INTO collaboration_sessions 
                (file_path, file_name, session_token, created_by, expires_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (actual_file_path, file_name, session_token, user_id, expires_at))
            
            db.commit()
            
            # 获取会话ID
            cur = db.execute("SELECT last_insert_rowid() as id")
            session_id = cur.fetchone()['id']
            
            # 添加创建者为参与者
            self.add_participant(session_id, user_id, "创建者")
            
            return {
                'session_id': session_id,
                'session_token': session_token,
                'share_url': f"/collaboration.html?token={session_token}",
                'expires_at': expires_at.isoformat()
            }
            
        except Exception as e:
            print(f"Error creating collaboration session: {e}")
            return None
    
    def add_participant(self, session_id, user_id, username):
        """添加参与者"""
        try:
            db = get_db()
            
            # 检查是否已经是参与者
            cur = db.execute(
                "SELECT id FROM collaboration_participants WHERE session_id=? AND user_id=?",
                (session_id, user_id)
            )
            
            if not cur.fetchone():
                # 添加新参与者
                db.execute('''
                    INSERT INTO collaboration_participants (session_id, user_id, username)
                    VALUES (?, ?, ?)
                ''', (session_id, user_id, username))
                
                # 更新当前参与者数量
                db.execute('''
                    UPDATE collaboration_sessions 
                    SET current_participants = current_participants + 1
                    WHERE id = ?
                ''', (session_id,))
                
                db.commit()
            
            return True
            
        except Exception as e:
            print(f"Error adding participant: {e}")
            return False
    
    def _find_actual_file_path(self, file_path, file_name):
        """查找文件的实际路径"""
        try:
            # 首先检查原始路径是否存在
            if os.path.exists(file_path):
                return file_path
            
            # 如果原始路径不存在，尝试在所有可用盘符中查找
            for base_dir in BASE_DIRS:
                if os.path.exists(base_dir):
                    # 从原始路径中提取相对路径部分
                    # 例如：从 "F:/nas_data/file.docx" 提取 "nas_data/file.docx"
                    relative_path = file_path
                    for drive in BASE_DIRS:
                        if file_path.startswith(drive):
                            relative_path = file_path[len(drive):]
                            break
                    
                    # 构建新的完整路径
                    new_path = os.path.join(base_dir, relative_path.lstrip('/'))
                    if os.path.exists(new_path):
                        print(f"找到文件实际位置: {new_path}")
                        return new_path
            
            print(f"文件不存在: {file_path}")
            return None
            
        except Exception as e:
            print(f"查找文件路径时出错: {e}")
            return None
    
    def get_session_info(self, session_token):
        """获取会话信息"""
        try:
            db = get_db()
            
            cur = db.execute('''
                SELECT cs.*, u.username as creator_name
                FROM collaboration_sessions cs
                JOIN users u ON cs.created_by = u.id
                WHERE cs.session_token = ? AND cs.is_active = 1
            ''', (session_token,))
            
            session = cur.fetchone()
            if not session:
                return None
            
            # 检查是否过期
            if session['expires_at'] and datetime.fromisoformat(session['expires_at']) < datetime.now():
                return None
            
            # 获取参与者列表
            participants = db.execute('''
                SELECT username, is_online, last_active
                FROM collaboration_participants
                WHERE session_id = ?
                ORDER BY joined_at
            ''', (session['id'],)).fetchall()
            
            return {
                'session_id': session['id'],
                'file_name': session['file_name'],
                'file_path': session['file_path'],
                'creator_name': session['creator_name'],
                'created_at': session['created_at'],
                'expires_at': session['expires_at'],
                'current_participants': session['current_participants'],
                'max_participants': session['max_participants'],
                'participants': [dict(p) for p in participants]
            }
            
        except Exception as e:
            print(f"Error getting session info: {e}")
            return None
    
    def join_session(self, session_token, user_id, username):
        """加入协作会话"""
        try:
            session_info = self.get_session_info(session_token)
            if not session_info:
                return False, "会话不存在或已过期"
            
            # 检查参与者数量限制
            if session_info['current_participants'] >= session_info['max_participants']:
                return False, "会话已满"
            
            # 添加参与者
            if self.add_participant(session_info['session_id'], user_id, username):
                return True, "成功加入会话"
            else:
                return False, "加入会话失败"
                
        except Exception as e:
            print(f"Error joining session: {e}")
            return False, "加入会话失败"
    
    def get_user_sessions(self, user_id):
        """获取用户创建的协作会话"""
        try:
            db = get_db()
            
            sessions = db.execute('''
                SELECT cs.*, 
                       (SELECT COUNT(*) FROM collaboration_participants WHERE session_id = cs.id) as participant_count
                FROM collaboration_sessions cs
                WHERE cs.created_by = ? AND cs.is_active = 1
                ORDER BY cs.created_at DESC
            ''', (user_id,)).fetchall()
            
            return [dict(s) for s in sessions]
            
        except Exception as e:
            print(f"Error getting user sessions: {e}")
            return []
    
    def get_participating_sessions(self, user_id):
        """获取用户参与的协作会话"""
        try:
            db = get_db()
            
            sessions = db.execute('''
                SELECT cs.*, u.username as creator_name,
                       (SELECT COUNT(*) FROM collaboration_participants WHERE session_id = cs.id) as participant_count
                FROM collaboration_sessions cs
                JOIN collaboration_participants cp ON cs.id = cp.session_id
                JOIN users u ON cs.created_by = u.id
                WHERE cp.user_id = ? AND cs.is_active = 1 AND cs.created_by != ?
                ORDER BY cs.created_at DESC
            ''', (user_id, user_id)).fetchall()
            
            return [dict(s) for s in sessions]
            
        except Exception as e:
            print(f"Error getting participating sessions: {e}")
            return []
    
    def close_session(self, session_id, user_id):
        """关闭协作会话"""
        try:
            db = get_db()
            
            # 检查权限
            cur = db.execute(
                "SELECT created_by FROM collaboration_sessions WHERE id=?",
                (session_id,)
            )
            session = cur.fetchone()
            
            if not session or session['created_by'] != user_id:
                return False, "没有权限关闭此会话"
            
            # 关闭会话
            db.execute(
                "UPDATE collaboration_sessions SET is_active = 0 WHERE id = ?",
                (session_id,)
            )
            db.commit()
            
            return True, "会话已关闭"
            
        except Exception as e:
            print(f"Error closing session: {e}")
            return False, "关闭会话失败" 