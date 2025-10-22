# 文件: filemanager.py (最终干净版本 - 只保留非冲突路由)

# 文件: filemanager.py (修改顶部导入)

import os
import shutil
from flask import Blueprint, request, jsonify, session
# 确保从 common 导入 _is_ec_volume
from common import get_actual_file_path, is_path_allowed, _is_ec_volume
from permission_decorator import permission_required
# 确保所有文件操作路由都已在 app.py 中用 EC 卷逻辑优先实现。
# 本文件只保留 app.py 中没有的或功能不重复的路由。

file_bp = Blueprint('filemanager', __name__, url_prefix='/api')


# =================================================================
# 核心原则：以下路由都在 app.py 中有 EC 兼容版本，故在此删除。
# /list, /download, /upload, /delete, /preview, /rename
# =================================================================


# ========== 1. 创建目录 (/api/mkdir) - 集成 EC 卷隔离 ==========
@file_bp.route('/mkdir', methods=['POST'])
@permission_required('readwrite')
def make_dir():
    data = request.json
    parent = data.get('parent', '/')
    new_dir = data.get('name')

    if not new_dir:
        return jsonify({"error": "目录名不能为空"}), 400
    if not parent:
        return jsonify({'error': '父路径不能为空'}), 400

    # 1. 优先处理 EC 卷（虚拟创建，只返回成功）
    if _is_ec_volume(parent):
        return jsonify({'success': True, 'message': '虚拟目录将在上传文件后自动体现'})

    # 2. 物理盘创建
    try:
        # (这部分逻辑不变)
        parent_abs = get_actual_file_path(parent)

        if not parent_abs or _is_ec_volume(parent_abs):
            return jsonify({"error": "路径无效或 EC 卷处理错误"}), 400
        if not os.path.isdir(parent_abs):
            return jsonify({"error": "目标父目录不存在"}), 404

        abs_path = os.path.join(parent_abs, new_dir)

        if not is_path_allowed(abs_path):
            return jsonify({"error": "不允许访问该路径"}), 403

        if os.path.exists(abs_path):
            return jsonify({"error": "目录已存在"}), 400

        os.makedirs(abs_path, exist_ok=False)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ========== 2. 文件编辑 (/api/edit) - 集成 EC 卷隔离 ==========
# 5. [修改] 替换装饰器 (注意：这里改为'readonly'，允许只读用户查看)
@file_bp.route('/edit', methods=['GET', 'POST'])
@permission_required('readonly')
def edit_file():
    req_path = request.args.get('path') or request.get_json().get('path')
    if not req_path:
        return jsonify({"error": "未指定文件路径"}), 400

    # 1. 优先处理 EC 卷（功能未实现）
    if _is_ec_volume(req_path):
        return jsonify({"error": "EC卷文件编辑功能暂不支持"}), 501

    # 2. 物理盘处理
    actual_path = get_actual_file_path(req_path)

    if not actual_path or not os.path.exists(actual_path) or not os.path.isfile(actual_path):
        return jsonify({'error': '文件不存在或不是文件'}), 404
    if not is_path_allowed(actual_path):
        return jsonify({"error": "路径不在允许的目录中"}), 403

    if request.method == 'GET':
        # (GET请求，'readonly' 权限已足够)
        # (读取逻辑不变)
        try:
            encodings = ['utf-8', 'utf-16', 'gbk', 'latin-1']
            content = None
            for encoding in encodings:
                try:
                    with open(actual_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            if content is None:
                return jsonify({"error": "无法读取文件，编码格式不支持"}), 400
            return jsonify({"success": True, "content": content})
        except Exception as e:
            return jsonify({"error": f"读取失败: {str(e)}"}), 500

    elif request.method == 'POST':

        # 6. [新增] 内部权限检查！
        # 装饰器只检查了 'readonly'，但 POST 保存需要 'readwrite' 权限
        user_perm = session.get('file_permission', 'readonly')
        user_role = session.get('role')

        # 检查是否不是管理员，并且权限低于 'readwrite'
        if user_role != 'admin' and user_perm not in ['readwrite', 'fullcontrol']:
            return jsonify({
                "error": "权限不足",
                "message": f"保存文件需要 'readwrite' 或 'fullcontrol' 权限，您当前为 '{user_perm}'"
            }), 403

        # (权限检查通过，开始保存文件)
        # (保存逻辑不变)
        data = request.get_json()
        new_content = data.get('content', '')

        try:
            # 备份原文件
            backup_name = os.path.basename(actual_path) + '.bak_' + datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = os.path.join(os.path.dirname(actual_path), backup_name)
            shutil.copy2(actual_path, backup_path)

            # 保存新内容
            with open(actual_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            return jsonify({"success": True, "message": "保存成功，已备份原文件为 " + backup_name})
        except Exception as e:
            return jsonify({"error": f"保存失败: {str(e)}"}), 500