# 核心类：AgentStatusPage（封装状态页逻辑）
# 核心函数：render_agent_status_table()、auto_refresh()
import streamlit as st
import sys
from datetime import datetime

sys.path.append("../../")
from main import get_agent_context


class AgentStatusPage:
    """Agent状态监控页核心类"""

    def __init__(self):
        self.context = get_agent_context()
        self.auto_refresh_seconds = 2  # 自动刷新间隔

    def auto_refresh(self):
        """页面自动刷新（实时展示状态）"""
        st.markdown(
            f"""<meta http-equiv="refresh" content="{self.auto_refresh_seconds}">""",
            unsafe_allow_html=True
        )

    def render_agent_status_table(self):
        """渲染Agent状态表格（带可视化）"""
        agent_data = []
        for agent_id, agent in self.context.state_manager.agents.items():
            agent_data.append({
                "Agent ID": agent_id,
                "类型": agent.agent_type,
                "状态": agent.state.status,
                "负载率": f"{agent.state.load:.1%}",
                "最后更新": agent.state.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                "错误信息": agent.state.error_msg or "-"
            })

        if not agent_data:
            st.warning("⚠️ 暂无Agent数据，请先启动Agent系统！")
            return

        # 渲染表格（带进度条/标签可视化）
        st.dataframe(
            agent_data,
            width='stretch',
            column_config={
                "状态": st.column_config.SelectboxColumn(
                    "状态",
                    options=["idle", "running", "error", "stopped"],
                    default="idle",
                    width="medium"
                ),
                "负载率": st.column_config.ProgressColumn(
                    "负载率",
                    format="%.1f%%",
                    min_value=0,
                    max_value=100,
                    width="medium"
                ),
                "错误信息": st.column_config.TextColumn("错误信息", width="large")
            },
            hide_index=True
        )

    def render(self):
        """渲染整个状态页"""
        st.set_page_config(page_title="Agent状态监控", layout="wide")
        self.auto_refresh()

        # 页面标题
        st.title("🕵️ Agent状态监控")
        st.divider()

        # 渲染状态表格
        st.subheader("Agent实时状态")
        self.render_agent_status_table()

        # 单个Agent操作
        st.subheader("单个Agent操作")
        selected_agent = st.selectbox(
            "选择Agent",
            list(self.context.state_manager.agents.keys()),
            placeholder="请选择要操作的Agent..."
        )
        if selected_agent:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("重启Agent", type="primary"):
                    agent = self.context.state_manager.agents[selected_agent]
                    agent.stop()
                    agent.start()
                    st.success(f"✅ Agent {selected_agent} 已重启！")
            with col2:
                if st.button("查看详情", type="secondary"):
                    agent = self.context.state_manager.agents[selected_agent]
                    with st.expander(f"Agent {selected_agent} 详情"):
                        st.json(agent.state.model_dump())


# 入口执行
if __name__ == "__main__":
    page = AgentStatusPage()
    page.render()