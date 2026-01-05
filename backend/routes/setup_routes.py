# routes/setup_routes.py
import os
import sys
import socket
import threading
from flask import Blueprint, request, jsonify, current_app, make_response, send_from_directory

setup_bp = Blueprint('setup', __name__)

# 外部依赖
_ctx = {
    'save_node_config': None,
    'load_node_config': None,
    'FLASK_PORT': 5000,
}


def init_setup_routes(save_node_config, load_node_config, flask_port):
    _ctx['save_node_config'] = save_node_config
    _ctx['load_node_config'] = load_node_config
    _ctx['FLASK_PORT'] = flask_port


@setup_bp.route('/')
def index():
    """首页 - 根据模式返回不同页面"""
    static_folder = current_app.static_folder or 'static'

    if current_app.config.get('SETUP_MODE'):
        response = make_response(send_from_directory(static_folder, "setup.html"))
    else:
        response = make_response(send_from_directory(static_folder, "desktop.html"))

    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@setup_bp.route('/api/setup/save', methods=['POST'])
def save_setup():
    """保存节点配置"""
    try:
        data = request.json
        master_url = data.get('master_url')
        node_id = data.get('node_id')
        shared_secret = data.get('shared_secret')
        local_ip = data.get('ip')
        local_port = data.get('port', _ctx['FLASK_PORT'])

        # 自动获取 IP
        if not local_ip:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(('8.8.8.8', 80))
                local_ip = s.getsockname()[0]
            except:
                local_ip = "127.0.0.1"
            finally:
                s.close()

        if not all([master_url, node_id, shared_secret]):
            return jsonify({'success': False, 'error': '缺少必填参数'}), 400

        config = {
            'master_url': master_url,
            'node_id': node_id,
            'shared_secret': shared_secret,
            'ip': local_ip,
            'port': local_port
        }
        _ctx['save_node_config'](config)

        return jsonify({'success': True, 'message': '配置保存成功'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@setup_bp.route('/api/setup/current-config', methods=['GET'])
def get_current_setup_config():
    """返回当前配置信息（不含密钥）"""
    load_func = _ctx.get('load_node_config')
    if load_func is None:
        return {"error": "load_node_config 未初始化"}, 500
    cfg = load_func()
    if cfg:
        return jsonify({
            'master_url': cfg.get('master_url', ''),
            'node_id': cfg.get('node_id', '')
        })
    return jsonify({})


@setup_bp.route('/api/setup/restart')
def restart_service():
    """重启服务"""
    try:
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>重启中</title>
            <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="bg-gradient-to-br from-purple-500 to-purple-700 min-h-screen flex items-center justify-center">
            <div class="bg-white rounded-2xl shadow-2xl p-12 text-center">
                <div class="text-6xl mb-4">🔄</div>
                <h1 class="text-2xl font-bold text-gray-800 mb-4">正在重启服务...</h1>
                <p class="text-gray-600 mb-4">请稍候,页面将自动跳转</p>
                <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600 mx-auto"></div>
            </div>
            <script>
                setTimeout(() => { window.location.href = '/'; }, 5000);
            </script>
        </body>
        </html>
        """

        def restart():
            import time
            time.sleep(2)
            os.execl(sys.executable, sys.executable, *sys.argv)

        threading.Thread(target=restart, daemon=True).start()
        return html

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500