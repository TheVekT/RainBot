// Reverse backend status index mapping
const REVERSE_STATE_MAP = {
    0: "offline", 1: "online", 2: "voice_online",
    3: "voice_mute", 4: "voice_deaf", 5: "voice_afk", 6: "voice_alone"
};

const COLOR_MAP = {
    "offline": "#4b5563", "online": "#22c55e", "voice_online": "#06b6d4",
    "voice_mute": "#84cc16", "voice_deaf": "#ef4444", "voice_afk": "#ec4899", "voice_alone": "#8b5cf6"
};

let radarChartInstance = null;

// Custom ISO string generator ensuring compliance across locales
function getYYYYMMDD(date) {
    const yyyy = date.getFullYear();
    const mm = String(date.getMonth() + 1).padStart(2, '0');
    const dd = String(date.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
}

function formatTimeStr(dateObj) {
    return dateObj.toTimeString().split(' ')[0];
}

function formatDuration(seconds) {
    if (seconds <= 0) return '0s';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;

    if (h > 0) {
        return `${h}h${m > 0 ? `, ${m}m` : ''}`;
    }
    if (m > 0) {
        return `${m}m`;
    }
    return `${s}s`;
}

let currentTimelineDate = null;
let zoomStartTs = null;
let zoomEndTs = null;
let activeSliderTimestamp = null;
let isDraggingSlider = false;

function updateTimelineLabels(startTs, endTs) {
    const container = document.getElementById('timeline-labels');
    if (!container) return;
    container.innerHTML = '';

    const steps = 6;
    for (let i = 0; i <= steps; i++) {
        const ts = startTs + (endTs - startTs) * (i / steps);
        const date = new Date(ts * 1000);
        const hh = String(date.getHours()).padStart(2, '0');
        const mm = String(date.getMinutes()).padStart(2, '0');

        const span = document.createElement('span');
        span.innerText = `${hh}:${mm}`;
        container.appendChild(span);
    }
}

function updateSliderTooltip(timestamp, clientX) {
    const tooltip = document.getElementById('slider-tooltip');
    const timeEl = document.getElementById('slider-tooltip-time');
    const channelLabelEl = document.getElementById('slider-tooltip-channel-label');
    const usersEl = document.getElementById('slider-tooltip-users');

    if (!tooltip || !timeEl || !channelLabelEl || !usersEl) return;

    // Format timestamp as time string: HH:MM:SS
    const date = new Date(timestamp * 1000);
    const hh = String(date.getHours()).padStart(2, '0');
    const mm = String(date.getMinutes()).padStart(2, '0');
    const ss = String(date.getSeconds()).padStart(2, '0');
    timeEl.innerText = `${hh}:${mm}:${ss}`;

    // Find active voice users at this second (using half-open interval [start, end) to prevent transition overlaps)
    const activeVoiceUsersRaw = (typeof globalVoiceData !== 'undefined' ? globalVoiceData : []).filter(item => {
        return timestamp >= item[3] && timestamp < item[4];
    });

    // De-duplicate users by account_id to be absolutely sure no one is shown twice
    const seenUsers = new Set();
    const activeVoiceUsers = [];
    for (const user of activeVoiceUsersRaw) {
        const userId = String(user[0]);
        if (!seenUsers.has(userId)) {
            seenUsers.add(userId);
            activeVoiceUsers.push(user);
        }
    }

    // Find the main user's presence to get channel_id
    const mainUserPresence = activeVoiceUsers.find(item => String(item[0]) === String(typeof currentUserAccountId !== 'undefined' ? currentUserAccountId : ''));
    const currentChannelId = mainUserPresence ? mainUserPresence[5] : null;

    if (!currentChannelId) {
        channelLabelEl.innerText = 'Not in voice channel';
        channelLabelEl.className = 'text-[10px] text-gray-500 font-bold uppercase tracking-wider mt-0.5';
        usersEl.innerHTML = '<div class="text-[11px] text-gray-500 italic mt-0.5">No co-listeners</div>';
    } else {
        // Find channel name from rawHistory
        const mainUserHistoryPeriod = rawHistory.find(item => {
            return timestamp >= item[1] && timestamp <= item[2];
        });
        const channelName = (mainUserHistoryPeriod && mainUserHistoryPeriod[3]) ? mainUserHistoryPeriod[3] : `Channel #${currentChannelId}`;

        channelLabelEl.innerText = `🔊 ${channelName}`;
        channelLabelEl.className = 'text-[10px] text-indigo-400 font-bold uppercase tracking-wider mt-0.5 truncate';

        // Find channel participants
        const participants = activeVoiceUsers.filter(item => {
            return item[5] === currentChannelId;
        });

        // Sort participants: current user first, then alphabetically by nickname
        participants.sort((a, b) => {
            const isAMain = String(a[0]) === String(typeof currentUserAccountId !== 'undefined' ? currentUserAccountId : '');
            const isBMain = String(b[0]) === String(typeof currentUserAccountId !== 'undefined' ? currentUserAccountId : '');
            
            if (isAMain && !isBMain) return -1;
            if (!isAMain && isBMain) return 1;
            
            const nameA = (a[1] || '').toLowerCase();
            const nameB = (b[1] || '').toLowerCase();
            return nameA.localeCompare(nameB);
        });

        if (participants.length === 0) {
            usersEl.innerHTML = '<div class="text-[11px] text-gray-500 italic mt-0.5">Alone in room</div>';
        } else {
            usersEl.innerHTML = '';
            participants.forEach(user => {
                const isMainUser = String(user[0]) === String(typeof currentUserAccountId !== 'undefined' ? currentUserAccountId : '');
                const nickname = user[1] || 'Unknown User';
                const stateInt = user[2];
                const stateStr = REVERSE_STATE_MAP[stateInt] || 'unknown';

                const userRow = document.createElement('div');
                userRow.className = `flex items-center justify-between text-[11px] py-0.5 ${isMainUser ? 'text-indigo-300 font-bold' : 'text-gray-300'}`;

                const nameSpan = document.createElement('span');
                nameSpan.className = 'truncate max-w-[130px]';
                nameSpan.innerText = nickname;

                const statusContainer = document.createElement('div');
                statusContainer.className = 'flex items-center gap-1';

                const MIC_MUTE_SVG = `
                <svg class="w-3.5 h-3.5 text-red-500 inline-block" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="filter: drop-shadow(0 0 2px rgba(239, 68, 68, 0.4));">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                    <path stroke-linecap="round" stroke-linejoin="round" d="M3 3l18 18" stroke="#ef4444" stroke-width="2.5" />
                </svg>
                `;

                const DEAF_SVG = `
                <svg class="w-3.5 h-3.5 text-red-500 inline-block" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="filter: drop-shadow(0 0 2px rgba(239, 68, 68, 0.4));">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 18.5a6.5 6.5 0 01-6.5-6.5V11a6.5 6.5 0 1113 0v1a6.5 6.5 0 01-6.5 6.5z" />
                    <path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12h1.5a1.5 1.5 0 011.5 1.5v3a1.5 1.5 0 01-1.5 1.5H4.5A1.5 1.5 0 013 16.5v-3A1.5 1.5 0 014.5 12zM18 12h1.5a1.5 1.5 0 011.5 1.5v3a1.5 1.5 0 01-1.5 1.5H18a1.5 1.5 0 01-1.5-1.5v-3A1.5 1.5 0 0118 12z" />
                    <path stroke-linecap="round" stroke-linejoin="round" d="M3 3l18 18" stroke="#ef4444" stroke-width="2.5" />
                </svg>
                `;

                if (stateStr === 'voice_mute') {
                    statusContainer.innerHTML = MIC_MUTE_SVG;
                } else if (stateStr === 'voice_deaf') {
                    statusContainer.innerHTML = MIC_MUTE_SVG + DEAF_SVG;
                }

                userRow.appendChild(nameSpan);
                userRow.appendChild(statusContainer);

                usersEl.appendChild(userRow);
            });
        }
    }

    // Position tooltip
    const trackRect = document.getElementById('timeline-track').getBoundingClientRect();
    const tooltipWidth = 208; // w-52 is 208px

    const sliderLeft = clientX - trackRect.left;
    let tooltipLeft = sliderLeft - tooltipWidth / 2;

    // Clamp tooltipLeft within track boundaries to prevent screen overflow
    const minLeft = 0;
    const maxLeft = trackRect.width - tooltipWidth;
    tooltipLeft = Math.max(minLeft, Math.min(maxLeft, tooltipLeft));

    tooltip.style.left = `${tooltipLeft}px`;
    tooltip.classList.remove('hidden');

    // Adjust tooltip arrow to point exactly to the slider
    const arrow = document.getElementById('slider-tooltip-arrow');
    if (arrow) {
        const arrowLeft = sliderLeft - tooltipLeft;
        arrow.style.left = `${arrowLeft}px`;
    }
}

// --- TIMELINE CONTROLLER ---
function renderTimeline(targetDateStr) {
    if (currentTimelineDate !== targetDateStr) {
        currentTimelineDate = targetDateStr;
        zoomStartTs = null;
        zoomEndTs = null;
    }

    const track = document.getElementById('timeline-track');
    track.innerHTML = '';

    document.getElementById('active-date-label').innerText = new Date(`${targetDateStr}T12:00:00`).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });

    const localStart = new Date(`${targetDateStr}T00:00:00`);
    const localEnd = new Date(`${targetDateStr}T23:59:59.999`);

    const dayStartTs = Math.floor(localStart.getTime() / 1000);
    const dayEndTs = Math.floor(localEnd.getTime() / 1000);

    const viewStartTs = zoomStartTs !== null ? zoomStartTs : dayStartTs;
    const viewEndTs = zoomEndTs !== null ? zoomEndTs : dayEndTs;
    const viewDuration = viewEndTs - viewStartTs;

    updateTimelineLabels(viewStartTs, viewEndTs);

    const visiblePeriods = rawHistory.filter(item => item[1] < viewEndTs && item[2] > viewStartTs);

    if (visiblePeriods.length === 0) {
        track.innerHTML = `<div class="w-full h-full bg-gray-700/20 flex items-center justify-center text-xs text-gray-400">No presence logs available for this period</div>`;
        return;
    }

    const tooltip = document.getElementById('timeline-tooltip');

    visiblePeriods.forEach(item => {
        const stateStr = REVERSE_STATE_MAP[item[0]] || 'unknown';
        const startTs = item[1];
        const endTs = item[2];
        const chName = item[3] || 'N/A';

        const clampedStart = Math.max(startTs, viewStartTs);
        const clampedEnd = Math.min(endTs, viewEndTs);
        const duration = clampedEnd - clampedStart;

        if (duration <= 0) return;

        const leftPct = ((clampedStart - viewStartTs) / viewDuration) * 100;
        const widthPct = (duration / viewDuration) * 100;

        const segment = document.createElement('div');
        segment.style.position = 'absolute';
        segment.style.left = `${leftPct}%`;
        segment.style.width = `${widthPct}%`;
        segment.style.height = '100%';
        segment.style.backgroundColor = COLOR_MAP[stateStr] || '#4b5563';
        segment.className = 'cursor-crosshair border-r border-gray-950/10 timeline-segment-hover';

        const displayStart = formatTimeStr(new Date(clampedStart * 1000));
        const displayEnd = formatTimeStr(new Date(clampedEnd * 1000));

        segment.addEventListener('mouseenter', () => tooltip.classList.remove('hidden'));
        segment.addEventListener('mouseleave', () => tooltip.classList.add('hidden'));
        segment.addEventListener('mousemove', (e) => {
            tooltip.style.left = `${e.clientX + 15}px`;
            tooltip.style.top = `${e.clientY - 50}px`;

            tooltip.innerHTML = `
                <div class="font-bold text-indigo-400">${stateStr.replace('_', ' ').toUpperCase()}</div>
                ${chName !== 'N/A' ? `<div class="text-gray-300 font-medium">🔊 ${chName}</div>` : ''}
                <div class="text-gray-500 mt-0.5">${displayStart} — ${displayEnd}</div>
            `;
        });

        track.appendChild(segment);
    });

    // Update slider position if active
    const slider = document.getElementById('timeline-slider');
    const sliderTooltip = document.getElementById('slider-tooltip');
    if (slider) {
        if (activeSliderTimestamp !== null && activeSliderTimestamp >= viewStartTs && activeSliderTimestamp <= viewEndTs) {
            const pct = (activeSliderTimestamp - viewStartTs) / viewDuration;
            slider.style.left = `${pct * 100}%`;
            slider.classList.remove('hidden');
        } else {
            slider.classList.add('hidden');
            if (sliderTooltip) sliderTooltip.classList.add('hidden');
        }
    }
}

