(() => {
    'use strict';
    const form = document.getElementById('panel-password-form');
    const message = document.getElementById('auth-error');
    const submit = document.getElementById('password-submit');
    const submitLabel = submit.querySelector('.submit-label');
    const current = document.getElementById('current-password');
    const next = document.getElementById('new-password');
    const confirmation = document.getElementById('confirm-password');
    const match = document.getElementById('password-match');
    let idleLabel = '更新密码';
    let pending = false;

    document.querySelectorAll('[data-toggle-password]').forEach(button => {
        button.addEventListener('click', () => {
            const input = document.getElementById(button.dataset.togglePassword);
            const show = input.type === 'password';
            input.type = show ? 'text' : 'password';
            button.setAttribute('aria-pressed', String(show));
            button.setAttribute('aria-label', (show ? '隐藏' : '显示') + button.dataset.passwordLabel);
        });
    });

    [current, next, confirmation].forEach(input => {
        input.addEventListener('input', () => {
            message.textContent = '';
            form.classList.remove('has-error');
            form.querySelectorAll('[aria-invalid]').forEach(field => field.removeAttribute('aria-invalid'));
            form.querySelectorAll('.is-invalid').forEach(field => field.classList.remove('is-invalid'));
            const matches = next.value.length >= 8 && confirmation.value === next.value;
            confirmation.closest('.password-field').classList.toggle('is-matched', matches);
            match.textContent = matches ? '密码一致 ✓' : '';
        });
    });

    function showError(text, input) {
        message.textContent = text;
        form.classList.add('has-error');
        if (input) {
            input.setAttribute('aria-invalid', 'true');
            input.closest('.password-field').classList.add('is-invalid');
        }
    }
    fetch('/api/auth/status', { cache: 'no-store' })
        .then(response => response.json())
        .then(data => {
            if (!data.authenticated) {
                location.replace('/login');
                return;
            }
            if (!data.must_change_password) return;
            document.body.classList.add('is-setup');
            document.getElementById('security-heading').textContent = '设置你的面板密码';
            document.getElementById('security-description').textContent = '设置新密码，即可继续。';
            document.getElementById('current-password-label').textContent = '当前 / 初始密码';
            document.getElementById('security-back').hidden = true;
            idleLabel = '设置密码';
            if (!pending) submitLabel.textContent = idleLabel;
        })
        .catch(() => { message.textContent = '无法读取登录状态，请刷新页面重试'; });
    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (pending) return;
        message.textContent = '';
        const password = next.value;
        if (password !== confirmation.value) {
            showError('两次输入的新密码不一致', confirmation);
            return;
        }
        pending = true;
        form.classList.add('is-submitting');
        form.setAttribute('aria-busy', 'true');
        submit.disabled = true;
        submitLabel.textContent = '正在更新…';
        let succeeded = false;
        try {
            const response = await fetch('/api/auth/password', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    current_password: current.value,
                    new_password: password,
                }),
            });
            const data = await response.json();
            if (!response.ok || !data.success) {
                showError(data.error || '密码更新失败', response.status === 401 ? current : next);
                return;
            }
            form.reset();
            succeeded = true;
            form.classList.remove('is-submitting');
            form.classList.add('is-success');
            submitLabel.textContent = '密码已更新';
            location.replace('/login');
        } catch (_) {
            showError('连接失败，请重试');
        } finally {
            if (!succeeded) {
                pending = false;
                form.classList.remove('is-submitting');
                form.removeAttribute('aria-busy');
                submit.disabled = false;
                submitLabel.textContent = idleLabel;
            }
        }
    });
    document.getElementById('panel-logout').addEventListener('click', () => window.BiliGoAuth.logout());
})();
