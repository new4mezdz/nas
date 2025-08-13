# show_structure.py - 显示项目结构
import os


def show_tree(path, prefix="", max_depth=3, current_depth=0):
    """显示目录树结构"""
    if current_depth > max_depth:
        return

    try:
        items = sorted(os.listdir(path))
        for i, item in enumerate(items):
            if item.startswith('.'):  # 跳过隐藏文件
                continue

            item_path = os.path.join(path, item)
            is_last = (i == len(items) - 1)

            # 显示当前项目
            connector = "└── " if is_last else "├── "
            print(f"{prefix}{connector}{item}")

            # 如果是目录，递归显示
            if os.path.isdir(item_path) and current_depth < max_depth:
                extension = "    " if is_last else "│   "
                show_tree(item_path, prefix + extension, max_depth, current_depth + 1)

    except PermissionError:
        print(f"{prefix}└── [权限不足]")


def main():
    print("📁 项目结构:")
    print("=" * 50)

    # 显示当前目录
    current_dir = os.getcwd()
    print(f"当前目录: {current_dir}")
    print(f"项目根目录: {os.path.basename(current_dir)}")
    print()

    # 显示目录树
    show_tree(".")

    # 显示一些关键文件的详细信息
    print("\n" + "=" * 50)
    print("🔍 关键文件检查:")

    key_files = [
        'app.py',
        'backend/app.py',
        'client/pwa/manifest.json',
        'client/pwa/sw.js',
        'static/index.html',
        'static/app.js',
        'static/pwa/icons/icon-192.png'
    ]

    for file_path in key_files:
        if os.path.exists(file_path):
            if os.path.isfile(file_path):
                size = os.path.getsize(file_path)
                print(f"✅ {file_path} ({size} bytes)")
            else:
                print(f"📁 {file_path} (目录)")
        else:
            print(f"❌ {file_path} (不存在)")


if __name__ == "__main__":
    main()