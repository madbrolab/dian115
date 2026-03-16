
// STRM Manager JavaScript

const API_BASE = '/api';

// Toast通知系统
function showToast(message, type = 'info', duration = 3000) {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.style.cssText = 'position:fixed;top:20px;right:20px;z-index:10000;display:flex;flex-direction:column;gap:8px;pointer-events:none;';
        document.body.appendChild(container);
    }
    const icons = { success: 'ri-check-line', error: 'ri-close-circle-line', info: 'ri-information-line', warning: 'ri-alert-line' };
    const colors = { success: '#4caf50', error: '#f44336', info: '#2196f3', warning: '#ff9800' };
    const toast = document.createElement('div');
    toast.style.cssText = `pointer-events:auto;display:flex;align-items:center;gap:8px;padding:10px 16px;border-radius:8px;background:var(--card-bg,#fff);color:var(--text-color,#333);box-shadow:0 4px 12px rgba(0,0,0,0.15);border-left:4px solid ${colors[type] || colors.info};font-size:13px;opacity:0;transform:translateX(40px);transition:all 0.3s ease;max-width:360px;`;
    toast.innerHTML = `<i class="${icons[type] || icons.info}" style="color:${colors[type] || colors.info};font-size:16px;flex-shrink:0;"></i><span>${message}</span>`;
    container.appendChild(toast);
    requestAnimationFrame(() => { toast.style.opacity = '1'; toast.style.transform = 'translateX(0)'; });
    setTimeout(() => {
        toast.style.opacity = '0'; toast.style.transform = 'translateX(40px)';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    loadStatus();
    loadRules();
    loadSettings();
    loadEmbyProxies();
    load115Cookies();
    loadCategories();
    loadDashboardStats();
    
    // 启动SSE日志流（全局，页面加载即连接）
    startLogStream();
    
    // 定时刷新状态
    setInterval(loadStatus, 30000);
    // 定时刷新仪表板数据
    setInterval(loadDashboardStats, 60000);
    
    // 绑定导航事件
    document.querySelectorAll('.nav-item[data-page]').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const page = item.dataset.page;
            showPage(page);
        });
    });
    
    // 绑定设置标签页事件
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            switchSettingsTab(tab);
        });
    });
});

// ==================== 页面导航 ====================

function showPage(pageName) {
    // 隐藏所有页面
    document.querySelectorAll('.page').forEach(page => {
        page.classList.remove('active');
    });
    
    // 显示目标页面
    const targetPage = document.getElementById('page-' + pageName);
    if (targetPage) {
        targetPage.classList.add('active');
    }
    
    // 更新导航状态
    document.querySelectorAll('.nav-item[data-page]').forEach(item => {
        item.classList.remove('active');
        if (item.dataset.page === pageName) {
            item.classList.add('active');
        }
    });
    
    // 加载页面数据
    if (pageName === 'rules') {
        loadRules();
    } else if (pageName === 'settings') {
        loadSettings();
    } else if (pageName === 'emby302') {
        loadEmbyProxies();
    }
}

// ==================== 设置标签页切换 ====================

function switchSettingsTab(tabName) {
    // 更新标签按钮状态
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.tab === tabName) {
            btn.classList.add('active');
        }
    });
    
    // 更新标签内容
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    const targetContent = document.getElementById('tab-' + tabName);
    if (targetContent) {
        targetContent.classList.add('active');
    }
}

// ==================== 状态管理 ====================

async function loadStatus() {
    try {
        const resp = await fetch(`${API_BASE}/status`);
        const status = await resp.json();
        
        // 更新CD2状态
        const cd2Card = document.getElementById('cd2-status');
        const cd2Text = document.getElementById('cd2-status-text');
        if (status.cd2_connected) {
            cd2Card.className = 'status-card connected';
            cd2Text.textContent = '✓ 已连接';
        } else {
            cd2Card.className = 'status-card disconnected';
            cd2Text.textContent = '✗ 未连接';
        }
        
        // 更新115状态
        const s115Card = document.getElementById('s115-status');
        const s115Text = document.getElementById('s115-status-text');
        if (status.login_115) {
            const invalidCount = accounts115.filter(a => a.cookie_status === 'invalid').length;
            const activeInvalid = accounts115.find(a => a.is_active && a.cookie_status === 'invalid');
            if (activeInvalid) {
                s115Card.className = 'status-card disconnected';
                s115Text.innerHTML = `⚠ 当前Cookie已失效 <span style="font-size:11px;color:var(--danger);">请切换账号</span>`;
            } else if (invalidCount > 0) {
                s115Card.className = 'status-card connected';
                s115Text.innerHTML = `✓ ${status.user_115 || '已登录'} <span style="color:#ff9800;font-size:11px;">(${invalidCount}个Cookie失效)</span>`;
            } else {
                s115Card.className = 'status-card connected';
                s115Text.textContent = `✓ ${status.user_115 || '已登录'}`;
            }
        } else {
            s115Card.className = 'status-card disconnected';
            s115Text.textContent = '✗ 未登录';
        }
        
        // 更新Emby状态
        const embyCard = document.getElementById('emby-status');
        const embyText = document.getElementById('emby-status-text');
        if (status.emby_connected) {
            embyCard.className = 'status-card connected';
            embyText.textContent = '✓ 已连接';
        } else {
            embyCard.className = 'status-card disconnected';
            embyText.textContent = '✗ 未连接';
        }
        
    } catch (err) {
        console.error('加载状态失败:', err);
    }
}

// ==================== 规则管理 ====================

async function loadRules() {
    try {
        const resp = await fetch(`${API_BASE}/rules`);
        const rules = await resp.json();
        
        const container = document.getElementById('rules-list');
        
        if (!rules || rules.length === 0) {
            container.innerHTML = '<div class="empty-state"><i class="ri-folder-add-line" style="font-size:40px;margin-bottom:12px;display:block;"></i>暂无规则，点击"添加规则"创建</div>';
            return;
        }
        
        container.innerHTML = rules.map(rule => {
            // 格式化最后同步时间
            let lastSyncText = '从未同步';
            if (rule.last_sync_time && rule.last_sync_time !== '0001-01-01T00:00:00Z') {
                const d = new Date(rule.last_sync_time);
                lastSyncText = d.toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
            }

            // 同步方式标签
            let syncModeText = '手动';
            if (rule.sync_mode) {
                const modes = rule.sync_mode.split(',').map(m => m.trim());
                const labels = [];
                if (modes.includes('cron')) labels.push('定时');
                if (modes.includes('realtime')) labels.push('实时');
                if (labels.length > 0) syncModeText = labels.join('+');
            }

            // 目录树统计
            let treeStatsHtml = '';
            if (rule.tree_built) {
                treeStatsHtml = `<span class="rule-tag tree"><i class="ri-node-tree"></i> ${rule.tree_dir_count || 0}目录 / ${rule.tree_video_count || 0}视频</span>`;
            }

            return `
            <div class="rule-card ${rule.enabled ? '' : 'disabled'}">
                <div class="rule-header">
                    <div class="rule-name">${escapeHtml(rule.name)}</div>
                    <div class="rule-badges">
                        ${rule.enabled ? '<span class="rule-badge enabled">启用</span>' : '<span class="rule-badge disabled">停用</span>'}
                        <span class="rule-badge mode">${syncModeText}</span>
                    </div>
                </div>
                <div class="rule-paths">
                    <span><i class="ri-folder-line"></i> ${escapeHtml(rule.source_path)}</span>
                    <span><i class="ri-file-text-line"></i> ${escapeHtml(rule.output_path)}</span>
                </div>
                <div class="rule-stats-row">
                    <span class="rule-tag sync"><i class="ri-file-copy-line"></i> 已同步 ${rule.file_count || 0} 个文件</span>
                    ${treeStatsHtml}
                    <span class="rule-tag time"><i class="ri-time-line"></i> ${lastSyncText}</span>
                </div>
                <div class="rule-actions">
                    <button class="btn btn-sm ${rule.enabled ? 'btn-danger' : 'btn-success'}" onclick="toggleRule(${rule.id})" title="${rule.enabled ? '停用规则' : '启用规则'}">
                        <i class="${rule.enabled ? 'ri-stop-line' : 'ri-play-line'}"></i> ${rule.enabled ? '停用' : '启用'}
                    </button>
                    <button class="btn btn-sm btn-primary" onclick="syncRule(${rule.id})" ${!rule.enabled ? 'disabled' : ''}>
                        <i class="ri-refresh-line"></i> 同步
                    </button>
                    <button class="btn btn-sm btn-warning" onclick="fullSyncRule(${rule.id})" ${!rule.enabled ? 'disabled' : ''} title="重建目录树并同步">
                        <i class="ri-restart-line"></i> 全量
                    </button>
                    <button class="btn btn-sm" onclick="editRule(${rule.id})">
                        <i class="ri-edit-line"></i> 编辑
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="deleteRule(${rule.id})">
                        <i class="ri-delete-bin-line"></i>
                    </button>
                </div>
            </div>`;
        }).join('');
    } catch (err) {
        console.error('加载规则失败:', err);
    }
}

// ==================== 模板功能 ====================

let cachedRules = []; // 缓存规则列表用于模板

// 加载模板选项
async function loadTemplateOptions() {
    const select = document.getElementById('rule-template');
    if (!select) return;
    
    // 保留第一个默认选项
    select.innerHTML = '<option value="">默认（不使用模板）</option>';
    
    try {
        const resp = await fetch(`${API_BASE}/rules`);
        cachedRules = await resp.json() || [];
        
        cachedRules.forEach(rule => {
            const opt = document.createElement('option');
            opt.value = rule.id;
            opt.textContent = rule.name;
            select.appendChild(opt);
        });
    } catch (err) {
        console.error('加载模板列表失败:', err);
    }
}

// 应用模板
function applyTemplate() {
    const templateId = document.getElementById('rule-template').value;
    if (!templateId) return;
    
    const rule = cachedRules.find(r => r.id === parseInt(templateId));
    if (!rule) return;
    
    // 填充配置项（不覆盖名称、源路径、输出路径）
    document.getElementById('rule-recursive').checked = rule.recursive;
    document.getElementById('rule-exclude-keys').value = rule.exclude_keys || '';
    document.getElementById('rule-cloud-name').value = rule.cloud_name || '';
    document.getElementById('rule-file-extensions').value = rule.file_extensions || '';
    document.getElementById('rule-smart-clean').checked = rule.smart_clean || false;
    
    
    
    
    
    document.getElementById('rule-meta-extensions').value = rule.meta_extensions || '';
    
    
    // 同步方式
    setSyncMode(rule.sync_mode || 'manual');
    document.getElementById('rule-cron').value = rule.cron_expr || '';
    document.getElementById('rule-full-sync-cron').value = rule.full_sync_cron || '';
    
}

function showAddRuleModal() {
    document.getElementById('rule-modal-title').textContent = '添加规则';
    document.getElementById('rule-id').value = '';
    document.getElementById('rule-name').value = '';
    document.getElementById('rule-source').value = '';
    document.getElementById('rule-output').value = '';
    document.getElementById('rule-recursive').checked = true;
    document.getElementById('rule-enabled').checked = true;
    
    // 重置排除关键字
    document.getElementById('rule-exclude-keys').value = '';
    
    // 重置新字段
    document.getElementById('rule-cloud-name').value = '';
    document.getElementById('rule-file-extensions').value = '';
    
    
    
    
    
    
    // 重置模板选择
    document.getElementById('rule-template').value = '';
    document.getElementById('rule-template').parentElement.style.display = '';
    loadTemplateOptions();
    
    // 重置同步方式
    setSyncMode('manual');
    document.getElementById('rule-cron').value = '';
    document.getElementById('rule-full-sync-cron').value = '';
    
    // 重置智能清理和元数据后缀
    document.getElementById('rule-smart-clean').checked = false;
    document.getElementById('rule-meta-extensions').value = '';
    
    
    showModal('rule-modal');
}

async function editRule(id) {
    try {
        const resp = await fetch(`${API_BASE}/rules`);
        const rules = await resp.json();
        const rule = rules.find(r => r.id === id);
        
        if (!rule) {
            alert('规则不存在');
            return;
        }
        
        document.getElementById('rule-modal-title').textContent = '编辑规则';
        document.getElementById('rule-id').value = rule.id;
        
        // 编辑时隐藏模板选择
        document.getElementById('rule-template').parentElement.style.display = 'none';
        document.getElementById('rule-name').value = rule.name;
        document.getElementById('rule-source').value = rule.source_path;
        document.getElementById('rule-output').value = rule.output_path;
        document.getElementById('rule-recursive').checked = rule.recursive;
        document.getElementById('rule-enabled').checked = rule.enabled;
        document.getElementById('rule-exclude-keys').value = rule.exclude_keys || '';
        
        // 设置新字段
        document.getElementById('rule-cloud-name').value = rule.cloud_name || '';
        document.getElementById('rule-file-extensions').value = rule.file_extensions || '';
        document.getElementById('rule-smart-clean').checked = rule.smart_clean || false;
        
        
        
        
        
        document.getElementById('rule-meta-extensions').value = rule.meta_extensions || '';
        
        
        // 设置同步方式
        setSyncMode(rule.sync_mode || 'manual');
        document.getElementById('rule-cron').value = rule.cron_expr || '';
        document.getElementById('rule-full-sync-cron').value = rule.full_sync_cron || '';
        
        
        showModal('rule-modal');
    } catch (err) {
        alert('加载规则失败: ' + err.message);
    }
}

