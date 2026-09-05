let douyinRules = [];
let isDouyinMonitoring = false;
let douyinStatusPollMs = 3000;
let douyinStatusPollTimer = null;
let loginPollTimer = null;
let loginSuccessNotified = false;
let currentDouyinPage = 1;
const douyinRulesPerPage = 5;
const DOUYIN_DEFAULT_AVATAR = 'tik-tok.png';
const DOUYIN_MONITOR_START_LABEL = '开始监控';
const DOUYIN_MONITOR_STARTING_LABEL = '正在启动中，请稍后';

document.addEventListener('DOMContentLoaded', () => {
    loadDouyinConfig();
    loadPlatformEmailConfig();
    loadDouyinRules();
    refreshLoginStatus(false);
    checkDouyinStatus();
    loadDouyinLogs();
    fetch('/api/douyin-login/status?verify=1').then(() => refreshLoginStatus(false));
    scheduleDouyinStatusPoll();
    setInterval(loadDouyinLogs, 4000);
});

async function loadPlatformEmailConfig() {
    try {
        const data = await (await fetch('/api/platform-email-config/douyin')).json();
        const cfg = data.config || {};
        const enabled = document.getElementById('platform-email-enabled');
        const receiver = document.getElementById('platform-email-receiver');
        if (enabled) enabled.checked = !!cfg.enabled;
        if (receiver) receiver.value = cfg.receiver_email || '';
    } catch (error) { console.warn('加载抖音邮件提醒配置失败', error); }
}

async function savePlatformEmailConfig() {
    const enabled = !!document.getElementById('platform-email-enabled')?.checked;
    const receiver_email = document.getElementById('platform-email-receiver')?.value.trim() || '';
    const response = await fetch('/api/platform-email-config/douyin', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({enabled, receiver_email})
    });
    const data = await response.json();
    showToast(data.success ? '抖音异常邮件提醒设置已保存' : (data.error || '保存失败'), data.success ? 'success' : 'error');
}

function scheduleDouyinStatusPoll() {
    if (douyinStatusPollTimer) {
        clearInterval(douyinStatusPollTimer);
    }
    douyinStatusPollTimer = setInterval(checkDouyinStatus, douyinStatusPollMs);
}

function applyDouyinMonitorButtonState(startBtn, data) {
    if (data.monitor_starting) {
        setMonitorStartButtonLoading(startBtn, true, DOUYIN_MONITOR_START_LABEL, DOUYIN_MONITOR_STARTING_LABEL);
        return;
    }
    setMonitorStartButtonLoading(startBtn, false, DOUYIN_MONITOR_START_LABEL);
    startBtn.disabled = !!(data.monitoring || !data.logged_in || data.session_expired);
}

function setMonitorStartButtonLoading(startBtn, loading, idleLabel, startingLabel = '正在启动中，请稍后') {
    if (loading) {
        startBtn.disabled = true;
        startBtn.classList.add('is-loading');
        // 状态轮询期间保持同一个 spinner DOM，避免每次刷新都重启动画而产生顿挫。
        let spinner = startBtn.querySelector('.btn-spinner');
        let label = startBtn.querySelector('.btn-label');
        if (!spinner || !label) {
            spinner = document.createElement('span');
            spinner.className = 'btn-spinner';
            spinner.setAttribute('aria-hidden', 'true');
            label = document.createElement('span');
            label.className = 'btn-label';
            startBtn.replaceChildren(spinner, label);
        }
        if (label.textContent !== startingLabel) label.textContent = startingLabel;
        return;
    }
    const wasLoading = startBtn.classList.contains('is-loading');
    startBtn.classList.remove('is-loading');
    if (wasLoading || startBtn.textContent !== idleLabel) startBtn.textContent = idleLabel;
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

document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        const resetModal = document.getElementById('reset-confirm-modal');
        if (resetModal && resetModal.style.display === 'block') {
            closeResetConfirmModal();
            return;
        }
        const importModal = document.getElementById('douyin-import-modal');
        if (importModal && importModal.style.display === 'block') {
            closeDouyinImportModal();
            return;
        }
        const switcher = document.getElementById('platform-switcher');
        if (switcher) switcher.classList.remove('open');
    }
});

function checkUpdate() {
    window.open('https://github.com/Chiyang001/BiliGo/releases/', '_blank');
}