// --- RADAR CONTROLLER ---
function calculateAndRenderRadar(targetDateStr) {
    const activeSeconds = {
        "online": 0, "voice_online": 0, "voice_mute": 0, "voice_deaf": 0, "voice_afk": 0, "voice_alone": 0
    };

    const localStart = new Date(`${targetDateStr}T00:00:00`);
    const localEnd = new Date(`${targetDateStr}T23:59:59.999`);

    const viewStartTs = Math.floor(localStart.getTime() / 1000);
    const viewEndTs = Math.floor(localEnd.getTime() / 1000);

    rawHistory.forEach(item => {
        const stateStr = REVERSE_STATE_MAP[item[0]];
        if (stateStr && stateStr !== "offline" && activeSeconds[stateStr] !== undefined) {
            const startTs = item[1];
            const endTs = item[2];

            const clampedStart = Math.max(startTs, viewStartTs);
            const clampedEnd = Math.min(endTs, viewEndTs);
            const duration = clampedEnd - clampedStart;

            if (duration > 0) {
                activeSeconds[stateStr] += duration;
            }
        }
    });

    const labels = Object.keys(activeSeconds).map(s => s.replace('_', ' ').toUpperCase());
    const dataValues = Object.values(activeSeconds);

    // Populate day quick stats panel (if elements exist)
    const activeMins = Object.values(activeSeconds).reduce((a, b) => a + b, 0);
    const voiceMins = Object.entries(activeSeconds)
        .filter(([k]) => k.startsWith('voice'))
        .reduce((sum, [, val]) => sum + val, 0);

    const formatMins = (totalSecs) => {
        const h = Math.floor(totalSecs / 3600);
        const m = Math.round((totalSecs % 3600) / 60);
        if (h > 0) return `${h}h ${m}m`;
        return `${m} mins`;
    };

    const qsOnline = document.getElementById('qs-online-duration');
    const qsVoice = document.getElementById('qs-voice-duration');
    if (qsOnline) qsOnline.innerText = formatMins(activeSeconds.online + voiceMins);
    if (qsVoice) qsVoice.innerText = formatMins(voiceMins);

    const ctx = document.getElementById('radar-chart-canvas').getContext('2d');

    if (radarChartInstance) {
        radarChartInstance.destroy();
    }

    if (typeof Chart !== 'undefined' && Chart.register && Chart.Filler) {
        Chart.register(Chart.Filler);
    }

    const selDate = new Date(targetDateStr + 'T12:00:00');
    const dateStrFormatted = selDate.toLocaleDateString('en-US', { day: 'numeric', month: 'short' });

    const maxVal = Math.max(...dataValues, 600);
    const minVal = -0.15 * maxVal;

    radarChartInstance = new Chart(ctx, {
        type: 'radar',
        data: {
            labels: labels,
            datasets: [{
                label: `Activity on ${dateStrFormatted}`,
                data: dataValues,
                fill: 'start',
                spanGaps: true,
                backgroundColor: 'rgba(99, 102, 241, 0.22)',
                borderColor: 'rgba(99, 102, 241, 0.85)',
                borderWidth: 1.5,
                pointBackgroundColor: 'rgba(129, 140, 248, 1)',
                pointBorderColor: '#fff',
                pointRadius: dataValues.map(v => v > 0 ? 3 : 0),
                pointHoverRadius: dataValues.map(v => v > 0 ? 4 : 0)
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                r: {
                    min: minVal,
                    suggestedMax: 600,
                    grid: { color: 'rgba(75, 85, 99, 0.25)' },
                    angleLines: { color: 'rgba(75, 85, 99, 0.25)' },
                    pointLabels: { color: '#9ca3af', font: { family: 'Outfit', size: 9, weight: 'bold' } },
                    ticks: { display: false }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            const label = context.dataset.label || '';
                            const value = context.raw;
                            return `${label}: ${formatDuration(value)}`;
                        }
                    }
                }
            }
        }
    });
}

