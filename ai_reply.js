const PLATFORM_ROUTES = { bili_message: '/', bili_comment: '/comment', xiaohongshu: '/xiaohongshu', weibo: '/weibo', douyin: '/douyin', xianyu: '/xianyu' };
const MASKED_API_KEY = '************';
let apiKeyConfigured = false;
let showingMaskedApiKey = false;
let knowledgeBases = [];
let knowledgeAssignments = {};
let selectedKnowledgeBaseId = null;
let handoffRefreshTimer = null;
let savedAiEnabled = false;
let savedPlatforms = {};
let savedModelSettings = {};
let savedKnowledgeEnabled = false;
let savedKnowledgeAssignments = {};
let savedHandoffEnabled = false;
let providerSwitchSaving = false;
let knowledgeSwitchSaving = false;

function initAiAmbientAnimation() {
    const hero = document.querySelector('.ai-settings-hero');
    const canvas = document.getElementById('ai-ambient-canvas');
    if (!hero || !canvas) return;
    const context = canvas.getContext('2d');
    if (!context) return;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let width = 0;
    let height = 0;
    let animationFrame = 0;
    let particles = [];
    const pointer = {x: 0, y: 0, active: false};

    function createParticle(index, count) {
        return {
            x: Math.random() * width,
            y: Math.random() * height,
            vx: reducedMotion ? 0 : (Math.random() - .5) * .16,
            vy: reducedMotion ? 0 : (Math.random() - .5) * .12,
            radius: index % 7 === 0 ? 1.7 : 1.05,
            phase: (index / Math.max(count, 1)) * Math.PI * 2
        };
    }

    function resize() {
        const rect = hero.getBoundingClientRect();
        width = Math.max(1, Math.round(rect.width));
        height = Math.max(1, Math.round(rect.height));
        const ratio = Math.min(window.devicePixelRatio || 1, 1.75);
        canvas.width = Math.round(width * ratio);
        canvas.height = Math.round(height * ratio);
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        context.setTransform(ratio, 0, 0, ratio, 0, 0);
        const count = Math.max(20, Math.min(44, Math.round(width / 34)));
        particles = Array.from({length: count}, (_, index) => createParticle(index, count));
        if (reducedMotion) draw(0);
    }

    function draw(time) {
        context.clearRect(0, 0, width, height);
        particles.forEach((particle, index) => {
            if (!reducedMotion) {
                particle.x += particle.vx;
                particle.y += particle.vy;
                if (particle.x < -8) particle.x = width + 8;
                if (particle.x > width + 8) particle.x = -8;
                if (particle.y < -8) particle.y = height + 8;
                if (particle.y > height + 8) particle.y = -8;
                if (pointer.active) {
                    const dx = pointer.x - particle.x;
                    const dy = pointer.y - particle.y;
                    const distance = Math.hypot(dx, dy);
                    if (distance < 150 && distance > 1) {
                        const influence = (1 - distance / 150) * .018;
                        particle.x += dx * influence;
                        particle.y += dy * influence;
                    }
                }
            }
            for (let nextIndex = index + 1; nextIndex < particles.length; nextIndex += 1) {
                const next = particles[nextIndex];
                const distance = Math.hypot(next.x - particle.x, next.y - particle.y);
                if (distance < 112) {
                    context.beginPath();
                    context.moveTo(particle.x, particle.y);
                    context.lineTo(next.x, next.y);
                    context.strokeStyle = `rgba(157, 196, 230, ${(1 - distance / 112) * .13})`;
                    context.lineWidth = .65;
                    context.stroke();
                }
            }
            const glow = .62 + Math.sin(time * .0007 + particle.phase) * .18;
            context.beginPath();
            context.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
            context.fillStyle = index % 7 === 0 ? `rgba(229, 194, 104, ${glow})` : `rgba(190, 220, 244, ${glow * .52})`;
            context.fill();
        });
        if (!reducedMotion && !document.hidden) animationFrame = requestAnimationFrame(draw);
    }

    hero.addEventListener('pointermove', event => {
        const rect = hero.getBoundingClientRect();
        pointer.x = event.clientX - rect.left;
        pointer.y = event.clientY - rect.top;
        pointer.active = true;
        hero.style.setProperty('--ai-pointer-x', `${(pointer.x / rect.width) * 100}%`);
        hero.style.setProperty('--ai-pointer-y', `${(pointer.y / rect.height) * 100}%`);
    });
    hero.addEventListener('pointerleave', () => { pointer.active = false; });
    const observer = new ResizeObserver(resize);
    observer.observe(hero);
    document.addEventListener('visibilitychange', () => {
        cancelAnimationFrame(animationFrame);
        if (!document.hidden && !reducedMotion) animationFrame = requestAnimationFrame(draw);
    });
    resize();
    if (!reducedMotion) animationFrame = requestAnimationFrame(draw);
}