async function saveRule() {
    const id = document.getElementById('rule-id').value;
    const syncMode = getSyncMode();
    const rule = {
        name: document.getElementById('rule-name').value,
        source_path: document.getElementById('rule-source').value,
        output_path: document.getElementById('rule-output').value,
        recursive: document.getElementById('rule-recursive').checked,
        enabled: document.getElementById('rule-enabled').checked,
        sync_mode: syncMode,
        cron_expr: syncMode.includes('cron') ? document.getElementById('rule-cron').value : '',
        full_sync_cron: document.getElementById('rule-full-sync-cron').value,
        meta_extensions: document.getElementById('rule-meta-extensions').value,
        exclude_keys: document.getElementById('rule-exclude-keys').value,
        cloud_name: document.getElementById('rule-cloud-name').value,
        file_extensions: document.getElementById('rule-file-extensions').value,
        smart_clean: document.getElementById('rule-smart-clean').checked
    };
    
    if (!rule.name || !rule.source_path || !rule.output_path) {
        alert('请填写完整信息');
        return;
    }

    if (!rule.cloud_name) {
        alert('请填写115云盘名称');
        return;
    }
    
    if (syncMode.includes('cron') && !rule.cron_expr) {
        alert('请填写定时同步Cron表达式');
        return;
    }
    
    try {
        const url = id ? `${API_BASE}/rules/${id}` : `${API_BASE}/rules`;
        const method = id ? 'PUT' : 'POST';
        
        const resp = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(rule)
        });
        
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.error || '保存失败');
        }
        
        closeModal('rule-modal');
        loadRules();
    } catch (err) {
        alert('保存失败: ' + err.message);
    }
}

// ==================== 本地路径浏览器 ====================

let localPathTarget = null;
let currentLocalPath = '/';

function openLocalPathBrowser(target) {
    localPathTarget = target;
    const currentPath = document.getElementById('rule-output').value || '/';
    currentLocalPath = currentPath || '/';
    document.getElementById('selected-local-path').value = currentLocalPath;
    showModal('local-path-browser-modal');
    browseLocalPath(currentLocalPath);
}

async function browseLocalPath(path) {
    currentLocalPath = path;
    document.getElementById('selected-local-path').value = path;
    
    const listContainer = document.getElementById('local-path-list');
    listContainer.innerHTML = '<div class="loading">加载中...</div>';
    
    try {
        const resp = await fetch(`${API_BASE}/local-dirs?path=${encodeURIComponent(path)}`);
        const data = await resp.json();
        
        if (data.error) {
            listContainer.innerHTML = `<div class="error-state">${escapeHtml(data.error)}</div>`;
            return;
        }
        
        // 更新面包屑
        updateLocalPathBreadcrumb(data.current);
        
        // 渲染目录列表
        const entries = data.entries || [];
        if (entries.length === 0) {
            listContainer.innerHTML = '<div class="empty-state">空目录</div>';
            return;
        }
        
        listContainer.innerHTML = entries.map(entry => `
            <div class="path-item ${entry.is_dir ? 'folder' : 'file'}" onclick="browseLocalPath('${escapeHtml(entry.path)}')">
                <i class="ri-${entry.is_dir ? 'folder' : 'file'}-line"></i>
                <span>${escapeHtml(entry.name)}</span>
            </div>
        `).join('');
    } catch (err) {
        listContainer.innerHTML = `<div class="error-state">加载失败: ${escapeHtml(err.message)}</div>`;
    }
}

function updateLocalPathBreadcrumb(path) {
    const container = document.getElementById('local-path-breadcrumb');
    const parts = path.split('/').filter(p => p);
    
    let html = '<span class="breadcrumb-item" onclick="browseLocalPath(\'/\')">/</span>';
    let currentPath = '';
    
    parts.forEach((part, index) => {
        currentPath += '/' + part;
        const isLast = index === parts.length - 1;
        html += `<span class="breadcrumb-item${isLast ? ' active' : ''}" onclick="browseLocalPath('${escapeHtml(currentPath)}')">${escapeHtml(part)}</span>`;
    });
    
    container.innerHTML = html;
}

function confirmLocalPathSelection() {
    const selectedPath = document.getElementById('selected-local-path').value;
    if (localPathTarget === 'output') {
        document.getElementById('rule-output').value = selectedPath;
    }
    closeModal('local-path-browser-modal');
}

// 切换同步方式选项显示
function toggleSyncModeOptions() {
    const cronChecked = document.getElementById('sync-mode-cron').checked;
    const realtimeChecked = document.getElementById('sync-mode-realtime').checked;
    
    document.getElementById('cron-options').style.display = cronChecked ? 'block' : 'none';
    document.getElementById('realtime-options').style.display = realtimeChecked ? 'block' : 'none';
}

// 获取当前选中的同步模式（逗号分隔）
function getSyncMode() {
    const modes = [];
    if (document.getElementById('sync-mode-cron').checked) modes.push('cron');
    if (document.getElementById('sync-mode-realtime').checked) modes.push('realtime');
    return modes.length > 0 ? modes.join(',') : 'manual';
}

// 设置同步模式（支持逗号分隔的多模式）
function setSyncMode(syncMode) {
    const modes = (syncMode || 'manual').split(',');
    document.getElementById('sync-mode-cron').checked = modes.includes('cron');
    document.getElementById('sync-mode-realtime').checked = modes.includes('realtime');
    toggleSyncModeOptions();
}

// ==================== 目录树操作 ====================

// 启用/停用规则
async function toggleRule(ruleId) {
    try {
        const resp = await fetch(`${API_BASE}/rules/${ruleId}/toggle`, { method: 'POST' });
        const data = await resp.json();
        
        if (!resp.ok) {
            throw new Error(data.error || '操作失败');
        }
        
        loadRules();
    } catch (err) {
        alert('操作失败: ' + err.message);
    }
}

// 全量同步（重建目录树 + 同步STRM）
async function fullSyncRule(ruleId) {
    if (!confirm('全量同步将重新构建目录树并同步所有STRM文件，可能需要较长时间。确定继续？')) {
        return;
    }
    
    try {
        const resp = await fetch(`${API_BASE}/rules/${ruleId}/full-sync`, { method: 'POST' });
        const data = await resp.json();
        
        if (!resp.ok) {
            throw new Error(data.error || '启动失败');
        }
        
        alert('全量同步任务已启动，可在任务管理中查看进度。');
        loadRules();
    } catch (err) {
        alert('全量同步失败: ' + err.message);
    }
}

// 构建目录树
async function buildTree(ruleId) {
    if (!confirm('确定要构建/重建目录树吗？这将调用115 API遍历整个目录，可能需要较长时间。')) {
        return;
    }
    
    try {
        const resp = await fetch(`${API_BASE}/rules/${ruleId}/tree/build`, { method: 'POST' });
        const data = await resp.json();
        
        if (!resp.ok) {
            throw new Error(data.error || '构建失败');
        }
        
        alert('目录树构建任务已启动，可在任务管理中查看进度。任务ID: ' + data.task_id);
        loadRules();
    } catch (err) {
        alert('构建目录树失败: ' + err.message);
    }
}

// 格式化文件大小
function formatSize(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + units[i];
}

// ==================== 路径浏览器 ====================

let pathBrowserTarget = null; // 'source' 或 'output'
let currentBrowsePath = '/';

function openPathBrowser(target) {
    pathBrowserTarget = target;
    currentBrowsePath = '/';
    document.getElementById('selected-path').value = '/';
    browsePath('/');
    showModal('path-browser-modal');
}

async function browsePath(path) {
    currentBrowsePath = path;
    document.getElementById('selected-path').value = path;
    
    // 更新面包屑
    updateBreadcrumb(path);
    
    // 显示加载状态
    const listContainer = document.getElementById('path-list');
    listContainer.innerHTML = '<div class="loading">加载中...</div>';
    
    try {
        const resp = await fetch(`${API_BASE}/browse?path=${encodeURIComponent(path)}`);
        const data = await resp.json();
        
        if (data.error) {
            listContainer.innerHTML = `<div class="loading">加载失败: ${data.error}</div>`;
            return;
        }
        
        const files = data.files || [];
        
        if (files.length === 0) {
            listContainer.innerHTML = '<div class="loading">目录为空</div>';
            return;
        }
        
        // 只显示文件夹
        const folders = files.filter(f => f.is_dir);
        
        if (folders.length === 0) {
            listContainer.innerHTML = '<div class="loading">没有子目录</div>';
            return;
        }
        
        listContainer.innerHTML = folders.map(f => `
            <div class="path-item folder" onclick="selectPath('${escapeHtml(f.path)}')" ondblclick="browsePath('${escapeHtml(f.path)}')">
                <i class="ri-folder-fill"></i>
                <span class="path-item-name">${escapeHtml(f.name)}</span>
            </div>
        `).join('');
        
    } catch (err) {
        listContainer.innerHTML = `<div class="loading">加载失败: ${err.message}</div>`;
    }
}

function updateBreadcrumb(path) {
    const container = document.getElementById('path-breadcrumb');
    const parts = path.split('/').filter(p => p);
    
    let html = '<span class="breadcrumb-item" onclick="browsePath(\'/\')">根目录</span>';
    let currentPath = '';
    
    for (const part of parts) {
        currentPath += '/' + part;
        const pathCopy = currentPath;
        html += `<span class="breadcrumb-item" onclick="browsePath('${escapeHtml(pathCopy)}')">${escapeHtml(part)}</span>`;
    }
    
    container.innerHTML = html;
}

function selectPath(path) {
    currentBrowsePath = path;
    document.getElementById('selected-path').value = path;
    
    // 高亮选中项
    document.querySelectorAll('.path-item').forEach(el => {
        el.classList.remove('selected');
    });
    event.currentTarget.classList.add('selected');
}

function confirmPathSelection() {
    const selectedPath = document.getElementById('selected-path').value;
    
    if (pathBrowserTarget === 'source') {
        document.getElementById('rule-source').value = selectedPath;
    } else if (pathBrowserTarget === 'output') {
        document.getElementById('rule-output').value = selectedPath;
    }
    
    closeModal('path-browser-modal');
}

async function deleteRule(id) {
    if (!confirm('确定要删除这个规则吗？')) return;
    
    try {
        await fetch(`${API_BASE}/rules/${id}`, { method: 'DELETE' });
        loadRules();
    } catch (err) {
        alert('删除失败: ' + err.message);
    }
}

async function syncRule(id) {
    try {
        const resp = await fetch(`${API_BASE}/rules/${id}/sync`, { method: 'POST' });
        const result = await resp.json();
        
        if (result.error) {
            alert('同步失败: ' + result.error);
        } else if (result.task_id) {
            // 后台任务模式
            alert('同步任务已创建，请在"后台任务"页面查看进度');
            // 可选：自动跳转到任务页面
            // showPage('tasks');
        } else {
            // 兼容旧的同步结果格式
            if (result.errors && result.errors.length > 0) {
                alert(`同步完成（有错误）\n成功: ${result.success}, 失败: ${result.failed}`);
            } else {
                alert(`同步完成\n成功: ${result.success || 0}, 删除: ${result.deleted || 0}`);
            }
        }
        
        loadRules();
    } catch (err) {
        alert('同步失败: ' + err.message);
    }
}

async function syncAllRules() {
    try {
        const resp = await fetch(`${API_BASE}/rules/sync-all`, { method: 'POST' });
        const result = await resp.json();
        
        if (result.error) {
            alert('同步失败: ' + result.error);
        } else if (result.task_id) {
            // 后台任务模式
            alert('同步任务已创建，请在"后台任务"页面查看进度');
        } else {
            // 兼容旧的同步结果格式（数组）
            let totalSuccess = 0, totalFailed = 0, totalDeleted = 0;
            for (const r of result) {
                totalSuccess += r.success || 0;
                totalFailed += r.failed || 0;
                totalDeleted += r.deleted || 0;
            }
            alert(`同步完成\n总计: 成功 ${totalSuccess}, 失败 ${totalFailed}, 删除 ${totalDeleted}`);
        }
        
        loadRules();
    } catch (err) {
        alert('同步失败: ' + err.message);
    }
}

