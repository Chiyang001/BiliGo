const PLATFORM_ASSETS = {
    bili_message: 'bilibili.png', bili_comment: 'bilibili.png', douyin: 'tik-tok.png',
    xiaohongshu: 'xiaohongshu-seeklogo.png', weibo: 'sina-weibo-seeklogo.png',
    xianyu: 'xianyu.jpg',
};
const RETURN_TARGETS = {
    bili_message: '/', bili_comment: '/comment', douyin: '/douyin',
    xiaohongshu: '/xiaohongshu', weibo: '/weibo',
    xianyu: '/xianyu',
};
let selectedRange = '30d';
let dashboardData = null;
let refreshTimer = null;
let requestSequence = 0;

document.addEventListener('DOMContentLoaded', () => {
    const source = new URLSearchParams(location.search).get('from');
    setupHeroMotion();
    document.getElementById('dashboard-back').onclick = () => { location.href = RETURN_TARGETS[source] || '/'; };
    document.querySelectorAll('[data-range]').forEach(button => button.addEventListener('click', () => {
        if (button.dataset.range === selectedRange) return;
        selectedRange = button.dataset.range;
        document.querySelectorAll('[data-range]').forEach(item => item.classList.toggle('active', item === button));
        loadDashboard(false);
    }));
    document.getElementById('refresh-dashboard').onclick = () => loadDashboard(false);
    loadDashboard(true);
    refreshTimer = setInterval(() => { if (!document.hidden) loadDashboard(false); }, 30000);
});