function selectedPlatforms() {
    return Object.fromEntries(Array.from(document.querySelectorAll('[data-platform]')).map(input => [input.dataset.platform, input.checked]));
}

function updatePlatformCount() {
    const count = Array.from(document.querySelectorAll('[data-platform]:checked')).length;
    document.getElementById('ai-platform-count').textContent = `${count} / 5`;
    document.querySelectorAll('.ai-tab-button[data-tab]').forEach(button => {
        const input = document.querySelector(`[data-platform="${button.dataset.tab}"]`);
        button.classList.toggle('enabled', Boolean(input && input.checked));
    });
}

function openTab(tabName) {
    // 操作反馈只属于产生它的页面，切换 Tab 时不带到其他配置页。
    showResult('');
    document.querySelectorAll('.ai-tab-button').forEach(button => {
        const active = button.dataset.tab === tabName;
        button.classList.toggle('active', active);
        button.setAttribute('aria-selected', String(active));
    });
    document.querySelectorAll('.ai-tab-panel').forEach(panel => {
        panel.hidden = panel.dataset.panel !== tabName;
    });
    const saveBar = document.querySelector('.ai-save-bar');
    if (saveBar) saveBar.classList.toggle('is-hidden', tabName === 'handoff');
    if (tabName === 'handoff') loadHandoffs();
}

function handoffTime(timestamp) {
    const date = new Date(Number(timestamp || 0) * 1000);
    if (Number.isNaN(date.getTime())) return '刚刚';
    return new Intl.DateTimeFormat('zh-CN', {
        month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
    }).format(date);
}

function updateHandoffCount(count) {
    const value = Math.max(0, Number(count) || 0);
    document.getElementById('ai-handoff-count').textContent = value.toLocaleString('zh-CN');
    const badge = document.getElementById('ai-handoff-badge');
    badge.textContent = value > 99 ? '99+' : String(value);
    badge.hidden = value === 0;
}

