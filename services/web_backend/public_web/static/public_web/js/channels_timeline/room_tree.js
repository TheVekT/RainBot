// Server Voice Rooms list tree manager for RainBot Analytics chronology
function renderChannelTree(targetTs) {
    // 1. Group active users in voice channels at this second (using [start, end) interval range)
    const activeVoiceUsers = globalVoiceData.filter(item => {
        return item[1] !== 0 && targetTs >= item[2] && targetTs < item[3];
    });

    // Map listeners by channels mapping
    const listenersByChannel = {};
    activeVoiceUsers.forEach(item => {
        const chId = item[4];
        if (chId) {
            if (!listenersByChannel[chId]) listenersByChannel[chId] = [];
            listenersByChannel[chId].push(item);
        }
    });

    // SVGs
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

    let totalActiveRooms = 0;

    allVoiceChannels.forEach(ch => {
        const chId = ch.channel_id;
        const roomWrapper = document.querySelector(`.room-card-wrapper[data-channel-id="${chId}"]`);
        if (!roomWrapper) return;

        const listeners = listenersByChannel[chId] || [];
        const isVisible = ch.is_active || listeners.length > 0;

        if (isVisible) {
            totalActiveRooms++;
            
            // Expand styles: explicit height, padding, margin, opacity
            const calculatedWrapperHeight = 46 + (listeners.length > 0 ? 10 + 28 * listeners.length : 0);
            roomWrapper.style.maxHeight = `${calculatedWrapperHeight}px`;
            roomWrapper.style.padding = '12px';
            roomWrapper.style.marginBottom = '8px'; // Reduced gap between channels
            roomWrapper.style.opacity = '1';
            roomWrapper.style.borderColor = 'rgba(31, 41, 55, 0.4)'; // border-gray-800/40

            if (highlightedChannelId !== null && highlightedChannelId !== chId) {
                roomWrapper.style.opacity = '0.4';
            } else if (highlightedChannelId === chId) {
                roomWrapper.classList.add('channel-card-highlight');
                const targetColor = getChannelColor(chId);
                roomWrapper.style.setProperty('--highlight-color', `${targetColor}40`);
                roomWrapper.style.setProperty('--shadow-color', `${targetColor}25`);
                roomWrapper.style.opacity = '1.0';
            } else {
                roomWrapper.classList.remove('channel-card-highlight');
                roomWrapper.style.opacity = '1.0';
            }

            // Update badge count
            const badgeCount = roomWrapper.querySelector('.text-\\[10px\\]');
            if (badgeCount) badgeCount.innerText = listeners.length;

            // Re-render users container
            const usersContainer = roomWrapper.querySelector('.users-container');
            if (usersContainer) {
                if (listeners.length === 0) {
                    usersContainer.innerHTML = '';
                    usersContainer.style.maxHeight = '0px';
                    usersContainer.style.opacity = '0';
                    usersContainer.style.marginTop = '0px';
                } else {
                    // Sort users
                    listeners.sort((a, b) => {
                        const metaA = usersMetadata[a[0]] || {};
                        const metaB = usersMetadata[b[0]] || {};
                        const nicknameA = metaA.nickname || 'Unknown User';
                        const nicknameB = metaB.nickname || 'Unknown User';
                        return nicknameA.localeCompare(nicknameB);
                    });

                    usersContainer.innerHTML = '';
                    listeners.forEach(user => {
                        const userId = user[0];
                        const userMeta = usersMetadata[userId] || {};
                        const nickname = userMeta.nickname || 'Unknown User';

                        const userRow = document.createElement('div');
                        userRow.className = "flex items-center justify-between text-[11px] py-1 text-gray-300 hover:text-white transition-colors user-row-fade";
                        
                        const profileBlock = document.createElement('a');
                        profileBlock.href = `/users/${userId}/`;
                        profileBlock.className = "flex items-center gap-2 min-w-0 hover:text-indigo-400 transition-colors cursor-pointer";

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

                        const userNickname = document.createElement('span');
                        userNickname.className = "font-medium truncate";
                        userNickname.innerText = nickname;

                        profileBlock.appendChild(avatarCircle);
                        profileBlock.appendChild(userNickname);
                        userRow.appendChild(profileBlock);

                        const statusContainer = document.createElement('div');
                        statusContainer.className = "flex items-center gap-1.5 pr-0.5";

                        const stateStr = REVERSE_STATE_MAP[user[1]] || 'unknown';
                        if (stateStr === 'voice_mute') {
                            statusContainer.innerHTML = MIC_MUTE_SVG;
                        } else if (stateStr === 'voice_deaf') {
                            statusContainer.innerHTML = MIC_MUTE_SVG + DEAF_SVG;
                        } else if (stateStr === 'voice_afk') {
                            statusContainer.innerHTML = `<span class="bg-pink-600/20 text-pink-400 text-[8.5px] font-extrabold px-1.5 py-0.5 rounded border border-pink-500/30 uppercase tracking-wider scale-90">AFK</span>`;
                        }

                        userRow.appendChild(statusContainer);
                        usersContainer.appendChild(userRow);
                    });

                    // Expand users container
                    usersContainer.style.marginTop = '8px';
                    const calculatedMaxHeight = 28 * listeners.length + 10;
                    usersContainer.style.maxHeight = `${calculatedMaxHeight}px`;
                    usersContainer.style.opacity = '1';
                }
            }
        } else {
            // Collapse styles: explicit height, padding, margin, opacity
            roomWrapper.style.maxHeight = '0px';
            roomWrapper.style.padding = '0px';
            roomWrapper.style.marginBottom = '0px';
            roomWrapper.style.opacity = '0';
            roomWrapper.style.borderColor = 'transparent';

            const usersContainer = roomWrapper.querySelector('.users-container');
            if (usersContainer) {
                usersContainer.style.maxHeight = '0px';
                usersContainer.style.opacity = '0';
                usersContainer.style.marginTop = '0px';
            }
        }
    });

    // If all rooms are collapsed, show placeholder
    const placeholder = document.getElementById('no-rooms-placeholder');
    if (totalActiveRooms === 0) {
        if (!placeholder) {
            const ph = document.createElement('div');
            ph.id = 'no-rooms-placeholder';
            ph.className = 'h-64 flex flex-col items-center justify-center text-center p-4 user-row-fade';
            ph.innerHTML = `
                <span class="text-3xl">🔇</span>
                <div class="text-sm font-semibold text-gray-400 mt-3">No Voice Channels Recorded</div>
                <div class="text-xs text-gray-500 mt-1">Both active rooms list and activity database ranges are empty.</div>
            `;
            document.getElementById('channel-tree-list').appendChild(ph);
        }
    } else {
        if (placeholder) placeholder.remove();
    }
}

