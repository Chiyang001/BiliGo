let rules = [];
let isMonitoring = false;
let currentPage = 1;
const rulesPerPage = 10;
let editingRuleId = null;

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', function() {
    loadConfig();
    loadRules(); // loadRules内部会调用updateRulesDisplay()
    checkServerStatus();
});

// 显示提示消息
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toast-container');
    
    // 创建提示元素
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    // 根据类型设置图标
    let icon = 'info-circle-fill';
    if (type === 'success') icon = 'check-circle-fill';
    if (type === 'error') icon = 'exclamation-circle-fill';
    if (type === 'warning') icon = 'exclamation-triangle-fill';
    
    toast.innerHTML = `
        <i class="bi bi-${icon} toast-icon"></i>
        <div class="toast-message">${message}</div>
    `;
    
    // 添加到容器
    toastContainer.appendChild(toast);
    
    // 3秒后自动移除
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

// 保存配置
function saveConfig() {
    const sessdata = document.getElementById('sessdata').value;
    const bili_jct = document.getElementById('bili_jct').value;
    
    if (!sessdata || !bili_jct) {
        showToast('请填写完整的登录配置', 'error');
        return;
    }
    
    fetch('/api/config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            sessdata: sessdata,
            bili_jct: bili_jct
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('配置保存成功', 'success');
            addLog('配置保存成功', 'success');
        } else {
            showToast('配置保存失败: ' + data.error, 'error');
            addLog('配置保存失败: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showToast('配置保存失败: ' + error, 'error');
        addLog('配置保存失败: ' + error, 'error');
    });
}

// 加载配置
function loadConfig() {
    fetch('/api/config')
    .then(response => response.json())
    .then(data => {
        if (data.sessdata) {
            document.getElementById('sessdata').value = data.sessdata;
        }
        if (data.bili_jct) {
            document.getElementById('bili_jct').value = data.bili_jct;
        }
        
        // 加载默认回复设置
        if (document.getElementById('default-reply-enabled')) {
            document.getElementById('default-reply-enabled').checked = data.default_reply_enabled || false;
            document.getElementById('default-reply-message').value = data.default_reply_message || '您好，我现在不在，稍后会回复您的消息。';
        }
    })
    .catch(error => {
        console.error('加载配置失败:', error);
    });
}

// 保存默认回复设置
function saveDefaultReply() {
    const enabled = document.getElementById('default-reply-enabled').checked;
    const message = document.getElementById('default-reply-message').value.trim();
    
    if (!message) {
        showToast('请填写默认回复内容', 'warning');
        return;
    }
    
    fetch('/api/config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            default_reply_enabled: enabled,
            default_reply_message: message
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('默认回复设置已保存', 'success');
            addLog('默认回复设置已更新', 'success');
        } else {
            showToast('保存默认回复设置失败', 'error');
            addLog('保存默认回复设置失败', 'error');
        }
    })
    .catch(error => {
        showToast('保存默认回复设置失败: ' + error, 'error');
        addLog('保存默认回复设置失败: ' + error, 'error');
    });
}

// 添加回复规则
function addRule() {
    const name = document.getElementById('rule-title').value.trim();
    const keywords = document.getElementById('keywords').value.trim();
    const reply = document.getElementById('reply').value.trim();
    
    if (!name || !keywords || !reply) {
        showToast('请填写完整的规则信息（标题、关键词、回复内容）', 'warning');
        return;
    }
    
    const rule = {
        id: Date.now(),
        name: name,
        keyword: keywords,  // keywords.json 使用 keyword 字段存储逗号分隔的关键词
        reply: reply,
        enabled: true,
        use_regex: false,
        created_at: new Date().toISOString()
    };
    
    rules.push(rule);
    saveRules();
    updateRulesDisplay();
    
    // 清空输入框
    document.getElementById('rule-title').value = '';
    document.getElementById('keywords').value = '';
    document.getElementById('reply').value = '';
    
    showToast(`规则"${name}"添加成功`, 'success');
    addLog(`添加规则成功: ${name}`, 'success');
}

// 删除规则
function deleteRule(id) {
    const rule = rules.find(r => r.id === id);
    if (!rule) return;
    
    const ruleName = rule.name;
    rules = rules.filter(rule => rule.id !== id);
    saveRules();
    updateRulesDisplay();
    
    showToast(`规则"${ruleName}"已删除`, 'success');
    addLog('删除规则成功', 'success');
}

// 保存规则到本地存储
function saveRules() {
    localStorage.setItem('bilibili_reply_rules', JSON.stringify(rules));
    
    // 同时发送到服务器
    fetch('/api/rules', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({rules: rules})
    })
    .catch(error => {
        console.error('同步规则到服务器失败:', error);
        showToast('同步规则到服务器失败', 'error');
    });
}