function createHandoffCard(item) {
    const card = document.createElement('article');
    card.className = 'ai-handoff-card';
    const head = document.createElement('div');
    head.className = 'ai-handoff-card-head';
    const identity = document.createElement('div');
    const platform = document.createElement('span');
    platform.className = 'ai-handoff-platform';
    platform.textContent = item.platform_name || item.platform;
    const sender = document.createElement('strong');
    sender.className = 'ai-handoff-sender';
    sender.textContent = item.sender_name || '未知用户';
    identity.append(platform, sender);
    const time = document.createElement('span');
    time.className = 'ai-handoff-time';
    time.textContent = handoffTime(item.created_at);
    head.append(identity, time);

    const message = document.createElement('div');
    message.className = 'ai-handoff-message';
    message.textContent = item.message_text;
    const reason = document.createElement('p');
    reason.className = 'ai-handoff-reason';
    const reasonLabel = document.createElement('strong');
    reasonLabel.textContent = 'AI 判断';
    const reasonText = document.createElement('span');
    reasonText.textContent = item.reason || '建议由人工确认后回复';
    reason.append(reasonLabel, reasonText);

    const compose = document.createElement('div');
    compose.className = 'ai-handoff-compose';
    const textarea = document.createElement('textarea');
    textarea.maxLength = 2000;
    textarea.placeholder = '输入人工回复内容…';
    textarea.setAttribute('aria-label', `回复 ${item.sender_name || '用户'}`);
    const dismiss = document.createElement('button');
    dismiss.type = 'button';
    dismiss.className = 'btn-secondary ai-handoff-dismiss';
    dismiss.textContent = '忽略';
    const reply = document.createElement('button');
    reply.type = 'button';
    reply.className = 'btn-primary';
    reply.textContent = '发送回复';
    const feedback = document.createElement('div');
    feedback.className = 'ai-handoff-card-status';
    feedback.setAttribute('role', 'status');
    feedback.setAttribute('aria-live', 'polite');
    const showCardResult = (text, type = '') => {
        feedback.textContent = text;
        feedback.className = `ai-handoff-card-status${type ? ` is-${type}` : ''}`;
    };
    const setBusy = busy => {
        textarea.disabled = busy;
        dismiss.disabled = busy;
        reply.disabled = busy;
        reply.textContent = busy ? '发送中…' : '发送回复';
    };
    const send = async () => {
        const text = textarea.value.trim();
        if (!text) { textarea.focus(); return showCardResult('请输入人工回复内容', 'error'); }
        showCardResult('');
        setBusy(true);
        try {
            const response = await fetch(`/api/ai-handoffs/${encodeURIComponent(item.id)}/reply`, {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text}),
            });
            const body = await response.json();
            if (!response.ok || body.success === false) throw new Error(body.error || '发送失败');
            await loadHandoffs();
        } catch (error) {
            showCardResult(error.message || '人工回复发送失败', 'error');
            setBusy(false);
        }
    };
    reply.addEventListener('click', send);
    textarea.addEventListener('keydown', event => {
        if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); send(); }
    });
    dismiss.addEventListener('click', async () => {
        setBusy(true);
        try {
            const response = await fetch(`/api/ai-handoffs/${encodeURIComponent(item.id)}/dismiss`, {method: 'POST'});
            const body = await response.json();
            if (!response.ok || body.success === false) throw new Error(body.error || '操作失败');
            await loadHandoffs();
        } catch (error) {
            showCardResult(error.message || '忽略失败', 'error');
            setBusy(false);
        }
    });
    compose.append(textarea, dismiss, reply);
    card.append(head, message, reason, compose, feedback);
    return card;
}

async function loadHandoffs(countOnly = false) {
    const filter = document.getElementById('ai-handoff-platform');
    const platform = countOnly ? '' : filter.value;
    try {
        const response = await fetch(`/api/ai-handoffs?platform=${encodeURIComponent(platform)}`, {cache: 'no-store'});
        const body = await response.json();
        if (!response.ok) throw new Error(body.error || '读取失败');
        updateHandoffCount(body.pending_count);
        if (countOnly) return;
        const list = document.getElementById('ai-handoff-list');
        const items = Array.isArray(body.items) ? body.items : [];
        if (!items.length) {
            list.innerHTML = '<div class="ai-handoff-empty">当前没有待人工处理的消息</div>';
            return;
        }
        list.replaceChildren(...items.map(createHandoffCard));
    } catch (error) {
        if (!countOnly) document.getElementById('ai-handoff-list').innerHTML = '<div class="ai-handoff-empty">暂时无法读取待回消息，请稍后重试</div>';
    }
}

function showResult(message, type = '') {
    const result = document.getElementById('ai-save-result');
    result.textContent = message;
    result.style.color = type === 'error' ? '#dc3545' : type === 'success' ? '#198754' : '#66758a';
}

function showHandoffSaveStatus(message, type = '') {
    const status = document.getElementById('ai-handoff-save-status');
    if (!status) return;
    status.textContent = message;
    status.className = type ? `is-${type}` : '';
}

function setProviderSwitchesDisabled(disabled) {
    document.querySelectorAll('#ai-enabled, [data-platform], #ai-human-handoff-enabled, #ai-context-enabled, #ai-auto-compress').forEach(input => {
        input.disabled = disabled;
    });
}

async function saveProviderSwitchPartial(data, onSaved, onRollback, handoffStatus = false) {
    if (providerSwitchSaving) return;
    providerSwitchSaving = true;
    setProviderSwitchesDisabled(true);
    if (handoffStatus) showHandoffSaveStatus('正在保存…', 'saving');
    else showResult('正在保存…');
    try {
        const response = await fetch('/api/ai-config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data),
        });
        const body = await response.json();
        if (!response.ok || body.success === false) throw new Error(body.error || '保存失败');
        onSaved();
        if (handoffStatus) showHandoffSaveStatus('');
        else showResult('');
    } catch (error) {
        onRollback();
        const message = error.message || '保存失败，已恢复原设置';
        if (handoffStatus) showHandoffSaveStatus(message, 'error');
        else showResult(message, 'error');
    } finally {
        setProviderSwitchesDisabled(false);
        providerSwitchSaving = false;
    }
}

