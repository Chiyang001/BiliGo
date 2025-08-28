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
    initMobileOptimizations();
    initReplyTypeHandlers();
});

// 全局变量
let currentImageBrowserTarget = null; // 当前图片浏览器的目标
let currentBrowserPath = '';
let selectedImagePath = '';

// 初始化回复类型处理器
function initReplyTypeHandlers() {
    // 默认回复类型切换
    const defaultRadios = document.querySelectorAll('input[name="default-reply-type"]');
    defaultRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            toggleDefaultReplyContent(this.value);
        });
    });
    
    // 规则回复类型切换
    const ruleRadios = document.querySelectorAll('input[name="rule-reply-type"]');
    ruleRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            toggleRuleReplyContent(this.value);
        });
    });
    
    // 编辑回复类型切换
    const editRadios = document.querySelectorAll('input[name="edit-reply-type"]');
    editRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            toggleEditReplyContent(this.value);
        });
    });
}

// 切换默认回复内容显示
function toggleDefaultReplyContent(type) {
    const textContent = document.getElementById('default-text-content');
    const imageContent = document.getElementById('default-image-content');
    
    if (type === 'text') {
        textContent.style.display = 'block';
        imageContent.style.display = 'none';
    } else {
        textContent.style.display = 'none';
        imageContent.style.display = 'block';
    }
}

// 切换规则回复内容显示
function toggleRuleReplyContent(type) {
    const textContent = document.getElementById('rule-text-content');
    const imageContent = document.getElementById('rule-image-content');
    
    if (type === 'text') {
        textContent.style.display = 'block';
        imageContent.style.display = 'none';
    } else {
        textContent.style.display = 'none';
        imageContent.style.display = 'block';
    }
}

// 切换编辑回复内容显示
function toggleEditReplyContent(type) {
    const textContent = document.getElementById('edit-text-content');
    const imageContent = document.getElementById('edit-image-content');
    
    if (type === 'text') {
        textContent.style.display = 'block';
        imageContent.style.display = 'none';
    } else {
        textContent.style.display = 'none';
        imageContent.style.display = 'block';
    }
}

// 移动端优化初始化
function initMobileOptimizations() {
    // 防止iOS Safari缩放
    document.addEventListener('gesturestart', function (e) {
        e.preventDefault();
    });
    
    // 优化触摸滚动
    if ('ontouchstart' in window) {
        document.body.style.webkitOverflowScrolling = 'touch';
    }
    
    // 添加触摸反馈
    addTouchFeedback();
    
    // 优化输入框体验
    optimizeInputs();
    
    // 添加下拉刷新功能
    addPullToRefresh();
}

// 添加触摸反馈
function addTouchFeedback() {
    const buttons = document.querySelectorAll('button');
    buttons.forEach(button => {
        button.addEventListener('touchstart', function() {
            this.style.transform = 'scale(0.95)';
            this.style.opacity = '0.8';
        });
        
        button.addEventListener('touchend', function() {
            this.style.transform = 'scale(1)';
            this.style.opacity = '1';
        });
        
        button.addEventListener('touchcancel', function() {
            this.style.transform = 'scale(1)';
            this.style.opacity = '1';
        });
    });
}

// 优化输入框体验
function optimizeInputs() {
    const inputs = document.querySelectorAll('input, textarea');
    inputs.forEach(input => {
        // 防止iOS Safari在聚焦时缩放
        input.addEventListener('focus', function() {
            if (window.innerWidth < 768) {
                document.querySelector('meta[name=viewport]').setAttribute('content', 
                    'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no');
            }
        });
        
        input.addEventListener('blur', function() {
            if (window.innerWidth < 768) {
                document.querySelector('meta[name=viewport]').setAttribute('content', 
                    'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no');
            }
        });
    });
}

