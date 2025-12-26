# sockets/collaboration.py
# -*- coding: utf-8 -*-
"""
文档协作 WebSocket 事件处理
"""

from flask import request
from flask_socketio import emit, join_room, leave_room

# 存储每个文档的在线用户
# 格式: {doc_id: {sid: {username, avatar}, ...}}
doc_users = {}


def init_collaboration_events(socketio):
    """
    注册所有协作相关的 WebSocket 事件
    在 app.py 中调用: init_collaboration_events(socketio)
    """
    
    @socketio.on('join_doc')
    def handle_join_doc(data):
        """用户加入文档编辑"""
        doc_id = data.get('doc_id')
        username = data.get('username', '匿名用户')
        avatar = data.get('avatar', '')
        
        join_room(doc_id)
        
        if doc_id not in doc_users:
            doc_users[doc_id] = {}
        doc_users[doc_id][request.sid] = {
            'username': username,
            'avatar': avatar
        }
        
        # 广播用户列表更新（包含头像）
        emit('users_update', {
            'users': [
                {'username': u['username'], 'avatar': u['avatar']}
                for u in doc_users[doc_id].values()
            ],
            'count': len(doc_users[doc_id])
        }, room=doc_id)
        
        print(f"[协作] {username} 加入文档 {doc_id}，当前 {len(doc_users[doc_id])} 人")
    
    
    @socketio.on('leave_doc')
    def handle_leave_doc(data):
        """用户离开文档"""
        doc_id = data.get('doc_id')
        
        leave_room(doc_id)
        
        if doc_id in doc_users and request.sid in doc_users[doc_id]:
            user_info = doc_users[doc_id].pop(request.sid)
            username = user_info['username'] if isinstance(user_info, dict) else user_info
            emit('users_update', {
                'users': [
                    {'username': u['username'], 'avatar': u['avatar']}
                    for u in doc_users[doc_id].values()
                ],
                'count': len(doc_users[doc_id])
            }, room=doc_id)
            print(f"[协作] {username} 离开文档 {doc_id}")
    
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """用户断开连接"""
        for doc_id in list(doc_users.keys()):
            if request.sid in doc_users[doc_id]:
                user_info = doc_users[doc_id].pop(request.sid)
                emit('users_update', {
                    'users': [
                        {'username': u['username'], 'avatar': u['avatar']}
                        for u in doc_users[doc_id].values()
                    ],
                    'count': len(doc_users[doc_id])
                }, room=doc_id)
    
    
    @socketio.on('doc_change')
    def handle_doc_change(data):
        """文档内容变更 - 广播给其他用户"""
        doc_id = data.get('doc_id')
        change = data.get('change')
        username = data.get('username')
        
        # 广播给同一文档的其他用户（排除自己）
        emit('doc_change', {
            'change': change,
            'username': username
        }, room=doc_id, include_self=False)
    
    
    @socketio.on('cursor_move')
    def handle_cursor_move(data):
        """光标位置同步"""
        doc_id = data.get('doc_id')
        emit('cursor_move', {
            'username': data.get('username'),
            'position': data.get('position'),
            'color': data.get('color')
        }, room=doc_id, include_self=False)
    
    print("[SOCKETS] 协作 WebSocket 事件注册完成")
