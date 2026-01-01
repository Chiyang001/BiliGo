// 评论回复系统 JavaScript

let commentRules = [];
let isCommentMonitoring = false;
let currentCommentPage = 1;
const commentRulesPerPage = 10;
let editingCommentRuleId = null;

// 全局变量
let currentImageBrowserTarget = null;
let currentBrowserPath = '';
let selectedImagePath = '';

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', function() {
    loadCommentConfig();
    loadCommentRules();
    checkCommentServerStatus();
    initCommentMobileOptimizations();
    initCommentReplyTypeHandlers();
    loadCommentTimingConfig();
});

// 初始化回复类型处理器
function initCommentReplyTypeHandlers() {
    // 默认评论回复类型切换
    const defaultCommentRadios = document.querySelectorAll('input[name="default-comment-reply-type"]');
    defaultCommentRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            toggleDefaultCommentReplyContent(this.value);
        });
    });
    
    // 规则评论回复类型切换
    const ruleCommentRadios = document.querySelectorAll('input[name="comment-rule-reply-type"]');
    ruleCommentRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            toggleCommentRuleReplyContent(this.value);
        });
    });
    
    // 编辑评论回复类型切换
    const editCommentRadios = document.querySelectorAll('input[name="edit-comment-reply-type"]');
    editCommentRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            toggleEditCommentReplyContent(this.value);
        });
    });
}

// 切换默认评论回复内容显示
function toggleDefaultCommentReplyContent(type) {
    const textContent = document.getElementById('default-comment-text-content');
    const imageContent = document.getElementById('default-comment-image-content');
    
    if (type === 'text') {
        textContent.style.display = 'block';
        imageContent.style.display = 'none';
    } else {
        textContent.style.display = 'none';
        imageContent.style.display = 'block';
    }
}

// 切换评论规则回复内容显示
function toggleCommentRuleReplyContent(type) {
    const textContent = document.getElementById('comment-rule-text-content');
    const imageContent = document.getElementById('comment-rule-image-content');
    
    if (type === 'text') {
        textContent.style.display = 'block';
        imageContent.style.display = 'none';
    } else {
        textContent.style.display = 'none';
        imageContent.style.display = 'block';
    }
}

// 切换编辑评论回复内容显示
function toggleEditCommentReplyContent(type) {
    const textContent = document.getElementById('edit-comment-text-content');
    const imageContent = document.getElementById('edit-comment-image-content');
    
    if (type === 'text') {
        textContent.style.display = 'block';
        imageContent.style.display = 'none';
    } else {
        textContent.style.display = 'none';
        imageContent.style.display = 'block';
    }
}

// 移动端优化初始化
function initCommentMobileOptimizations() {
    // 防止iOS Safari缩放
    document.addEventListener('gesturestart', function (e) {
        e.preventDefault();
    });
    
    // 优化触摸滚动
    if ('ontouchstart' in window) {
        document.body.style.webkitOverflowScrolling = 'touch';
    }
    
    // 添加触摸反馈
    addCommentTouchFeedback();
    
    // 优化输入框体验
    optimizeCommentInputs();
}

