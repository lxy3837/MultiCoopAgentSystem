#!/usr/bin/env python3
"""
启动脚本：同时启动Streamlit前端和FastAPI后端
"""
import subprocess
import sys
import os
import time
from pathlib import Path


def start_streamlit():
    """启动Streamlit前端"""
    streamlit_cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "streamlit_app/main_page.py",
        "--server.port",
        "8501",
        "--server.address",
        "0.0.0.0"
    ]
    
    print("🚀 正在启动Streamlit前端...")
    return subprocess.Popen(
        streamlit_cmd,
        cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )


def start_fastapi():
    """启动FastAPI后端"""
    fastapi_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--reload"
    ]
    
    print("🚀 正在启动FastAPI后端...")
    return subprocess.Popen(
        fastapi_cmd,
        cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )


def print_status(streamlit_proc, fastapi_proc):
    """打印服务状态"""
    print("\n" + "="*50)
    print("📋 服务状态")
    print("="*50)
    print(f"Streamlit前端: {'运行中' if streamlit_proc.poll() is None else '已停止'}")
    print(f"  访问地址: http://localhost:8501")
    print(f"FastAPI后端: {'运行中' if fastapi_proc.poll() is None else '已停止'}")
    print(f"  API文档: http://localhost:8000/docs")
    print(f"  访问地址: http://localhost:8000")
    print("="*50 + "\n")


def main():
    """主函数"""
    global ROOT_DIR
    ROOT_DIR = Path(__file__).parent
    
    print("🌟 MCASys - 多Agent协作系统")
    print("📦 正在启动全栈服务...\n")
    
    # 启动服务
    streamlit_proc = start_streamlit()
    fastapi_proc = start_fastapi()
    
    # 等待服务启动
    time.sleep(3)
    
    # 打印状态
    print_status(streamlit_proc, fastapi_proc)
    
    try:
        # 持续监控服务
        while True:
            time.sleep(5)
            
            # 检查服务状态
            if streamlit_proc.poll() is not None:
                print("❌ Streamlit前端已停止!")
                print("日志:")
                print(streamlit_proc.stderr.read())
                break
                
            if fastapi_proc.poll() is not None:
                print("❌ FastAPI后端已停止!")
                print("日志:")
                print(fastapi_proc.stderr.read())
                break
                
    except KeyboardInterrupt:
        print("\n🛑 正在停止服务...")
        streamlit_proc.terminate()
        fastapi_proc.terminate()
        
        # 等待进程结束
        streamlit_proc.wait()
        fastapi_proc.wait()
        
        print("✅ 所有服务已停止")


if __name__ == "__main__":
    main()
