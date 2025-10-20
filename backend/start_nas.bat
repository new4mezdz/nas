@echo off

:: 设置窗口标题
TITLE NAS 控制台

echo [1/3] 正在设置脚本目录...
:: 切换到批处理文件所在的目录 (F:\python\nas\backend)
cd /d "%~dp0"

echo [2/3] 正在激活 Python 虚拟环境...
call venv\Scripts\activate.bat

echo [3/3] 正在以管理员权限启动主程序...
echo ========================================

:: 运行 Python 主程序
python app.py

echo ========================================
echo 程序已退出，按任意键关闭此窗口。
pause