// Instantiate channel components inside sidebar list layout once on initial load
function initializeDOMRooms() {
    const container = document.getElementById('channel-tree-list');
    if (!container) return;
    container.innerHTML = '';

    allVoiceChannels.forEach((ch, idx) => {
        const chId = ch.channel_id;
        
        const roomWrapper = document.createElement('div');
        roomWrapper.className = "room-card-wrapper border rounded-xl bg-gray-900/35 transition-all duration-300 ease-in-out overflow-hidden select-none";
        roomWrapper.setAttribute('data-channel-id', chId);
        
        roomWrapper.style.maxHeight = '0px';
        roomWrapper.style.opacity = '0';
        roomWrapper.style.padding = '0px';
        roomWrapper.style.marginBottom = '0px';
        roomWrapper.style.borderColor = 'transparent';

        roomWrapper.addEventListener('mouseenter', () => highlightChannel(chId));
        roomWrapper.addEventListener('mouseleave', () => unhighlightChannel());

        const roomHeader = document.createElement('div');
        roomHeader.className = "flex justify-between items-center mb-2.5";
        
        const titleBlock = document.createElement('div');
        titleBlock.className = "flex items-center gap-2 min-w-0";
        titleBlock.innerHTML = `
            <span class="text-sm">🔊</span>
            <span class="text-xs font-bold text-gray-200 truncate pr-1">${ch.name}</span>
            ${!ch.is_active ? '<span class="text-[9px] bg-red-950/40 border border-red-900/40 text-red-400 font-extrabold px-1 rounded-sm uppercase tracking-wider">Deleted</span>' : ''}
        `;

        const badgeCount = document.createElement('span');
        badgeCount.className = "text-[10px] font-bold px-2 py-0.5 rounded-full bg-gray-950/60 border border-gray-850 text-indigo-400 font-mono";
        badgeCount.innerText = '0';

        roomHeader.appendChild(titleBlock);
        roomHeader.appendChild(badgeCount);
        roomWrapper.appendChild(roomHeader);

        const usersContainer = document.createElement('div');
        usersContainer.className = "users-container flex flex-col gap-1.5 pl-3 border-l border-gray-800/60 transition-all duration-300 ease-in-out overflow-hidden";
        usersContainer.style.maxHeight = '0px';
        usersContainer.style.opacity = '0';
        
        roomWrapper.appendChild(usersContainer);
        container.appendChild(roomWrapper);
    });
}