// --- HEATMAP CONTROLLER ---
function renderHeatmap() {
    const container = document.getElementById('heatmap-container');
    container.innerHTML = '';

    const dailyCoefficient = {};

    rawHistory.forEach(item => {
        const stateStr = REVERSE_STATE_MAP[item[0]];
        if (!stateStr || stateStr === 'offline') return;

        const startMs = item[1] * 1000;
        const dateKey = getYYYYMMDD(new Date(startMs));
        dailyCoefficient[dateKey] = (dailyCoefficient[dateKey] || 0) + (item[2] - item[1]);
    });

    const boxSize = 11;
    const gap = 3;
    const offsetX = 30; // Left offset for day labels
    const offsetY = 20; // Top offset for month labels
    const gridWidth = 53 * (boxSize + gap);
    const gridHeight = 7 * (boxSize + gap);
    const width = offsetX + gridWidth;
    const height = offsetY + gridHeight + 25; // Bottom offset for legend

    let svgHtml = `<svg viewBox="0 0 ${width} ${height}" class="w-full h-auto max-w-[780px] overflow-visible">`;

    const endDate = new Date();
    endDate.setHours(12, 0, 0, 0);
    endDate.setDate(endDate.getDate() + (6 - endDate.getDay())); // Align to nearest Saturday

    const startDate = new Date(endDate);
    startDate.setDate(endDate.getDate() - (53 * 7 - 1)); // Sunday 53 weeks ago

    const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    let lastMonthLabelWeek = -1;
    let monthLabelsHtml = '';

    let dayLabelsHtml = `
        <text x="25" y="${offsetY + 1 * 14 + 9}" font-size="9" fill="#9ca3af" font-family="Outfit" font-weight="500" text-anchor="end">Mon</text>
        <text x="25" y="${offsetY + 3 * 14 + 9}" font-size="9" fill="#9ca3af" font-family="Outfit" font-weight="500" text-anchor="end">Wed</text>
        <text x="25" y="${offsetY + 5 * 14 + 9}" font-size="9" fill="#9ca3af" font-family="Outfit" font-weight="500" text-anchor="end">Fri</text>
    `;

    let rectsHtml = '';

    const todayEnd = new Date();
    todayEnd.setHours(23, 59, 59, 999);

    const selectedDateVal = document.getElementById('timeline-date-picker').value;

    const currentCellDate = new Date(startDate);
    for (let w = 0; w < 53; w++) {
        const weekDate = new Date(startDate);
        weekDate.setDate(startDate.getDate() + w * 7);
        const monthIdx = weekDate.getMonth();

        if (w === 0 || (monthIdx !== new Date(startDate.getTime() + (w - 1) * 7 * 24 * 60 * 60 * 1000).getMonth() && w - lastMonthLabelWeek >= 3)) {
            const monthName = MONTHS[monthIdx];
            const labelX = offsetX + w * (boxSize + gap);
            monthLabelsHtml += `<text x="${labelX}" y="12" font-size="9" fill="#9ca3af" font-family="Outfit" font-weight="500">${monthName}</text>`;
            lastMonthLabelWeek = w;
        }

        for (let d = 0; d < 7; d++) {
            if (currentCellDate > todayEnd) {
                currentCellDate.setDate(currentCellDate.getDate() + 1);
                continue;
            }

            const dateKey = getYYYYMMDD(currentCellDate);

            const activeSeconds = dailyCoefficient[dateKey] || 0;
            const coefficient = Math.min(activeSeconds / 86400, 1.0);

            let fillStyle = '#1f2937';
            if (coefficient > 0) {
                fillStyle = `rgba(34, 197, 94, ${0.15 + coefficient * 0.85})`;
            }

            const x = offsetX + w * (boxSize + gap);
            const y = offsetY + d * (boxSize + gap);

            const isSelected = dateKey === selectedDateVal;
            const strokeColor = isSelected ? '#818cf8' : 'rgba(0,0,0,0.1)';
            const strokeWidth = isSelected ? '2' : '1';

            rectsHtml += `
                <rect 
                    x="${x}" y="${y}" width="${boxSize}" height="${boxSize}" rx="2" 
                    fill="${fillStyle}" stroke="${strokeColor}" stroke-width="${strokeWidth}"
                    class="transition-all duration-150 hover:stroke-indigo-400 cursor-pointer"
                    data-date="${dateKey}" data-hours="${(activeSeconds / 3600).toFixed(1)}"
                    data-w="${w}" data-d="${d}"
                />`;

            currentCellDate.setDate(currentCellDate.getDate() + 1);
        }
    }

    // Bottom Legend
    const legendStartX = width - 150;
    let legendHtml = `
        <text x="${legendStartX}" y="${offsetY + gridHeight + 18}" font-size="9" fill="#9ca3af" font-family="Outfit">Less</text>
    `;
    const legendColors = [
        '#1f2937',
        'rgba(34, 197, 94, 0.25)',
        'rgba(34, 197, 94, 0.5)',
        'rgba(34, 197, 94, 0.75)',
        'rgba(34, 197, 94, 1.0)'
    ];
    legendColors.forEach((color, idx) => {
        const lx = legendStartX + 30 + idx * 14;
        const ly = offsetY + gridHeight + 9;
        legendHtml += `<rect x="${lx}" y="${ly}" width="11" height="11" rx="2" fill="${color}" stroke="rgba(0,0,0,0.1)" stroke-width="1" />`;
    });
    const moreStartX = legendStartX + 30 + 5 * 14 + 5;
    legendHtml += `
        <text x="${moreStartX}" y="${offsetY + gridHeight + 18}" font-size="9" fill="#9ca3af" font-family="Outfit">More</text>
    `;

    svgHtml += monthLabelsHtml + dayLabelsHtml + rectsHtml + legendHtml + '</svg>';
    container.innerHTML = svgHtml;

    const svgElement = container.querySelector('svg');
    const lens = document.getElementById('heatmap-lens');
    const lensGrid = document.getElementById('lens-grid');

    function updateLens(clientX, clientY, targetElement) {
        const hoveredRect = targetElement && targetElement.tagName && targetElement.tagName.toLowerCase() === 'rect' && targetElement.getAttribute('data-date') ? targetElement : null;

        const svgRect = svgElement.getBoundingClientRect();
        const mouseX = clientX - svgRect.left;
        const mouseY = clientY - svgRect.top;

        const svgX = (mouseX / svgRect.width) * width;
        const svgY = (mouseY / svgRect.height) * height;

        const gridLeft = offsetX - 7;
        const gridRight = offsetX + 53 * 14 - 7;
        const gridTop = offsetY - 7;
        const gridBottom = offsetY + 7 * 14 - 7;

        if (svgX < gridLeft || svgX > gridRight || svgY < gridTop || svgY > gridBottom) {
            lens.classList.add('hidden');
            return;
        }

        let colCenter, rowCenter;
        if (hoveredRect) {
            colCenter = Number(hoveredRect.getAttribute('data-w'));
            rowCenter = Number(hoveredRect.getAttribute('data-d'));
        } else {
            const w = Math.round((svgX - offsetX) / 14);
            const d = Math.round((svgY - offsetY) / 14);
            colCenter = Math.max(0, Math.min(52, w));
            rowCenter = Math.max(0, Math.min(6, d));
        }

        const targetRect = svgElement.querySelector(`rect[data-w="${colCenter}"][data-d="${rowCenter}"]`);
        if (!targetRect) {
            lens.classList.add('hidden');
            return;
        }

        const rectBounds = targetRect.getBoundingClientRect();
        const cellWidth = rectBounds.width;
        const cellHeight = rectBounds.height;
        const stepX = cellWidth * (14 / 11);
        const stepY = cellHeight * (14 / 11);

        const centerCell_screenX = rectBounds.left + cellWidth / 2;
        const centerCell_screenY = rectBounds.top + cellHeight / 2;

        lens.classList.remove('hidden');
        lens.style.left = `${clientX - 88}px`;
        lens.style.top = `${clientY - 88}px`;

        lensGrid.innerHTML = '';

        const R_max = 44;

        const searchRadiusW = Math.ceil((R_max / (svgRect.width / width)) / 14) + 1;
        const searchRadiusD = Math.ceil((R_max / (svgRect.height / height)) / 14) + 1;

        for (let dw = -searchRadiusW; dw <= searchRadiusW; dw++) {
            for (let dd = -searchRadiusD; dd <= searchRadiusD; dd++) {
                const col = colCenter + dw;
                const row = rowCenter + dd;
                if (col < 0 || col >= 53 || row < 0 || row >= 7) continue;

                const cellRect = svgElement.querySelector(`rect[data-w="${col}"][data-d="${row}"]`);
                if (!cellRect) continue;

                const cellDateStr = cellRect.getAttribute('data-date');
                const cellFill = cellRect.getAttribute('fill');
                const cellDateObj = new Date(cellDateStr + 'T12:00:00');

                const dx = centerCell_screenX + dw * stepX - clientX;
                const dy = centerCell_screenY + dd * stepY - clientY;
                const R = Math.sqrt(dx * dx + dy * dy);

                if (R > R_max) continue;

                const r_max = 82;
                const ratio = R / R_max;
                const r = r_max * Math.sin(ratio * (Math.PI / 2));
                const theta = R === 0 ? 0 : Math.atan2(dy, dx);

                const lens_dx = r * Math.cos(theta);
                const lens_dy = r * Math.sin(theta);

                const baseSize = 9.0;
                const localMag = r_max * (Math.PI / (2 * R_max)) * Math.cos(ratio * (Math.PI / 2));
                const size = baseSize * localMag;
                const opacity = 1 - Math.pow(ratio, 4);

                const left = 88 + lens_dx - size / 2;
                const top = 88 + lens_dy - size / 2;

                const strokeColorVal = cellRect.getAttribute('stroke');
                const isSelected = strokeColorVal === '#818cf8' || cellRect.getAttribute('stroke-width') === '2';

                const monthsEn = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
                const cellText = `${cellDateObj.getDate()} ${monthsEn[cellDateObj.getMonth()]}`;

                const cellDiv = document.createElement('div');
                cellDiv.className = 'absolute flex flex-col items-center justify-center rounded text-white text-center shadow-inner transition-all duration-75 leading-none select-none';
                cellDiv.style.backgroundColor = cellFill;
                cellDiv.style.width = `${size}px`;
                cellDiv.style.height = `${size}px`;
                cellDiv.style.left = `${left}px`;
                cellDiv.style.top = `${top}px`;
                cellDiv.style.opacity = opacity;
                cellDiv.style.boxShadow = 'inset 0 0 4px rgba(255,255,255,0.2)';

                const theta_deg = theta * (180 / Math.PI);
                const tilt_angle = 42 * ratio;
                const z_disp = 12 * (1 - ratio * ratio);
                cellDiv.style.transform = `perspective(150px) translateZ(${z_disp}px) rotateZ(${theta_deg}deg) rotateY(${tilt_angle}deg) rotateZ(${-theta_deg}deg)`;

                const isHovered = hoveredRect && col === colCenter && row === rowCenter;

                if (isHovered) {
                    cellDiv.style.border = isSelected ? '2px solid #818cf8' : '1.5px solid rgba(255, 255, 255, 0.85)';
                    cellDiv.style.boxShadow = '0 0 10px rgba(255, 255, 255, 0.25), inset 0 0 4px rgba(255,255,255,0.2)';
                } else if (isSelected) {
                    cellDiv.style.border = '2px solid #818cf8';
                    cellDiv.style.boxShadow = 'inset 0 0 4px rgba(255,255,255,0.2)';
                } else {
                    cellDiv.style.border = '1px solid rgba(255, 255, 255, 0.15)';
                }

                if (size >= 18) {
                    const fontSize = Math.max(7.5, Math.min(10, 4.5 * localMag));
                    cellDiv.style.fontSize = `${fontSize}px`;
                    cellDiv.style.fontWeight = 'bold';
                    cellDiv.innerHTML = cellText.replace(' ', '<br/>');
                } else {
                    cellDiv.innerHTML = '';
                }

                lensGrid.appendChild(cellDiv);
            }
        }
    }

    svgElement.addEventListener('mousemove', (e) => {
        updateLens(e.clientX, e.clientY, e.target);
    });

    svgElement.addEventListener('mouseleave', () => {
        lens.classList.add('hidden');
    });

    svgElement.addEventListener('click', (e) => {
        const rect = e.target.closest('rect');
        if (rect && rect.getAttribute('data-date')) {
            const dateStr = rect.getAttribute('data-date');
            const picker = document.getElementById('timeline-date-picker');
            picker.value = dateStr;
            picker.dispatchEvent(new Event('change'));

            svgElement.querySelectorAll('rect').forEach(r => {
                if (r.getAttribute('data-date')) {
                    r.setAttribute('stroke', 'rgba(0,0,0,0.1)');
                    r.setAttribute('stroke-width', '1');
                }
            });
            rect.setAttribute('stroke', '#818cf8');
            rect.setAttribute('stroke-width', '2');

            updateLens(e.clientX, e.clientY, rect);
        }
    });
}