function saveAiEnabledSetting() {
    const input = document.getElementById('ai-enabled');
    const nextEnabled = input.checked;
    if (nextEnabled) {
        const data = payload();
        if (!data.base_url || !data.model || (!data.api_key && !apiKeyConfigured)) {
            input.checked = savedAiEnabled;
            showResult('启用 AI 前请完整填写提供商配置', 'error');
            return Promise.resolve();
        }
    }
    return saveProviderSwitchPartial(
        {enabled: nextEnabled},
        () => { savedAiEnabled = nextEnabled; },
        () => { input.checked = savedAiEnabled; },
    );
}

function saveModelBooleanSetting(inputId, settingKey) {
    const input = document.getElementById(inputId);
    const nextValue = input.value === 'true';
    return saveProviderSwitchPartial(
        {model_settings: {[settingKey]: nextValue}},
        () => { savedModelSettings[settingKey] = nextValue; },
        () => { input.value = String(savedModelSettings[settingKey] !== false); },
    );
}

function saveContextWindowSetting() {
    const input = document.getElementById('ai-context-window');
    const previous = Number(savedModelSettings.context_window || 6000);
    const nextValue = Math.max(500, Math.min(128000, Number(input.value || 6000)));
    input.value = String(nextValue);
    return saveProviderSwitchPartial(
        {model_settings: {context_window: nextValue}},
        () => { savedModelSettings.context_window = nextValue; },
        () => { input.value = String(previous); },
    );
}

function savePlatformSettings() {
    const nextPlatforms = selectedPlatforms();
    return saveProviderSwitchPartial(
        {platforms: nextPlatforms},
        () => { savedPlatforms = {...nextPlatforms}; },
        () => {
            Object.entries(savedPlatforms).forEach(([key, value]) => {
                const input = document.querySelector(`[data-platform="${key}"]`);
                if (input) input.checked = Boolean(value);
            });
            updatePlatformCount();
        },
    );
}

function saveHandoffSetting() {
    const input = document.getElementById('ai-human-handoff-enabled');
    const nextEnabled = input.checked;
    return saveProviderSwitchPartial(
        {human_handoff: {enabled: nextEnabled}},
        () => { savedHandoffEnabled = nextEnabled; },
        () => { input.checked = savedHandoffEnabled; },
        true,
    );
}

function payload() {
    return {
        enabled: document.getElementById('ai-enabled').checked,
        platforms: selectedPlatforms(),
        format: document.getElementById('ai-format').value,
        base_url: document.getElementById('ai-base-url').value.trim(),
        model: document.getElementById('ai-model').value.trim(),
        api_key: showingMaskedApiKey ? '' : document.getElementById('ai-api-key').value.trim(),
        model_settings: {
            context_enabled: document.getElementById('ai-context-enabled').value === 'true',
            context_window: Number(document.getElementById('ai-context-window').value || 6000),
            auto_compress: document.getElementById('ai-auto-compress').value === 'true',
            prohibited_words: document.getElementById('ai-prohibited-words').value.split('，').map(item => item.trim()).filter(Boolean),
        },
        human_handoff: {
            enabled: document.getElementById('ai-human-handoff-enabled').checked,
        },
    };
}

function showProviderToolResult(message, type = '') {
    const result = document.getElementById('ai-provider-tools-result');
    result.textContent = message;
    result.style.color = type === 'error' ? '#dc3545' : type === 'success' ? '#198754' : '#66758a';
}

function formatFileSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function selectedKnowledgeBase() {
    return knowledgeBases.find(base => base.id === selectedKnowledgeBaseId) || null;
}

function renderKnowledgeDocuments() {
    const base = selectedKnowledgeBase();
    const documents = base ? (base.documents || []) : [];
    const hint = document.getElementById('ai-knowledge-content-hint');
    hint.textContent = documents.length
        ? `已展示 ${documents[0].name} 的 Markdown 原文，可直接编辑后保存`
        : '适合录入常见问题、品牌信息和回复规范';
}