// 添加触摸反馈
function addCommentTouchFeedback() {
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
function optimizeCommentInputs() {
    const inputs = document.querySelectorAll('input, textarea');
    inputs.forEach(input => {
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

// 显示提示消息
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toast-container');
    
    // 安全检查：如果toast容器不存在，直接返回
    if (!toastContainer) {
        console.log(`Toast: [${type.toUpperCase()}] ${message}`);
        return;
    }
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let icon = 'ℹ️';
    if (type === 'success') icon = '✅';
    if (type === 'error') icon = '❌';
    if (type === 'warning') icon = '⚠️';
    
    toast.innerHTML = `
        <span class="toast-icon">${icon}</span>
        <div class="toast-message">${message}</div>
    `;
    
    toastContainer.appendChild(toast);
    
    setTimeout(() => {
        if (toast && toast.parentNode) {
            toast.remove();
        }
    }, 4000);
}

// 切换到私信模式
function switchToMessageMode() {
    window.location.href = 'index.html';
}

// 跳转到日志页面
function goToLogsPage() {
    window.location.href = 'logs.html';
}

// 加载评论回复配置
function loadCommentConfig() {
    fetch('/api/comment-config')
    .then(response => response.json())
    .then(data => {
        // 加载登录配置
        if (data.sessdata) {
            document.getElementById('sessdata').value = data.sessdata;
        }
        if (data.bili_jct) {
            document.getElementById('bili_jct').value = data.bili_jct;
        }
        
        // 加载默认评论回复设置
        if (document.getElementById('default-comment-reply-enabled')) {
            document.getElementById('default-comment-reply-enabled').checked = data.default_comment_reply_enabled || false;
            
            const replyType = data.default_comment_reply_type || 'text';
            document.querySelector(`input[name="default-comment-reply-type"][value="${replyType}"]`).checked = true;
            toggleDefaultCommentReplyContent(replyType);
            
            document.getElementById('default-comment-reply-message').value = data.default_comment_reply_message || '感谢您的评论！';
            
            if (data.default_comment_reply_image) {
                document.getElementById('default-comment-reply-image-path').value = data.default_comment_reply_image;
                showImagePreview('default-comment', data.default_comment_reply_image);
            }
        }
        
        // 加载监控配置
        if (document.getElementById('comment-check-interval')) {
            document.getElementById('comment-check-interval').value = data.comment_check_interval || 30;
        }
        if (document.getElementById('comment-send-delay')) {
            document.getElementById('comment-send-delay').value = data.comment_send_delay || 2.0;
        }
        if (document.getElementById('only-reply-new-comments')) {
            document.getElementById('only-reply-new-comments').checked = data.only_reply_new_comments !== false;
        }
    })
    .catch(error => {
        console.error('加载评论回复配置失败:', error);
    });
}

// 保存评论登录配置
function saveCommentLoginConfig() {
    const sessdata = document.getElementById('sessdata').value;
    const bili_jct = document.getElementById('bili_jct').value;
    
    if (!sessdata || !bili_jct) {
        showToast('请填写完整的登录配置', 'error');
        return;
    }
    
    fetch('/api/comment-config', {
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
            showToast('登录配置保存成功', 'success');
            addCommentLog('登录配置保存成功', 'success');
        } else {
            showToast('保存失败: ' + data.error, 'error');
            addCommentLog('保存登录配置失败: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showToast('保存失败: ' + error, 'error');
        addCommentLog('保存登录配置失败: ' + error, 'error');
    });
}

// 保存默认评论回复设置
function saveDefaultCommentReply() {
    const enabled = document.getElementById('default-comment-reply-enabled').checked;
    const replyType = document.querySelector('input[name="default-comment-reply-type"]:checked').value;
    
    let configData = {
        default_comment_reply_enabled: enabled,
        default_comment_reply_type: replyType
    };
    
    if (replyType === 'text') {
        const message = document.getElementById('default-comment-reply-message').value.trim();
        if (!message) {
            showToast('请填写默认评论回复内容', 'warning');
            return;
        }
        configData.default_comment_reply_message = message;
        configData.default_comment_reply_image = '';
    } else {
        const imagePath = document.getElementById('default-comment-reply-image-path').value.trim();
        if (!imagePath) {
            showToast('请选择默认评论回复图片', 'warning');
            return;
        }
        configData.default_comment_reply_image = imagePath;
        configData.default_comment_reply_message = '';
    }
    
    fetch('/api/comment-config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(configData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('默认评论回复设置已保存', 'success');
            addCommentLog('默认评论回复设置已更新', 'success');
        } else {
            showToast('保存默认评论回复设置失败', 'error');
            addCommentLog('保存默认评论回复设置失败', 'error');
        }
    })
    .catch(error => {
        showToast('保存默认评论回复设置失败: ' + error, 'error');
        addCommentLog('保存默认评论回复设置失败: ' + error, 'error');
    });
}

// 添加评论回复规则
function addCommentRule() {
    const name = document.getElementById('comment-rule-title').value.trim();
    const keywords = document.getElementById('comment-keywords').value.trim();
    const replyType = document.querySelector('input[name="comment-rule-reply-type"]:checked').value;
    
    if (!name || !keywords) {
        showToast('请填写规则标题和关键词', 'warning');
        return;
    }
    
    let rule = {
        id: Date.now(),
        name: name,
        keyword: keywords,
        reply_type: replyType,
        enabled: true,
        created_at: new Date().toISOString()
    };
    
    if (replyType === 'text') {
        const reply = document.getElementById('comment-reply').value.trim();
        if (!reply) {
            showToast('请填写回复内容', 'warning');
            return;
        }
        rule.reply = reply;
        rule.reply_image = '';
    } else {
        const imagePath = document.getElementById('comment-rule-reply-image-path').value.trim();
        if (!imagePath) {
            showToast('请选择回复图片', 'warning');
            return;
        }
        rule.reply = '[图片回复]';
        rule.reply_image = imagePath;
    }
    
    commentRules.push(rule);
    saveCommentRules();
    updateCommentRulesDisplay();
    
    // 清空输入框
    document.getElementById('comment-rule-title').value = '';
    document.getElementById('comment-keywords').value = '';
    document.getElementById('comment-reply').value = '';
    document.getElementById('comment-rule-reply-image-path').value = '';
    document.querySelector('input[name="comment-rule-reply-type"][value="text"]').checked = true;
    toggleCommentRuleReplyContent('text');
    hideImagePreview('comment-rule');
    
    showToast(`评论回复规则"${name}"添加成功`, 'success');
    addCommentLog(`添加评论回复规则成功: ${name}`, 'success');
}

// 删除评论回复规则
function deleteCommentRule(id) {
    const rule = commentRules.find(r => r.id === id);
    if (!rule) return;
    
    const ruleName = rule.name;
    commentRules = commentRules.filter(rule => rule.id !== id);
    saveCommentRules();
    updateCommentRulesDisplay();
    
    showToast(`评论回复规则"${ruleName}"已删除`, 'success');
    addCommentLog('删除评论回复规则成功', 'success');
}

// 保存评论回复规则
function saveCommentRules() {
    fetch('/api/comment-rules', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({rules: commentRules})
    })
    .catch(error => {
        console.error('同步评论回复规则到服务器失败:', error);
        showToast('同步评论回复规则到服务器失败', 'error');
    });
}

// 加载评论回复规则
function loadCommentRules() {
    fetch('/api/comment-rules')
    .then(response => response.json())
    .then(data => {
        if (data.rules && Array.isArray(data.rules)) {
            commentRules = data.rules;
            addCommentLog(`从服务器加载了 ${commentRules.length} 条评论回复规则`, 'success');
        } else {
            commentRules = [];
        }
        updateCommentRulesDisplay();
    })
    .catch(error => {
        console.error('从服务器加载评论回复规则失败:', error);
        commentRules = [];
        updateCommentRulesDisplay();
    });
}

// 更新评论回复规则显示
function updateCommentRulesDisplay() {
    const container = document.getElementById('comment-rules-list');
    
    if (commentRules.length === 0) {
        container.innerHTML = '<p style="color: #999; text-align: center; padding: 20px;">暂无评论回复规则</p>';
        updateCommentPaginationControls();
        return;
    }
    
    const sortedRules = [...commentRules].sort((a, b) => {
        const timeA = a.created_at ? new Date(a.created_at).getTime() : a.id || 0;
        const timeB = b.created_at ? new Date(b.created_at).getTime() : b.id || 0;
        return timeB - timeA;
    });
    
    const totalPages = Math.ceil(sortedRules.length / commentRulesPerPage);
    const startIndex = (currentCommentPage - 1) * commentRulesPerPage;
    const endIndex = startIndex + commentRulesPerPage;
    const currentRules = sortedRules.slice(startIndex, endIndex);
    
    container.innerHTML = currentRules.map(rule => {
        const enabledStatus = rule.enabled ? '<span style="color: #2ed573;">✅</span>' : '<span style="color: #ff4757;">❌</span>';
        
        let replyContent = '';
        const replyType = rule.reply_type || 'text';
        
        if (replyType === 'image') {
            const imageName = rule.reply_image ? rule.reply_image.split(/[/\\]/).pop() : '未选择图片';
            replyContent = `<span style="color: #007bff;">🖼️</span> 图片回复: ${imageName}`;
        } else {
            const replyText = rule.reply && rule.reply.length > 100 ? rule.reply.substring(0, 100) + '...' : (rule.reply || '');
            replyContent = `<span style="color: #28a745;">💬</span> 文字回复: ${replyText}`;
        }
        
        return `
        <div class="rule-item">
            <div class="rule-title">${enabledStatus} ${rule.name || '未命名规则'}</div>
            <div class="rule-keywords">关键词: ${rule.keyword || ''}</div>
            <div class="rule-reply" title="${rule.reply || rule.reply_image || ''}">${replyContent}</div>
            <div class="rule-actions">
                <button class="edit-btn" onclick="editCommentRule(${rule.id})">✏️ 编辑</button>
                <button class="delete-btn" onclick="deleteCommentRule(${rule.id})">🗑️ 删除</button>
                <button class="toggle-btn" onclick="toggleCommentRule(${rule.id})">
                    ${rule.enabled ? '🔴' : '🟢'} 
                    ${rule.enabled ? '禁用' : '启用'}
                </button>
            </div>
        </div>
        `;
    }).join('');
    
    updateCommentPaginationControls();
}

// 更新评论回复分页控件
function updateCommentPaginationControls() {
    const totalPages = Math.ceil(commentRules.length / commentRulesPerPage);
    const pageInfo = `第 ${currentCommentPage} 页，共 ${totalPages} 页`;
    
    document.getElementById('page-info').textContent = pageInfo;
    document.getElementById('page-info-bottom').textContent = pageInfo;
    
    const prevButtons = [document.getElementById('prev-page'), document.getElementById('prev-page-bottom')];
    const nextButtons = [document.getElementById('next-page'), document.getElementById('next-page-bottom')];
    
    prevButtons.forEach(btn => {
        btn.disabled = currentCommentPage <= 1;
    });
    
    nextButtons.forEach(btn => {
        btn.disabled = currentCommentPage >= totalPages;
    });
}

// 切换评论回复页面
function changePage(direction) {
    const totalPages = Math.ceil(commentRules.length / commentRulesPerPage);
    
    if (direction === -1 && currentCommentPage > 1) {
        currentCommentPage--;
    } else if (direction === 1 && currentCommentPage < totalPages) {
        currentCommentPage++;
    }
    
    updateCommentRulesDisplay();
}

// 开始评论监控
function startCommentMonitoring() {
    fetch('/api/comment-start', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            isCommentMonitoring = true;
            updateCommentButtonStates();
            updateCommentStatus('监控评论中...');
            showToast('开始监控评论回复', 'success');
            addCommentLog('开始监控评论回复', 'success');
            startCommentLogPolling();
        } else {
            showToast('启动评论监控失败: ' + data.error, 'error');
            addCommentLog('启动评论监控失败: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showToast('启动评论监控失败: ' + error, 'error');
        addCommentLog('启动评论监控失败: ' + error, 'error');
    });
}

// 停止评论监控
function stopCommentMonitoring() {
    fetch('/api/comment-stop', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            isCommentMonitoring = false;
            updateCommentButtonStates();
            updateCommentStatus('已停止');
            showToast('停止监控评论回复', 'warning');
            addCommentLog('停止监控评论回复', 'warning');
        } else {
            showToast('停止评论监控失败: ' + data.error, 'error');
            addCommentLog('停止评论监控失败: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showToast('停止评论监控失败: ' + error, 'error');
        addCommentLog('停止评论监控失败: ' + error, 'error');
    });
}

// 更新评论按钮状态
function updateCommentButtonStates() {
    document.getElementById('start-btn').disabled = isCommentMonitoring;
    document.getElementById('stop-btn').disabled = !isCommentMonitoring;
    
    const statusIndicator = document.querySelector('.status-indicator');
    if (isCommentMonitoring) {
        statusIndicator.classList.add('active');
        document.querySelector('.status-icon').style.color = '#2ed573';
    } else {
        statusIndicator.classList.remove('active');
        document.querySelector('.status-icon').style.color = '#ccc';
    }
}

// 更新评论状态显示
function updateCommentStatus(status) {
    document.getElementById('status').textContent = status;
}

// 添加评论日志
function addCommentLog(message, type = 'info') {
    const log = document.getElementById('comment-log');
    
    // 安全检查：如果log容器不存在，直接返回
    if (!log) {
        console.log(`Comment Log: [${type.toUpperCase()}] ${message}`);
        return;
    }
    
    const timestamp = new Date().toLocaleTimeString();
    const entry = document.createElement('div');
    entry.className = `log-entry log-${type}`;
    entry.textContent = `[${timestamp}] ${message}`;
    log.appendChild(entry);
    
    const container = document.getElementById('log-container');
    if (container) {
        container.scrollTop = container.scrollHeight;
    }
    
    const entries = log.children;
    if (entries.length > 100) {
        log.removeChild(entries[0]);
    }
}

// 检查评论服务器状态
function checkCommentServerStatus() {
    fetch('/api/comment-status')
    .then(response => response.json())
    .then(data => {
        isCommentMonitoring = data.monitoring;
        updateCommentButtonStates();
        updateCommentStatus(data.monitoring ? '监控评论中...' : '未启动');
        if (data.monitoring) {
            startCommentLogPolling();
        }
    })
    .catch(error => {
        updateCommentStatus('服务器连接失败');
        showToast('无法连接到评论回复服务器', 'error');
        addCommentLog('无法连接到评论回复服务器', 'error');
    });
}

// 轮询评论日志
let lastCommentLogCount = 0;

function startCommentLogPolling() {
    if (!isCommentMonitoring) return;
    
    fetch('/api/comment-logs')
    .then(response => response.json())
    .then(data => {
        if (data.logs && data.logs.length > 0) {
            // 只显示新的日志条目
            if (data.logs.length > lastCommentLogCount) {
                const newLogs = data.logs.slice(0, data.logs.length - lastCommentLogCount);
                newLogs.reverse().forEach(logEntry => {
                    addCommentLog(logEntry.message, logEntry.type);
                });
                lastCommentLogCount = data.logs.length;
            }
        }
        
        // 更新监控状态
        if (data.monitoring !== isCommentMonitoring) {
            isCommentMonitoring = data.monitoring;
            updateCommentButtonStates();
            updateCommentStatus(data.monitoring ? '监控评论中...' : '未启动');
        }
    })
    .catch(error => {
        console.error('获取评论日志失败:', error);
        addCommentLog('获取日志失败: ' + error.message, 'error');
    });
    
    setTimeout(startCommentLogPolling, 2000);
}

// 编辑评论回复规则
function editCommentRule(id) {
    const rule = commentRules.find(r => r.id === id);
    if (!rule) return;
    
    editingCommentRuleId = id;
    
    document.getElementById('edit-comment-rule-title').value = rule.name || '';
    document.getElementById('edit-comment-keywords').value = rule.keyword || '';
    
    const replyType = rule.reply_type || 'text';
    document.querySelector(`input[name="edit-comment-reply-type"][value="${replyType}"]`).checked = true;
    toggleEditCommentReplyContent(replyType);
    
    if (replyType === 'text') {
        document.getElementById('edit-comment-reply').value = rule.reply || '';
    } else {
        document.getElementById('edit-comment-reply-image-path').value = rule.reply_image || '';
        if (rule.reply_image) {
            showImagePreview('edit-comment', rule.reply_image);
        }
    }
    
    const modal = document.getElementById('comment-edit-modal');
    modal.style.display = 'block';
    
    if (window.innerWidth <= 768) {
        document.body.style.overflow = 'hidden';
        document.body.style.position = 'fixed';
        document.body.style.width = '100%';
        
        setTimeout(() => {
            document.getElementById('edit-comment-rule-title').focus();
        }, 300);
    }
}

// 保存编辑的评论回复规则
function saveEditCommentRule() {
    const name = document.getElementById('edit-comment-rule-title').value.trim();
    const keywords = document.getElementById('edit-comment-keywords').value.trim();
    const replyType = document.querySelector('input[name="edit-comment-reply-type"]:checked').value;
    
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
        const reply = document.getElementById('edit-comment-reply').value.trim();
        if (!reply) {
            showToast('请填写回复内容', 'warning');
            return;
        }
        updateData.reply = reply;
        updateData.reply_image = '';
    } else {
        const imagePath = document.getElementById('edit-comment-reply-image-path').value.trim();
        if (!imagePath) {
            showToast('请选择回复图片', 'warning');
            return;
        }
        updateData.reply = '[图片回复]';
        updateData.reply_image = imagePath;
    }
    
    const ruleIndex = commentRules.findIndex(r => r.id === editingCommentRuleId);
    if (ruleIndex !== -1) {
        commentRules[ruleIndex] = {
            ...commentRules[ruleIndex],
            ...updateData
        };
        
        saveCommentRules();
        updateCommentRulesDisplay();
        closeCommentEditModal();
        
        showToast(`评论回复规则"${name}"已更新`, 'success');
        addCommentLog(`评论回复规则编辑成功: ${name}`, 'success');
    }
}