// 同步进度弹窗
function showSyncProgress(message) {
    let modal = document.getElementById('sync-progress-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'sync-progress-modal';
        modal.className = 'modal show';
        modal.innerHTML = `
            <div class="modal-content" style="max-width:400px;text-align:center;">
                <div class="modal-body" style="padding:40px;">
                    <div class="sync-spinner"></div>
                    <div class="sync-message" style="margin-top:20px;font-size:16px;"></div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    }
    modal.querySelector('.sync-message').textContent = message;
    modal.classList.add('show');
}

function hideSyncProgress() {
    const modal = document.getElementById('sync-progress-modal');
    if (modal) {
        modal.classList.remove('show');
    }
}

function showSyncResult(type, title, message) {
    let modal = document.getElementById('sync-result-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'sync-result-modal';
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-content" style="max-width:500px;">
                <div class="modal-header">
                    <h3 class="sync-result-title"></h3>
                    <button class="btn-close" onclick="closeSyncResult()">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="sync-result-icon"></div>
                    <pre class="sync-result-message" style="white-space:pre-wrap;word-break:break-all;max-height:300px;overflow-y:auto;background:var(--bg);padding:12px;border-radius:8px;font-size:13px;"></pre>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-primary" onclick="closeSyncResult()">确定</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    }
    
    const iconMap = {
        success: '<i class="ri-check-circle-line" style="font-size:48px;color:var(--success);"></i>',
        warning: '<i class="ri-alert-line" style="font-size:48px;color:var(--warning);"></i>',
        error: '<i class="ri-error-warning-line" style="font-size:48px;color:var(--danger);"></i>'
    };
    
    modal.querySelector('.sync-result-title').textContent = title;
    modal.querySelector('.sync-result-icon').innerHTML = iconMap[type] || iconMap.success;
    modal.querySelector('.sync-result-message').textContent = message;
    modal.classList.add('show');
}

function closeSyncResult() {
    const modal = document.getElementById('sync-result-modal');
    if (modal) {
        modal.classList.remove('show');
    }
}

// ==================== Emby代理管理 ====================

let currentEmbyProxy = null;

async function loadEmbyProxies() {
    try {
        // 获取Emby统计信息
        const statsResp = await fetch(`${API_BASE}/emby/stats`);
        const stats = await statsResp.json();
        
        const emptyState = document.getElementById('emby-empty-state');
        const embyContent = document.getElementById('emby-content');
        
        if (!stats.configured) {
            // 未配置Emby，显示空状态
            emptyState.style.display = 'flex';
            embyContent.style.display = 'none';
            return;
        }
        
        // 已配置Emby，显示内容
        emptyState.style.display = 'none';
        embyContent.style.display = 'block';
        
        // 更新统计卡片
        document.getElementById('emby-stat-playing').textContent = stats.playing_count || 0;
        document.getElementById('emby-stat-recent').textContent = '-';
        document.getElementById('emby-stat-movies').textContent = stats.movie_count || 0;
        document.getElementById('emby-stat-series').textContent = stats.series_count || 0;
        
        // 更新服务器信息
        document.getElementById('emby-server-name').textContent = stats.name || 'Emby服务器';
        document.getElementById('emby-server-url').textContent = stats.host || '-';
        document.getElementById('emby-proxy-port-display').textContent = stats.port || '-';
        document.getElementById('emby-302-status').textContent = stats.local_only ? '禁用' : '启用';
        
        const statusBadge = document.getElementById('emby-server-status');
        if (stats.online) {
            statusBadge.textContent = '在线';
            statusBadge.className = 'status-badge online';
        } else {
            statusBadge.textContent = '离线';
            statusBadge.className = 'status-badge offline';
        }
        
        // 保存当前代理信息
        currentEmbyProxy = stats;
        
        // 加载媒体内容
        loadEmbyPlayingSessions();
        loadEmbyRecentItems();
        loadRandomMedia();
        loadEmbyPopularItems();
        
    } catch (err) {
        console.error('加载Emby信息失败:', err);
    }
}

async function loadEmbyPlayingSessions() {
    try {
        const resp = await fetch(`${API_BASE}/emby/playing`);
        const sessions = await resp.json();
        
        const container = document.getElementById('emby-playing-list');
        
        if (!sessions || sessions.length === 0) {
            container.innerHTML = '<div class="empty-hint">暂无正在播放的内容</div>';
            return;
        }
        
        container.innerHTML = sessions.map(session => `
            <div class="playing-item">
                <div class="playing-poster">
                    <i class="ri-play-circle-fill"></i>
                </div>
                <div class="playing-info">
                    <div class="playing-title">${escapeHtml(session.title || '未知')}</div>
                    <div class="playing-meta">
                        <span>${escapeHtml(session.user || '未知用户')}</span>
                        <span>${escapeHtml(session.device || '')}</span>
                    </div>
                </div>
            </div>
        `).join('');
        
        // 更新正在播放数量
        document.getElementById('emby-stat-playing').textContent = sessions.length;
    } catch (err) {
        console.error('加载正在播放失败:', err);
    }
}

async function loadEmbyRecentItems() {
    try {
        const resp = await fetch(`${API_BASE}/emby/recent?limit=12`);
        const items = await resp.json();
        
        const container = document.getElementById('emby-recent-list');
        
        if (!items || items.length === 0) {
            container.innerHTML = '<div class="empty-hint">暂无最近入库的内容</div>';
            return;
        }
        
        container.innerHTML = items.map(item => `
            <div class="media-item" onclick="openEmbyMedia('${escapeHtml(item.id)}')">
                <div class="media-poster">
                    <img src="${escapeHtml(item.poster)}" alt="${escapeHtml(item.name)}" onerror="this.parentElement.innerHTML='<i class=\\'ri-film-line\\'></i>'">
                </div>
                <div class="media-title" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</div>
                <div class="media-year">${item.year || ''}</div>
            </div>
        `).join('');
        
        // 更新最近入库数量
        document.getElementById('emby-stat-recent').textContent = items.length;
    } catch (err) {
        console.error('加载最近入库失败:', err);
    }
}

async function loadRandomMedia() {
    try {
        const resp = await fetch(`${API_BASE}/emby/random?limit=12`);
        const items = await resp.json();
        
        const container = document.getElementById('emby-random-list');
        
        if (!items || items.length === 0) {
            container.innerHTML = '<div class="empty-hint">暂无媒体内容</div>';
            return;
        }
        
        container.innerHTML = items.map(item => `
            <div class="media-item" onclick="openEmbyMedia('${escapeHtml(item.id)}')">
                <div class="media-poster">
                    <img src="${escapeHtml(item.poster)}" alt="${escapeHtml(item.name)}" onerror="this.parentElement.innerHTML='<i class=\\'ri-film-line\\'></i>'">
                </div>
                <div class="media-title" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</div>
                <div class="media-year">${item.year || ''}</div>
            </div>
        `).join('');
    } catch (err) {
        console.error('加载随机媒体失败:', err);
    }
}

async function loadEmbyPopularItems() {
    try {
        const resp = await fetch(`${API_BASE}/emby/popular?limit=12`);
        const items = await resp.json();
        
        const container = document.getElementById('emby-popular-list');
        
        if (!items || items.length === 0) {
            container.innerHTML = '<div class="empty-hint">暂无热门内容</div>';
            return;
        }
        
        container.innerHTML = items.map(item => `
            <div class="media-item" onclick="openEmbyMedia('${escapeHtml(item.id)}')">
                <div class="media-poster">
                    <img src="${escapeHtml(item.poster)}" alt="${escapeHtml(item.name)}" onerror="this.parentElement.innerHTML='<i class=\\'ri-film-line\\'></i>'">
                </div>
                <div class="media-title" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</div>
                <div class="media-year">${item.year || ''}</div>
            </div>
        `).join('');
    } catch (err) {
        console.error('加载热门媒体失败:', err);
    }
}

// 打开Emby媒体详情页（通过302代理端口）
function openEmbyMedia(itemId) {
    if (!currentEmbyProxy || !currentEmbyProxy.port) {
        alert('Emby服务器未配置');
        return;
    }
    // 使用302代理端口，构建代理地址
    const proxyPort = currentEmbyProxy.port;
    const serverId = currentEmbyProxy.server_id || '';
    // 获取当前页面的主机名（不含端口）
    const hostname = window.location.hostname;
    // 构建代理URL（包含serverId）
    let proxyUrl = `http://${hostname}:${proxyPort}/web/index.html#!/item?id=${itemId}`;
    if (serverId) {
        proxyUrl += `&serverId=${serverId}`;
    }
    window.open(proxyUrl, '_blank');
}

function refreshEmbyStats() {
    loadEmbyProxies();
}

function showEditEmbyModal() {
    // 获取当前代理配置并打开编辑弹窗
    fetch(`${API_BASE}/emby-proxies`)
        .then(resp => resp.json())
        .then(proxies => {
            if (proxies && proxies.length > 0) {
                editEmbyProxy(proxies[0].id);
            } else {
                showAddEmbyProxyModal();
            }
        });
}

function showAddEmbyProxyModal() {
    document.getElementById('emby-proxy-modal-title').textContent = '添加Emby代理';
    document.getElementById('emby-proxy-id').value = '';
    document.getElementById('emby-proxy-name').value = '';
    document.getElementById('emby-proxy-host').value = '';
    document.getElementById('emby-proxy-apikey').value = '';
    document.getElementById('emby-proxy-port').value = '8098';
    document.getElementById('emby-proxy-cloud-name').value = '';
    document.getElementById('emby-proxy-enabled').checked = true;
    document.getElementById('emby-proxy-local-only').checked = false;
    document.getElementById('emby-proxy-fallback-local').checked = true;
    showModal('emby-proxy-modal');
}

async function editEmbyProxy(id) {
    try {
        const resp = await fetch(`${API_BASE}/emby-proxies`);
        const proxies = await resp.json();
        const proxy = proxies.find(p => p.id === id);
        
        if (!proxy) {
            alert('代理不存在');
            return;
        }
        
        document.getElementById('emby-proxy-modal-title').textContent = '编辑Emby代理';
        document.getElementById('emby-proxy-id').value = proxy.id;
        document.getElementById('emby-proxy-name').value = proxy.name;
        document.getElementById('emby-proxy-host').value = proxy.emby_host;
        document.getElementById('emby-proxy-apikey').value = proxy.api_key || '';
        document.getElementById('emby-proxy-port').value = proxy.proxy_port;
        document.getElementById('emby-proxy-cloud-name').value = proxy.cloud_name || '';
        document.getElementById('emby-proxy-enabled').checked = proxy.enabled;
        document.getElementById('emby-proxy-local-only').checked = proxy.local_only || false;
        document.getElementById('emby-proxy-fallback-local').checked = proxy.fallback_local !== false; // 默认true
        showModal('emby-proxy-modal');
    } catch (err) {
        alert('加载代理失败: ' + err.message);
    }
}

async function saveEmbyProxy() {
    const id = document.getElementById('emby-proxy-id').value;
    const proxy = {
        name: document.getElementById('emby-proxy-name').value,
        emby_host: document.getElementById('emby-proxy-host').value,
        api_key: document.getElementById('emby-proxy-apikey').value,
        proxy_port: parseInt(document.getElementById('emby-proxy-port').value) || 8098,
        cloud_name: document.getElementById('emby-proxy-cloud-name').value,
        enabled: document.getElementById('emby-proxy-enabled').checked,
        local_only: document.getElementById('emby-proxy-local-only').checked,
        fallback_local: document.getElementById('emby-proxy-fallback-local').checked
    };
    
    if (!proxy.name || !proxy.emby_host || !proxy.proxy_port) {
        alert('请填写完整信息');
        return;
    }
    
    try {
        const url = id ? `${API_BASE}/emby-proxies/${id}` : `${API_BASE}/emby-proxies`;
        const method = id ? 'PUT' : 'POST';
        
        const resp = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(proxy)
        });
        
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.error || '保存失败');
        }
        
        alert('保存成功！请重启服务以应用新的代理配置');
        closeModal('emby-proxy-modal');
        loadEmbyProxies();
    } catch (err) {
        alert('保存失败: ' + err.message);
    }
}

async function deleteEmbyProxy(id) {
    if (!confirm('确定要删除这个代理吗？')) return;
    
    try {
        await fetch(`${API_BASE}/emby-proxies/${id}`, { method: 'DELETE' });
        loadEmbyProxies();
    } catch (err) {
        alert('删除失败: ' + err.message);
    }
}

// ==================== CD2设置管理 ====================

async function loadSettings() {
    try {
        const resp = await fetch(`${API_BASE}/settings`);
        const settings = await resp.json();
        
        // CD2设置
        document.getElementById('cd2-host').value = settings.cd2_host || '';
        document.getElementById('cd2-username').value = settings.cd2_username || '';
        document.getElementById('cd2-mount-prefix').value = settings.cd2_mount_prefix || '';
        document.getElementById('cd2-apitoken').value = settings.cd2_api_token || '';
        
        // 设置认证方式
        const useApiToken = settings.cd2_use_api_token || false;
        if (useApiToken) {
            document.querySelector('input[name="cd2-auth-type"][value="apitoken"]').checked = true;
        } else {
            document.querySelector('input[name="cd2-auth-type"][value="password"]').checked = true;
        }
        toggleCD2AuthType();
        
        // HTTP代理设置
        document.getElementById('proxy-host').value = settings.proxy_host || '';
        document.getElementById('proxy-port').value = settings.proxy_port || '';
        document.getElementById('proxy-username').value = settings.proxy_username || '';
        
        // 企业微信设置
        document.getElementById('wechat-corpid').value = settings.wechat_corpid || '';
        document.getElementById('wechat-agentid').value = settings.wechat_agentid || '';
        document.getElementById('wechat-touser').value = settings.wechat_touser || '';
        
        // Telegram设置
        document.getElementById('tg-chatid').value = settings.tg_chatid || '';
        
        // 加载115状态
        load115Status();
        loadAutoSwitchSetting();
    } catch (err) {
        console.error('加载设置失败:', err);
    }
}