function renderKnowledgeList() {
    const container = document.getElementById('ai-knowledge-list');
    if (!knowledgeBases.length) {
        container.innerHTML = '<p class="ai-knowledge-list-empty">暂无知识库<br>点击“新建”开始录入</p>';
        return;
    }
    container.replaceChildren(...knowledgeBases.map(base => {
        const row = document.createElement('div');
        row.className = `ai-knowledge-list-item${base.id === selectedKnowledgeBaseId ? ' active' : ''}`;
        const content = document.createElement('span');
        const name = document.createElement('strong');
        name.textContent = base.name;
        const meta = document.createElement('small');
        const documents = base.documents || [];
        meta.textContent = documents.length ? `Markdown · ${documents[0].name}` : '在线文本';
        content.append(name, meta);
        content.addEventListener('click', () => selectKnowledgeBase(base.id));
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'ai-knowledge-list-delete';
        remove.textContent = '×';
        remove.title = '删除知识库';
        remove.addEventListener('click', () => deleteKnowledgeBase(base.id));
        row.append(content, remove);
        return row;
    }));
}

function renderPlatformKnowledgeOptions() {
    document.querySelectorAll('[data-knowledge-platform]').forEach(container => {
        const platform = container.dataset.knowledgePlatform;
        if (!knowledgeBases.length) {
            container.innerHTML = '<span class="ai-platform-knowledge-empty">请先在知识库配置中创建知识库</span>';
            return;
        }
        const selected = new Set(knowledgeAssignments[platform] || []);
        container.replaceChildren(...knowledgeBases.map(base => {
            const label = document.createElement('label');
            label.className = 'ai-platform-knowledge-option';
            const input = document.createElement('input');
            input.type = 'checkbox';
            input.value = base.id;
            input.checked = selected.has(base.id);
            input.addEventListener('change', () => {
                knowledgeAssignments[platform] = Array.from(container.querySelectorAll('input:checked')).map(item => item.value);
                saveKnowledgeSwitchSettings();
            });
            label.append(input, document.createTextNode(base.name));
            return label;
        }));
    });
}

function selectKnowledgeBase(baseId) {
    selectedKnowledgeBaseId = baseId;
    const base = selectedKnowledgeBase();
    document.getElementById('ai-knowledge-name').value = base ? base.name : '';
    document.getElementById('ai-knowledge-text').value = base ? base.text : '';
    updateKnowledgeCharCount();
    renderKnowledgeList();
    renderKnowledgeDocuments();
}

function newKnowledgeBase() {
    selectedKnowledgeBaseId = null;
    document.getElementById('ai-knowledge-name').value = '';
    document.getElementById('ai-knowledge-text').value = '';
    updateKnowledgeCharCount();
    renderKnowledgeList();
    renderKnowledgeDocuments();
    document.getElementById('ai-knowledge-name').focus();
}

async function loadKnowledgeConfig() {
    try {
        const response = await fetch('/api/ai-knowledge');
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '读取知识库失败');
        savedKnowledgeEnabled = Boolean(data.enabled);
        document.getElementById('ai-knowledge-enabled').checked = savedKnowledgeEnabled;
        knowledgeBases = Array.isArray(data.bases) ? data.bases : [];
        knowledgeAssignments = data.platform_assignments || {};
        savedKnowledgeAssignments = cloneKnowledgeAssignments(knowledgeAssignments);
        selectKnowledgeBase(knowledgeBases[0] ? knowledgeBases[0].id : null);
        renderPlatformKnowledgeOptions();
    } catch (error) { showResult(error.message || '读取知识库失败', 'error'); }
}

function updateKnowledgeCharCount() {
    const length = document.getElementById('ai-knowledge-text').value.length;
    document.getElementById('ai-knowledge-char-count').textContent = `${length.toLocaleString()} 字`;
}

async function saveCurrentKnowledgeBase() {
    const name = document.getElementById('ai-knowledge-name').value.trim();
    if (!name) return showResult('请填写知识库名称', 'error');
    const response = await fetch('/api/ai-knowledge', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            id: selectedKnowledgeBaseId,
            name,
            text: document.getElementById('ai-knowledge-text').value
        })
    });
    const body = await response.json();
    if (!response.ok || body.success === false) throw new Error(body.error || '知识库保存失败');
    const index = knowledgeBases.findIndex(base => base.id === body.knowledge_base.id);
    if (index >= 0) knowledgeBases[index] = body.knowledge_base;
    else knowledgeBases.push(body.knowledge_base);
    selectedKnowledgeBaseId = body.knowledge_base.id;
    renderKnowledgeList();
    renderKnowledgeDocuments();
    renderPlatformKnowledgeOptions();
    showResult(`知识库“${body.knowledge_base.name}”已保存`, 'success');
}

