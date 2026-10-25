(() => {
    'use strict';
    const storageKey = 'biligo:auth-theme';
    const choices = ['system', 'light', 'dark'];
    const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
    let preference = 'system';
    try {
        const saved = localStorage.getItem(storageKey);
        if (choices.includes(saved)) preference = saved;
    } catch (_) { /* Theme selection also works when local storage is unavailable. */ }

    function applyTheme() {
        const theme = preference === 'system' ? (systemTheme.matches ? 'dark' : 'light') : preference;
        document.documentElement.dataset.theme = theme;
        document.documentElement.dataset.themePreference = preference;
        const meta = document.querySelector('meta[name="color-scheme"]');
        if (meta) meta.content = theme;
        document.querySelectorAll('[data-theme-choice]').forEach(button => {
            button.setAttribute('aria-pressed', String(button.dataset.themeChoice === preference));
        });
    }

    applyTheme(); // Run before styles/paint to avoid flashing the opposite theme.
    document.addEventListener('DOMContentLoaded', applyTheme, { once: true });
    document.addEventListener('click', (event) => {
        const button = event.target.closest('[data-theme-choice]');
        if (!button || !choices.includes(button.dataset.themeChoice)) return;
        preference = button.dataset.themeChoice;
        try {
            if (preference === 'system') localStorage.removeItem(storageKey);
            else localStorage.setItem(storageKey, preference);
        } catch (_) { /* Keep the selection for the current page without persistence. */ }
        applyTheme();
    });
    systemTheme.addEventListener('change', () => {
        if (preference === 'system') applyTheme();
    });
    window.addEventListener('storage', (event) => {
        if (event.key !== storageKey && event.key !== null) return;
        preference = choices.includes(event.newValue) ? event.newValue : 'system';
        applyTheme();
    });
})();