// 从本地存储和服务器加载规则
function loadRules() {
    // 首先尝试从服务器加载
    fetch('/api/rules')
    .then(response => response.json())
    .then(data => {
        if (data.rules && Array.isArray(data.rules)) {
            rules = data.rules;
            // 同步到本地存储
            localStorage.setItem('bilibili_reply_rules', JSON.stringify(rules));
            addLog(`从服务器加载了 ${rules.length} 条规则`, 'success');
        } else {
            // 如果服务器没有规则，尝试从本地存储加载
            const saved = localStorage.getItem('bilibili_reply_rules');
            if (saved) {
                rules = JSON.parse(saved);
                addLog(`从本地存储加载了 ${rules.length} 条规则`, 'info');
            }
        }
        updateRulesDisplay();
    })
    .catch(error => {
        // 服务器加载失败，尝试从本地存储加载
        console.error('从服务器加载规则失败:', error);
        const saved = localStorage.getItem('bilibili_reply_rules');
        if (saved) {
            try {
                rules = JSON.parse(saved);
                addLog(`从本地存储加载了 ${rules.length} 条规则`, 'info');
            } catch (e) {
                console.error('本地存储规则解析失败:', e);
                rules = [];
            }
        }
        updateRulesDisplay();
    });
}

// 更新规则显示
function updateRulesDisplay() {
    const container = document.getElementById('rules-list');
    
    if (rules.length === 0) {
        container.innerHTML = '<p style="color: #999; text-align: center; padding: 20px;">暂无回复规则</p>';
        updatePaginationControls();
        return;
    }
    
    // 按创建时间倒序排列，最新的在前面
    const sortedRules = [...rules].sort((a, b) => {
        const timeA = a.created_at ? new Date(a.created_at).getTime() : a.id || 0;
        const timeB = b.created_at ? new Date(b.created_at).getTime() : b.id || 0;
        return timeB - timeA; // 倒序排列
    });
    
    // 计算分页
    const totalPages = Math.ceil(sortedRules.length / rulesPerPage);
    const startIndex = (currentPage - 1) * rulesPerPage;
    const endIndex = startIndex + rulesPerPage;
    const currentRules = sortedRules.slice(startIndex, endIndex);
    
    container.innerHTML = currentRules.map(rule => {
        const replyText = rule.reply.length > 100 ? rule.reply.substring(0, 100) + '...' : rule.reply;
        const enabledStatus = rule.enabled ? '<i class="bi bi-check-circle-fill" style="color: #2ed573;"></i>' : '<i class="bi bi-x-circle-fill" style="color: #ff4757;"></i>';
        return `
        <div class="rule-item">
            <div class="rule-title">${enabledStatus} ${rule.name || '未命名规则'}</div>
            <div class="rule-keywords">关键词: ${rule.keyword || ''}</div>
            <div class="rule-reply" title="${rule.reply}">回复: ${replyText}</div>
            <div class="rule-actions">
                <button class="edit-btn" onclick="editRule(${rule.id})"><i class="bi bi-pencil-fill"></i> 编辑</button>
                <button class="delete-btn" onclick="deleteRule(${rule.id})"><i class="bi bi-trash-fill"></i> 删除</button>
                <button class="toggle-btn" onclick="toggleRule(${rule.id})">
                    <i class="bi bi-${rule.enabled ? 'toggle-on' : 'toggle-off'}"></i> 
                    ${rule.enabled ? '禁用' : '启用'}
                </button>
            </div>
        </div>
        `;
    }).join('');
    
    updatePaginationControls();
}

// 更新分页控件
function updatePaginationControls() {
    const totalPages = Math.ceil(rules.length / rulesPerPage);
    const pageInfo = `第 ${currentPage} 页，共 ${totalPages} 页`;
    
    // 更新页面信息
    document.getElementById('page-info').textContent = pageInfo;
    document.getElementById('page-info-bottom').textContent = pageInfo;
    
    // 更新按钮状态
    const prevButtons = [document.getElementById('prev-page'), document.getElementById('prev-page-bottom')];
    const nextButtons = [document.getElementById('next-page'), document.getElementById('next-page-bottom')];
    
    prevButtons.forEach(btn => {
        btn.disabled = currentPage <= 1;
    });
    
    nextButtons.forEach(btn => {
        btn.disabled = currentPage >= totalPages;
    });
}

// 切换页面
function changePage(direction) {
    const totalPages = Math.ceil(rules.length / rulesPerPage);
    
    if (direction === -1 && currentPage > 1) {
        currentPage--;
    } else if (direction === 1 && currentPage < totalPages) {
        currentPage++;
    }
    
    updateRulesDisplay();
}

// 开始监控
function startMonitoring() {
    fetch('/api/start', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            isMonitoring = true;
            updateButtonStates();
            updateStatus('监控中...');
            showToast('开始监控私信', 'success');
            addLog('开始监控私信', 'success');
            startLogPolling();
        } else {
            showToast('启动失败: ' + data.error, 'error');
            addLog('启动失败: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showToast('启动失败: ' + error, 'error');
        addLog('启动失败: ' + error, 'error');
    });
}