// 添加下拉刷新功能
function addPullToRefresh() {
    let startY = 0;
    let currentY = 0;
    let pullDistance = 0;
    let isPulling = false;
    let refreshThreshold = 80;
    
    document.addEventListener('touchstart', function(e) {
        if (window.scrollY === 0) {
            startY = e.touches[0].clientY;
            isPulling = true;
        }
    });
    
    document.addEventListener('touchmove', function(e) {
        if (!isPulling) return;
        
        currentY = e.touches[0].clientY;
        pullDistance = currentY - startY;
        
        if (pullDistance > 0 && window.scrollY === 0) {
            e.preventDefault();
            
            // 添加视觉反馈
            if (pullDistance > refreshThreshold) {
                document.body.style.transform = `translateY(${Math.min(pullDistance * 0.5, 50)}px)`;
                document.body.style.opacity = '0.8';
            }
        }
    });
    
    document.addEventListener('touchend', function(e) {
        if (!isPulling) return;
        
        isPulling = false;
        document.body.style.transform = '';
        document.body.style.opacity = '';
        
        if (pullDistance > refreshThreshold) {
            // 执行刷新
            refreshData();
        }
        
        startY = 0;
        currentY = 0;
        pullDistance = 0;
    });
}

// 刷新数据
function refreshData() {
    showToast('正在刷新数据...', 'info');
    loadRules();
    checkServerStatus();
    setTimeout(() => {
        showToast('刷新完成', 'success');
    }, 1000);
}

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
            
            // 设置回复类型
            const replyType = data.default_reply_type || 'text';
            document.querySelector(`input[name="default-reply-type"][value="${replyType}"]`).checked = true;
            toggleDefaultReplyContent(replyType);
            
            // 设置内容
            document.getElementById('default-reply-message').value = data.default_reply_message || '您好，我现在不在，稍后会回复您的消息。';
            
            if (data.default_reply_image) {
                document.getElementById('default-reply-image-path').value = data.default_reply_image;
                showImagePreview('default', data.default_reply_image);
            }
        }
    })
    .catch(error => {
        console.error('加载配置失败:', error);
    });
}

