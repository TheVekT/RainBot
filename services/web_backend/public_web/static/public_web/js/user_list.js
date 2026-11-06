const searchInput = document.getElementById('user-search-input');
    const userCards = Array.from(document.querySelectorAll('.user-card'));
    searchInput.addEventListener('input', () => {
        const query = searchInput.value.toLowerCase().replace('@', '').trim();
        let visible = 0;
        userCards.forEach(card => {
            const matches = !query || card.dataset.searchQuery.includes(query);
            card.classList.toggle('hidden', !matches);
            if (matches) visible++;
        });
        document.getElementById('search-empty').classList.toggle('hidden', !userCards.length || visible > 0);
        document.getElementById('user-count').textContent = `${visible} of ${userCards.length} users`;
    });

    const sortButton = document.getElementById('status-sort');
    const sortModeLabel = document.getElementById('status-sort-mode');
    const statusOrder = ['voice_online', 'voice_mute', 'voice_deaf', 'voice_afk', 'voice_alone', 'online', 'offline'];
    const statusRank = card => {
        const rank = statusOrder.indexOf(card.dataset.status);
        return rank === -1 ? statusOrder.length : rank;
    };
    let sortMode = 0;
    sortButton.addEventListener('click', () => {
        sortMode = (sortMode + 1) % 3;
        const ordered = userCards.map((card, index) => ({card, index}));
        if (sortMode) ordered.sort((a, b) => (sortMode === 1 ? 1 : -1) * (statusRank(a.card) - statusRank(b.card)) || a.index - b.index);
        const container = document.getElementById('users-grid');
        ordered.forEach(({card}) => container.appendChild(card));
        sortModeLabel.textContent = ['↕', '↑', '↓'][sortMode];
        const labels = ['Status: original order. Sort active users first.', 'Status: active users first. Sort offline users first.', 'Status: offline users first. Restore original order.'];
        sortButton.setAttribute('aria-label', labels[sortMode]);
        sortButton.title = labels[sortMode];
        document.getElementById('user-count').textContent = ['Original user order', 'Sorted by status: active users first', 'Sorted by status: offline users first'][sortMode];
    });
