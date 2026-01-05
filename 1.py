import os

target_dir = r"D:\9090\nas\static\images\help"

# 映射表
file_mapping = {
    "desktop-main.png": "desktop-overview.png",
    "2.png":            "desktop-search-bar.png",
    "3.png":            "files-manager-main.png",
    "4.png":            "files-editor-univer.png",
    "5.png":            "files-share-link.png",
    "6.png":            "pool-management.png",
    "7.png":            "disk-encryption-console.png",
    "8.png":            "disk-ec-raid-config.png",
    "9.png":            "system-info-dashboard.png",
    "bg-settings.png":  "settings-background.png"
}

if not os.path.exists(target_dir):
    print(f"错误: 目录不存在 {target_dir}")
    exit()

print(f"正在处理目录: {target_dir}\n")

for old_name, new_name in file_mapping.items():
    old_path = os.path.join(target_dir, old_name)
    new_path = os.path.join(target_dir, new_name)

    if os.path.exists(old_path):
        try:
            os.rename(old_path, new_path)
            print(f"[成功] {old_name} -> {new_name}")
        except Exception as e:
            print(f"[错误] 重命名 {old_name} 失败: {e}")
    elif os.path.exists(new_path):
        print(f"[跳过] {new_name} 已存在")
    else:
        print(f"[警告] 源文件未找到: {old_name}")

print("\n完成。")