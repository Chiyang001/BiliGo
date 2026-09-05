(function () {
    const platformNames = {
        bili_message: 'B站私信',
        bili_comment: 'B站评论',
        xiaohongshu: '小红书私信',
        weibo: '微博私信',
        douyin: '抖音私信',
        xianyu: '闲鱼消息'
    };

    function currentPlatform() {
        if (document.body.dataset.aiPlatform) return document.body.dataset.aiPlatform;
        if (document.body.dataset.apiPrefix) return document.body.dataset.apiPrefix;
        if (location.pathname.startsWith('/comment')) return 'bili_comment';
        if (location.pathname.startsWith('/douyin')) return 'douyin';
        if (location.pathname.startsWith('/weibo')) return 'weibo';
        if (location.pathname.startsWith('/xiaohongshu')) return 'xiaohongshu';
        if (location.pathname.startsWith('/xianyu')) return 'xianyu';
        return 'bili_message';
    }

    function lockTraditionalReplySettings(platform) {
        const selectors = ['.reply-settings-container', '.keyword-panel', '.rules-panel'];
        const panels = Array.from(new Set(selectors.flatMap(selector => Array.from(document.querySelectorAll(selector)))));
        if (!panels.length) return;

        const banner = document.createElement('div');
        banner.className = 'ai-mode-notice';
        banner.innerHTML = '<strong>已启用AI模式</strong><span>默认回复和自定义关键词回复已停用，请前往统一 AI 面板调整。</span>';
        banner.addEventListener('click', () => { location.href = `/ai-reply?from=${platform}`; });
        // Keep the notice outside the individual sections so it stays at the
        // top of the tab content regardless of which panel is active.
        const content = panels[0].parentNode;
        const firstSection = content.querySelector(':scope > section');
        content.insertBefore(banner, firstSection || panels[0]);

        panels.forEach(panel => {
            panel.classList.add('ai-mode-locked');
            panel.setAttribute('aria-disabled', 'true');
            panel.title = '已启用AI模式';
            panel.querySelectorAll('input, textarea, select, button, [contenteditable="true"]').forEach(control => {
                control.disabled = true;
                control.setAttribute('aria-disabled', 'true');
            });
        });
    }

    document.addEventListener('DOMContentLoaded', async () => {
        const platform = currentPlatform();
        const nav = document.querySelector('.ai-reply-nav');
        if (nav) {
            nav.onclick = () => { location.href = `/ai-reply?from=${platform}`; };
            nav.title = `配置${platformNames[platform] || ''} AI回复`;
        }
        try {
            const response = await fetch('/api/ai-config');
            if (!response.ok) return;
            const config = await response.json();
            if (config.enabled && config.platforms && config.platforms[platform]) {
                document.body.classList.add('ai-mode-active');
                lockTraditionalReplySettings(platform);
                if (nav) nav.classList.add('active');
            }
        } catch (_) {
            // 页面仍可使用传统回复配置。
        }
    });
})();
