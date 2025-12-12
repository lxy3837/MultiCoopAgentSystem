# 核心类：SystemLogsPage（日志页核心类）
# 核心函数：render_log_stream()、filter_logs()
import streamlit as st
import sys

sys.path.append("../../")
from utils.logger import get_logger
from main import get_agent_context


class SystemLogsPage:
    """系统日志页核心类"""

    def __init__(self):
        self.logger = get_logger("system_logs")
        self.context = get_agent_context()
        self.log_file_path = self.context.config.log_config["file_path"]

    def filter_logs(self, logs: list, level: str, keyword: str):
        """过滤日志（按级别/关键词）"""
        filtered = logs
        if level != "all":
            filtered = [l for l in filtered if level.upper() in l]
        if keyword:
            filtered = [l for l in filtered if keyword in l]
        return filtered

    def render_log_stream(self):
        """实时渲染日志流"""
        # 日志筛选控件
        col1, col2 = st.columns([1, 3])
        with col1:
            log_level = st.selectbox("日志级别", ["all", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        with col2:
            log_keyword = st.text_input("关键词筛选", placeholder="输入关键词搜索日志...")

        # 读取日志文件（实时刷新）
        try:
            with open(self.log_file_path, "r", encoding="utf-8") as f:
                logs = f.readlines()[-1000:]  # 只显示最后1000行
        except FileNotFoundError:
            st.warning("⚠️ 日志文件尚未生成，请先操作系统！")
            return

        # 过滤日志
        filtered_logs = self.filter_logs(logs, log_level, log_keyword)

        # 渲染日志（滚动容器）
        st.subheader("实时日志流")
        with st.container(height=600):
            for log in filtered_logs:
                # 按日志级别上色
                if "ERROR" in log or "CRITICAL" in log:
                    st.markdown(f"<span style='color:red;'>{log}</span>", unsafe_allow_html=True)
                elif "WARNING" in log:
                    st.markdown(f"<span style='color:orange;'>{log}</span>", unsafe_allow_html=True)
                elif "INFO" in log:
                    st.markdown(f"<span style='color:green;'>{log}</span>", unsafe_allow_html=True)
                else:
                    st.text(log)

    def render(self):
        """渲染整个日志页"""
        st.set_page_config(page_title="系统日志", layout="wide")
        st.title("📜 系统日志")
        st.divider()

        # 自动刷新（和日志同步）
        st.markdown("<meta http-equiv='refresh' content='2'>", unsafe_allow_html=True)

        # 渲染日志流
        self.render_log_stream()


# 入口执行
if __name__ == "__main__":
    page = SystemLogsPage()
    page.render()