document.getElementById('timeline-date-picker').addEventListener('change', (e) => {
    const selectedDate = e.target.value;

    renderTimeline(selectedDate);
    calculateAndRenderRadar(selectedDate);

    // Format selected date nicely in English
    const selDate = new Date(selectedDate + 'T12:00:00');
    const options = { day: 'numeric', month: 'long', year: 'numeric' };
    document.getElementById('selected-date-display').innerText = selDate.toLocaleDateString('en-US', options);

    // Asynchronously fetch global voice topology mapping for the new date without reloading
    fetch(window.location.pathname + '?date=' + selectedDate + '&format=json')
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            // Overwrite global JS variable holding the daily server topology
            globalVoiceData = data;

            // If the slider is currently active/placed, update the tooltip to reflect the new day's co-presences
            if (activeSliderTimestamp !== null) {
                const slider = document.getElementById('timeline-slider');
                const track = document.getElementById('timeline-track');
                if (slider && track) {
                    const rect = track.getBoundingClientRect();
                    const localStart = new Date(`${selectedDate}T00:00:00`);
                    const localEnd = new Date(`${selectedDate}T23:59:59.999`);
                    const dayStartTs = Math.floor(localStart.getTime() / 1000);
                    const dayEndTs = Math.floor(localEnd.getTime() / 1000);

                    const currentViewStart = zoomStartTs !== null ? zoomStartTs : dayStartTs;
                    const currentViewEnd = zoomEndTs !== null ? zoomEndTs : dayEndTs;

                    const pct = (activeSliderTimestamp - currentViewStart) / (currentViewEnd - currentViewStart);
                    const clientX = rect.left + pct * rect.width;
                    updateSliderTooltip(activeSliderTimestamp, clientX);
                }
            }
        })
        .catch(err => {
            console.error('Error fetching global voice data:', err);
        });
});