// 保存默认回复设置
function saveDefaultReply() {
    const enabled = document.getElementById('default-reply-enabled').checked;
    const replyType = document.querySelector('input[name="default-reply-type"]:checked').value;
    
    let configData = {
        default_reply_enabled: enabled,
        default_reply_type: replyType
    };
    
    if (replyType === 'text') {
        const message = document.getElementById('default-reply-message').value.trim();
        if (!message) {
            showToast('请填写默认回复内容', 'warning');
            return;
        }
        configData.default_reply_message = message;
        configData.default_reply_image = '';
    } else {
        const imagePath = document.getElementById('default-reply-image-path').value.trim();
        if (!imagePath) {
            showToast('请选择默认回复图片', 'warning');
            return;
        }
        configData.default_reply_image = imagePath;
        configData.default_reply_message = '';
    }
    
    fetch('/api/config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(configData)
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
    const replyType = document.querySelector('input[name="rule-reply-type"]:checked').value;
    
    if (!name || !keywords) {
        showToast('请填写规则标题和关键词', 'warning');
        return;
    }
    
    let rule = {
        id: Date.now(),
        name: name,
        keyword: keywords,  // keywords.json 使用 keyword 字段存储逗号分隔的关键词
        reply_type: replyType,
        enabled: true,
        use_regex: false,
        created_at: new Date().toISOString()
    };
    
    if (replyType === 'text') {
        const reply = document.getElementById('reply').value.trim();
        if (!reply) {
            showToast('请填写回复内容', 'warning');
            return;
        }
        rule.reply = reply;
        rule.reply_image = '';
    } else {
        const imagePath = document.getElementById('rule-reply-image-path').value.trim();
        if (!imagePath) {
            showToast('请选择回复图片', 'warning');
            return;
        }
        rule.reply = '[图片回复]';
        rule.reply_image = imagePath;
    }
    
    rules.push(rule);
    saveRules();
    updateRulesDisplay();
    
    // 清空输入框
    document.getElementById('rule-title').value = '';
    document.getElementById('keywords').value = '';
    document.getElementById('reply').value = '';
    document.getElementById('rule-reply-image-path').value = '';
    document.querySelector('input[name="rule-reply-type"][value="text"]').checked = true;
    toggleRuleReplyContent('text');
    hideImagePreview('rule');
    
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
        const enabledStatus = rule.enabled ? '<i class="bi bi-check-circle-fill" style="color: #2ed573;"></i>' : '<i class="bi bi-x-circle-fill" style="color: #ff4757;"></i>';
        
        // 根据回复类型显示不同的内容
        let replyContent = '';
        const replyType = rule.reply_type || 'text';
        
        if (replyType === 'image') {
            const imageName = rule.reply_image ? rule.reply_image.split(/[/\\]/).pop() : '未选择图片';
            replyContent = `<i class="bi bi-image-fill" style="color: #007bff;"></i> 图片回复: ${imageName}`;
        } else {
            const replyText = rule.reply && rule.reply.length > 100 ? rule.reply.substring(0, 100) + '...' : (rule.reply || '');
            replyContent = `<i class="bi bi-chat-text-fill" style="color: #28a745;"></i> 文字回复: ${replyText}`;
        }
        
        return `
        <div class="rule-item">
            <div class="rule-title">${enabledStatus} ${rule.name || '未命名规则'}</div>
            <div class="rule-keywords">关键词: ${rule.keyword || ''}</div>
            <div class="rule-reply" title="${rule.reply || rule.reply_image || ''}">${replyContent}</div>
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
    
    // 设置回复类型
    const replyType = rule.reply_type || 'text';
    document.querySelector(`input[name="edit-reply-type"][value="${replyType}"]`).checked = true;
    toggleEditReplyContent(replyType);
    
    if (replyType === 'text') {
        document.getElementById('edit-reply').value = rule.reply || '';
    } else {
        document.getElementById('edit-reply-image-path').value = rule.reply_image || '';
        if (rule.reply_image) {
            showImagePreview('edit', rule.reply_image);
        }
    }
    
    // 显示模态框
    const modal = document.getElementById('edit-modal');
    modal.style.display = 'block';
    
    // 移动端优化：防止背景滚动
    if (window.innerWidth <= 768) {
        document.body.style.overflow = 'hidden';
        document.body.style.position = 'fixed';
        document.body.style.width = '100%';
        
        // 聚焦到第一个输入框
        setTimeout(() => {
            document.getElementById('edit-rule-title').focus();
        }, 300);
    }
}

// 保存编辑的规则
function saveEditRule() {
    const name = document.getElementById('edit-rule-title').value.trim();
    const keywords = document.getElementById('edit-keywords').value.trim();
    const replyType = document.querySelector('input[name="edit-reply-type"]:checked').value;
    
    if (!name || !keywords) {
        showToast('请填写规则标题和关键词', 'warning');
        return;
    }
    
    let updateData = {
        name: name,
        keyword: keywords,
        reply_type: replyType
    };
    
    if (replyType === 'text') {
        const reply = document.getElementById('edit-reply').value.trim();
        if (!reply) {
            showToast('请填写回复内容', 'warning');
            return;
        }
        updateData.reply = reply;
        updateData.reply_image = '';
    } else {
        const imagePath = document.getElementById('edit-reply-image-path').value.trim();
        if (!imagePath) {
            showToast('请选择回复图片', 'warning');
            return;
        }
        updateData.reply = '[图片回复]';
        updateData.reply_image = imagePath;
    }
    
    // 更新规则
    const ruleIndex = rules.findIndex(r => r.id === editingRuleId);
    if (ruleIndex !== -1) {
        rules[ruleIndex] = {
            ...rules[ruleIndex],
            ...updateData
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
    
    // 移动端优化：恢复背景滚动
    if (window.innerWidth <= 768) {
        document.body.style.overflow = '';
        document.body.style.position = '';
        document.body.style.width = '';
    }
    
    // 清空表单
    document.getElementById('edit-rule-title').value = '';
    document.getElementById('edit-keywords').value = '';
    document.getElementById('edit-reply').value = '';
    document.getElementById('edit-reply-image-path').value = '';
    document.querySelector('input[name="edit-reply-type"][value="text"]').checked = true;
    toggleEditReplyContent('text');
    hideImagePreview('edit');
}

// 打开图片浏览器
function openImageBrowser(target) {
    currentImageBrowserTarget = target;
    selectedImagePath = '';
    
    // 显示模态框
    const modal = document.getElementById('image-browser-modal');
    modal.style.display = 'block';
    
    // 获取主目录并开始浏览
    fetch('/api/get-home-directory')
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // 优先显示图片目录，如果没有则显示主目录
            const startPath = data.common_directories.length > 0 ? 
                data.common_directories[0].path : data.home_directory;
            browsePath(startPath);
        } else {
            showToast('获取主目录失败: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showToast('获取主目录失败: ' + error, 'error');
    });
}

// 浏览指定路径
function browsePath(path) {
    currentBrowserPath = path;
    document.getElementById('current-path-text').textContent = path;
    
    const fileList = document.getElementById('file-list');
    fileList.innerHTML = '<div class="loading"><i class="bi bi-arrow-clockwise spin"></i> 加载中...</div>';
    
    fetch('/api/browse-images', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            folder_path: path
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            displayFileList(data.items);
        } else {
            fileList.innerHTML = `<div class="loading" style="color: var(--danger-color);"><i class="bi bi-exclamation-circle"></i> ${data.error}</div>`;
        }
    })
    .catch(error => {
        fileList.innerHTML = `<div class="loading" style="color: var(--danger-color);"><i class="bi bi-exclamation-circle"></i> 加载失败: ${error}</div>`;
    });
}

// 显示文件列表
function displayFileList(items) {
    const fileList = document.getElementById('file-list');
    
    if (items.length === 0) {
        fileList.innerHTML = '<div class="loading">此文件夹为空</div>';
        return;
    }
    
    fileList.innerHTML = items.map(item => {
        let icon, details = '';
        
        if (item.type === 'directory') {
            icon = item.name === '..' ? 'bi-arrow-up' : 'bi-folder-fill';
        } else {
            icon = 'bi-file-earmark-image';
            details = `${item.extension} • ${item.size}`;
        }
        
        // 对路径进行编码，避免特殊字符问题
        const encodedPath = encodeURIComponent(item.path);
        // 对显示的文件名进行HTML转义
        const escapedName = escapeHtml(item.name);
        
        return `
            <div class="file-item ${item.type}" onclick="selectFileItem('${encodedPath}', '${item.type}', this)">
                <i class="bi ${icon} file-icon"></i>
                <div class="file-info">
                    <div class="file-name">${escapedName}</div>
                    ${details ? `<div class="file-details">${details}</div>` : ''}
                </div>
            </div>
        `;
    }).join('');
}

// HTML转义函数
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 选择文件项
function selectFileItem(path, type, element) {
    // 解码路径，处理转义字符
    const decodedPath = decodeURIComponent(path);
    
    if (type === 'directory') {
        // 如果是目录，进入该目录
        browsePath(decodedPath);
    } else {
        // 如果是图片，选择该图片
        selectedImagePath = decodedPath;
        
        // 更新选中状态
        document.querySelectorAll('.file-item').forEach(item => {
            item.classList.remove('selected');
        });
        element.classList.add('selected');
        
        // 确认选择
        confirmImageSelection();
    }
}

// 确认图片选择
function confirmImageSelection() {
    if (!selectedImagePath) {
        showToast('请选择一张图片', 'warning');
        return;
    }
    
    // 根据目标设置图片路径
    if (currentImageBrowserTarget === 'default') {
        document.getElementById('default-reply-image-path').value = selectedImagePath;
        showImagePreview('default', selectedImagePath);
    } else if (currentImageBrowserTarget === 'rule') {
        document.getElementById('rule-reply-image-path').value = selectedImagePath;
        showImagePreview('rule', selectedImagePath);
    } else if (currentImageBrowserTarget === 'edit') {
        document.getElementById('edit-reply-image-path').value = selectedImagePath;
        showImagePreview('edit', selectedImagePath);
    }
    
    closeImageBrowser();
    showToast('图片选择成功', 'success');
}

// 关闭图片浏览器
function closeImageBrowser() {
    document.getElementById('image-browser-modal').style.display = 'none';
    currentImageBrowserTarget = null;
    selectedImagePath = '';
}

// 跳转到主目录
function goToHomeDirectory() {
    fetch('/api/get-home-directory')
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            browsePath(data.home_directory);
        } else {
            showToast('获取主目录失败: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showToast('获取主目录失败: ' + error, 'error');
    });
}

// 显示图片预览
function showImagePreview(target, imagePath) {
    const previewId = target + '-image-preview';
    const preview = document.getElementById(previewId);
    
    if (!preview) return;
    
    const fileName = imagePath.split(/[/\\]/).pop();
    
    // 通过后端API获取图片预览
    fetch('/api/preview-image', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            image_path: imagePath
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            preview.innerHTML = `
                <img src="data:${data.mime_type};base64,${data.image_data}" alt="预览图片" style="max-width: 200px; max-height: 150px; border-radius: 8px;">
                <div class="image-info">
                    <i class="bi bi-file-earmark-image"></i> ${fileName}
                    <br><small>${data.file_size}</small>
                </div>
            `;
        } else {
            preview.innerHTML = `
                <div style="color: var(--text-light); text-align: center; padding: 20px;">
                    <i class="bi bi-image" style="font-size: 24px; margin-bottom: 8px;"></i>
                    <div>无法预览图片</div>
                    <small>${data.error || '未知错误'}</small>
                </div>
                <div class="image-info">
                    <i class="bi bi-file-earmark-image"></i> ${fileName}
                </div>
            `;
        }
        preview.style.display = 'block';
    })
    .catch(error => {
        preview.innerHTML = `
            <div style="color: var(--text-light); text-align: center; padding: 20px;">
                <i class="bi bi-image" style="font-size: 24px; margin-bottom: 8px;"></i>
                <div>无法预览图片</div>
                <small>网络错误</small>
            </div>
            <div class="image-info">
                <i class="bi bi-file-earmark-image"></i> ${fileName}
            </div>
        `;
        preview.style.display = 'block';
    });
}

// 隐藏图片预览
function hideImagePreview(target) {
    const previewId = target + '-image-preview';
    const preview = document.getElementById(previewId);
    
    if (preview) {
        preview.style.display = 'none';
        preview.innerHTML = '';
    }
}

// 点击模态框外部关闭
window.onclick = function(event) {
    const modal = document.getElementById('edit-modal');
    if (event.target === modal) {
        closeEditModal();
    }
}

// 键盘事件处理
document.addEventListener('keydown', function(event) {
    // ESC键关闭模态框
    if (event.key === 'Escape') {
        const modal = document.getElementById('edit-modal');
        if (modal.style.display === 'block') {
            closeEditModal();
        }
    }
    
    // Enter键提交表单（在非textarea元素中）
    if (event.key === 'Enter' && event.target.tagName !== 'TEXTAREA') {
        if (event.target.closest('#edit-modal')) {
            event.preventDefault();
            saveEditRule();
        } else if (event.target.closest('.keyword-panel')) {
            event.preventDefault();
            addRule();
        } else if (event.target.closest('.config-panel')) {
            event.preventDefault();
            saveConfig();
        } else if (event.target.closest('.default-reply-panel')) {
            event.preventDefault();
            saveDefaultReply();
        }
    }
});

// 移动端虚拟键盘处理
function handleVirtualKeyboard() {
    let initialViewportHeight = window.innerHeight;
    
    window.addEventListener('resize', function() {
        const currentHeight = window.innerHeight;
        const heightDifference = initialViewportHeight - currentHeight;
        
        // 如果高度减少超过150px，认为是虚拟键盘弹出
        if (heightDifference > 150) {
            document.body.classList.add('keyboard-open');
            
            // 调整模态框位置
            const modal = document.querySelector('.modal-content');
            if (modal && document.getElementById('edit-modal').style.display === 'block') {
                modal.style.position = 'absolute';
                modal.style.top = '10px';
                modal.style.marginTop = '0';
            }
        } else {
            document.body.classList.remove('keyboard-open');
            
            // 恢复模态框位置
            const modal = document.querySelector('.modal-content');
            if (modal) {
                modal.style.position = '';
                modal.style.top = '';
                modal.style.marginTop = '';
            }
        }
    });
}

// 添加长按删除功能
function addLongPressDelete() {
    let pressTimer;
    
    document.addEventListener('touchstart', function(e) {
        if (e.target.closest('.delete-btn')) {
            pressTimer = setTimeout(function() {
                // 长按删除确认
                const ruleItem = e.target.closest('.rule-item');
                const ruleTitle = ruleItem.querySelector('.rule-title').textContent;
                
                if (confirm(`确定要删除规则"${ruleTitle.replace(/[✓✗]\s*/, '')}"吗？`)) {
                    const deleteBtn = e.target.closest('.delete-btn');
                    const ruleId = deleteBtn.getAttribute('onclick').match(/\d+/)[0];
                    deleteRule(parseInt(ruleId));
                }
            }, 1000); // 长按1秒
        }
    });
    
    document.addEventListener('touchend', function(e) {
        clearTimeout(pressTimer);
    });
    
    document.addEventListener('touchmove', function(e) {
        clearTimeout(pressTimer);
    });
}

// 初始化移动端功能
if (window.innerWidth <= 768) {
    handleVirtualKeyboard();
    addLongPressDelete();
}