// 切换评论回复规则启用状态
function toggleCommentRule(id) {
    const ruleIndex = commentRules.findIndex(r => r.id === id);
    if (ruleIndex !== -1) {
        commentRules[ruleIndex].enabled = !commentRules[ruleIndex].enabled;
        saveCommentRules();
        updateCommentRulesDisplay();
        
        const status = commentRules[ruleIndex].enabled ? '启用' : '禁用';
        showToast(`评论回复规则"${commentRules[ruleIndex].name}"已${status}`, 'info');
        addCommentLog(`评论回复规则${status}成功: ${commentRules[ruleIndex].name}`, 'info');
    }
}

// 关闭编辑评论回复模态框
function closeCommentEditModal() {
    document.getElementById('comment-edit-modal').style.display = 'none';
    editingCommentRuleId = null;
    
    if (window.innerWidth <= 768) {
        document.body.style.overflow = '';
        document.body.style.position = '';
        document.body.style.width = '';
    }
    
    document.getElementById('edit-comment-rule-title').value = '';
    document.getElementById('edit-comment-keywords').value = '';
    document.getElementById('edit-comment-reply').value = '';
    document.getElementById('edit-comment-reply-image-path').value = '';
    document.querySelector('input[name="edit-comment-reply-type"][value="text"]').checked = true;
    toggleEditCommentReplyContent('text');
    hideImagePreview('edit-comment');
}

