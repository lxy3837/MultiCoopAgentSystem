/**
 * MCASys Dashboard - Main Application Logic
 * Real-time dashboard with API polling + WebSocket live updates
 */
(function () {
  'use strict';

  // ── Configuration ──
  const API_BASE = window.location.origin.replace(/\/$/, '');
  const POLL_INTERVAL = 3000; // 3s stats poll
  const START_TIME = new Date();

  // ── State ──
  let statsData = { agents: 0, tasks: 0, completed: 0 };
  let agentsList = [];
  let tasksList = [];
  let steps = [];
  let ws = null;
  let wsReconnectTimer = null;

  // ── DOM Refs ──
  const $ = (id) => document.getElementById(id);

  // ── Initialization ──
  function init() {
    updateClock();
    setInterval(updateClock, 1000);
    refreshAll();
    setInterval(refreshStats, POLL_INTERVAL);
    connectWebSocket();
  }

  // ── Clock ──
  function updateClock() {
    const el = $('sysClock');
    if (el) el.textContent = new Date().toLocaleString('zh-CN');
  }

  // ── API Calls ──
  async function apiGet(path) {
    try {
      const res = await fetch(`${API_BASE}${path}`, {
        headers: { 'Authorization': 'Bearer mcasys-dev-key' }
      });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      return await res.json();
    } catch (e) {
      console.warn(`API ${path}:`, e.message);
      return null;
    }
  }

  async function apiPost(path, body) {
    try {
      const res = await fetch(`${API_BASE}${path}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mcasys-dev-key'
        },
        body: JSON.stringify(body)
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `${res.status} ${res.statusText}`);
      }
      return await res.json();
    } catch (e) {
      console.warn(`API POST ${path}:`, e.message);
      throw e;
    }
  }

  // ── Refresh All ──
  async function refreshAll() {
    await Promise.all([refreshStats(), refreshAgents(), refreshTasks()]);
  }

  async function refreshStats() {
    const data = await apiGet('/api/v1/system/stats');
    if (!data) return;
    statsData = data;

    // Use data.data if wrapped, else raw
    const d = data.data || data;
    // system/stats returns {tasks: {...}, agents: {...}}
    const tasksStats = d.tasks || {};
    const totalTasks = d.total_tasks ?? Object.values(tasksStats).reduce((a, b) => a + (b || 0), 0);
    const agentsMap = d.agents || {};
    const agentCount = d.agent_count ?? Object.keys(agentsMap).length;

    // Animate stat values
    animateValue('valAgents', agentCount);
    animateValue('valTasks', totalTasks);
    animateValue('valCompleted', tasksStats.completed ?? d.completed_tasks ?? d.completed ?? 0);

    // Uptime
    const sec = Math.floor((Date.now() - START_TIME) / 1000);
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    $('valUptime').textContent = `${h}h ${m}m`;
  }

  async function refreshAgents() {
    const data = await apiGet('/api/v1/agents');
    if (!data) return;

    const list = data.data || data.agents || data || [];
    agentsList = Array.isArray(list) ? list : [];
    renderAgents();
  }

  async function refreshTasks() {
    const data = await apiGet('/api/v1/tasks');
    if (!data) return;

    const list = data.data || data.tasks || data || [];
    tasksList = Array.isArray(list) ? list : [];
    renderTasks();
  }

  // ── Render: Agents ──
  function renderAgents() {
    const grid = $('agentsGrid');
    const badge = $('agentsCount');
    if (badge) badge.textContent = agentsList.length;

    if (agentsList.length === 0) {
      grid.innerHTML = '<div class="empty-state"><div class="empty-state-icon">◈</div><div class="empty-state-text">暂无 Agent 注册</div></div>';
      return;
    }

    const typeClass = {
      coordinator: 'coordinator',
      executor: 'executor',
      analyzer: 'analyzer',
      reviewer: 'reviewer'
    };

    grid.innerHTML = agentsList.map(a => {
      const t = (a.type || a.agent_type || 'executor').toLowerCase();
      const status = a.status || 'active';
      const taskCount = a.task_count ?? a.completed_tasks ?? 0;
      const statusClass = status === 'active' ? 'active' : (status === 'idle' ? 'idle' : 'offline');
      const statusText = status === 'active' ? 'ACTIVE' : (status === 'idle' ? 'IDLE' : 'OFFLINE');

      return `
        <div class="agent-card">
          <div class="agent-card-header">
            <div class="agent-name">${esc(a.name || a.id || 'Unknown')}</div>
            <div class="agent-type ${typeClass[t] || 'executor'}">${esc(t)}</div>
          </div>
          <div class="agent-id">${esc((a.id || a.agent_id || '').slice(0, 12))}</div>
          <div class="agent-stats">
            <div class="agent-stat">
              <div class="agent-stat-value">${taskCount}</div>
              <div class="agent-stat-label">tasks</div>
            </div>
            <div class="agent-stat">
              <div class="agent-stat-value">${statusText}</div>
              <div class="agent-stat-label">status</div>
            </div>
          </div>
          <div class="agent-status-bar">
            <div class="agent-status-fill ${statusClass}" style="width:${status === 'active' ? '100%' : '30%'}"></div>
          </div>
        </div>
      `;
    }).join('');
  }

  // ── Render: Tasks ──
  function renderTasks() {
    const list = $('taskList');
    const badge = $('tasksCount');
    if (badge) badge.textContent = tasksList.length;

    if (tasksList.length === 0) {
      list.innerHTML = '<div class="empty-state"><div class="empty-state-icon">◉</div><div class="empty-state-text">暂无任务</div></div>';
      // Also update steps
      renderSteps([]);
      return;
    }

    list.innerHTML = tasksList.slice().reverse().slice(0, 20).map(t => {
      const status = (t.status || 'pending').toLowerCase();
      const progress = t.progress ?? 0;
      const title = t.name || t.title || t.id || 'Unnamed';
      const type = t.type || t.task_type || 'analysis';

      return `
        <div class="task-item">
          <div class="task-info">
            <div class="task-title">${esc(title)}</div>
            <div class="task-meta">${esc(type)} · ${esc(t.id || '').slice(0, 8)}</div>
          </div>
          <div class="task-status ${status}">${status}</div>
          <div class="task-progress">
            <div class="progress-bar">
              <div class="progress-fill" style="width:${progress}%"></div>
            </div>
          </div>
        </div>
      `;
    }).join('');

    // Render steps from active tasks
    const runningTasks = tasksList.filter(t => (t.status || '').toLowerCase() === 'running');
    if (runningTasks.length > 0) {
      renderSteps(runningTasks);
    } else if (tasksList.some(t => (t.status || '').toLowerCase() === 'completed')) {
      renderSteps([{ name: 'All Complete', status: 'completed' }]);
    }
  }

  // ── Render: Steps ──
  function renderSteps(taskSteps) {
    const list = $('stepList');
    if (!taskSteps || taskSteps.length === 0) {
      list.innerHTML = '<div class="step-item"><div class="step-indicator pending">1</div><div class="step-name" style="color:var(--text-muted)">暂无活跃任务</div><div class="step-duration">--</div></div>';
      return;
    }

    // Generate workflow steps based on task state
    const workflowSteps = [
      { id: 1, name: '初始化', key: 'init' },
      { id: 2, name: '需求分析', key: 'requirement' },
      { id: 3, name: '任务分发', key: 'dispatch' },
      { id: 4, name: 'Agent 执行', key: 'execute' },
      { id: 5, name: '结果收集', key: 'collect' },
      { id: 6, name: '质量审核', key: 'review' },
      { id: 7, name: '完成', key: 'done' },
    ];

    // Determine current step based on running task count
    const runningCount = tasksList.filter(t => (t.status || '').toLowerCase() === 'running').length;
    const completedCount = tasksList.filter(t => (t.status || '').toLowerCase() === 'completed').length;
    const currentStep = runningCount > 0 ? 4 : (completedCount > 0 ? 7 : 1);

    list.innerHTML = workflowSteps.map(ws => {
      let statusClass = 'pending';
      if (ws.id < currentStep) statusClass = 'completed';
      else if (ws.id === currentStep) statusClass = 'running';
      let icon = ws.id;
      if (statusClass === 'completed') icon = '\u2713';

      return `
        <div class="step-item">
          <div class="step-indicator ${statusClass}">${icon}</div>
          <div class="step-name" style="${statusClass === 'running' ? 'color:var(--accent-cyan)' : ''}">${ws.name}</div>
          <div class="step-duration">${statusClass === 'completed' ? 'done' : (statusClass === 'running' ? 'active' : '--')}</div>
        </div>
      `;
    }).join('');
  }

  // ── Create Task ──
  async function createTask() {
    const name = $('taskName').value.trim() || 'New Task';
    const type = $('taskType').value;
    const desc = $('taskDesc').value.trim();

    try {
      const res = await apiPost('/api/v1/tasks', {
        name: name,
        task_type: type,
        description: desc || name
      });
      closeCreateTaskModal();
      toast('任务创建成功', 'success');
      addLiveEvent('task_created', `${name} (${type})`);
      refreshAll();
    } catch (e) {
      toast(`创建失败: ${e.message}`, 'error');
    }
  }

  // ── Modal ──
  function showCreateTaskModal() {
    $('createTaskModal').classList.add('active');
    $('taskName').focus();
  }

  function closeCreateTaskModal() {
    $('createTaskModal').classList.remove('active');
    // Clear form
    $('taskName').value = '';
    $('taskDesc').value = '';
    $('taskType').value = 'analysis';
  }

  // Close modal on overlay click
  $('createTaskModal').addEventListener('click', (e) => {
    if (e.target === $('createTaskModal')) closeCreateTaskModal();
  });

  // Close modal on Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && $('createTaskModal').classList.contains('active')) {
      closeCreateTaskModal();
    }
  });

  // ── Toast ──
  function toast(message, type = 'info') {
    const container = $('toastContainer');
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => {
      el.style.opacity = '0';
      el.style.transition = 'opacity 0.3s';
      setTimeout(() => el.remove(), 300);
    }, 3000);
  }

  // ── Live Feed ──
  function addLiveEvent(type, msg) {
    const feed = $('liveFeed');
    const time = new Date().toLocaleTimeString('zh-CN');

    // Remove empty placeholder
    const empty = feed.querySelector('.empty-state');
    if (empty) empty.remove();

    const el = document.createElement('div');
    el.className = 'live-event';
    el.innerHTML = `
      <span class="live-event-time">${time}</span>
      <span class="live-event-type">[${type}]</span>
      <span class="live-event-msg">${esc(msg)}</span>
    `;
    feed.prepend(el);

    // Keep max 50 events
    while (feed.children.length > 50) {
      feed.lastChild.remove();
    }
  }

  function clearLiveFeed() {
    $('liveFeed').innerHTML = '<div class="empty-state" style="padding:var(--space-lg)"><div class="empty-state-text">等待事件...</div></div>';
  }

  // ── Clear All Tasks ──
  async function clearAllTasks() {
    if (!confirm('确认清除所有已完成和失败的任务？')) return;
    toast('清除功能需要通过管理 API 实现', 'warning');
    addLiveEvent('action', 'Clear tasks requested');
  }

  // ── Export Report ──
  function exportReport() {
    const data = {
      timestamp: new Date().toISOString(),
      stats: statsData,
      agents: agentsList,
      tasks: tasksList.slice(0, 50),
    };

    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `mcasys_report_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);

    toast('报告已下载', 'success');
    addLiveEvent('export', 'Report exported');
  }

  // ── WebSocket ──
  function connectWebSocket() {
    const wsUrl = API_BASE.replace(/^http/, 'ws') + '/ws/events';
    try {
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('WebSocket connected');
        $('statusDot').style.background = 'var(--accent-emerald)';
        $('statusText').textContent = '系统运行中';
        addLiveEvent('system', 'WebSocket 已连接');
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);

          // Event from event bus → add to live feed
          if (msg.type === 'event' || msg.event_type) {
            const eventType = msg.event_type || msg.type;
            const data = msg.data || msg;
            const stepInfo = data.step;
            if (stepInfo) {
              addLiveEvent('step', `${stepInfo.title}: ${stepInfo.status}`);
            } else if (data.message || data.msg) {
              addLiveEvent(eventType, data.message || data.msg);
            }
          } else if (msg.type === 'track') {
            // Stream tracker event
            const step = msg.step || msg;
            if (step && step.title) {
              addLiveEvent('track', `${step.title}: ${step.status || 'update'} [${step.progress || 0}%]`);
            }
          }

          // Refresh on task-related events
          if (msg.event_type && msg.event_type.includes('task')) {
            refreshTasks();
          }
        } catch (e) {
          // Ignore malformed WS messages
        }
      };

      ws.onclose = () => {
        $('statusDot').style.background = 'var(--accent-amber)';
        $('statusText').textContent = 'WebSocket 断开，将在 5s 后重连';
        wsReconnectTimer = setTimeout(connectWebSocket, 5000);
        addLiveEvent('system', 'WebSocket 断开, 5s 后重连');
      };

      ws.onerror = () => {
        // onclose will fire after onerror
      };

    } catch (e) {
      console.warn('WebSocket connect failed:', e);
      wsReconnectTimer = setTimeout(connectWebSocket, 5000);
    }
  }

  // ── Utilities ──
  function esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
  }

  function animateValue(id, target) {
    const el = $(id);
    if (!el) return;
    const current = parseInt(el.textContent) || 0;
    if (current === target) return;
    el.textContent = target;
  }

  // ── Expose to global ──
  window.refreshAll = refreshAll;
  window.showCreateTaskModal = showCreateTaskModal;
  window.closeCreateTaskModal = closeCreateTaskModal;
  window.createTask = createTask;
  window.clearAllTasks = clearAllTasks;
  window.clearLiveFeed = clearLiveFeed;
  window.exportReport = exportReport;

  // ── Start ──
  document.addEventListener('DOMContentLoaded', init);
})();
