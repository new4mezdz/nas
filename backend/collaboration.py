import os
import json
import sqlite3
from datetime import datetime
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask import request, g
import jwt
from common import get_db

class CollaborationManager:
    def __init__(self, app, socketio):
        self.app = app
        self.socketio = socketio
        self.active_documents = {}  # {doc_id: {users: [], content: "", version: 0}}
        self.user_sessions = {}  # {user_id: {username: "", current_doc: None}}
        
        # 初始化数据库表
        self.init_collaboration_tables()
        
        # 注册WebSocket事件
        self.register_events()
    
    def init_collaboration_tables(self):
        """初始化协作编辑相关的数据库表"""
        with self.app.app_context():
            db = get_db()
            
            # 文档表
            db.execute('''
                CREATE TABLE IF NOT EXISTS collaborative_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT DEFAULT '',
                    file_path TEXT,
                    created_by INTEGER NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER DEFAULT 1,
                    FOREIGN KEY (created_by) REFERENCES users (id)
                )
            ''')
            
            # 文档版本表
            db.execute('''
                CREATE TABLE IF NOT EXISTS document_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL,
                    version_number INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    created_by INTEGER NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    change_description TEXT,
                    FOREIGN KEY (document_id) REFERENCES collaborative_documents (id),
                    FOREIGN KEY (created_by) REFERENCES users (id)
                )
            ''')
            
            # 文档权限表
            db.execute('''
                CREATE TABLE IF NOT EXISTS document_permissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    permission_type TEXT NOT NULL, -- 'read', 'write', 'admin'
                    granted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (document_id) REFERENCES collaborative_documents (id),
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    UNIQUE(document_id, user_id)
                )
            ''')
            
            # 编辑会话表
            db.execute('''
                CREATE TABLE IF NOT EXISTS editing_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    session_start DATETIME DEFAULT CURRENT_TIMESTAMP,
                    session_end DATETIME,
                    FOREIGN KEY (document_id) REFERENCES collaborative_documents (id),
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            db.commit()
    
    def register_events(self):
        """注册WebSocket事件处理器"""
        
        @self.socketio.on('connect')
        def handle_connect():
            print(f"Client connected: {request.sid}")
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            print(f"Client disconnected: {request.sid}")
            self.handle_user_disconnect(request.sid)
        
        @self.socketio.on('join_collaboration')
        def handle_join_collaboration(data):
            """用户加入协作会话"""
            try:
                session_token = data.get('session_token')
                username = data.get('username')
                
                if not session_token or not username:
                    emit('error', {'message': '缺少必要参数'})
                    return
                
                # 加入协作房间
                room = f"collab_{session_token}"
                join_room(room)
                
                # 记录用户会话
                self.user_sessions[request.sid] = {
                    'username': username,
                    'session_token': session_token,
                    'room': room
                }
                
                # 通知其他用户
                emit('user_joined', {
                    'username': username
                }, room=room, include_self=False)
                
                print(f"User {username} joined collaboration session {session_token}")
                
            except Exception as e:
                print(f"Error in join_collaboration: {e}")
                emit('error', {'message': '加入协作失败'})
        
        @self.socketio.on('content_change')
        def handle_content_change(data):
            """处理内容变更"""
            try:
                session_token = data.get('session_token')
                content = data.get('content')
                username = data.get('username')
                
                if not session_token or not content:
                    return
                
                # 广播内容变更给其他用户
                room = f"collab_{session_token}"
                emit('content_change', {
                    'content': content,
                    'username': username
                }, room=room, include_self=False)
                
            except Exception as e:
                print(f"Error in content_change: {e}")
        
        @self.socketio.on('cursor_move')
        def handle_cursor_move(data):
            """处理光标移动"""
            try:
                session_token = data.get('session_token')
                position = data.get('position')
                username = data.get('username')
                
                if not session_token or position is None:
                    return
                
                # 广播光标位置给其他用户
                room = f"collab_{session_token}"
                emit('cursor_move', {
                    'position': position,
                    'username': username
                }, room=room, include_self=False)
                
            except Exception as e:
                print(f"Error in cursor_move: {e}")
        
        @self.socketio.on('join_document')
        def handle_join_document(data):
            """用户加入文档编辑"""
            try:
                token = data.get('token')
                doc_id = data.get('document_id')
                
                if not token or not doc_id:
                    emit('error', {'message': '缺少必要参数'})
                    return
                
                # 验证用户
                user = self.verify_token(token)
                if not user:
                    emit('error', {'message': '无效的token'})
                    return
                
                # 检查文档权限
                if not self.check_document_permission(doc_id, user['id'], 'read'):
                    emit('error', {'message': '没有访问权限'})
                    return
                
                # 加入房间
                room = f"doc_{doc_id}"
                join_room(room)
                
                # 记录用户会话
                self.user_sessions[request.sid] = {
                    'user_id': user['id'],
                    'username': user['username'],
                    'current_doc': doc_id
                }
                
                # 初始化文档状态
                if doc_id not in self.active_documents:
                    self.active_documents[doc_id] = {
                        'users': [],
                        'content': self.get_document_content(doc_id),
                        'version': 0
                    }
                
                # 添加用户到活跃文档
                if user['id'] not in self.active_documents[doc_id]['users']:
                    self.active_documents[doc_id]['users'].append(user['id'])
                
                # 记录编辑会话
                self.record_editing_session(doc_id, user['id'])
                
                # 通知其他用户
                emit('user_joined', {
                    'user_id': user['id'],
                    'username': user['username']
                }, room=room, include_self=False)
                
                # 发送当前文档状态
                emit('document_state', {
                    'content': self.active_documents[doc_id]['content'],
                    'version': self.active_documents[doc_id]['version'],
                    'active_users': self.get_active_users_info(doc_id)
                })
                
                print(f"User {user['username']} joined document {doc_id}")
                
            except Exception as e:
                print(f"Error in join_document: {e}")
                emit('error', {'message': '加入文档失败'})
        
        @self.socketio.on('leave_document')
        def handle_leave_document(data):
            """用户离开文档编辑"""
            try:
                doc_id = data.get('document_id')
                if not doc_id:
                    return
                
                room = f"doc_{doc_id}"
                leave_room(room)
                
                # 更新用户会话
                if request.sid in self.user_sessions:
                    user_info = self.user_sessions[request.sid]
                    user_id = user_info['user_id']
                    
                    # 从活跃文档中移除用户
                    if doc_id in self.active_documents and user_id in self.active_documents[doc_id]['users']:
                        self.active_documents[doc_id]['users'].remove(user_id)
                    
                    # 结束编辑会话
                    self.end_editing_session(doc_id, user_id)
                    
                    # 通知其他用户
                    emit('user_left', {
                        'user_id': user_id,
                        'username': user_info['username']
                    }, room=room, include_self=False)
                    
                    # 清理用户会话
                    del self.user_sessions[request.sid]
                
            except Exception as e:
                print(f"Error in leave_document: {e}")
        
        @self.socketio.on('document_change')
        def handle_document_change(data):
            """处理文档内容变更"""
            try:
                token = data.get('token')
                doc_id = data.get('document_id')
                content = data.get('content')
                change_type = data.get('change_type', 'update')  # 'update', 'insert', 'delete'
                position = data.get('position', 0)
                length = data.get('length', 0)
                text = data.get('text', '')
                
                if not token or not doc_id:
                    return
                
                # 验证用户
                user = self.verify_token(token)
                if not user:
                    return
                
                # 检查写权限
                if not self.check_document_permission(doc_id, user['id'], 'write'):
                    return
                
                room = f"doc_{doc_id}"
                
                # 更新文档内容
                if doc_id in self.active_documents:
                    if change_type == 'update':
                        self.active_documents[doc_id]['content'] = content
                    elif change_type == 'insert':
                        current_content = self.active_documents[doc_id]['content']
                        new_content = current_content[:position] + text + current_content[position:]
                        self.active_documents[doc_id]['content'] = new_content
                    elif change_type == 'delete':
                        current_content = self.active_documents[doc_id]['content']
                        new_content = current_content[:position] + current_content[position + length:]
                        self.active_documents[doc_id]['content'] = new_content
                    
                    self.active_documents[doc_id]['version'] += 1
                
                # 广播变更给其他用户
                emit('document_updated', {
                    'user_id': user['id'],
                    'username': user['username'],
                    'content': self.active_documents[doc_id]['content'],
                    'version': self.active_documents[doc_id]['version'],
                    'change_type': change_type,
                    'position': position,
                    'length': length,
                    'text': text,
                    'timestamp': datetime.now().isoformat()
                }, room=room, include_self=False)
                
            except Exception as e:
                print(f"Error in document_change: {e}")
        
        @self.socketio.on('save_document')
        def handle_save_document(data):
            """保存文档"""
            try:
                token = data.get('token')
                doc_id = data.get('document_id')
                content = data.get('content')
                description = data.get('description', '自动保存')
                
                if not token or not doc_id:
                    emit('save_result', {'success': False, 'message': '缺少必要参数'})
                    return
                
                # 验证用户
                user = self.verify_token(token)
                if not user:
                    emit('save_result', {'success': False, 'message': '无效的token'})
                    return
                
                # 检查写权限
                if not self.check_document_permission(doc_id, user['id'], 'write'):
                    emit('save_result', {'success': False, 'message': '没有写权限'})
                    return
                
                # 保存文档
                success = self.save_document_version(doc_id, content, user['id'], description)
                
                if success:
                    emit('save_result', {'success': True, 'message': '保存成功'})
                    # 通知其他用户文档已保存
                    room = f"doc_{doc_id}"
                    emit('document_saved', {
                        'user_id': user['id'],
                        'username': user['username'],
                        'timestamp': datetime.now().isoformat()
                    }, room=room, include_self=False)
                else:
                    emit('save_result', {'success': False, 'message': '保存失败'})
                
            except Exception as e:
                print(f"Error in save_document: {e}")
                emit('save_result', {'success': False, 'message': '保存失败'})
    
    def verify_token(self, token):
        """验证JWT token并返回用户信息"""
        try:
            data = jwt.decode(token, self.app.config['SECRET_KEY'], algorithms=["HS256"])
            db = get_db()
            cur = db.execute("SELECT * FROM users WHERE id=?", (data['id'],))
            user = cur.fetchone()
            if user and user['is_active']:
                return dict(user)
        except Exception as e:
            print(f"Token verification failed: {e}")
        return None
    
    def check_document_permission(self, doc_id, user_id, permission_type):
        """检查用户对文档的权限"""
        db = get_db()
        
        # 检查是否是文档创建者
        cur = db.execute("SELECT created_by FROM collaborative_documents WHERE id=?", (doc_id,))
        doc = cur.fetchone()
        if doc and doc['created_by'] == user_id:
            return True
        
        # 检查特定权限
        cur = db.execute(
            "SELECT permission_type FROM document_permissions WHERE document_id=? AND user_id=?",
            (doc_id, user_id)
        )
        permission = cur.fetchone()
        
        if permission:
            if permission_type == 'read':
                return True
            elif permission_type == 'write' and permission['permission_type'] in ['write', 'admin']:
                return True
            elif permission_type == 'admin' and permission['permission_type'] == 'admin':
                return True
        
        return False
    
    def get_document_content(self, doc_id):
        """获取文档内容"""
        db = get_db()
        cur = db.execute("SELECT content FROM collaborative_documents WHERE id=?", (doc_id,))
        doc = cur.fetchone()
        return doc['content'] if doc else ""
    
    def get_active_users_info(self, doc_id):
        """获取文档的活跃用户信息"""
        if doc_id not in self.active_documents:
            return []
        
        db = get_db()
        users_info = []
        for user_id in self.active_documents[doc_id]['users']:
            cur = db.execute("SELECT id, username FROM users WHERE id=?", (user_id,))
            user = cur.fetchone()
            if user:
                users_info.append(dict(user))
        
        return users_info
    
    def record_editing_session(self, doc_id, user_id):
        """记录编辑会话开始"""
        db = get_db()
        db.execute(
            "INSERT INTO editing_sessions (document_id, user_id) VALUES (?, ?)",
            (doc_id, user_id)
        )
        db.commit()
    
    def end_editing_session(self, doc_id, user_id):
        """结束编辑会话"""
        db = get_db()
        db.execute(
            "UPDATE editing_sessions SET session_end = CURRENT_TIMESTAMP WHERE document_id = ? AND user_id = ? AND session_end IS NULL",
            (doc_id, user_id)
        )
        db.commit()
    
    def save_document_version(self, doc_id, content, user_id, description):
        """保存文档版本"""
        try:
            db = get_db()
            
            # 更新文档内容
            db.execute(
                "UPDATE collaborative_documents SET content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (content, doc_id)
            )
            
            # 获取当前版本号
            cur = db.execute(
                "SELECT MAX(version_number) as max_version FROM document_versions WHERE document_id = ?",
                (doc_id,)
            )
            result = cur.fetchone()
            next_version = (result['max_version'] or 0) + 1
            
            # 创建新版本
            db.execute(
                "INSERT INTO document_versions (document_id, version_number, content, created_by, change_description) VALUES (?, ?, ?, ?, ?)",
                (doc_id, next_version, content, user_id, description)
            )
            
            db.commit()
            return True
        except Exception as e:
            print(f"Error saving document version: {e}")
            return False
    
    def handle_user_disconnect(self, sid):
        """处理用户断开连接"""
        if sid in self.user_sessions:
            user_info = self.user_sessions[sid]
            doc_id = user_info['current_doc']
            
            if doc_id:
                # 从活跃文档中移除用户
                if doc_id in self.active_documents and user_info['user_id'] in self.active_documents[doc_id]['users']:
                    self.active_documents[doc_id]['users'].remove(user_info['user_id'])
                
                # 结束编辑会话
                self.end_editing_session(doc_id, user_info['user_id'])
                
                # 通知其他用户
                room = f"doc_{doc_id}"
                emit('user_left', {
                    'user_id': user_info['user_id'],
                    'username': user_info['username']
                }, room=room, include_self=False)
            
            # 清理用户会话
            del self.user_sessions[sid] 