// 切换评论配置
function toggleCommentConfig() {
    const content = document.getElementById('comment-config-content');
    const icon = document.getElementById('comment-toggle-icon');
    
    if (content.style.display === 'none' || content.style.display === '') {
        content.style.display = 'block';
        icon.classList.add('rotated');
        localStorage.setItem('comment-config-expanded', 'true');
    } else {
        content.style.display = 'none';
        icon.classList.remove('rotated');
        localStorage.setItem('comment-config-expanded', 'false');
    }
}

// 加载评论时间配置
function loadCommentTimingConfig() {
    const isExpanded = localStorage.getItem('comment-config-expanded') === 'true';
    const content = document.getElementById('comment-config-content');
    const icon = document.getElementById('comment-toggle-icon');
    
    if (isExpanded && content && icon) {
        content.style.display = 'block';
        icon.classList.add('rotated');
    }
}

// 保存评论配置
function saveCommentConfig() {
    const commentCheckInterval = parseInt(document.getElementById('comment-check-interval').value);
    const commentSendDelay = parseFloat(document.getElementById('comment-send-delay').value);
    const onlyReplyNewComments = document.getElementById('only-reply-new-comments').checked;
    
    if (isNaN(commentCheckInterval) || commentCheckInterval < 10 || commentCheckInterval > 300) {
        showToast('评论检查间隔必须在10-300秒之间', 'error');
        return;
    }
    
    if (isNaN(commentSendDelay) || commentSendDelay < 1 || commentSendDelay > 10) {
        showToast('回复发送间隔必须在1-10秒之间', 'error');
        return;
    }
    
    if (commentSendDelay < 2.0) {
        if (!confirm(`回复间隔设置为${commentSendDelay}秒可能触发B站风控系统，建议设置为2秒以上。确定要保存吗？`)) {
            return;
        }
    }
    
    const configData = {
        comment_check_interval: commentCheckInterval,
        comment_send_delay: commentSendDelay,
        only_reply_new_comments: onlyReplyNewComments
    };
    
    fetch('/api/comment-config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(configData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('评论监控配置保存成功', 'success');
            addCommentLog('评论监控配置已更新', 'success');
            
            if (commentCheckInterval >= 30) {
                showToast('✅ 检查间隔设置合理，有助于避免频率限制', 'success');
            } else {
                showToast('⚠️ 检查间隔较短，请注意频率限制风险', 'warning');
            }
            
            if (commentSendDelay >= 2.0) {
                showToast('✅ 回复间隔设置合理，有助于避免风控', 'success');
            } else {
                showToast('⚠️ 回复间隔较短，请注意风控风险', 'warning');
            }
        } else {
            showToast('保存失败: ' + data.error, 'error');
            addCommentLog('评论监控配置保存失败: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showToast('保存失败: ' + error, 'error');
        addCommentLog('评论监控配置保存异常: ' + error, 'error');
    });
}

