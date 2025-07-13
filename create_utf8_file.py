#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# 创建UTF-8编码的测试文件
test_content = "这是一个测试文档，用于验证协作编辑功能。\n包含中文和英文内容。\nThis is a test document for collaboration editing.\n"

# 使用UTF-8编码创建文件
with open("D:\\nas_data\\test_utf8.txt", "w", encoding="utf-8") as f:
    f.write(test_content)

print("✅ 已创建UTF-8编码的测试文件: D:\\nas_data\\test_utf8.txt")
print(f"文件内容: {repr(test_content)}")

# 检查文件编码
with open("D:\\nas_data\\test_utf8.txt", "rb") as f:
    raw_content = f.read()
    print(f"文件大小: {len(raw_content)} 字节")
    print(f"前20字节: {raw_content[:20]}")
    print(f"前20字节(hex): {raw_content[:20].hex()}")
    
    # 尝试解码
    try:
        decoded = raw_content.decode('utf-8')
        print(f"UTF-8解码成功: {repr(decoded)}")
    except Exception as e:
        print(f"UTF-8解码失败: {e}") 