// 停止监控
function stopMonitoring() {
    fetch('/api/stop', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            isMonitoring = false;
            updateButtonStates();
            updateStatus('已停止');
            showToast('停止监控私信', 'warning');
            addLog('停止监控私信', 'warning');
        } else {
            showToast('停止失败: ' + data.error, 'error');
            addLog('停止失败: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showToast('停止失败: ' + error, 'error');
        addLog('停止失败: ' + error, 'error');
    });
}

// 更新按钮状态
function updateButtonStates() {
    document.getElementById('start-btn').disabled = isMonitoring;
    document.getElementById('stop-btn').disabled = !isMonitoring;
    
    // 更新状态指示器样式
    const statusIndicator = document.querySelector('.status-indicator');
    if (isMonitoring) {
        statusIndicator.classList.add('active');
        document.querySelector('.status-icon').style.color = '#2ed573';
    } else {
        statusIndicator.classList.remove('active');
        document.querySelector('.status-icon').style.color = '#ccc';
    }
}

// 更新状态显示
function updateStatus(status) {
    document.getElementById('status').textContent = status;
}

// 添加日志
function addLog(message, type = 'info') {
    const log = document.getElementById('log');
    const timestamp = new Date().toLocaleTimeString();
    const entry = document.createElement('div');
    entry.className = `log-entry log-${type}`;
    entry.textContent = `[${timestamp}] ${message}`;
    log.appendChild(entry);
    
    // 自动滚动到底部
    const container = document.getElementById('log-container');
    container.scrollTop = container.scrollHeight;
    
    // 限制日志条数
    const entries = log.children;
    if (entries.length > 100) {
        log.removeChild(entries[0]);
    }
}

// 检查服务器状态
function checkServerStatus() {
    fetch('/api/status')
    .then(response => response.json())
    .then(data => {
        isMonitoring = data.monitoring;
        updateButtonStates();
        updateStatus(data.monitoring ? '监控中...' : '未启动');
        if (data.monitoring) {
            startLogPolling();
        }
    })
    .catch(error => {
        updateStatus('服务器连接失败');
        showToast('无法连接到服务器', 'error');
        addLog('无法连接到服务器', 'error');
    });
}

// 轮询日志
function startLogPolling() {
    if (!isMonitoring) return;
    
    fetch('/api/logs')
    .then(response => response.json())
    .then(data => {
        if (data.logs && data.logs.length > 0) {
            data.logs.forEach(logEntry => {
                addLog(logEntry.message, logEntry.type);
            });
        }
    })
    .catch(error => {
        console.error('获取日志失败:', error);
    });
    
    // 每3秒轮询一次
    setTimeout(startLogPolling, 3000);
}

// 编辑规则
function editRule(id) {
    const rule = rules.find(r => r.id === id);
    if (!rule) return;
    
    editingRuleId = id;
    
    // 填充编辑表单
    document.getElementById('edit-rule-title').value = rule.name || '';
    document.getElementById('edit-keywords').value = rule.keyword || '';
    document.getElementById('edit-reply').value = rule.reply || '';
    
    // 显示模态框
    document.getElementById('edit-modal').style.display = 'block';
}

// 保存编辑的规则
function saveEditRule() {
    const name = document.getElementById('edit-rule-title').value.trim();
    const keywords = document.getElementById('edit-keywords').value.trim();
    const reply = document.getElementById('edit-reply').value.trim();
    
    if (!name || !keywords || !reply) {
        showToast('请填写完整的规则信息（标题、关键词、回复内容）', 'warning');
        return;
    }
    
    // 更新规则
    const ruleIndex = rules.findIndex(r => r.id === editingRuleId);
    if (ruleIndex !== -1) {
        rules[ruleIndex] = {
            ...rules[ruleIndex],
            name: name,
            keyword: keywords,
            reply: reply
        };
        
        saveRules();
        updateRulesDisplay();
        closeEditModal();
        
        showToast(`规则"${name}"已更新`, 'success');
        addLog(`规则编辑成功: ${name}`, 'success');
    }
}

// 切换规则启用状态
function toggleRule(id) {
    const ruleIndex = rules.findIndex(r => r.id === id);
    if (ruleIndex !== -1) {
        rules[ruleIndex].enabled = !rules[ruleIndex].enabled;
        saveRules();
        updateRulesDisplay();
        
        const status = rules[ruleIndex].enabled ? '启用' : '禁用';
        showToast(`规则"${rules[ruleIndex].name}"已${status}`, 'info');
        addLog(`规则${status}成功: ${rules[ruleIndex].name}`, 'info');
    }
}

// 关闭编辑模态框
function closeEditModal() {
    document.getElementById('edit-modal').style.display = 'none';
    editingRuleId = null;
    
    // 清空表单
    document.getElementById('edit-rule-title').value = '';
    document.getElementById('edit-keywords').value = '';
    document.getElementById('edit-reply').value = '';
}

// 点击模态框外部关闭
window.onclick = function(event) {
    const modal = document.getElementById('edit-modal');
    if (event.target === modal) {
        closeEditModal();
    }
}