function openDocsPage() {
    window.location.href = '/docs.html?from=douyin#douyin-mode';
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="toast-icon"></span>
        <div class="toast-message">${escapeHtml(message)}</div>
    `;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
}

function formatLoginTime(raw) {
    if (!raw) return '-';
    try {
        const d = new Date(raw);
        if (Number.isNaN(d.getTime())) return raw;
        return d.toLocaleString('zh-CN', { hour12: false });
    } catch (e) {
        return raw;
    }
}

function stopLoginPoll() {
    if (loginPollTimer) {
        clearInterval(loginPollTimer);
        loginPollTimer = null;
    }
}

function toggleDouyinTimingConfig() {
    const content = document.getElementById('douyin-timing-config-content');
    const icon = document.getElementById('douyin-timing-toggle-icon');
    if (!content || !icon) return;

    if (content.style.display === 'none' || content.style.display === '') {
        content.style.display = 'block';
        icon.textContent = '▲';
        icon.classList.add('rotated');
        localStorage.setItem('douyin-timing-config-expanded', 'true');
    } else {
        content.style.display = 'none';
        icon.textContent = '▼';
        icon.classList.remove('rotated');
        localStorage.setItem('douyin-timing-config-expanded', 'false');
    }
}

function restoreDouyinTimingConfigState() {
    const isExpanded = localStorage.getItem('douyin-timing-config-expanded') === 'true';
    const content = document.getElementById('douyin-timing-config-content');
    const icon = document.getElementById('douyin-timing-toggle-icon');
    if (!content || !icon) return;

    if (isExpanded) {
        content.style.display = 'block';
        icon.textContent = '▲';
        icon.classList.add('rotated');
    } else {
        content.style.display = 'none';
        icon.textContent = '▼';
        icon.classList.remove('rotated');
    }
}

function collectDouyinTimingConfig() {
    return {
        message_check_interval: parseFloat(document.getElementById('message-check-interval').value),
        send_delay_interval: parseFloat(document.getElementById('send-delay-interval').value),
    };
}

function collectDouyinMessageConfig() {
    const unlimitedReplies = document.getElementById('unlimited-replies-per-user').checked;
    const maxReplies = parseInt(document.getElementById('max-replies-per-user').value, 10);
    return {
        max_replies_per_user: Number.isInteger(maxReplies) && maxReplies >= 1 ? maxReplies : 3,
        unlimited_replies_per_user: unlimitedReplies,
        only_reply_new_messages: document.getElementById('only-reply-new-messages').checked,
    };
}

function collectDouyinDefaultReplyConfig() {
    return {
        default_reply_enabled: document.getElementById('default-reply-enabled').checked,
        default_reply_message: document.getElementById('default-reply-message').value,
        default_reply_type: 'text',
        default_reply_image: '',
    };
}

function collectDouyinConfigFields() {
    return {
        ...collectDouyinTimingConfig(),
        ...collectDouyinMessageConfig(),
        ...collectDouyinDefaultReplyConfig(),
    };
}

async function postDouyinConfig(payload, silent = false, successMessage = '配置已保存') {
    try {
        const res = await fetch('/api/douyin-config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (data.success === false) {
            // Starting monitoring re-submits the whole form. AI mode intentionally
            // rejects traditional reply fields, but this must not block startup.
            if (silent && res.status === 409 && String(data.error || '').includes('AI')) return true;
            showToast(data.error || '保存失败', 'error');
            return false;
        }
        if (!silent) showToast(successMessage, 'success');
        return true;
    } catch (e) {
        showToast('保存配置失败', 'error');
        return false;
    }
}

async function loadDouyinConfig() {
    try {
        const res = await fetch('/api/douyin-config');
        const cfg = await res.json();
        document.getElementById('message-check-interval').value = cfg.message_check_interval ?? 0.5;
        document.getElementById('send-delay-interval').value = cfg.send_delay_interval ?? 0.5;
        document.getElementById('max-replies-per-user').value = cfg.max_replies_per_user ?? 3;
        document.getElementById('unlimited-replies-per-user').checked = !!cfg.unlimited_replies_per_user;
        updateDouyinReplyLimitState();
        document.getElementById('only-reply-new-messages').checked = cfg.only_reply_new_messages !== false;
        document.getElementById('default-reply-enabled').checked = !!cfg.default_reply_enabled;
        document.getElementById('default-reply-message').value = cfg.default_reply_message || '';
        restoreDouyinTimingConfigState();
        updateAccountUI(cfg.account || {}, cfg.logged_in, cfg.login_time, cfg.session_expired);
    } catch (e) {
        showToast('加载配置失败', 'error');
    }
}

async function saveDouyinTimingConfig() {
    const timing = collectDouyinTimingConfig();
    if (Number.isNaN(timing.message_check_interval) || timing.message_check_interval < 0.5 || timing.message_check_interval > 60) {
        showToast('消息监测间隔必须在 0.5-60 秒之间', 'error');
        return false;
    }
    if (Number.isNaN(timing.send_delay_interval) || timing.send_delay_interval < 0.5 || timing.send_delay_interval > 30) {
        showToast('发送等待间隔必须在 0.5-30 秒之间', 'error');
        return false;
    }
    return postDouyinConfig(timing, false, '时间配置已保存');
}

async function saveDouyinMessageConfig() {
    const messageConfig = collectDouyinMessageConfig();
    if (!messageConfig.unlimited_replies_per_user) {
        const maxReplies = messageConfig.max_replies_per_user;
        if (!Number.isInteger(maxReplies) || maxReplies < 1 || maxReplies > 100) {
            showToast('单用户最大回复次数必须在 1-100 之间', 'error');
            return false;
        }
    }
    return postDouyinConfig(messageConfig, false, '消息设置已保存');
}

async function saveDouyinDefaultReply() {
    const config = collectDouyinDefaultReplyConfig();
    if (config.default_reply_enabled && !config.default_reply_message.trim()) {
        showToast('请输入默认回复内容', 'warning');
        return false;
    }
    return postDouyinConfig(config, false, '默认回复已保存');
}

async function saveDouyinConfig(silent = false) {
    const messageConfig = collectDouyinMessageConfig();
    const defaultConfig = collectDouyinDefaultReplyConfig();
    if (!messageConfig.unlimited_replies_per_user) {
        const maxReplies = messageConfig.max_replies_per_user;
        if (!Number.isInteger(maxReplies) || maxReplies < 1) {
            showToast('单用户最大回复次数不能小于 1', 'error');
            return false;
        }
    }
    if (!silent && defaultConfig.default_reply_enabled && !defaultConfig.default_reply_message.trim()) {
        showToast('请输入默认回复内容', 'warning');
        return false;
    }
    return postDouyinConfig(collectDouyinConfigFields(), silent);
}

function updateDouyinReplyLimitState() {
    const unlimited = document.getElementById('unlimited-replies-per-user');
    const maxInput = document.getElementById('max-replies-per-user');
    if (!unlimited || !maxInput) return;
    maxInput.disabled = unlimited.checked;
    maxInput.title = unlimited.checked ? '当前已启用不限制回复条数' : '';
}

async function loadDouyinRules() {
    try {
        const res = await fetch('/api/douyin-rules');
        const data = await res.json();
        douyinRules = data.rules || [];
        currentDouyinPage = 1;
        renderDouyinRules();
    } catch (e) {
        showToast('加载规则失败', 'error');
    }
}

function renderDouyinRules() {
    const list = document.getElementById('rules-list');
    const totalPages = Math.max(1, Math.ceil(douyinRules.length / douyinRulesPerPage));
    if (currentDouyinPage > totalPages) currentDouyinPage = totalPages;
    if (currentDouyinPage < 1) currentDouyinPage = 1;

    const start = (currentDouyinPage - 1) * douyinRulesPerPage;
    const pageRules = douyinRules.slice(start, start + douyinRulesPerPage);

    list.innerHTML = '';
    if (pageRules.length === 0) {
        list.innerHTML = '<p class="help-text" style="padding: 20px; text-align: center;">暂无规则，请在上方添加或从 B 站导入</p>';
    } else {
        pageRules.forEach((rule, idx) => {
            const realIdx = start + idx;
            const div = document.createElement('div');
            div.className = 'rule-item';
            const replySummary = rule.reply || '';
            div.innerHTML = `
                <div class="rule-title">${escapeHtml(rule.name || '未命名规则')}</div>
                <div class="rule-keywords">关键词: ${escapeHtml(rule.keyword || '')}</div>
                <div class="rule-reply">${escapeHtml(replySummary)}</div>
                <div class="rule-actions">
                    <label class="checkbox-wrapper">
                        <input type="checkbox" ${rule.enabled !== false ? 'checked' : ''} onchange="toggleDouyinRule(${realIdx}, this.checked)">
                        <span>${rule.enabled !== false ? '已启用' : '已禁用'}</span>
                    </label>
                    <div>
                        <button class="btn-secondary btn-sm" onclick="editDouyinRule(${realIdx})">编辑</button>
                        <button class="btn-danger btn-sm" onclick="removeDouyinRule(${realIdx})">删除</button>
                    </div>
                </div>
            `;
            list.appendChild(div);
        });
    }

    const pageText = `第 ${currentDouyinPage} 页，共 ${totalPages} 页`;
    const pageInfoBottom = document.getElementById('page-info-bottom');
    if (pageInfoBottom) pageInfoBottom.textContent = pageText;
    const prevDisabled = currentDouyinPage <= 1;
    const nextDisabled = currentDouyinPage >= totalPages;
    ['prev-page-bottom', 'next-page-bottom'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        if (id.startsWith('prev')) el.disabled = prevDisabled;
        else el.disabled = nextDisabled;
    });
}

function changeDouyinPage(delta) {
    currentDouyinPage += delta;
    renderDouyinRules();
}

function toggleDouyinRule(idx, enabled) {
    if (douyinRules[idx]) {
        douyinRules[idx].enabled = enabled;
        renderDouyinRules();
    }
}

function editDouyinRule(idx) {
    const rule = douyinRules[idx];
    if (!rule) return;
    document.getElementById('rule-name').value = rule.name || '';
    document.getElementById('rule-keyword').value = rule.keyword || '';
    document.getElementById('rule-reply').value = rule.reply || '';
    removeDouyinRule(idx);
    document.getElementById('rule-name').scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function addDouyinRuleFromForm() {
    const name = document.getElementById('rule-name').value.trim();
    const keyword = document.getElementById('rule-keyword').value.trim();
    const reply = document.getElementById('rule-reply').value.trim();
    if (!keyword || !reply) {
        showToast('请填写关键词和回复内容', 'warning');
        return;
    }
    douyinRules.push({
        name: name || '新规则',
        keyword,
        reply,
        reply_type: 'text',
        reply_image: '',
        enabled: true,
    });
    document.getElementById('rule-name').value = '';
    document.getElementById('rule-keyword').value = '';
    document.getElementById('rule-reply').value = '';
    renderDouyinRules();
    showToast('规则已添加，记得点击保存', 'success');
}

function removeDouyinRule(idx) {
    douyinRules.splice(idx, 1);
    renderDouyinRules();
}

async function saveDouyinRules(silent = false) {
    try {
        const res = await fetch('/api/douyin-rules', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rules: douyinRules }),
        });
        const data = await res.json();
        if (data.success === false) {
            if (silent && res.status === 409 && String(data.error || '').includes('AI')) return true;
            showToast(data.error || '保存失败', 'error');
            return false;
        }
        if (!silent) showToast('规则已保存', 'success');
        return true;
    } catch (e) {
        showToast('保存规则失败', 'error');
        return false;
    }
}

function getDouyinAvatarSrc(url) {
    if (!url) return '';
    if (url.startsWith('/api/douyin-avatar')) return url;
    return `/api/douyin-avatar?url=${encodeURIComponent(url)}`;
}

function updateAccountUI(account, loggedIn, loginTime, sessionExpired = false) {
    const card = document.getElementById('account-card');
    const statusEl = document.getElementById('login-status-text');
    const startBtn = document.getElementById('start-btn');
    const expiredBanner = document.getElementById('session-expired-banner');

    if (expiredBanner) {
        expiredBanner.style.display = sessionExpired ? 'block' : 'none';
    }

    const nickname = account.nickname && account.nickname !== '海量优质视频内容'
        ? account.nickname : (loggedIn ? '已登录用户' : '未登录');
    const uid = account.uid && account.uid !== 'self' ? account.uid : (account.sec_uid || '-');

    document.getElementById('account-nickname').textContent = loggedIn ? nickname : '未登录';
    document.getElementById('account-uid').textContent = loggedIn ? `UID: ${uid}` : 'UID: -';
    document.getElementById('account-login-time').textContent = formatLoginTime(loginTime);

    const avatarEl = document.getElementById('account-avatar');
    const avatarUrl = (account.avatar || account.avatarUrl || '').trim();
    const showUserAvatar = loggedIn && !sessionExpired && avatarUrl;

    if (showUserAvatar) {
        avatarEl.classList.remove('account-avatar--default');
        avatarEl.innerHTML = `<img src="${escapeHtml(getDouyinAvatarSrc(avatarUrl))}" alt="avatar" referrerpolicy="no-referrer">`;
    } else {
        avatarEl.classList.add('account-avatar--default');
        avatarEl.innerHTML = `<img src="${DOUYIN_DEFAULT_AVATAR}" alt="抖音">`;
    }

    if (loggedIn && !sessionExpired) {
        card.classList.add('logged-in');
        statusEl.textContent = '已登录';
        statusEl.className = 'value ok';
        if (!isDouyinMonitoring) {
            startBtn.disabled = false;
        }
    } else if (sessionExpired) {
        card.classList.remove('logged-in');
        statusEl.textContent = '已失效';
        statusEl.className = 'value warn';
        startBtn.disabled = true;
    } else {
        card.classList.remove('logged-in');
        statusEl.textContent = '未登录';
        statusEl.className = 'value warn';
        startBtn.disabled = true;
    }
    if (typeof setPlatformLoginRequired === 'function') {
        setPlatformLoginRequired(!loggedIn || sessionExpired);
    }
}

async function refreshLoginStatus(showMessage = false) {
    try {
        const res = await fetch('/api/douyin-login/status');
        const data = await res.json();
        updateAccountUI(data.account || {}, data.logged_in, data.login_time, data.session_expired);
        const loginBtn = document.getElementById('login-btn');
        if (data.login_in_progress) {
            loginBtn.disabled = true;
            loginBtn.textContent = '等待登录中…';
        } else {
            loginBtn.disabled = false;
            loginBtn.textContent = '打开登录窗口';
        }
        if (showMessage && data.logged_in) {
            showToast('状态已刷新', 'success');
        }
    } catch (e) {
        console.error(e);
    }
}

async function refreshAccountInfo() {
    try {
        const res = await fetch('/api/douyin-account/refresh', { method: 'POST' });
        const data = await res.json();
        if (!data.success) {
            showToast(data.error || '刷新失败', 'error');
            return;
        }
        updateAccountUI(
            data.account || {},
            true,
            document.getElementById('account-login-time').textContent,
            false
        );
        loadDouyinConfig();
        showToast('账号信息已更新', 'success');
    } catch (e) {
        showToast('刷新账号失败', 'error');
    }
}

async function startDouyinLogin() {
    if (loginPollTimer) stopLoginPoll();
    loginSuccessNotified = false;

    try {
        const res = await fetch('/api/douyin-login/start', { method: 'POST' });
        const data = await res.json();
        if (!data.success) {
            showToast(data.error || '无法打开登录窗口', 'error');
            return;
        }
        showToast('请在登录窗口中完成登录', 'info');

        loginPollTimer = setInterval(async () => {
            try {
                const st = await (await fetch('/api/douyin-login/status')).json();
                await refreshLoginStatus(false);

                if (st.logged_in && !st.login_in_progress) {
                    stopLoginPoll();
                    if (!loginSuccessNotified) {
                        loginSuccessNotified = true;
                        showToast('登录成功，监控将自动启动', 'success');
                        loadDouyinConfig();
                        checkDouyinStatus();
                    }
                }
            } catch (e) {
                console.error(e);
            }
        }, 2000);
    } catch (e) {
        showToast('启动登录失败，请确认已安装 playwright', 'error');
    }
}

async function douyinLogout() {
    if (!confirm('确定退出抖音登录？')) return;
    stopLoginPoll();
    loginSuccessNotified = false;
    try {
        const response = await fetch('/api/douyin-logout', { method: 'POST' });
        const data = await response.json();
        if (!response.ok || !data.success) {
            showToast(data.error || '退出失败，浏览器登录数据未完全清除', 'error');
            return;
        }
        showToast(data.message || '已退出登录，浏览器登录数据已清除', 'success');
        refreshLoginStatus(false);
        checkDouyinStatus();
    } catch (e) {
        showToast('退出失败', 'error');
    }
}

async function startDouyinMonitoring() {
    const configOk = await saveDouyinConfig(true);
    if (!configOk) return;
    const rulesOk = await saveDouyinRules(true);
    if (!rulesOk) return;
    const startBtn = document.getElementById('start-btn');
    setMonitorStartButtonLoading(startBtn, true, DOUYIN_MONITOR_START_LABEL, DOUYIN_MONITOR_STARTING_LABEL);
    try {
        const res = await fetch('/api/douyin-start', { method: 'POST' });
        const data = await res.json();
        if (!data.success) {
            showToast(data.error || '启动失败', 'error');
            applyDouyinMonitorButtonState(startBtn, { monitoring: false, logged_in: true, session_expired: false });
            return;
        }
        showToast('监控正在启动…', 'info');
        checkDouyinStatus();
    } catch (e) {
        showToast('启动监控失败', 'error');
        applyDouyinMonitorButtonState(startBtn, { monitoring: false, logged_in: true, session_expired: false });
    }
}

async function stopDouyinMonitoring() {
    try {
        await fetch('/api/douyin-stop', { method: 'POST' });
        showToast('监控已停止', 'success');
        checkDouyinStatus();
    } catch (e) {
        showToast('停止失败', 'error');
    }
}

async function checkDouyinStatus() {
    try {
        const res = await fetch('/api/douyin-status');
        const data = await res.json();
        isDouyinMonitoring = !!data.monitoring;
        const statusText = document.getElementById('status');
        const indicator = document.getElementById('status-indicator');
        const startBtn = document.getElementById('start-btn');
        const stopBtn = document.getElementById('stop-btn');

        indicator.classList.remove('running', 'logged-in', 'monitoring', 'active');
        if (data.monitor_starting) {
            statusText.textContent = '正在启动…';
            indicator.classList.add('monitoring', 'active');
            stopBtn.disabled = false;
        } else if (data.monitoring) {
            statusText.textContent = '监控中';
            indicator.classList.add('monitoring', 'active');
            startBtn.disabled = true;
            stopBtn.disabled = false;
        } else if (data.session_expired) {
            statusText.textContent = '登录已失效';
            indicator.classList.remove('monitoring', 'active', 'logged-in');
            startBtn.disabled = true;
            stopBtn.disabled = true;
        } else if (data.logged_in) {
            statusText.textContent = '已登录 · 未监控';
            indicator.classList.add('logged-in');
            startBtn.disabled = false;
            stopBtn.disabled = true;
        } else {
            statusText.textContent = '未启动';
            startBtn.disabled = true;
            stopBtn.disabled = true;
        }
        applyDouyinMonitorButtonState(startBtn, data);
        updateAccountUI(data.account || {}, data.logged_in, data.login_time, data.session_expired);
        const nextPollMs = data.monitor_starting ? 1000 : 3000;
        if (nextPollMs !== douyinStatusPollMs) {
            douyinStatusPollMs = nextPollMs;
            scheduleDouyinStatusPoll();
        }
    } catch (e) {
        console.error(e);
    }
}

async function loadDouyinLogs() {
    try {
        const res = await fetch('/api/douyin-logs?limit=50');
        const data = await res.json();
        renderPlatformLogs(data.logs, document.getElementById('logs-container'));
    } catch (e) {
        console.error(e);
    }
}

function formatDouyinFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function exportDouyinConfig() {
    showToast('正在导出抖音配置...', 'info');
    fetch('/api/export-douyin-config')
        .then(response => {
            if (response.ok) return response.blob();
            return response.json().then(data => {
                throw new Error(data.error || '导出失败');
            });
        })
        .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            const now = new Date();
            const timestamp = now.getFullYear()
                + String(now.getMonth() + 1).padStart(2, '0')
                + String(now.getDate()).padStart(2, '0') + '_'
                + String(now.getHours()).padStart(2, '0')
                + String(now.getMinutes()).padStart(2, '0')
                + String(now.getSeconds()).padStart(2, '0');
            a.download = `biligo_douyin_config_${timestamp}.json`;
            if (document.body) {
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
            } else {
                a.click();
            }
            window.URL.revokeObjectURL(url);
            showToast(`成功导出抖音配置（${douyinRules.length} 条规则）`, 'success');
        })
        .catch(error => {
            showToast(`导出失败: ${error.message || error}`, 'error');
        });
}

function openDouyinImportModal() {
    document.getElementById('douyin-import-modal').style.display = 'block';
    clearDouyinImportForm();
}

function closeDouyinImportModal() {
    document.getElementById('douyin-import-modal').style.display = 'none';
    clearDouyinImportForm();
}

function clearDouyinImportForm() {
    const fileInput = document.getElementById('douyin-config-file');
    if (fileInput) fileInput.value = '';
    const fileInfo = document.getElementById('douyin-file-info');
    const importOptions = document.getElementById('douyin-import-options');
    const importBtn = document.getElementById('douyin-import-btn');
    const uploadArea = document.getElementById('douyin-file-upload-area');
    if (fileInfo) fileInfo.style.display = 'none';
    if (importOptions) importOptions.style.display = 'none';
    if (importBtn) importBtn.disabled = true;
    if (uploadArea) uploadArea.classList.remove('dragover');
}

function handleDouyinFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;
    displayDouyinFileInfo(file);
    validateDouyinConfigFile(file);
}

function displayDouyinFileInfo(file) {
    document.getElementById('douyin-file-name').textContent = file.name;
    document.getElementById('douyin-file-size').textContent = formatDouyinFileSize(file.size);
    document.getElementById('douyin-file-info').style.display = 'block';
}

function clearDouyinSelectedFile() {
    clearDouyinImportForm();
}

function validateDouyinConfigFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    fetch('/api/validate-douyin-config-file', {
        method: 'POST',
        body: formData,
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                document.getElementById('douyin-import-options').style.display = 'block';
                document.getElementById('douyin-import-btn').disabled = false;
                const configHint = data.has_config ? '，包含配置项' : '';
                showToast(`文件验证成功，发现 ${data.valid_rules} 条有效规则${configHint}`, 'success');
            } else {
                showToast(`文件验证失败: ${data.error}`, 'error');
                document.getElementById('douyin-import-btn').disabled = true;
            }
        })
        .catch(error => {
            showToast(`验证文件时出错: ${error}`, 'error');
            document.getElementById('douyin-import-btn').disabled = true;
        });
}

async function importDouyinConfig() {
    const fileInput = document.getElementById('douyin-config-file');
    const importModeInput = document.querySelector('input[name="douyin-import-mode"]:checked');
    if (!fileInput.files[0]) {
        showToast('请选择文件', 'error');
        return;
    }
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('import_mode', importModeInput ? importModeInput.value : 'replace');
    const importBtn = document.getElementById('douyin-import-btn');
    const originalText = importBtn.innerHTML;
    importBtn.disabled = true;
    importBtn.innerHTML = '导入中...';
    try {
        const res = await fetch('/api/import-douyin-config', {
            method: 'POST',
            body: formData,
        });
        const data = await res.json();
        if (data.success) {
            showToast(data.message, 'success');
            closeDouyinImportModal();
            await loadDouyinConfig();
            await loadDouyinRules();
        } else {
            showToast(`导入失败: ${data.error}`, 'error');
        }
    } catch (error) {
        showToast(`导入时出错: ${error}`, 'error');
    } finally {
        importBtn.disabled = false;
        importBtn.innerHTML = originalText;
    }
}

document.addEventListener('click', function(event) {
    const importModal = document.getElementById('douyin-import-modal');
    if (importModal && event.target === importModal) {
        closeDouyinImportModal();
    }
    const resetModal = document.getElementById('reset-confirm-modal');
    if (resetModal && event.target === resetModal) {
        closeResetConfirmModal();
    }
});

function confirmResetAllData() {
    const modal = document.getElementById('reset-confirm-modal');
    if (modal) modal.style.display = 'block';
}

function closeResetConfirmModal() {
    const modal = document.getElementById('reset-confirm-modal');
    if (modal) modal.style.display = 'none';
}

function executeResetAllData() {
    closeResetConfirmModal();
    stopLoginPoll();
    loginSuccessNotified = false;
    showToast('正在清除所有数据...', 'info');

    fetch('/api/reset-douyin-data', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showToast('所有数据已清除，页面即将刷新...', 'success');
                setTimeout(() => window.location.reload(), 2000);
            } else {
                showToast('清除数据失败: ' + (data.error || '未知错误'), 'error');
            }
        })
        .catch(error => {
            showToast('清除数据失败: ' + error.message, 'error');
        });
}
