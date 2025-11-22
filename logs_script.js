// 系统日志页面 JavaScript

let logs = [];
let filteredLogs = [];
let currentFilter = 'all';
let currentLogType = 'all'; // 新增：日志类型过滤 (all/message/comment)
let autoRefreshInterval = null;
let maxLogEntries = 200;
let isLoading = true; // 添加加载状态标记

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM加载完成，开始初始化日志页面');
    
    // 立即初始化页面UI
    initializePage();
    setupEventListeners();
    
    // 异步加载数据，不阻塞页面显示
    setTimeout(() => {
        console.log('尝试加载真实日志数据');
        updateStatus();
        loadRealLogsIfAvailable(); // 静默尝试加载真实数据
        startAutoRefresh();
    }, 100); // 增加延迟确保DOM完全准备好
});

// 初始化页面
function initializePage() {
    // 显示初始状态，不依赖API
    showInitialState();
    updateLogStats();
    // 初始化空的日志数组
    logs = [];
    filteredLogs = [];
    
    // 立即生成一些模拟数据作为初始显示，确保页面不空白
    console.log('初始化页面，生成初始模拟数据');
    generateMockLogs();
}

// 显示初始状态
function showInitialState() {
    const statusElement = document.getElementById('status');
    const statusText = document.getElementById('status-text');
    statusElement.classList.remove('active');
    statusText.textContent = '正在连接...';
}

// 设置事件监听器
function setupEventListeners() {
    // 过滤按钮
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            setLogFilter(this.dataset.level);
        });
    });

    // 日志类型过滤按钮（新增）
    const logTypeButtons = document.querySelectorAll('.log-type-filter');
    if (logTypeButtons.length > 0) {
        logTypeButtons.forEach(btn => {
            btn.addEventListener('click', function() {
                setLogTypeFilter(this.dataset.type);
            });
        });
    }

    // 自动刷新复选框
    const autoRefreshCheckbox = document.getElementById('autoRefresh');
    if (autoRefreshCheckbox) {
        autoRefreshCheckbox.addEventListener('change', function() {
            if (this.checked) {
                startAutoRefresh();
            } else {
                stopAutoRefresh();
            }
        });
    }

    // 最大显示条数选择
    const maxLogEntriesSelect = document.getElementById('maxLogEntries');
    if (maxLogEntriesSelect) {
        maxLogEntriesSelect.addEventListener('change', function() {
            maxLogEntries = parseInt(this.value);
            applyLogFilter();
        });
    }

    // 搜索框
    const logSearchInput = document.getElementById('logSearch');
    if (logSearchInput) {
        logSearchInput.addEventListener('input', function() {
            applyLogFilter();
        });
    }

    // 键盘快捷键
    document.addEventListener('keydown', function(e) {
        if (e.ctrlKey || e.metaKey) {
            switch(e.key) {
                case 'f':
                    e.preventDefault();
                    const searchInput = document.getElementById('logSearch');
                    if (searchInput) {
                        searchInput.focus();
                    }
                    break;
                case 'r':
                    e.preventDefault();
                    refreshLogs();
                    break;
            }
        }
    });
}

// 页面跳转函数
function goToMessageMode() {
    window.location.href = 'index.html';
}

function goToCommentMode() {
    window.location.href = 'comment';
}

// 检查更新
function checkUpdate() {
    window.open('https://github.com/Chiyang001/BiliGo/releases/', '_blank');
}

// 打开使用教程
function openTutorial() {
    window.open('https://www.bilibili.com/video/BV1F8e4z7Eae/', '_blank');
}

