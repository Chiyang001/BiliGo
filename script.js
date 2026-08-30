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
    loadNewMessageConfig();
    loadFollowCheckIntervalConfig();
    loadTimingConfig();
    loadAccounts();  // 加载多账号列表
    loadEmailConfig();  // 加载邮件配置
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
    
    // 已关注用户回复类型切换
    const followedRadios = document.querySelectorAll('input[name="followed-reply-type"]');
    followedRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            toggleFollowedReplyContent(this.value);
        });
    });
    
    // 未关注用户回复类型切换
    const unfollowedRadios = document.querySelectorAll('input[name="unfollowed-reply-type"]');
    unfollowedRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            toggleUnfollowedReplyContent(this.value);
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
    
    // 关注后回复类型切换
    const followRadios = document.querySelectorAll('input[name="follow-reply-type"]');
    followRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            toggleFollowReplyContent(this.value);
        });
    });
    
    // 取消关注回复类型切换
    const unfollowRadios = document.querySelectorAll('input[name="unfollow-reply-type"]');
    unfollowRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            toggleUnfollowReplyContent(this.value);
        });
    });
}

// 切换区分用户类型的回复显示
function toggleSeparateReply() {
    const separateEnabled = document.getElementById('separate-reply-by-follow').checked;
    const unifiedSection = document.getElementById('unified-reply-section');
    const separateSection = document.getElementById('separate-reply-section');
    
    if (separateEnabled) {
        unifiedSection.style.display = 'none';
        separateSection.style.display = 'block';
    } else {
        unifiedSection.style.display = 'block';
        separateSection.style.display = 'none';
    }
}

// 切换已关注用户回复内容显示
function toggleFollowedReplyContent(type) {
    const textContent = document.getElementById('followed-text-content');
    const imageContent = document.getElementById('followed-image-content');
    
    if (type === 'text') {
        textContent.style.display = 'block';
        imageContent.style.display = 'none';
    } else {
        textContent.style.display = 'none';
        imageContent.style.display = 'block';
    }
}

// 切换未关注用户回复内容显示
function toggleUnfollowedReplyContent(type) {
    const textContent = document.getElementById('unfollowed-text-content');
    const imageContent = document.getElementById('unfollowed-image-content');
    
    if (type === 'text') {
        textContent.style.display = 'block';
        imageContent.style.display = 'none';
    } else {
        textContent.style.display = 'none';
        imageContent.style.display = 'block';
    }
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
    
    // 安全检查：如果toast容器不存在，直接返回
    if (!toastContainer) {
        console.log(`Toast: [${type.toUpperCase()}] ${message}`);
        return;
    }
    
    // 创建提示元素
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    // 根据类型设置图标
    let icon = '';
    if (type === 'success') icon = '';
    if (type === 'error') icon = '';
    if (type === 'warning') icon = '';
    
    toast.innerHTML = `
        <span class="toast-icon">${icon}</span>
        <div class="toast-message">${message}</div>
    `;
    
    // 添加到容器
    toastContainer.appendChild(toast);
    
    // 3秒后自动移除
    setTimeout(() => {
        if (toast && toast.parentNode) {
            toast.remove();
        }
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
            showToast('保存失败: ' + data.error, 'error');
            addLog('保存失败: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showToast('保存失败: ' + error, 'error');
        addLog('保存失败: ' + error, 'error');
    });
}

// 加载取消关注回复配置
function loadUnfollowReplyConfig() {
    fetch('/api/unfollow-reply-config')
    .then(response => response.json())
    .then(data => {
        if (document.getElementById('unfollow-reply-enabled')) {
            document.getElementById('unfollow-reply-enabled').checked = data.unfollow_reply_enabled || false;
            
            // 设置回复类型
            const replyType = data.unfollow_reply_type || 'text';
            document.querySelector(`input[name="unfollow-reply-type"][value="${replyType}"]`).checked = true;
            toggleUnfollowReplyContent(replyType);
            
            // 设置内容
            document.getElementById('unfollow-reply-message').value = data.unfollow_reply_message || '很遗憾看到您取消了关注，希望我们还有机会再见！';
            
            if (data.unfollow_reply_image) {
                document.getElementById('unfollow-reply-image-path').value = data.unfollow_reply_image;
                showImagePreview('unfollow', data.unfollow_reply_image);
            }
        }
    })
    .catch(error => {
        console.error('加载取消关注回复配置失败:', error);
    });
}

// 切换取消关注回复内容显示
function toggleUnfollowReplyContent(type) {
    const textContent = document.getElementById('unfollow-text-content');
    const imageContent = document.getElementById('unfollow-image-content');
    
    if (type === 'text') {
        textContent.style.display = 'block';
        imageContent.style.display = 'none';
    } else {
        textContent.style.display = 'none';
        imageContent.style.display = 'block';
    }
}

// 保存取消关注回复设置
function saveUnfollowReplyConfig() {
    const enabled = document.getElementById('unfollow-reply-enabled').checked;
    const replyType = document.querySelector('input[name="unfollow-reply-type"]:checked').value;
    
    let configData = {
        unfollow_reply_enabled: enabled,
        unfollow_reply_type: replyType
    };
    
    if (replyType === 'text') {
        const message = document.getElementById('unfollow-reply-message').value.trim();
        if (enabled && !message) {
            showToast('请填写取消关注回复消息', 'warning');
            return;
        }
        configData.unfollow_reply_message = message;
        configData.unfollow_reply_image = '';
    } else {
        const imagePath = document.getElementById('unfollow-reply-image-path').value.trim();
        if (enabled && !imagePath) {
            showToast('请选择取消关注回复图片', 'warning');
            return;
        }
        configData.unfollow_reply_message = '很遗憾看到您取消了关注';
        configData.unfollow_reply_image = imagePath;
    }
    
    fetch('/api/unfollow-reply-config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(configData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('取消关注回复设置保存成功', 'success');
            addLog('取消关注回复设置保存成功', 'success');
        } else {
            showToast('保存失败: ' + data.error, 'error');
            addLog('取消关注回复设置保存失败: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showToast('保存失败: ' + error, 'error');
        addLog('取消关注回复设置保存失败: ' + error, 'error');
    });
}

// 在页面加载时也加载取消关注回复配置
document.addEventListener('DOMContentLoaded', function() {
    // 加载取消关注回复设置
    loadUnfollowReplyConfig();
});

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
            
            // 加载区分用户类型的设置
            const separateByFollow = data.separate_reply_by_follow || false;
            document.getElementById('separate-reply-by-follow').checked = separateByFollow;
            toggleSeparateReply();
            
            // 设置统一回复类型
            const replyType = data.default_reply_type || 'text';
            document.querySelector(`input[name="default-reply-type"][value="${replyType}"]`).checked = true;
            toggleDefaultReplyContent(replyType);
            
            // 设置统一回复内容
            document.getElementById('default-reply-message').value = data.default_reply_message || '您好，我现在不在，稍后会回复您的消息。';
            
            if (data.default_reply_image) {
                document.getElementById('default-reply-image-path').value = data.default_reply_image;
                showImagePreview('default', data.default_reply_image);
            }
            
            // 加载已关注用户回复设置
            const followedReplyType = data.followed_reply_type || 'text';
            document.querySelector(`input[name="followed-reply-type"][value="${followedReplyType}"]`).checked = true;
            toggleFollowedReplyContent(followedReplyType);
            document.getElementById('followed-reply-message').value = data.followed_reply_message || '您好，感谢您的关注！我现在不在，稍后会回复您的消息。';
            if (data.followed_reply_image) {
                document.getElementById('followed-reply-image-path').value = data.followed_reply_image;
                showImagePreview('followed', data.followed_reply_image);
            }
            
            // 加载未关注用户回复设置
            const unfollowedReplyType = data.unfollowed_reply_type || 'text';
            document.querySelector(`input[name="unfollowed-reply-type"][value="${unfollowedReplyType}"]`).checked = true;
            toggleUnfollowedReplyContent(unfollowedReplyType);
            document.getElementById('unfollowed-reply-message').value = data.unfollowed_reply_message || '您好，我现在不在，稍后会回复您的消息。';
            if (data.unfollowed_reply_image) {
                document.getElementById('unfollowed-reply-image-path').value = data.unfollowed_reply_image;
                showImagePreview('unfollowed', data.unfollowed_reply_image);
            }
        }
        
        // 加载关注后回复设置
        loadFollowReplyConfig();
        
        // 加载仅回复新消息设置
        if (document.getElementById('only-reply-new-messages')) {
            document.getElementById('only-reply-new-messages').checked = data.only_reply_new_messages || false;
        }
        
        // 加载单用户最大回复次数设置
        if (document.getElementById('max-replies-per-user')) {
            document.getElementById('max-replies-per-user').value = data.max_replies_per_user || 3;
        }
    })
    .catch(error => {
        console.error('加载配置失败:', error);
    });
}

