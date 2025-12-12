# 核心函数：init_session_state()、render_homepage()
import streamlit as st
import sys

sys.path.append("../")  # 关联根目录
from main import init_agent_system, get_agent_context


def init_session_state():
    """初始化Streamlit会话状态（全局共享）"""
    if "agent_context" not in st.session_state:
        st.session_state.agent_context = init_agent_system()
    if "sidebar_collapsed" not in st.session_state:
        st.session_state.sidebar_collapsed = False


def render_homepage():
    """渲染首页核心内容"""
    # 页面配置
    st.set_page_config(
        page_title="多Agent协作系统 (MCASys)",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # 加载自定义样式
    with open("styles/custom.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

    # 初始化会话
    init_session_state()
    context = st.session_state.agent_context

    # 首页UI
    st.title("🤖 MCASys 多Agent协作系统")
    st.divider()

    # 系统概览卡片
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("在线Agent数", len(context.state_manager.agents))
    with col2:
        st.metric("待执行任务数", len(context.state_manager.pending_tasks))
    with col3:
        st.metric("已完成任务数", len(context.state_manager.completed_tasks))

    # 快速操作按钮
    st.subheader("快速操作")
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("启动所有Agent", type="primary", use_container_width=True):
            for agent in context.state_manager.agents.values():
                agent.start()
            st.success("✅ 所有Agent已启动！")
    with col_btn2:
        if st.button("停止所有Agent", type="secondary", use_container_width=True):
            for agent in context.state_manager.agents.values():
                agent.stop()
            st.success("🛑 所有Agent已停止！")


# 入口执行
if __name__ == "__main__":
    render_homepage()