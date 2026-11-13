(() => {
  const tooltip = document.getElementById('status-tooltip');
  if (!tooltip) return;
  function show(bar) {
    for (const name of ['range', 'up', 'degraded', 'down', 'unknown']) {
      tooltip.querySelector(`[data-tooltip="${name}"]`).textContent = bar.dataset[name];
    }
    tooltip.hidden = false;
    const rect = bar.getBoundingClientRect();
    const box = tooltip.getBoundingClientRect();
    const x = Math.max(8, Math.min(window.innerWidth - box.width - 8, rect.left + rect.width / 2 - box.width / 2));
    const y = rect.top - box.height - 10 >= 8 ? rect.top - box.height - 10 : Math.min(window.innerHeight - box.height - 8, rect.bottom + 10);
    tooltip.style.left = `${x}px`;
    tooltip.style.top = `${Math.max(8, y)}px`;
  }
  function hide() { tooltip.hidden = true; }
  document.querySelectorAll('.status-bar').forEach((bar) => {
    bar.addEventListener('mouseenter', () => show(bar));
    bar.addEventListener('mouseleave', hide);
    bar.addEventListener('focus', () => show(bar));
    bar.addEventListener('blur', hide);
  });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') hide(); });
  window.addEventListener('scroll', hide, { passive: true });
})();