// 从私信配置导入
function importFromMessageConfig() {
    if (!confirm('确定要从私信回复配置导入设置吗？这将会覆盖当前的评论回复配置。')) {
        return;
    }
    
    showToast('正在导入私信配置...', 'info');
    
    fetch('/api/import-from-message-config', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast(data.message, 'success');
            addCommentLog('从私信配置导入成功: ' + data.message, 'success');
            
            // 重新加载配置和规则
            loadCommentConfig();
            loadCommentRules();
        } else {
            showToast('导入失败: ' + data.error, 'error');
            addCommentLog('从私信配置导入失败: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showToast('导入失败: ' + error, 'error');
        addCommentLog('从私信配置导入异常: ' + error, 'error');
    });
}

// 导出评论配置
function exportCommentConfig() {
    showToast('正在导出评论回复配置...', 'info');
    
    fetch('/api/export-comment-config')
    .then(response => {
        if (response.ok) {
            return response.blob();
        } else {
            return response.json().then(data => {
                throw new Error(data.error || '导出失败');
            });
        }
    })
    .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        
        const now = new Date();
        const timestamp = now.getFullYear() + 
            String(now.getMonth() + 1).padStart(2, '0') + 
            String(now.getDate()).padStart(2, '0') + '_' +
            String(now.getHours()).padStart(2, '0') + 
            String(now.getMinutes()).padStart(2, '0') + 
            String(now.getSeconds()).padStart(2, '0');
        
        a.download = `biligo_comment_config_${timestamp}.json`;
        
        // 安全检查：确保document.body存在
        if (document.body) {
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        } else {
            // 如果body不存在，尝试直接点击
            a.click();
        }
        
        window.URL.revokeObjectURL(url);
        
        showToast(`成功导出评论回复配置（${commentRules.length} 条规则）`, 'success');
    })
    .catch(error => {
        showToast('导出失败: ' + error, 'error');
    });
}

