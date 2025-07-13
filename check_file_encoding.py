#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os

def check_file_encoding(file_path):
    """检查文件的编码和内容"""
    print(f"检查文件: {file_path}")
    
    if not os.path.exists(file_path):
        print("文件不存在")
        return
    
    # 读取二进制内容
    with open(file_path, 'rb') as f:
        raw_content = f.read()
    
    print(f"文件大小: {len(raw_content)} 字节")
    print(f"前20字节: {raw_content[:20]}")
    print(f"前20字节(hex): {raw_content[:20].hex()}")
    
    # 尝试不同编码
    encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'big5', 'latin-1']
    
    for encoding in encodings:
        try:
            content = raw_content.decode(encoding)
            print(f"\n编码 {encoding} 成功:")
            print(f"内容: {repr(content)}")
            print(f"长度: {len(content)}")
            if len(content) > 0:
                print(f"前50字符: {content[:50]}")
            break
        except UnicodeDecodeError as e:
            print(f"编码 {encoding} 失败: {e}")
    else:
        print("\n所有编码都失败，尝试替换模式:")
        try:
            content = raw_content.decode('utf-8', errors='replace')
            print(f"替换模式内容: {repr(content)}")
        except Exception as e:
            print(f"替换模式也失败: {e}")

if __name__ == "__main__":
    # 检查测试文件
    check_file_encoding("D:\\nas_data\\test.txt")
    
    # 创建新的测试文件
    test_content = "这是一个测试文档，用于验证协作编辑功能。\n包含中文和英文内容。\nThis is a test document for collaboration editing.\n"
    
    # 使用UTF-8创建
    with open("D:\\nas_data\\test_utf8.txt", "w", encoding="utf-8") as f:
        f.write(test_content)
    
    print("\n" + "="*50)
    print("创建了新的测试文件，检查编码:")
    check_file_encoding("D:\\nas_data\\test_utf8.txt") 