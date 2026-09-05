document.addEventListener('DOMContentLoaded', function () {
    setupDocsBackLink();

    const tabGroups = document.querySelectorAll('.tabs');
    tabGroups.forEach(group => {
        group.addEventListener('click', e => {
            const btn = e.target.closest('.tab-btn');
            if (!btn) return;

            group.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const targetId = btn.getAttribute('data-target');
            if (!targetId) return;

            const section = group.parentElement;
            section.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            const targetPanel = section.querySelector('#' + targetId);
            if (targetPanel) targetPanel.classList.add('active');
        });
    });

    const sendDelayEl = document.getElementById('demo-send-delay');
    const checkIntervalEl = document.getElementById('demo-check-interval');
    const riskModeEl = document.getElementById('demo-risk-mode');
    const concurrencyEl = document.getElementById('demo-concurrency');
    if (sendDelayEl && checkIntervalEl) {
        const update = () => updateRiskDemo();
        sendDelayEl.addEventListener('input', update);
        checkIntervalEl.addEventListener('input', update);
        if (riskModeEl) riskModeEl.addEventListener('change', update);
        if (concurrencyEl) concurrencyEl.addEventListener('input', update);
        updateRiskDemo();
    }
});

function setupDocsBackLink() {
    const params = new URLSearchParams(window.location.search);
    const from = params.get('from') || '';
    const backLink = document.getElementById('docs-back-link');
    if (!backLink) return;

    const backTargets = {
        douyin: { href: '/douyin', label: '返回抖音私信' },
        comment: { href: '/comment', label: '返回 B 站评论' },
        message: { href: 'index.html', label: '返回 B 站私信' },
    };
    const target = backTargets[from];
    if (target) {
        backLink.href = target.href;
        backLink.textContent = target.label;
    }

    if (from === 'douyin' && !window.location.hash) {
        window.location.hash = 'douyin-mode';
    } else if (from === 'comment' && !window.location.hash) {
        window.location.hash = 'comment-mode';
    }

    scrollToDocsSection(window.location.hash);
}

