#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os

# 创建测试文件
test_content = "这是一个测试文档，用于验证协作编辑功能。\n包含中文和英文内容。\nThis is a test document for collaboration editing.\n"

# 使用UTF-8编码创建文件
with open("D:\\nas_data\\test_utf8.txt", "w", encoding="utf-8") as f:
    f.write(test_content)

# 使用GBK编码创建文件
with open("D:\\nas_data\\test_gbk.txt", "w", encoding="gbk") as f:
    f.write(test_content)

print("测试文件已创建：")
print("- D:\\nas_data\\test_utf8.txt (UTF-8编码)")
print("- D:\\nas_data\\test_gbk.txt (GBK编码)") 