const selectedDateDisp = document.getElementById('selected-date-display');
if (selectedDateDisp) {
    selectedDateDisp.addEventListener('click', () => {
        const picker = document.getElementById('timeline-date-picker');
        if (picker && typeof picker.showPicker === 'function') {
            picker.showPicker();
        }
    });
}

// Run Initializations
const initialDatePicker = document.getElementById('timeline-date-picker');
if (initialDatePicker) {
    initialDatePicker.value = getYYYYMMDD(new Date());
}
renderTimeline(initialDatePicker.value);

const initDateObj = new Date(initialDatePicker.value + 'T12:00:00');
document.getElementById('selected-date-display').innerText = initDateObj.toLocaleDateString('en-US', { day: 'numeric', month: 'long', year: 'numeric' });

calculateAndRenderRadar(initialDatePicker.value);
renderHeatmap();

// Timeline selection zoom and slider logic
const trackElement = document.getElementById('timeline-track');
const sliderElement = document.getElementById('timeline-slider');
const sliderTooltip = document.getElementById('slider-tooltip');

if (trackElement && sliderElement) {
    let isDraggingZoom = false;
    let zoomStartX = 0;
    let zoomOverlay = null;
    let trackMouseDownX = 0;

    trackElement.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;

        const rect = trackElement.getBoundingClientRect();
        trackMouseDownX = e.clientX;
        zoomStartX = e.clientX - rect.left;
        isDraggingZoom = true;

        zoomOverlay = document.createElement('div');
        zoomOverlay.style.position = 'absolute';
        zoomOverlay.style.top = '0';
        zoomOverlay.style.height = '100%';
        zoomOverlay.style.left = `${zoomStartX}px`;
        zoomOverlay.style.width = '0px';
        zoomOverlay.style.backgroundColor = 'rgba(99, 102, 241, 0.3)';
        zoomOverlay.style.borderLeft = '1px solid rgba(99, 102, 241, 0.6)';
        zoomOverlay.style.borderRight = '1px solid rgba(99, 102, 241, 0.6)';
        zoomOverlay.style.pointerEvents = 'none';
        zoomOverlay.style.zIndex = '10';
        trackElement.appendChild(zoomOverlay);

        e.preventDefault();
    });

    sliderElement.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        e.stopPropagation(); // Stop zoom drag from starting
        isDraggingSlider = true;
        e.preventDefault();
    });

    sliderElement.addEventListener('mouseenter', () => {
        if (activeSliderTimestamp !== null) {
            const rect = trackElement.getBoundingClientRect();
            const localStart = new Date(`${currentTimelineDate}T00:00:00`);
            const localEnd = new Date(`${currentTimelineDate}T23:59:59.999`);
            const dayStartTs = Math.floor(localStart.getTime() / 1000);
            const dayEndTs = Math.floor(localEnd.getTime() / 1000);

            const currentViewStart = zoomStartTs !== null ? zoomStartTs : dayStartTs;
            const currentViewEnd = zoomEndTs !== null ? zoomEndTs : dayEndTs;

            const pct = (activeSliderTimestamp - currentViewStart) / (currentViewEnd - currentViewStart);
            const clientX = rect.left + pct * rect.width;
            updateSliderTooltip(activeSliderTimestamp, clientX);
        }
    });

    sliderElement.addEventListener('mouseleave', () => {
        if (!isDraggingSlider && sliderTooltip) {
            sliderTooltip.classList.add('hidden');
        }
    });

    window.addEventListener('mousemove', (e) => {
        const rect = trackElement.getBoundingClientRect();

        if (isDraggingZoom && zoomOverlay) {
            const currentX = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
            const left = Math.min(zoomStartX, currentX);
            const width = Math.abs(zoomStartX - currentX);
            zoomOverlay.style.left = `${left}px`;
            zoomOverlay.style.width = `${width}px`;
        }

        if (isDraggingSlider) {
            const currentX = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
            sliderElement.style.left = `${(currentX / rect.width) * 100}%`;

            const localStart = new Date(`${currentTimelineDate}T00:00:00`);
            const localEnd = new Date(`${currentTimelineDate}T23:59:59.999`);
            const dayStartTs = Math.floor(localStart.getTime() / 1000);
            const dayEndTs = Math.floor(localEnd.getTime() / 1000);

            const currentViewStart = zoomStartTs !== null ? zoomStartTs : dayStartTs;
            const currentViewEnd = zoomEndTs !== null ? zoomEndTs : dayEndTs;
            const currentViewDur = currentViewEnd - currentViewStart;

            const pct = currentX / rect.width;
            activeSliderTimestamp = Math.floor(currentViewStart + currentViewDur * pct);

            updateSliderTooltip(activeSliderTimestamp, rect.left + currentX);
        }
    });

    window.addEventListener('mouseup', (e) => {
        const rect = trackElement.getBoundingClientRect();

        if (isDraggingZoom) {
            isDraggingZoom = false;

            if (zoomOverlay) {
                const overlayWidth = parseFloat(zoomOverlay.style.width);
                const overlayLeft = parseFloat(zoomOverlay.style.left);

                zoomOverlay.remove();
                zoomOverlay = null;

                const dragDistance = Math.abs(e.clientX - trackMouseDownX);

                if (dragDistance <= 8) {
                    // It's a click! Place the slider
                    const clickX = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
                    sliderElement.style.left = `${(clickX / rect.width) * 100}%`;
                    sliderElement.classList.remove('hidden');

                    const localStart = new Date(`${currentTimelineDate}T00:00:00`);
                    const localEnd = new Date(`${currentTimelineDate}T23:59:59.999`);
                    const dayStartTs = Math.floor(localStart.getTime() / 1000);
                    const dayEndTs = Math.floor(localEnd.getTime() / 1000);

                    const currentViewStart = zoomStartTs !== null ? zoomStartTs : dayStartTs;
                    const currentViewEnd = zoomEndTs !== null ? zoomEndTs : dayEndTs;
                    const currentViewDur = currentViewEnd - currentViewStart;

                    const pct = clickX / rect.width;
                    activeSliderTimestamp = Math.floor(currentViewStart + currentViewDur * pct);

                    updateSliderTooltip(activeSliderTimestamp, rect.left + clickX);
                } else if (overlayWidth > 10) {
                    // Zoom logic
                    const localStart = new Date(`${currentTimelineDate}T00:00:00`);
                    const localEnd = new Date(`${currentTimelineDate}T23:59:59.999`);
                    const dayStartTs = Math.floor(localStart.getTime() / 1000);
                    const dayEndTs = Math.floor(localEnd.getTime() / 1000);

                    const currentViewStart = zoomStartTs !== null ? zoomStartTs : dayStartTs;
                    const currentViewEnd = zoomEndTs !== null ? zoomEndTs : dayEndTs;
                    const currentViewDur = currentViewEnd - currentViewStart;

                    const leftPct = overlayLeft / rect.width;
                    const rightPct = (overlayLeft + overlayWidth) / rect.width;

                    const newStartTs = Math.floor(currentViewStart + currentViewDur * leftPct);
                    const newEndTs = Math.floor(currentViewStart + currentViewDur * rightPct);

                    if (newEndTs - newStartTs >= 60) {
                        zoomStartTs = newStartTs;
                        zoomEndTs = newEndTs;
                        renderTimeline(currentTimelineDate);
                    }
                }
            }
        }

        if (isDraggingSlider) {
            isDraggingSlider = false;
            // Hide tooltip if cursor is not over the slider element
            const rectSlider = sliderElement.getBoundingClientRect();
            const isHovering = (
                e.clientX >= rectSlider.left &&
                e.clientX <= rectSlider.right &&
                e.clientY >= rectSlider.top &&
                e.clientY <= rectSlider.bottom
            );
            if (!isHovering && sliderTooltip) {
                sliderTooltip.classList.add('hidden');
            }
        }
    });

    trackElement.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        // Right click resets zoom, hides slider
        zoomStartTs = null;
        zoomEndTs = null;
        activeSliderTimestamp = null;
        sliderElement.classList.add('hidden');
        if (sliderTooltip) sliderTooltip.classList.add('hidden');
        renderTimeline(currentTimelineDate);
    });
}
