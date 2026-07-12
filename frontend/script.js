// 企业级前端模块化架构
;(function() {
    'use strict';
    
    // 全局配置对象
    const CONFIG = {
        API_BASE_URL: 'http://localhost:8000',
        MESSAGE_DURATION: 3000,
        I18N: {
            nav: {
                home: '首页',
                agents: 'Agent管理',
                tasks: '任务管理',
                logs: '系统日志'
            },
            sections: {
                overview: '系统概览',
                quickActions: '快速操作',
                systemDetails: '系统状态详情',
                agentList: 'Agent列表',
                taskList: '任务列表',
                logList: '系统日志'
            },
            metrics: {
                agentCount: { label: '在线Agent数', help: '已注册到系统的Agent总数' },
                pendingTasks: { label: '待执行任务数', help: '状态为「待执行」的任务数' },
                completedTasks: { label: '已完成任务数', help: '状态为「已完成」的任务数' },
                failedTasks: { label: '失败任务数', help: '状态为「失败」的任务数' }
            },
            actions: {
                startAll: '启动所有Agent',
                stopAll: '停止所有Agent',
                refresh: '刷新',
                start: '启动',
                stop: '停止',
                delete: '删除',
                create: '创建'
            },
            details: {
                initTime: '系统初始化时间：',
                agentList: '已注册Agent列表：',
                totalTasks: '任务总数：'
            },
            status: {
                pending: '待执行',
                running: '运行中',
                completed: '已完成',
                failed: '失败'
            },
            agents: {
                columns: {
                    id: 'Agent ID',
                    type: 'Agent类型',
                    status: '状态',
                    created: '创建时间',
                    updated: '最后更新',
                    actions: '操作'
                },
                messages: {
                    loading: '加载中...',
                    noData: '暂无Agent数据'
                }
            },
            tasks: {
                createSection: '创建新任务',
                form: {
                    name: '任务名称',
                    type: '任务类型',
                    params: '任务参数（JSON格式）'
                },
                filter: {
                    all: '全部状态'
                },
                columns: {
                    id: '任务ID',
                    name: '任务名称',
                    type: '任务类型',
                    status: '状态',
                    agent: '执行Agent',
                    created: '创建时间',
                    started: '开始时间',
                    ended: '结束时间',
                    actions: '操作'
                },
                messages: {
                    loading: '加载中...',
                    noData: '暂无任务数据',
                    createSuccess: '任务创建成功！',
                    statusUpdateSuccess: '任务状态已更新！',
                    deleteSuccess: '任务已成功删除！'
                }
            },
            logs: {
                actions: {
                    clear: '清空日志'
                },
                filter: {
                    level: '日志级别：'
                },
                levels: {
                    error: '错误',
                    warning: '警告',
                    info: '信息',
                    debug: '调试'
                },
                messages: {
                    loading: '加载中...',
                    noData: '暂无日志数据',
                    cleared: '日志已清空'
                }
            }
        },
        PAGE_CONFIG: {
            index: {
                title: 'MCASys - 多Agent协作系统'
            },
            agents: {
                title: 'Agent管理 - MCASys'
            },
            tasks: {
                title: '任务管理 - MCASys'
            },
            logs: {
                title: '系统日志 - MCASys'
            }
        },
        STATUS_MAP: {
            PENDING: { className: 'status-badge--pending', text: '待执行' },
            RUNNING: { className: 'status-badge--running', text: '运行中' },
            COMPLETED: { className: 'status-badge--completed', text: '已完成' },
            FAILED: { className: 'status-badge--failed', text: '失败' }
        }
    };
    
    // API服务模块
    const APIService = {
        async request(endpoint, method = 'GET', body = null) {
            const url = `${CONFIG.API_BASE_URL}${endpoint}`;
            
            const options = {
                method: method,
                headers: {
                    'Content-Type': 'application/json',
                },
            };
            
            if (body) {
                options.body = JSON.stringify(body);
            }
            
            try {
                const response = await fetch(url, options);
                
                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
                }
                
                return await response.json();
            } catch (error) {
                console.error(`API请求失败 [${method} ${endpoint}]:`, error);
                throw error;
            }
        },
        
        // 获取健康检查数据
        getHealth() {
            return this.request('/health');
        },
        
        // 启动所有Agent
        startAllAgents() {
            return this.request('/agents/start-all', 'POST');
        },
        
        // 停止所有Agent
        stopAllAgents() {
            return this.request('/agents/stop-all', 'POST');
        },
        
        // 获取Agent列表
        getAgents() {
            return this.request('/agents');
        },
        
        // 启动单个Agent
        startAgent(agentId) {
            return this.request(`/agents/${agentId}/start`, 'POST');
        },
        
        // 停止单个Agent
        stopAgent(agentId) {
            return this.request(`/agents/${agentId}/stop`, 'POST');
        },
        
        // 获取任务列表
        getTasks(status = null) {
            const endpoint = status ? `/tasks?status=${status}` : '/tasks';
            return this.request(endpoint);
        },
        
        // 创建任务
        createTask(taskData) {
            return this.request('/tasks', 'POST', taskData);
        },
        
        // 更新任务状态
        updateTaskStatus(taskId, status) {
            return this.request(`/tasks/${taskId}/status`, 'PUT', { status });
        },
        
        // 删除任务
        deleteTask(taskId) {
            return this.request(`/tasks/${taskId}`, 'DELETE');
        }
    };
    
    // UI管理模块
    const UIManager = {
        // 初始化页面
        initPage() {
            // 设置当前页面的导航链接为活跃状态
            const currentPath = window.location.pathname;
            const navLinks = document.querySelectorAll('.nav-link');
            
            navLinks.forEach(link => {
                if (link.getAttribute('href') === currentPath.split('/').pop()) {
                    link.classList.add('active');
                } else {
                    link.classList.remove('active');
                }
            });
            
            // 动态渲染页面文本
            this.renderPageContent();
            
            // 绑定侧边栏切换按钮事件
            const sidebarToggle = document.getElementById('sidebarToggle');
            if (sidebarToggle) {
                sidebarToggle.addEventListener('click', () => {
                    const sidebar = document.querySelector('.sidebar');
                    sidebar.classList.toggle('open');
                });
            }
        },
        
        // 动态渲染页面内容
        renderPageContent() {
            const currentPath = window.location.pathname;
            const pageName = currentPath.split('/').pop().replace('.html', '');
            
            // 设置页面标题
            const pageTitleEl = document.getElementById('pageTitle');
            if (pageTitleEl && CONFIG.PAGE_CONFIG[pageName]) {
                pageTitleEl.textContent = CONFIG.PAGE_CONFIG[pageName].title;
            }
            
            // 渲染国际化文本
            this.renderI18nContent();
            
            // 渲染指标标签和帮助文本
            this.renderMetricsContent();
            
            // 渲染按钮文本
            this.renderActionsContent();
        },
        
        // 渲染国际化文本
        renderI18nContent() {
            const i18nElements = document.querySelectorAll('[data-i18n]');
            
            i18nElements.forEach(element => {
                const key = element.getAttribute('data-i18n');
                const value = this.getValueFromConfig(CONFIG.I18N, key);
                
                if (value) {
                    element.textContent = value;
                }
            });
        },
        
        // 渲染指标标签和帮助文本
        renderMetricsContent() {
            // 渲染指标标签
            const metricLabels = document.querySelectorAll('[data-metric]');
            metricLabels.forEach(element => {
                const metricKey = element.getAttribute('data-metric');
                const metricConfig = CONFIG.I18N.metrics[metricKey];
                
                if (metricConfig && metricConfig.label) {
                    element.textContent = metricConfig.label;
                }
            });
            
            // 渲染指标帮助文本
            const metricHelpElements = document.querySelectorAll('[data-metric-help]');
            metricHelpElements.forEach(element => {
                const metricKey = element.getAttribute('data-metric-help');
                const metricConfig = CONFIG.I18N.metrics[metricKey];
                
                if (metricConfig && metricConfig.help) {
                    element.textContent = metricConfig.help;
                }
            });
        },
        
        // 渲染按钮文本
        renderActionsContent() {
            const actionElements = document.querySelectorAll('[data-action]');
            actionElements.forEach(element => {
                const actionKey = element.getAttribute('data-action');
                const actionText = CONFIG.I18N.actions[actionKey];
                
                if (actionText) {
                    element.textContent = actionText;
                }
            });
        },
        
        // 从配置对象中获取值
        getValueFromConfig(config, key) {
            const keys = key.split('.');
            let value = config;
            
            for (const k of keys) {
                if (value && typeof value === 'object' && k in value) {
                    value = value[k];
                } else {
                    return null;
                }
            }
            
            return value;
        },
        
        // 显示消息
        showMessage(message, type = 'info') {
            // 移除现有的消息
            const existingMessage = document.querySelector('.message');
            if (existingMessage) {
                existingMessage.remove();
            }
            
            // 创建新消息元素
            const messageEl = document.createElement('div');
            messageEl.className = `message message--${type}`;
            messageEl.textContent = message;
            
            // 添加到主内容区域顶部
            const mainEl = document.querySelector('.main-content');
            if (mainEl) {
                mainEl.insertBefore(messageEl, mainEl.firstChild);
                
                // 3秒后自动移除消息
                setTimeout(() => {
                    messageEl.remove();
                }, CONFIG.MESSAGE_DURATION);
            }
        },
        
        // 显示加载状态
        showLoading(elementId, text = '加载中...') {
            const element = document.getElementById(elementId);
            if (element) {
                element.disabled = true;
                element.innerHTML = `<span class="loading"></span> ${text}`;
            }
        },
        
        // 隐藏加载状态
        hideLoading(elementId, originalText) {
            const element = document.getElementById(elementId);
            if (element) {
                element.disabled = false;
                element.textContent = originalText;
            }
        },
        
        // 更新仪表盘指标
        updateDashboardMetrics(data) {
            // 更新在线Agent数
            this.updateElement('agentCount', data.agent_count);
            
            // 更新待执行任务数
            this.updateElement('pendingTasks', data.pending_tasks);
            
            // 更新已完成任务数
            this.updateElement('completedTasks', data.completed_tasks);
            
            // 更新失败任务数（兼容后端响应，后端可能不返回该字段）
            this.updateElement('failedTasks', data.failed_tasks || 0);
        },
        
        // 更新元素内容
        updateElement(elementId, content) {
            const element = document.getElementById(elementId);
            if (element) {
                element.textContent = content;
            }
        },
        
        // 获取状态标签
        getStatusBadge(status) {
            const config = CONFIG.STATUS_MAP[status] || { className: 'status-badge--pending', text: status };
            return `<span class="status-badge ${config.className}">${config.text}</span>`;
        },
        
        // 格式化日期
        formatDate(dateString) {
            const date = new Date(dateString);
            return date.toLocaleString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
        }
    };
    
    // 仪表盘控制器
    const DashboardController = {
        // 初始化仪表盘
        async init() {
            this.bindEventListeners();
            await this.loadData();
        },
        
        // 绑定事件监听器
        bindEventListeners() {
            // 启动所有Agent按钮
            const startAllBtn = document.getElementById('startAllAgents');
            if (startAllBtn) {
                startAllBtn.addEventListener('click', () => this.startAllAgents());
            }
            
            // 停止所有Agent按钮
            const stopAllBtn = document.getElementById('stopAllAgents');
            if (stopAllBtn) {
                stopAllBtn.addEventListener('click', () => this.stopAllAgents());
            }
            
            // 刷新系统状态按钮
            const refreshBtn = document.getElementById('refreshStatus');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', () => this.loadData());
            }
        },
        
        // 加载仪表盘数据
        async loadData() {
            try {
                UIManager.showLoading('refreshStatus', CONFIG.I18N.actions.refresh);
                
                const healthData = await APIService.getHealth();
                UIManager.updateDashboardMetrics(healthData);
                
                UIManager.hideLoading('refreshStatus', CONFIG.I18N.actions.refresh);
            } catch (error) {
                console.error('加载仪表盘数据失败:', error);
                UIManager.showMessage('加载数据失败: ' + error.message, 'error');
                UIManager.hideLoading('refreshStatus', CONFIG.I18N.actions.refresh);
            }
        },
        
        // 启动所有Agent
        async startAllAgents() {
            const startBtn = document.getElementById('startAllAgents');
            const originalText = startBtn ? startBtn.textContent : CONFIG.I18N.actions.startAll;
            
            try {
                UIManager.showLoading('startAllAgents', '启动中...');
                
                await APIService.startAllAgents();
                
                UIManager.showMessage('成功启动所有Agent！', 'success');
                await this.loadData();
                
                UIManager.hideLoading('startAllAgents', originalText);
            } catch (error) {
                console.error('启动所有Agent失败:', error);
                UIManager.showMessage('启动Agent失败: ' + error.message, 'error');
                UIManager.hideLoading('startAllAgents', originalText);
            }
        },
        
        // 停止所有Agent
        async stopAllAgents() {
            const stopBtn = document.getElementById('stopAllAgents');
            const originalText = stopBtn ? stopBtn.textContent : CONFIG.I18N.actions.stopAll;
            
            try {
                UIManager.showLoading('stopAllAgents', '停止中...');
                
                await APIService.stopAllAgents();
                
                UIManager.showMessage('成功停止所有Agent！', 'success');
                await this.loadData();
                
                UIManager.hideLoading('stopAllAgents', originalText);
            } catch (error) {
                console.error('停止所有Agent失败:', error);
                UIManager.showMessage('停止Agent失败: ' + error.message, 'error');
                UIManager.hideLoading('stopAllAgents', originalText);
            }
        }
    };
    
    // Agent页面控制器
    const AgentsController = {
        // 初始化Agent页面
        async init() {
            this.bindEventListeners();
            await this.loadAndRenderAgents();
        },
        
        // 绑定事件监听器
        bindEventListeners() {
            // 刷新Agent列表按钮
            const refreshAgentsBtn = document.getElementById('refreshAgents');
            if (refreshAgentsBtn) {
                refreshAgentsBtn.addEventListener('click', () => this.loadAndRenderAgents());
            }
        },
        
        // 加载并渲染Agent列表
        async loadAndRenderAgents() {
            try {
                UIManager.showLoading('refreshAgents', '刷新中...');
                
                const agentsData = await APIService.getAgents();
                this.renderAgentsTable(agentsData.agents);
                
                UIManager.hideLoading('refreshAgents', CONFIG.I18N.actions.refresh);
            } catch (error) {
                console.error('加载Agent列表失败:', error);
                UIManager.showMessage('加载Agent列表失败: ' + error.message, 'error');
                UIManager.hideLoading('refreshAgents', CONFIG.I18N.actions.refresh);
            }
        },
        
        // 渲染Agent表格
        renderAgentsTable(agents) {
            const tableBody = document.getElementById('agentsTableBody');
            if (!tableBody) return;
            
            if (agents.length === 0) {
                tableBody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: rgba(255, 255, 255, 0.6);">${CONFIG.I18N.agents.messages.noData}</td></tr>`;
                return;
            }
            
            const rows = agents.map(agent => `
                <tr>
                    <td>${agent.agent_id}</td>
                    <td>${agent.agent_type}</td>
                    <td>${UIManager.getStatusBadge(agent.status)}</td>
                    <td>${UIManager.formatDate(agent.created_at)}</td>
                    <td>${agent.last_updated ? UIManager.formatDate(agent.last_updated) : '-'}</td>
                    <td>
                        <div style="display: flex; gap: 0.5rem;">
                            <button class="action-btn action-btn--primary" style="padding: 0.3rem 0.8rem; font-size: 0.8rem;" onclick="window.MCASys.AgentsController.startAgent('${agent.agent_id}')">${CONFIG.I18N.actions.start}</button>
                            <button class="action-btn action-btn--secondary" style="padding: 0.3rem 0.8rem; font-size: 0.8rem;" onclick="window.MCASys.AgentsController.stopAgent('${agent.agent_id}')">${CONFIG.I18N.actions.stop}</button>
                        </div>
                    </td>
                </tr>
            `).join('');
            
            tableBody.innerHTML = rows;
        },
        
        // 启动单个Agent
        async startAgent(agentId) {
            try {
                await APIService.request(`/agents/${agentId}/start`, 'POST');
                UIManager.showMessage(`成功启动Agent ${agentId}！`, 'success');
                await this.loadAndRenderAgents();
            } catch (error) {
                console.error(`启动Agent ${agentId}失败:`, error);
                UIManager.showMessage(`启动Agent ${agentId}失败: ${error.message}`, 'error');
            }
        },
        
        // 停止单个Agent
        async stopAgent(agentId) {
            try {
                await APIService.request(`/agents/${agentId}/stop`, 'POST');
                UIManager.showMessage(`成功停止Agent ${agentId}！`, 'success');
                await this.loadAndRenderAgents();
            } catch (error) {
                console.error(`停止Agent ${agentId}失败:`, error);
                UIManager.showMessage(`停止Agent ${agentId}失败: ${error.message}`, 'error');
            }
        }
    };
    
    // 任务页面控制器
    const TasksController = {
        // 初始化任务页面
        async init() {
            this.bindEventListeners();
            await this.loadAndRenderTasks();
        },
        
        // 绑定事件监听器
        bindEventListeners() {
            // 刷新任务列表按钮
            const refreshTasksBtn = document.getElementById('refreshTasks');
            if (refreshTasksBtn) {
                refreshTasksBtn.addEventListener('click', () => this.loadAndRenderTasks());
            }
            
            // 状态筛选下拉框
            const statusFilter = document.getElementById('statusFilter');
            if (statusFilter) {
                statusFilter.addEventListener('change', () => this.loadAndRenderTasks());
            }
            
            // 创建任务表单
            const createTaskForm = document.getElementById('createTaskForm');
            if (createTaskForm) {
                createTaskForm.addEventListener('submit', (event) => this.handleCreateTask(event));
            }
        },
        
        // 加载并渲染任务列表
        async loadAndRenderTasks() {
            try {
                UIManager.showLoading('refreshTasks', '刷新中...');
                
                // 获取状态筛选值
                const statusFilter = document.getElementById('statusFilter');
                const status = statusFilter ? statusFilter.value : null;
                
                const tasksData = await APIService.getTasks(status);
                this.renderTasksTable(tasksData.tasks);
                
                UIManager.hideLoading('refreshTasks', CONFIG.I18N.actions.refresh);
            } catch (error) {
                console.error('加载任务列表失败:', error);
                UIManager.showMessage('加载任务列表失败: ' + error.message, 'error');
                UIManager.hideLoading('refreshTasks', CONFIG.I18N.actions.refresh);
            }
        },
        
        // 渲染任务表格
        renderTasksTable(tasks) {
            const tableBody = document.getElementById('tasksTableBody');
            if (!tableBody) return;
            
            if (tasks.length === 0) {
                tableBody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: rgba(255, 255, 255, 0.6);">${CONFIG.I18N.tasks.messages.noData}</td></tr>`;
                return;
            }
            
            const rows = tasks.map(task => `
                <tr>
                    <td>${task.task_id}</td>
                    <td>${task.name}</td>
                    <td>${task.type}</td>
                    <td>${UIManager.getStatusBadge(task.status)}</td>
                    <td>${task.executor_agent_id || '-'}</td>
                    <td>${UIManager.formatDate(task.create_time)}</td>
                    <td>${task.start_time ? UIManager.formatDate(task.start_time) : '-'}</td>
                    <td>${task.end_time ? UIManager.formatDate(task.end_time) : '-'}</td>
                    <td>
                        <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                            ${task.status === 'PENDING' ? `
                                <button class="action-btn action-btn--primary" style="padding: 0.3rem 0.8rem; font-size: 0.8rem;" onclick="window.MCASys.TasksController.updateTaskStatus('${task.task_id}', 'RUNNING')">开始</button>
                            ` : ''}
                            ${task.status === 'RUNNING' ? `
                                <button class="action-btn action-btn--secondary" style="padding: 0.3rem 0.8rem; font-size: 0.8rem;" onclick="window.MCASys.TasksController.updateTaskStatus('${task.task_id}', 'COMPLETED')">完成</button>
                                <button class="action-btn action-btn--secondary" style="padding: 0.3rem 0.8rem; font-size: 0.8rem; background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);" onclick="window.MCASys.TasksController.updateTaskStatus('${task.task_id}', 'FAILED')">失败</button>
                            ` : ''}
                            <button class="action-btn action-btn--secondary" style="padding: 0.3rem 0.8rem; font-size: 0.8rem; background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);" onclick="window.MCASys.TasksController.deleteTask('${task.task_id}')">删除</button>
                        </div>
                    </td>
                </tr>
            `).join('');
            
            tableBody.innerHTML = rows;
        },
        
        // 处理创建任务表单提交
        async handleCreateTask(event) {
            event.preventDefault();
            
            const form = event.target;
            const formData = new FormData(form);
            
            try {
                // 构建任务数据
                const taskData = {
                    name: formData.get('name'),
                    type: formData.get('type'),
                    params: formData.get('params') ? JSON.parse(formData.get('params')) : {}
                };
                
                // 发送请求创建任务
                await APIService.request('/tasks', 'POST', taskData);
                
                UIManager.showMessage(CONFIG.I18N.tasks.messages.createSuccess, 'success');
                
                // 重置表单
                form.reset();
                
                // 刷新任务列表
                await this.loadAndRenderTasks();
            } catch (error) {
                console.error('创建任务失败:', error);
                UIManager.showMessage('创建任务失败: ' + error.message, 'error');
            }
        },
        
        // 更新任务状态
        async updateTaskStatus(taskId, newStatus) {
            try {
                await APIService.request(`/tasks/${taskId}/status`, 'PUT', { status: newStatus });
                UIManager.showMessage(`任务 ${taskId} 状态已更新为 ${newStatus}！`, 'success');
                await this.loadAndRenderTasks();
            } catch (error) {
                console.error(`更新任务 ${taskId} 状态失败:`, error);
                UIManager.showMessage(`更新任务 ${taskId} 状态失败: ${error.message}`, 'error');
            }
        },
        
        // 删除任务
        async deleteTask(taskId) {
            if (!confirm(`确定要删除任务 ${taskId} 吗？`)) {
                return;
            }
            
            try {
                await APIService.request(`/tasks/${taskId}`, 'DELETE');
                UIManager.showMessage(`任务 ${taskId} 已成功删除！`, 'success');
                await this.loadAndRenderTasks();
            } catch (error) {
                console.error(`删除任务 ${taskId} 失败:`, error);
                UIManager.showMessage(`删除任务 ${taskId} 失败: ${error.message}`, 'error');
            }
        }
    };
    
    // 日志页面控制器
    const LogsController = {
        // 初始化日志页面
        async init() {
            this.bindEventListeners();
            await this.loadAndRenderLogs();
        },
        
        // 绑定事件监听器
        bindEventListeners() {
            // 刷新日志按钮
            const refreshLogsBtn = document.getElementById('refreshLogs');
            if (refreshLogsBtn) {
                refreshLogsBtn.addEventListener('click', () => this.loadAndRenderLogs());
            }
            
            // 清空日志按钮
            const clearLogsBtn = document.getElementById('clearLogs');
            if (clearLogsBtn) {
                clearLogsBtn.addEventListener('click', () => this.clearLogs());
            }
            
            // 日志级别筛选复选框
            const logLevelCheckboxes = document.querySelectorAll('input[name="logLevel"]');
            logLevelCheckboxes.forEach(checkbox => {
                checkbox.addEventListener('change', () => this.filterLogs());
            });
        },
        
        // 加载并渲染日志
        async loadAndRenderLogs() {
            try {
                UIManager.showLoading('refreshLogs', '刷新中...');
                
                // 这里可以根据实际情况从API获取日志
                // 目前使用模拟数据
                const logs = this.generateMockLogs();
                this.renderLogs(logs);
                
                UIManager.hideLoading('refreshLogs', CONFIG.I18N.actions.refresh);
            } catch (error) {
                console.error('加载日志失败:', error);
                UIManager.showMessage('加载日志失败: ' + error.message, 'error');
                UIManager.hideLoading('refreshLogs', CONFIG.I18N.actions.refresh);
            }
        },
        
        // 渲染日志
        renderLogs(logs) {
            const logsContainer = document.getElementById('logsContainer');
            if (!logsContainer) return;
            
            logsContainer.innerHTML = '';
            
            if (logs.length === 0) {
                logsContainer.innerHTML = `<div class="log-entry" style="text-align: center; color: rgba(255, 255, 255, 0.6);">${CONFIG.I18N.logs.messages.noData}</div>`;
                return;
            }
            
            logs.forEach(log => {
                const logEntry = document.createElement('div');
                logEntry.className = `log-entry log-entry--${log.level.toLowerCase()}`;
                
                logEntry.innerHTML = `
                    <span class="log-timestamp">${log.timestamp}</span>
                    <span class="log-level">${log.level}</span>
                    <span class="log-message">${log.message}</span>
                `;
                
                logsContainer.appendChild(logEntry);
            });
            
            // 滚动到底部
            logsContainer.scrollTop = logsContainer.scrollHeight;
        },
        
        // 筛选日志
        filterLogs() {
            const selectedLevels = Array.from(document.querySelectorAll('input[name="logLevel"]:checked'))
                .map(checkbox => checkbox.value);
            
            const logEntries = document.querySelectorAll('.log-entry');
            logEntries.forEach(entry => {
                const level = entry.querySelector('.log-level').textContent;
                if (selectedLevels.includes(level)) {
                    entry.style.display = 'block';
                } else {
                    entry.style.display = 'none';
                }
            });
        },
        
        // 清空日志
        clearLogs() {
            if (confirm('确定要清空所有日志吗？')) {
                const logsContainer = document.getElementById('logsContainer');
                if (logsContainer) {
                    logsContainer.innerHTML = `<div class="log-entry" style="text-align: center; color: rgba(255, 255, 255, 0.6);">${CONFIG.I18N.logs.messages.cleared}</div>`;
                }
            }
        },
        
        // 生成模拟日志数据
        generateMockLogs() {
            const logs = [];
            const levels = ['ERROR', 'WARNING', 'INFO', 'DEBUG'];
            const messages = [
                '系统初始化完成',
                'Agent 123 启动成功',
                'Agent 456 停止成功',
                '任务 task_789 创建成功',
                '任务 task_789 执行失败：连接超时',
                '健康检查通过，系统运行正常',
                '检测到新的Agent注册请求',
                '配置文件加载成功',
                '数据库连接已建立',
                'API请求处理完成，耗时 123ms'
            ];
            
            for (let i = 0; i < 20; i++) {
                const timestamp = new Date(Date.now() - i * 10000).toLocaleString('zh-CN');
                const level = levels[Math.floor(Math.random() * levels.length)];
                const message = messages[Math.floor(Math.random() * messages.length)];
                
                logs.push({
                    timestamp: timestamp,
                    level: level,
                    message: message
                });
            }
            
            return logs;
        }
    };
    
    // 页面路由控制器
    const PageController = {
        // 初始化页面
        init() {
            UIManager.initPage();
            
            const currentPath = window.location.pathname;
            const pageName = currentPath.split('/').pop().replace('.html', '');
            
            // 根据页面名称初始化对应的控制器
            switch (pageName) {
                case 'index':
                    DashboardController.init();
                    break;
                case 'agents':
                    AgentsController.init();
                    break;
                case 'tasks':
                    TasksController.init();
                    break;
                case 'logs':
                    LogsController.init();
                    break;
                default:
                    console.warn(`未知页面: ${pageName}`);
            }
        }
    };
    
    // DOM加载完成后初始化应用
    document.addEventListener('DOMContentLoaded', function() {
        PageController.init();
    });
    
    // 暴露全局API（可选，根据需求）
    window.MCASys = {
        CONFIG,
        APIService,
        UIManager,
        AgentsController,
        TasksController,
        LogsController
    };
})();