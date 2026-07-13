/**
 * MCASys Workbench - IDE-Style JavaScript Controller
 * WebSocket + API polling + Chat + Resizable panels + Workflow tracking
 */
(function () {
  'use strict';

  // ── Configuration ──
  const API_BASE = (window.location.origin || 'http://localhost:8000').replace(/\/$/, '');
  const POLL_INTERVAL = 3000;
  const START_TIME = new Date();

  // ── Workflow Steps ──
  const WORKFLOW_STEPS = [
    { id: 'init', icon: 'fa-plug', label: '初始化', order: 1 },
    { id: 'requirement', icon: 'fa-search', label: '需求分析', order: 2 },
    { id: 'dispatch', icon: 'fa-share-nodes', label: '任务分发', order: 3 },
    { id: 'execution', icon: 'fa-microchip', label: 'Agent 执行', order: 4 },
    { id: 'collection', icon: 'fa-archive', label: '结果收集', order: 5 },
    { id: 'review', icon: 'fa-check-double', label: '质量审核', order: 6 },
    { id: 'complete', icon: 'fa-flag-checkered', label: '完成', order: 7 }
  ];

  // ── State ──
  let state = {
    agents: [],
    tasks: [],
    currentStep: 'welcome',
    activeContentPanel: 'welcome',
    status: 'idle', // idle, running, completed, error
    wsConnected: false,
    sidebarCollapsed: false,
    bottomCollapsed: false,
    bottomMaximized: false,
    prevBottomH: 200,
    progress: 0,
    connectedAgent: 'Coordinator',
    agentOnline: false,
    autoScroll: true,
    pollTimer: null,
    ws: null,
    wsReconnectTimer: null,
    uptimeTimer: null
  };

  // ── DOM Refs ──
  const $ = (id) => document.getElementById(id);

  // ── Initialization ──
  function init() {
    bindEvents();
    renderStepTree();
    renderFileTree();
    updateUptime();
    state.uptimeTimer = setInterval(updateUptime, 30000);
    refreshAll();
    connectWebSocket();
    state.pollTimer = setInterval(refreshAll, POLL_INTERVAL);
    addLog('info', '工作台初始化完成');
    toast('工作台已就绪', 'info');
  }

  // ── Event Bindings ──
  function bindEvents() {
    // Toolbar buttons
    $('btnStartWorkflow').addEventListener('click', startWorkflow);
    $('btnPauseWorkflow').addEventListener('click', pauseWorkflow);
    $('btnRefresh').addEventListener('click', refreshAll);
    $('btnSettings').addEventListener('click', showSettings);

    // Welcome buttons
    $('btnWelcomeStart').addEventListener('click', startWorkflow);
    $('btnWelcomeRefresh').addEventListener('click', refreshAll);

    // Sidebar toggle
    $('btnToggleSidebar').addEventListener('click', toggleSidebar);

    // Sidebar tabs
    document.querySelectorAll('.wb-sb-tab').forEach(tab => {
      tab.addEventListener('click', () => switchSidebarTab(tab.dataset.tab));
    });

    // Editor tabs
    document.querySelectorAll('.wb-editor-tab').forEach(tab => {
      tab.addEventListener('click', () => switchEditorTab(tab.dataset.step));
    });

    // Step tree nodes - delegated
    $('workflowStepTree').addEventListener('click', (e) => {
      const node = e.target.closest('.wb-step-node');
      if (node) switchEditorTab(node.dataset.step);
    });

    // Chat
    $('btnSendChat').addEventListener('click', sendChat);
    $('chatInput').addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && e.ctrlKey) {
        e.preventDefault();
        sendChat();
      }
    });

    // Bottom panel
    $('btnClearLogs').addEventListener('click', clearLogs);
    $('btnToggleBottom').addEventListener('click', toggleBottom);
    $('btnMaxBottom').addEventListener('click', toggleMaxBottom);
    document.querySelectorAll('.wb-bt-tab').forEach(tab => {
      tab.addEventListener('click', () => switchBottomTab(tab.dataset.bottom));
    });

    // Settings modal
    $('btnCloseSettings').addEventListener('click', hideSettings);
    $('btnCancelSettings').addEventListener('click', hideSettings);
    $('btnSaveSettings').addEventListener('click', saveSettings);
    $('settingsModal').addEventListener('click', (e) => {
      if (e.target === $('settingsModal')) hideSettings();
    });

    // Panel resize
    bindResize('resizeMainRight', 'horizontal');
    bindResize('resizeBottom', 'vertical');

    // Keyboard shortcuts
    document.addEventListener('keydown', handleKeyboard);
  }

  // ── Resize ──
  function bindResize(handleId, direction) {
    const handle = $(handleId);
    if (!handle) return;

    let dragging = false;
    let startX, startY, startW, startH;

    handle.addEventListener('mousedown', (e) => {
      dragging = true;
      handle.classList.add('active');
      document.body.style.cursor = direction === 'horizontal' ? 'col-resize' : 'row-resize';
      document.body.style.userSelect = 'none';

      if (direction === 'horizontal') {
        startX = e.clientX;
        startW = $('wbRightPanel').offsetWidth;
      } else {
        startY = e.clientY;
        startH = $('wbBottomPanel').offsetHeight;
      }

      e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
      if (!dragging) return;

      if (direction === 'horizontal') {
        const diff = startX - e.clientX;
        const newW = Math.max(200, Math.min(600, startW + diff));
        $('wbRightPanel').style.width = newW + 'px';
      } else {
        const diff = startY - e.clientY;
        const newH = Math.max(28, Math.min(500, startH + diff));
        $('wbBottomPanel').style.height = newH + 'px';
        $('wbBottomPanel').style.minHeight = '28px';
        if (!state.bottomCollapsed) {
          state.prevBottomH = newH;
        }
      }
    });

    document.addEventListener('mouseup', () => {
      if (dragging) {
        dragging = false;
        handle.classList.remove('active');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    });
  }

  // ── Keyboard Shortcuts ──
  function handleKeyboard(e) {
    // Ctrl+S: refresh
    if (e.key === 's' && e.ctrlKey && !e.shiftKey) {
      e.preventDefault();
      refreshAll();
      toast('已刷新', 'info');
    }
    // Ctrl+Enter: start workflow / send chat
    if (e.key === 'Enter' && e.ctrlKey) {
      if (document.activeElement === $('chatInput')) return; // handled by chat input
      e.preventDefault();
      startWorkflow();
    }
    // Escape: close modals
    if (e.key === 'Escape') {
      hideSettings();
    }
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
    await Promise.all([refreshAgents(), refreshTasks()]);
    updateWelcomeStats();
  }

  async function refreshAgents() {
    const data = await apiGet('/api/v1/agents');
    if (!data) return;

    const list = data.data || data.agents || data || [];
    state.agents = Array.isArray(list) ? list : [];
    state.agentOnline = state.agents.length > 0;
    updateAgentBadge();
    updateAgentChatInfo();
  }

  async function refreshTasks() {
    const data = await apiGet('/api/v1/tasks');
    if (!data) return;

    const list = data.data || data.tasks || data || [];
    state.tasks = Array.isArray(list) ? list : [];
    updateTaskBadge();
    updateStepTreeStatus();
    updateProgress();
    updateExecutionCards();
  }

  // ── Welcome Stats ──
  function updateWelcomeStats() {
    $('welcomeAgentCount').textContent = state.agents.length;
    $('welcomeTaskCount').textContent = state.tasks.length;
    const completed = state.tasks.filter(t => (t.status || '').toLowerCase() === 'completed').length;
    $('welcomeCompleted').textContent = completed;
  }

  // ── Badges ──
  function updateAgentBadge() {
    $('wbAgentCount').textContent = state.agents.length;
  }

  function updateTaskBadge() {
    $('wbTaskCount').textContent = state.tasks.length;
  }

  function setStatus(status) {
    state.status = status;
    const badge = $('wbStatusBadge');
    badge.dataset.status = status;

    const labels = {
      idle: '<i class="fas fa-circle"></i> 空闲',
      running: '<i class="fas fa-circle"></i> 运行中',
      completed: '<i class="fas fa-circle"></i> 已完成',
      error: '<i class="fas fa-circle"></i> 异常'
    };
    badge.innerHTML = labels[status] || labels.idle;
  }

  // ── Agent Chat Info ──
  function updateAgentChatInfo() {
    const info = $('agentChatInfo');
    const agentName = state.agents.length > 0 ? esc(state.agents[0].name || state.agents[0].id || 'Unknown') : 'Coordinator';
    const online = state.agentOnline;
    info.innerHTML = `
      <i class="fas fa-robot"></i>
      <span>${agentName}</span>
      <span class="wb-agent-dot ${online ? 'online' : 'offline'}"></span>
    `;
    state.connectedAgent = agentName;
  }

  // ── Step Tree ──
  function renderStepTree() {
    const tree = $('workflowStepTree');
    tree.innerHTML = WORKFLOW_STEPS.map((step, i) => `
      <div class="wb-step-node" data-step="${step.id}">
        <div class="wb-step-node-icon pending">${i + 1}</div>
        <div class="wb-step-node-label">${step.label}</div>
        <div class="wb-step-node-badge">--</div>
      </div>
    `).join('');
  }

  function updateStepTreeStatus() {
    const runningCount = state.tasks.filter(t => (t.status || '').toLowerCase() === 'running').length;
    const completedCount = state.tasks.filter(t => (t.status || '').toLowerCase() === 'completed').length;
    const failedCount = state.tasks.filter(t => (t.status || '').toLowerCase() === 'failed').length;
    const hasAny = state.tasks.length > 0;

    let maxDoneStep = 0;
    if (!hasAny) {
      maxDoneStep = 0;
    } else if (runningCount > 0) {
      maxDoneStep = 3; // through dispatch
      setStatus('running');
    } else if (failedCount > 0) {
      maxDoneStep = hasAny ? 3 : 0;
      setStatus('error');
    } else if (completedCount > 0) {
      maxDoneStep = 7;
      setStatus('completed');
    } else {
      maxDoneStep = 0;
      setStatus('idle');
    }

    const nodes = document.querySelectorAll('.wb-step-node');
    nodes.forEach((node, i) => {
      const step = WORKFLOW_STEPS[i];
      const icon = node.querySelector('.wb-step-node-icon');
      const badge = node.querySelector('.wb-step-node-badge');

      icon.className = 'wb-step-node-icon';
      if (i < maxDoneStep - 1) {
        icon.classList.add('done');
        icon.innerHTML = '<i class="fas fa-check"></i>';
        badge.textContent = 'done';
      } else if (i === maxDoneStep - 1 && runningCount > 0) {
        icon.classList.add('running');
        icon.textContent = i + 1;
        badge.textContent = 'active';
      } else if (i === 6 && completedCount > 0 && runningCount === 0) {
        icon.classList.add('done');
        icon.innerHTML = '<i class="fas fa-check"></i>';
        badge.textContent = 'done';
      } else {
        icon.classList.add('pending');
        icon.textContent = i + 1;
        badge.textContent = '--';
      }
    });
  }

  // ── File Tree (dummy data) ──
  function renderFileTree() {
    const tree = $('projectFileTree');
    const mockFiles = [
      { type: 'folder', name: 'src', children: [
        { type: 'folder', name: 'agents', children: [
          { type: 'file', icon: 'fa-file-code', name: 'coordinator.py' },
          { type: 'file', icon: 'fa-file-code', name: 'executor.py' },
          { type: 'file', icon: 'fa-file-code', name: 'analyzer.py' }
        ]},
        { type: 'folder', name: 'tasks', children: [
          { type: 'file', icon: 'fa-file-code', name: 'task_manager.py' },
          { type: 'file', icon: 'fa-file-code', name: 'task_queue.py' }
        ]},
        { type: 'file', icon: 'fa-file-code', name: 'main.py' }
      ]},
      { type: 'folder', name: 'config', children: [
        { type: 'file', icon: 'fa-file-alt', name: 'settings.yaml' },
        { type: 'file', icon: 'fa-file-alt', name: 'agents.yaml' }
      ]},
      { type: 'file', icon: 'fa-file-alt', name: 'requirements.txt' },
      { type: 'file', icon: 'fa-file', name: 'README.md' }
    ];

    tree.innerHTML = renderFileNodes(mockFiles, 0);

    // Bind click for expand/collapse
    tree.querySelectorAll('.wb-file-node').forEach(node => {
      node.addEventListener('click', function (e) {
        e.stopPropagation();
        const arrow = this.querySelector('.wb-file-arrow');
        const children = this.nextElementSibling;
        if (arrow && children && children.classList.contains('wb-file-children')) {
          arrow.classList.toggle('expanded');
          children.style.display = arrow.classList.contains('expanded') ? '' : 'none';
        }
      });
    });
  }

  function renderFileNodes(nodes, depth) {
    return nodes.map(node => {
      let html = '';
      if (node.type === 'folder') {
        html += `<div class="wb-file-node" style="padding-left:${8 + depth * 14}px">
          <span class="wb-file-arrow expanded"><i class="fas fa-chevron-right"></i></span>
          <i class="fas fa-folder"></i> ${esc(node.name)}
        </div>`;
        if (node.children) {
          html += `<div class="wb-file-children">${renderFileNodes(node.children, depth + 1)}</div>`;
        }
      } else {
        html += `<div class="wb-file-node" style="padding-left:${8 + depth * 14 + 12}px">
          <span style="width:12px;flex-shrink:0"></span>
          <i class="fas ${node.icon || 'fa-file'}"></i> ${esc(node.name)}
        </div>`;
      }
      return html;
    }).join('');
  }

  // ── Sidebar Toggle ──
  function toggleSidebar() {
    state.sidebarCollapsed = !state.sidebarCollapsed;
    const sidebar = $('wbSidebar');
    const btn = $('btnToggleSidebar');
    sidebar.classList.toggle('collapsed', state.sidebarCollapsed);
    btn.querySelector('i').className = state.sidebarCollapsed ? 'fas fa-chevron-right' : 'fas fa-chevron-left';
  }

  // ── Tab Switching ──
  function switchSidebarTab(tabName) {
    document.querySelectorAll('.wb-sb-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.wb-sb-content').forEach(c => c.classList.remove('active'));

    const tabBtn = document.querySelector(`.wb-sb-tab[data-tab="${tabName}"]`);
    if (tabBtn) tabBtn.classList.add('active');

    const sbSteps = tabName === 'steps' ? $('sbSteps') : null;
    const sbFiles = tabName === 'files' ? $('sbFiles') : null;
    if (sbSteps) sbSteps.classList.add('active');
    if (sbFiles) sbFiles.classList.add('active');
  }

  function switchEditorTab(step) {
    state.currentStep = step;
    state.activeContentPanel = step;

    // Update tab active states
    document.querySelectorAll('.wb-editor-tab').forEach(t => t.classList.remove('active'));
    const tab = document.querySelector(`.wb-editor-tab[data-step="${step}"]`);
    if (tab) tab.classList.add('active');

    // Update content panel visibility
    document.querySelectorAll('.wb-content-panel').forEach(p => p.classList.remove('active'));
    const panel = $(`panel-${step}`);
    if (panel) panel.classList.add('active');

    // Update step tree active
    document.querySelectorAll('.wb-step-node').forEach(n => n.classList.remove('active'));
    const stepNode = document.querySelector(`.wb-step-node[data-step="${step}"]`);
    if (stepNode) stepNode.classList.add('active');

    // Update status bar
    const stepLabel = WORKFLOW_STEPS.find(s => s.id === step);
    $('sbCurrentStep').innerHTML = `<i class="fas fa-circle-notch"></i> 当前步骤: ${stepLabel ? stepLabel.label : '空闲'}`;
  }

  function switchBottomTab(tabName) {
    document.querySelectorAll('.wb-bt-tab').forEach(t => t.classList.remove('active'));
    const activeTab = document.querySelector(`.wb-bt-tab[data-bottom="${tabName}"]`);
    if (activeTab) activeTab.classList.add('active');

    $('bottomOutput').style.display = tabName === 'output' ? '' : 'none';
    $('bottomProblems').style.display = tabName === 'problems' ? '' : 'none';
  }

  // ── Bottom Panel ──
  function toggleBottom() {
    state.bottomCollapsed = !state.bottomCollapsed;
    const panel = $('wbBottomPanel');
    if (state.bottomCollapsed) {
      state.prevBottomH = panel.offsetHeight;
      panel.classList.add('collapsed');
      $('btnToggleBottom').querySelector('i').className = 'fas fa-chevron-up';
    } else {
      panel.classList.remove('collapsed');
      panel.style.height = state.prevBottomH + 'px';
      $('btnToggleBottom').querySelector('i').className = 'fas fa-chevron-down';
    }
  }

  function toggleMaxBottom() {
    state.bottomMaximized = !state.bottomMaximized;
    const panel = $('wbBottomPanel');
    if (state.bottomMaximized) {
      state.prevBottomH = panel.offsetHeight;
      panel.style.height = 'calc(100vh - 130px)';
      $('btnMaxBottom').querySelector('i').className = 'fas fa-minimize';
    } else {
      panel.style.height = state.prevBottomH + 'px';
      $('btnMaxBottom').querySelector('i').className = 'fas fa-maximize';
    }
  }

  // ── Workflow Control ──
  async function startWorkflow() {
    toast('正在启动工作流...', 'info');
    addLog('info', '启动工作流...');
    setStatus('running');
    state.progress = 5;
    updateProgress();

    try {
      const res = await apiPost('/api/v1/tasks', {
        name: '工作台任务 ' + new Date().toLocaleTimeString('zh-CN'),
        task_type: 'analysis',
        description: '从工作台启动的工作流任务'
      });
      if (res) {
        addLog('success', '工作流任务创建成功');
        toast('工作流已启动', 'success');
        switchEditorTab('init');
        refreshAll();
      }
    } catch (e) {
      addLog('error', '启动失败: ' + e.message);
      toast('启动失败: ' + e.message, 'error');
      setStatus('error');
    }
  }

  function pauseWorkflow() {
    addLog('warn', '工作流已暂停');
    toast('工作流已暂停', 'warning');
    setStatus('idle');
  }

  // ── Progress ──
  function updateProgress() {
    const runningCount = state.tasks.filter(t => (t.status || '').toLowerCase() === 'running').length;
    const total = state.tasks.length || 1;
    const completedCount = state.tasks.filter(t => (t.status || '').toLowerCase() === 'completed').length;

    let progress = 0;
    if (completedCount === total && total > 0) {
      progress = 100;
    } else if (runningCount > 0) {
      progress = Math.max(state.progress, 5 + Math.floor((completedCount / total) * 90));
    } else if (completedCount > 0) {
      progress = 80 + Math.floor((completedCount / total) * 20);
    } else if (state.tasks.length > 0) {
      progress = 10;
    }

    state.progress = Math.min(100, Math.max(state.progress, progress));
    $('wbProgressFill').style.width = state.progress + '%';
    $('wbProgressText').textContent = state.progress + '%';
  }

  // ── Execution Cards ──
  function updateExecutionCards() {
    const grid = $('executionCards');
    const empty = $('executionEmpty');
    const runningTasks = state.tasks.filter(t => (t.status || '').toLowerCase() === 'running');

    if (runningTasks.length === 0 && state.tasks.filter(t => (t.status || '').toLowerCase() !== 'running').length === 0) {
      grid.style.display = 'none';
      empty.style.display = '';
      return;
    }

    grid.style.display = '';
    empty.style.display = 'none';

    grid.innerHTML = state.tasks.slice(0, 8).map(t => {
      const status = (t.status || 'pending').toLowerCase();
      const progress = t.progress ?? 0;
      const name = t.name || t.title || t.id || 'Unnamed';
      const type = t.type || t.task_type || 'analysis';

      return `
        <div class="wb-agent-exec-card">
          <div class="wb-agent-exec-card-header">
            <div class="wb-agent-exec-card-name">${esc(name)}</div>
            <div class="wb-agent-exec-card-type">${esc(type)}</div>
          </div>
          <div style="font-size:10px;color:var(--text-muted)">${esc((t.id || '').slice(0, 12))} · ${status}</div>
          <div class="wb-agent-exec-card-progress">
            <div class="wb-agent-exec-card-progress-fill" style="width:${progress}%"></div>
          </div>
        </div>
      `;
    }).join('');
  }

  // ── Chat ──
  async function sendChat() {
    const input = $('chatInput');
    const msg = input.value.trim();
    if (!msg) return;

    // Remove empty state
    const empty = $('chatMessages').querySelector('.wb-chat-empty');
    if (empty) empty.remove();

    addChatMessage('user', msg);
    input.value = '';
    input.style.height = 'auto';

    // Show typing indicator
    const typingEl = document.createElement('div');
    typingEl.className = 'wb-chat-msg agent typing';
    typingEl.innerHTML = '<div class="wb-chat-msg-bubble"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div>';
    const container = $('chatMessages');
    container.appendChild(typingEl);
    container.scrollTop = container.scrollHeight;

    try {
      const res = await fetch('/api/v1/chat', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${API_KEY}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: msg,
          history: state.chatHistory || [],
        }),
      });

      // Remove typing indicator
      typingEl.remove();

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        if (res.status === 503) {
          addChatMessage('agent', 'LLM 未配置。请设置 SILICONFLOW_API_KEY 环境变量后重启服务。');
        } else {
          addChatMessage('agent', `错误: ${err.detail || '请求失败'}`);
        }
        return;
      }

      const data = await res.json();
      const reply = data.message;
      addChatMessage('agent', reply);

      // Update chat history
      state.chatHistory = state.chatHistory || [];
      state.chatHistory.push({ role: 'user', content: msg });
      state.chatHistory.push({ role: 'assistant', content: reply });
      // Keep last 10 turns
      if (state.chatHistory.length > 20) {
        state.chatHistory = state.chatHistory.slice(-20);
      }
    } catch (e) {
      typingEl.remove();
      addChatMessage('agent', '无法连接到服务器，请检查服务是否正常。');
    }

    addLog('event', '[Chat] 用户: ' + msg);
  }

  function addChatMessage(type, text) {
    const container = $('chatMessages');
    const time = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });

    const el = document.createElement('div');
    el.className = `wb-chat-msg ${type}`;
    el.innerHTML = `
      <div class="wb-chat-msg-bubble">${esc(text)}</div>
      <div class="wb-chat-msg-time">${time}</div>
    `;

    container.appendChild(el);

    if (state.autoScroll) {
      container.scrollTop = container.scrollHeight;
    }
  }

  // ── Logging ──
  function addLog(level, message) {
    const output = $('logOutput');
    const emptyLog = $('logEmpty');
    if (emptyLog) emptyLog.style.display = 'none';

    const time = new Date().toLocaleTimeString('zh-CN', { hour12: false });

    const entry = document.createElement('div');
    entry.className = 'wb-log-entry';
    entry.innerHTML = `
      <span class="wb-log-time">${time}</span>
      <span class="wb-log-level ${level}">[${level.toUpperCase()}]</span>
      <span class="wb-log-msg">${esc(message)}</span>
    `;

    output.appendChild(entry);

    // Keep max 500 entries
    while (output.children.length > 500) {
      output.firstChild.remove();
    }

    if (state.autoScroll) {
      output.scrollTop = output.scrollHeight;
    }

    // Also append to step-specific logs if applicable
    const stepLogMap = {
      init: 'initLogs',
      requirement: 'requirementLogs',
      dispatch: 'dispatchLogs',
      collection: 'collectionLogs',
      review: 'reviewLogs'
    };

    const stepLogId = stepLogMap[state.currentStep];
    if (stepLogId && $(stepLogId)) {
      const stepLog = $(stepLogId);
      const stepEmpty = $(state.currentStep + 'Empty');
      if (stepEmpty) stepEmpty.style.display = 'none';
      stepLog.style.display = '';
      const stepEntry = entry.cloneNode(true);
      stepLog.appendChild(stepEntry);
    }
  }

  function clearLogs() {
    const output = $('logOutput');
    output.innerHTML = `
      <div class="wb-log-empty" id="logEmpty">
        <i class="fas fa-terminal"></i>
        <span>输出已清除</span>
      </div>
    `;
  }

  // ── WebSocket ──
  function connectWebSocket() {
    const wsUrl = API_BASE.replace(/^http/, 'ws') + '/ws/events';
    try {
      state.ws = new WebSocket(wsUrl);

      state.ws.onopen = () => {
        state.wsConnected = true;
        updateConnectionStatus(true);
        addLog('success', 'WebSocket 已连接');
        console.log('WebSocket connected');
      };

      state.ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          handleWsMessage(msg);
        } catch (e) { /* ignore */ }
      };

      state.ws.onclose = () => {
        state.wsConnected = false;
        updateConnectionStatus(false);
        addLog('warn', 'WebSocket 断开，5s 后重连');
        state.wsReconnectTimer = setTimeout(connectWebSocket, 5000);
      };

      state.ws.onerror = () => { /* onclose follows */ };

    } catch (e) {
      console.warn('WS connect failed:', e);
      state.wsReconnectTimer = setTimeout(connectWebSocket, 5000);
    }
  }

  function handleWsMessage(msg) {
    const type = msg.type || msg.event_type || '';

    // Event bus events
    if (msg.type === 'event' || msg.event_type) {
      const eventType = msg.event_type || msg.type;
      const data = msg.data || msg;
      const stepInfo = data.step;

      if (stepInfo) {
        addLog('info', `[${stepInfo.status || 'update'}] ${stepInfo.title || 'step'}`);
      } else if (data.message || data.msg) {
        addLog('event', data.message || data.msg);
      }

      if (eventType.includes('task')) {
        refreshTasks();
      }
    }

    // Stream tracker
    if (msg.type === 'track') {
      const step = msg.step || msg;
      if (step && step.title) {
        addLog('event', `[tracker] ${step.title}: ${step.status || 'update'} [${step.progress || 0}%]`);
      }
    }

    // Chat messages from agent
    if (msg.type === 'chat' || msg.message_type === 'chat') {
      const chatMsg = msg.message || msg.content || msg.text || '';
      if (chatMsg) {
        addChatMessage('agent', chatMsg);
      }
    }
  }

  function updateConnectionStatus(connected) {
    const connEl = $('sbConnection');
    if (connected) {
      connEl.innerHTML = '<i class="fas fa-circle" style="font-size:8px;color:var(--accent-emerald)"></i> 已连接';
    } else {
      connEl.innerHTML = '<i class="fas fa-circle" style="font-size:8px;color:var(--accent-rose)"></i> 已断开';
    }
  }

  // ── Settings Modal ──
  function showSettings() {
    $('settingApiBase').value = API_BASE;
    $('settingWsUrl').value = API_BASE.replace(/^http/, 'ws') + '/ws/events';
    $('settingPollInterval').value = POLL_INTERVAL;
    $('settingAutoScroll').checked = state.autoScroll;
    $('settingsModal').classList.add('active');
  }

  function hideSettings() {
    $('settingsModal').classList.remove('active');
  }

  function saveSettings() {
    state.autoScroll = $('settingAutoScroll').checked;
    hideSettings();
    toast('设置已保存', 'success');
  }

  // ── Uptime ──
  function updateUptime() {
    const sec = Math.floor((Date.now() - START_TIME) / 1000);
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    $('sbUptime').innerHTML = `<i class="fas fa-clock"></i> 运行时间: ${h}h ${m}m`;
  }

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

  // ── Utilities ──
  function esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
  }

  // ── Start ──
  document.addEventListener('DOMContentLoaded', init);
})();
