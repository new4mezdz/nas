# 文档协作功能使用说明

## 功能概述

您的NAS系统现在已经支持多人实时协作编辑文档功能，类似于Google Docs的体验。

## 主要特性

### 1. 实时协作编辑
- 多人同时编辑同一文档
- 实时显示其他用户的编辑内容
- 在线用户状态显示
- 实时保存和同步

### 2. 权限管理
- **所有者**: 可以编辑、分享、删除文档
- **管理员**: 可以编辑、分享文档
- **读写**: 可以编辑文档
- **只读**: 只能查看文档

### 3. 版本控制
- 自动保存文档版本
- 查看版本历史
- 支持版本回滚

### 4. 文档分享
- 分享给特定用户
- 设置不同的权限级别
- 权限管理

## 使用方法

### 1. 启动服务器

首先安装新的依赖：

```bash
pip install -r requirements.txt
```

然后启动服务器：

```bash
python backend/app.py
```

### 2. 创建文档

1. 登录到NAS系统
2. 点击"文档协作"按钮
3. 点击"新建文档"
4. 输入文档标题和初始内容
5. 点击"创建"

### 3. 分享文档

1. 在文档列表中，点击文档右侧的"分享"按钮
2. 输入要分享的用户名
3. 选择权限级别（只读/读写/管理员）
4. 点击"分享"

### 4. 协作编辑

1. 点击文档进入编辑模式
2. 开始编辑文档内容
3. 其他用户会实时看到您的编辑
4. 点击"保存"按钮手动保存

### 5. 查看版本历史

1. 在文档列表中，点击文档右侧的"版本"按钮
2. 查看所有保存的版本
3. 可以查看特定版本的内容

## 技术架构

### 后端技术栈
- **Flask**: Web框架
- **Flask-SocketIO**: WebSocket支持
- **SQLite**: 数据存储
- **JWT**: 用户认证

### 前端技术栈
- **Vue.js 3**: 前端框架
- **Socket.IO**: 实时通信
- **Tailwind CSS**: 样式框架

### 数据库表结构

#### collaborative_documents (文档表)
- `id`: 文档ID
- `title`: 文档标题
- `content`: 文档内容
- `created_by`: 创建者ID
- `created_at`: 创建时间
- `updated_at`: 更新时间

#### document_versions (版本表)
- `id`: 版本ID
- `document_id`: 文档ID
- `version_number`: 版本号
- `content`: 版本内容
- `created_by`: 创建者ID
- `created_at`: 创建时间
- `change_description`: 变更描述

#### document_permissions (权限表)
- `id`: 权限ID
- `document_id`: 文档ID
- `user_id`: 用户ID
- `permission_type`: 权限类型
- `granted_at`: 授权时间

#### editing_sessions (编辑会话表)
- `id`: 会话ID
- `document_id`: 文档ID
- `user_id`: 用户ID
- `session_start`: 会话开始时间
- `session_end`: 会话结束时间

## WebSocket事件

### 客户端发送的事件
- `join_document`: 加入文档编辑
- `leave_document`: 离开文档编辑
- `document_change`: 文档内容变更
- `save_document`: 保存文档

### 服务器发送的事件
- `document_state`: 文档当前状态
- `document_updated`: 文档更新通知
- `user_joined`: 用户加入通知
- `user_left`: 用户离开通知
- `document_saved`: 文档保存通知
- `error`: 错误信息

## 测试

运行测试脚本：

```bash
python test_collaboration.py
```

这个脚本会：
1. 创建两个测试用户
2. 创建一个测试文档
3. 分享文档给另一个用户
4. 验证权限和访问

## 注意事项

1. **网络连接**: 实时协作需要稳定的网络连接
2. **浏览器兼容性**: 建议使用现代浏览器（Chrome、Firefox、Safari、Edge）
3. **并发用户数**: 建议单个文档同时编辑用户不超过10人
4. **文档大小**: 建议文档内容不超过1MB

## 故障排除

### 常见问题

1. **WebSocket连接失败**
   - 检查服务器是否正常运行
   - 检查防火墙设置
   - 确认端口5000未被占用

2. **实时同步不工作**
   - 检查浏览器控制台是否有错误
   - 确认网络连接正常
   - 刷新页面重试

3. **权限问题**
   - 确认用户已正确登录
   - 检查文档权限设置
   - 联系文档所有者

### 日志查看

服务器日志会显示：
- WebSocket连接状态
- 用户加入/离开事件
- 文档保存操作
- 错误信息

## 扩展功能

未来可以考虑添加的功能：
- 评论系统
- 文档模板
- 导出功能（PDF、Word等）
- 离线编辑支持
- 更丰富的文本编辑器
- 文档标签和分类 