// 切换CD2认证方式
function toggleCD2AuthType() {
    const authType = document.querySelector('input[name="cd2-auth-type"]:checked').value;
    const passwordSection = document.getElementById('cd2-auth-password');
    const apiTokenSection = document.getElementById('cd2-auth-apitoken');
    const refreshTokenBtn = document.getElementById('cd2-refresh-token-btn');
    
    if (authType === 'apitoken') {
        passwordSection.style.display = 'none';
        apiTokenSection.style.display = 'block';
        if (refreshTokenBtn) refreshTokenBtn.style.display = 'none';
    } else {
        passwordSection.style.display = 'block';
        apiTokenSection.style.display = 'none';
        if (refreshTokenBtn) refreshTokenBtn.style.display = '';
    }
}

async function load115Status() {
    try {
        const resp = await fetch(`${API_BASE}/115/status`);
        const status = await resp.json();
        
        const container = document.getElementById('s115-login-status');
        if (status.logged_in) {
            container.className = 'login-status success';
            container.textContent = `✓ 已登录: ${status.user_info?.user_name || '未知用户'}`;
        } else {
            container.className = 'login-status error';
            container.textContent = '✗ 未登录';
        }
    } catch (err) {
        console.error('加载115状态失败:', err);
    }
}

async function saveCD2Settings() {
    const authType = document.querySelector('input[name="cd2-auth-type"]:checked').value;
    const useApiToken = authType === 'apitoken';
    
    const settings = {
        cd2_host: document.getElementById('cd2-host').value,
        cd2_mount_prefix: document.getElementById('cd2-mount-prefix').value,
        cd2_use_api_token: useApiToken
    };
    
    if (useApiToken) {
        settings.cd2_api_token = document.getElementById('cd2-apitoken').value;
    } else {
        settings.cd2_username = document.getElementById('cd2-username').value;
        settings.cd2_password = document.getElementById('cd2-password').value;
    }
    
    try {
        const resp = await fetch(`${API_BASE}/settings/cd2`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.error || '保存失败');
        }
        
        alert('CD2设置已保存');
        loadStatus();
    } catch (err) {
        alert('保存失败: ' + err.message);
    }
}

async function testCD2() {
    try {
        const authType = document.querySelector('input[name="cd2-auth-type"]:checked').value;
        const useApiToken = authType === 'apitoken';
        
        const params = {
            host: document.getElementById('cd2-host').value,
            use_api_token: useApiToken
        };
        
        if (useApiToken) {
            params.api_token = document.getElementById('cd2-apitoken').value;
        } else {
            params.username = document.getElementById('cd2-username').value;
            params.password = document.getElementById('cd2-password').value;
        }
        
        const resp = await fetch(`${API_BASE}/settings/test/cd2`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
        });
        const result = await resp.json();
        
        if (result.success) {
            alert('✓ CloudDrive2 连接成功');
            loadStatus();
        } else {
            alert('✗ 连接失败: ' + result.error);
        }
    } catch (err) {
        alert('测试失败: ' + err.message);
    }
}

async function refreshCD2Token() {
    try {
        const resp = await fetch(`${API_BASE}/settings/cd2/refresh-token`, { method: 'POST' });
        const result = await resp.json();
        
        if (result.success) {
            alert('✓ Token刷新成功');
        } else {
            alert('✗ 刷新失败: ' + result.error);
        }
    } catch (err) {
        alert('刷新失败: ' + err.message);
    }
}

// ==================== 115 账号管理 ====================

let accounts115 = [];
let draggedAccount = null;

async function load115Cookies() {
    // 兼容旧函数名，实际调用新的加载函数
    await loadAccounts115();
}

async function loadAccounts115() {
    const container = document.getElementById('account-115-list');
    if (!container) return;
    
    try {
        const resp = await fetch(`${API_BASE}/accounts/115`);
        accounts115 = await resp.json() || [];
        renderAccounts115();
    } catch (err) {
        console.error('加载115账号列表失败:', err);
        accounts115 = [];
        container.innerHTML = '<div class="empty-state" style="padding:20px;">暂无115账号，请扫码或手动添加</div>';
    }
}

function renderAccounts115() {
    const container = document.getElementById('account-115-list');
    if (!container) return;
    
    if (accounts115.length === 0) {
        container.innerHTML = '<div class="empty-state" style="padding:20px;">暂无115账号，请扫码或手动添加</div>';
        return;
    }

    const deviceLabel = (type) => {
        const map = {
            'ios':'115生活_苹果端','115ios':'115_苹果端','android':'115生活_安卓端',
            '115android':'115_安卓端','ipad':'115生活_苹果平板端','115ipad':'115_苹果平板端',
            'tv':'115生活_安卓电视端','apple_tv':'115生活_苹果电视端','qandroid':'115管理_安卓端',
            'qios':'115管理_苹果端','qipad':'115管理_苹果平板端','wechatmini':'115生活_微信小程序端',
            'alipaymini':'115生活_支付宝小程序端','harmony':'115_鸿蒙端'
        };
        return map[type] || type || '未知';
    };

    const formatSize = (bytes) => {
        if (!bytes || bytes === 0) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + units[i];
    };

    const statusColor = (status) => {
        switch(status) {
            case 'valid': return 'var(--success, #4caf50)';
            case 'invalid': return 'var(--danger, #f44336)';
            default: return 'var(--text-muted, #999)';
        }
    };
    
    container.innerHTML = '<div class="account-grid">' + accounts115.map(account => {
        const usedPct = account.space_total > 0 ? Math.round(account.space_used / account.space_total * 100) : 0;
        const avatarSrc = account.avatar_local ? '/' + account.avatar_local : (account.avatar_url || '');
        const avatarHtml = avatarSrc
            ? `<img src="${avatarSrc}" class="account-avatar" alt="avatar" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"><div class="account-avatar-fallback" style="display:none"><i class="ri-user-3-line"></i></div>`
            : `<div class="account-avatar-fallback"><i class="ri-user-3-line"></i></div>`;
        const configName = account.name || '未命名';
        return `
        <div class="account-card ${account.is_active ? 'active' : ''}" data-id="${account.id}" style="border-left: 4px solid ${statusColor(account.cookie_status)};">
            <div class="account-card-header">
                ${avatarHtml}
                <div class="account-card-title">
                    <div class="account-card-name" title="${escapeHtml(account.user_name || configName)}">${escapeHtml(account.user_name || configName)}${account.is_vip ? ' <i class="ri-vip-crown-line" style="color:#ff9800;"></i>' : ''}</div>
                    <div class="account-card-sub">${escapeHtml(configName)}${account.is_active ? ' <span class="badge-active">当前</span>' : ''}</div>
                </div>
            </div>
            <div class="account-card-body">
                <div class="account-card-device"><i class="ri-device-line"></i> ${deviceLabel(account.device_type)}</div>
                ${account.space_total > 0 ? `
                <div class="account-card-space">
                    <div class="space-bar"><div class="space-bar-fill" style="width:${usedPct}%"></div></div>
                    <span class="space-text">${formatSize(account.space_used)} / ${formatSize(account.space_total)}</span>
                </div>` : ''}
                ${account.auto_sign ? '<div class="account-card-sign"><i class="ri-calendar-check-line"></i> 自动签到</div>' : ''}
            </div>
            <div class="account-card-actions">
                ${account.is_active ?
                    '<button class="btn btn-xs btn-activate active" disabled title="已激活"><i class="ri-check-line"></i></button>' :
                    `<button class="btn btn-xs btn-activate" onclick="activateAccount115(${account.id})" title="激活"><i class="ri-play-line"></i></button>`
                }
                <button class="btn btn-xs" onclick="refreshAndCheckAccount115(${account.id}, this)" title="刷新并检查"><i class="ri-refresh-line"></i></button>
                <button class="btn btn-xs" onclick="openEditAccount115(${account.id})" title="编辑"><i class="ri-edit-line"></i></button>
                <button class="btn btn-xs btn-danger" onclick="deleteAccount115(${account.id})" ${account.is_active ? 'disabled' : ''} title="删除"><i class="ri-delete-bin-line"></i></button>
            </div>
        </div>`;
    }).join('') + '</div>';
    
    // 更新代理弹窗中的Cookie选择
    updateCookieSelect();
}

// 检查单个Cookie有效性（内部使用）
async function checkSingleCookie(id, btn) {
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line spin"></i>';
    }
    try {
        const resp = await fetch(`${API_BASE}/accounts/115/${id}/check`, { method: 'POST' });
        const data = await resp.json();
        if (data.status === 'valid') {
            btn && (btn.innerHTML = '<i class="ri-check-line" style="color:green;"></i>');
        } else {
            btn && (btn.innerHTML = '<i class="ri-close-line" style="color:red;"></i>');
        }
        return data.status;
    } catch (err) {
        showToast('检查失败: ' + err.message, 'error');
        btn && (btn.innerHTML = '<i class="ri-shield-check-line"></i>');
        return null;
    } finally {
        if (btn) btn.disabled = false;
    }
}

// 合并的刷新+检查按钮
async function refreshAndCheckAccount115(id, btn) {
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="ri-loader-4-line spin"></i>'; }
    try {
        // 先检查Cookie
        const checkResp = await fetch(`${API_BASE}/accounts/115/${id}/check`, { method: 'POST' });
        const checkData = await checkResp.json();
        
        // 再刷新信息
        const refreshResp = await fetch(`${API_BASE}/accounts/115/${id}/refresh`, { method: 'POST' });
        const refreshData = await refreshResp.json();
        
        if (checkData.status === 'valid') {
            showToast('Cookie有效，信息已刷新', 'success');
        } else {
            showToast('Cookie已失效', 'error');
        }
        
        if (refreshData.error) {
            showToast('刷新失败: ' + refreshData.error, 'error');
        }
        
        loadAccounts115();
    } catch (err) {
        showToast('操作失败: ' + err.message, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="ri-refresh-line"></i>'; }
    }
}

function updateCookieSelect() {
    const select = document.getElementById('emby-proxy-cookie');
    if (!select) return;
    
    select.innerHTML = '<option value="">默认账号</option>' +
        accounts115.map(account =>
            `<option value="${account.id}">${escapeHtml(account.name)}</option>`
        ).join('');
}

// 添加115账号
async function addAccount115() {
    const cookie = document.getElementById('s115-cookie-input').value.trim();
    const name = document.getElementById('s115-account-name').value.trim();
    const deviceType = document.getElementById('qrcode-device-type').value;
    const autoSign = document.getElementById('s115-auto-sign').checked;
    
    if (!cookie) {
        showToast('请输入Cookie', 'error');
        return;
    }
    
    try {
        const resp = await fetch(`${API_BASE}/accounts/115`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, cookie, device_type: deviceType, auto_sign: autoSign })
        });
        
        const result = await resp.json();
        
        if (result.error) {
            showToast('添加失败: ' + result.error, 'error');
            return;
        }
        
        showToast('账号添加成功', 'success');
        document.getElementById('s115-cookie-input').value = '';
        document.getElementById('s115-account-name').value = '';
        loadAccounts115();
        load115Status();
        loadStatus();
    } catch (err) {
        showToast('添加失败: ' + err.message, 'error');
    }
}

// 激活115账号
async function activateAccount115(id) {
    try {
        const resp = await fetch(`${API_BASE}/accounts/115/${id}/activate`, { method: 'POST' });
        const result = await resp.json();
        
        if (result.error) {
            showToast('激活失败: ' + result.error, 'error');
            return;
        }
        
        showToast('账号已激活', 'success');
        loadAccounts115();
        load115Status();
        loadStatus();
    } catch (err) {
        showToast('激活失败: ' + err.message, 'error');
    }
}

// 刷新115账号信息（保留兼容）
async function refreshAccount115(id, btn) {
    return refreshAndCheckAccount115(id, btn);
}

