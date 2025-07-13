# OnlyOffice 集成说明

## 概述

本项目已集成 OnlyOffice Document Server，提供强大的在线文档编辑功能，支持 Word、Excel、PowerPoint 等格式的实时协作编辑。

## 功能特性

### 1. 文档编辑
- 支持 Word (.docx, .doc, .odt, .rtf, .txt)
- 支持 Excel (.xlsx, .xls, .ods)
- 支持 PowerPoint (.pptx, .ppt, .odp)
- 实时协作编辑
- 自动保存

### 2. 权限管理
- **所有者**: 完全控制权限
- **读写**: 编辑和保存权限
- **只读**: 仅查看权限
- **评论**: 添加评论权限
- **填写**: 填写表单权限

### 3. 协作功能
- 多人同时编辑
- 实时显示其他用户光标
- 评论和讨论
- 版本历史
- 文档分享

## 安装部署

### 1. 安装 OnlyOffice Document Server

#### Docker 方式（推荐）

```bash
# 创建数据目录
mkdir -p /opt/onlyoffice/data
mkdir -p /opt/onlyoffice/logs
mkdir -p /opt/onlyoffice/cache

# 运行 OnlyOffice Document Server
docker run -i -t -d -p 80:80 \
    -v /opt/onlyoffice/data:/var/www/onlyoffice/Data \
    -v /opt/onlyoffice/logs:/var/log/onlyoffice \
    -v /opt/onlyoffice/cache:/var/lib/onlyoffice \
    onlyoffice/documentserver
```

#### 直接安装

```bash
# Ubuntu/Debian
wget -O - https://download.onlyoffice.com/GPG-KEY-ONLYOFFICE | apt-key add -
echo "deb https://download.onlyoffice.com/repo/debian squeeze main" | tee /etc/apt/sources.list.d/onlyoffice.list
apt-get update
apt-get install onlyoffice-documentserver

# CentOS/RHEL
yum install epel-release
yum install https://download.onlyoffice.com/repo/onlyoffice.repo
yum install onlyoffice-documentserver
```

### 2. 配置 OnlyOffice

编辑配置文件 `/etc/onlyoffice/documentserver/default.json`：

```json
{
  "services": {
    "CoAuthoring": {
      "request": {
        "inbox": true,
        "outbox": true
      }
    }
  },
  "rabbitmq": {
    "url": "amqp://guest:guest@localhost"
  },
  "redis": {
    "host": "localhost",
    "port": 6379
  },
  "storage": {
    "fs": {
      "path": "/var/www/onlyoffice/Data"
    }
  }
}
```

### 3. 启动服务

```bash
# 启动 OnlyOffice Document Server
supervisorctl start all

# 或者重启
supervisorctl restart all
```

### 4. 验证安装

访问 `http://your-server-ip` 应该能看到 OnlyOffice 的欢迎页面。

## 项目配置

### 1. 更新配置文件

在 `backend/onlyoffice.py` 中修改配置：

```python
class OnlyOfficeManager:
    def __init__(self, app):
        self.app = app
        # 修改为你的 OnlyOffice Document Server 地址
        self.documents_server_url = "http://your-server-ip:80"
        self.secret_key = "your-secret-key"  # 设置安全的密钥
        self.storage_path = os.path.join(BASE_DIR, "documents")
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 启动应用

```bash
python backend/app.py
```

## 使用方法

### 1. 创建文档

1. 登录到 NAS 系统
2. 点击"OnlyOffice 编辑"按钮
3. 点击"创建新文档"
4. 选择文档类型（Word/Excel/PowerPoint）
5. 输入文件名
6. 点击"创建"

### 2. 编辑文档

1. 在文档列表中点击"编辑"按钮
2. 文档将在新窗口中打开
3. 开始编辑文档内容
4. 系统会自动保存更改

### 3. 分享文档

1. 在文档编辑器中点击"分享"按钮
2. 输入要分享的用户名
3. 选择权限级别
4. 点击"分享"

### 4. 协作编辑

1. 多个用户同时打开同一文档
2. 实时看到其他用户的编辑
3. 支持评论和讨论
4. 自动同步所有更改

## API 接口

### 获取文档列表
```
GET /api/onlyoffice/documents
Authorization: Bearer <token>
```

### 创建文档
```
POST /api/onlyoffice/documents
Authorization: Bearer <token>
Content-Type: application/json