// 图片浏览器相关函数（复用私信系统的逻辑）
function openImageBrowser(target) {
    currentImageBrowserTarget = target;
    selectedImagePath = '';
    
    const modal = document.getElementById('image-browser-modal');
    modal.style.display = 'block';
    
    fetch('/api/get-home-directory')
    .then(response => response.json())
    .then(data => {
        if (data.success) {
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

function browsePath(path) {
    currentBrowserPath = path;
    document.getElementById('current-path-text').textContent = '📂 ' + path;
    
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
            fileList.innerHTML = `<div class="loading" style="color: var(--danger-color);">⚠️ ${data.error}</div>`;
        }
    })
    .catch(error => {
        fileList.innerHTML = `<div class="loading" style="color: var(--danger-color);">⚠️ 加载失败: ${error}</div>`;
    });
}

function displayFileList(items) {
    const fileList = document.getElementById('file-list');
    
    if (items.length === 0) {
        fileList.innerHTML = '<div class="loading">此文件夹为空</div>';
        return;
    }
    
    fileList.innerHTML = items.map(item => {
        let icon, details = '';
        
        if (item.type === 'directory') {
            icon = item.name === '..' ? '⬆️' : '📁';
        } else {
            icon = '🖼️';
            details = `${item.extension} • ${item.size}`;
        }
        
        const encodedPath = encodeURIComponent(item.path);
        const escapedName = escapeHtml(item.name);
        
        return `
            <div class="file-item ${item.type}" onclick="selectFileItem('${encodedPath}', '${item.type}', this)">
                <span class="file-icon">${icon}</span>
                <div class="file-info">
                    <div class="file-name">${escapedName}</div>
                    ${details ? `<div class="file-details">${details}</div>` : ''}
                </div>
            </div>
        `;
    }).join('');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function selectFileItem(path, type, element) {
    const decodedPath = decodeURIComponent(path);
    
    if (type === 'directory') {
        browsePath(decodedPath);
    } else {
        selectedImagePath = decodedPath;
        
        document.querySelectorAll('.file-item').forEach(item => {
            item.classList.remove('selected');
        });
        element.classList.add('selected');
        
        confirmImageSelection();
    }
}

function confirmImageSelection() {
    if (!selectedImagePath) {
        showToast('请选择一张图片', 'warning');
        return;
    }
    
    if (currentImageBrowserTarget === 'default-comment') {
        document.getElementById('default-comment-reply-image-path').value = selectedImagePath;
        showImagePreview('default-comment', selectedImagePath);
    } else if (currentImageBrowserTarget === 'comment-rule') {
        document.getElementById('comment-rule-reply-image-path').value = selectedImagePath;
        showImagePreview('comment-rule', selectedImagePath);
    } else if (currentImageBrowserTarget === 'edit-comment') {
        document.getElementById('edit-comment-reply-image-path').value = selectedImagePath;
        showImagePreview('edit-comment', selectedImagePath);
    }
    
    closeImageBrowser();
    showToast('图片选择成功', 'success');
}

function closeImageBrowser() {
    document.getElementById('image-browser-modal').style.display = 'none';
    currentImageBrowserTarget = null;
    selectedImagePath = '';
}

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

function showImagePreview(target, imagePath) {
    const previewId = target + '-image-preview';
    const preview = document.getElementById(previewId);
    
    if (!preview) return;
    
    const fileName = imagePath.split(/[/\\]/).pop();
    
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
                    🖼️ ${fileName}
                    <br><small>${data.file_size}</small>
                </div>
            `;
        } else {
            preview.innerHTML = `
                <div style="color: var(--text-light); text-align: center; padding: 20px;">
                    🖼️
                    <div>无法预览图片</div>
                    <small>${data.error || '未知错误'}</small>
                </div>
                <div class="image-info">
                    🖼️ ${fileName}
                </div>
            `;
        }
        preview.style.display = 'block';
    })
    .catch(error => {
        preview.innerHTML = `
            <div style="color: var(--text-light); text-align: center; padding: 20px;">
                🖼️
                <div>无法预览图片</div>
                <small>网络错误</small>
            </div>
            <div class="image-info">
                🖼️ ${fileName}
            </div>
        `;
        preview.style.display = 'block';
    });
}

function hideImagePreview(target) {
    const previewId = target + '-image-preview';
    const preview = document.getElementById(previewId);
    
    if (preview) {
        preview.style.display = 'none';
        preview.innerHTML = '';
    }
}

// 导入配置相关函数
function openCommentImportModal() {
    document.getElementById('comment-import-modal').style.display = 'block';
    clearCommentImportForm();
}

function closeCommentImportModal() {
    document.getElementById('comment-import-modal').style.display = 'none';
    clearCommentImportForm();
}

function clearCommentImportForm() {
    document.getElementById('comment-keywords-file').value = '';
    document.getElementById('comment-file-info').style.display = 'none';
    document.getElementById('comment-import-options').style.display = 'none';
    document.getElementById('comment-import-btn').disabled = true;
    
    const uploadArea = document.getElementById('comment-file-upload-area');
    uploadArea.classList.remove('dragover');
}

function handleCommentFileSelect(event) {
    const file = event.target.files[0];
    if (file) {
        displayCommentFileInfo(file);
        validateCommentFile(file);
    }
}

function displayCommentFileInfo(file) {
    const fileInfo = document.getElementById('comment-file-info');
    const fileName = document.getElementById('comment-file-name');
    const fileSize = document.getElementById('comment-file-size');
    
    fileName.textContent = file.name;
    fileSize.textContent = formatFileSize(file.size);
    fileInfo.style.display = 'block';
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function clearCommentSelectedFile() {
    document.getElementById('comment-keywords-file').value = '';
    clearCommentImportForm();
}

function validateCommentFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    fetch('/api/validate-comment-keywords-file', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            document.getElementById('comment-import-options').style.display = 'block';
            document.getElementById('comment-import-btn').disabled = false;
            showToast(`文件验证成功，发现 ${data.valid_rules} 条有效规则`, 'success');
        } else {
            showToast('文件验证失败: ' + data.error, 'error');
            document.getElementById('comment-import-btn').disabled = true;
        }
    })
    .catch(error => {
        showToast('验证文件时出错: ' + error, 'error');
        document.getElementById('comment-import-btn').disabled = true;
    });
}

function importCommentConfig() {
    const fileInput = document.getElementById('comment-keywords-file');
    const importMode = document.querySelector('input[name="comment-import-mode"]:checked').value;
    
    if (!fileInput.files[0]) {
        showToast('请选择文件', 'error');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('import_mode', importMode);
    
    const importBtn = document.getElementById('comment-import-btn');
    const originalText = importBtn.innerHTML;
    importBtn.disabled = true;
    importBtn.innerHTML = '🔄 导入中...';
    
    fetch('/api/import-comment-config', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast(data.message, 'success');
            closeCommentImportModal();
            loadCommentRules();
            loadCommentConfig();
        } else {
            showToast('导入失败: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showToast('导入时出错: ' + error, 'error');
    })
    .finally(() => {
        importBtn.disabled = false;
        importBtn.innerHTML = originalText;
    });
}

// 点击模态框外部关闭
window.onclick = function(event) {
    const editModal = document.getElementById('comment-edit-modal');
    const importModal = document.getElementById('comment-import-modal');
    const imageModal = document.getElementById('image-browser-modal');
    
    if (event.target === editModal) {
        closeCommentEditModal();
    } else if (event.target === importModal) {
        closeCommentImportModal();
    } else if (event.target === imageModal) {
        closeImageBrowser();
    }
}

// 键盘事件处理
document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        const editModal = document.getElementById('comment-edit-modal');
        const importModal = document.getElementById('comment-import-modal');
        const imageModal = document.getElementById('image-browser-modal');
        
        if (editModal.style.display === 'block') {
            closeCommentEditModal();
        } else if (importModal.style.display === 'block') {
            closeCommentImportModal();
        } else if (imageModal.style.display === 'block') {
            closeImageBrowser();
        }
    }
    
    if (event.key === 'Enter' && event.target.tagName !== 'TEXTAREA') {
        if (event.target.closest('#comment-edit-modal')) {
            event.preventDefault();
            saveEditCommentRule();
        } else if (event.target.closest('.keyword-panel')) {
            event.preventDefault();
            addCommentRule();
        } else if (event.target.closest('.config-panel')) {
            event.preventDefault();
            saveCommentLoginConfig();
        } else if (event.target.closest('.default-reply-panel')) {
            event.preventDefault();
            saveDefaultCommentReply();
        }
    }
});

// 移动端功能
if (window.innerWidth <= 768) {
    // 处理虚拟键盘
    let initialViewportHeight = window.innerHeight;
    
    window.addEventListener('resize', function() {
        const currentHeight = window.innerHeight;
        const heightDifference = initialViewportHeight - currentHeight;
        
        if (heightDifference > 150) {
            document.body.classList.add('keyboard-open');
            
            const modal = document.querySelector('.modal-content');
            if (modal && (document.getElementById('comment-edit-modal').style.display === 'block' || 
                         document.getElementById('comment-import-modal').style.display === 'block')) {
                modal.style.position = 'absolute';
                modal.style.top = '10px';
                modal.style.marginTop = '0';
            }
        } else {
            document.body.classList.remove('keyboard-open');
            
            const modal = document.querySelector('.modal-content');
            if (modal) {
                modal.style.position = '';
                modal.style.top = '';
                modal.style.marginTop = '';
            }
        }
    });
}


// ==================== 评论系统扫码登录相关函数 ====================

let commentQrcodePollingInterval = null;
let currentCommentQRCodeKey = null;
let isCommentQRCodeLoginSuccess = false; // 添加标志位，防止重复处理

// 显示扫码登录
function showCommentQRCodeLogin() {
    document.getElementById('comment-qrcode-login-modal').style.display = 'block';
    
    // 重置标志位和显示状态
    isCommentQRCodeLoginSuccess = false;
    document.getElementById('comment-qrcode-loading').style.display = 'block';
    document.getElementById('comment-qrcode-display').style.display = 'none';
    document.getElementById('comment-qrcode-error').style.display = 'none';
    document.getElementById('comment-qrcode-success').style.display = 'none';
    
    // 生成二维码
    generateCommentQRCode();
}

// 生成二维码
function generateCommentQRCode() {
    fetch('/api/qrcode-login/generate')
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            currentCommentQRCodeKey = data.qrcode_key;
            
            // 显示二维码
            document.getElementById('comment-qrcode-loading').style.display = 'none';
            document.getElementById('comment-qrcode-display').style.display = 'block';
            
            // 使用Google Chart API生成二维码图片
            const qrcodeContainer = document.getElementById('comment-qrcode-image');
            qrcodeContainer.innerHTML = '';
            
            const qrcodeUrl = `https://api.qrserver.com/v1/create-qr-code/?size=280x280&data=${encodeURIComponent(data.url)}`;
            const img = document.createElement('img');
            img.src = qrcodeUrl;
            img.style.width = '100%';
            img.style.border = '2px solid #e0e0e0';
            img.style.borderRadius = '8px';
            qrcodeContainer.appendChild(img);
            
            // 开始轮询状态
            startCommentQRCodePolling();
        } else {
            showCommentQRCodeError(data.error || '生成二维码失败');
        }
    })
    .catch(error => {
        console.error('生成二维码失败:', error);
        showCommentQRCodeError('网络错误，请重试');
    });
}