function setupHeroMotion() {
    const hero = document.querySelector('.overview-hero');
    const canvas = document.getElementById('dashboard-ambient-canvas');
    if (!hero || !canvas) return;
    const context = canvas.getContext('2d');
    if (!context) return;
    const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
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
            phase: (index / Math.max(count, 1)) * Math.PI * 2,
        };
    }

    function resize() {
        const bounds = hero.getBoundingClientRect();
        width = Math.max(1, Math.round(bounds.width));
        height = Math.max(1, Math.round(bounds.height));
        const ratio = Math.min(devicePixelRatio || 1, 1.75);
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
        const bounds = hero.getBoundingClientRect();
        pointer.x = event.clientX - bounds.left;
        pointer.y = event.clientY - bounds.top;
        pointer.active = true;
        hero.style.setProperty('--dashboard-pointer-x', `${(pointer.x / bounds.width) * 100}%`);
        hero.style.setProperty('--dashboard-pointer-y', `${(pointer.y / bounds.height) * 100}%`);
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

async function loadDashboard(initial) {
    const sequence = ++requestSequence;
    const requestedRange = selectedRange;
    const refresh = document.getElementById('refresh-dashboard');
    refresh.classList.add('refreshing');
    if (initial) document.body.classList.add('is-loading');
    try {
        const response = await fetch(`/api/dashboard?range=${encodeURIComponent(requestedRange)}`, {cache: 'no-store'});
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const result = await response.json();
        if (sequence !== requestSequence || requestedRange !== selectedRange) return;
        dashboardData = result;
        renderDashboard(dashboardData);
        document.querySelector('.sync-state').classList.remove('error');
        document.getElementById('sync-label').textContent = '自动同步';
    } catch (error) {
        if (sequence !== requestSequence) return;
        document.querySelector('.sync-state').classList.add('error');
        document.getElementById('sync-label').textContent = '同步失败';
        renderFetchError();
    } finally {
        if (sequence === requestSequence) {
            document.body.classList.remove('is-loading');
            refresh.classList.remove('refreshing');
        }
    }
}

function renderDashboard(data) {
    animateValue('kpi-total', data.summary.total_replies);
    animateValue('kpi-inbound', data.summary.period_inbound);
    animateValue('kpi-rate', data.summary.success_rate, '%');
    document.getElementById('kpi-running').textContent = `${data.summary.running_platforms}/${(data.platforms || []).length}`;
    document.getElementById('kpi-outcome').textContent = `成功 ${formatNumber(data.summary.period_success)} · 失败 ${formatNumber(data.summary.period_failure)}`;
    document.getElementById('kpi-range-label').textContent = rangeLabel(data.range.key);
    document.getElementById('last-updated').textContent = `更新于 ${formatTime(data.generated_at)}`;
    renderTrend(data.series || []);
    renderComparison(data.platforms || []);
    renderPlatforms(data.platforms || []);
}

function animateValue(id, target, suffix = '') {
    const element = document.getElementById(id);
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const end = Number(target) || 0;
    if (reduce) { element.textContent = `${formatNumber(end)}${suffix}`; return; }
    const start = Number(element.dataset.value || 0);
    const begun = performance.now();
    const frame = now => {
        const progress = Math.min(1, (now - begun) / 520);
        const value = start + (end - start) * (1 - Math.pow(1 - progress, 3));
        element.textContent = `${suffix ? value.toFixed(1).replace('.0','') : formatNumber(Math.round(value))}${suffix}`;
        if (progress < 1) requestAnimationFrame(frame); else element.dataset.value = String(end);
    };
    requestAnimationFrame(frame);
}

function compressSeries(series, maximum = 90) {
    if (series.length <= maximum) return series;
    const size = Math.ceil(series.length / maximum);
    const result = [];
    for (let index = 0; index < series.length; index += size) {
        const group = series.slice(index, index + size);
        result.push({date: group[group.length - 1].date, inbound: sum(group,'inbound'), success: sum(group,'success'), failure: sum(group,'failure')});
    }
    return result;
}

function renderTrend(rawSeries) {
    const container = document.getElementById('trend-chart');
    const series = compressSeries(rawSeries);
    if (!series.length) { container.innerHTML = '<div class="empty-chart">暂无趋势数据</div>'; return; }
    const width = 760, height = 270, left = 38, right = 16, top = 18, bottom = 34;
    const plotWidth = width - left - right, plotHeight = height - top - bottom;
    const max = Math.max(1, ...series.flatMap(item => [item.inbound, item.success, item.failure]));
    const x = index => left + (series.length === 1 ? plotWidth / 2 : index * plotWidth / (series.length - 1));
    const y = value => top + plotHeight - value * plotHeight / max;
    const tickValues = max <= 4 ? Array.from({length: max + 1}, (_, index) => index) : [0,.25,.5,.75,1].map(part => Math.round(max * part));
    const grid = [...new Set(tickValues)].map(value => `<line class="grid-line" x1="${left}" y1="${y(value)}" x2="${width-right}" y2="${y(value)}"/><text class="axis-label" x="${left-8}" y="${y(value)+3}" text-anchor="end">${value}</text>`).join('');
    const definitions = [
        ['inbound','#7594bd'], ['success','#b58b34'], ['failure','#ca5b62'],
    ];
    const paths = definitions.map(([key,color]) => {
        const points = series.map((item,index) => `${x(index)},${y(item[key])}`);
        const path = `M ${points.join(' L ')}`;
        const area = `${path} L ${x(series.length-1)},${top+plotHeight} L ${x(0)},${top+plotHeight} Z`;
        const dots = series.map((item,index) => `<g class="chart-point" tabindex="0" data-tip="${formatDate(item.date)} · 收到 ${item.inbound} · 成功 ${item.success} · 失败 ${item.failure}" transform="translate(${x(index)} ${y(item[key])})"><circle r="10" fill="transparent"/><circle class="visible" r="2.6" fill="${color}"/></g>`).join('');
        return `${key === 'success' ? `<path class="trend-area" d="${area}" fill="${color}"/>` : ''}<path class="trend-line" d="${path}" stroke="${color}"/>${dots}`;
    }).join('');
    const labels = series.map((item,index) => index % Math.max(1,Math.ceil(series.length/6)) === 0 || index === series.length-1 ? `<text class="axis-label" x="${x(index)}" y="${height-8}" text-anchor="middle">${formatShortDate(item.date)}</text>` : '').join('');
    container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" aria-hidden="true">${grid}${paths}${labels}</svg>`;
    container.setAttribute('aria-label', `${rangeLabel(selectedRange)}共收到 ${sum(series,'inbound')} 条，成功回复 ${sum(series,'success')} 条，失败 ${sum(series,'failure')} 条`);
    bindTooltips(container);
}

function renderComparison(platforms) {
    const container = document.getElementById('platform-chart');
    const width = 520, height = 270, left = 82, right = 25, top = 22, rowHeight = 47;
    const max = Math.max(1, ...platforms.flatMap(item => [item.inbound,item.success]));
    const plotWidth = width - left - right;
    const rows = platforms.map((item,index) => {
        const y = top + index * rowHeight;
        const inbound = item.inbound * plotWidth / max;
        const success = item.success * plotWidth / max;
        return `<text class="axis-label" x="${left-9}" y="${y+15}" text-anchor="end">${escapeHtml(item.name.replace('私信',''))}</text><rect x="${left}" y="${y}" width="${plotWidth}" height="9" rx="4" fill="#eef2f6"/><rect class="comparison-bar" x="${left}" y="${y}" width="${inbound}" height="9" rx="4" fill="#7594bd"/><rect class="comparison-bar" x="${left}" y="${y+14}" width="${success}" height="9" rx="4" fill="#b58b34"/><text class="axis-label" x="${Math.min(width-right, left+Math.max(inbound,success)+7)}" y="${y+18}">${item.inbound}/${item.success}</text>`;
    }).join('');
    container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" aria-hidden="true">${rows}</svg>`;
    container.setAttribute('aria-label', platforms.map(item => `${item.name}收到${item.inbound}条，成功${item.success}条`).join('；'));
}

function renderPlatforms(platforms) {
    const grid = document.getElementById('platform-grid');
    grid.replaceChildren(...platforms.map(item => {
        const card = document.createElement('article');
        card.className = `platform-card ${item.state}`;
        const activity = item.last_activity ? formatTime(new Date(item.last_activity * 1000).toISOString()) : '暂无活动';
        card.innerHTML = `<div class="platform-title"><img class="platform-icon" src="${PLATFORM_ASSETS[item.id]}" alt=""><div><strong>${escapeHtml(item.name)}</strong><span class="platform-state"><i></i>${escapeHtml(item.state_label)}</span></div></div><div class="platform-metrics"><div><span>收到 / 成功</span><strong>${formatNumber(item.inbound)} / ${formatNumber(item.success)}</strong></div><div><span>触达用户</span><strong>${formatNumber(item.contacts)}</strong></div><div><span>成功率</span><strong>${item.success_rate}%</strong></div><div><span>回复规则</span><strong>${formatNumber(item.rules_count)}</strong></div></div><p class="platform-meta">最后活动 ${activity}${item.account_count > 1 ? ` · ${item.account_count} 个账号` : ''}</p>`;
        return card;
    }));
}

function bindTooltips(container) {
    const tooltip = document.getElementById('chart-tooltip');
    const show = event => {
        const target = event.currentTarget;
        const box = target.getBoundingClientRect();
        tooltip.textContent = target.dataset.tip;
        tooltip.style.left = `${box.left + box.width/2}px`;
        tooltip.style.top = `${box.top}px`;
        tooltip.classList.add('show');
    };
    container.querySelectorAll('[data-tip]').forEach(point => {
        point.addEventListener('pointerenter', show); point.addEventListener('focus', show);
        point.addEventListener('pointerleave', () => tooltip.classList.remove('show'));
        point.addEventListener('blur', () => tooltip.classList.remove('show'));
    });
}

function renderFetchError() {
    document.getElementById('sync-label').textContent = '同步失败，请重试';
}
function sum(items,key) { return items.reduce((total,item) => total + (Number(item[key]) || 0), 0); }
function formatNumber(value) { return new Intl.NumberFormat('zh-CN').format(Number(value) || 0); }
function rangeLabel(value) { return ({'7d':'最近 7 天','30d':'最近 30 天','90d':'最近 90 天','all':'全部时间'})[value] || '最近 30 天'; }
function formatDate(value) { return new Intl.DateTimeFormat('zh-CN',{month:'short',day:'numeric'}).format(new Date(`${value}T00:00:00`)); }
function formatShortDate(value) { const [,month,day] = value.split('-'); return `${Number(month)}/${Number(day)}`; }
function formatTime(value) { const date = new Date(value); return Number.isNaN(date.getTime()) ? '刚刚' : new Intl.DateTimeFormat('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}).format(date); }
function escapeHtml(value) { const node = document.createElement('span'); node.textContent = String(value ?? ''); return node.innerHTML; }
