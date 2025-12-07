"""
文档播放器打包脚本
使用 PyInstaller 将 document_player.py 打包成可执行文件
"""

import os
import sys
import subprocess

def install_pyinstaller():
    """安装 PyInstaller"""
    print("正在安装 PyInstaller...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller", "--break-system-packages"])

def build_exe():
    """打包成可执行文件"""
    print("\n开始打包...")

    # PyInstaller 打包命令
    cmd = [
        "pyinstaller",
        "--name=文档播放器",           # 程序名称
        "--onefile",                   # 打包成单个文件
        "--windowed",                  # 不显示控制台窗口（GUI程序）
        "--icon=NONE",                 # 如果有图标文件可以指定
        "4.py"                         # 源文件
    ]

    # 执行打包
    result = subprocess.run(cmd)

    if result.returncode == 0:
        print("\n✅ 打包成功！")
        print(f"可执行文件位置: dist/文档播放器.exe")
    else:
        print("\n❌ 打包失败！")
        return False

    return True

def main():
    print("=" * 50)
    print("文档播放器打包工具")
    print("=" * 50)

    # 检查源文件是否存在
    if not os.path.exists("4.py"):
        print("❌ 错误: 找不到 4.py 文件")
        print("请确保 4.py 和 build.py 在同一目录下")
        return

    # 安装 PyInstaller
    install_pyinstaller()

    # 打包
    if build_exe():
        print("\n" + "=" * 50)
        print("打包完成！")
        print("可执行文件在 dist 文件夹中")
        print("=" * 50)

if __name__ == "__main__":
    main()