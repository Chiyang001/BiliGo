// 系统日志页面 JavaScript

let logs = [];
let filteredLogs = [];
let currentFilter = 'all';
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
        console.log('开始加载日志数据');
        showLoadingState();
        loadLogs(false); // 初始加载，不显示刷新提示
        updateStatus();
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

    // 自动刷新复选框
    document.getElementById('autoRefresh').addEventListener('change', function() {
        if (this.checked) {
            startAutoRefresh();
        } else {
            stopAutoRefresh();
        }
    });

    // 最大显示条数选择
    document.getElementById('maxLogEntries').addEventListener('change', function() {
        maxLogEntries = parseInt(this.value);
        applyLogFilter();
    });

    // 搜索框
    document.getElementById('logSearch').addEventListener('input', function() {
        applyLogFilter();
    });

    // 键盘快捷键
    document.addEventListener('keydown', function(e) {
        if (e.ctrlKey || e.metaKey) {
            switch(e.key) {
                case 'f':
                    e.preventDefault();
                    document.getElementById('logSearch').focus();
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
            
            if (data.monitoring) {
                statusElement.classList.add('active');
                statusText.textContent = '系统运行中';
            } else {
                statusElement.classList.remove('active');
                statusText.textContent = '系统已停止';
            }
        })
        .catch(error => {
            clearTimeout(timeoutId);
            console.warn('获取状态失败:', error.message);
            const statusElement = document.getElementById('status');
            const statusText = document.getElementById('status-text');
            statusElement.classList.remove('active');
            
            if (error.name === 'AbortError') {
                statusText.textContent = '连接超时';
            } else {
                statusText.textContent = '离线模式';
            }
        });
}

// 加载日志
function loadLogs(isRefresh = false) {
    console.log('开始加载日志，isRefresh:', isRefresh);
    
    // 设置超时控制，缩短超时时间以便快速切换到模拟数据
    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
        console.log('API请求超时，中止请求');
        controller.abort();
    }, 2000); // 缩短到2秒超时
    
    fetch('/api/logs', { 
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
            logs = data.logs || [];
            isLoading = false; // 标记加载完成
            applyLogFilter();
            updateLogStats();
            updateLastUpdateTime();
            
            // 如果是手动刷新，显示成功提示
            if (isRefresh) {
                showToast('日志刷新成功', 'success');
            }
        })
        .catch(error => {
            clearTimeout(timeoutId);
            console.warn('加载日志失败:', error.message);
            isLoading = false; // 标记加载完成（即使失败）
            
            // 如果是首次加载失败，使用模拟数据
            if (logs.length === 0) {
                console.log('API不可用，切换到模拟数据模式');
                generateMockLogs();
                if (!isRefresh) {
                    showToast('API不可用，显示模拟数据', 'warning');
                }
            } else if (isRefresh) {
                // 只有在手动刷新时才显示刷新失败提示
                showToast('刷新日志失败，显示缓存数据', 'warning');
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
                // 加载完成但无数据
                logContainer.innerHTML = `
                    <div class="log-placeholder" id="log-placeholder">
                        <i class="fas fa-file-alt"></i>
                        <p>暂无日志数据</p>
                        <small>系统运行时会在此显示相关日志信息</small>
                    </div>
                `;
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
        
        return `
            <div class="log-entry">
                <span class="log-timestamp">${timestamp}</span>
                <span class="log-level ${levelClass}">[${levelText}]</span>
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
    if (confirm('确定要清空所有日志吗？此操作不可撤销。')) {
        fetch('/api/logs', {
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
                showToast('日志已清空', 'success');
            } else {
                showToast('清空日志失败', 'error');
            }
        })
        .catch(error => {
            console.error('清空日志失败:', error);
            showToast('清空日志失败', 'error');
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
    console.log('生成模拟日志数据...');
    const now = Date.now();
    const mockLogs = [
        { timestamp: new Date(now).toISOString(), level: 'info', message: '日志系统已启动（模拟模式）' },
        { timestamp: new Date(now - 30000).toISOString(), level: 'success', message: '成功发送私信回复：感谢您的关注！' },
        { timestamp: new Date(now - 90000).toISOString(), level: 'info', message: '检测到新的私信消息' },
        { timestamp: new Date(now - 150000).toISOString(), level: 'warning', message: '回复频率过快，等待中...' },
        { timestamp: new Date(now - 210000).toISOString(), level: 'success', message: '成功发送评论回复：谢谢支持！' },
        { timestamp: new Date(now - 270000).toISOString(), level: 'error', message: '网络连接失败，正在重试...' },
        { timestamp: new Date(now - 330000).toISOString(), level: 'info', message: '开始监控评论消息' },
        { timestamp: new Date(now - 390000).toISOString(), level: 'success', message: '规则匹配成功，准备回复' },
        { timestamp: new Date(now - 450000).toISOString(), level: 'info', message: '系统配置已加载' },
        { timestamp: new Date(now - 510000).toISOString(), level: 'warning', message: '检测到重复消息，跳过处理' }
    ];
    
    logs = mockLogs;
    isLoading = false; // 标记加载完成
    console.log('模拟日志数据已设置，条数:', logs.length);
    applyLogFilter();
    updateLogStats();
    updateLastUpdateTime();
    console.log('模拟日志数据处理完成，过滤后条数:', filteredLogs.length);
}

// 页面卸载时清理
window.addEventListener('beforeunload', function() {
    stopAutoRefresh();
});