function scrollToDocsSection(hash) {
    if (!hash) return;
    const target = document.querySelector(hash);
    if (!target) return;
    window.setTimeout(() => {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 120);
}

function runRuleDemo() {
    const input = document.getElementById('demo-message-input');
    const items = Array.from(document.querySelectorAll('.demo-rule-item'));
    const result = document.getElementById('demo-rule-result');
    if (!input || !result || items.length === 0) return;

    const text = (input.value || '').toLowerCase();
    items.forEach(i => i.classList.remove('hit'));

    let hitName = '';
    for (const item of items) {
        const raw = item.getAttribute('data-keywords') || '';
        const keywords = raw.split(',').map(k => k.trim().toLowerCase()).filter(Boolean);
        if (keywords.some(k => text.includes(k))) {
            item.classList.add('hit');
            hitName = item.textContent || '';
            break;
        }
    }

    if (hitName) {
        result.textContent = '结果：命中 ' + hitName;
    } else {
        result.textContent = '结果：未命中规则，将走默认回复（若已开启）';
    }
}

function updateRiskDemo() {
    const sendDelayEl = document.getElementById('demo-send-delay');
    const checkIntervalEl = document.getElementById('demo-check-interval');
    const riskModeEl = document.getElementById('demo-risk-mode');
    const concurrencyEl = document.getElementById('demo-concurrency');
    const bar = document.getElementById('risk-bar');
    const text = document.getElementById('risk-text');
    const kpiFrequency = document.getElementById('risk-kpi-frequency');
    const kpiSend = document.getElementById('risk-kpi-send');
    const causes = document.getElementById('risk-causes');
    const actions = document.getElementById('risk-actions');
    const impact = document.getElementById('risk-impact');
    if (!sendDelayEl || !checkIntervalEl || !bar || !text || !kpiFrequency || !kpiSend || !causes || !actions || !impact) return;

    const sendDelay = parseFloat(sendDelayEl.value);
    const checkInterval = parseFloat(checkIntervalEl.value);
    const mode = riskModeEl ? riskModeEl.value : 'message';
    const concurrency = concurrencyEl ? parseInt(concurrencyEl.value, 10) : 8;

    // 请求/发送估算
    const pollsPerHour = Math.round(3600 / checkInterval);
    const estimatedRequestsPerHour = pollsPerHour * Math.max(1, Math.round(concurrency / (mode === 'comment' ? 2 : 1)));
    const sendsPerHourCap = Math.round(3600 / sendDelay);

    // 风险评分：按模式和并发动态加权
    const sendSafeBase = mode === 'comment' ? 2.0 : 1.2;
    const checkSafeBase = mode === 'comment' ? 25 : 8;
    const sendRisk = Math.max(0, Math.min(1, (sendSafeBase - sendDelay) / sendSafeBase));
    const checkRisk = Math.max(0, Math.min(1, (checkSafeBase - checkInterval) / checkSafeBase));
    const concurrencyRisk = Math.max(0, Math.min(1, (concurrency - 8) / 24));
    const trafficRisk = Math.max(0, Math.min(1, (estimatedRequestsPerHour - 1200) / 2400));
    const score = Math.round((sendRisk * 0.42 + checkRisk * 0.28 + concurrencyRisk * 0.15 + trafficRisk * 0.15) * 100);

    bar.style.width = Math.max(8, score) + '%';
    if (score >= 70) {
        text.textContent = `风险评估：高风险（${score}分），建议增大发送/检测间隔`;
    } else if (score >= 40) {
        text.textContent = `风险评估：中风险（${score}分），建议继续观察日志`;
    } else {
        text.textContent = `风险评估：中低风险（${score}分），处于推荐区间`;
    }

    kpiFrequency.textContent = `每小时请求估算：${estimatedRequestsPerHour} 次（轮询 ${pollsPerHour} 次）`;
    kpiSend.textContent = `每小时发送上限估算：${sendsPerHourCap} 条`;

    const causeList = [];
    if (sendDelay < sendSafeBase) causeList.push(`发送间隔偏短（当前 ${sendDelay}s，建议 >= ${sendSafeBase}s）`);
    if (checkInterval < checkSafeBase) causeList.push(`检测间隔偏短（当前 ${checkInterval}s，建议 >= ${checkSafeBase}s）`);
    if (concurrency > 16) causeList.push(`并发对象偏多（当前 ${concurrency}）`);
    if (estimatedRequestsPerHour > 1800) causeList.push(`请求频次偏高（${estimatedRequestsPerHour}/h）`);
    causes.textContent = causeList.length ? causeList.join('，') : '参数处于较稳健区间，暂无明显高风险来源';

    const actionList = [];
    if (sendDelay < sendSafeBase) actionList.push(`将发送间隔提高到 ${sendSafeBase}-${sendSafeBase + 0.8}s`);
    if (checkInterval < checkSafeBase) actionList.push(`将检测间隔提高到 ${checkSafeBase}-${checkSafeBase + 20}s`);
    if (concurrency > 16) actionList.push('减少单轮处理对象数量，分批检测');
    if (actionList.length === 0) actionList.push('可小幅优化速度，每次仅调整一个参数并观察日志');
    actions.textContent = actionList.join('，');

    if (score >= 70) {
        impact.textContent = '可能影响：触发限流、发送失败率上升、短期内回复中断';
    } else if (score >= 40) {
        impact.textContent = '可能影响：偶发失败增多，需要持续监控 error 日志与重试情况';
    } else {
        impact.textContent = '可能影响：整体稳定，仍建议在峰值时段观察账号状态';
    }
}

function playFlowDemo() {
    const select = document.getElementById('flow-case-select');
    const status = document.getElementById('flow-status');
    const detail = document.getElementById('flow-detail');
    const log = document.getElementById('flow-log');
    const steps = Array.from(document.querySelectorAll('.flow-step'));
    if (!select || !status || !detail || !log || steps.length === 0) return;

    const scenarios = {
        'cooperation': {
            input: '用户私信：你好，想咨询合作报价',
            stepText: [
                '检测：收到新私信，会话时间戳晚于上次记录。',
                '过滤：通过（不是历史消息，且未超过单用户回复上限）。',
                '匹配：命中关键词“合作/报价”，使用“合作咨询回复”规则。',
                '发送：按发送间隔执行，回复成功并写入缓存。'
            ],
            logs: [
                '[INFO] 检测到新消息: 你好，想咨询合作报价',
                '[INFO] 消息通过过滤条件',
                '[SUCCESS] 规则命中: 合作咨询回复',
                '[SUCCESS] 回复发送成功，缓存已更新'
            ]
        },
        'default-reply': {
            input: '用户私信：在吗',
            stepText: [
                '检测：收到新私信，会话进入待处理队列。',
                '过滤：通过（消息为新消息）。',
                '匹配：未命中关键词规则，转入默认回复分支。',
                '发送：发送默认回复内容并记录日志。'
            ],
            logs: [
                '[INFO] 检测到新消息: 在吗',
                '[INFO] 消息通过过滤条件',
                '[INFO] 未命中规则，使用默认回复',
                '[SUCCESS] 默认回复发送成功'
            ]
        },
        'old-comment': {
            input: '评论：这个视频真不错（发表于系统启动前）',
            stepText: [
                '检测：评论被读取到待处理列表。',
                '过滤：命中“仅回复新评论”条件，被判定为历史评论。',
                '匹配：跳过（已在过滤阶段终止）。',
                '发送：不执行发送，仅记录跳过原因。'
            ],
            logs: [
                '[INFO] 检测到评论: 这个视频真不错',
                '[INFO] 仅回复新评论开启，评论时间早于启动时间',
                '[INFO] 本条评论已跳过',
                '[INFO] 本轮未发送回复'
            ]
        }
    };

    const scenario = scenarios[select.value] || scenarios['cooperation'];
    steps.forEach(s => s.classList.remove('active', 'done'));
    status.textContent = '状态：流程开始';
    detail.textContent = '输入示例：' + scenario.input;
    log.textContent = '[系统] 演示开始\n';

    let idx = 0;
    const tick = () => {
        if (idx > 0) steps[idx - 1].classList.remove('active');
        if (idx > 0) steps[idx - 1].classList.add('done');

        if (idx >= steps.length) {
            status.textContent = '状态：流程完成';
            return;
        }

        steps[idx].classList.add('active');
        status.textContent = `状态：执行第 ${idx + 1} 步`;
        detail.textContent = '步骤说明：' + scenario.stepText[idx];
        log.textContent += scenario.logs[idx] + '\n';
        idx += 1;
        setTimeout(tick, 850);
    };
    tick();
}
