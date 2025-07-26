import os
from flask import Blueprint, request, jsonify, send_file
from common import token_required, BASE_DIRS, get_base_dir_for_path, get_actual_file_path
import shutil
from datetime import datetime

file_bp = Blueprint('filemanager', __name__, url_prefix='/api')


def safe_join(base, *paths):
    final_path = os.path.abspath(os.path.join(base, *paths))
    if not final_path.startswith(os.path.abspath(base)):
        raise ValueError("不允许访问此路径")
    return final_path


@file_bp.route('/files', methods=['GET'])
@token_required()
def list_files():
    req_path = request.args.get('path', '/')
    try:
        base_dir = get_base_dir_for_path(req_path)
        if not base_dir:
            return jsonify({"error": "路径不在允许的目录中"}), 400
        abs_path = safe_join(base_dir, req_path.lstrip("/\\"))
    except Exception:
        return jsonify({"error": "路径非法"}), 400
    if not os.path.exists(abs_path):
        return jsonify({"error": "路径不存在"}), 404
    if not os.path.isdir(abs_path):
        return jsonify({"error": "不是文件夹"}), 400
    items = []
    for fname in os.listdir(abs_path):
        fpath = os.path.join(abs_path, fname)
        stat = os.stat(fpath)
        items.append({
            "name": fname,
            "is_dir": os.path.isdir(fpath),
            "size": stat.st_size if os.path.isfile(fpath) else None,
            "mtime": stat.st_mtime
        })
    return jsonify({
        "current": req_path if req_path.startswith("/") else "/" + req_path,
        "items": items
    })


@file_bp.route('/download', methods=['GET'])
@token_required()
def download_file():
    req_path = request.args.get('path')
    if not req_path:
        return jsonify({"error": "未指定文件"}), 400

    print(f"[DEBUG] 下载请求路径: {req_path}")

    # 使用增强的路径处理
    actual_path = get_actual_file_path(req_path)
    if not actual_path or not os.path.exists(actual_path):
        print(f"[DEBUG] 文件不存在: {actual_path}")
        return jsonify({"error": "文件不存在"}), 404

    if not os.path.isfile(actual_path):
        return jsonify({"error": "不是文件"}), 400

    print(f"[DEBUG] 实际下载路径: {actual_path}")
    return send_file(actual_path, as_attachment=True)


