// SVG multi-line chronology chart renderer for RainBot Analytics
function renderTimelineChart() {
    const svg = document.getElementById('timeline-svg-chart');
    const legend = document.getElementById('chart-legend-container');
    if (!svg || !legend) return;
    
    svg.innerHTML = '';
    legend.innerHTML = '';

    const localStart = new Date(`${currentDateString}T00:00:00`);
    const localEnd = new Date(`${currentDateString}T23:59:59.999`);
    const startTs = Math.floor(localStart.getTime() / 1000);
    const endTs = Math.floor(localEnd.getTime() / 1000);

    // Fetch active channels from global intervals
    const presentChannelsMap = new Map();
    globalVoiceData.forEach(item => {
        const chId = item[4];
        if (chId) {
            presentChannelsMap.set(chId, true);
        }
    });

    // Filter voice channels: active channels, or inactive channels that have voice records
    const filterChannels = allVoiceChannels.filter(ch => {
        return ch.is_active || presentChannelsMap.has(ch.channel_id);
    });

    // Build channel maps for fast mapping
    const channelsNameMap = new Map();
    allVoiceChannels.forEach(ch => {
        channelsNameMap.set(ch.channel_id, ch.name);
    });

    // 1. Calculate active users timeline counts (288 sampling steps - every 5 mins) using sweep-line peak concurrency
    const samplingSteps = 288;
    const timeInterval = (endTs - startTs) / samplingSteps;
    const channelsTimeValues = {};

    // Initialize matrices
    filterChannels.forEach(ch => {
        channelsTimeValues[ch.channel_id] = new Array(samplingSteps).fill(0);
    });

    let globalMaxCount = 5; // Minimum default boundary

    function getPeakConcurrency(items, rangeStart, rangeEnd) {
        const events = [];
        items.forEach(item => {
            events.push({ time: Math.max(item[2], rangeStart), type: 1 });
            events.push({ time: Math.min(item[3], rangeEnd), type: -1 });
        });
        events.sort((a, b) => {
            if (a.time !== b.time) return a.time - b.time;
            return a.type - b.type; // leaves (-1) before joins (1)
        });
        let maxActive = 0;
        let current = 0;
        events.forEach(ev => {
            current += ev.type;
            if (current > maxActive) {
                maxActive = current;
            }
        });
        return maxActive;
    }

    for (let s = 0; s < samplingSteps; s++) {
        const stepStart = startTs + s * timeInterval;
        const stepEnd = stepStart + timeInterval;

        // Filter active records in this step range
        const stepActive = globalVoiceData.filter(item => {
            return item[1] !== 0 && item[2] < stepEnd && item[3] > stepStart;
        });

        // Group by channel id
        const activeByChannel = {};
        stepActive.forEach(item => {
            const chId = item[4];
            if (chId) {
                if (!activeByChannel[chId]) activeByChannel[chId] = [];
                activeByChannel[chId].push(item);
            }
        });

        // Calculate peak concurrency for each channel in this step
        filterChannels.forEach(ch => {
            const chId = ch.channel_id;
            const items = activeByChannel[chId] || [];
            channelsTimeValues[chId][s] = getPeakConcurrency(items, stepStart, stepEnd);
        });
    }

    // Calculate global max count for scaling
    filterChannels.forEach(ch => {
        const max = Math.max(...channelsTimeValues[ch.channel_id]);
        if (max > globalMaxCount) globalMaxCount = max;
    });

    // Width/height bounds of SVG
    const rect = svg.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;
    const paddingBottom = 4;
    const paddingTop = 4;
    const chartHeight = height - paddingBottom - paddingTop;

    // Render background grid lines
    const gridLinesCount = 3;
    for (let i = 1; i <= gridLinesCount; i++) {
        const yVal = paddingTop + (chartHeight * (i / (gridLinesCount + 1)));
        const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
        line.setAttribute("x1", "0");
        line.setAttribute("y1", yVal);
        line.setAttribute("x2", "100%");
        line.setAttribute("y2", yVal);
        line.setAttribute("stroke", "rgba(75, 85, 99, 0.15)");
        line.setAttribute("stroke-width", "1");
        svg.appendChild(line);
    }

    // Draw line for each channel (EXCLUDING deleted/inactive channels from graph-timeline!)
    const activeDrawChannels = filterChannels.filter(ch => ch.is_active);

    const isToday = (currentDateString === todayDateStr);
    let maxDrawTs = endTs;
    if (isToday) {
        let maxRecordTs = startTs;
        globalVoiceData.forEach(item => {
            if (item[3] > maxRecordTs) {
                maxRecordTs = item[3];
            }
        });
        maxDrawTs = Math.min(maxRecordTs, Math.floor(Date.now() / 1000));
        if (maxDrawTs < startTs) maxDrawTs = startTs;
    }
    // Share with main script guides calculations
    window.maxDrawTs = maxDrawTs;

    activeDrawChannels.forEach((ch, idx) => {
        const chId = ch.channel_id;
        const chColor = getChannelColor(chId, idx);
        const values = channelsTimeValues[chId];

        // Build SVG path points representation
        let pathPoints = [];
        for (let s = 0; s < samplingSteps; s++) {
            const stepStart = startTs + s * timeInterval;
            if (isToday && stepStart > maxDrawTs) {
                break;
            }
            const x = (s / (samplingSteps - 1)) * width;
            const y = height - paddingBottom - (values[s] / globalMaxCount) * chartHeight;
            pathPoints.push(`${x},${y}`);
        }

        if (pathPoints.length > 0) {
            // Render path
            const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
            path.setAttribute("d", `M ${pathPoints.join(" L ")}`);
            path.setAttribute("fill", "none");
            path.setAttribute("stroke", chColor);
            path.setAttribute("stroke-width", "2");
            path.setAttribute("stroke-linejoin", "round");
            path.setAttribute("stroke-linecap", "round");
            path.setAttribute("class", "channel-path cursor-pointer");
            path.setAttribute("id", `chart-path-${chId}`);
            path.style.opacity = "0.85";

            // Setup line hover effects
            path.addEventListener('mouseenter', () => highlightChannel(chId));
            path.addEventListener('mouseleave', () => unhighlightChannel());

            svg.appendChild(path);
        }

        // Add legend chip
        const legendChip = document.createElement('div');
        legendChip.className = "flex items-center gap-2 px-3 py-1.5 rounded-xl bg-gray-900/60 cursor-pointer select-none transition-all hover:bg-gray-800/80";
        legendChip.innerHTML = `
            <span class="w-2.5 h-2.5 rounded-full" style="background-color: ${chColor};"></span>
            <span class="text-xs text-gray-300 font-semibold truncate max-w-[120px]">${ch.name}</span>
        `;
        legendChip.addEventListener('mouseenter', () => highlightChannel(chId));
        legendChip.addEventListener('mouseleave', () => unhighlightChannel());
        legend.appendChild(legendChip);
    });

    // Store values and scales globally for custom hover tooltip access
    window.timelineChannels = activeDrawChannels;
    window.timelineValues = channelsTimeValues;
    window.channelsNameMap = channelsNameMap;
    window.globalMaxCount = globalMaxCount;
}

