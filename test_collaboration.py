#!/usr/bin/env python3
"""
文档协作功能测试脚本
"""

import requests
import json
import time

# 服务器地址
BASE_URL = "http://localhost:5000"

def test_collaboration():
    """测试文档协作功能"""
    
    # 1. 注册两个测试用户
    print("1. 注册测试用户...")
    
    # 用户1
    user1_data = {
        "username": "testuser1",
        "password": "password123"
    }
    
    # 用户2
    user2_data = {
        "username": "testuser2", 
        "password": "password123"
    }
    
    try:
        # 注册用户1
        response = requests.post(f"{BASE_URL}/api/register", json=user1_data)
        print(f"用户1注册: {response.status_code}")
        
        # 注册用户2
        response = requests.post(f"{BASE_URL}/api/register", json=user2_data)
        print(f"用户2注册: {response.status_code}")
        
    except Exception as e:
        print(f"注册失败: {e}")
        return
    
    # 2. 用户1登录
    print("\n2. 用户1登录...")
    try:
        response = requests.post(f"{BASE_URL}/api/login", json=user1_data)
        if response.status_code == 200:
            user1_token = response.json()['token']
            print("用户1登录成功")
        else:
            print(f"用户1登录失败: {response.text}")
            return
    except Exception as e:
        print(f"登录失败: {e}")
        return
    
    # 3. 用户1创建文档
    print("\n3. 创建测试文档...")
    doc_data = {
        "title": "测试协作文档",
        "content": "这是一个测试文档的初始内容。"
    }
    
    headers = {"Authorization": f"Bearer {user1_token}"}
    
    try:
        response = requests.post(f"{BASE_URL}/api/documents", json=doc_data, headers=headers)
        if response.status_code == 200:
            doc_id = response.json()['document_id']
            print(f"文档创建成功，ID: {doc_id}")
        else:
            print(f"文档创建失败: {response.text}")
            return
    except Exception as e:
        print(f"创建文档失败: {e}")
        return
    
    # 4. 用户1分享文档给用户2
    print("\n4. 分享文档给用户2...")
    share_data = {
        "username": "testuser2",
        "permission_type": "write"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/documents/{doc_id}/permissions", 
                               json=share_data, headers=headers)
        if response.status_code == 200:
            print("文档分享成功")
        else:
            print(f"文档分享失败: {response.text}")
    except Exception as e:
        print(f"分享文档失败: {e}")
    
    # 5. 用户2登录
    print("\n5. 用户2登录...")
    try:
        response = requests.post(f"{BASE_URL}/api/login", json=user2_data)
        if response.status_code == 200:
            user2_token = response.json()['token']
            print("用户2登录成功")
        else:
            print(f"用户2登录失败: {response.text}")
            return
    except Exception as e:
        print(f"用户2登录失败: {e}")
        return
    
    # 6. 用户2获取文档列表
    print("\n6. 用户2获取文档列表...")
    headers2 = {"Authorization": f"Bearer {user2_token}"}
    
    try:
        response = requests.get(f"{BASE_URL}/api/documents", headers=headers2)
        if response.status_code == 200:
            documents = response.json()
            print(f"用户2可访问的文档数量: {len(documents)}")
            for doc in documents:
                print(f"  - {doc['title']} (权限: {doc['permission']})")
        else:
            print(f"获取文档列表失败: {response.text}")
    except Exception as e:
        print(f"获取文档列表失败: {e}")
    
    # 7. 用户2获取文档详情
    print("\n7. 用户2获取文档详情...")
    try:
        response = requests.get(f"{BASE_URL}/api/documents/{doc_id}", headers=headers2)
        if response.status_code == 200:
            doc_info = response.json()
            print(f"文档标题: {doc_info['document']['title']}")
            print(f"文档内容: {doc_info['document']['content'][:50]}...")
        else:
            print(f"获取文档详情失败: {response.text}")
    except Exception as e:
        print(f"获取文档详情失败: {e}")
    
    print("\n测试完成！")
    print("现在可以在浏览器中测试实时协作编辑功能。")
    print(f"文档ID: {doc_id}")

if __name__ == "__main__":
    test_collaboration() 