let xhsRules = [];
let currentXhsPage = 1;
const xhsRulesPerPage = 5;
let xhsMonitoring = false;
let xhsStatusPollMs = 3000;
let xhsStatusPollTimer = null;
let xhsLoginTimer = null;
let xhsLoginPollGeneration = 0;
let xhsLoginPollInFlight = false;
const PLATFORM_API = document.body?.dataset.apiPrefix || 'xiaohongshu';
const PLATFORM_NAME = document.body?.dataset.platformName || '小红书';
const PLATFORM_DEFAULT_AVATARS = {
    xiaohongshu: '/xiaohongshu-seeklogo.png',
    weibo: '/sina-weibo-seeklogo.png',
    xianyu: '/xianyu.jpg',
};
const PLATFORM_DEFAULT_AVATAR = PLATFORM_DEFAULT_AVATARS[PLATFORM_API] || '/bilibili.png';
const PLATFORM_MONITOR_START_LABEL = '开始监控';
const PLATFORM_MONITOR_STARTING_LABEL = '正在启动中，请稍后';
const platformApi = suffix => `/api/${PLATFORM_API}${suffix}`;

function checkUpdate() {
    window.open('https://github.com/Chiyang001/BiliGo/releases/', '_blank');
}

function openDocsPage() {
    const section = `${PLATFORM_API}-mode`;
    window.location.href = `/docs.html?from=${encodeURIComponent(PLATFORM_API)}#${section}`;
}

document.addEventListener('DOMContentLoaded', async () => {
    await Promise.all([loadXhsConfig(), loadXhsRules(), loadPlatformEmailConfig()]);
    await refreshXhsLogin(false);
    await checkXhsStatus();
    loadXhsLogs();
    if (!xhsMonitoring) {
        fetch(platformApi('-login/status?verify=1')).catch(() => {});
    }
    scheduleXhsStatusPoll();
    setInterval(loadXhsLogs, 4000);
});

async function loadPlatformEmailConfig() {
    try {
        const data = await (await fetch(`/api/platform-email-config/${PLATFORM_API}`)).json();
        const cfg = data.config || {};
        const enabled = document.getElementById('platform-email-enabled');
        const receiver = document.getElementById('platform-email-receiver');
        if (enabled) enabled.checked = !!cfg.enabled;
        if (receiver) receiver.value = cfg.receiver_email || '';
    } catch (error) { console.warn('加载平台邮件提醒配置失败', error); }
}

async function savePlatformEmailConfig() {
    const enabled = !!document.getElementById('platform-email-enabled')?.checked;
    const receiver_email = document.getElementById('platform-email-receiver')?.value.trim() || '';
    const response = await fetch(`/api/platform-email-config/${PLATFORM_API}`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({enabled, receiver_email})
    });
    const data = await response.json();
    showToast(data.success ? `${PLATFORM_NAME}异常邮件提醒设置已保存` : (data.error || '保存失败'), data.success ? 'success' : 'error');
}

function scheduleXhsStatusPoll() {
    if (xhsStatusPollTimer) {
        clearInterval(xhsStatusPollTimer);
    }
    xhsStatusPollTimer = setInterval(checkXhsStatus, xhsStatusPollMs);
}

