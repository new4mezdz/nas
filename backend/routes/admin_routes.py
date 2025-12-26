# routes/admin_routes.py
import requests
from datetime import datetime
from flask import Blueprint, request, jsonify

from permission_decorator import permission_required

admin_bp = Blueprint('admin', __name__)

# 存储待处理的访问申请
pending_requests = {}

# 外部依赖
_ctx = {
    'NAS_CENTER_API_URL': None,
    'NAS_SHARED_SECRET': None,
}


def init_admin_routes(center_api_url, shared_secret):
    _ctx['NAS_CENTER_API_URL'] = center_api_url
    _ctx['NAS_SHARED_SECRET'] = shared_secret


@admin_bp.route('/api/internal/access-request', methods=['POST'])
def receive_access_request():
    """接收来自管理端的访问申请"""
    data = request.json

    secret = request.headers.get('X-NAS-Secret')
    if secret != _ctx['NAS_SHARED_SECRET']:
        return jsonify({"success": False, "message": "未授权的请求"}), 403

    request_id = data.get('request_id')
    username = data.get('username')
    requested_permission = data.get('permission')
    node_id = data.get('node_id')

    if not all([request_id, username, requested_permission, node_id]):
        return jsonify({"success": False, "message": "缺少必要参数"}), 400

    pending_requests[request_id] = {
        'username': username,
        'permission': requested_permission,
        'node_id': node_id,
        'status': 'pending',
        'created_at': datetime.now().isoformat()
    }

    print(f"[访问申请] 收到用户 {username} 的访问申请 (权限: {requested_permission})")

    return jsonify({
        "success": True,
        "message": "访问申请已接收",
        "request_id": request_id
    })


@admin_bp.route('/api/admin/access-requests', methods=['GET'])
@permission_required('fullcontrol')
def get_pending_requests():
    """管理员查看待处理的访问申请"""
    return jsonify({
        "success": True,
        "requests": [
            {"request_id": req_id, **req_data}
            for req_id, req_data in pending_requests.items()
            if req_data['status'] == 'pending'
        ]
    })


@admin_bp.route('/api/admin/access-requests/<request_id>/approve', methods=['POST'])
@permission_required('fullcontrol')
def approve_access_request(request_id):
    """管理员批准访问申请"""
    if request_id not in pending_requests:
        return jsonify({"success": False, "message": "申请不存在"}), 404

    request_data = pending_requests[request_id]
    request_data['status'] = 'approved'
    request_data['approved_at'] = datetime.now().isoformat()

    try:
        response = requests.post(
            f"{_ctx['NAS_CENTER_API_URL']}/api/internal/access-approved",
            json={
                "request_id": request_id,
                "username": request_data['username'],
                "node_id": request_data['node_id']
            },
            headers={"X-NAS-Secret": _ctx['NAS_SHARED_SECRET']},
            timeout=5
        )

        if response.status_code == 200:
            print(f"[访问申请] 已通知管理端：用户 {request_data['username']} 的申请已批准")
            return jsonify({"success": True, "message": "申请已批准"})
        else:
            return jsonify({"success": False, "message": "通知管理端失败"}), 500

    except Exception as e:
        print(f"[错误] 通知管理端失败: {e}")
        return jsonify({"success": False, "message": f"通知失败: {str(e)}"}), 500


@admin_bp.route('/api/admin/access-requests/<request_id>/reject', methods=['POST'])
@permission_required('fullcontrol')
def reject_access_request(request_id):
    """管理员拒绝访问申请"""
    if request_id not in pending_requests:
        return jsonify({"success": False, "message": "申请不存在"}), 404

    request_data = pending_requests[request_id]
    reason = request.json.get('reason', '管理员拒绝')

    request_data['status'] = 'rejected'
    request_data['rejected_at'] = datetime.now().isoformat()
    request_data['reject_reason'] = reason

    try:
        response = requests.post(
            f"{_ctx['NAS_CENTER_API_URL']}/api/internal/access-rejected",
            json={
                "request_id": request_id,
                "username": request_data['username'],
                "node_id": request_data['node_id'],
                "reason": reason
            },
            headers={"X-NAS-Secret": _ctx['NAS_SHARED_SECRET']},
            timeout=5
        )

        if response.status_code == 200:
            print(f"[访问申请] 已通知管理端：用户 {request_data['username']} 的申请已拒绝")
            return jsonify({"success": True, "message": "申请已拒绝"})
        else:
            return jsonify({"success": False, "message": "通知管理端失败"}), 500

    except Exception as e:
        print(f"[错误] 通知管理端失败: {e}")
        return jsonify({"success": False, "message": f"通知失败: {str(e)}"}), 500