@file_bp.route('/upload', methods=['POST'])
@token_required()
def upload_file():
    req_path = request.form.get('path', '/')
    try:
        base_dir = get_base_dir_for_path(req_path)
        if not base_dir:
            return jsonify({"error": "路径不在允许的目录中"}), 400
        abs_path = safe_join(base_dir, req_path.lstrip("/\\"))
    except Exception:
        return jsonify({"error": "路径非法"}), 400
    if not os.path.isdir(abs_path):
        return jsonify({"error": "上传路径不存在"}), 400
    if 'file' not in request.files:
        return jsonify({"error": "没有检测到上传文件"}), 400
    f = request.files['file']
    filename = os.path.basename(f.filename)
    save_path = os.path.join(abs_path, filename)
    try:
        f.save(save_path)
        return jsonify({"success": True, "message": "上传成功"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@file_bp.route('/mkdir', methods=['POST'])
@token_required(admin_only=True)
def make_dir():
    data = request.json
    parent = data.get('parent', '/')
    new_dir = data.get('name')
    if not new_dir:
        return jsonify({"error": "目录名不能为空"}), 400
    try:
        base_dir = get_base_dir_for_path(parent)
        if not base_dir:
            return jsonify({"error": "路径不在允许的目录中"}), 400
        parent_abs = safe_join(base_dir, parent.lstrip("/\\"))
        if not os.path.isdir(parent_abs):
            return jsonify({"error": "目标父目录不存在"}), 400
        abs_path = os.path.join(parent_abs, new_dir)
        if os.path.exists(abs_path):
            return jsonify({"error": "目录已存在"}), 400
        os.mkdir(abs_path)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@file_bp.route('/delete', methods=['POST'])
@token_required(admin_only=True)
def delete_entry():
    data = request.json
    path = data.get('path')
    if not path:
        return jsonify({"error": "未指定路径"}), 400

    print(f"[DEBUG] 删除请求路径: {path}")

    # 使用增强的路径处理
    actual_path = get_actual_file_path(path)
    if not actual_path or not os.path.exists(actual_path):
        print(f"[DEBUG] 要删除的文件不存在: {actual_path}")
        return jsonify({"error": "文件不存在"}), 404

    try:
        if os.path.isdir(actual_path):
            shutil.rmtree(actual_path)
            print(f"[DEBUG] 成功删除目录: {actual_path}")
        else:
            os.remove(actual_path)
            print(f"[DEBUG] 成功删除文件: {actual_path}")
        return jsonify({"success": True})
    except Exception as e:
        print(f"[DEBUG] 删除失败: {e}")
        return jsonify({"error": str(e)}), 500


# ========== 增强的重命名功能 ==========
@file_bp.route('/rename', methods=['POST'])
@token_required()  # 允许普通用户重命名
def rename_entry():
    data = request.json
    path = data.get('path')
    new_name = data.get('new_name')

    print(f"[DEBUG] 重命名请求 - 原路径: {path}, 新名称: {new_name}")

    if not path or not new_name:
        return jsonify({"error": "参数缺失"}), 400

    # 基本的安全检查：防止路径穿越
    if '..' in new_name or '/' in new_name or '\\' in new_name:
        return jsonify({"error": "文件名包含非法字符"}), 400

    try:
        # 使用增强的路径处理函数
        actual_path = get_actual_file_path(path)
        print(f"[DEBUG] 解析的实际路径: {actual_path}")

        if not actual_path or not os.path.exists(actual_path):
            print(f"[DEBUG] 源文件不存在: {actual_path}")
            return jsonify({"error": "源文件不存在"}), 404

        # 构建新文件的完整路径
        parent_dir = os.path.dirname(actual_path)
        new_actual_path = os.path.join(parent_dir, new_name)

        print(f"[DEBUG] 目标路径: {new_actual_path}")

        # 检查新文件名是否已存在
        if os.path.exists(new_actual_path):
            return jsonify({"error": "目标文件名已存在"}), 400

        # 执行重命名
        os.rename(actual_path, new_actual_path)
        print(f"[DEBUG] 重命名成功: {actual_path} -> {new_actual_path}")

        return jsonify({"success": True, "message": f"已将 '{os.path.basename(actual_path)}' 重命名为 '{new_name}'"})

    except Exception as e:
        print(f"[DEBUG] 重命名失败: {e}")
        return jsonify({"error": f"重命名失败: {str(e)}"}), 500


@file_bp.route('/edit', methods=['GET', 'POST'])
@token_required()
def edit_file():
    req_path = request.args.get('path')
    if not req_path:
        return jsonify({"error": "未指定文件路径"}), 400

    print(f"[DEBUG] 编辑请求路径: {req_path}")

    # 使用增强的路径处理
    actual_path = get_actual_file_path(req_path)
    if not actual_path or not os.path.exists(actual_path):
        return jsonify({"error": "文件不存在"}), 404

    if not os.path.isfile(actual_path):
        return jsonify({"error": "不是文件"}), 400

    if request.method == 'GET':
        # 读取文件内容
        try:
            # 尝试多种编码方式
            encodings = ['utf-8', 'utf-16', 'gbk', 'latin-1']
            content = None
            used_encoding = None

            for encoding in encodings:
                try:
                    with open(actual_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    used_encoding = encoding
                    break
                except UnicodeDecodeError:
                    continue

            if content is None:
                return jsonify({"error": "无法读取文件，编码格式不支持"}), 400

            print(f"[DEBUG] 成功读取文件，使用编码: {used_encoding}")
            return jsonify({"success": True, "content": content})
        except Exception as e:
            print(f"[DEBUG] 读取文件失败: {e}")
            return jsonify({"error": f"读取失败: {str(e)}"}), 500

    elif request.method == 'POST':
        # 保存文件内容，并生成历史备份
        data = request.get_json()
        new_content = data.get('content', '')
        backup_name = os.path.basename(actual_path) + '.bak_' + datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(os.path.dirname(actual_path), backup_name)

        try:
            # 备份原文件
            shutil.copy2(actual_path, backup_path)
            print(f"[DEBUG] 创建备份文件: {backup_path}")

            # 保存新内容
            with open(actual_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            print(f"[DEBUG] 文件保存成功: {actual_path}")
            return jsonify({"success": True, "message": "保存成功，已备份原文件为 " + backup_name})
        except Exception as e:
            print(f"[DEBUG] 保存文件失败: {e}")
            return jsonify({"error": f"保存失败: {str(e)}"}), 500


# ========== 预览功能也需要增强路径处理 ==========
@file_bp.route('/preview', methods=['GET'])
@token_required()
def preview_file():
    path = request.args.get('path', '').lstrip('/\\')

    print(f"[DEBUG] 预览请求路径: {path}")

    # 使用增强的路径处理
    actual_path = get_actual_file_path(path)
    if not actual_path or not os.path.exists(actual_path):
        print(f"[DEBUG] 预览文件不存在: {actual_path}")
        return jsonify({'error': '文件不存在'}), 404

    print(f"[DEBUG] 实际预览路径: {actual_path}")

    ext = os.path.splitext(actual_path)[1].lower()

    # ===== 1. DOCX: 直接返回原文件 =====
    if ext == '.docx':
        return send_file(actual_path,
                         mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')

    # ===== 2. 文本类文件（纯文本返回） =====
    elif ext in ['.txt', '.log', '.md', '.py', '.js', '.html', '.json', '.css', '.csv']:
        try:
            # 多编码支持的文本读取
            encodings = ['utf-8', 'utf-16-le', 'utf-16-be', 'gbk', 'gb2312', 'big5', 'latin-1']
            content = None
            used_encoding = None

            # 首先读取文件的二进制内容检查BOM
            with open(actual_path, 'rb') as f:
                raw_content = f.read()

            # 检查BOM
            if raw_content.startswith(b'\xff\xfe'):
                try:
                    content = raw_content.decode('utf-16-le')
                    used_encoding = 'utf-16-le (BOM detected)'
                except UnicodeDecodeError:
                    pass
            elif raw_content.startswith(b'\xfe\xff'):
                try:
                    content = raw_content.decode('utf-16-be')
                    used_encoding = 'utf-16-be (BOM detected)'
                except UnicodeDecodeError:
                    pass
            elif raw_content.startswith(b'\xef\xbb\xbf'):
                try:
                    content = raw_content.decode('utf-8-sig')
                    used_encoding = 'utf-8-sig (BOM detected)'
                except UnicodeDecodeError:
                    pass

            # 如果没有BOM，尝试多种编码
            if content is None:
                for encoding in encodings:
                    try:
                        content = raw_content.decode(encoding)
                        used_encoding = encoding
                        break
                    except UnicodeDecodeError:
                        continue

            if content is None:
                content = raw_content.decode('utf-8', errors='replace')
                used_encoding = 'utf-8 (with replacement)'

            print(f"[DEBUG] 文本文件读取成功，编码: {used_encoding}")
            return content, 200, {'Content-Type': 'text/plain; charset=utf-8'}
        except Exception as e:
            print(f"[DEBUG] 文本文件读取失败: {e}")
            return jsonify({'error': f'无法读取文本内容: {str(e)}'}), 500

    # ===== 3. PDF文件：返回内嵌预览 =====
    elif ext == '.pdf':
        if request.args.get('inline') == 'true':
            response = send_file(actual_path, mimetype='application/pdf')
            response.headers['Content-Disposition'] = 'inline'
            return response
        else:
            token = request.args.get('token', '')
            pdf_url = f'/api/preview?path={path}&inline=true'
            if token:
                pdf_url += f'&token={token}'

            html_content = f'''
            <!DOCTYPE html>
            <html>
            <head>
                <title>PDF预览 - {os.path.basename(actual_path)}</title>
                <style>
                    body {{ margin: 0; padding: 0; height: 100vh; }}
                    iframe {{ width: 100%; height: 100%; border: none; }}
                </style>
            </head>
            <body>
                <iframe src="{pdf_url}" type="application/pdf"></iframe>
            </body>
            </html>
            '''
            return html_content, 200, {'Content-Type': 'text/html; charset=utf-8'}

    # ===== 4. 其他格式（图片、音视频等）原样返回 =====
    else:
        import mimetypes
        mime = mimetypes.guess_type(actual_path)[0] or 'application/octet-stream'
        return send_file(actual_path, mimetype=mime)