function applyPlatformMonitorButtonState(startBtn, data) {
    if (data.monitor_starting) {
        setMonitorStartButtonLoading(startBtn, true, PLATFORM_MONITOR_START_LABEL, PLATFORM_MONITOR_STARTING_LABEL);
        return;
    }
    setMonitorStartButtonLoading(startBtn, false, PLATFORM_MONITOR_START_LABEL);
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

function escapeHtml(value) {
    return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span class="toast-icon"></span><div class="toast-message">${escapeHtml(message)}</div>`;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3200);
}

function togglePlatformSwitcher(event) {
    event.stopPropagation();
    document.getElementById('platform-switcher').classList.toggle('open');
}

document.addEventListener('click', event => {
    const switcher = document.getElementById('platform-switcher');
    if (switcher && !switcher.contains(event.target)) switcher.classList.remove('open');
});

function collectXhsDefault() {
    return {
        default_reply_enabled: document.getElementById('default-reply-enabled').checked,
        default_reply_type: 'text',
        default_reply_message: document.getElementById('default-reply-message').value,
        default_reply_image: '',
    };
}

function collectXhsConfig() {
    const maxReplies = parseInt(document.getElementById('max-replies-per-user').value, 10);
    return {
        message_check_interval: parseFloat(document.getElementById('message-check-interval').value),
        send_delay_interval: parseFloat(document.getElementById('send-delay-interval').value),
        only_reply_new_messages: document.getElementById('only-reply-new-messages').checked,
        max_replies_per_user: Number.isInteger(maxReplies) ? maxReplies : 3,
        unlimited_replies_per_user: document.getElementById('unlimited-replies-per-user').checked,
        ...collectXhsDefault(),
    };
}

function validateXhsConfig(config, skipTraditional = false) {
    if (!Number.isFinite(config.message_check_interval) || config.message_check_interval < 0.5 || config.message_check_interval > 60) return '消息检测间隔必须在 0.5-60 秒之间';
    if (!Number.isFinite(config.send_delay_interval) || config.send_delay_interval < 0.5 || config.send_delay_interval > 30) return '发送间隔必须在 0.5-30 秒之间';
    if (!config.unlimited_replies_per_user && (!Number.isInteger(config.max_replies_per_user) || config.max_replies_per_user < 1)) return '单用户回复次数不能小于 1';
    if (!skipTraditional && config.default_reply_enabled && !config.default_reply_message.trim()) return '请输入默认回复内容';
    return '';
}

async function postXhsConfig(config, silent = false) {
    const error = validateXhsConfig(config, silent);
    if (error) { showToast(error, 'warning'); return false; }
    try {
        const response = await fetch(platformApi('-config'), {
            method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(config),
        });
        const data = await response.json();
        if (data.success === false && silent && response.status === 409 && String(data.error || '').includes('AI')) return true;
        if (!data.success) throw new Error(data.error || '保存失败');
        if (!silent) showToast('配置已保存', 'success');
        return true;
    } catch (e) { showToast(e.message || '保存失败', 'error'); return false; }
}

function resolveXhsLoggedIn(cfg) {
    if (cfg.session_expired) return false;
    if (cfg.logged_in) return true;
    const account = cfg.account || {};
    return !!(account.uid || account.nickname);
}

async function loadXhsConfig() {
    try {
        const cfg = await (await fetch(platformApi('-config'))).json();
        document.getElementById('message-check-interval').value = cfg.message_check_interval ?? 1;
        document.getElementById('send-delay-interval').value = cfg.send_delay_interval ?? 1;
        document.getElementById('only-reply-new-messages').checked = cfg.only_reply_new_messages !== false;
        document.getElementById('max-replies-per-user').value = cfg.max_replies_per_user ?? 3;
        document.getElementById('unlimited-replies-per-user').checked = !!cfg.unlimited_replies_per_user;
        document.getElementById('default-reply-enabled').checked = !!cfg.default_reply_enabled;
        document.getElementById('default-reply-message').value = cfg.default_reply_message || '';
        updateXhsReplyLimitState();
        updateXhsAccount(
            cfg.account || {},
            resolveXhsLoggedIn(cfg),
            cfg.login_time,
            cfg.session_expired,
        );
    } catch (e) { showToast(`加载${PLATFORM_NAME}配置失败`, 'error'); }
}

function saveXhsConfig(silent = false) { return postXhsConfig(collectXhsConfig(), silent); }
function saveXhsDefaultReply() { return postXhsConfig(collectXhsDefaultWithCurrent(), false); }

function collectXhsDefaultWithCurrent() {
    return {...collectXhsConfig(), ...collectXhsDefault()};
}

function updateXhsReplyLimitState() {
    const unlimited = document.getElementById('unlimited-replies-per-user').checked;
    document.getElementById('max-replies-per-user').disabled = unlimited;
}

async function loadXhsRules() {
    try { xhsRules = (await (await fetch(platformApi('-rules'))).json()).rules || []; currentXhsPage = 1; renderXhsRules(); }
    catch (e) { showToast('加载规则失败', 'error'); }
}

function renderXhsRules() {
    const list = document.getElementById('rules-list');
    const totalPages = Math.max(1, Math.ceil(xhsRules.length / xhsRulesPerPage));
    currentXhsPage = Math.max(1, Math.min(currentXhsPage, totalPages));
    const start = (currentXhsPage - 1) * xhsRulesPerPage;
    const pageRules = xhsRules.slice(start, start + xhsRulesPerPage);
    if (!pageRules.length) list.innerHTML = '<p class="help-text" style="padding:20px;text-align:center;">暂无规则</p>';
    else list.innerHTML = pageRules.map((rule, pageIndex) => {
        const index = start + pageIndex;
        const reply = rule.reply;
        return `<div class="rule-item">
            <div class="rule-title">${escapeHtml(rule.name || '未命名规则')}</div>
            <div class="rule-keywords">关键词: ${escapeHtml(rule.keyword || '')}</div>
            <div class="rule-reply">${escapeHtml(reply || '')}</div>
            <div class="rule-actions"><label class="checkbox-wrapper"><input type="checkbox" ${rule.enabled !== false ? 'checked':''} onchange="toggleXhsRule(${index},this.checked)"><span>${rule.enabled !== false ? '已启用':'已禁用'}</span></label>
            <div><button class="btn-secondary btn-sm" onclick="editXhsRule(${index})">编辑</button> <button class="btn-danger btn-sm" onclick="removeXhsRule(${index})">删除</button></div></div>
        </div>`;
    }).join('');
    const pageText = `第 ${currentXhsPage} 页，共 ${totalPages} 页`;
    ['xhs-page-info-bottom'].forEach(id => {
        const element = document.getElementById(id);
        if (element) element.textContent = pageText;
    });
    ['xhs-prev-page-bottom'].forEach(id => {
        const element = document.getElementById(id);
        if (element) element.disabled = currentXhsPage <= 1;
    });
    ['xhs-next-page-bottom'].forEach(id => {
        const element = document.getElementById(id);
        if (element) element.disabled = currentXhsPage >= totalPages;
    });
}

function changeXhsPage(delta) {
    currentXhsPage += delta;
    renderXhsRules();
}

function addXhsRule() {
    const name = document.getElementById('rule-name').value.trim();
    const keyword = document.getElementById('rule-keyword').value.trim();
    const reply = document.getElementById('rule-reply').value.trim();
    if (!keyword || !reply) {
        showToast('请填写关键词和回复内容', 'warning'); return;
    }
    xhsRules.push({name:name || '新规则', keyword, reply, reply_type:'text', reply_image:'', enabled:true});
    currentXhsPage = Math.max(1, Math.ceil(xhsRules.length / xhsRulesPerPage));
    clearXhsRuleForm(); renderXhsRules(); showToast('规则已添加，请保存', 'success');
}

function editXhsRule(index) {
    const rule = xhsRules[index]; if (!rule) return;
    document.getElementById('rule-name').value = rule.name || '';
    document.getElementById('rule-keyword').value = rule.keyword || '';
    document.getElementById('rule-reply').value = rule.reply || '';
    xhsRules.splice(index, 1); renderXhsRules();
    document.getElementById('rule-name').scrollIntoView({behavior:'smooth'});
}

function clearXhsRuleForm() {
    ['rule-name','rule-keyword','rule-reply'].forEach(id => document.getElementById(id).value = '');
}

function removeXhsRule(index) { xhsRules.splice(index,1); renderXhsRules(); }
function toggleXhsRule(index, enabled) { if (xhsRules[index]) xhsRules[index].enabled = enabled; renderXhsRules(); }

async function saveXhsRules(silent = false) {
    try {
        const response = await fetch(platformApi('-rules'), {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rules:xhsRules})});
        const data = await response.json();
        if (data.success === false && silent && response.status === 409 && String(data.error || '').includes('AI')) return true;
        if (!data.success) throw new Error(data.error || '保存失败');
        if (!silent) showToast('规则已保存', 'success'); return true;
    } catch (e) { showToast(e.message || '保存规则失败', 'error'); return false; }
}

function updateXhsAccount(account, loggedIn, loginTime, expired = false) {
    const valid = !!loggedIn && !expired;
    if (typeof setPlatformLoginRequired === 'function') {
        setPlatformLoginRequired(!valid);
    } else {
        const loginHint = document.getElementById('login-required-hint');
        if (loginHint) loginHint.hidden = valid;
    }
    document.getElementById('account-nickname').textContent = valid ? (account.nickname || '已登录用户') : '未登录';
    document.getElementById('account-uid').textContent = valid ? `用户 ID: ${account.uid || '-'}` : '用户 ID: -';
    document.getElementById('account-login-time').textContent = loginTime ? new Date(loginTime).toLocaleString('zh-CN',{hour12:false}) : '-';
    const status = document.getElementById('login-status-text'); status.textContent = expired ? '已失效' : (valid ? '已登录':'未登录'); status.className = `value ${valid ? 'ok':'warn'}`;
    const avatar = document.getElementById('account-avatar');
    const avatarUrl = ['weibo', 'xianyu'].includes(PLATFORM_API) && account.avatar
        ? `${platformApi('-account/avatar')}?v=${encodeURIComponent(account.avatar)}`
        : account.avatar;
    avatar.innerHTML = valid && avatarUrl
        ? `<img src="${escapeHtml(avatarUrl)}" alt="头像" referrerpolicy="no-referrer" onerror="this.onerror=null;this.src='${PLATFORM_DEFAULT_AVATAR}'">`
        : `<img class="default-platform-avatar" src="${PLATFORM_DEFAULT_AVATAR}" alt="${PLATFORM_NAME}默认头像">`;
}

function openPlatformAccountPanel() {
    const accountTab = document.querySelector('[data-platform-tab="account"]');
    if (accountTab) {
        accountTab.click();
        return;
    }
    document.querySelector('.config-panel')?.scrollIntoView({behavior: 'smooth', block: 'start'});
}

async function refreshXhsLogin(show = false) {
    try { const data = await (await fetch(platformApi('-login/status'))).json(); updateXhsAccount(data.account||{},data.logged_in,data.login_time,data.session_expired); if(show) showToast('账号状态已刷新','success'); }
    catch (e) { if(show) showToast('刷新失败','error'); }
}

async function startXhsLogin() {
    const data = await (await fetch(platformApi('-login/start'),{method:'POST'})).json();
    if (!data.success) { showToast(data.error || '无法打开登录窗口','error'); return; }
    showToast(`请在浏览器窗口中完成${PLATFORM_NAME}登录`,'info');
    if (xhsLoginTimer) clearTimeout(xhsLoginTimer);
    const generation = ++xhsLoginPollGeneration;
    xhsLoginPollInFlight = false;

    const pollLoginStatus = async () => {
        if (generation !== xhsLoginPollGeneration || xhsLoginPollInFlight) return;
        xhsLoginPollInFlight = true;
        try {
            const state = await (await fetch(platformApi('-login/status'))).json();
            if (generation !== xhsLoginPollGeneration) return;
            updateXhsAccount(state.account||{},state.logged_in,state.login_time,state.session_expired);
            if (state.logged_in && !state.login_in_progress) {
                xhsLoginTimer = null;
                ++xhsLoginPollGeneration;
                showToast(`${PLATFORM_NAME}登录成功`, 'success');
                checkXhsStatus();
                return;
            }
        } catch (e) {
            if (generation !== xhsLoginPollGeneration) return;
        } finally {
            xhsLoginPollInFlight = false;
        }
        if (generation === xhsLoginPollGeneration) {
            xhsLoginTimer = setTimeout(pollLoginStatus, 2000);
        }
    };
    xhsLoginTimer = setTimeout(pollLoginStatus, 800);
}

async function refreshXhsAccount() {
    const data = await (await fetch(platformApi('-account/refresh'),{method:'POST'})).json();
    if (!data.success) { showToast(data.error || '刷新失败','error'); return; }
    showToast('账号信息已更新','success'); refreshXhsLogin(false);
}

async function xhsLogout() {
    if (!confirm(`确定退出${PLATFORM_NAME}登录？`)) return;
    ++xhsLoginPollGeneration;
    if (xhsLoginTimer) clearTimeout(xhsLoginTimer);
    xhsLoginTimer = null;
    try {
        const response = await fetch(platformApi('-logout'), {method:'POST'});
        const data = await response.json();
        if (!response.ok || !data.success) {
            showToast(data.error || '退出失败，浏览器登录数据未完全清除', 'error');
            return;
        }
        showToast(data.message || `已退出${PLATFORM_NAME}登录，浏览器登录数据已清除`, 'success');
        refreshXhsLogin(false);
        checkXhsStatus();
    } catch (e) {
        showToast('退出失败', 'error');
    }
}

async function startXhsMonitoring() {
    if (!await saveXhsConfig(true) || !await saveXhsRules(true)) return;
    const startBtn = document.getElementById('start-btn');
    setMonitorStartButtonLoading(startBtn, true, PLATFORM_MONITOR_START_LABEL, PLATFORM_MONITOR_STARTING_LABEL);
    const data = await (await fetch(platformApi('-start'),{method:'POST'})).json();
    if (!data.success) {
        showToast(data.error || '启动失败','error');
        applyPlatformMonitorButtonState(startBtn, { monitoring: false, logged_in: true, session_expired: false });
        return;
    }
    showToast(`${PLATFORM_NAME}监控正在启动…`,'info');
    checkXhsStatus();
}

async function stopXhsMonitoring() { await fetch(platformApi('-stop'),{method:'POST'}); showToast('监控已停止','success'); checkXhsStatus(); }

async function checkXhsStatus() {
    try {
        const data = await (await fetch(platformApi('-status'))).json();
        xhsMonitoring = !!data.monitoring;
        const startBtn = document.getElementById('start-btn');
        const stopBtn = document.getElementById('stop-btn');
        const text = data.monitor_starting
            ? '正在启动…'
            : data.monitoring
                ? '监控中'
                : data.session_expired
                    ? '登录已失效'
                    : data.logged_in
                        ? '已登录 · 未监控'
                        : '未启动';
        document.getElementById('status').textContent = text;
        const indicator = document.getElementById('status-indicator');
        indicator.classList.toggle('active', data.monitoring || data.monitor_starting);
        indicator.classList.toggle('monitoring', data.monitoring || data.monitor_starting);
        stopBtn.disabled = !(data.monitoring || data.monitor_starting);
        applyPlatformMonitorButtonState(startBtn, data);
        updateXhsAccount(data.account||{},data.logged_in,data.login_time,data.session_expired);
        const nextPollMs = data.monitor_starting ? 1000 : 3000;
        if (nextPollMs !== xhsStatusPollMs) {
            xhsStatusPollMs = nextPollMs;
            scheduleXhsStatusPoll();
        }
    } catch (e) { console.error(e); }
}

async function loadXhsLogs() {
    try {
        const data = await (await fetch(platformApi('-logs?limit=50'))).json();
        renderPlatformLogs(data.logs, document.getElementById('logs-container'));
    } catch (e) { console.error(e); }
}

async function resetXhsData() {
    if (!confirm(`确定清除全部${PLATFORM_NAME}登录、配置、规则和回复图片？`)) return;
    await fetch(platformApi('-reset-all'),{method:'POST'}); showToast(`${PLATFORM_NAME}数据已清除`,'success'); location.reload();
}

function exportPlatformConfig() {
    window.location.href = platformApi('-export-config');
}

function openPlatformConfigImport() {
    document.getElementById('platform-config-import-modal').style.display = 'block';
}

function closePlatformConfigImport() {
    document.getElementById('platform-config-import-modal').style.display = 'none';
}

async function importPlatformConfig() {
    const fileInput = document.getElementById('platform-config-file');
    if (!fileInput.files[0]) {
        showToast('请选择 JSON 配置文件', 'warning');
        return;
    }
    const mode = document.querySelector('input[name="platform-config-import-mode"]:checked').value;
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('import_mode', mode);
    const button = document.getElementById('platform-config-import-submit');
    button.disabled = true;
    button.textContent = '导入中...';
    try {
        const response = await fetch(platformApi('-import-config'), {method: 'POST', body: formData});
        const data = await response.json();
        if (!data.success) throw new Error(data.error || '导入失败');
        showToast(data.message || '配置导入成功', 'success');
        closePlatformConfigImport();
        setTimeout(() => window.location.reload(), 700);
    } catch (error) {
        showToast(error.message || '导入失败', 'error');
    } finally {
        button.disabled = false;
        button.textContent = '导入';
    }
}
