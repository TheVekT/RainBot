const searchInput = document.getElementById('user-search-input');
const showFormerMembers = document.getElementById('show-former-members');
const filterToggle = document.getElementById('filter-toggle');
const filterPanel = document.getElementById('filter-panel');
const filterIndicator = document.getElementById('filter-indicator');
const statusFilters = Array.from(document.querySelectorAll('.status-filter'));
const userCards = Array.from(document.querySelectorAll('.user-card'));
const sortButton = document.getElementById('status-sort');
const sortModeLabel = document.getElementById('status-sort-mode');
const statusOrder = ['voice_online', 'voice_mute', 'voice_deaf', 'voice_afk', 'voice_alone', 'online', 'offline'];
let sortMode = 0;

function filterUsers() {
    const query = searchInput.value.toLowerCase().replace('@', '').trim();
    const selectedStatuses = new Set(statusFilters.filter(input => input.checked).map(input => input.value));
    filterIndicator.hidden = !showFormerMembers.checked && statusFilters.every(input => input.checked);
    let visible = 0;
    let eligible = 0;
    userCards.forEach(card => {
        // Former members have no current Discord status, so their last saved
        // status must not affect their visibility.
        const included = card.dataset.member === 'true'
            ? selectedStatuses.has(card.dataset.status)
            : showFormerMembers.checked;
        const matches = !query || card.dataset.searchQuery.includes(query);
        card.hidden = !included || !matches;
        if (included) eligible++;
        if (!card.hidden) visible++;
    });
    document.getElementById('search-empty').hidden = !userCards.length || visible > 0;
    document.getElementById('user-count').textContent = `${visible} of ${eligible} users`;
}

function statusRank(card) {
    const rank = statusOrder.indexOf(card.dataset.status);
    return rank === -1 ? statusOrder.length : rank;
}

function sortUsers() {
    const ordered = userCards.map((card, index) => ({card, index}));
    ordered.sort((a, b) => {
        // Membership always takes priority, regardless of the status sort direction.
        const memberOrder = Number(b.card.dataset.member === 'true') - Number(a.card.dataset.member === 'true');
        if (memberOrder) return memberOrder;
        if (sortMode && a.card.dataset.member === 'true') {
            const statusComparison = statusRank(a.card) - statusRank(b.card);
            if (statusComparison) return sortMode === 1 ? statusComparison : -statusComparison;
        }
        return a.index - b.index;
    });
    const container = document.getElementById('users-grid');
    ordered.forEach(({card}) => container.appendChild(card));
}

searchInput.addEventListener('input', filterUsers);
showFormerMembers.addEventListener('change', filterUsers);
statusFilters.forEach(input => input.addEventListener('change', filterUsers));

function setFiltersOpen(open) {
    filterPanel.hidden = !open;
    filterToggle.setAttribute('aria-expanded', String(open));
}

filterToggle.addEventListener('click', () => setFiltersOpen(filterPanel.hidden));
document.addEventListener('click', event => {
    if (!filterPanel.hidden && !filterPanel.contains(event.target) && !filterToggle.contains(event.target)) {
        setFiltersOpen(false);
    }
});
document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !filterPanel.hidden) {
        setFiltersOpen(false);
        filterToggle.focus();
    }
});
sortButton.addEventListener('click', () => {
    sortMode = (sortMode + 1) % 3;
    sortUsers();
    sortModeLabel.textContent = ['↕', '↑', '↓'][sortMode];
    const labels = ['Status: original order. Sort active users first.', 'Status: active users first. Sort offline users first.', 'Status: offline users first. Restore original order.'];
    sortButton.setAttribute('aria-label', labels[sortMode]);
    sortButton.title = labels[sortMode];
});

sortUsers();
filterUsers();