// 开始轮询二维码状态
function startCommentQRCodePolling() {
    // 清除之前的轮询
    if (commentQrcodePollingInterval) {
        clearInterval(commentQrcodePollingInterval);
    }
    
    // 重置成功标志
    isCommentQRCodeLoginSuccess = false;
    
    // 每2秒轮询一次
    commentQrcodePollingInterval = setInterval(() => {
        pollCommentQRCodeStatus();
    }, 2000);
    
    // 3分钟后自动停止轮询（二维码过期）
    setTimeout(() => {
        if (commentQrcodePollingInterval && !isCommentQRCodeLoginSuccess) {
            clearInterval(commentQrcodePollingInterval);
            commentQrcodePollingInterval = null;
            
            // 检查是否还在等待扫码状态
            const displayElement = document.getElementById('comment-qrcode-display');
            if (displayElement && displayElement.style.display !== 'none') {
                showCommentQRCodeError('二维码已过期，请重新生成');
            }
        }
    }, 180000);
}

// 轮询二维码状态
function pollCommentQRCodeStatus() {
    if (!currentCommentQRCodeKey || isCommentQRCodeLoginSuccess) return;
    
    fetch('/api/qrcode-login/poll', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            qrcode_key: currentCommentQRCodeKey
        })
    })
    .then(response => response.json())
    .then(data => {
        console.log('扫码状态:', data);
        
        // 如果已经成功，不再处理后续响应
        if (isCommentQRCodeLoginSuccess) {
            return;
        }
        
        if (data.success) {
            const status = data.status;
            const statusElement = document.getElementById('comment-qrcode-status');
            
            if (status === 'waiting') {
                statusElement.innerHTML = '<p>📱 请使用哔哩哔哩APP扫描二维码</p>';
            } else if (status === 'scanned') {
                statusElement.innerHTML = '<p style="color: #00a1d6; font-weight: 600;">✅ 已扫码，请在APP中确认登录</p>';
            } else if (status === 'success') {
                // 登录成功 - 立即设置标志位并停止轮询
                isCommentQRCodeLoginSuccess = true;
                clearInterval(commentQrcodePollingInterval);
                commentQrcodePollingInterval = null;
                
                // 显示成功状态
                document.getElementById('comment-qrcode-display').style.display = 'none';
                document.getElementById('comment-qrcode-success').style.display = 'block';
                
                showToast('扫码登录成功！', 'success');
                addCommentLog('扫码登录成功，配置已自动保存', 'success');
                
                // 3秒后关闭模态框并刷新配置
                setTimeout(() => {
                    closeCommentQRCodeLoginModal();
                    loadCommentConfig();
                }, 3000);
            }
        } else {
            // 只有在未成功的情况下才处理错误
            if (!isCommentQRCodeLoginSuccess) {
                if (data.status === 'expired') {
                    clearInterval(commentQrcodePollingInterval);
                    commentQrcodePollingInterval = null;
                    showCommentQRCodeError('二维码已过期，请重新生成');
                } else if (data.status === 'error') {
                    clearInterval(commentQrcodePollingInterval);
                    commentQrcodePollingInterval = null;
                    showCommentQRCodeError(data.message || '登录失败，请重试');
                    console.error('扫码登录错误:', data);
                } else {
                    console.error('轮询状态失败:', data.message);
                }
            }
        }
    })
    .catch(error => {
        console.error('轮询状态失败:', error);
        // 网络错误不停止轮询，继续尝试
    });
}

