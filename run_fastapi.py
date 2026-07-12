#!/usr/bin/env python3
"""
直接运行FastAPI应用的脚本
"""
import uvicorn
from app import app

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