// 保存默认回复设置
function saveDefaultReply() {
    const enabled = document.getElementById('default-reply-enabled').checked;
    const separateByFollow = document.getElementById('separate-reply-by-follow').checked;
    
    let configData = {
        default_reply_enabled: enabled,
        separate_reply_by_follow: separateByFollow
    };
    
    if (separateByFollow) {
        // 保存已关注用户回复设置
        const followedReplyType = document.querySelector('input[name="followed-reply-type"]:checked').value;
        configData.followed_reply_type = followedReplyType;
        
        if (followedReplyType === 'text') {
            const message = document.getElementById('followed-reply-message').value.trim();
            if (enabled && !message) {
                showToast('请填写已关注用户的回复内容', 'warning');
                return;
            }
            configData.followed_reply_message = message;
            configData.followed_reply_image = '';
        } else {
            const imagePath = document.getElementById('followed-reply-image-path').value.trim();
            if (enabled && !imagePath) {
                showToast('请选择已关注用户的回复图片', 'warning');
                return;
            }
            configData.followed_reply_message = '';
            configData.followed_reply_image = imagePath;
        }
        
        // 保存未关注用户回复设置
        const unfollowedReplyType = document.querySelector('input[name="unfollowed-reply-type"]:checked').value;
        configData.unfollowed_reply_type = unfollowedReplyType;
        
        if (unfollowedReplyType === 'text') {
            const message = document.getElementById('unfollowed-reply-message').value.trim();
            if (enabled && !message) {
                showToast('请填写未关注用户的回复内容', 'warning');
                return;
            }
            configData.unfollowed_reply_message = message;
            configData.unfollowed_reply_image = '';
        } else {
            const imagePath = document.getElementById('unfollowed-reply-image-path').value.trim();
            if (enabled && !imagePath) {
                showToast('请选择未关注用户的回复图片', 'warning');
                return;
            }
            configData.unfollowed_reply_message = '';
            configData.unfollowed_reply_image = imagePath;
        }
    } else {
        // 保存统一的默认回复设置
        const replyType = document.querySelector('input[name="default-reply-type"]:checked').value;
        configData.default_reply_type = replyType;
        
        if (replyType === 'text') {
            const message = document.getElementById('default-reply-message').value.trim();
            if (enabled && !message) {
                showToast('请填写默认回复内容', 'warning');
                return;
            }
            configData.default_reply_message = message;
            configData.default_reply_image = '';
        } else {
            const imagePath = document.getElementById('default-reply-image-path').value.trim();
            if (enabled && !imagePath) {
                showToast('请选择默认回复图片', 'warning');
                return;
            }
            configData.default_reply_image = imagePath;
            configData.default_reply_message = '';
        }
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
        const enabledStatus = rule.enabled ? '<span style="color: #2ed573;"></span>' : '<span style="color: #ff4757;"></span>';
        
        // 根据回复类型显示不同的内容
        let replyContent = '';
        const replyType = rule.reply_type || 'text';
        
        if (replyType === 'image') {
            const imageName = rule.reply_image ? rule.reply_image.split(/[/\\]/).pop() : '未选择图片';
            replyContent = `<span style="color: #007bff;"></span> 图片回复: ${imageName}`;
        } else {
            const replyText = rule.reply && rule.reply.length > 100 ? rule.reply.substring(0, 100) + '...' : (rule.reply || '');
            replyContent = `<span style="color: #28a745;"></span> 文字回复: ${replyText}`;
        }
        
        return `
        <div class="rule-item">
            <div class="rule-title">${enabledStatus} ${rule.name || '未命名规则'}</div>
            <div class="rule-keywords">关键词: ${rule.keyword || ''}</div>
            <div class="rule-reply" title="${rule.reply || rule.reply_image || ''}">${replyContent}</div>
            <div class="rule-actions">
                <button class="edit-btn" onclick="editRule(${rule.id})"> 编辑</button>
                <button class="delete-btn" onclick="deleteRule(${rule.id})"> 删除</button>
                <button class="toggle-btn" onclick="toggleRule(${rule.id})">
                    ${rule.enabled ? '' : ''} 
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
    // 仅启动私信监控
    fetch('/api/start', { method: 'POST' })
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
            showToast('启动私信监控失败: ' + data.error, 'error');
            addLog('启动私信监控失败: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showToast('启动私信监控失败: ' + error, 'error');
        addLog('启动私信监控失败: ' + error, 'error');
    });
}

// 停止监控
function stopMonitoring() {
    // 仅停止私信监控
    fetch('/api/stop', { method: 'POST' })
    .then(response => response.json())
    .then(data => {
        isMonitoring = false;
        updateButtonStates();
        updateStatus('已停止');
        if (data.success) {
            showToast('停止监控私信', 'warning');
            addLog('停止监控私信', 'warning');
        } else {
            showToast('停止私信监控失败', 'warning');
            addLog('停止私信监控失败', 'warning');
        }
    })
    .catch(error => {
        isMonitoring = false;
        updateButtonStates();
        updateStatus('已停止');
        showToast('停止私信监控失败: ' + error, 'error');
        addLog('停止私信监控失败: ' + error, 'error');
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
    
    // 安全检查：如果log容器不存在，直接返回
    if (!log) {
        console.log(`Log: [${type.toUpperCase()}] ${message}`);
        return;
    }
    
    const timestamp = new Date().toLocaleTimeString();
    const entry = document.createElement('div');
    entry.className = `log-entry log-${type}`;
    entry.textContent = `[${timestamp}] ${message}`;
    log.appendChild(entry);
    
    // 自动滚动到底部
    const container = document.getElementById('log-container');
    if (container) {
        container.scrollTop = container.scrollHeight;
    }
    
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
    document.getElementById('current-path-text').textContent = ' ' + path;
    
    const fileList = document.getElementById('file-list');
    fileList.innerHTML = '<div class="loading"> 加载中...</div>';
    
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
            fileList.innerHTML = `<div class="loading" style="color: var(--danger-color);"> ${data.error}</div>`;
        }
    })
    .catch(error => {
        fileList.innerHTML = `<div class="loading" style="color: var(--danger-color);"> 加载失败: ${error}</div>`;
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
    } else if (currentImageBrowserTarget === 'followed') {
        document.getElementById('followed-reply-image-path').value = selectedImagePath;
        showImagePreview('followed', selectedImagePath);
    } else if (currentImageBrowserTarget === 'unfollowed') {
        document.getElementById('unfollowed-reply-image-path').value = selectedImagePath;
        showImagePreview('unfollowed', selectedImagePath);
    } else if (currentImageBrowserTarget === 'rule') {
        document.getElementById('rule-reply-image-path').value = selectedImagePath;
        showImagePreview('rule', selectedImagePath);
    } else if (currentImageBrowserTarget === 'edit') {
        document.getElementById('edit-reply-image-path').value = selectedImagePath;
        showImagePreview('edit', selectedImagePath);
    } else if (currentImageBrowserTarget === 'follow') {
        document.getElementById('follow-reply-image-path').value = selectedImagePath;
        showImagePreview('follow', selectedImagePath);
    } else if (currentImageBrowserTarget === 'unfollow') {
        document.getElementById('unfollow-reply-image-path').value = selectedImagePath;
        showImagePreview('unfollow', selectedImagePath);
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
                     ${fileName}
                    <br><small>${data.file_size}</small>
                </div>
            `;
        } else {
            preview.innerHTML = `
                <div style="color: var(--text-light); text-align: center; padding: 20px;">
                    
                    <div>无法预览图片</div>
                    <small>${data.error || '未知错误'}</small>
                </div>
                <div class="image-info">
                     ${fileName}
                </div>
            `;
        }
        preview.style.display = 'block';
    })
    .catch(error => {
        preview.innerHTML = `
            <div style="color: var(--text-light); text-align: center; padding: 20px;">
                
                <div>无法预览图片</div>
                <small>网络错误</small>
            </div>
            <div class="image-info">
                 ${fileName}
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
        } else if (event.target.closest('#unfollow-reply-config-panel')) {
            event.preventDefault();
            saveUnfollowReplyConfig();
        } else if (event.target.closest('.follow-reply-panel')) {
            event.preventDefault();
            saveFollowReply();
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
                
                if (confirm(`确定要删除规则"${ruleTitle.replace(/[]\s*/, '')}"吗？`)) {
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

// 关注后回复功能相关函数

// 加载关注后回复配置
function loadFollowReplyConfig() {
    fetch('/api/follow-reply-config')
    .then(response => response.json())
    .then(data => {
        if (document.getElementById('follow-reply-enabled')) {
            document.getElementById('follow-reply-enabled').checked = data.follow_reply_enabled || false;
            
            // 设置回复类型
            const replyType = data.follow_reply_type || 'text';
            document.querySelector(`input[name="follow-reply-type"][value="${replyType}"]`).checked = true;
            toggleFollowReplyContent(replyType);
            
            // 设置内容
            document.getElementById('follow-reply-message').value = data.follow_reply_message || '感谢您的关注！欢迎来到我的频道~';
            
            if (data.follow_reply_image) {
                document.getElementById('follow-reply-image-path').value = data.follow_reply_image;
                showImagePreview('follow', data.follow_reply_image);
            }
        }
    })
    .catch(error => {
        console.error('加载关注后回复配置失败:', error);
    });
}

// 切换关注后回复内容显示
function toggleFollowReplyContent(type) {
    const textContent = document.getElementById('follow-text-content');
    const imageContent = document.getElementById('follow-image-content');
    
    if (type === 'text') {
        textContent.style.display = 'block';
        imageContent.style.display = 'none';
    } else {
        textContent.style.display = 'none';
        imageContent.style.display = 'block';
    }
}

// 切换关注/取消关注配置面板
function toggleFollowReplyMode(mode) {
    const followPanel = document.getElementById('follow-reply-config-panel');
    const unfollowPanel = document.getElementById('unfollow-reply-config-panel');
    const followBtn = document.getElementById('follow-mode-btn');
    const unfollowBtn = document.getElementById('unfollow-mode-btn');

    if (!followPanel || !unfollowPanel || !followBtn || !unfollowBtn) return;

    if (mode === 'unfollow') {
        followPanel.style.display = 'none';
        unfollowPanel.style.display = 'block';
        followBtn.classList.remove('active');
        unfollowBtn.classList.add('active');
    } else {
        followPanel.style.display = 'block';
        unfollowPanel.style.display = 'none';
        unfollowBtn.classList.remove('active');
        followBtn.classList.add('active');
    }
}

// 保存关注后回复设置
function saveFollowReply() {
    const enabled = document.getElementById('follow-reply-enabled').checked;
    const replyType = document.querySelector('input[name="follow-reply-type"]:checked').value;
    const interval = document.getElementById('follow-check-interval').value;
    const scanPages = document.getElementById('follow-scan-pages').value;
    const newWindowSeconds = document.getElementById('follow-new-window-seconds').value;
    const backfillOnFirstRun = document.getElementById('follow-backfill-on-first-run').checked;
    
    // 验证检查间隔
    const intervalNum = parseInt(interval);
    if (isNaN(intervalNum) || intervalNum < 1 || intervalNum > 3600) {
        showToast('检查间隔必须在1-3600秒之间', 'error');
        return;
    }

    const scanPagesNum = parseInt(scanPages);
    if (isNaN(scanPagesNum) || scanPagesNum < 1 || scanPagesNum > 50) {
        showToast('扫描页数必须在1-50之间', 'error');
        return;
    }

    const newWindowSecondsNum = parseInt(newWindowSeconds);
    if (isNaN(newWindowSecondsNum) || newWindowSecondsNum < 30 || newWindowSecondsNum > 2592000) {
        showToast('新关注检测窗口必须在30-2592000秒之间', 'error');
        return;
    }
    
    // 风控提示
    if (intervalNum < 30) {
        if (!confirm(`检查间隔设置为${intervalNum}秒可能触发B站风控系统，建议设置为30秒以上。确定要保存吗？`)) {
            return;
        }
    }
    
    let configData = {
        follow_reply_enabled: enabled,
        follow_reply_type: replyType
    };
    
    if (replyType === 'text') {
        const message = document.getElementById('follow-reply-message').value.trim();
        if (enabled && !message) {
            showToast('请填写关注后回复消息', 'warning');
            return;
        }
        configData.follow_reply_message = message;
        configData.follow_reply_image = '';
    } else {
        const imagePath = document.getElementById('follow-reply-image-path').value.trim();
        if (enabled && !imagePath) {
            showToast('请选择关注后回复图片', 'warning');
            return;
        }
        configData.follow_reply_message = '感谢您的关注！';
        configData.follow_reply_image = imagePath;
    }
    
    // 先保存关注回复设置
    fetch('/api/follow-reply-config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(configData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // 关注回复设置保存成功后，保存检查间隔设置
            return fetch('/api/follow-check-interval-config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    follow_check_interval: intervalNum,
                    follow_scan_pages: scanPagesNum,
                    follow_new_window_seconds: newWindowSecondsNum,
                    follow_backfill_on_first_run: backfillOnFirstRun
                })
            });
        } else {
            throw new Error(data.error || '保存关注回复设置失败');
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('关注回复设置和检查间隔保存成功', 'success');
            addLog('关注回复设置和检查间隔保存成功', 'success');
            
            // 显示风控提示
            if (intervalNum < 30) {
                showToast(' 间隔较短，请注意风控风险', 'warning');
            } else {
                showToast(' 间隔设置合理，有助于避免风控', 'success');
            }
        } else {
            throw new Error(data.error || '保存检查间隔设置失败');
        }
    })
    .catch(error => {
        showToast('保存失败: ' + error, 'error');
        addLog('保存关注回复设置失败: ' + error, 'error');
    });
}

// 测试关注者检测功能
function testFollowDetection() {
    showToast('正在测试关注者检测功能...', 'info');
    addLog('开始测试关注者检测功能', 'info');
    
    fetch('/api/test-follow-detection', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast(data.message, 'success');
            addLog(`测试成功: ${data.message}`, 'success');
            
            if (data.followers && data.followers.length > 0) {
                addLog('最近关注者列表:', 'info');
                data.followers.forEach(follower => {
                    const followTime = new Date(follower.mtime * 1000).toLocaleString();
                    addLog(`- ${follower.uname} (UID: ${follower.mid}) 关注时间: ${followTime}`, 'info');
                });
            }
        } else {
            showToast('测试失败: ' + data.error, 'error');
            addLog('测试关注者检测失败: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showToast('测试失败: ' + error, 'error');
        addLog('测试关注者检测异常: ' + error, 'error');
    });
}

// 加载仅回复新消息配置
function loadNewMessageConfig() {
    fetch('/api/new-message-config')
    .then(response => response.json())
    .then(data => {
        if (document.getElementById('only-reply-new-messages')) {
            document.getElementById('only-reply-new-messages').checked = data.only_reply_new_messages || false;
        }
        if (document.getElementById('max-replies-per-user')) {
            document.getElementById('max-replies-per-user').value = data.max_replies_per_user || 3;
        }
    })
    .catch(error => {
        console.error('加载仅回复新消息配置失败:', error);
    });
}

// 保存仅回复新消息配置
function saveNewMessageConfig() {
    const onlyReplyNewMessages = document.getElementById('only-reply-new-messages').checked;
    const maxRepliesPerUser = parseInt(document.getElementById('max-replies-per-user').value);
    
    // 验证输入值
    if (isNaN(maxRepliesPerUser) || maxRepliesPerUser < 1 || maxRepliesPerUser > 100) {
        showToast('单用户最大回复次数必须在1-100之间', 'error');
        return;
    }
    
    fetch('/api/new-message-config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            only_reply_new_messages: onlyReplyNewMessages,
            max_replies_per_user: maxRepliesPerUser
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('消息设置已保存', 'success');
            addLog('仅回复新消息配置已更新', 'success');
            if (maxRepliesPerUser <= 5) {
                addLog(`单用户最大回复次数设置为${maxRepliesPerUser}次，有助于避免重复骚扰`, 'success');
            }
        } else {
            showToast('保存失败', 'error');
            addLog('保存仅回复新消息配置失败', 'error');
        }
    })
    .catch(error => {
        showToast('保存失败: ' + error, 'error');
        addLog('保存仅回复新消息配置异常: ' + error, 'error');
    });
}

// 加载关注者检查间隔配置
function loadFollowCheckIntervalConfig() {
    fetch('/api/follow-check-interval-config')
    .then(response => response.json())
    .then(data => {
        if (document.getElementById('follow-check-interval')) {
            document.getElementById('follow-check-interval').value = data.follow_check_interval || 1800;
        }
        if (document.getElementById('follow-scan-pages')) {
            document.getElementById('follow-scan-pages').value = data.follow_scan_pages || 3;
        }
        if (document.getElementById('follow-new-window-seconds')) {
            document.getElementById('follow-new-window-seconds').value = data.follow_new_window_seconds || 90;
        }
        if (document.getElementById('follow-backfill-on-first-run')) {
            document.getElementById('follow-backfill-on-first-run').checked = data.follow_backfill_on_first_run || false;
        }
    })
    .catch(error => {
        console.error('加载关注者检查间隔配置失败:', error);
    });
}

// ==================== 导入/导出功能 ====================

// 打开导入模态框
function openImportModal() {
    document.getElementById('import-modal').style.display = 'block';
    clearImportForm();
}

// 关闭导入模态框
function closeImportModal() {
    document.getElementById('import-modal').style.display = 'none';
    clearImportForm();
}

// 清空导入表单
function clearImportForm() {
    document.getElementById('keywords-file').value = '';
    document.getElementById('file-info').style.display = 'none';
    document.getElementById('validation-result').style.display = 'none';
    document.getElementById('import-options').style.display = 'none';
    document.getElementById('import-btn').disabled = true;
    
    // 重置上传区域
    const uploadArea = document.getElementById('file-upload-area');
    uploadArea.classList.remove('dragover');
}

// 处理文件选择
function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) {
        displayFileInfo(file);
        validateFile(file);
    }
}

// 显示文件信息
function displayFileInfo(file) {
    const fileInfo = document.getElementById('file-info');
    const fileName = document.getElementById('file-name');
    const fileSize = document.getElementById('file-size');
    
    fileName.textContent = file.name;
    fileSize.textContent = formatFileSize(file.size);
    fileInfo.style.display = 'block';
}

// 格式化文件大小
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

// 清除选择的文件
function clearSelectedFile() {
    document.getElementById('keywords-file').value = '';
    clearImportForm();
}

// 验证文件
function validateFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    fetch('/api/validate-keywords-file', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            displayValidationResult(data);
            document.getElementById('import-options').style.display = 'block';
            document.getElementById('import-btn').disabled = false;
        } else {
            showToast('文件验证失败: ' + data.error, 'error');
            document.getElementById('import-btn').disabled = true;
        }
    })
    .catch(error => {
        showToast('验证文件时出错: ' + error, 'error');
        document.getElementById('import-btn').disabled = true;
    });
}

// 显示验证结果
function displayValidationResult(data) {
    const validationResult = document.getElementById('validation-result');
    const totalRules = document.getElementById('total-rules');
    const validRules = document.getElementById('valid-rules');
    const invalidRules = document.getElementById('invalid-rules');
    const sampleRulesList = document.getElementById('sample-rules-list');
    
    totalRules.textContent = data.total_rules;
    validRules.textContent = data.valid_rules;
    invalidRules.textContent = data.invalid_rules;
    
    // 显示规则预览
    if (sampleRulesList) {
        sampleRulesList.innerHTML = '';
        if (data.sample_rules && data.sample_rules.length > 0) {
            data.sample_rules.forEach(rule => {
                const ruleItem = document.createElement('div');
                ruleItem.className = 'sample-rule-item';
                ruleItem.innerHTML = `
                    <div class="rule-name">${escapeHtml(rule.name)}</div>
                    <div class="rule-keyword">关键词: ${escapeHtml(rule.keyword)}</div>
                    <div class="rule-reply">回复: ${escapeHtml(rule.reply)}</div>
                `;
                sampleRulesList.appendChild(ruleItem);
            });
        } else {
            sampleRulesList.innerHTML = '<p style="color: #666; font-size: 13px;">无有效规则预览</p>';
        }
    }
    
    validationResult.style.display = 'block';
}

// HTML转义函数
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 导入关键词
function importConfig() {
    const fileInput = document.getElementById('keywords-file');
    const importMode = document.querySelector('input[name="import-mode"]:checked').value;
    
    if (!fileInput.files[0]) {
        showToast('请选择文件', 'error');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('import_mode', importMode);
    
    // 禁用导入按钮，显示加载状态
    const importBtn = document.getElementById('import-btn');
    const originalText = importBtn.innerHTML;
    importBtn.disabled = true;
    importBtn.innerHTML = ' 导入中...';
    
    fetch('/api/import-config', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast(data.message, 'success');
            closeImportModal();
            loadRules(); // 重新加载规则列表
            loadConfig(); // 重新加载配置
        } else {
            showToast('导入失败: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showToast('导入时出错: ' + error, 'error');
    })
    .finally(() => {
        // 恢复按钮状态
        importBtn.disabled = false;
        importBtn.innerHTML = originalText;
    });
}

// 导出关键词
function exportConfig() {
    showToast('正在导出配置包...', 'info');
    
    fetch('/api/export-config')
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
        // 创建下载链接
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        
        // 生成文件名
        const now = new Date();
        const timestamp = now.getFullYear() + 
            String(now.getMonth() + 1).padStart(2, '0') + 
            String(now.getDate()).padStart(2, '0') + '_' +
            String(now.getHours()).padStart(2, '0') + 
            String(now.getMinutes()).padStart(2, '0') + 
            String(now.getSeconds()).padStart(2, '0');
        
        a.download = `biligo_config_${timestamp}.json`;
        
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
        
        showToast(`成功导出完整配置包（${rules.length} 条规则）`, 'success');
    })
    .catch(error => {
        showToast('导出失败: ' + error, 'error');
    });
}

// 文件拖拽功能
document.addEventListener('DOMContentLoaded', function() {
    const uploadArea = document.getElementById('file-upload-area');
    
    if (uploadArea) {
        // 阻止默认拖拽行为
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            uploadArea.addEventListener(eventName, preventDefaults, false);
        });
        
        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }
        
        // 拖拽进入和悬停
        ['dragenter', 'dragover'].forEach(eventName => {
            uploadArea.addEventListener(eventName, highlight, false);
        });
        
        // 拖拽离开
        ['dragleave', 'drop'].forEach(eventName => {
            uploadArea.addEventListener(eventName, unhighlight, false);
        });
        
        function highlight(e) {
            uploadArea.classList.add('dragover');
        }
        
        function unhighlight(e) {
            uploadArea.classList.remove('dragover');
        }
        
        // 处理文件放置
        uploadArea.addEventListener('drop', handleDrop, false);
        
        function handleDrop(e) {
            const dt = e.dataTransfer;
            const files = dt.files;
            
            if (files.length > 0) {
                const file = files[0];
                if (file.name.toLowerCase().endsWith('.json')) {
                    document.getElementById('keywords-file').files = files;
                    displayFileInfo(file);
                    validateFile(file);
                } else {
                    showToast('请选择JSON格式文件', 'error');
                }
            }
        }
    }
});

// ==================== 时间间隔配置功能 ====================

// 切换时间间隔配置容器
function toggleTimingConfig() {
    const content = document.getElementById('timing-config-content');
    const icon = document.getElementById('timing-toggle-icon');
    
    if (content.style.display === 'none' || content.style.display === '') {
        content.style.display = 'block';
        icon.textContent = '▲'; // 上箭头
        icon.classList.add('rotated');
        
        // 保存展开状态到本地存储
        localStorage.setItem('timing-config-expanded', 'true');
    } else {
        content.style.display = 'none';
        icon.textContent = '▼'; // 下箭头
        icon.classList.remove('rotated');
        
        // 保存收起状态到本地存储
        localStorage.setItem('timing-config-expanded', 'false');
    }
}

// 加载时间间隔配置
function loadTimingConfig() {
    fetch('/api/timing-config')
    .then(response => response.json())
    .then(data => {
        if (document.getElementById('message-check-interval')) {
            document.getElementById('message-check-interval').value = data.message_check_interval || 0.05;
        }
        if (document.getElementById('send-delay-interval')) {
            document.getElementById('send-delay-interval').value = data.send_delay_interval || 1.0;
        }
        if (document.getElementById('auto-restart-interval')) {
            document.getElementById('auto-restart-interval').value = data.auto_restart_interval || 300;
        }
        
        // 恢复展开/收起状态
        const isExpanded = localStorage.getItem('timing-config-expanded') === 'true';
        const content = document.getElementById('timing-config-content');
        const icon = document.getElementById('timing-toggle-icon');
        
        if (isExpanded && content && icon) {
            content.style.display = 'block';
            icon.textContent = '▲'; // 上箭头
            icon.classList.add('rotated');
        } else if (icon) {
            icon.textContent = '▼'; // 下箭头
        }
    })
    .catch(error => {
        console.error('加载时间间隔配置失败:', error);
    });
}

// 保存时间间隔配置
function saveTimingConfig() {
    const messageCheckInterval = parseFloat(document.getElementById('message-check-interval').value);
    const sendDelayInterval = parseFloat(document.getElementById('send-delay-interval').value);
    const autoRestartInterval = parseInt(document.getElementById('auto-restart-interval').value);
    
    // 验证输入值
    if (isNaN(messageCheckInterval) || messageCheckInterval < 0.01 || messageCheckInterval > 5) {
        showToast('消息监测间隔必须在0.01-5秒之间', 'error');
        return;
    }
    
    if (isNaN(sendDelayInterval) || sendDelayInterval < 0.1 || sendDelayInterval > 10) {
        showToast('发送等待间隔必须在0.1-10秒之间', 'error');
        return;
    }
    
    if (isNaN(autoRestartInterval) || autoRestartInterval < 60 || autoRestartInterval > 3600) {
        showToast('自动重启间隔必须在60-3600秒之间', 'error');
        return;
    }
    
    // 风控提示
    if (sendDelayInterval < 1.0) {
        if (!confirm(`发送间隔设置为${sendDelayInterval}秒可能触发B站风控系统，建议设置为1秒以上。确定要保存吗？`)) {
            return;
        }
    }
    
    const configData = {
        message_check_interval: messageCheckInterval,
        send_delay_interval: sendDelayInterval,
        auto_restart_interval: autoRestartInterval
    };
    
    fetch('/api/timing-config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(configData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('时间间隔配置保存成功', 'success');
            addLog('时间间隔配置已更新', 'success');
            
            // 显示配置提示
            if (messageCheckInterval <= 0.05) {
                showToast(' 消息监测间隔设置合理，响应速度快', 'success');
            }
            if (sendDelayInterval >= 1.0) {
                showToast(' 发送间隔设置合理，有助于避免风控', 'success');
            } else {
                showToast(' 发送间隔较短，请注意风控风险', 'warning');
            }
        } else {
            showToast('保存失败: ' + data.error, 'error');
            addLog('时间间隔配置保存失败: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showToast('保存失败: ' + error, 'error');
        addLog('时间间隔配置保存异常: ' + error, 'error');
    });
}

// 切换到评论回复模式
function switchToCommentMode() {
    window.location.href = 'comment';
}

// 跳转到日志页面
function goToLogsPage() {
    window.location.href = 'logs.html';
}

// 检查更新
function checkUpdate() {
    window.open('https://github.com/Chiyang001/BiliGo/releases/', '_blank');
}

// 打开教程文档页
function openDocsPage() {
    window.location.href = 'docs.html';
}


// ==================== 多账号管理功能 ====================

// 加载账号列表
function loadAccounts() {
    fetch('/api/accounts')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updateAccountsList(data.accounts);
                
                // 更新多账号模式开关与界面显示（不触发服务端保存）
                const multiModeCheckbox = document.getElementById('multi-account-mode');
                if (multiModeCheckbox) {
                    multiModeCheckbox.checked = data.multi_account_mode || false;
                    applyAccountModeUI(data.multi_account_mode || false);
                }
            }
        })
        .catch(error => {
            console.error('加载账号列表失败:', error);
        });
}

// 更新账号列表显示
function updateAccountsList(accounts) {
    const accountsList = document.getElementById('accounts-list');
    if (!accountsList) return;
    
    if (!accounts || accounts.length === 0) {
        accountsList.innerHTML = '<p class="help-text">暂无账号，点击下方按钮添加</p>';
        return;
    }
    
    let html = '<div class="accounts-container">';
    accounts.forEach(account => {
        const statusClass = account.enabled ? 'enabled' : 'disabled';
        const statusText = account.enabled ? '已启用' : '已禁用';
        const statusIcon = account.enabled ? '' : '⏸';
        
        html += `
            <div class="account-item ${statusClass}">
                <div class="account-info">
                    <div class="account-name">${statusIcon} ${account.name}</div>
                    <div class="account-details">
                        <span>UID: ${account.uid || '未知'}</span>
                        <span>SESSDATA: ${account.sessdata_preview}</span>
                    </div>
                </div>
                <div class="account-actions">
                    <button class="btn-small ${account.enabled ? 'btn-warning' : 'btn-success'}" 
                            onclick="toggleAccount('${account.name}', ${!account.enabled})">
                        ${account.enabled ? '禁用' : '启用'}
                    </button>
                    <button class="btn-small btn-danger" onclick="deleteAccount('${account.name}')">
                        删除
                    </button>
                </div>
            </div>
        `;
    });
    html += '</div>';
    
    accountsList.innerHTML = html;
}

// 仅切换界面显示，不保存到服务端
function applyAccountModeUI(multiMode) {
    const singleConfig = document.getElementById('single-account-config');
    const multiConfig = document.getElementById('multi-account-config');
    
    if (!singleConfig || !multiConfig) return;
    
    if (multiMode) {
        singleConfig.style.display = 'none';
        multiConfig.style.display = 'block';
    } else {
        singleConfig.style.display = 'block';
        multiConfig.style.display = 'none';
    }
}

// 切换账号模式显示并保存
function toggleAccountMode() {
    const multiMode = document.getElementById('multi-account-mode').checked;
    applyAccountModeUI(multiMode);
    toggleMultiAccountMode(multiMode);
}

// 切换多账号模式（保存到服务端）
function toggleMultiAccountMode(enabled) {
    fetch('/api/accounts', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            action: 'toggle_mode',
            enabled: enabled
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast(data.message, 'success');
        } else {
            showToast(data.error || '切换模式失败', 'error');
            // 恢复复选框状态
            document.getElementById('multi-account-mode').checked = !enabled;
        }
    })
    .catch(error => {
        showToast('切换模式失败: ' + error, 'error');
        document.getElementById('multi-account-mode').checked = !enabled;
    });
}

// 打开添加账号模态框
function openAddAccountModal(keepExisting = false) {
    const modal = document.getElementById('add-account-modal');
    if (modal) {
        modal.style.display = 'block';
        if (!keepExisting) {
            // 清空输入框
            document.getElementById('account-name').value = '';
            document.getElementById('account-sessdata').value = '';
            document.getElementById('account-bili-jct').value = '';
            document.getElementById('account-email').value = '';
        }
    }
}

// 关闭添加账号模态框
function closeAddAccountModal() {
    const modal = document.getElementById('add-account-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// 添加账号
function addAccount() {
    const name = document.getElementById('account-name').value.trim();
    const sessdata = document.getElementById('account-sessdata').value.trim();
    const bili_jct = document.getElementById('account-bili-jct').value.trim();
    const email = document.getElementById('account-email').value.trim();
    
    if (!name) {
        showToast('请输入账号名称', 'error');
        return;
    }
    
    if (!sessdata || !bili_jct) {
        showToast('请填写完整的登录信息', 'error');
        return;
    }
    
    // 显示加载提示
    showToast('正在验证账号...', 'info');
    
    fetch('/api/accounts', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            action: 'add',
            name: name,
            sessdata: sessdata,
            bili_jct: bili_jct,
            email: email
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast(data.message, 'success');
            closeAddAccountModal();
            loadAccounts();  // 重新加载账号列表
        } else {
            showToast(data.error || '添加账号失败', 'error');
        }
    })
    .catch(error => {
        showToast('添加账号失败: ' + error, 'error');
    });
}

// 切换账号启用状态
function toggleAccount(name, enabled) {
    fetch('/api/accounts', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            action: 'update',
            name: name,
            enabled: enabled
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast(data.message, 'success');
            loadAccounts();  // 重新加载账号列表
        } else {
            showToast(data.error || '操作失败', 'error');
        }
    })
    .catch(error => {
        showToast('操作失败: ' + error, 'error');
    });
}

// 删除账号
function deleteAccount(name) {
    if (!confirm(`确定要删除账号 "${name}" 吗？此操作不可恢复。`)) {
        return;
    }
    
    fetch('/api/accounts', {
        method: 'DELETE',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            name: name
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast(data.message, 'success');
            loadAccounts();  // 重新加载账号列表
        } else {
            showToast(data.error || '删除失败', 'error');
        }
    })
    .catch(error => {
        showToast('删除失败: ' + error, 'error');
    });
}

// 点击模态框外部关闭
window.onclick = function(event) {
    const addAccountModal = document.getElementById('add-account-modal');
    if (event.target == addAccountModal) {
        closeAddAccountModal();
    }
}
// 邮件配置相关函数
function toggleEmailConfig() {
    const content = document.getElementById('email-config-content');
    const icon = document.getElementById('email-toggle-icon');
    
    if (content.style.display === 'none' || content.style.display === '') {
        content.style.display = 'block';
        icon.textContent = '▲';
        icon.classList.add('rotated');
    } else {
        content.style.display = 'none';
        icon.textContent = '▼';
        icon.classList.remove('rotated');
    }
}

function toggleEmailNotification() {
    const enabled = document.getElementById('email-notification-enabled').checked;
    const settings = document.getElementById('email-settings');
    
    if (enabled) {
        settings.style.display = 'block';
    } else {
        settings.style.display = 'none';
    }
}

function showEmailSetupGuide() {
    document.getElementById('email-setup-modal').style.display = 'block';
}

function closeEmailSetupGuide() {
    document.getElementById('email-setup-modal').style.display = 'none';
}

function saveEmailConfig() {
    const enabled = document.getElementById('email-notification-enabled').checked;
    const senderEmail = document.getElementById('sender-email').value.trim();
    const senderPassword = document.getElementById('sender-password').value.trim();
    const receiverEmail = document.getElementById('receiver-email').value.trim();
    const smtpServer = document.getElementById('smtp-server').value.trim();
    const smtpPort = parseInt(document.getElementById('smtp-port').value);
    
    if (enabled) {
        if (!senderEmail || !senderPassword || !receiverEmail) {
            showToast('请填写完整的邮件配置信息', 'error');
            return;
        }
        
        // 验证邮箱格式
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(senderEmail) || !emailRegex.test(receiverEmail)) {
            showToast('请输入有效的邮箱地址', 'error');
            return;
        }
        
        // 检查是否为QQ邮箱
        if (!senderEmail.includes('@qq.com')) {
            showToast('发送邮箱必须是QQ邮箱（@qq.com）', 'error');
            return;
        }
    }
    
    const emailConfig = {
        enabled: enabled,
        smtp_server: smtpServer,
        smtp_port: smtpPort,
        sender_email: senderEmail,
        sender_password: senderPassword,
        receiver_email: receiverEmail
    };
    
    fetch('/api/save_email_config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(emailConfig)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('邮件配置保存成功', 'success');
        } else {
            showToast('保存失败: ' + (data.error || '未知错误'), 'error');
        }
    })
    .catch(error => {
        console.error('保存邮件配置失败:', error);
        showToast('保存失败: ' + error.message, 'error');
    });
}

function testEmailNotification() {
    const enabled = document.getElementById('email-notification-enabled').checked;
    
    if (!enabled) {
        showToast('请先启用邮件提醒功能', 'warning');
        return;
    }
    
    const senderEmail = document.getElementById('sender-email').value.trim();
    const senderPassword = document.getElementById('sender-password').value.trim();
    const receiverEmail = document.getElementById('receiver-email').value.trim();
    
    if (!senderEmail || !senderPassword || !receiverEmail) {
        showToast('请先完整填写邮件配置信息', 'error');
        return;
    }
    
    showToast('正在发送测试邮件...', 'info');
    
    fetch('/api/test_email', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            sender_email: senderEmail,
            sender_password: senderPassword,
            receiver_email: receiverEmail
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('测试邮件发送成功！请检查您的邮箱', 'success');
        } else {
            showToast('测试邮件发送失败: ' + (data.error || '未知错误'), 'error');
        }
    })
    .catch(error => {
        console.error('发送测试邮件失败:', error);
        showToast('发送测试邮件失败: ' + error.message, 'error');
    });
}

function loadEmailConfig() {
    fetch('/api/get_email_config')
    .then(response => response.json())
    .then(data => {
        if (data.success && data.config) {
            const config = data.config;
            
            document.getElementById('email-notification-enabled').checked = config.enabled || false;
            document.getElementById('sender-email').value = config.sender_email || '';
            document.getElementById('sender-password').value = config.sender_password || '';
            document.getElementById('receiver-email').value = config.receiver_email || '';
            document.getElementById('smtp-server').value = config.smtp_server || 'smtp.qq.com';
            document.getElementById('smtp-port').value = config.smtp_port || 587;
            
            // 根据启用状态显示/隐藏设置区域
            toggleEmailNotification();
        }
    })
    .catch(error => {
        console.error('加载邮件配置失败:', error);
    });
}

// 在页面加载时调用邮件配置加载
// 已在上面的DOMContentLoaded中调用

// 清除所有数据相关函数
function confirmResetAllData() {
    // 显示确认模态框
    document.getElementById('reset-confirm-modal').style.display = 'block';
}

function closeResetConfirmModal() {
    document.getElementById('reset-confirm-modal').style.display = 'none';
}

function executeResetAllData() {
    // 关闭模态框
    closeResetConfirmModal();
    
    // 显示加载提示
    showToast('正在清除所有数据...', 'info');
    
    fetch('/api/reset_all_data', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('所有数据已清除，页面即将刷新...', 'success');
            
            // 2秒后刷新页面
            setTimeout(() => {
                window.location.reload();
            }, 2000);
        } else {
            showToast('清除数据失败: ' + (data.error || '未知错误'), 'error');
        }
    })
    .catch(error => {
        console.error('清除数据失败:', error);
        showToast('清除数据失败: ' + error.message, 'error');
    });
}

// 点击模态框外部关闭
window.addEventListener('click', function(event) {
    const resetModal = document.getElementById('reset-confirm-modal');
    if (event.target === resetModal) {
        closeResetConfirmModal();
    }
});

// ==================== 扫码登录相关函数 ====================

let qrcodePollingInterval = null;
let currentQRCodeKey = null;
let isQRCodeLoginSuccess = false; // 添加标志位，防止重复处理
let qrcodeLoginContext = 'single';
let reopenAddAccountAfterQRCode = false;

// 显示扫码登录
function showQRCodeLogin(context = 'single') {
    qrcodeLoginContext = context;
    document.getElementById('qrcode-login-modal').style.display = 'block';
    
    // 重置标志位和显示状态
    isQRCodeLoginSuccess = false;
    document.getElementById('qrcode-loading').style.display = 'block';
    document.getElementById('qrcode-display').style.display = 'none';
    document.getElementById('qrcode-error').style.display = 'none';
    document.getElementById('qrcode-success').style.display = 'none';
    
    // 生成二维码
    generateQRCode();
}

function showAddAccountQRCodeLogin() {
    const addAccountModal = document.getElementById('add-account-modal');
    if (addAccountModal) {
        // 临时隐藏添加账号弹窗，避免层级遮挡二维码弹窗
        addAccountModal.style.display = 'none';
        reopenAddAccountAfterQRCode = true;
    }
    showQRCodeLogin('add-account');
}

// 生成二维码
function generateQRCode() {
    fetch('/api/qrcode-login/generate')
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            currentQRCodeKey = data.qrcode_key;
            
            // 显示二维码
            document.getElementById('qrcode-loading').style.display = 'none';
            document.getElementById('qrcode-display').style.display = 'block';
            
            // 使用qrcodejs2库生成二维码（如果没有，使用简单的方式）
            const qrcodeContainer = document.getElementById('qrcode-image');
            qrcodeContainer.innerHTML = '';
            
            // 使用Google Chart API生成二维码图片
            const qrcodeUrl = `https://api.qrserver.com/v1/create-qr-code/?size=280x280&data=${encodeURIComponent(data.url)}`;
            const img = document.createElement('img');
            img.src = qrcodeUrl;
            img.style.width = '100%';
            img.style.border = '2px solid #e0e0e0';
            img.style.borderRadius = '8px';
            qrcodeContainer.appendChild(img);
            
            // 开始轮询状态
            startQRCodePolling();
        } else {
            showQRCodeError(data.error || '生成二维码失败');
        }
    })
    .catch(error => {
        console.error('生成二维码失败:', error);
        showQRCodeError('网络错误，请重试');
    });
}