async function saveKnowledgeSettings() {
    const response = await fetch('/api/ai-knowledge/settings', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({enabled: document.getElementById('ai-knowledge-enabled').checked, platform_assignments: knowledgeAssignments})
    });
    const body = await response.json();
    if (!response.ok || body.success === false) throw new Error(body.error || '知识库分配保存失败');
}

function cloneKnowledgeAssignments(value) {
    return Object.fromEntries(
        Object.entries(value || {}).map(([platform, ids]) => [platform, Array.isArray(ids) ? [...ids] : []]),
    );
}

function setKnowledgeSwitchesDisabled(disabled) {
    document.querySelectorAll('#ai-knowledge-enabled, [data-knowledge-platform] input').forEach(input => {
        input.disabled = disabled;
    });
}

async function saveKnowledgeSwitchSettings() {
    if (knowledgeSwitchSaving) return;
    knowledgeSwitchSaving = true;
    setKnowledgeSwitchesDisabled(true);
    showResult('正在保存…');
    try {
        await saveKnowledgeSettings();
        savedKnowledgeEnabled = document.getElementById('ai-knowledge-enabled').checked;
        savedKnowledgeAssignments = cloneKnowledgeAssignments(knowledgeAssignments);
        showResult('');
    } catch (error) {
        document.getElementById('ai-knowledge-enabled').checked = savedKnowledgeEnabled;
        knowledgeAssignments = cloneKnowledgeAssignments(savedKnowledgeAssignments);
        renderPlatformKnowledgeOptions();
        showResult(error.message || '保存失败，已恢复原设置', 'error');
    } finally {
        setKnowledgeSwitchesDisabled(false);
        knowledgeSwitchSaving = false;
    }
}

async function uploadKnowledgeDocument(file) {
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    showResult('正在从 Markdown 创建知识库...');
    try {
        const response = await fetch('/api/ai-knowledge/upload', {method: 'POST', body: form});
        const body = await response.json();
        if (!response.ok || body.success === false) throw new Error(body.error || '上传失败');
        const index = knowledgeBases.findIndex(base => base.id === body.knowledge_base.id);
        if (index >= 0) knowledgeBases[index] = body.knowledge_base;
        else knowledgeBases.push(body.knowledge_base);
        selectKnowledgeBase(body.knowledge_base.id);
        renderPlatformKnowledgeOptions();
        showResult(`已从 ${body.document.name} 创建知识库`, 'success');
    } catch (error) { showResult(error.message || '上传失败', 'error'); }
    document.getElementById('ai-knowledge-file').value = '';
}

async function deleteKnowledgeDocument(documentId) {
    try {
        const response = await fetch(`/api/ai-knowledge/documents/${encodeURIComponent(documentId)}`, {method: 'DELETE'});
        const body = await response.json();
        if (!response.ok || body.success === false) throw new Error(body.error || '删除失败');
        const base = selectedKnowledgeBase();
        base.documents = (base.documents || []).filter(item => item.id !== documentId);
        renderKnowledgeDocuments();
        renderKnowledgeList();
        showResult('知识库文档已删除', 'success');
    } catch (error) { showResult(error.message || '删除失败', 'error'); }
}

async function deleteKnowledgeBase(baseId) {
    try {
        const response = await fetch(`/api/ai-knowledge/bases/${encodeURIComponent(baseId)}`, {method: 'DELETE'});
        const body = await response.json();
        if (!response.ok || body.success === false) throw new Error(body.error || '删除失败');
        knowledgeBases = knowledgeBases.filter(base => base.id !== baseId);
        Object.keys(knowledgeAssignments).forEach(platform => {
            knowledgeAssignments[platform] = (knowledgeAssignments[platform] || []).filter(id => id !== baseId);
        });
        selectKnowledgeBase(knowledgeBases[0] ? knowledgeBases[0].id : null);
        renderPlatformKnowledgeOptions();
        showResult('知识库已删除', 'success');
    } catch (error) { showResult(error.message || '删除失败', 'error'); }
}

