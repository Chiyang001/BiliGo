(() => {
    'use strict';

    const nativeFetch = window.fetch.bind(window);
    let csrfPromise;
    let redirecting = false;

    function requireLogin() {
        if (redirecting) return;
        redirecting = true;
        location.replace('/login?next=' + encodeURIComponent(location.pathname + location.search));
    }

    function requirePasswordChange() {
        if (redirecting || location.pathname === '/panel-security') return;
        redirecting = true;
        location.replace('/panel-security?setup=1');
    }

    function sessionStatus() {
        if (!csrfPromise) {
            csrfPromise = nativeFetch('/api/auth/status', { cache: 'no-store', credentials: 'same-origin' })
                .then(response => response.json())
                .then(data => {
                    if (!data.authenticated) {
                        requireLogin();
                        throw new Error('请先登录面板');
                    }
                    if (data.must_change_password && location.pathname !== '/panel-security') {
                        requirePasswordChange();
                        throw new Error('请先设置自定义面板密码');
                    }
                    return data.csrf_token;
                });
        }
        return csrfPromise;
    }

    window.fetch = async (input, options = {}) => {
        const url = new URL(input instanceof Request ? input.url : input, location.href);
        const isPanelApi = url.origin === location.origin && url.pathname.startsWith('/api/');
        const method = (options.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
        if (isPanelApi && !['GET', 'HEAD', 'OPTIONS'].includes(method)) {
            const headers = new Headers(options.headers || (input instanceof Request ? input.headers : undefined));
            headers.set('X-BiliGo-CSRF', await sessionStatus());
            options = { ...options, headers, credentials: 'same-origin' };
        }
        const response = await nativeFetch(input, options);
        if (isPanelApi && response.status === 401 && url.pathname !== '/api/auth/password') requireLogin();
        if (isPanelApi && response.status === 428) {
            const data = await response.clone().json().catch(() => ({}));
            if (data.code === 'PASSWORD_CHANGE_REQUIRED') requirePasswordChange();
        }
        return response;
    };

    async function logout() {
        try {
            const response = await fetch('/api/auth/logout', { method: 'POST' });
            if (response.ok || response.status === 401) location.replace('/login');
            else alert('退出失败，请刷新页面后重试');
        } catch (_) {
            alert('连接失败，请重试');
        }
    }
    window.BiliGoAuth = { logout };

    let actions = document.querySelector('.header-actions, .topbar-actions');
    if (!document.body.classList.contains('auth-page')) {
        if (!actions) {
            const header = document.querySelector('header');
            if (header) {
                actions = document.createElement('div');
                const back = header.querySelector(':scope > #docs-back-link');
                if (back) actions.append(back);
                header.append(actions);
            }
        }
    }
    if (actions && !document.body.classList.contains('auth-page')) {
        const stylesheet = document.createElement('link');
        stylesheet.rel = 'stylesheet';
        stylesheet.href = '/web_auth.css';
        document.head.append(stylesheet);
        actions.classList.add('biligo-header-actions');
        const security = document.createElement('a');
        security.href = '/panel-security';
        security.className = 'panel-security-link';
        security.title = '面板安全与密码设置';
        security.innerHTML = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m12 3 7 3v5c0 5-7 10-7 10S5 16 5 11V6l7-3Z"/><path d="m9 11 2 2 4-4"/></svg><span>面板安全</span>';
        actions.append(security);
    }

    window.addEventListener('pageshow', (event) => {
        if (!event.persisted) return;
        csrfPromise = undefined;
        sessionStatus().catch(() => requireLogin());
    });
})();