// 打开编辑115账号弹窗
async function openEditAccount115(id) {
    const account = accounts115.find(a => a.id === id);
    if (!account) return;

    // 获取完整Cookie
    let fullCookie = '';
    try {
        const resp = await fetch(`${API_BASE}/accounts/115/${id}/cookie`);
        const data = await resp.json();
        fullCookie = data.cookie || '';
    } catch(e) {}

    // 移除已有弹窗
    const existing = document.getElementById('edit-account-modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'edit-account-modal';
    modal.className = 'modal-overlay';
    modal.innerHTML = `
        <div class="modal-content" style="max-width:480px;">
            <div class="modal-header">
                <h3>编辑账号</h3>
                <button class="modal-close" onclick="document.getElementById('edit-account-modal').remove()">&times;</button>
            </div>
            <div class="modal-body">
                <div class="form-group">
                    <label>配置名称</label>
                    <input type="text" id="edit-acc-name" class="form-input" value="${escapeHtml(account.name)}">
                </div>
                <div class="form-group">
                    <label>Cookie</label>
                    <textarea id="edit-acc-cookie" class="form-input" rows="4" style="font-size:12px;word-break:break-all;">${escapeHtml(fullCookie)}</textarea>
                </div>
                <div class="form-group" style="display:flex;align-items:center;gap:8px;">
                    <label style="margin:0;">每日自动签到</label>
                    <label class="switch">
                        <input type="checkbox" id="edit-acc-autosign" ${account.auto_sign ? 'checked' : ''}>
                        <span class="slider"></span>
                    </label>
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn" onclick="document.getElementById('edit-account-modal').remove()">取消</button>
                <button class="btn btn-primary" onclick="saveEditAccount115(${id})">保存</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

// 保存编辑的115账号
async function saveEditAccount115(id) {
    const name = document.getElementById('edit-acc-name').value.trim();
    const cookie = document.getElementById('edit-acc-cookie').value.trim();
    const autoSign = document.getElementById('edit-acc-autosign').checked;

    if (!cookie) { showToast('Cookie不能为空', 'error'); return; }

    try {
        const resp = await fetch(`${API_BASE}/accounts/115/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, cookie, auto_sign: autoSign })
        });
        const result = await resp.json();
        if (result.error) {
            showToast('更新失败: ' + result.error, 'error');
            return;
        }
        showToast('账号已更新', 'success');
        document.getElementById('edit-account-modal').remove();
        loadAccounts115();
    } catch (err) {
        showToast('更新失败: ' + err.message, 'error');
    }
}

// 删除115账号
async function deleteAccount115(id) {
    if (!confirm('确定要删除这个账号吗？')) return;
    
    try {
        const resp = await fetch(`${API_BASE}/accounts/115/${id}`, { method: 'DELETE' });
        const result = await resp.json();
        
        if (result.error) {
            showToast('删除失败: ' + result.error, 'error');
            return;
        }
        
        showToast('账号已删除', 'success');
        loadAccounts115();
    } catch (err) {
        showToast('删除失败: ' + err.message, 'error');
    }
}

// 拖拽排序相关
function handleAccountDragStart(event, id) {
    draggedAccount = id;
    event.currentTarget.classList.add('dragging');
}

function handleAccountDragOver(event) {
    event.preventDefault();
}

function handleAccountDrop(event, targetId) {
    event.preventDefault();
    if (draggedAccount === null || draggedAccount === targetId) return;
    
    // 重新排序
    const draggedIndex = accounts115.findIndex(a => a.id === draggedAccount);
    const targetIndex = accounts115.findIndex(a => a.id === targetId);
    
    if (draggedIndex === -1 || targetIndex === -1) return;
    
    // 移动元素
    const [removed] = accounts115.splice(draggedIndex, 1);
    accounts115.splice(targetIndex, 0, removed);
    
    // 保存新顺序
    saveAccountsOrder();
    renderAccounts115();
}

function handleAccountDragEnd(event) {
    event.currentTarget.classList.remove('dragging');
    draggedAccount = null;
}

async function saveAccountsOrder() {
    const ids = accounts115.map(a => a.id);
    try {
        await fetch(`${API_BASE}/accounts/115/reorder`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids })
        });
    } catch (err) {
        console.error('保存排序失败:', err);
    }
}

// 兼容旧函数
function showAddCookieModal() {
    // 切换到115设置标签页
    switchSettingsTab('s115');
}

async function saveCookie() {
    await addAccount115();
}

async function setDefaultCookie(index) {
    // 兼容旧API
    if (accounts115[index]) {
        await activateAccount115(accounts115[index].id);
    }
}

async function deleteCookie(index) {
    // 兼容旧API
    if (accounts115[index]) {
        await deleteAccount115(accounts115[index].id);
    }
}

// ==================== 115扫码登录 ====================

let qrcodeCheckInterval = null;

async function show115QRCode() {
    const container = document.getElementById('qrcode-container');
    const statusText = document.getElementById('qrcode-status');
    const qrcodeImg = document.getElementById('qrcode-img');
    
    // 获取选中的设备类型
    const deviceSelect = document.getElementById('qrcode-device-type');
    const app = deviceSelect ? deviceSelect.value : 'web';
    
    const placeholder = document.getElementById('qrcode-placeholder');
    container.style.display = 'block';
    statusText.textContent = '正在获取二维码...';
    statusText.className = 'qrcode-status';
    qrcodeImg.style.display = 'none';
    if (placeholder) placeholder.style.display = 'flex';
    
    try {
        const resp = await fetch(`${API_BASE}/115/qrcode?app=${app}`);
        const qrcode = await resp.json();
        
        if (qrcode.error) {
            statusText.textContent = '获取二维码失败: ' + qrcode.error;
            statusText.className = 'qrcode-status error';
            return;
        }
        
        qrcodeImg.src = qrcode.qrcode;
        qrcodeImg.style.display = 'block';
        if (placeholder) placeholder.style.display = 'none';
        statusText.textContent = '请使用115 APP扫描二维码';
        
        // 开始轮询状态
        if (qrcodeCheckInterval) clearInterval(qrcodeCheckInterval);
        qrcodeCheckInterval = setInterval(checkQRCodeStatus, 2000);
    } catch (err) {
        statusText.textContent = '获取二维码失败: ' + err.message;
        statusText.className = 'qrcode-status error';
    }
}

async function checkQRCodeStatus() {
    const statusText = document.getElementById('qrcode-status');
    
    try {
        const resp = await fetch(`${API_BASE}/115/qrcode/status`);
        const result = await resp.json();
        
        switch (result.status) {
            case 0:
                statusText.textContent = '等待扫码...';
                break;
            case 1:
                statusText.textContent = '已扫码，请在手机上确认';
                break;
            case 2:
                statusText.textContent = '✓ 登录成功！正在获取Cookie...';
                statusText.className = 'qrcode-status success';
                clearInterval(qrcodeCheckInterval);
                
                // 完成登录并获取Cookie，填入输入框
                try {
                    const loginResp = await fetch(`${API_BASE}/115/login`, { method: 'POST' });
                    const loginResult = await loginResp.json();
                    
                    if (loginResult.success && loginResult.cookie) {
                        statusText.textContent = '✓ Cookie已获取，请点击"添加账号"保存';
                        // 将Cookie填入输入框
                        const cookieInput = document.getElementById('s115-cookie-input');
                        if (cookieInput) {
                            cookieInput.value = loginResult.cookie;
                        }
                        // 隐藏二维码，显示占位图标
                        document.getElementById('qrcode-img').style.display = 'none';
                        var ph = document.getElementById('qrcode-placeholder');
                        if (ph) ph.style.display = 'flex';
                    } else if (loginResult.success) {
                        // 兼容旧API：直接保存成功
                        statusText.textContent = '✓ 登录成功！账号已添加';
                        setTimeout(() => {
                            loadAccounts115();
                            load115Status();
                            loadStatus();
                        }, 1500);
                    } else {
                        statusText.textContent = '✗ 获取Cookie失败: ' + loginResult.error;
                        statusText.className = 'qrcode-status error';
                    }
                } catch (e) {
                    statusText.textContent = '✗ 获取Cookie失败: ' + e.message;
                    statusText.className = 'qrcode-status error';
                }
                break;
            case -1:
                statusText.textContent = '✗ 二维码已过期，请重新获取';
                statusText.className = 'qrcode-status error';
                clearInterval(qrcodeCheckInterval);
                break;
            case -2:
                statusText.textContent = '✗ 登录被拒绝';
                statusText.className = 'qrcode-status error';
                clearInterval(qrcodeCheckInterval);
                break;
        }
    } catch (err) {
        console.error('检查状态失败:', err);
    }
}

// ==================== Cookie健康检查 & 自动切换 ====================

// 检查所有Cookie有效性
async function checkAllCookies() {
    const btn = document.getElementById('btn-check-cookies');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line spin"></i> 检查中...';
    }
    try {
        const resp = await fetch(`${API_BASE}/115/check-cookies`, { method: 'POST' });
        const data = await resp.json();
        if (data.results) {
            const valid = data.results.filter(r => r.status === 'valid').length;
            const invalid = data.results.filter(r => r.status === 'invalid').length;
            alert(`检查完成：${valid} 个有效，${invalid} 个失效`);
        }
        loadAccounts115();
        loadStatus();
    } catch (err) {
        alert('检查失败: ' + err.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="ri-shield-check-line"></i> 检查Cookie';
        }
    }
}

// 切换自动切换开关
async function toggleAutoSwitch() {
    const toggle = document.getElementById('auto-switch-toggle');
    const enabled = toggle.checked;
    try {
        await fetch(`${API_BASE}/115/auto-switch`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled })
        });
    } catch (err) {
        console.error('保存自动切换设置失败:', err);
        toggle.checked = !toggle.checked;
    }
}

// 加载自动切换设置
async function loadAutoSwitchSetting() {
    try {
        const resp = await fetch(`${API_BASE}/settings`);
        const data = await resp.json();
        const toggle = document.getElementById('auto-switch-toggle');
        if (toggle) {
            toggle.checked = data['115_auto_switch'] === true;
        }
        // 加载QPS设置
        const qpsInput = document.getElementById('api-qps-input');
        if (qpsInput) {
            qpsInput.value = data['115_api_qps'] || 5;
        }
        const qpsDisplay = document.getElementById('api-qps-display');
        if (qpsDisplay) {
            qpsDisplay.textContent = data['115_api_qps'] || 5;
        }
    } catch (err) {
        console.error('加载设置失败:', err);
    }
}

// 保存115 API QPS限制
async function saveAPIRateLimit() {
    const qpsInput = document.getElementById('api-qps-input');
    if (!qpsInput) return;
    const qps = parseInt(qpsInput.value);
    if (isNaN(qps) || qps < 1 || qps > 50) {
        showToast('QPS必须在1-50之间', 'error');
        return;
    }
    try {
        const resp = await fetch(`${API_BASE}/115/rate-limit`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ qps })
        });
        const data = await resp.json();
        if (data.error) {
            showToast('保存失败: ' + data.error, 'error');
        } else {
            showToast('API频率限制已设为 ' + qps + ' 次/秒', 'success');
        }
    } catch (err) {
        showToast('保存失败: ' + err.message, 'error');
    }
}

// ==================== HTTP代理设置 ====================

async function saveProxySettings() {
    const settings = {
        proxy_host: document.getElementById('proxy-host').value,
        proxy_port: document.getElementById('proxy-port').value,
        proxy_username: document.getElementById('proxy-username').value,
        proxy_password: document.getElementById('proxy-password').value
    };
    
    try {
        const resp = await fetch(`${API_BASE}/settings/proxy`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.error || '保存失败');
        }
        
        alert('代理设置已保存');
    } catch (err) {
        alert('保存失败: ' + err.message);
    }
}

async function testProxy() {
    const host = document.getElementById('proxy-host').value;
    const port = document.getElementById('proxy-port').value;
    
    if (!host || !port) {
        alert('请填写代理地址和端口');
        return;
    }
    
    try {
        const resp = await fetch(`${API_BASE}/settings/test/proxy`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                host,
                port: parseInt(port),
                username: document.getElementById('proxy-username').value,
                password: document.getElementById('proxy-password').value
            })
        });
        const result = await resp.json();
        
        if (result.success) {
            alert('✓ 代理连接成功 (YouTube可访问)');
        } else {
            alert('✗ 代理测试失败: ' + result.error);
        }
    } catch (err) {
        alert('测试失败: ' + err.message);
    }
}

// ==================== 消息推送设置 ====================

async function saveWechatSettings() {
    const settings = {
        wechat_corpid: document.getElementById('wechat-corpid').value,
        wechat_secret: document.getElementById('wechat-secret').value,
        wechat_agentid: document.getElementById('wechat-agentid').value,
        wechat_touser: document.getElementById('wechat-touser').value
    };
    
    try {
        const resp = await fetch(`${API_BASE}/settings/wechat`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.error || '保存失败');
        }
        
        alert('企业微信设置已保存');
    } catch (err) {
        alert('保存失败: ' + err.message);
    }
}

async function testWechat() {
    try {
        const resp = await fetch(`${API_BASE}/settings/test/wechat`, { method: 'POST' });
        const result = await resp.json();
        
        if (result.success) {
            alert('✓ 测试消息已发送');
        } else {
            alert('✗ 发送失败: ' + result.error);
        }
    } catch (err) {
        alert('测试失败: ' + err.message);
    }
}

async function saveTelegramSettings() {
    const settings = {
        tg_token: document.getElementById('tg-token').value,
        tg_chatid: document.getElementById('tg-chatid').value
    };
    
    try {
        const resp = await fetch(`${API_BASE}/settings/telegram`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.error || '保存失败');
        }
        
        alert('Telegram设置已保存');
    } catch (err) {
        alert('保存失败: ' + err.message);
    }
}

async function testTelegram() {
    try {
        const resp = await fetch(`${API_BASE}/settings/test/telegram`, { method: 'POST' });
        const result = await resp.json();
        
        if (result.success) {
            alert('✓ 测试消息已发送');
        } else {
            alert('✗ 发送失败: ' + result.error);
        }
    } catch (err) {
        alert('测试失败: ' + err.message);
    }
}

// ==================== 分类设置 ====================

let categories = [];

