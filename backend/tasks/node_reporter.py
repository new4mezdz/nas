# tasks/node_reporter.py
# -*- coding: utf-8 -*-
"""
节点上报后台任务
- 向管理端注册节点
- 定期上报磁盘信息
- 定期获取管理端配置
"""

import time
import threading
import requests
import psutil

from config import runtime_config, NODE_CONFIG_PATH, FLASK_PORT


def load_node_config():
    """加载节点配置"""
    import os
    import json
    if os.path.exists(NODE_CONFIG_PATH):
        with open(NODE_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def save_node_config(config):
    """保存节点配置"""
    import json
    with open(NODE_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def collect_disks():
    """收集磁盘信息"""
    disks = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "mount": part.mountpoint,
                "status": "online",
                "capacity_gb": round(usage.total / (1024**3), 2),
                "is_encrypted": 0,
                "is_locked": 0
            })
        except Exception:
            continue
    return disks


def register_to_master():
    """客户端启动时主动向主控端注册"""
    try:
        # 从配置文件读取IP和端口
        node_config = load_node_config()
        
        if node_config and 'ip' in node_config:
            local_ip = node_config['ip']
            local_port = node_config.get('port', FLASK_PORT)
            print(f"[使用配置] IP={local_ip}, Port={local_port}")
        else:
            print("⚠️  警告：node_config.json 中未配置 'ip' 字段")
            import socket
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            local_port = FLASK_PORT
            print(f"⚠️  自动获取的IP可能不准确: {local_ip}")
        
        data = {
            "node_id": runtime_config.this_node_id,
            "ip": local_ip,
            "port": local_port,
            "status": "online"
        }
        
        res = requests.post(
            f"{runtime_config.nas_center_api_url}/api/nodes/register",
            json=data,
            headers={'X-NAS-Secret': runtime_config.nas_shared_secret},
            timeout=5
        )
        
        if res.status_code == 200:
            print(f"[注册成功] 节点ID={runtime_config.this_node_id}")
            # 启动磁盘上报线程
            threading.Thread(target=report_disks, daemon=True).start()
        else:
            print(f"[注册失败] 管理端返回状态 {res.status_code}: {res.text}")
    except Exception as e:
        print(f"[注册异常] 无法连接管理端: {e}")
        import traceback
        traceback.print_exc()


def report_disks():
    """每隔 60 秒上报一次磁盘信息"""
    while True:
        try:
            payload = {
                "node_id": runtime_config.this_node_id,
                "disks": collect_disks()
            }
            res = requests.post(
                f"{runtime_config.nas_center_api_url}/api/nodes/update-disks",
                json=payload,
                headers={'X-NAS-Secret': runtime_config.nas_shared_secret},
                timeout=5
            )
            print(f"[节点上报] {runtime_config.this_node_id}: {res.status_code}")
        except Exception as e:
            print(f"[节点上报失败] {e}")
        time.sleep(60)


def fetch_nas_center_config():
    """
    启动时从管理端获取配置 (如公网URL)
    """
    target_url = f"{runtime_config.nas_center_api_url}/api/ngrok-url"
    
    print(f"🔗  正在从管理端 {runtime_config.nas_center_api_url} 获取公网地址...")
    
    max_retries = 30  # 最多重试30次 (约5分钟)
    for i in range(max_retries):
        try:
            response = requests.get(target_url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('url'):
                    runtime_config.nas_center_public_url = data['url']
                    print(f"✅  成功获取公网地址: {runtime_config.nas_center_public_url}")
                    return True
                else:
                    print(f"⚠️  管理端返回了数据，但缺少 'url' 字段。")
            else:
                print(f"⚠️  管理端返回状态 {response.status_code}。")
                
        except requests.ConnectionError:
            print(f"🔌  无法连接到管理端... ({i + 1}/{max_retries})")
        except Exception as e:
            print(f"❌  获取配置时发生错误: {e}")
        
        if i < max_retries - 1:
            print(f"   将在 10 秒后重试...")
            time.sleep(10)
    
    print("❌  获取管理端配置失败。公网分享功能将不可用。")
    return False


def update_nas_center_url_periodically():
    """定期更新管理端公网地址(每5分钟)"""
    while True:
        time.sleep(300)  # 5分钟
        try:
            fetch_nas_center_config()
        except Exception as e:
            print(f"⚠️ 更新管理端地址失败: {e}")


def start_reporter_threads():
    """启动所有上报相关的后台线程"""
    # 启动定期更新公网地址线程
    update_thread = threading.Thread(target=update_nas_center_url_periodically, daemon=True)
    update_thread.start()
    print("✅  已启动公网地址定期更新任务(每5分钟)")
