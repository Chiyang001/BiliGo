// 评论回复系统 JavaScript

let commentRules = [];
let isCommentMonitoring = false;
let isCommentLoggedIn = false;
let currentCommentPage = 1;
const commentRulesPerPage = 10;
let editingCommentRuleId = null;

function escapeCommentHtml(value) {
    const node = document.createElement('span');
    node.textContent = String(value ?? '');
    return node.innerHTML;
}

async function requireCommentApiSuccess(response, fallbackMessage) {
    let data = null;
    try {
        data = await response.json();
    } catch {
        throw new Error(fallbackMessage);
    }
    if (!response.ok || !data.success) {
        throw new Error(data.error || fallbackMessage);
    }
    return data;
}

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', function() {
    loadCommentPlatformEmailConfig();
    loadCommentConfig();
    loadCommentRules();
    checkCommentServerStatus();
    loadCommentLogs();
    setInterval(loadCommentLogs, 4000);
    initCommentMobileOptimizations();
    loadCommentTimingConfig();
});

function loadCommentPlatformEmailConfig() {
    fetch('/api/platform-email-config/bili_comment').then(r => r.json()).then(data => {
        const cfg = data.config || {};
        const enabled = document.getElementById('platform-email-enabled');
        const receiver = document.getElementById('platform-email-receiver');
        if (enabled) enabled.checked = !!cfg.enabled;
        if (receiver) receiver.value = cfg.receiver_email || '';
    }).catch(error => console.warn('加载评论邮件提醒配置失败', error));
}

function saveCommentPlatformEmailConfig() {
    const enabled = !!document.getElementById('platform-email-enabled')?.checked;
    const receiver_email = document.getElementById('platform-email-receiver')?.value.trim() || '';
    fetch('/api/platform-email-config/bili_comment', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({enabled, receiver_email})
    }).then(r => r.json()).then(data => {
        if (typeof showToast === 'function') showToast(data.success ? '评论邮件提醒设置已保存' : (data.error || '保存失败'), data.success ? 'success' : 'error');
    }).catch(error => { if (typeof showToast === 'function') showToast('保存失败: ' + error.message, 'error'); });
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
    const icon = document.createElement('span');
    icon.className = 'toast-icon';
    const text = document.createElement('div');
    text.className = 'toast-message';
    text.textContent = String(message ?? '');
    toast.append(icon, text);
    
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

// 检查更新
function checkUpdate() {
    window.open('https://github.com/Chiyang001/BiliGo/releases/', '_blank');
}

// 打开教程文档页
function openDocsPage() {
    window.location.href = 'docs.html?from=comment#comment-mode';
}

// 平台切换下拉菜单
function togglePlatformSwitcher(event) {
    event.stopPropagation();
    document.getElementById('platform-switcher').classList.toggle('open');
}

document.addEventListener('click', function(event) {
    const switcher = document.getElementById('platform-switcher');
    if (switcher && !switcher.contains(event.target)) {
        switcher.classList.remove('open');
    }
});