async function loadCategories() {
    try {
        const resp = await fetch(`${API_BASE}/settings/categories`);
        categories = await resp.json() || [];
        renderCategories();
    } catch (err) {
        console.error('加载分类失败:', err);
        categories = [];
        renderCategories();
    }
}

function renderCategories() {
    const container = document.getElementById('category-list');
    
    if (categories.length === 0) {
        container.innerHTML = '<div class="empty-state" style="padding:20px;">暂无分类配置</div>';
        return;
    }
    
    const parentNames = {
        movie: '电影',
        tv: '电视剧',
        anime: '动漫',
        variety: '综艺',
        documentary: '纪录片'
    };
    
    container.innerHTML = categories.map((cat, index) => `
        <div class="category-item">
            <span class="category-parent">${parentNames[cat.parent] || cat.parent}</span>
            <span class="category-name">${escapeHtml(cat.name)}</span>
            <span class="category-keywords">${escapeHtml(cat.keywords)}</span>
            <button class="btn btn-sm btn-danger" onclick="deleteCategory(${index})">
                <i class="ri-delete-bin-line"></i>
            </button>
        </div>
    `).join('');
}

function showAddCategoryModal() {
    document.getElementById('category-parent').value = 'movie';
    document.getElementById('category-name').value = '';
    document.getElementById('category-keywords').value = '';
    showModal('category-modal');
}

function addCategory() {
    const category = {
        parent: document.getElementById('category-parent').value,
        name: document.getElementById('category-name').value,
        keywords: document.getElementById('category-keywords').value
    };
    
    if (!category.name) {
        alert('请填写分类名称');
        return;
    }
    
    categories.push(category);
    renderCategories();
    closeModal('category-modal');
}

function deleteCategory(index) {
    categories.splice(index, 1);
    renderCategories();
}

async function saveCategorySettings() {
    try {
        const resp = await fetch(`${API_BASE}/settings/categories`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(categories)
        });
        
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.error || '保存失败');
        }
        
        alert('分类设置已保存');
    } catch (err) {
        alert('保存失败: ' + err.message);
    }
}

// ==================== 工具函数 ====================

function showModal(id) {
    document.getElementById(id).classList.add('show');
}

function closeModal(id) {
    document.getElementById(id).classList.remove('show');
    
    // 清理二维码轮询
    if (qrcodeCheckInterval) {
        clearInterval(qrcodeCheckInterval);
        qrcodeCheckInterval = null;
    }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 点击弹窗外部关闭
document.querySelectorAll('.modal').forEach(modal => {
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            closeModal(modal.id);
        }
    });
});

// ==================== 日志管理 ====================

let logEventSource = null;
let logAutoScroll = true;
let logEntries = [];
let logCurrentPage = 0;
let logPageSize = 20;
let currentLogLevel = 'all';
let logAutoRefreshInterval = null;
let logStatsTimer = null;

const LOG_TYPE_LABELS = {
    'sync': 'STRM同步', 'monitor': '文件监控', 'scheduler': '定时任务',
    'emby': 'Emby代理', '115': '115网盘', 'system': '系统',
    'api': 'API', 'archive': '归档'
};

const LOG_LEVEL_LABELS = {
    'debug': 'DEBUG', 'info': '普通', 'success': '成功',
    'warning': '警告', 'error': '错误'
};

const LOG_CATEGORY_LABELS = {
    'normal': '普通', 'success': '成功', 'fail': '失败', 'error': '错误'
};

async function loadLogs() {
    const logType = document.getElementById('log-type-filter')?.value || 'all';
    const category = document.getElementById('log-category-filter')?.value || 'all';
    const offset = logCurrentPage * logPageSize;
    
    try {
        const params = new URLSearchParams({
            type: logType, category: category, level: currentLogLevel,
            limit: logPageSize, offset: offset
        });
        const resp = await fetch(`${API_BASE}/logs?${params}`);
        const data = await resp.json();
        logEntries = data.logs || [];
        renderLogs();
        renderLogPagination(data.total || 0);
    } catch (err) {
        console.error('加载日志失败:', err);
    }
}

async function loadLogStats() {
    try {
        const resp = await fetch(`${API_BASE}/logs/stats`);
        const stats = await resp.json();
        
        const setEl = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val || 0;
        };
        setEl('log-stat-total', stats.total);
        setEl('log-stat-today', stats.today);
        setEl('log-stat-success', stats.success_count);
        setEl('log-stat-error', stats.error_count || stats.today_errors);
        setEl('log-stat-warning', stats.warning_count);
    } catch (err) {
        console.error('加载日志统计失败:', err);
    }
}

function renderLogs() {
    const container = document.getElementById('log-output');
    if (!container) return;
    
    if (logEntries.length === 0) {
        container.innerHTML = `<div class="log-empty">
            <i class="ri-inbox-line" style="font-size: 48px; opacity: 0.3;"></i>
            <p>暂无日志记录</p>
        </div>`;
        return;
    }
    
    container.innerHTML = logEntries.map((entry, idx) => {
        const time = formatLogTime(entry.created_at);
        const typeClass = `type-${entry.type}`;
        const levelClass = `level-${entry.level}`;
        const entryClass = `entry-${entry.level}`;
        const typeLabel = LOG_TYPE_LABELS[entry.type] || entry.type;
        const levelIcon = getLogLevelIcon(entry.level);
        
        // 直接显示详情在消息中
        let fullMessage = escapeHtml(entry.message);
        if (entry.details && entry.details !== '' && entry.details !== '{}' && entry.details !== 'null') {
            try {
                const detailObj = JSON.parse(entry.details);
                const detailText = formatDetailsAsText(detailObj);
                if (detailText) {
                    fullMessage += `<div class="log-details-inline">${detailText}</div>`;
                }
            } catch(e) {
                // 如果不是JSON，直接显示
                if (entry.details.length < 200) {
                    fullMessage += `<div class="log-details-inline">${escapeHtml(entry.details)}</div>`;
                }
            }
        }
        
        let categoryHtml = '';
        if (entry.category && entry.category !== '') {
            const categoryLabel = LOG_CATEGORY_LABELS[entry.category] || entry.category;
            categoryHtml = `<span class="log-category-tag">${escapeHtml(categoryLabel)}</span>`;
        }
        
        return `
            <div class="log-entry ${entryClass}">
                <span class="log-time">${time}</span>
                <span class="log-type ${typeClass}">${typeLabel}</span>
                ${categoryHtml}
                <span class="log-level ${levelClass}">${levelIcon}</span>
                <div class="log-message">${fullMessage}</div>
            </div>
        `;
    }).join('');
    
    if (logAutoScroll) {
        container.scrollTop = 0;
    }
}

// 格式化详情为中文文本
function formatDetailsAsText(obj) {
    if (!obj || typeof obj !== 'object') return '';
    
    const parts = [];
    if (obj.file) parts.push(`文件: ${obj.file}`);
    if (obj.path) parts.push(`路径: ${obj.path}`);
    if (obj.error) parts.push(`错误: ${obj.error}`);
    if (obj.count !== undefined) parts.push(`数量: ${obj.count}`);
    if (obj.size !== undefined) parts.push(`大小: ${formatSize(obj.size)}`);
    if (obj.duration !== undefined) parts.push(`耗时: ${formatDuration(obj.duration)}`);
    if (obj.rule_id) parts.push(`规则ID: ${obj.rule_id}`);
    if (obj.rule_name) parts.push(`规则: ${obj.rule_name}`);
    
    return parts.length > 0 ? parts.join(' | ') : '';
}

function renderLogPagination(total) {
    const container = document.getElementById('log-pagination');
    if (!container) return;
    const maxPages = 50;
    let totalPages = Math.ceil(total / logPageSize);
    const cappedPages = Math.min(totalPages, maxPages);
    if (cappedPages <= 1) {
        container.innerHTML = '';
        return;
    }
    const overflowHint = totalPages > maxPages ? ` <span style="font-size:11px;color:#999;">(最多${maxPages}页)</span>` : '';
    container.innerHTML = `
        <button onclick="goLogPage(0)" ${logCurrentPage === 0 ? 'disabled' : ''}><i class="ri-skip-back-line"></i> 首页</button>
        <button onclick="goLogPage(${logCurrentPage - 1})" ${logCurrentPage === 0 ? 'disabled' : ''}><i class="ri-arrow-left-s-line"></i> 上一页</button>
        <span class="page-info">${logCurrentPage + 1} / ${cappedPages}${overflowHint}</span>
        <button onclick="goLogPage(${logCurrentPage + 1})" ${logCurrentPage >= cappedPages - 1 ? 'disabled' : ''}>下一页 <i class="ri-arrow-right-s-line"></i></button>
        <button onclick="goLogPage(${cappedPages - 1})" ${logCurrentPage >= cappedPages - 1 ? 'disabled' : ''}>末页 <i class="ri-skip-forward-line"></i></button>
    `;
}

function goLogPage(page) {
    logCurrentPage = Math.max(0, page);
    loadLogs();
}

function changeLogPageSize() {
    const select = document.getElementById('log-page-size');
    if (select) {
        logPageSize = parseInt(select.value) || 20;
        logCurrentPage = 0;
        loadLogs();
    }
}

function formatLogTime(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleString('zh-CN', {
        month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
    });
}

function getLogLevelIcon(level) {
    const icons = {
        debug: '<i class="ri-bug-line"></i>',
        info: '<i class="ri-information-line"></i>',
        success: '<i class="ri-check-line"></i>',
        warning: '<i class="ri-alert-line"></i>',
        error: '<i class="ri-error-warning-line"></i>'
    };
    return icons[level] || icons.info;
}

function toggleLogDetails(idx) {
    const el = document.getElementById(`log-details-${idx}`);
    if (el) el.classList.toggle('show');
}

