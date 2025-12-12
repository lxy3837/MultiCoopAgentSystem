MCASys 多Agent协作系统

基于 Python + Streamlit 开发的轻量、可扩展多Agent协作系统，提供可视化Web UI，支持Agent状态监控、任务创建与分配、系统日志追踪等核心能力，适合快速验证多Agent协作逻辑或小范围内部使用。

📋 项目概述

核心定位

以「轻量化、高开发效率、易扩展」为目标，实现多Agent的协同工作与可视化管理，无需前端开发经验即可通过纯Python完成全流程搭建。

技术栈

- 后端核心：Python 3.9+（多Agent逻辑、任务调度）

- Web UI：Streamlit（快速构建交互式界面，支持实时刷新）

- 数据模型：Pydantic（结构化数据校验与管理）

- 日志工具：Loguru（统一日志输出，支持UI实时展示）

- 配置管理：PyYAML（灵活的配置文件管理）

核心能力

1. Agent全生命周期管理：启动/停止/重启，实时监控状态（负载、运行状态等）

2. 任务可视化管理：创建任务、配置参数、分配给指定Agent执行

3. 系统日志追踪：按级别筛选日志，实时查看Agent运行与任务执行详情

4. 模块化扩展：新增Agent类型、任务分配算法无需修改核心框架

🚀 快速开始

1. 环境准备

1.1 安装Python

要求Python版本 ≥ 3.9，推荐3.10版本。下载地址：Python官方下载

1.2 克隆/下载项目

# 克隆项目（若使用Git）
git clone https://github.com/lxy3837/MultiCoopAgentSystem
cd MCASys

1.3 安装依赖

使用pip安装项目所需依赖，建议先创建虚拟环境隔离依赖：

# 创建虚拟环境（Windows）
python -m venv venv
venv\Scripts\activate

# 创建虚拟环境（Linux/macOS）
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

2. 配置系统（可选）

修改 config/config.yaml 配置文件，自定义Agent参数、日志路径、UI刷新间隔等：

# 示例配置
logging:
  level: "INFO"  # 日志级别：DEBUG/INFO/WARNING/ERROR
  file_path: "./logs/system.log"  # 日志存储路径
  rotation: "100MB"  # 日志文件滚动大小
  retention: "7 days"  # 日志保留时间

agent:
  default_load_threshold: 0.8  # Agent负载阈值（超过则不分配任务）
  auto_start: True  # 系统启动时自动启动所有Agent

streamlit:
  refresh_interval: 2  # UI自动刷新间隔（秒）

3. 启动系统

在项目根目录执行以下命令启动Streamlit Web UI：

streamlit run streamlit_app/main_page.py

启动成功后，浏览器会自动打开页面，默认访问地址：http://localhost:8501

📂 项目结构

目录/文件

核心内容

作用说明

main.py

Agent系统初始化入口

创建全局Agent上下文，初始化状态管理器与核心Agent

streamlit_app/

Web UI相关代码

包含首页、Agent状态页、任务管理页等可视化模块

agents/

Agent核心模块

BaseAgent基类 + specialized_agents专用Agent子包（协调/执行/分析Agent）

collaboration/

协作逻辑模块

状态管理、任务分配、Agent通信、冲突解决等核心协作能力

config/

配置管理模块

加载yaml配置文件，提供结构化配置模型

data/

数据管理模块

任务/Agent状态数据的读写与模型定义

utils/

工具函数模块

日志工具、参数校验、通用转换函数等辅助能力

tests/

单元测试模块

Agent逻辑、协作规则、工具函数的自动化测试用例

requirements.txt

项目依赖清单

记录所有依赖包及版本，用于环境复现

🔧 核心模块使用指南

1. Agent管理

1.1 新增Agent类型

1. 在 agents/specialized_agents/ 下新建文件（如 monitor_agent.py）

2. 继承 BaseAgent 抽象类，实现 send_message 和 execute_task 方法：
        from agents.base_agent import BaseAgent

class MonitorAgent(BaseAgent):
    def __init__(self, agent_id: str):
        super().__init__(agent_id, agent_type="monitor")
    
    def send_message(self, target_agent_id: str, message: dict):
        # 实现监控Agent的消息发送逻辑
        pass
    
    def execute_task(self, task: dict) -> dict:
        # 实现监控任务逻辑（如Agent状态巡检）
        self.update_state(status="running", load=0.3)
        # 业务逻辑...
        self.update_state(status="idle", load=0.0)
        return {"code": 0, "msg": "监控任务完成"}

3. 在 agents/specialized_agents/__init__.py 中导出该类，即可在系统中使用

2. 任务管理

通过Streamlit「任务管理」页面创建任务，支持以下操作：

- 输入任务名称、选择任务类型（数据处理/分析/通知等）

- 以JSON格式配置任务参数（如文件路径、分析规则）

- 点击「创建并分配任务」，系统会自动通过协调Agent分配给最优执行Agent

- 在任务列表中可按状态筛选任务（待执行/运行中/已完成/失败）

3. 日志查看

「系统日志」页面支持：

- 按日志级别筛选（DEBUG/INFO/WARNING/ERROR）

- 关键词搜索日志内容

- 日志实时刷新，错误日志标红、警告日志标橙，便于快速定位问题

📈 进阶扩展

1. 自定义任务分配算法

修改 collaboration/task_allocation.py 中的 TaskAllocator 类，实现自定义分配逻辑（如基于强化学习、负载均衡等）：

class TaskAllocator:
    def greedy_allocation(self, task: dict, agents: dict) -> str:
        # 原有贪心算法：选择负载最低的Agent
        pass
    
    def custom_allocation(self, task: dict, agents: dict) -> str:
        # 自定义算法：如按Agent类型匹配任务类型
        for agent_id, agent in agents.items():
            if agent.agent_type == task["type"] and agent.state.load < 0.5:
                return agent_id
        return list(agents.keys())[0]

2. 部署到服务器

如需在服务器上长期运行，可使用 nohup 命令后台启动：

# Linux/macOS后台启动，日志输出到streamlit.log
nohup streamlit run streamlit_app/main_page.py --server.port 80 > streamlit.log 2>&1 

启动后通过服务器IP:80即可访问系统（需开放服务器端口权限）。

⚠️ 注意事项

- Python版本需 ≥ 3.9，低于该版本可能导致依赖安装失败

- 启动前确保已激活虚拟环境，避免依赖包冲突

- 日志文件默认存储在 ./logs/ 目录，需确保该目录有写入权限

- 任务参数需严格按照JSON格式填写，否则会导致任务创建失败

📞 问题反馈

如遇到以下问题，可按对应方式处理：

- 依赖安装问题：检查Python版本，或使用pip install --upgrade pip 更新pip

- Agent启动失败：查看系统日志，检查配置文件中Agent参数是否正确

- UI无法访问：确认Streamlit启动命令是否正确，或更换端口（--server.port 8502）

- 其他功能问题：提交Issue至项目仓库，或联系开发人员

📄 许可证

本项目已开源至GitHub，仓库地址：https://github.com/lxy3837/MultiCoopAgentSystem，采用MIT许可证，完整内容如下：

MIT License

Copyright (c) 2025 lxy3837

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.