// 更新系统状态
function updateStatus() {
    // 设置超时控制
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000); // 3秒超时
    
    fetch('/api/status', { 
        signal: controller.signal,
        headers: {
            'Cache-Control': 'no-cache'
        }
    })
        .then(response => {
            clearTimeout(timeoutId);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            const statusElement = document.getElementById('status');
            const statusText = document.getElementById('status-text');
            
            if (statusElement && statusText) {
                // 显示组合状态：私信监控状态 + 评论监控状态
                const messageStatus = data.message_monitoring || data.monitoring; // 兼容性
                const commentStatus = data.comment_monitoring;
                
                if (messageStatus || commentStatus) {
                    statusElement.classList.add('active');
                    
                    let statusMsg = '系统运行中';
                    if (messageStatus && commentStatus) {
                        statusMsg = '私信&评论监控中';
                    } else if (messageStatus) {
                        statusMsg = '私信监控中';
                    } else if (commentStatus) {
                        statusMsg = '评论监控中';
                    }
                    
                    statusText.textContent = statusMsg;
                } else {
                    statusElement.classList.remove('active');
                    statusText.textContent = '系统已停止';
                }
            }
        })
        .catch(error => {
            clearTimeout(timeoutId);
            console.warn('获取状态失败:', error.message);
            const statusElement = document.getElementById('status');
            const statusText = document.getElementById('status-text');
            
            if (statusElement && statusText) {
                statusElement.classList.remove('active');
                
                if (error.name === 'AbortError') {
                    statusText.textContent = '连接超时';
                } else {
                    statusText.textContent = '离线模式';
                }
            }
        });
}

// 加载日志
function loadLogs(isRefresh = false) {
    console.log('开始加载日志，isRefresh:', isRefresh, 'logType:', currentLogType);
    
    // 设置超时控制，缩短超时时间以便快速切换到模拟数据
    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
        console.log('API请求超时，中止请求');
        controller.abort();
    }, 2000); // 缩短到2秒超时
    
    // 构建API URL，支持日志类型过滤
    let apiUrl = '/api/logs';
    if (currentLogType !== 'all') {
        apiUrl += `?type=${currentLogType}`;
    }
    
    fetch(apiUrl, { 
        signal: controller.signal,
        headers: {
            'Cache-Control': 'no-cache'
        }
    })
        .then(response => {
            clearTimeout(timeoutId);
            console.log('API响应成功，状态:', response.status);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('API数据加载成功，日志条数:', data.logs ? data.logs.length : 0);
            console.log('API返回的日志类型:', data.type || 'unknown');
            logs = data.logs || [];
            isLoading = false; // 标记加载完成
            
            // 如果API返回空数据且是首次加载，使用模拟数据
            if (logs.length === 0 && !isRefresh) {
                console.log('API返回空数据，使用模拟数据');
                generateMockLogs();
                showToast('暂无真实日志数据，显示模拟数据', 'info');
                return; // 直接返回，不需要再次处理
            }
            
            applyLogFilter();
            updateLogStats();
            updateLastUpdateTime();
            
            // 如果是手动刷新，显示成功提示
            if (isRefresh) {
                const logTypeText = currentLogType === 'all' ? '全部' : 
                                  currentLogType === 'message' ? '私信' : '评论';
                showToast(`${logTypeText}日志刷新成功`, 'success');
            }
        })
        .catch(error => {
            clearTimeout(timeoutId);
            console.warn('加载日志失败:', error.message);
            isLoading = false; // 标记加载完成（即使失败）
            
            // 如果是首次加载失败或没有数据，使用模拟数据
            if (logs.length === 0) {
                console.log('API不可用或无数据，切换到模拟数据模式');
                generateMockLogs();
                if (!isRefresh) {
                    showToast('API不可用，显示模拟数据', 'warning');
                }
            } else if (isRefresh) {
                // 只有在手动刷新时才显示刷新失败提示
                const logTypeText = currentLogType === 'all' ? '全部' : 
                                  currentLogType === 'message' ? '私信' : '评论';
                showToast(`刷新${logTypeText}日志失败，显示缓存数据`, 'warning');
            }
            // 自动刷新失败时不显示任何提示，静默处理
        });
}

// 刷新日志
function refreshLogs() {
    showToast('正在刷新日志...', 'info');
    isLoading = true; // 重新设置加载状态
    showLoadingState(); // 显示加载状态
    loadLogs(true); // 传入true表示这是手动刷新
}