// Highlight/dim functions
function highlightChannel(channelId) {
    highlightedChannelId = channelId;
    const paths = document.querySelectorAll('.channel-path');
    const targetColor = getChannelColor(channelId);

    paths.forEach(p => {
        const id = p.getAttribute('id').replace('chart-path-', '');
        if (id === channelId) {
            p.setAttribute('stroke-width', '3.5');
            p.style.opacity = '1.0';
        } else {
            p.style.opacity = '0.15';
        }
    });

    // Update sidebar channel list highlights
    const sidebarCards = document.querySelectorAll('.room-card-wrapper');
    sidebarCards.forEach(card => {
        const id = card.getAttribute('data-channel-id');
        if (card.style.maxHeight !== '0px') {
            if (id === channelId) {
                card.classList.add('channel-card-highlight');
                card.style.setProperty('--highlight-color', `${targetColor}40`);
                card.style.setProperty('--shadow-color', `${targetColor}25`);
                card.style.opacity = '1.0';
            } else {
                card.style.opacity = '0.4';
            }
        }
    });
}

function unhighlightChannel() {
    highlightedChannelId = null;
    const paths = document.querySelectorAll('.channel-path');
    paths.forEach(p => {
        p.setAttribute('stroke-width', '2');
        p.style.opacity = '0.85';
    });

    const sidebarCards = document.querySelectorAll('.room-card-wrapper');
    sidebarCards.forEach(card => {
        card.classList.remove('channel-card-highlight');
        if (card.style.maxHeight !== '0px') {
            card.style.opacity = '1.0';
        }
    });
}
