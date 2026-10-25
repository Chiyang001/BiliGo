(() => {
    'use strict';
    const form = document.getElementById('panel-login-form');
    const message = document.getElementById('auth-error');
    const submit = document.getElementById('login-submit');
    const submitLabel = submit.querySelector('.submit-label');
    const password = document.getElementById('panel-password');
    const visibility = document.getElementById('toggle-password');
    const help = document.getElementById('login-help');
    const helpText = document.getElementById('login-help-text');
    let pending = false;

    visibility.addEventListener('click', () => {
        const show = password.type === 'password';
        password.type = show ? 'text' : 'password';
        visibility.setAttribute('aria-pressed', String(show));
        visibility.setAttribute('aria-label', show ? '隐藏密码' : '显示密码');
    });
    help.addEventListener('click', () => {
        helpText.hidden = !helpText.hidden;
        help.setAttribute('aria-expanded', String(!helpText.hidden));
    });
    password.addEventListener('input', () => {
        form.classList.remove('has-error');
        password.removeAttribute('aria-invalid');
        message.textContent = '';
    });

    function showError(text) {
        message.textContent = text;
        form.classList.add('has-error');
        password.setAttribute('aria-invalid', 'true');
    }

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (pending) return;
        pending = true;
        message.textContent = '';
        form.classList.remove('has-error');
        form.classList.add('is-submitting');
        form.setAttribute('aria-busy', 'true');
        password.removeAttribute('aria-invalid');
        submit.disabled = true;
        submitLabel.textContent = '正在验证…';
        let succeeded = false;
        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST', credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json', 'X-BiliGo-Login': '1' },
                body: JSON.stringify({
                    password: password.value,
                    remember: document.getElementById('remember-login').checked,
                    next: new URLSearchParams(location.search).get('next') || '/',
                }),
            });
            const data = await response.json();
            if (!response.ok || !data.success) {
                showError(data.error || '登录失败，请重试');
                return;
            }
            succeeded = true;
            password.value = '';
            form.classList.remove('is-submitting');
            form.classList.add('is-success');
            submitLabel.textContent = '验证成功，正在进入…';
            location.replace(data.next || '/');
        } catch (_) {
            showError('连接失败，请检查网络后重试');
        } finally {
            if (!succeeded) {
                pending = false;
                form.classList.remove('is-submitting');
                form.removeAttribute('aria-busy');
                submit.disabled = false;
                submitLabel.textContent = '登录面板';
            }
        }
    });
})();