async function loadProviderModels() {
    showProviderToolResult('正在获取模型列表...');
    try {
        const response = await fetch('/api/ai-models', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload()) });
        const body = await response.json();
        if (!response.ok || body.success === false) throw new Error(body.error || '获取失败');
        const models = Array.isArray(body.models) ? body.models : [];
        const list = document.getElementById('ai-model-options');
        list.replaceChildren(...models.map(model => {
            const option = document.createElement('option');
            option.value = model;
            return option;
        }));
        const select = document.getElementById('ai-model-select');
        const promptOption = document.createElement('option');
        promptOption.value = '';
        promptOption.textContent = `从 ${models.length} 个模型中选择`;
        select.replaceChildren(promptOption, ...models.map(model => {
            const option = document.createElement('option');
            option.value = model;
            option.textContent = model;
            return option;
        }));
        select.hidden = models.length === 0;
        if (models.length === 1 && !document.getElementById('ai-model').value.trim()) document.getElementById('ai-model').value = models[0];
        showProviderToolResult(`已获取 ${models.length} 个模型 · ${body.latency_ms} ms，可点击模型框选择`, 'success');
    } catch (error) { showProviderToolResult(error.message || '获取模型列表失败', 'error'); }
}

async function testProviderLatency() {
    showProviderToolResult('正在测速...');
    try {
        const response = await fetch('/api/ai-latency', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload()) });
        const body = await response.json();
        if (!response.ok || body.success === false) throw new Error(body.error || '测速失败');
        showProviderToolResult(`当前延迟 ${body.latency_ms} ms · ${body.level}`, 'success');
    } catch (error) { showProviderToolResult(error.message || '测速失败', 'error'); }
}

async function saveSettings() {
    const data = payload();
    if (data.enabled && !Object.values(data.platforms).some(Boolean)) return showResult('请至少选择一个开放平台', 'error');
    if (data.enabled && (!data.base_url || !data.model || (!data.api_key && !apiKeyConfigured))) return showResult('启用 AI 前请完整填写提供商配置', 'error');
    showResult('正在保存...');
    try {
        const response = await fetch('/api/ai-config', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data) });
        const body = await response.json();
        if (!response.ok || body.success === false) throw new Error(body.error || '保存失败');
        await saveKnowledgeSettings();
        savedAiEnabled = data.enabled;
        savedPlatforms = {...data.platforms};
        savedModelSettings = {...data.model_settings};
        savedHandoffEnabled = data.human_handoff.enabled;
        savedKnowledgeEnabled = document.getElementById('ai-knowledge-enabled').checked;
        savedKnowledgeAssignments = cloneKnowledgeAssignments(knowledgeAssignments);
        apiKeyConfigured = Boolean(body.api_key_configured);
        const keyInput = document.getElementById('ai-api-key');
        keyInput.value = apiKeyConfigured ? MASKED_API_KEY : '';
        showingMaskedApiKey = apiKeyConfigured;
        showResult('AI 回复设置已保存', 'success');
    } catch (error) { showResult(error.message || '保存失败', 'error'); }
}

async function testConnection() {
    const data = payload();
    if (!data.base_url || !data.model || (!data.api_key && !apiKeyConfigured)) return showResult('请完整填写接口地址、模型和 API Key', 'error');
    showResult('正在测试连接...');
    try {
        const response = await fetch('/api/ai-test', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data) });
        const body = await response.json();
        if (!response.ok || body.success === false) throw new Error(body.error || '连接失败');
        showResult(body.message || '连接成功', 'success');
    } catch (error) { showResult(error.message || '连接失败', 'error'); }
}

