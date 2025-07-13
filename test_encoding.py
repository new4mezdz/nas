import requests
import json

# 测试文本文件预览
def test_text_preview():
    # 模拟登录获取token
    login_data = {
        "username": "admin",
        "password": "admin123"
    }
    
    try:
        # 登录
        response = requests.post('http://localhost:5000/api/login', json=login_data)
        if response.status_code == 200:
            token = response.json().get('token')
            print(f"登录成功，获取到token: {token[:20]}...")
            
            # 测试文本文件预览
            headers = {'Authorization': f'Bearer {token}'}
            preview_response = requests.get(
                'http://localhost:5000/api/preview?path=D:/nas_data/test.txt',
                headers=headers
            )
            
            print(f"预览响应状态码: {preview_response.status_code}")
            print(f"预览响应内容: {repr(preview_response.text[:100])}")
            
            if preview_response.status_code == 200:
                print("✅ 文本文件预览成功")
                print(f"内容: {preview_response.text}")
            else:
                print("❌ 文本文件预览失败")
                print(f"错误: {preview_response.text}")
        else:
            print(f"登录失败: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"测试失败: {e}")

if __name__ == "__main__":
    test_text_preview() 