{
  "file_name": "文档名称.docx",
  "file_type": ".docx"
}
```

### 获取编辑器配置
```
GET /api/onlyoffice/documents/{doc_id}/config?action=edit
Authorization: Bearer <token>
```

### 分享文档
```
POST /api/onlyoffice/documents/{doc_id}/share
Authorization: Bearer <token>
Content-Type: application/json

{
  "username": "用户名",
  "permission_type": "read"
}
```

### 下载文档
```
GET /api/onlyoffice/download/{doc_id}
Authorization: Bearer <token>
```

## 数据库表结构

### onlyoffice_documents
- `id`: 文档ID
- `file_name`: 文件名
- `file_path`: 文件路径
- `file_type`: 文件类型
- `created_by`: 创建者ID
- `created_at`: 创建时间
- `updated_at`: 更新时间
- `is_active`: 是否激活

### onlyoffice_permissions
- `id`: 权限ID
- `document_id`: 文档ID
- `user_id`: 用户ID
- `permission_type`: 权限类型
- `granted_at`: 授权时间

### onlyoffice_sessions
- `id`: 会话ID
- `document_id`: 文档ID
- `user_id`: 用户ID
- `session_key`: 会话密钥
- `session_start`: 会话开始时间
- `session_end`: 会话结束时间

## 故障排除

### 1. OnlyOffice 无法连接

检查以下几点：
- OnlyOffice Document Server 是否正常运行
- 防火墙是否开放 80 端口
- 网络连接是否正常
- 配置文件中的地址是否正确

### 2. 文档无法保存

检查以下几点：
- 回调 URL 是否正确配置
- 网络连接是否正常
- 存储路径是否有写权限
- 日志中是否有错误信息

### 3. 协作功能不工作

检查以下几点：
- WebSocket 连接是否正常
- 用户权限是否正确设置
- 浏览器是否支持 WebSocket
- 网络环境是否稳定

### 4. 查看日志

```bash
# OnlyOffice 日志
tail -f /var/log/onlyoffice/documentserver.log

# 应用日志
tail -f /var/log/your-app.log
```

## 性能优化

### 1. 服务器配置

- 建议至少 4GB 内存
- 多核 CPU 以提高并发处理能力
- SSD 存储以提高 I/O 性能

### 2. 网络优化

- 使用 CDN 加速静态资源
- 配置反向代理
- 启用 Gzip 压缩

### 3. 缓存配置

- 配置 Redis 缓存
- 启用浏览器缓存
- 使用内存缓存减少数据库查询

## 安全考虑

### 1. 网络安全

- 使用 HTTPS 加密传输
- 配置防火墙规则
- 定期更新安全补丁

### 2. 访问控制

- 实施严格的权限控制
- 记录用户操作日志
- 定期审查访问权限

### 3. 数据安全

- 定期备份文档数据
- 加密敏感文档
- 实施数据保留策略

## 扩展功能

未来可以考虑添加的功能：
- 文档模板系统
- 批量操作功能
- 文档版本管理
- 离线编辑支持
- 移动端适配
- 文档搜索功能
- 工作流集成
- 第三方存储集成

## 技术支持

如果遇到问题，可以：
1. 查看官方文档：https://helpcenter.onlyoffice.com/
2. 查看社区论坛：https://forum.onlyoffice.com/
3. 提交 Issue 到项目仓库
4. 联系技术支持团队 