// 静默尝试加载真实日志数据（不影响现有显示）
function loadRealLogsIfAvailable() {
    console.log('静默尝试加载真实日志数据...');
    
    // 设置超时控制
    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
        console.log('真实数据加载超时，保持模拟数据');
        controller.abort();
    }, 5000); // 5秒超时
    
    // 构建 API URL
    let apiUrl = '/api/logs';
    if (currentLogType !== 'all') {
        apiUrl += `?type=${currentLogType}`;
    }
    
    fetch(apiUrl, { 
        signal: controller.signal,
        headers: {
            'Cache-Control': 'no-cache',
            'Accept': 'application/json'
        }
    })
        .then(response => {
            clearTimeout(timeoutId);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('真实数据加载成功，数量:', data.logs ? data.logs.length : 0);
            
            // 如果有真实数据，替换模拟数据
            if (data.logs && data.logs.length > 0) {
                logs = Array.isArray(data.logs) ? data.logs : [];
                applyLogFilter();
                updateLogStats();
                updateLastUpdateTime();
                console.log('已替换为真实日志数据');
                showToast('已加载真实日志数据', 'success');
            } else {
                console.log('服务器无日志数据，保持模拟数据');
            }
        })
        .catch(error => {
            clearTimeout(timeoutId);
            console.log('真实数据加载失败，保持模拟数据:', error.message);
            // 不显示错误提示，静默处理
        });
}

// 设置日志过滤器
function setLogFilter(level) {
    currentFilter = level;
    
    // 更新按钮状态
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`[data-level="${level}"]`).classList.add('active');
    
    applyLogFilter();
}

// 设置日志类型过滤器（新增）
function setLogTypeFilter(type) {
    currentLogType = type;
    
    // 更新按钮状态
    document.querySelectorAll('.log-type-filter').forEach(btn => {
        btn.classList.remove('active');
    });
    
    const activeBtn = document.querySelector(`[data-type="${type}"]`);
    if (activeBtn) {
        activeBtn.classList.add('active');
    }
    
    // 重新加载对应类型的日志
    loadLogs(false);
}

// 应用日志过滤
function applyLogFilter() {
    const searchTerm = document.getElementById('logSearch').value.toLowerCase();
    
    filteredLogs = logs.filter(log => {
        // 级别过滤
        if (currentFilter !== 'all' && log.level !== currentFilter) {
            return false;
        }
        
        // 搜索过滤
        if (searchTerm && !log.message.toLowerCase().includes(searchTerm)) {
            return false;
        }
        
        return true;
    });
    
    // 限制显示条数
    if (maxLogEntries > 0 && filteredLogs.length > maxLogEntries) {
        filteredLogs = filteredLogs.slice(-maxLogEntries);
    }
    
    updateLogDisplay();
    updateLogCounts();
}

// 更新日志显示
function updateLogDisplay() {
    const logContainer = document.getElementById('log');
    
    if (!logContainer) {
        console.error('日志容器元素未找到');
        return;
    }
    
    console.log('更新日志显示 - 总日志数:', logs.length, '过滤后日志数:', filteredLogs.length);
    
    if (filteredLogs.length === 0) {
        if (logs.length === 0) {
            if (isLoading) {
                // 正在加载状态
                logContainer.innerHTML = `
                    <div class="log-placeholder">
                        <i class="fas fa-spinner fa-spin"></i>
                        <p>正在加载日志数据...</p>
                        <small>请稍候，正在连接服务器</small>
                    </div>
                `;
            } else {
                // 加载完成但无数据 - 这个情况不应该出现，因为我们已经有模拟数据保障
                console.warn('异常情况：加载完成但无日志数据，强制生成模拟数据');
                generateMockLogs();
                return; // 重新生成后直接返回
            }
        } else {
            logContainer.innerHTML = `
                <div class="log-placeholder">
                    <i class="fas fa-search"></i>
                    <p>没有匹配的日志</p>
                    <small>请尝试调整过滤条件或搜索关键词</small>
                </div>
            `;
        }
        return;
    }
    
    console.log('生成日志HTML，条目数:', filteredLogs.length);
    
    const logHtml = filteredLogs.map(log => {
        const timestamp = new Date(log.timestamp).toLocaleString('zh-CN');
        const levelClass = `log-${log.level}`;
        const levelText = getLevelText(log.level);
        
        // 添加系统标识
        const systemPrefix = log.system === 'comment' ? '[评论]' : 
                           log.system === 'message' ? '[私信]' : '';
        
        return `
            <div class="log-entry ${log.system ? `log-system-${log.system}` : ''}">
                <span class="log-timestamp">${timestamp}</span>
                <span class="log-level ${levelClass}">[${levelText}]</span>
                ${systemPrefix ? `<span class="log-system">${systemPrefix}</span>` : ''}
                <span class="log-message">${escapeHtml(log.message)}</span>
            </div>
        `;
    }).join('');
    
    console.log('设置日志容器HTML内容');
    logContainer.innerHTML = logHtml;
    
    // 自动滚动到底部
    setTimeout(() => {
        if (logContainer) {
            logContainer.scrollTop = logContainer.scrollHeight;
        }
    }, 100);
}

