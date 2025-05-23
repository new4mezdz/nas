import os
from flask import Blueprint, request, jsonify, send_file
from app import token_required, BASE_DIR

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
        abs_path = safe_join(BASE_DIR, req_path.lstrip("/\\"))
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
    try:
        abs_path = safe_join(BASE_DIR, req_path.lstrip("/\\"))
    except Exception:
        return jsonify({"error": "路径非法"}), 400
    if not os.path.isfile(abs_path):
        return jsonify({"error": "文件不存在"}), 404
    return send_file(abs_path, as_attachment=True)

@file_bp.route('/upload', methods=['POST'])
@token_required()
def upload_file():
    req_path = request.form.get('path', '/')
    try:
        abs_path = safe_join(BASE_DIR, req_path.lstrip("/\\"))
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
        parent_abs = safe_join(BASE_DIR, parent.lstrip("/\\"))
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
    try:
        abs_path = safe_join(BASE_DIR, path.lstrip("/\\"))
        if not os.path.exists(abs_path):
            return jsonify({"error": "文件不存在"}), 404
        if os.path.isdir(abs_path):
            import shutil
            shutil.rmtree(abs_path)
        else:
            os.remove(abs_path)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@file_bp.route('/rename', methods=['POST'])
@token_required(admin_only=True)
def rename_entry():
    data = request.json
    path = data.get('path')
    new_name = data.get('new_name')
    if not path or not new_name:
        return jsonify({"error": "参数缺失"}), 400
    try:
        abs_path = safe_join(BASE_DIR, path.lstrip("/\\"))
        if not os.path.exists(abs_path):
            return jsonify({"error": "文件不存在"}), 404
        new_abs = os.path.join(os.path.dirname(abs_path), new_name)
        os.rename(abs_path, new_abs)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