// 加载评论回复配置
function loadCommentConfig() {
    fetch('/api/comment-config')
    .then(response => response.json())
    .then(data => {
        isCommentLoggedIn = !!(data.sessdata && data.bili_jct);
        updateCommentButtonStates();
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
            
            document.getElementById('default-comment-reply-message').value = data.default_comment_reply_message || '感谢您的评论！';
        }
        
        // 加载监控配置
        if (document.getElementById('comment-check-interval')) {
            document.getElementById('comment-check-interval').value = data.comment_check_interval || 5;
        }
        if (document.getElementById('comment-fetch-gap')) {
            document.getElementById('comment-fetch-gap').value =
                data.comment_fetch_gap !== undefined && data.comment_fetch_gap !== null
                    ? data.comment_fetch_gap
                    : 1;
        }
        if (document.getElementById('comment-fetch-mode')) {
            document.getElementById('comment-fetch-mode').value =
                data.comment_fetch_mode === 'browser' ? 'browser' : 'wbi';
        }
        if (document.getElementById('max-videos-to-check')) {
            document.getElementById('max-videos-to-check').value =
                data.max_videos_to_check !== undefined && data.max_videos_to_check !== null
                    ? data.max_videos_to_check
                    : 50;
        }
        if (document.getElementById('comments-per-video')) {
            document.getElementById('comments-per-video').value =
                data.comments_per_video !== undefined && data.comments_per_video !== null
                    ? data.comments_per_video
                    : 10;
        }
        if (document.getElementById('comment-monitor-sub-replies')) {
            document.getElementById('comment-monitor-sub-replies').checked =
                data.comment_monitor_sub_replies !== false;
        }
        if (document.getElementById('max-sub-pages-per-root')) {
            document.getElementById('max-sub-pages-per-root').value =
                data.max_sub_pages_per_root !== undefined && data.max_sub_pages_per_root !== null
                    ? data.max_sub_pages_per_root
                    : 15;
        }
        if (document.getElementById('video-list-strategy')) {
            document.getElementById('video-list-strategy').value =
                data.video_list_strategy === 'newest' ? 'newest' : 'both_ends';
        }
        if (document.getElementById('comment-main-sort-mode')) {
            document.getElementById('comment-main-sort-mode').value =
                String(data.comment_main_sort_mode) === '2' ? '2' : '3';
        }
        if (document.getElementById('comment-main-pages-max')) {
            document.getElementById('comment-main-pages-max').value =
                data.comment_main_pages_max !== undefined && data.comment_main_pages_max !== null
                    ? data.comment_main_pages_max
                    : 15;
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
async function saveDefaultCommentReply() {
    const enabled = document.getElementById('default-comment-reply-enabled').checked;
    const message = document.getElementById('default-comment-reply-message').value.trim();
    if (!message) {
        showToast('请填写默认评论回复内容', 'warning');
        return;
    }
    const configData = {
        default_comment_reply_enabled: enabled,
        default_comment_reply_message: message
    };
    
    try {
        const response = await fetch('/api/comment-config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(configData)
        });
        await requireCommentApiSuccess(response, '保存默认评论回复设置失败');
        showToast('默认评论回复设置已保存', 'success');
        addCommentLog('默认评论回复设置已更新', 'success');
    } catch (error) {
        const message = '保存默认评论回复设置失败: ' + error.message;
        showToast(message, 'error');
        addCommentLog(message, 'error');
    }
}

// 添加评论回复规则
async function addCommentRule() {
    const name = document.getElementById('comment-rule-title').value.trim();
    const keywords = document.getElementById('comment-keywords').value.trim();
    const reply = document.getElementById('comment-reply').value.trim();
    
    if (!name || !keywords) {
        showToast('请填写规则标题和关键词', 'warning');
        return;
    }
    if (!reply) {
        showToast('请填写回复内容', 'warning');
        return;
    }
    
    const rule = {
        id: Date.now(),
        name: name,
        keyword: keywords,
        reply: reply,
        enabled: true,
        created_at: new Date().toISOString()
    };
    
    const nextRules = [...commentRules, rule];
    try {
        await saveCommentRules(nextRules);
        commentRules = nextRules;
        updateCommentRulesDisplay();

        document.getElementById('comment-rule-title').value = '';
        document.getElementById('comment-keywords').value = '';
        document.getElementById('comment-reply').value = '';

        showToast(`评论回复规则"${name}"添加成功`, 'success');
        addCommentLog(`添加评论回复规则成功: ${name}`, 'success');
    } catch (error) {
        const message = '添加评论回复规则失败: ' + error.message;
        showToast(message, 'error');
        addCommentLog(message, 'error');
    }
}

// 删除评论回复规则
async function deleteCommentRule(id) {
    const rule = commentRules.find(r => r.id === id);
    if (!rule) return;
    
    const ruleName = rule.name;
    const nextRules = commentRules.filter(item => item.id !== id);
    try {
        await saveCommentRules(nextRules);
        commentRules = nextRules;
        updateCommentRulesDisplay();
        showToast(`评论回复规则"${ruleName}"已删除`, 'success');
        addCommentLog('删除评论回复规则成功', 'success');
    } catch (error) {
        const message = '删除评论回复规则失败: ' + error.message;
        showToast(message, 'error');
        addCommentLog(message, 'error');
    }
}

// 保存评论回复规则
async function saveCommentRules(rulesToSave = commentRules) {
    const response = await fetch('/api/comment-rules', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({rules: rulesToSave})
    });
    return requireCommentApiSuccess(response, '同步评论回复规则到服务器失败');
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
        currentCommentPage = 1;
        container.innerHTML = '<p style="color: #999; text-align: center; padding: 20px;">暂无评论回复规则</p>';
        updateCommentPaginationControls();
        return;
    }
    
    const sortedRules = [...commentRules].sort((a, b) => {
        const timeA = a.created_at ? new Date(a.created_at).getTime() : a.id || 0;
        const timeB = b.created_at ? new Date(b.created_at).getTime() : b.id || 0;
        return timeB - timeA;
    });
    
    const totalPages = Math.max(1, Math.ceil(sortedRules.length / commentRulesPerPage));
    currentCommentPage = Math.max(1, Math.min(currentCommentPage, totalPages));
    const startIndex = (currentCommentPage - 1) * commentRulesPerPage;
    const endIndex = startIndex + commentRulesPerPage;
    const currentRules = sortedRules.slice(startIndex, endIndex);
    
    container.innerHTML = currentRules.map(rule => {
        const enabledStatus = rule.enabled ? '<span style="color: #2ed573;"></span>' : '<span style="color: #ff4757;"></span>';
        
        const fullReply = String(rule.reply || '');
        const replyText = fullReply.length > 100 ? fullReply.substring(0, 100) + '...' : fullReply;
        const replyContent = `<span style="color: #28a745;"></span> 文字回复: ${escapeCommentHtml(replyText)}`;
        const ruleId = Number.isSafeInteger(Number(rule.id)) ? Number(rule.id) : 0;
        
        return `
        <div class="rule-item">
            <div class="rule-title">${enabledStatus} ${escapeCommentHtml(rule.name || '未命名规则')}</div>
            <div class="rule-keywords">关键词: ${escapeCommentHtml(rule.keyword || '')}</div>
            <div class="rule-reply" title="${escapeCommentHtml(fullReply)}">${replyContent}</div>
            <div class="rule-actions">
                <button class="edit-btn" onclick="editCommentRule(${ruleId})"> 编辑</button>
                <button class="delete-btn" onclick="deleteCommentRule(${ruleId})"> 删除</button>
                <button class="toggle-btn" onclick="toggleCommentRule(${ruleId})">
                    ${rule.enabled ? '' : ''} 
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
    const totalPages = Math.max(1, Math.ceil(commentRules.length / commentRulesPerPage));
    const pageInfo = `第 ${currentCommentPage} 页，共 ${totalPages} 页`;
    
    const pageInfoBottom = document.getElementById('page-info-bottom');
    if (pageInfoBottom) pageInfoBottom.textContent = pageInfo;
    
    const prevButtons = [document.getElementById('prev-page-bottom')].filter(Boolean);
    const nextButtons = [document.getElementById('next-page-bottom')].filter(Boolean);
    
    prevButtons.forEach(btn => {
        btn.disabled = currentCommentPage <= 1;
    });
    
    nextButtons.forEach(btn => {
        btn.disabled = currentCommentPage >= totalPages;
    });
}

// 切换评论回复页面
function changePage(direction) {
    const totalPages = Math.max(1, Math.ceil(commentRules.length / commentRulesPerPage));
    
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
    document.getElementById('start-btn').disabled = isCommentMonitoring || !isCommentLoggedIn;
    document.getElementById('stop-btn').disabled = !isCommentMonitoring || !isCommentLoggedIn;
    if (typeof setPlatformLoginRequired === 'function') {
        setPlatformLoginRequired(!isCommentLoggedIn);
    }
    
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
    const container = document.getElementById('logs-container');
    if (!container) {
        console.log(`Comment Log: [${type.toUpperCase()}] ${message}`);
        return;
    }
    appendPlatformLog(container, message, type);
}

async function loadCommentLogs() {
    try {
        const res = await fetch('/api/comment-logs');
        const data = await res.json();
        renderPlatformLogs(data.logs, document.getElementById('logs-container'));
        if (data.monitoring !== isCommentMonitoring) {
            isCommentMonitoring = data.monitoring;
            updateCommentButtonStates();
            updateCommentStatus(data.monitoring ? '监控评论中...' : '未启动');
        }
    } catch (e) {
        console.error('获取评论日志失败:', e);
    }
}

// 检查评论服务器状态
function checkCommentServerStatus() {
    fetch('/api/comment-status')
    .then(response => response.json())
    .then(data => {
        isCommentMonitoring = data.monitoring;
        isCommentLoggedIn = !!data.logged_in;
        updateCommentButtonStates();
        updateCommentStatus(data.monitoring ? '监控评论中...' : '未启动');
    })
    .catch(error => {
        updateCommentStatus('服务器连接失败');
        showToast('无法连接到评论回复服务器', 'error');
        addCommentLog('无法连接到评论回复服务器', 'error');
    });
}

// 编辑评论回复规则
function editCommentRule(id) {
    const rule = commentRules.find(r => r.id === id);
    if (!rule) return;
    
    editingCommentRuleId = id;
    
    document.getElementById('edit-comment-rule-title').value = rule.name || '';
    document.getElementById('edit-comment-keywords').value = rule.keyword || '';
    
    document.getElementById('edit-comment-reply').value = rule.reply || '';
    
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
async function saveEditCommentRule() {
    const name = document.getElementById('edit-comment-rule-title').value.trim();
    const keywords = document.getElementById('edit-comment-keywords').value.trim();
    const reply = document.getElementById('edit-comment-reply').value.trim();
    
    if (!name || !keywords) {
        showToast('请填写规则标题和关键词', 'warning');
        return;
    }
    if (!reply) {
        showToast('请填写回复内容', 'warning');
        return;
    }
    
    const ruleIndex = commentRules.findIndex(r => r.id === editingCommentRuleId);
    if (ruleIndex !== -1) {
        const nextRules = [...commentRules];
        nextRules[ruleIndex] = {
            ...commentRules[ruleIndex],
            name: name,
            keyword: keywords,
            reply: reply
        };

        try {
            await saveCommentRules(nextRules);
            commentRules = nextRules;
            updateCommentRulesDisplay();
            closeCommentEditModal();
            showToast(`评论回复规则"${name}"已更新`, 'success');
            addCommentLog(`评论回复规则编辑成功: ${name}`, 'success');
        } catch (error) {
            const message = '编辑评论回复规则失败: ' + error.message;
            showToast(message, 'error');
            addCommentLog(message, 'error');
        }
    }
}

// 切换评论回复规则启用状态
async function toggleCommentRule(id) {
    const ruleIndex = commentRules.findIndex(r => r.id === id);
    if (ruleIndex !== -1) {
        const nextRules = commentRules.map((rule, index) =>
            index === ruleIndex ? {...rule, enabled: !rule.enabled} : rule
        );
        try {
            await saveCommentRules(nextRules);
            commentRules = nextRules;
            updateCommentRulesDisplay();
            const status = commentRules[ruleIndex].enabled ? '启用' : '禁用';
            showToast(`评论回复规则"${commentRules[ruleIndex].name}"已${status}`, 'info');
            addCommentLog(`评论回复规则${status}成功: ${commentRules[ruleIndex].name}`, 'info');
        } catch (error) {
            const message = '更新评论回复规则状态失败: ' + error.message;
            showToast(message, 'error');
            addCommentLog(message, 'error');
        }
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
    const commentCheckInterval = parseFloat(document.getElementById('comment-check-interval').value);
    const commentFetchGap = parseFloat(document.getElementById('comment-fetch-gap').value);
    const commentFetchMode = document.getElementById('comment-fetch-mode')
        ? document.getElementById('comment-fetch-mode').value
        : 'wbi';
    const commentSendDelay = parseFloat(document.getElementById('comment-send-delay').value);
    const onlyReplyNewComments = document.getElementById('only-reply-new-comments').checked;
    
    if (isNaN(commentCheckInterval) || commentCheckInterval < 0 || !Number.isFinite(commentCheckInterval)) {
        showToast('评论检查间隔须为大于等于 0 的有限数字', 'error');
        return;
    }
    
    if (isNaN(commentFetchGap) || commentFetchGap < 0 || !Number.isFinite(commentFetchGap)) {
        showToast('多视频拉取间隔须为大于等于 0 的有限数字', 'error');
        return;
    }
    
    if (isNaN(commentSendDelay) || commentSendDelay < 1 || commentSendDelay > 10) {
        showToast('回复发送间隔必须在1-10秒之间', 'error');
        return;
    }
    
    const maxVideosToCheck = parseInt(document.getElementById('max-videos-to-check').value, 10);
    const commentsPerVideo = parseInt(document.getElementById('comments-per-video').value, 10);
    const maxSubPages = parseInt(document.getElementById('max-sub-pages-per-root').value, 10);
    const monitorSubReplies = document.getElementById('comment-monitor-sub-replies').checked;
    
    if (isNaN(maxVideosToCheck) || maxVideosToCheck < 1 || maxVideosToCheck > 500) {
        showToast('检查视频数量须在 1～500 之间', 'error');
        return;
    }
    if (isNaN(commentsPerVideo) || commentsPerVideo < 1 || commentsPerVideo > 30) {
        showToast('每视频顶层评论数须在 1～30 之间', 'error');
        return;
    }
    if (isNaN(maxSubPages) || maxSubPages < 1 || maxSubPages > 100) {
        showToast('楼中楼翻页上限须在 1～100 之间', 'error');
        return;
    }
    
    const videoListStrategy = document.getElementById('video-list-strategy')
        ? document.getElementById('video-list-strategy').value
        : 'both_ends';
    const commentMainSortMode = parseInt(
        document.getElementById('comment-main-sort-mode')
            ? document.getElementById('comment-main-sort-mode').value
            : '3',
        10
    );
    const commentMainPagesMax = parseInt(
        document.getElementById('comment-main-pages-max')
            ? document.getElementById('comment-main-pages-max').value
            : '15',
        10
    );
    if (commentMainSortMode !== 2 && commentMainSortMode !== 3) {
        showToast('主评论排序须为 2 或 3', 'error');
        return;
    }
    if (isNaN(commentMainPagesMax) || commentMainPagesMax < 1 || commentMainPagesMax > 50) {
        showToast('主评论翻页数须在 1～50 之间', 'error');
        return;
    }
    
    if (commentSendDelay < 2.0) {
        if (!confirm(`回复间隔设置为${commentSendDelay}秒可能触发B站风控系统，建议设置为2秒以上。确定要保存吗？`)) {
            return;
        }
    }
    
    const configData = {
        comment_check_interval: commentCheckInterval,
        comment_fetch_gap: commentFetchGap,
        comment_fetch_mode: commentFetchMode === 'browser' ? 'browser' : 'wbi',
        max_videos_to_check: maxVideosToCheck,
        comments_per_video: commentsPerVideo,
        comment_monitor_sub_replies: monitorSubReplies,
        max_sub_pages_per_root: maxSubPages,
        video_list_strategy: videoListStrategy === 'newest' ? 'newest' : 'both_ends',
        comment_main_sort_mode: commentMainSortMode,
        comment_main_pages_max: commentMainPagesMax,
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
            
            if (commentCheckInterval === 0) {
                showToast(' 检查间隔为 0 将尽量连续检查，请注意频率限制风险', 'warning');
            } else if (commentCheckInterval >= 30) {
                showToast(' 检查间隔设置合理，有助于避免频率限制', 'success');
            } else {
                showToast(' 检查间隔较短，请注意频率限制风险', 'warning');
            }
            
            if (commentSendDelay >= 2.0) {
                showToast(' 回复间隔设置合理，有助于避免风控', 'success');
            } else {
                showToast(' 回复间隔较短，请注意风控风险', 'warning');
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
    importBtn.innerHTML = ' 导入中...';
    
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
    
    if (event.target === editModal) {
        closeCommentEditModal();
    } else if (event.target === importModal) {
        closeCommentImportModal();
    }
}

// 键盘事件处理
document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        const editModal = document.getElementById('comment-edit-modal');
        const importModal = document.getElementById('comment-import-modal');
        const platformSwitcher = document.getElementById('platform-switcher');

        if (editModal.style.display === 'block') {
            closeCommentEditModal();
        } else if (importModal.style.display === 'block') {
            closeCommentImportModal();
        } else if (platformSwitcher) {
            platformSwitcher.classList.remove('open');
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
                statusElement.innerHTML = '<p> 请使用哔哩哔哩APP扫描二维码</p>';
            } else if (status === 'scanned') {
                statusElement.innerHTML = '<p style="color: #00a1d6; font-weight: 600;"> 已扫码，请在APP中确认登录</p>';
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

function confirmResetAllData() {
    const modal = document.getElementById('reset-confirm-modal');
    if (modal) {
        modal.style.display = 'block';
    }
}

function closeResetConfirmModal() {
    const modal = document.getElementById('reset-confirm-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

function executeResetAllData() {
    closeResetConfirmModal();
    showToast('正在清除所有数据...', 'info');

    fetch('/api/reset_all_data', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('所有数据已清除，页面即将刷新...', 'success');
            setTimeout(() => {
                window.location.reload();
            }, 2000);
        } else {
            showToast('清除数据失败: ' + (data.error || '未知错误'), 'error');
        }
    })
    .catch(error => {
        showToast('清除数据失败: ' + error.message, 'error');
    });
}

// 点击模态框外部关闭
window.addEventListener('click', function(event) {
    const commentQrcodeModal = document.getElementById('comment-qrcode-login-modal');
    const resetModal = document.getElementById('reset-confirm-modal');
    if (event.target === commentQrcodeModal) {
        closeCommentQRCodeLoginModal();
    }
    if (event.target === resetModal) {
        closeResetConfirmModal();
    }
});
