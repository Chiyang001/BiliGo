(function () {
    const labels = {
        bili_message: 'B站私信',
        bili_comment: 'B站评论',
        douyin: '抖音私信',
        xiaohongshu: '小红书私信',
        weibo: '微博私信',
        xianyu: '闲鱼消息',
    };

    function currentPlatform() {
        return document.body.dataset.aiPlatform || document.body.dataset.apiPrefix || '';
    }

    function notify(message, type) {
        if (typeof window.showToast === 'function') window.showToast(message, type);
        else window.alert(message);
    }

    function closeModal(modal) {
        modal.style.display = 'none';
    }

    async function submitImport(target, modal) {
        const source = modal.querySelector('[data-platform-import-source]').value;
        const mode = modal.querySelector('input[name="cross-platform-import-mode"]:checked').value;
        if (!source) {
            notify('请选择源平台', 'warning');
            return;
        }
        if (mode === 'replace' && !window.confirm('替换模式会清空当前平台的传统规则，确定继续吗？')) return;
        const button = modal.querySelector('[data-platform-import-submit]');
        button.disabled = true;
        button.textContent = '导入中...';
        try {
            const response = await fetch('/api/platform-import', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({source, target, mode}),
            });
            const data = await response.json();
            if (!data.success) throw new Error(data.error || '导入失败');
            notify(`${data.message}，新增 ${data.imported_rules} 条规则`, 'success');
            closeModal(modal);
            window.setTimeout(() => window.location.reload(), 700);
        } catch (error) {
            notify(error.message || '导入失败', 'error');
            button.disabled = false;
            button.textContent = '开始导入';
        }
    }

    function createModal(target) {
        const modal = document.createElement('div');
        modal.className = 'modal';
        modal.id = 'platform-import-modal';
        const options = Object.entries(labels)
            .filter(([key]) => key !== target)
            .map(([key, label]) => `<option value="${key}">${label}</option>`)
            .join('');
        modal.innerHTML = `
            <div class="modal-content" style="max-width: 440px;">
                <div class="modal-header">
                    <h3>从其他平台导入</h3>
                    <button type="button" class="close-btn" data-platform-import-close aria-label="关闭"></button>
                </div>
                <div class="modal-body">
                    <p class="help-text">导入文字规则和通用监控参数，不包含账号、Cookie、登录会话、统计或日志。</p>
                    <div class="form-row">
                        <label for="platform-import-source">源平台:</label>
                        <select id="platform-import-source" data-platform-import-source>
                            <option value="">请选择</option>${options}
                        </select>
                    </div>
                    <div class="form-row">
                        <label>导入模式:</label>
                        <div class="radio-group">
                            <div class="radio-wrapper"><input type="radio" id="cross-platform-import-replace" name="cross-platform-import-mode" value="replace" checked><label for="cross-platform-import-replace">替换现有规则</label></div>
                            <div class="radio-wrapper"><input type="radio" id="cross-platform-import-append" name="cross-platform-import-mode" value="append"><label for="cross-platform-import-append">追加新规则</label></div>
                        </div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn-primary" data-platform-import-submit>开始导入</button>
                    <button type="button" class="btn-secondary" data-platform-import-close>取消</button>
                </div>
            </div>`;
        modal.querySelectorAll('[data-platform-import-close]').forEach(button => {
            button.addEventListener('click', () => closeModal(modal));
        });
        modal.querySelector('[data-platform-import-submit]').addEventListener('click', () => submitImport(target, modal));
        modal.addEventListener('click', event => {
            if (event.target === modal) closeModal(modal);
        });
        document.body.appendChild(modal);
        return modal;
    }

    document.addEventListener('DOMContentLoaded', function () {
        const target = currentPlatform();
        if (!labels[target]) return;
        const modal = createModal(target);
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn-success';
        button.dataset.platformImportOpen = 'true';
        button.textContent = '从其他平台导入';
        button.title = '从其他平台导入规则和通用设置';
        button.addEventListener('click', () => { modal.style.display = 'block'; });

        const fileImportButton = document.querySelector(
            'button[onclick*="openImportModal"], button[onclick*="openCommentImportModal"], button[onclick*="openDouyinImportModal"], button[onclick*="openPlatformConfigImport"]'
        );
        if (fileImportButton) {
            fileImportButton.insertAdjacentElement('afterend', button);
            return;
        }
        const saveButton = document.querySelector('button[onclick*="saveXhsConfig"]');
        if (saveButton) saveButton.insertAdjacentElement('afterend', button);
    });
})();
