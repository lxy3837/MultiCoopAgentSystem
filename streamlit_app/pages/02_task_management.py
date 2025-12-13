# 核心类：TaskManagementPage（任务管理页核心类）
# 核心函数：create_task_form()、assign_task()、render_task_list()
from datetime import datetime

import streamlit as st
import sys

sys.path.append("../../")
from main import get_agent_context
from data.data_manager import TaskModel, TaskStatus


class TaskManagementPage:
    """任务管理页核心类"""

    def __init__(self):
        self.context = get_agent_context()
        self.data_manager = self.context.state_manager.data_manager

    def create_task_form(self):
        """渲染任务创建表单"""
        with st.form("task_create_form", clear_on_submit=True):
            st.subheader("📝 创建新任务")
            task_name = st.text_input("任务名称", placeholder="请输入任务名称（如：数据处理-001）")
            task_type = st.selectbox("任务类型", ["data_process", "analysis", "notification"])
            task_params = st.text_area("任务参数（JSON格式）", placeholder='{"file_path": "/data/test.csv"}')
            submit_btn = st.form_submit_button("创建并分配任务", type="primary")

            if submit_btn:
                if not task_name or not task_params:
                    st.error("❌ 任务名称和参数不能为空！")
                    return
                # 验证参数（简化版）
                try:
                    import json
                    task_params_dict = json.loads(task_params)
                except:
                    st.error("❌ 参数格式错误，请输入合法JSON！")
                    return
                # 创建任务模型
                task = TaskModel(
                    task_id=f"task_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    name=task_name,
                    type=task_type,
                    params=task_params_dict,
                    status=TaskStatus.PENDING,
                    create_time=datetime.now()
                )
                # 分配任务
                self.assign_task(task)
                st.success(f"✅ 任务 {task.task_id} 创建成功！")

    def assign_task(self, task: TaskModel):
        """分配任务给CoordinatorAgent"""
        coordinator = self.context.coordinator_agent
        coordinator.assign_task(task)
        # 保存任务到数据管理器
        self.data_manager.save_task(task)

    def render_task_list(self):
        """渲染任务列表（按状态筛选）"""
        st.subheader("📋 任务列表")
        # 状态筛选
        status_filter = st.selectbox(
            "筛选状态",
            ["all", "pending", "running", "completed", "failed"]
        )
        # 获取任务列表
        all_tasks = self.data_manager.get_all_tasks()
        if status_filter != "all":
            all_tasks = [t for t in all_tasks if t.status == status_filter]

        # 渲染任务列表
        task_data = []
        for task in all_tasks:
            task_data.append({
                "任务ID": task.task_id,
                "任务名称": task.name,
                "类型": task.type,
                "状态": task.status,
                "创建时间": task.create_time.strftime("%Y-%m-%d %H:%M:%S"),
                "执行Agent": task.executor_agent_id or "-"
            })

        if not task_data:
            st.info("ℹ️ 暂无符合条件的任务！")
            return

        st.dataframe(
            task_data,
            width='stretch',
            column_config={
                "状态": st.column_config.SelectboxColumn(
                    "状态",
                    options=["pending", "running", "completed", "failed"],
                    width="medium"
                )
            },
            hide_index=True
        )

    def render(self):
        """渲染整个任务管理页"""
        st.set_page_config(page_title="任务管理", layout="wide")

        # 分栏：左侧创建任务，右侧任务列表
        col1, col2 = st.columns([1, 2])
        with col1:
            self.create_task_form()
        with col2:
            self.render_task_list()


# 入口执行
if __name__ == "__main__":
    page = TaskManagementPage()
    page.render()