function filterByLevel(level, btn) {
    currentLogLevel = level;
    document.querySelectorAll('.log-level-tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    logCurrentPage = 0;
    loadLogs();
}

function filterLogs() {
    logCurrentPage = 0;
    loadLogs();
}

function refreshLogs() {
    logCurrentPage = 0;
    loadLogs();
    loadLogStats();
}

function toggleLogScroll() {
    logAutoScroll = !logAutoScroll;
    const btn = document.getElementById('log-scroll-btn');
    if (logAutoScroll) {
        btn.innerHTML = '<i class="ri-pause-line"></i> 停止滚动';
    } else {
        btn.innerHTML = '<i class="ri-play-line"></i> 自动滚动';
    }
}

async function clearLogs() {
    if (!confirm('确定要清空日志吗？此操作不可恢复。')) return;
    
    const logType = document.getElementById('log-type-filter')?.value || 'all';
    
    try {
        await fetch(`${API_BASE}/logs?type=${logType}`, { method: 'DELETE' });
        logEntries = [];
        renderLogs();
        loadLogStats();
    } catch (err) {
        alert('清空日志失败: ' + err.message);
    }
}

function startLogAutoRefresh() {
    if (logAutoRefreshInterval) clearInterval(logAutoRefreshInterval);
    const checkbox = document.getElementById('log-auto-refresh');
    if (checkbox && checkbox.checked) {
        logAutoRefreshInterval = setInterval(() => {
            if (logCurrentPage === 0) {
                loadLogs();
                loadLogStats();
            }
        }, 10000);
    }
}

function toggleLogAutoRefresh() {
    startLogAutoRefresh();
}

let logStreamRetryCount = 0;

function startLogStream() {
    if (logEventSource) {
        logEventSource.close();
        logEventSource = null;
    }
    
    const streamUrl = `${API_BASE}/logs/stream?id=${Date.now()}`;
    logEventSource = new EventSource(streamUrl);
    
    // 连接成功确认
    logEventSource.addEventListener('connected', () => {
        console.log('日志SSE连接已建立');
        logStreamRetryCount = 0;
    });
    
    logEventSource.addEventListener('log', (event) => {
        try {
            const entry = JSON.parse(event.data);
            
            // 只在第一页时追加实时日志
            if (logCurrentPage !== 0) return;
            
            // 检查当前筛选条件
            const logType = document.getElementById('log-type-filter')?.value || 'all';
            const category = document.getElementById('log-category-filter')?.value || 'all';
            
            // 类型筛选
            if (logType !== 'all' && entry.type !== logType) return;
            // 类别筛选
            if (category !== 'all' && entry.category !== category) return;
            // 级别筛选
            if (currentLogLevel !== 'all' && entry.level !== currentLogLevel) return;
            
            // 追加到数组头部（最新的在前）
            logEntries.unshift(entry);
            
            // 限制日志数量
            if (logEntries.length > 500) {
                logEntries = logEntries.slice(0, 500);
            }
            
            // 增量追加DOM而非全量重渲染
            appendLogEntryToDOM(entry, 0);
            
            // 延迟刷新统计，避免频繁请求
            if (logStatsTimer) clearTimeout(logStatsTimer);
            logStatsTimer = setTimeout(() => loadLogStats(), 3000);
        } catch (e) {
            console.error('解析日志失败:', e);
        }
    });
    
    logEventSource.addEventListener('ping', () => {
        // 心跳保活，无需处理
    });
    
    logEventSource.onerror = () => {
        if (logEventSource) {
            logEventSource.close();
            logEventSource = null;
        }
        logStreamRetryCount++;
        const delay = Math.min(logStreamRetryCount * 2000, 15000);
        console.log(`日志流连接断开，${delay/1000}秒后重连(第${logStreamRetryCount}次)...`);
        setTimeout(startLogStream, delay);
    };
}

// 增量追加单条日志到DOM
function appendLogEntryToDOM(entry, idx) {
    const container = document.getElementById('log-output');
    if (!container) return;
    
    // 移除空状态
    const emptyEl = container.querySelector('.log-empty');
    if (emptyEl) emptyEl.remove();
    
    const time = formatLogTime(entry.created_at);
    const typeClass = `type-${entry.type}`;
    const levelClass = `level-${entry.level}`;
    const entryClass = `entry-${entry.level}`;
    const typeLabel = LOG_TYPE_LABELS[entry.type] || entry.type;
    const levelIcon = getLogLevelIcon(entry.level);
    const categoryLabel = LOG_CATEGORY_LABELS[entry.category] || entry.category || '';
    
    let categoryHtml = '';
    if (categoryLabel) {
        categoryHtml = `<span class="log-category-tag">${escapeHtml(categoryLabel)}</span>`;
    }
    
    // 直接显示详情
    let fullMessage = escapeHtml(entry.message);
    if (entry.details && entry.details !== '' && entry.details !== '{}' && entry.details !== 'null') {
        try {
            const detailObj = JSON.parse(entry.details);
            const detailText = formatDetailsAsText(detailObj);
            if (detailText) fullMessage += `<div class="log-details-inline">${detailText}</div>`;
        } catch(e) {
            if (entry.details.length < 200) fullMessage += `<div class="log-details-inline">${escapeHtml(entry.details)}</div>`;
        }
    }

    const div = document.createElement('div');
    div.className = `log-entry ${entryClass} new`;
    div.innerHTML = `
        <span class="log-time">${time}</span>
        <span class="log-type ${typeClass}">${typeLabel}</span>
        ${categoryHtml}
        <span class="log-level ${levelClass}">${levelIcon}</span>
        <div class="log-message">${fullMessage}</div>
    `;
    
    // 插入到顶部
    if (container.firstChild) {
        container.insertBefore(div, container.firstChild);
    } else {
        container.appendChild(div);
    }
    
    // 移除动画class
    setTimeout(() => div.classList.remove('new'), 300);
    
    // 限制DOM节点数量
    const entries = container.querySelectorAll('.log-entry');
    if (entries.length > 500) {
        entries[entries.length - 1].remove();
    }
    
    if (logAutoScroll) {
        container.scrollTop = 0;
    }
}

// ==================== 历史记录管理 ====================

let historyRecords = [];
let historyPage = 1;
let historyTotal = 0;
const historyPageSize = 20;

async function loadHistoryRecords(page = 1) {
    historyPage = page;
    const recordType = document.getElementById('history-type-filter')?.value || 'all';
    const offset = (page - 1) * historyPageSize;
    
    try {
        const resp = await fetch(`${API_BASE}/history?type=${recordType}&limit=${historyPageSize}&offset=${offset}`);
        const data = await resp.json();
        historyRecords = data.records || [];
        historyTotal = data.total || 0;
        renderHistoryRecords();
        updateHistoryPagination();
        loadHistoryStats();
    } catch (err) {
        console.error('加载历史记录失败:', err);
    }
}

function renderHistoryRecords() {
    const container = document.getElementById('history-list');
    if (!container) return;
    
    if (historyRecords.length === 0) {
        container.innerHTML = '<div class="empty-state" style="padding:40px;">暂无历史记录</div>';
        return;
    }
    
    container.innerHTML = historyRecords.map(record => `
        <div class="history-item">
            <div class="history-icon ${record.type}">
                <i class="ri-${record.type === 'sync' ? 'refresh' : 'archive'}-line"></i>
            </div>
            <div class="history-info">
                <div class="history-title">${escapeHtml(record.rule_name || '未知规则')}</div>
                <div class="history-meta">
                    <span>${formatDateTime(record.created_at)}</span>
                    <span>耗时: ${formatDuration(record.duration)}</span>
                </div>
            </div>
            <div class="history-stats-inline">
                <span class="success"><i class="ri-check-line"></i> ${record.success}</span>
                <span class="failed"><i class="ri-close-line"></i> ${record.failed}</span>
            </div>
        </div>
    `).join('');
}

function updateHistoryPagination() {
    const totalPages = Math.ceil(historyTotal / historyPageSize) || 1;
    
    document.getElementById('history-pagination-info').textContent = `共 ${historyTotal} 条`;
    document.getElementById('history-page-info').textContent = `${historyPage} / ${totalPages}`;
    document.getElementById('history-prev-btn').disabled = historyPage <= 1;
    document.getElementById('history-next-btn').disabled = historyPage >= totalPages;
}

async function loadHistoryStats() {
    try {
        const resp = await fetch(`${API_BASE}/history/stats`);
        const stats = await resp.json();
        
        document.getElementById('history-sync-count').textContent = stats.sync || 0;
        document.getElementById('history-archive-count').textContent = stats.archive || 0;
    } catch (err) {
        console.error('加载历史统计失败:', err);
    }
}

function formatDateTime(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function formatDuration(ms) {
    if (ms < 1000) return ms + '毫秒';
    if (ms < 60000) return (ms / 1000).toFixed(2) + '秒';
    return (ms / 60000).toFixed(1) + '分';
}

// ==================== 媒体分类管理 ====================

let mediaCategories = [];
let currentMediaType = 'movie';

async function loadMediaCategories(mediaType = currentMediaType) {
    currentMediaType = mediaType;
    
    try {
        const resp = await fetch(`${API_BASE}/categories?media_type=${mediaType}`);
        mediaCategories = await resp.json() || [];
        renderMediaCategories();
    } catch (err) {
        console.error('加载分类失败:', err);
        mediaCategories = [];
        renderMediaCategories();
    }
}

function renderMediaCategories() {
    const container = document.getElementById('category-list');
    if (!container) return;
    
    if (mediaCategories.length === 0) {
        container.innerHTML = '<div class="empty-state" style="padding:20px;">暂无分类配置</div>';
        return;
    }
    
    container.innerHTML = mediaCategories.map(cat => {
        const conditions = parseConditions(cat.conditions);
        return `
            <div class="category-item" data-id="${cat.id}" draggable="true"
                 ondragstart="handleCategoryDragStart(event, ${cat.id})"
                 ondragover="handleCategoryDragOver(event)"
                 ondrop="handleCategoryDrop(event, ${cat.id})"
                 ondragend="handleCategoryDragEnd(event)">
                <div class="category-drag-handle">
                    <i class="ri-drag-move-2-line"></i>
                </div>
                <div class="category-info">
                    <div class="category-name">${escapeHtml(cat.name)}</div>
                    <div class="category-conditions">${conditions}</div>
                </div>
                ${cat.is_default ? '<span class="category-badge default">默认</span>' : ''}
                <div class="category-actions">
                    <button class="btn btn-sm" onclick="editMediaCategory(${cat.id})">
                        <i class="ri-edit-line"></i>
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="deleteMediaCategory(${cat.id})" ${cat.is_default ? 'disabled' : ''}>
                        <i class="ri-delete-bin-line"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

function parseConditions(conditionsStr) {
    if (!conditionsStr || conditionsStr === '{}') return '无条件（默认分类）';
    
    try {
        const cond = JSON.parse(conditionsStr);
        const parts = [];
        if (cond.genre_ids) parts.push(`类型ID: ${cond.genre_ids}`);
        if (cond.original_language) parts.push(`语言: ${cond.original_language}`);
        if (cond.origin_country) parts.push(`国家: ${cond.origin_country}`);
        return parts.join(', ') || '无条件';
    } catch (e) {
        return conditionsStr;
    }
}

function switchCategoryTab(mediaType) {
    currentMediaType = mediaType;
    
    document.querySelectorAll('.category-tabs .tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mediaType === mediaType);
    });
    
    loadMediaCategories(mediaType);
}

function showAddCategoryModal() {
    // TODO: 实现添加分类弹窗
    const name = prompt('分类名称:');
    if (!name) return;
    
    const conditions = prompt('匹配条件 (JSON格式，如 {"genre_ids":"16"}):', '{}');
    
    createMediaCategory({
        media_type: currentMediaType,
        name: name,
        conditions: conditions || '{}'
    });
}

async function createMediaCategory(category) {
    try {
        const resp = await fetch(`${API_BASE}/categories`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(category)
        });
        
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.error || '创建失败');
        }
        
        loadMediaCategories();
    } catch (err) {
        alert('创建分类失败: ' + err.message);
    }
}

async function editMediaCategory(id) {
    const cat = mediaCategories.find(c => c.id === id);
    if (!cat) return;
    
    const name = prompt('分类名称:', cat.name);
    if (name === null) return;
    
    const conditions = prompt('匹配条件 (JSON格式):', cat.conditions);
    if (conditions === null) return;
    
    try {
        const resp = await fetch(`${API_BASE}/categories/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, conditions })
        });
        
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.error || '更新失败');
        }
        
        loadMediaCategories();
    } catch (err) {
        alert('更新分类失败: ' + err.message);
    }
}

async function deleteMediaCategory(id) {
    if (!confirm('确定要删除这个分类吗？')) return;
    
    try {
        await fetch(`${API_BASE}/categories/${id}`, { method: 'DELETE' });
        loadMediaCategories();
    } catch (err) {
        alert('删除分类失败: ' + err.message);
    }
}

// 分类拖拽排序
let draggedCategoryId = null;

function handleCategoryDragStart(event, id) {
    draggedCategoryId = id;
    event.currentTarget.classList.add('dragging');
}

function handleCategoryDragOver(event) {
    event.preventDefault();
}

function handleCategoryDrop(event, targetId) {
    event.preventDefault();
    if (draggedCategoryId === null || draggedCategoryId === targetId) return;
    
    const draggedIndex = mediaCategories.findIndex(c => c.id === draggedCategoryId);
    const targetIndex = mediaCategories.findIndex(c => c.id === targetId);
    
    if (draggedIndex === -1 || targetIndex === -1) return;
    
    const [removed] = mediaCategories.splice(draggedIndex, 1);
    mediaCategories.splice(targetIndex, 0, removed);
    
    saveCategoryOrder();
    renderMediaCategories();
}

function handleCategoryDragEnd(event) {
    event.currentTarget.classList.remove('dragging');
    draggedCategoryId = null;
}

async function saveCategoryOrder() {
    const ids = mediaCategories.map(c => c.id);
    try {
        await fetch(`${API_BASE}/categories/reorder`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids })
        });
    } catch (err) {
        console.error('保存排序失败:', err);
    }
}

// ==================== 整理规则管理 ====================

let organizeRules = [];

async function loadOrganizeRules() {
    try {
        const resp = await fetch(`${API_BASE}/organize-rules`);
        organizeRules = await resp.json() || [];
        renderOrganizeRules();
    } catch (err) {
        console.error('加载整理规则失败:', err);
        organizeRules = [];
        renderOrganizeRules();
    }
}

function renderOrganizeRules() {
    const container = document.getElementById('organize-rules-list');
    if (!container) return;
    
    if (organizeRules.length === 0) {
        container.innerHTML = '<div class="empty-state" style="padding:40px;">暂无整理规则，点击上方按钮添加</div>';
        return;
    }
    
    container.innerHTML = organizeRules.map(rule => `
        <div class="organize-rule-item">
            <div class="organize-rule-icon ${rule.media_type}">
                <i class="ri-${rule.media_type === 'movie' ? 'film' : 'tv'}-line"></i>
            </div>
            <div class="organize-rule-info">
                <div class="organize-rule-name">${escapeHtml(rule.name)}</div>
                <div class="organize-rule-paths">
                    ${escapeHtml(rule.source_path)} → ${escapeHtml(rule.target_path)}
                </div>
            </div>
            <div class="organize-rule-actions">
                <button class="btn btn-sm" onclick="editOrganizeRule(${rule.id})">
                    <i class="ri-edit-line"></i>
                </button>
                <button class="btn btn-sm btn-danger" onclick="deleteOrganizeRule(${rule.id})">
                    <i class="ri-delete-bin-line"></i>
                </button>
            </div>
        </div>
    `).join('');
}

function showAddOrganizeRuleModal() {
    const name = prompt('规则名称:');
    if (!name) return;
    
    const sourcePath = prompt('源路径:');
    if (!sourcePath) return;
    
    const targetPath = prompt('目标路径:');
    if (!targetPath) return;
    
    const mediaType = prompt('媒体类型 (movie/tv):', 'movie');
    
    createOrganizeRule({
        name,
        source_path: sourcePath,
        target_path: targetPath,
        media_type: mediaType || 'movie',
        use_category: true
    });
}

async function createOrganizeRule(rule) {
    try {
        const resp = await fetch(`${API_BASE}/organize-rules`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(rule)
        });
        
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.error || '创建失败');
        }
        
        loadOrganizeRules();
    } catch (err) {
        alert('创建规则失败: ' + err.message);
    }
}

