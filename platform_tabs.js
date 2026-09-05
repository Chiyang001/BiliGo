(() => {
    'use strict';

    const PLATFORM_META = {
        bili_message: {name: 'B站私信', eyebrow: 'BILIBILI MESSAGE', icon: 'bilibili.png', accent: '#00a9e0', deep: '#087ba7', soft: '#eefaff', border: '#93d9ee'},
        bili_comment: {name: 'B站评论', eyebrow: 'BILIBILI COMMENT', icon: 'bilibili.png', accent: '#00a9e0', deep: '#087ba7', soft: '#eefaff', border: '#93d9ee'},
        douyin: {name: '抖音私信', eyebrow: 'DOUYIN MESSAGE', icon: 'tik-tok.png', accent: '#00a6b2', deep: '#087783', soft: '#ecfafb', border: '#8ed3d8'},
        xiaohongshu: {name: '小红书私信', eyebrow: 'XIAOHONGSHU MESSAGE', icon: 'xiaohongshu-seeklogo.png', accent: '#e43b4f', deep: '#b92539', soft: '#fff2f4', border: '#f0a4ae'},
        weibo: {name: '微博私信', eyebrow: 'WEIBO MESSAGE', icon: 'sina-weibo-seeklogo.png', accent: '#f27b22', deep: '#b95615', soft: '#fff5ec', border: '#efb586'},
        xianyu: {name: '闲鱼消息', eyebrow: 'XIANYU MESSAGE', icon: 'xianyu.jpg', accent: '#f6c900', deep: '#8d7600', soft: '#fffbea', border: '#ead36b'},
    };

    const SECTION_META = {
        'control-panel': {id: 'control', title: '运行控制', subtitle: '监控与运行参数', icon: 'power'},
        'config-panel': {id: 'account', title: '账号配置', subtitle: '登录与身份信息', icon: 'user'},
        'reply-settings-container': {id: 'reply', title: '回复设置', subtitle: '默认回复与策略', icon: 'reply'},
        'unfollow-keyword-container': {id: 'keywords', title: '关键词回复', subtitle: '自动匹配策略', icon: 'rules'},
        'rules-panel': {id: 'rules', title: '关键词规则', subtitle: '自动匹配规则', icon: 'rules'},
        'log-panel': {id: 'logs', title: '运行日志', subtitle: '实时处理记录', icon: 'logs'},
    };

    const ICONS = {
        power: '<svg viewBox="0 0 24 24"><path d="M12 3v9m-5.7-6.4a8 8 0 1 0 11.4 0"/></svg>',
        user: '<svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.5"/><path d="M5 20c.7-4 3-6 7-6s6.3 2 7 6"/></svg>',
        reply: '<svg viewBox="0 0 24 24"><path d="M9 8 4 12l5 4v-3h5.5a5.5 5.5 0 0 1 5.5 5.5V19a8 8 0 0 0-8-8H9V8Z"/></svg>',
        unlink: '<svg viewBox="0 0 24 24"><path d="m9 15-2 2a3.5 3.5 0 0 1-5-5l3-3a3.5 3.5 0 0 1 4.8-.1M15 9l2-2a3.5 3.5 0 0 1 5 5l-3 3a3.5 3.5 0 0 1-4.8.1M4 4l16 16"/></svg>',
        rules: '<svg viewBox="0 0 24 24"><path d="M5 5h14M5 12h14M5 19h14"/><circle cx="9" cy="5" r="2"/><circle cx="15" cy="12" r="2"/><circle cx="10" cy="19" r="2"/></svg>',
        logs: '<svg viewBox="0 0 24 24"><path d="M5 3h14v18H5zM8 8h8m-8 4h8m-8 4h5"/></svg>',
    };

    function platformKey(body) {
        return body.dataset.aiPlatform || body.dataset.apiPrefix || 'bili_message';
    }

    function sectionConfig(section, usedIds) {
        const className = Object.keys(SECTION_META).find(name => section.classList.contains(name));
        if (!className) return null;
        const base = SECTION_META[className];
        let id = base.id;
        let suffix = 2;
        while (usedIds.has(id)) id = `${base.id}-${suffix++}`;
        usedIds.add(id);
        const heading = section.querySelector(':scope > h2');
        return {
            ...base,
            id,
            title: (heading?.textContent || base.title).replace(/[\u{1F300}-\u{1FAFF}]/gu, '').trim() || base.title,
        };
    }

    function updateRuntimeMirror(source, dot, text) {
        const value = (source?.textContent || '未启动').trim();
        const running = /运行|监控中|已启动|正在/.test(value) && !/未启动|已停止|停止中/.test(value);
        dot.classList.toggle('is-running', running);
        text.textContent = value;
    }

    function initPlatformTabs() {
        const body = document.body;
        const content = body.querySelector('.container > .main-content');
        if (!content || content.dataset.tabsReady === 'true') return;

        const sections = [...content.children].filter(node => node.matches?.('section'));
        const usedIds = new Set();
        const entries = sections.map(section => ({section, config: sectionConfig(section, usedIds)})).filter(item => item.config);
        if (entries.length < 2) return;

        const key = platformKey(body);
        const meta = PLATFORM_META[key] || PLATFORM_META.bili_message;
        body.classList.add('platform-console-page');
        body.dataset.platformTheme = key;
        body.style.setProperty('--workspace-accent', meta.accent);
        body.style.setProperty('--workspace-accent-deep', meta.deep);
        body.style.setProperty('--workspace-accent-soft', meta.soft);
        body.style.setProperty('--workspace-accent-border', meta.border);
        content.dataset.tabsReady = 'true';
        content.classList.add('platform-tab-content');

        const workspace = document.createElement('main');
        workspace.className = 'platform-settings-workspace';
        const sidebar = document.createElement('aside');
        sidebar.className = 'platform-tab-sidebar';
        sidebar.setAttribute('aria-label', `${meta.name}设置分类`);

        const switcher = body.querySelector('.header-actions .platform-switcher');
        if (switcher) {
            const switchSlot = document.createElement('div');
            switchSlot.className = 'platform-tab-switcher';
            const switchLabel = document.createElement('span');
            switchLabel.textContent = '切换平台';
            switchSlot.append(switchLabel, switcher);
            sidebar.append(switchSlot);
        }

        const identity = document.createElement('div');
        identity.className = 'platform-tab-identity';
        identity.innerHTML = `<img src="${meta.icon}" alt=""><span><small>${meta.eyebrow}</small><strong>${meta.name}</strong></span>`;
        sidebar.append(identity);

        const groupLabel = document.createElement('div');
        groupLabel.className = 'platform-tab-group-label';
        groupLabel.innerHTML = '<span>功能设置</span><b>WORKSPACE</b>';
        sidebar.append(groupLabel);

        const tabList = document.createElement('div');
        tabList.className = 'platform-tab-list';
        tabList.setAttribute('role', 'tablist');
        tabList.setAttribute('aria-orientation', 'vertical');
        sidebar.append(tabList);

        const runtime = document.createElement('div');
        runtime.className = 'platform-tab-runtime';
        runtime.innerHTML = '<i></i><span><small>当前状态</small><strong>未启动</strong></span>';
        sidebar.append(runtime);

        content.parentNode.insertBefore(workspace, content);
        workspace.append(sidebar, content);

        const tabs = entries.map(({section, config}, index) => {
            section.classList.add('platform-tab-panel');
            section.dataset.platformPanel = config.id;
            section.setAttribute('role', 'tabpanel');
            section.id = section.id || `platform-panel-${key}-${config.id}`;

            const tab = document.createElement('button');
            tab.type = 'button';
            tab.className = 'platform-tab-button';
            tab.dataset.platformTab = config.id;
            tab.id = `platform-tab-${key}-${config.id}`;
            tab.setAttribute('role', 'tab');
            tab.setAttribute('aria-controls', section.id);
            tab.innerHTML = `<span class="platform-tab-icon">${ICONS[config.icon]}</span><span class="platform-tab-copy"><strong>${config.title}</strong><small>${config.subtitle}</small></span><b aria-hidden="true">›</b>`;
            tabList.append(tab);
            section.setAttribute('aria-labelledby', tab.id);
            return {tab, section, config, index};
        });

        const storageKey = `biligo:${key}:active-tab`;
        const hashMatch = location.hash.match(/^#tab=([\w-]+)$/);
        const requested = hashMatch?.[1] || sessionStorage.getItem(storageKey) || tabs[0].config.id;

        function activate(id, focus = false) {
            const target = tabs.find(item => item.config.id === id) || tabs[0];
            tabs.forEach(item => {
                const active = item === target;
                item.tab.classList.toggle('active', active);
                item.tab.setAttribute('aria-selected', String(active));
                item.tab.tabIndex = active ? 0 : -1;
                item.section.hidden = !active;
                item.section.classList.toggle('active', active);
            });
            sessionStorage.setItem(storageKey, target.config.id);
            history.replaceState(null, '', `${location.pathname}${location.search}#tab=${target.config.id}`);
            if (focus) target.tab.focus({preventScroll: true});
            content.scrollTop = 0;
        }

        tabs.forEach((item, index) => {
            item.tab.addEventListener('click', () => activate(item.config.id));
            item.tab.addEventListener('keydown', event => {
                if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
                event.preventDefault();
                let next = index;
                if (event.key === 'ArrowDown') next = (index + 1) % tabs.length;
                if (event.key === 'ArrowUp') next = (index - 1 + tabs.length) % tabs.length;
                if (event.key === 'Home') next = 0;
                if (event.key === 'End') next = tabs.length - 1;
                activate(tabs[next].config.id, true);
            });
        });
        activate(requested);

        const sourceStatus = document.getElementById('status');
        const runtimeDot = runtime.querySelector('i');
        const runtimeText = runtime.querySelector('strong');
        updateRuntimeMirror(sourceStatus, runtimeDot, runtimeText);
        if (sourceStatus) {
            new MutationObserver(() => updateRuntimeMirror(sourceStatus, runtimeDot, runtimeText))
                .observe(sourceStatus, {childList: true, characterData: true, subtree: true});
        }

        requestAnimationFrame(() => body.classList.add('platform-tabs-ready'));
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initPlatformTabs);
    else initPlatformTabs();
})();

window.setPlatformLoginRequired = function (required) {
    const hint = document.getElementById('login-required-hint');
    if (hint) hint.hidden = !required;
    if (!required) return;
    const startButton = document.getElementById('start-btn');
    const stopButton = document.getElementById('stop-btn');
    if (startButton) startButton.disabled = true;
    if (stopButton) stopButton.disabled = true;
};

window.openPlatformAccountPanel = function () {
    const accountTab = document.querySelector('[data-platform-tab="account"]');
    if (accountTab) {
        accountTab.click();
        return;
    }
    document.querySelector('.config-panel')?.scrollIntoView({behavior: 'smooth', block: 'start'});
};

// Render the same complete SMTP form on every platform account tab.
window.initPlatformEmailForm = function (platform) {
    const host = document.querySelector('.platform-email-alert');
    if (!host || host.dataset.ready === 'true') return;
    host.dataset.ready = 'true';
    host.innerHTML = `<div class="collapsible-section"><div class="collapsible-header" role="button" tabindex="0" aria-expanded="true"><h3>邮件提醒配置</h3><span class="toggle-icon rotated" aria-hidden="true">▼</span></div><div class="collapsible-content" style="display:block"><div class="form-row"><div class="checkbox-wrapper"><input type="checkbox" id="email-notification-enabled"><label for="email-notification-enabled">启用邮件提醒</label></div><p class="help-text">启用后，${platform === 'bili_comment' ? '评论' : '私信'}系统出现错误时会发送邮件通知</p></div><div id="email-settings"><div class="form-row"><label for="sender-email">发送邮箱:</label><input type="email" id="sender-email" placeholder="例如：your_email@qq.com"></div><div class="form-row"><label for="sender-password">邮箱授权码:</label><input type="password" id="sender-password" placeholder="请输入邮箱授权码"></div><div class="form-row"><label for="receiver-email">接收邮箱:</label><input type="email" id="receiver-email" placeholder="例如：your_email@qq.com"></div><div class="form-row"><label for="smtp-server">SMTP服务器:</label><input type="text" id="smtp-server" value="smtp.qq.com"></div><div class="form-row"><label for="smtp-port">SMTP端口:</label><input type="number" id="smtp-port" value="587"></div><div class="button-group"><button class="btn-primary" type="button" onclick="savePlatformEmailForm('${platform}')">保存邮件配置</button><button class="btn-secondary" type="button" onclick="testPlatformEmailForm('${platform}')">发送测试邮件</button></div></div></div></div>`;
    const header = host.querySelector('.collapsible-header');
    const content = host.querySelector('.collapsible-content');
    const icon = host.querySelector('.toggle-icon');
    const toggle = () => {
        const expanded = content.style.display !== 'none';
        content.style.display = expanded ? 'none' : 'block';
        header.setAttribute('aria-expanded', String(!expanded));
        icon.classList.toggle('rotated', !expanded);
    };
    header.addEventListener('click', toggle);
    header.addEventListener('keydown', event => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        toggle();
    });
    document.getElementById('email-notification-enabled').addEventListener('change', () => {
        document.getElementById('email-settings').style.display = document.getElementById('email-notification-enabled').checked ? 'block' : 'none';
    });
};
window.loadPlatformEmailForm = async function (platform) {
    window.initPlatformEmailForm(platform);
    const data = await (await fetch(`/api/platform-email-config/${platform}`)).json();
    const cfg = data.config || {};
    for (const [id, key] of [['email-notification-enabled','enabled'],['sender-email','sender_email'],['sender-password','sender_password'],['receiver-email','receiver_email'],['smtp-server','smtp_server'],['smtp-port','smtp_port']]) { const el = document.getElementById(id); if (el) el.type === 'checkbox' ? el.checked = !!cfg[key] : el.value = cfg[key] ?? ''; }
    const settings = document.getElementById('email-settings'); if (settings) settings.style.display = cfg.enabled ? 'block' : 'none';
};
window.savePlatformEmailForm = async function (platform) {
    const value = id => document.getElementById(id)?.value?.trim() || '';
    const payload = {enabled: !!document.getElementById('email-notification-enabled')?.checked, sender_email: value('sender-email'), sender_password: document.getElementById('sender-password')?.value || '', receiver_email: value('receiver-email'), smtp_server: value('smtp-server') || 'smtp.qq.com', smtp_port: parseInt(value('smtp-port') || '587', 10)};
    const data = await (await fetch(`/api/platform-email-config/${platform}`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)})).json();
    if (typeof showToast === 'function') showToast(data.success ? '邮件配置保存成功' : (data.error || '保存失败'), data.success ? 'success' : 'error');
};
window.testPlatformEmailForm = async function (platform) {
    const value = id => document.getElementById(id)?.value?.trim() || '';
    const data = await (await fetch('/api/test_email', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({platform, sender_email:value('sender-email'), sender_password:document.getElementById('sender-password')?.value || '', receiver_email:value('receiver-email'), smtp_server:value('smtp-server') || 'smtp.qq.com', smtp_port:parseInt(value('smtp-port') || '587', 10)})})).json();
    if (typeof showToast === 'function') showToast(data.success ? '测试邮件发送成功' : (data.error || '发送失败'), data.success ? 'success' : 'error');
};

(() => {
    const platform = document.body?.dataset.aiPlatform || document.body?.dataset.apiPrefix;
    if (!platform || platform === 'bili_message' || !document.querySelector('.platform-email-alert')) return;
    const run = () => window.loadPlatformEmailForm(platform).catch(err => console.warn('加载邮件配置失败', err));
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run, {once: true});
    else run();
})();
