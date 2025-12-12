@echo off
:: 切换编码为UTF-8，避免中文乱码
chcp 65001 > nul 2>&1
echo ==============================================
echo          开始创建MCASys项目结构
echo ==============================================

:: 定义项目根目录（当前运行脚本的目录，即MCASys）
set "ROOT=%cd%"

:: 1. 创建所有目录
echo [1/2] 正在创建目录结构...
md "%ROOT%\streamlit_app" > nul 2>&1
md "%ROOT%\streamlit_app\pages" > nul 2>&1
md "%ROOT%\streamlit_app\styles" > nul 2>&1
md "%ROOT%\agents" > nul 2>&1
md "%ROOT%\collaboration" > nul 2>&1
md "%ROOT%\config" > nul 2>&1
md "%ROOT%\data" > nul 2>&1
md "%ROOT%\utils" > nul 2>&1
md "%ROOT%\tests" > nul 2>&1

:: 2. 创建所有空文件
echo [2/2] 正在创建空文件...
:: Streamlit相关文件
type nul > "%ROOT%\streamlit_app\main_page.py"
type nul > "%ROOT%\streamlit_app\pages\01_agent_status.py"
type nul > "%ROOT%\streamlit_app\pages\02_task_management.py"
type nul > "%ROOT%\streamlit_app\pages\03_system_logs.py"
type nul > "%ROOT%\streamlit_app\styles\custom.css"

:: 依赖文件（自动写入基础依赖，无需手动加）
type nul > "%ROOT%\requirements.txt"
echo streamlit>=1.35.0 >> "%ROOT%\requirements.txt"
echo python-multipart>=0.0.9 >> "%ROOT%\requirements.txt"
echo websockets>=12.0 >> "%ROOT%\requirements.txt"
echo pyyaml>=6.0.1 >> "%ROOT%\requirements.txt"
echo loguru>=0.7.2 >> "%ROOT%\requirements.txt"

echo ==============================================
echo ✅ 项目结构创建完成！
echo 📁 已创建目录：
echo   - streamlit_app/ (含pages、styles子目录)
echo   - agents/
echo   - collaboration/
echo   - config/
echo   - data/
echo   - utils/
echo   - tests/
echo 📄 已创建空文件：
echo   - streamlit_app/main_page.py
echo   - streamlit_app/pages/01_agent_status.py
echo   - streamlit_app/pages/02_task_management.py
echo   - streamlit_app/pages/03_system_logs.py
echo   - streamlit_app/styles/custom.css
echo   - requirements.txt (已写入基础依赖)
echo ==============================================
pause