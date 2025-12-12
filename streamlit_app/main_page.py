# 核心函数：init_session_state()、render_homepage()
import streamlit as st
import sys
import os
from pathlib import Path

# 修复：改为绝对路径（解决不同运行目录下的模块导入问题）
ROOT_DIR = Path(__file__).parent.parent  # 定位到项目根目录（MCASys/）
sys.path.append(str(ROOT_DIR))

from main import init_agent_system, get_agent_context
from utils.logger import get_logger  # 新增：日志
from data.models import TaskStatus  # 新增：任务状态枚举

# 初始化日志
logger = get_logger("streamlit_homepage")

def init_session_state():
    """初始化Streamlit会话状态（全局共享），增加异常处理+加载提示"""
    # 1. 加载状态提示（优化用户体验）
    if "agent_context_loading" not in st.session_state:
        st.session_state.agent_context_loading = False

    # 2. 初始化Agent上下文（捕获异常，避免页面崩溃）
    if "agent_context" not in st.session_state:
        st.session_state.agent_context_loading = True
        try:
            with st.spinner("📌 正在初始化Agent系统..."):
                st.session_state.agent_context = init_agent_system()
            logger.info("Agent系统初始化成功（Streamlit会话）")
        except Exception as e:
            st.error(f"❌ Agent系统初始化失败：{str(e)}", icon="🚨")
            logger.error(f"Agent系统初始化失败：{e}", exc_info=True)
            st.session_state.agent_context = None
        finally:
            st.session_state.agent_context_loading = False

    # 3. 侧边栏状态（补充默认值，后续可扩展折叠功能）
    if "sidebar_collapsed" not in st.session_state:
        st.session_state.sidebar_collapsed = False

    # 4. 任务状态筛选（新增：为后续功能预留）
    if "task_status_filter" not in st.session_state:
        st.session_state.task_status_filter = TaskStatus.PENDING

def render_homepage():
    """渲染首页核心内容（优化路径+功能+体验）"""
    # 关键：st.set_page_config 必须放在所有Streamlit命令最前面
    st.set_page_config(
        page_title="多Agent协作系统 (MCASys)",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # 加载自定义样式（修复路径+兜底逻辑）
    css_path = ROOT_DIR / "streamlit_app" / "styles" / "custom.css"
    try:
        with open(css_path, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        logger.warning(f"自定义样式文件未找到：{css_path}，使用默认样式")
        st.warning("⚠️ 自定义样式文件缺失，将使用默认样式", icon="ℹ️")
    except Exception as e:
        logger.error(f"加载样式文件失败：{e}", exc_info=True)

    # 初始化会话状态
    init_session_state()

    # 校验Agent上下文是否初始化成功
    if st.session_state.agent_context is None:
        st.stop()  # 初始化失败时停止渲染

    context = st.session_state.agent_context

    # 首页UI
    st.title("🤖 MCASys 多Agent协作系统")
    st.divider()

    # 系统概览卡片（补充失败任务数，与StateManager对齐）
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            label="在线Agent数",
            value=len(context.state_manager.agents),
            help="已注册到系统的Agent总数"
        )
    with col2:
        st.metric(
            label="待执行任务数",
            value=len(context.state_manager.pending_tasks),
            help=f"状态为「{TaskStatus.PENDING}」的任务数"
        )
    with col3:
        st.metric(
            label="已完成任务数",
            value=len(context.state_manager.completed_tasks),
            help=f"状态为「{TaskStatus.COMPLETED}」的任务数"
        )
    with col4:
        st.metric(
            label="失败任务数",
            value=len(context.state_manager.failed_tasks),  # 新增：失败任务数
            help=f"状态为「{TaskStatus.FAILED}」的任务数",
            delta_color="inverse"
        )

    # 快速操作按钮（优化交互+日志+状态刷新）
    st.subheader("快速操作")
    col_btn1, col_btn2, col_btn3 = st.columns(3)  # 新增刷新按钮
    with col_btn1:
        if st.button("启动所有Agent", type="primary", use_container_width=True, disabled=st.session_state.agent_context_loading):
            try:
                agent_count = 0
                for agent in context.state_manager.agents.values():
                    agent.start()
                    agent_count += 1
                st.success(f"✅ 成功启动 {agent_count} 个Agent！", icon="✅")
                logger.info(f"用户手动启动所有Agent，共启动{agent_count}个")
                # 刷新页面（同步状态）
                st.rerun()
            except Exception as e:
                st.error(f"❌ 启动Agent失败：{str(e)}", icon="🚨")
                logger.error(f"启动Agent失败：{e}", exc_info=True)

    with col_btn2:
        if st.button("停止所有Agent", type="secondary", use_container_width=True, disabled=st.session_state.agent_context_loading):
            try:
                agent_count = 0
                for agent in context.state_manager.agents.values():
                    agent.stop()  # 需确保BaseAgent实现stop方法
                    agent_count += 1
                st.success(f"🛑 成功停止 {agent_count} 个Agent！", icon="🛑")
                logger.info(f"用户手动停止所有Agent，共停止{agent_count}个")
                st.rerun()
            except Exception as e:
                st.error(f"❌ 停止Agent失败：{str(e)}", icon="🚨")
                logger.error(f"停止Agent失败：{e}", exc_info=True)

    with col_btn3:
        if st.button("刷新系统状态", type="secondary", use_container_width=True):
            try:
                # 刷新任务列表+Agent状态
                context.state_manager._refresh_task_lists()
                for agent in context.state_manager.agents.values():
                    context.state_manager.sync_agent_state(agent.agent_id)
                st.success("🔄 系统状态已刷新！", icon="🔄")
                logger.info("用户手动刷新系统状态")
                st.rerun()
            except Exception as e:
                st.error(f"❌ 刷新状态失败：{str(e)}", icon="🚨")
                logger.error(f"刷新系统状态失败：{e}", exc_info=True)

    # 新增：系统状态说明（提升透明度）
    with st.expander("📋 系统状态详情", expanded=False):
        st.write(f"**系统初始化时间**：{context.state_manager.updated_at.strftime('%Y-%m-%d %H:%M:%S')}")
        st.write(f"**已注册Agent列表**：{list(context.state_manager.agents.keys())}")
        st.write(f"**任务总数**：{len(context.state_manager.pending_tasks) + len(context.state_manager.running_tasks) + len(context.state_manager.completed_tasks) + len(context.state_manager.failed_tasks)}")


# 入口执行（增加防护）
if __name__ == "__main__":
    try:
        render_homepage()
    except Exception as e:
        st.error(f"💥 页面渲染失败：{str(e)}", icon="💥")
        logger.critical(f"Streamlit首页渲染失败：{e}", exc_info=True)