// 显示二维码错误
function showCommentQRCodeError(message) {
    // 如果已经成功，不显示错误
    if (isCommentQRCodeLoginSuccess) {
        return;
    }
    
    document.getElementById('comment-qrcode-loading').style.display = 'none';
    document.getElementById('comment-qrcode-display').style.display = 'none';
    document.getElementById('comment-qrcode-error').style.display = 'block';
    document.getElementById('comment-qrcode-error-message').textContent = message;
    
    // 清除轮询
    if (commentQrcodePollingInterval) {
        clearInterval(commentQrcodePollingInterval);
        commentQrcodePollingInterval = null;
    }
}

// 重试生成二维码
function retryCommentQRCodeLogin() {
    isCommentQRCodeLoginSuccess = false;
    document.getElementById('comment-qrcode-error').style.display = 'none';
    document.getElementById('comment-qrcode-loading').style.display = 'block';
    generateCommentQRCode();
}

// 关闭扫码登录模态框
function closeCommentQRCodeLoginModal() {
    document.getElementById('comment-qrcode-login-modal').style.display = 'none';
    
    // 清除轮询
    if (commentQrcodePollingInterval) {
        clearInterval(commentQrcodePollingInterval);
        commentQrcodePollingInterval = null;
    }
    
    currentCommentQRCodeKey = null;
    isCommentQRCodeLoginSuccess = false;
}

// 点击模态框外部关闭
window.addEventListener('click', function(event) {
    const commentQrcodeModal = document.getElementById('comment-qrcode-login-modal');
    if (event.target === commentQrcodeModal) {
        closeCommentQRCodeLoginModal();
    }
});
