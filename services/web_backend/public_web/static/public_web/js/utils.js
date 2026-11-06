// Shared, decorative voice-channel icon used across the analytics views.
const VOICE_ICON = `<svg class="ui-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H3v6h3l5 4V5ZM15 9a5 5 0 0 1 0 6M18 6a9 9 0 0 1 0 12"/></svg>`;

// Constants and common helper functions for RainBot Analytics
const REVERSE_STATE_MAP = {
    0: "offline", 1: "online", 2: "voice_online",
    3: "voice_mute", 4: "voice_deaf", 5: "voice_afk", 6: "voice_alone"
};

const COLOR_MAP = {
    "offline": "#4b5563", "online": "#22c55e", "voice_online": "#06b6d4",
    "voice_mute": "#84cc16", "voice_deaf": "#ef4444", "voice_afk": "#ec4899", "voice_alone": "#8b5cf6"
};

const CHANNEL_COLORS = [
    '#d0ac64', // Gold
    '#8eb59a', // Sage
    '#ca8c67', // Copper
    '#b595b6', // Mauve
    '#83aebc', // Blue grey
    '#b8bd83', // Olive
    '#d29499', // Rose
    '#8f9dc8', // Periwinkle
    '#78b5ae', // Teal
    '#c2a68e'  // Sand
];

// Hash code generator for consistent colors
function getStringHash(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    return hash;
}

function getChannelColor(channelId, index) {
    const idx = Math.abs(getStringHash(channelId)) % CHANNEL_COLORS.length;
    return CHANNEL_COLORS[idx];
}

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
