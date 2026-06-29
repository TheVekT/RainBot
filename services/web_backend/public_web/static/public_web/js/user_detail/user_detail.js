// Detailed User Analytics Controller for RainBot Analytics
let radarChartInstance = null;

function calculateAndRenderRadar(targetDateStr) {
    const activeSeconds = {
        "online": 0, "voice_online": 0, "voice_mute": 0,
        "voice_deaf": 0, "voice_afk": 0, "voice_alone": 0
    };

    const localStart = new Date(`${targetDateStr}T00:00:00`);
    const localEnd = new Date(`${targetDateStr}T23:59:59.999`);
    const dayStartTs = Math.floor(localStart.getTime() / 1000);
    const dayEndTs = Math.floor(localEnd.getTime() / 1000);

    const viewStartTs = zoomStartTs !== null ? zoomStartTs : dayStartTs;
    const viewEndTs = zoomEndTs !== null ? zoomEndTs : dayEndTs;

    rawHistory.forEach(item => {
        const stateStr = REVERSE_STATE_MAP[item[0]];
        if (stateStr && stateStr !== 'offline') {
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

    const radarCanvas = document.getElementById('radar-chart-canvas');
    if (!radarCanvas) return;
    const ctx = radarCanvas.getContext('2d');

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

// Setup picker interactions and data loading triggers
document.addEventListener('DOMContentLoaded', () => {
    const picker = document.getElementById('timeline-date-picker');
    const selectedDateDisp = document.getElementById('selected-date-display');

    if (selectedDateDisp && picker) {
        selectedDateDisp.addEventListener('click', () => {
            if (typeof picker.showPicker === 'function') {
                picker.showPicker();
            }
        });

        picker.addEventListener('change', (e) => {
            const selectedDate = e.target.value;

            renderTimeline(selectedDate);
            calculateAndRenderRadar(selectedDate);
            renderHeatmap();

            // Format selected date nicely in English
            const selDate = new Date(selectedDate + 'T12:00:00');
            const options = { day: 'numeric', month: 'long', year: 'numeric' };
            selectedDateDisp.innerText = selDate.toLocaleDateString('en-US', options);

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
                .catch(error => {
                    console.error('Error updating presence overlay data:', error);
                });
        });

        // Run Initializations
        const urlParams = new URLSearchParams(window.location.search);
        picker.value = urlParams.get('date') || getYYYYMMDD(new Date());
        renderTimeline(picker.value);
        calculateAndRenderRadar(picker.value);
        renderHeatmap();

        const initDateObj = new Date(picker.value + 'T12:00:00');
        selectedDateDisp.innerText = initDateObj.toLocaleDateString('en-US', { day: 'numeric', month: 'long', year: 'numeric' });
    }
});
