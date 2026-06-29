// Daily Presence Timeline module for RainBot Analytics user details
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
        return timestamp >= item[2] && timestamp < item[3];
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
    const currentChannelId = mainUserPresence ? mainUserPresence[4] : null;

    if (!currentChannelId) {
        channelLabelEl.innerText = 'Not in voice channel';
        channelLabelEl.className = 'text-[10px] text-gray-500 font-bold uppercase tracking-wider mt-0.5';
        usersEl.innerHTML = '<div class="text-[11px] text-gray-500 italic mt-0.5">No co-listeners</div>';
    } else {
        // Find channel name from rawHistory using channelsMapping
        const mainUserHistoryPeriod = rawHistory.find(item => {
            return timestamp >= item[1] && timestamp <= item[2];
        });
        const channelIdStr = (mainUserHistoryPeriod && mainUserHistoryPeriod[3]) ? String(mainUserHistoryPeriod[3]) : String(currentChannelId);
        const channelName = (typeof channelsMapping !== 'undefined' && channelsMapping[channelIdStr]) ? channelsMapping[channelIdStr] : (channelIdStr ? `Channel #${channelIdStr}` : 'N/A');

        channelLabelEl.innerText = `🔊 ${channelName}`;
        channelLabelEl.className = 'text-[10px] text-indigo-400 font-bold uppercase tracking-wider mt-0.5 truncate';

        // Find channel participants
        const participants = activeVoiceUsers.filter(item => {
            return item[4] === currentChannelId;
        });

        // Sort participants: current user first, then alphabetically by nickname
        participants.sort((a, b) => {
            const isAMain = String(a[0]) === String(typeof currentUserAccountId !== 'undefined' ? currentUserAccountId : '');
            const isBMain = String(b[0]) === String(typeof currentUserAccountId !== 'undefined' ? currentUserAccountId : '');
            
            if (isAMain && !isBMain) return -1;
            if (!isAMain && isBMain) return 1;
            
            const metaA = (typeof usersMetadata !== 'undefined' ? usersMetadata[a[0]] : null) || {};
            const metaB = (typeof usersMetadata !== 'undefined' ? usersMetadata[b[0]] : null) || {};
            const nameA = (metaA.nickname || '').toLowerCase();
            const nameB = (metaB.nickname || '').toLowerCase();
            return nameA.localeCompare(nameB);
        });

        if (participants.length === 0) {
            usersEl.innerHTML = '<div class="text-[11px] text-gray-500 italic mt-0.5">Alone in room</div>';
        } else {
            usersEl.innerHTML = '';
            participants.forEach(user => {
                const userId = String(user[0]);
                const isMainUser = userId === String(typeof currentUserAccountId !== 'undefined' ? currentUserAccountId : '');
                const userMeta = (typeof usersMetadata !== 'undefined' ? usersMetadata[userId] : null) || {};
                const nickname = userMeta.nickname || 'Unknown User';
                const stateInt = user[1];
                const stateStr = REVERSE_STATE_MAP[stateInt] || 'unknown';

                const userRow = document.createElement('div');
                userRow.className = `flex items-center justify-between text-[11px] py-0.5 ${isMainUser ? 'text-indigo-300 font-bold' : 'text-gray-300'}`;

                const nameContainer = document.createElement('div');
                nameContainer.className = 'flex items-center gap-1.5 min-w-0';

                const avatarCircle = document.createElement('div');
                avatarCircle.className = "w-4.5 h-4.5 rounded-full bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-[9px] font-extrabold text-indigo-400 select-none uppercase shrink-0";
                if (userMeta.avatar_url) {
                    const img = document.createElement('img');
                    img.src = userMeta.avatar_url;
                    img.className = 'w-full h-full rounded-full object-cover';
                    avatarCircle.appendChild(img);
                } else {
                    avatarCircle.innerText = nickname.slice(0, 1);
                }

                const nameSpan = document.createElement('span');
                nameSpan.className = 'truncate max-w-[110px]';
                nameSpan.innerText = nickname;

                nameContainer.appendChild(avatarCircle);
                nameContainer.appendChild(nameSpan);

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
                } else if (stateStr === 'voice_afk') {
                    statusContainer.innerHTML = `<span class="bg-pink-600/20 text-pink-400 text-[9px] font-extrabold px-1.5 py-0.5 rounded border border-pink-500/30 uppercase tracking-wider scale-90 origin-right">AFK</span>`;
                }

                userRow.appendChild(nameContainer);
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
    if (!track) return;
    track.innerHTML = '';

    const activeDateLabel = document.getElementById('active-date-label');
    if (activeDateLabel) {
        activeDateLabel.innerText = new Date(`${targetDateStr}T12:00:00`).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
    }

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
        const chIdStr = item[3] ? String(item[3]) : null;
        const chName = (chIdStr && typeof channelsMapping !== 'undefined' && channelsMapping[chIdStr]) ? channelsMapping[chIdStr] : (chIdStr ? `Channel #${chIdStr}` : 'N/A');

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

        if (tooltip) {
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
        }

        track.appendChild(segment);
    });
}

// Setup Timeline interaction listeners
document.addEventListener('DOMContentLoaded', () => {
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
});