// 显示加载状态
function showLoadingState() {
    const logContainer = document.getElementById('log');
    logContainer.innerHTML = `
        <div class="log-placeholder">
            <i class="fas fa-spinner fa-spin"></i>
            <p>正在加载日志数据...</p>
            <small>请稍候，正在连接服务器</small>
        </div>
    `;
}

// 更新日志统计
function updateLogStats() {
    const stats = {
        info: 0,
        success: 0,
        warning: 0,
        error: 0
    };
    
    logs.forEach(log => {
        if (stats.hasOwnProperty(log.level)) {
            stats[log.level]++;
        }
    });
    
    document.getElementById('infoCount').textContent = stats.info;
    document.getElementById('successCount').textContent = stats.success;
    document.getElementById('warningCount').textContent = stats.warning;
    document.getElementById('errorCount').textContent = stats.error;
}

// 更新日志计数
function updateLogCounts() {
    document.getElementById('totalLogCount').textContent = logs.length;
    document.getElementById('displayedCount').textContent = filteredLogs.length;
    document.getElementById('totalCount').textContent = logs.length;
}

// 更新最后更新时间
function updateLastUpdateTime() {
    const now = new Date().toLocaleString('zh-CN');
    document.getElementById('lastUpdate').textContent = now;
}

// 获取级别文本
function getLevelText(level) {
    const levelMap = {
        'info': '信息',
        'success': '成功',
        'warning': '警告',
        'error': '错误'
    };
    return levelMap[level] || level.toUpperCase();
}

// 清空日志
function clearLogs() {
    const logTypeText = currentLogType === 'all' ? '所有' : 
                       currentLogType === 'message' ? '私信' : '评论';
    
    if (confirm(`确定要清空${logTypeText}日志吗？此操作不可撤销。`)) {
        let apiUrl = '/api/logs';
        if (currentLogType !== 'all') {
            apiUrl += `?type=${currentLogType}`;
        }
        
        fetch(apiUrl, {
            method: 'DELETE'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                logs = [];
                filteredLogs = [];
                updateLogDisplay();
                updateLogStats();
                updateLogCounts();
                showToast(data.message || `${logTypeText}日志已清空`, 'success');
            } else {
                showToast(`清空${logTypeText}日志失败`, 'error');
            }
        })
        .catch(error => {
            console.error(`清空${logTypeText}日志失败:`, error);
            showToast(`清空${logTypeText}日志失败`, 'error');
        });
    }
}


    


// 清空搜索
function clearSearch() {
    document.getElementById('logSearch').value = '';
    applyLogFilter();
}

// 滚动到底部
function scrollToBottom() {
    const logContainer = document.getElementById('log');
    logContainer.scrollTop = logContainer.scrollHeight;
}

// 开始自动刷新
function startAutoRefresh() {
    stopAutoRefresh();
    
    // 检查自动刷新复选框状态
    const autoRefreshCheckbox = document.getElementById('autoRefresh');
    if (!autoRefreshCheckbox || !autoRefreshCheckbox.checked) {
        return;
    }
    
    autoRefreshInterval = setInterval(() => {
        // 只有在复选框仍然选中时才刷新
        if (autoRefreshCheckbox.checked) {
            loadLogs(false); // 传入false表示这是自动刷新，不显示提示
            updateStatus();
        } else {
            stopAutoRefresh();
        }
    }, 5000); // 每5秒刷新一次
}