// 开始轮询二维码状态
function startQRCodePolling() {
    // 清除之前的轮询
    if (qrcodePollingInterval) {
        clearInterval(qrcodePollingInterval);
    }
    
    // 重置成功标志
    isQRCodeLoginSuccess = false;
    
    // 每2秒轮询一次
    qrcodePollingInterval = setInterval(() => {
        pollQRCodeStatus();
    }, 2000);
    
    // 3分钟后自动停止轮询（二维码过期）
    setTimeout(() => {
        if (qrcodePollingInterval && !isQRCodeLoginSuccess) {
            clearInterval(qrcodePollingInterval);
            qrcodePollingInterval = null;
            
            // 检查是否还在等待扫码状态
            const displayElement = document.getElementById('qrcode-display');
            if (displayElement && displayElement.style.display !== 'none') {
                showQRCodeError('二维码已过期，请重新生成');
            }
        }
    }, 180000);
}

// 轮询二维码状态
function pollQRCodeStatus() {
    if (!currentQRCodeKey || isQRCodeLoginSuccess) return;
    
    fetch('/api/qrcode-login/poll', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            qrcode_key: currentQRCodeKey,
            auto_save: qrcodeLoginContext !== 'add-account'
        })
    })
    .then(response => response.json())
    .then(data => {
        console.log('扫码状态:', data); // 添加调试日志
        
        // 如果已经成功，不再处理后续响应
        if (isQRCodeLoginSuccess) {
            return;
        }
        
        if (data.success) {
            const status = data.status;
            const statusElement = document.getElementById('qrcode-status');
            
            if (status === 'waiting') {
                statusElement.innerHTML = '<p> 请使用哔哩哔哩APP扫描二维码</p>';
            } else if (status === 'scanned') {
                statusElement.innerHTML = '<p style="color: #00a1d6; font-weight: 600;"> 已扫码，请在APP中确认登录</p>';
            } else if (status === 'success') {
                // 登录成功 - 立即设置标志位并停止轮询
                isQRCodeLoginSuccess = true;
                clearInterval(qrcodePollingInterval);
                qrcodePollingInterval = null;
                
                // 显示成功状态
                document.getElementById('qrcode-display').style.display = 'none';
                document.getElementById('qrcode-success').style.display = 'block';
                
                const sessdata = data.sessdata || '';
                const biliJct = data.bili_jct || '';
                if (qrcodeLoginContext === 'add-account') {
                    const sessInput = document.getElementById('account-sessdata');
                    const jctInput = document.getElementById('account-bili-jct');
                    if (sessInput && jctInput && sessdata && biliJct) {
                        sessInput.value = sessdata;
                        jctInput.value = biliJct;
                    }
                    showToast('扫码成功，已填充账号Cookie', 'success');
                    addLog('账号扫码成功，已填充SESSDATA和bili_jct', 'success');
                } else {
                    showToast('扫码登录成功！', 'success');
                    addLog('扫码登录成功，配置已自动保存', 'success');
                }
                
                // 3秒后关闭模态框并刷新配置
                setTimeout(() => {
                    const loginContext = qrcodeLoginContext;
                    closeQRCodeLoginModal();
                    if (loginContext !== 'add-account') {
                        loadConfig();
                    }
                }, 3000);
            }
        } else {
            // 只有在未成功的情况下才处理错误
            if (!isQRCodeLoginSuccess) {
                if (data.status === 'expired') {
                    clearInterval(qrcodePollingInterval);
                    qrcodePollingInterval = null;
                    showQRCodeError('二维码已过期，请重新生成');
                } else if (data.status === 'error') {
                    clearInterval(qrcodePollingInterval);
                    qrcodePollingInterval = null;
                    showQRCodeError(data.message || '登录失败，请重试');
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
function showQRCodeError(message) {
    // 如果已经成功，不显示错误
    if (isQRCodeLoginSuccess) {
        return;
    }
    
    document.getElementById('qrcode-loading').style.display = 'none';
    document.getElementById('qrcode-display').style.display = 'none';
    document.getElementById('qrcode-error').style.display = 'block';
    document.getElementById('qrcode-error-message').textContent = message;
    
    // 清除轮询
    if (qrcodePollingInterval) {
        clearInterval(qrcodePollingInterval);
        qrcodePollingInterval = null;
    }
}

// 重试生成二维码
function retryQRCodeLogin() {
    isQRCodeLoginSuccess = false;
    document.getElementById('qrcode-error').style.display = 'none';
    document.getElementById('qrcode-loading').style.display = 'block';
    generateQRCode();
}

// 关闭扫码登录模态框
function closeQRCodeLoginModal() {
    const shouldReopenAddAccount = (qrcodeLoginContext === 'add-account' && reopenAddAccountAfterQRCode);
    document.getElementById('qrcode-login-modal').style.display = 'none';
    
    // 清除轮询
    if (qrcodePollingInterval) {
        clearInterval(qrcodePollingInterval);
        qrcodePollingInterval = null;
    }
    
    currentQRCodeKey = null;
    isQRCodeLoginSuccess = false;
    qrcodeLoginContext = 'single';
    reopenAddAccountAfterQRCode = false;

    if (shouldReopenAddAccount) {
        openAddAccountModal(true);
    }
}

// 点击模态框外部关闭
window.addEventListener('click', function(event) {
    const qrcodeModal = document.getElementById('qrcode-login-modal');
    if (event.target === qrcodeModal) {
        closeQRCodeLoginModal();
    }
});
