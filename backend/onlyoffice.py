import os
import json
import hashlib
import time
import requests
from datetime import datetime, timedelta
from flask import request, jsonify, g
from common import get_db, BASE_DIRS
import jwt
from functools import wraps
import shutil

class OnlyOfficeManager:
    def __init__(self, app):
        self.app = app
        # OnlyOffice Document Server URL
        # 本地安装的 OnlyOffice Document Server
        self.documents_server_url = "http://localhost:80"
        self.secret_key = "ND8NKsCEYy5iypHAd7N7DCfNFmkM5j"  # 用于签名
        self.storage_path = os.path.join(BASE_DIRS[0], "documents")  # 文档存储路径
        
        # 确保文档存储目录存在
        os.makedirs(self.storage_path, exist_ok=True)
        
        # 初始化数据库表
        self.init_onlyoffice_tables()
    
    def init_onlyoffice_tables(self):
        """初始化OnlyOffice相关的数据库表"""
        with self.app.app_context():
            db = get_db()
            
            # OnlyOffice文档表
            db.execute('''
                CREATE TABLE IF NOT EXISTS onlyoffice_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    created_by INTEGER NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER DEFAULT 1,
                    FOREIGN KEY (created_by) REFERENCES users (id)
                )
            ''')
            
            # 文档权限表
            db.execute('''
                CREATE TABLE IF NOT EXISTS onlyoffice_permissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    permission_type TEXT NOT NULL, -- 'read', 'write', 'comment', 'fill'
                    granted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (document_id) REFERENCES onlyoffice_documents (id),
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    UNIQUE(document_id, user_id)
                )
            ''')
            
            # 编辑会话表
            db.execute('''
                CREATE TABLE IF NOT EXISTS onlyoffice_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    session_key TEXT NOT NULL,
                    session_start DATETIME DEFAULT CURRENT_TIMESTAMP,
                    session_end DATETIME,
                    FOREIGN KEY (document_id) REFERENCES onlyoffice_documents (id),
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            db.commit()
    
    def get_document_config(self, doc_id, user_id, action="edit"):
        """生成OnlyOffice文档配置"""
        db = get_db()
        
        # 获取文档信息
        cur = db.execute("SELECT * FROM onlyoffice_documents WHERE id=?", (doc_id,))
        doc = cur.fetchone()
        if not doc:
            return None
        
        # 获取用户信息
        cur = db.execute("SELECT * FROM users WHERE id=?", (user_id,))
        user = cur.fetchone()
        if not user:
            return None
        
        # 检查权限
        if not self.check_document_permission(doc_id, user_id, action):
            return None
        
        # 生成文档密钥
        doc_key = self.generate_document_key(doc_id)
        
        # 构建配置
        config = {
            "document": {
                "fileType": doc['file_type'].lstrip('.'),
                "key": doc_key,
                "title": doc['file_name'],
                "url": f"{request.host_url}api/onlyoffice/download/{doc_id}",
                "permissions": {
                    "comment": self.check_document_permission(doc_id, user_id, "comment"),
                    "copy": True,
                    "download": True,
                    "edit": self.check_document_permission(doc_id, user_id, "write"),
                    "fillForms": self.check_document_permission(doc_id, user_id, "fill"),
                    "modifyFilter": True,
                    "modifyContentControl": True,
                    "review": True,
                    "print": True
                }
            },
            "documentType": self.get_document_type(doc['file_type']),
            "editorConfig": {
                "mode": "edit" if action == "edit" else "view",
                "lang": "zh-CN",
                "callbackUrl": f"{request.host_url}api/onlyoffice/callback",
                "user": {
                    "id": str(user_id),
                    "name": user['username']
                },
                "customization": {
                    "autosave": True,
                    "forcesave": True,
                    "comments": True,
                    "zoom": 100
                }
            },
            "height": "100%",
            "width": "100%"
        }
        
        return config
    
    def get_document_type(self, file_type):
        """根据文件类型返回文档类型"""
        text_types = ['.doc', '.docx', '.odt', '.rtf', '.txt']
        spreadsheet_types = ['.xls', '.xlsx', '.ods']
        presentation_types = ['.ppt', '.pptx', '.odp']
        
        if file_type.lower() in text_types:
            return "text"
        elif file_type.lower() in spreadsheet_types:
            return "spreadsheet"
        elif file_type.lower() in presentation_types:
            return "presentation"
        else:
            return "text"
    
    def generate_document_key(self, doc_id):
        """生成文档密钥"""
        return hashlib.md5(f"doc_{doc_id}_{int(time.time())}".encode()).hexdigest()
    
    def check_document_permission(self, doc_id, user_id, permission_type):
        """检查用户对文档的权限"""
        db = get_db()
        
        # 检查是否是文档创建者
        cur = db.execute("SELECT created_by FROM onlyoffice_documents WHERE id=?", (doc_id,))
        doc = cur.fetchone()
        if doc and doc['created_by'] == user_id:
            return True
        
        # 检查特定权限
        cur = db.execute(
            "SELECT permission_type FROM onlyoffice_permissions WHERE document_id=? AND user_id=?",
            (doc_id, user_id)
        )
        permission = cur.fetchone()
        
        if permission:
            if permission_type == "read":
                return True
            elif permission_type == "write" and permission['permission_type'] in ['write', 'admin']:
                return True
            elif permission_type == "comment" and permission['permission_type'] in ['comment', 'write', 'admin']:
                return True
            elif permission_type == "fill" and permission['permission_type'] in ['fill', 'write', 'admin']:
                return True
            elif permission_type == "admin" and permission['permission_type'] == 'admin':
                return True
        
        return False
    
    def save_document(self, doc_id, download_url):
        """保存文档"""
        try:
            # 下载文档
            response = requests.get(download_url)
            if response.status_code != 200:
                return False
            
            db = get_db()
            cur = db.execute("SELECT file_path FROM onlyoffice_documents WHERE id=?", (doc_id,))
            doc = cur.fetchone()
            if not doc:
                return False
            
            # 保存到本地
            file_path = os.path.join(self.storage_path, doc['file_path'])
            with open(file_path, 'wb') as f:
                f.write(response.content)
            
            # 更新数据库
            db.execute(
                "UPDATE onlyoffice_documents SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (doc_id,)
            )
            db.commit()
            
            return True
        except Exception as e:
            print(f"Error saving document: {e}")
            return False
    
    def create_document(self, file_name, file_path, file_type, user_id):
        """创建新文档记录"""
        try:
            db = get_db()
            db.execute(
                "INSERT INTO onlyoffice_documents (file_name, file_path, file_type, created_by) VALUES (?, ?, ?, ?)",
                (file_name, file_path, file_type, user_id)
            )
            db.commit()
            
            # 获取新创建的文档ID
            cur = db.execute("SELECT last_insert_rowid() as id")
            return cur.fetchone()['id']
        except Exception as e:
            print(f"Error creating document: {e}")
            return None
    
    def share_document(self, doc_id, username, permission_type):
        """分享文档给用户"""
        try:
            db = get_db()
            
            # 查找用户
            cur = db.execute("SELECT id FROM users WHERE username=?", (username,))
            user = cur.fetchone()
            if not user:
                return False, "用户不存在"
            
            # 检查是否已经分享
            cur = db.execute(
                "SELECT id FROM onlyoffice_permissions WHERE document_id=? AND user_id=?",
                (doc_id, user['id'])
            )
            if cur.fetchone():
                # 更新权限
                db.execute(
                    "UPDATE onlyoffice_permissions SET permission_type=?, granted_at=CURRENT_TIMESTAMP WHERE document_id=? AND user_id=?",
                    (permission_type, doc_id, user['id'])
                )
            else:
                # 创建新权限
                db.execute(
                    "INSERT INTO onlyoffice_permissions (document_id, user_id, permission_type) VALUES (?, ?, ?)",
                    (doc_id, user['id'], permission_type)
                )
            
            db.commit()
            return True, "分享成功"
        except Exception as e:
            print(f"Error sharing document: {e}")
            return False, "分享失败"
    
    def get_user_documents(self, user_id):
        """获取用户可访问的文档列表"""
        db = get_db()
        
        # 获取用户创建的文档
        created_docs = db.execute(
            "SELECT * FROM onlyoffice_documents WHERE created_by=? AND is_active=1",
            (user_id,)
        ).fetchall()
        
        # 获取分享给用户的文档
        shared_docs = db.execute('''
            SELECT od.*, op.permission_type 
            FROM onlyoffice_documents od
            JOIN onlyoffice_permissions op ON od.id = op.document_id
            WHERE op.user_id = ? AND od.is_active = 1
        ''', (user_id,)).fetchall()
        
        documents = []
        
        # 处理创建的文档
        for doc in created_docs:
            documents.append({
                'id': doc['id'],
                'file_name': doc['file_name'],
                'file_type': doc['file_type'],
                'created_at': doc['created_at'],
                'updated_at': doc['updated_at'],
                'permission': 'owner',
                'created_by': doc['created_by']
            })
        
        # 处理分享的文档
        for doc in shared_docs:
            documents.append({
                'id': doc['id'],
                'file_name': doc['file_name'],
                'file_type': doc['file_type'],
                'created_at': doc['created_at'],
                'updated_at': doc['updated_at'],
                'permission': doc['permission_type'],
                'created_by': doc['created_by']
            })
        
        return documents
    
    def upload_document(self, file, user_id):
        """上传文档到OnlyOffice"""
        try:
            # 检查文件类型
            allowed_extensions = {
                '.doc', '.docx', '.odt', '.rtf', '.txt',  # 文本文档
                '.xls', '.xlsx', '.ods',  # 电子表格
                '.ppt', '.pptx', '.odp'   # 演示文稿
            }
            
            filename = file.filename
            file_ext = os.path.splitext(filename)[1].lower()
            
            if file_ext not in allowed_extensions:
                return False, "不支持的文件类型"
            
            # 生成唯一文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_filename = f"{timestamp}_{filename}"
            file_path = os.path.join(self.storage_path, safe_filename)
            
            # 保存文件
            file.save(file_path)
            
            # 创建数据库记录
            doc_id = self.create_document(filename, safe_filename, file_ext, user_id)
            if not doc_id:
                return False, "创建文档记录失败"
            
            return True, {"doc_id": doc_id, "filename": filename}
            
        except Exception as e:
            print(f"Error uploading document: {e}")
            return False, "上传失败"
    
    def get_supported_formats(self):
        """获取支持的文件格式"""
        return {
            "text": [".doc", ".docx", ".odt", ".rtf", ".txt"],
            "spreadsheet": [".xls", ".xlsx", ".ods"],
            "presentation": [".ppt", ".pptx", ".odp"]
        } 