async function editOrganizeRule(id) {
    const rule = organizeRules.find(r => r.id === id);
    if (!rule) return;
    
    const name = prompt('规则名称:', rule.name);
    if (name === null) return;
    
    const sourcePath = prompt('源路径:', rule.source_path);
    if (sourcePath === null) return;
    
    const targetPath = prompt('目标路径:', rule.target_path);
    if (targetPath === null) return;
    
    try {
        const resp = await fetch(`${API_BASE}/organize-rules/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name,
                source_path: sourcePath,
                target_path: targetPath,
                media_type: rule.media_type,
                use_category: rule.use_category,
                enabled: rule.enabled
            })
        });
        
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.error || '更新失败');
        }
        
        loadOrganizeRules();
    } catch (err) {
        alert('更新规则失败: ' + err.message);
    }
}

async function deleteOrganizeRule(id) {
    if (!confirm('确定要删除这个规则吗？')) return;
    
    try {
        await fetch(`${API_BASE}/organize-rules/${id}`, { method: 'DELETE' });
        loadOrganizeRules();
    } catch (err) {
        alert('删除规则失败: ' + err.message);
    }
}

// ==================== 仪表板数据 ====================

// 计算入库统计应显示的条数
function calculateLibraryLimit() {
    const container = document.getElementById('latest-movies');
    if (!container) return 20;
    
    // 根据容器高度计算可显示的条数
    const containerHeight = container.clientHeight || 400;
    const itemHeight = 80; // 每个项目大约80px高度
    const limit = Math.max(6, Math.floor(containerHeight / itemHeight));
    return Math.min(limit, 50); // 最多50条
}

async function loadDashboardStats() {
    try {
        const limit = calculateLibraryLimit();
        const resp = await fetch(`${API_BASE}/dashboard/stats?limit=${limit}`);
        const data = await resp.json();
        
        // 更新入库统计
        if (data.library) {
            const libTotal = document.getElementById('library-total');
            if (libTotal) libTotal.textContent = data.library.total || 0;
            renderLatestMovies(data.library.latest_movies || []);
        }
        
        // 更新302跳转统计
        if (data.redirect) {
            const redPlaying = document.getElementById('redirect-playing');
            const redToday = document.getElementById('redirect-today');
            const redTotal = document.getElementById('redirect-total');
            if (redPlaying) redPlaying.textContent = data.redirect.playing || 0;
            if (redToday) redToday.textContent = data.redirect.today || 0;
            if (redTotal) redTotal.textContent = data.redirect.total || 0;
            renderPlayingNow(data.redirect.playing_now || []);
        }
        
        // 更新同步图表
        if (data.syncChart) {
            renderSyncChart(data.syncChart);
        }
        
        // 更新关键指标
        if (data.metrics) {
            const strmTotal = document.getElementById('metric-strm-total');
            const strmToday = document.getElementById('metric-strm-today');
            const sync24h = document.getElementById('metric-sync-24h');
            const errors = document.getElementById('metric-errors');
            if (strmTotal) strmTotal.textContent = data.metrics.strm_total || 0;
            if (strmToday) strmToday.textContent = data.metrics.strm_today || 0;
            if (sync24h) sync24h.textContent = data.metrics.sync_24h || 0;
            if (errors) errors.textContent = data.metrics.error_count || 0;
        }
        
        // 更新115统计
        if (data.driver115) {
            const space = document.getElementById('stat-115-space');
            const accounts = document.getElementById('stat-115-accounts');
            const apiCalls = document.getElementById('stat-115-api-calls');
            if (space) space.textContent = data.driver115.space_used || '-';
            if (accounts) accounts.textContent = data.driver115.account_count || 0;
            if (apiCalls) apiCalls.textContent = data.driver115.api_calls_today || 0;
        }
        
        // 更新最近活动
        if (data.recentActivity) {
            renderRecentActivity(data.recentActivity);
        }
    } catch (err) {
        console.error('加载仪表板数据失败:', err);
    }
}

function renderLatestMovies(movies) {
    const container = document.getElementById('latest-movies');
    if (!container) return;
    
    if (movies.length === 0) {
        container.innerHTML = '<div class="empty-state" style="padding:20px;text-align:center;color:var(--text-muted);">暂无入库记录</div>';
        return;
    }
    
    container.innerHTML = movies.map(movie => {
        const posterUrl = movie.poster || '';
        const posterHtml = posterUrl
            ? `<img src="${escapeHtml(posterUrl)}" alt="${escapeHtml(movie.name)}" onerror="this.parentElement.innerHTML='<i class=\\'ri-film-line\\'></i>'">`
            : '<i class="ri-film-line"></i>';
        
        return `
            <div class="movie-item">
                <div class="movie-poster ${posterUrl ? '' : 'placeholder'}">
                    ${posterHtml}
                </div>
                <div class="movie-title" title="${escapeHtml(movie.name)}">${escapeHtml(movie.name)}</div>
            </div>
        `;
    }).join('');
}

function renderPlayingNow(items) {
    const container = document.getElementById('playing-now');
    if (!container) return;
    
    if (items.length === 0) {
        container.innerHTML = '<div style="text-align:center;color:var(--text-muted);font-size:13px;">暂无正在播放</div>';
        return;
    }
    
    container.innerHTML = items.map(item => `
        <div class="playing-now-item">
            <div class="playing-indicator"></div>
            <div class="playing-info">
                <div class="playing-title">${escapeHtml(item.title)}</div>
                <div class="playing-user">${escapeHtml(item.user || '未知用户')}</div>
            </div>
        </div>
    `).join('');
}

function renderSyncChart(data) {
    const container = document.getElementById('sync-chart');
    if (!container) return;
    
    const labels = data.labels || [];
    const values = data.values || [];
    
    if (labels.length === 0) {
        container.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:60px;">暂无同步数据</div>';
        return;
    }
    
    // 计算最大值
    const maxValue = Math.max(...values, 1);
    
    // 生成简单的柱状图
    let barsHtml = '<div class="chart-bars">';
    values.forEach((value, index) => {
        const height = (value / maxValue) * 100;
        const date = labels[index] ? labels[index].slice(5) : ''; // 只显示月-日
        barsHtml += `<div class="chart-bar" style="height:${height}%" data-value="${value}" title="${labels[index]}: ${value}"></div>`;
    });
    barsHtml += '</div>';
    
    // 生成日期标签（只显示部分）
    let labelsHtml = '<div class="chart-labels">';
    const step = Math.ceil(labels.length / 7); // 最多显示7个标签
    values.forEach((_, index) => {
        const showLabel = index % step === 0 || index === labels.length - 1;
        const date = labels[index] ? labels[index].slice(5) : '';
        labelsHtml += `<div class="chart-label">${showLabel ? date : ''}</div>`;
    });
    labelsHtml += '</div>';
    
    container.innerHTML = barsHtml + labelsHtml;
}

function renderRecentActivity(logs) {
    const container = document.getElementById('recent-activity');
    if (!container) return;
    
    if (!logs || logs.length === 0) {
        container.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:20px;">暂无活动记录</div>';
        return;
    }
    
    const typeIcons = {
        'INFO': 'ri-information-line',
        'ERROR': 'ri-error-warning-line',
        'WARN': 'ri-alert-line'
    };
    
    const typeColors = {
        'INFO': '#2196f3',
        'ERROR': '#f44336',
        'WARN': '#ff9800'
    };
    
    container.innerHTML = logs.map(log => {
        const icon = typeIcons[log.type] || 'ri-information-line';
        const color = typeColors[log.type] || '#2196f3';
        const time = new Date(log.created_at).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
        
        return `
            <div class="activity-item">
                <i class="${icon}" style="color:${color}"></i>
                <div class="activity-content">
                    <div class="activity-message">${escapeHtml(log.message)}</div>
                    <div class="activity-time">${time}</div>
                </div>
            </div>
        `;
    }).join('');
}

// ==================== 工作队列管理 ====================

let taskRefreshInterval = null;

async function loadTasks() {
    try {
        const resp = await fetch(`${API_BASE}/workqueue/stats`);
        const stats = await resp.json();
        
        document.getElementById('wq-running').textContent = stats.running || 0;
        document.getElementById('wq-pending').textContent = stats.pending || 0;
        document.getElementById('wq-completed').textContent = stats.completed || 0;
        document.getElementById('wq-failed').textContent = stats.failed || 0;
        document.getElementById('wq-workers').textContent = stats.workers || 0;
        document.getElementById('wq-deduplicated').textContent = stats.deduplicated || 0;
    } catch (err) {
        console.error('加载工作队列统计失败:', err);
    }
}

function refreshTasks() {
    loadTasks();
}

function startTaskRefresh() {
    if (taskRefreshInterval) return; // Prevent multiple intervals
    loadTasks();
    taskRefreshInterval = setInterval(loadTasks, 3000);
}

function stopTaskRefresh() {
    if (taskRefreshInterval) {
        clearInterval(taskRefreshInterval);
        taskRefreshInterval = null;
    }
}

// ==================== 页面初始化扩展 ====================

// 扩展页面导航，加载对应数据
const originalShowPage = showPage;
showPage = function(pageName) {
    originalShowPage(pageName);
    
    // 停止任务刷新（如果离开任务页面）
    if (pageName !== 'tasks') {
        stopTaskRefresh();
    }
    
    if (pageName === 'dashboard') {
        loadDashboardStats();
    } else if (pageName === 'logs') {
        loadLogs();
        loadLogStats();
        startLogStream();
        startLogAutoRefresh();
    } else if (pageName === 'history') {
        loadHistoryRecords();
    } else if (pageName === 'scraper') {
        loadMediaCategories();
        loadOrganizeRules();
    } else if (pageName === 'tasks') {
        startTaskRefresh();
    }
};



// 加载仪表板关键指标
async function loadDashboardMetrics() {
    try {
        const [strmStats, syncStats, logStats] = await Promise.all([
            fetch('/api/stats/strm').then(r => r.json()).catch(() => ({total: 0, today: 0})),
            fetch('/api/stats/sync').then(r => r.json()).catch(() => ({count_24h: 0})),
            fetch('/api/logs/stats').then(r => r.json()).catch(() => ({error_count: 0}))
        ]);
        
        document.getElementById('metric-strm-total').textContent = strmStats.total || 0;
        document.getElementById('metric-strm-today').textContent = strmStats.today || 0;
        document.getElementById('metric-sync-24h').textContent = syncStats.count_24h || 0;
        document.getElementById('metric-errors').textContent = logStats.error_count || 0;
    } catch (error) {
        console.error('加载关键指标失败:', error);
    }
}

// 加载115网盘统计
async function load115Stats() {
    try {
        const response = await fetch('/api/115/stats');
        const data = await response.json();
        
        document.getElementById('stat-115-space').textContent = data.space_used || '-';
        document.getElementById('stat-115-accounts').textContent = data.account_count || 0;
        document.getElementById('stat-115-api-calls').textContent = data.api_calls_today || 0;
    } catch (error) {
        console.error('加载115统计失败:', error);
    }
}

// 加载工作队列统计
async function loadWorkQueueStats() {
    try {
        const response = await fetch('/api/workqueue/stats');
        const data = await response.json();
        
        document.getElementById('stat-wq-running').textContent = data.running || 0;
        document.getElementById('stat-wq-pending').textContent = data.pending || 0;
        document.getElementById('stat-wq-completed').textContent = data.completed || 0;
    } catch (error) {
        console.error('加载工作队列统计失败:', error);
    }
}

// 加载最近活动
async function loadRecentActivity() {
    try {
        const response = await fetch('/api/activity/recent?limit=10');
        const activities = await response.json();
        
        const container = document.getElementById('recent-activity');
        if (!activities || activities.length === 0) {
            container.innerHTML = '<div class="empty-hint">暂无最近活动</div>';
            return;
        }
        
        container.innerHTML = activities.map(activity => `
            <div class="activity-item">
                <div class="activity-icon">
                    <i class="${getActivityIcon(activity.type)}"></i>
                </div>
                <div class="activity-content">
                    <div class="activity-title">${escapeHtml(activity.title)}</div>
                    <div class="activity-desc">${escapeHtml(activity.description)}</div>
                </div>
                <div class="activity-time">${formatTimeAgo(activity.created_at)}</div>
            </div>
        `).join('');
    } catch (error) {
        console.error('加载最近活动失败:', error);
        document.getElementById('recent-activity').innerHTML = '<div class="empty-hint">加载失败</div>';
    }
}

// 获取活动图标
function getActivityIcon(type) {
    const icons = {
        'sync': 'ri-refresh-line',
        'strm': 'ri-file-text-line',
        'error': 'ri-error-warning-line',
        'success': 'ri-check-line',
        'monitor': 'ri-eye-line',
        'task': 'ri-task-line'
    };
    return icons[type] || 'ri-information-line';
}

// 格式化时间为"多久前"
function formatTimeAgo(timestamp) {
    const now = new Date();
    const time = new Date(timestamp);
    const diff = Math.floor((now - time) / 1000);
    
    if (diff < 60) return '刚刚';
    if (diff < 3600) return Math.floor(diff / 60) + '分钟前';
    if (diff < 86400) return Math.floor(diff / 3600) + '小时前';
    if (diff < 604800) return Math.floor(diff / 86400) + '天前';
    return time.toLocaleDateString('zh-CN');
}
