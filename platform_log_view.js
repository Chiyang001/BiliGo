const LOG_VIEW_MAX_ENTRIES = 25;
const LOG_VIEW_MAX_TEXT_LEN = 96;

// Keep the shared log renderer self-contained. Some platform pages do not
// define a global escapeHtml helper, which previously broke log rendering and
// made successful saves look like failures in the Bilibili comment UI.
function escapePlatformLogHtml(value) {
    const node = document.createElement('span');
    node.textContent = String(value ?? '');
    return node.innerHTML;
}

function truncateLogText(text, maxLen = LOG_VIEW_MAX_TEXT_LEN) {
    const value = String(text ?? '');
    if (value.length <= maxLen) return value;
    return `${value.slice(0, maxLen)}…`;
}

function normalizeLogEntry(log) {
    const type = log.type || log.level || 'info';
    let time = log.time || '';
    if (!time && log.timestamp) {
        try {
            time = new Date(log.timestamp).toLocaleString('zh-CN', { hour12: false });
        } catch {
            time = String(log.timestamp);
        }
    }
    return { ...log, type, time, message: log.message ?? '' };
}

function renderPlatformLogs(logs, container) {
    if (!container) return;
    const entries = (logs || []).slice(0, LOG_VIEW_MAX_ENTRIES).map(normalizeLogEntry);
    if (!entries.length) {
        container.innerHTML = '<div class="log-entry">暂无日志</div>';
        return;
    }
    container.innerHTML = entries.map(log => {
        const type = escapePlatformLogHtml(log.type || 'info');
        const time = escapePlatformLogHtml(log.time || '');
        const fullMessage = String(log.message ?? '');
        const message = escapePlatformLogHtml(truncateLogText(fullMessage));
        const title = escapePlatformLogHtml(fullMessage);
        return `<div class="log-entry ${type}" title="${title}"><span class="log-time">[${time}]</span> <span class="log-message">${message}</span></div>`;
    }).join('');
}

function appendPlatformLog(container, message, type = 'info') {
    if (!container) return;
    if (container.textContent.trim() === '暂无日志') {
        container.innerHTML = '';
    }
    const time = new Date().toLocaleString('zh-CN', { hour12: false });
    const fullMessage = String(message ?? '');
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    entry.title = fullMessage;
    entry.innerHTML = `<span class="log-time">[${escapePlatformLogHtml(time)}]</span> <span class="log-message">${escapePlatformLogHtml(truncateLogText(fullMessage))}</span>`;
    container.insertBefore(entry, container.firstChild);
    while (container.children.length > LOG_VIEW_MAX_ENTRIES) {
        container.removeChild(container.lastChild);
    }
}
