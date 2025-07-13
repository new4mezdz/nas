import os
import sys
sys.path.append('backend')

from collaboration_v2 import CollaborationV2
from common import BASE_DIRS

# 模拟Flask应用上下文
class MockApp:
    def app_context(self):
        return self
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

# 创建协作系统实例
collab = CollaborationV2(MockApp())

# 测试文件路径查找
test_cases = [
    ("F:/nas_data/周报周报.docx", "周报周报.docx"),
    ("F:/data/documents/20250713_183709_周报15.docx", "20250713_183709_周报15.docx"),
    ("D:/nas_data/test.txt", "test.txt"),
]

print("测试文件路径查找功能:")
print("=" * 50)

for file_path, file_name in test_cases:
    print(f"\n测试路径: {file_path}")
    print(f"文件名: {file_name}")
    
    # 检查原始路径是否存在
    print(f"原始路径存在: {os.path.exists(file_path)}")
    
    # 使用我们的查找函数
    actual_path = collab._find_actual_file_path(file_path, file_name)
    print(f"找到的实际路径: {actual_path}")
    
    if actual_path:
        print(f"实际路径存在: {os.path.exists(actual_path)}")
    else:
        print("未找到文件")

print("\n" + "=" * 50)
print("测试完成") 