document.addEventListener('DOMContentLoaded', async () => {
    initAiAmbientAnimation();
    const from = new URLSearchParams(location.search).get('from');
    document.getElementById('ai-back-button').onclick = () => { location.href = PLATFORM_ROUTES[from] || '/'; };
    document.getElementById('ai-enabled').addEventListener('change', saveAiEnabledSetting);
    document.querySelectorAll('[data-platform]').forEach(input => input.addEventListener('change', () => {
        updatePlatformCount();
        savePlatformSettings();
    }));
    document.querySelectorAll('.ai-tab-button').forEach(button => button.addEventListener('click', () => openTab(button.dataset.tab)));
    openTab(PLATFORM_ROUTES[from] ? from : 'bili_message');
    document.getElementById('ai-save-button').addEventListener('click', saveSettings);
    document.getElementById('ai-test-button').addEventListener('click', testConnection);
    document.getElementById('ai-load-models-button').addEventListener('click', loadProviderModels);
    document.getElementById('ai-latency-button').addEventListener('click', testProviderLatency);
    document.getElementById('ai-handoff-platform').addEventListener('change', () => loadHandoffs());
    document.getElementById('ai-refresh-handoffs').addEventListener('click', () => loadHandoffs());
    document.getElementById('ai-human-handoff-enabled').addEventListener('change', saveHandoffSetting);
    document.getElementById('ai-knowledge-enabled').addEventListener('change', saveKnowledgeSwitchSettings);
    document.getElementById('ai-context-enabled').addEventListener('change', () => saveModelBooleanSetting('ai-context-enabled', 'context_enabled'));
    document.getElementById('ai-context-window').addEventListener('change', saveContextWindowSetting);
    document.getElementById('ai-auto-compress').addEventListener('change', () => saveModelBooleanSetting('ai-auto-compress', 'auto_compress'));
    document.getElementById('ai-model-select').addEventListener('change', event => {
        if (event.target.value) document.getElementById('ai-model').value = event.target.value;
    });
    document.getElementById('ai-knowledge-text').addEventListener('input', updateKnowledgeCharCount);
    document.getElementById('ai-new-knowledge-button').addEventListener('click', newKnowledgeBase);
    document.getElementById('ai-save-knowledge-button').addEventListener('click', () => saveCurrentKnowledgeBase().catch(error => showResult(error.message || '知识库保存失败', 'error')));
    document.getElementById('ai-knowledge-upload-button').addEventListener('click', () => document.getElementById('ai-knowledge-file').click());
    document.getElementById('ai-knowledge-file').addEventListener('change', event => uploadKnowledgeDocument(event.target.files[0]));
    const keyInput = document.getElementById('ai-api-key');
    keyInput.addEventListener('focus', () => {
        if (showingMaskedApiKey) keyInput.select();
    });
    keyInput.addEventListener('beforeinput', () => {
        if (showingMaskedApiKey) {
            keyInput.value = '';
            showingMaskedApiKey = false;
        }
    });
    loadKnowledgeConfig();
    try {
        const response = await fetch('/api/ai-config');
        const config = await response.json();
        savedAiEnabled = Boolean(config.enabled);
        document.getElementById('ai-enabled').checked = savedAiEnabled;
        document.getElementById('ai-format').value = config.format || 'openai';
        document.getElementById('ai-base-url').value = config.base_url || '';
        document.getElementById('ai-model').value = config.model || '';
        const modelSettings = config.model_settings || {};
        savedModelSettings = {...modelSettings};
        document.getElementById('ai-context-enabled').value = String(modelSettings.context_enabled !== false);
        document.getElementById('ai-context-window').value = modelSettings.context_window || 6000;
        document.getElementById('ai-auto-compress').value = String(modelSettings.auto_compress !== false);
        document.getElementById('ai-prohibited-words').value = (modelSettings.prohibited_words || []).join('，');
        savedHandoffEnabled = Boolean((config.human_handoff || {}).enabled);
        document.getElementById('ai-human-handoff-enabled').checked = savedHandoffEnabled;
        apiKeyConfigured = Boolean(config.api_key_configured);
        keyInput.value = apiKeyConfigured ? MASKED_API_KEY : '';
        showingMaskedApiKey = apiKeyConfigured;
        Object.entries(config.platforms || {}).forEach(([key, value]) => {
            const input = document.querySelector(`[data-platform="${key}"]`);
            if (input) input.checked = Boolean(value);
        });
        savedPlatforms = selectedPlatforms();
        updatePlatformCount();
    } catch (_) { showResult('暂时无法读取 AI 配置', 'error'); }
    loadHandoffs(true);
    handoffRefreshTimer = setInterval(() => {
        const panel = document.querySelector('[data-panel="handoff"]');
        loadHandoffs(Boolean(panel && panel.hidden));
    }, 15000);
});