// 停止自动刷新
function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }
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
    
    const iconMap = {
        'success': 'fas fa-check-circle',
        'error': 'fas fa-times-circle',
        'warning': 'fas fa-exclamation-triangle',
        'info': 'fas fa-info-circle'
    };
    
    toast.innerHTML = `
        <i class="toast-icon ${iconMap[type]}"></i>
        <span class="toast-message">${message}</span>
    `;
    
    toastContainer.appendChild(toast);
    
    // 自动移除
    setTimeout(() => {
        if (toast.parentNode) {
            toast.parentNode.removeChild(toast);
        }
    }, 4000);
}

// HTML转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 模拟日志数据（用于演示）
function generateMockLogs() {
    console.log('生成模拟日志数据，当前日志类型:', currentLogType);
    const now = Date.now();
    const mockLogs = [
        { timestamp: new Date(now).toISOString(), level: 'info', message: '系统日志页面已加载（模拟模式）', system: 'message' },
        { timestamp: new Date(now - 30000).toISOString(), level: 'success', message: '成功发送私信回复：感谢您的关注！', system: 'message' },
        { timestamp: new Date(now - 90000).toISOString(), level: 'info', message: '检测到新的私信消息', system: 'message' },
        { timestamp: new Date(now - 150000).toISOString(), level: 'warning', message: '回复频率过快，等待中...', system: 'message' },
        { timestamp: new Date(now - 210000).toISOString(), level: 'success', message: '成功发送评论回复：谢谢支持！', system: 'comment' },
        { timestamp: new Date(now - 270000).toISOString(), level: 'error', message: '网络连接失败，正在重试...', system: 'comment' },
        { timestamp: new Date(now - 330000).toISOString(), level: 'info', message: '开始监控评论消息', system: 'comment' },
        { timestamp: new Date(now - 390000).toISOString(), level: 'success', message: '规则匹配成功，准备回复', system: 'message' },
        { timestamp: new Date(now - 450000).toISOString(), level: 'info', message: '系统配置已加载', system: 'message' },
        { timestamp: new Date(now - 510000).toISOString(), level: 'warning', message: '检测到重复消息，跳过处理', system: 'comment' }
    ];
    
    // 根据当前日志类型过滤模拟数据
    if (currentLogType === 'message') {
        logs = mockLogs.filter(log => log.system === 'message');
        console.log('过滤私信日志，条数:', logs.length);
    } else if (currentLogType === 'comment') {
        logs = mockLogs.filter(log => log.system === 'comment');
        console.log('过滤评论日志，条数:', logs.length);
    } else {
        logs = mockLogs;
        console.log('使用全部模拟日志，条数:', logs.length);
    }
    
    // 确保至少有一条日志
    if (logs.length === 0) {
        const logTypeText = currentLogType === 'comment' ? '评论' : 
                           currentLogType === 'message' ? '私信' : '系统';
        logs = [{ 
            timestamp: new Date(now).toISOString(), 
            level: 'info', 
            message: `${logTypeText}系统已启动，等待日志数据...`, 
            system: currentLogType === 'comment' ? 'comment' : 
                   currentLogType === 'message' ? 'message' : 'message'
        }];
        console.log('添加默认日志，确保有内容显示');
    }
    
    isLoading = false; // 标记加载完成
    console.log('模拟日志数据已设置，总条数:', logs.length);
    applyLogFilter();
    updateLogStats();
    updateLastUpdateTime();
    console.log('模拟日志数据处理完成，过滤后条数:', filteredLogs.length);
    
    // 确保显示更新
    setTimeout(() => {
        updateLogDisplay();
        console.log('强制更新显示完成');
    }, 100);
}

// 页面卸载时清理
window.addEventListener('beforeunload', function() {
    stopAutoRefresh();
});