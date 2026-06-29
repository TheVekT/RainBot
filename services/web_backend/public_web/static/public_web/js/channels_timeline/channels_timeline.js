const urlParams = new URLSearchParams(window.location.search);
let currentDateString = urlParams.get('date') || getYYYYMMDD(new Date());
let sliderPercentage = 0.5; // Defaults to 12:00 (mid-day)
let isDraggingSlider = false;
let highlightedChannelId = null;

// Initialize calendar popover widget
const calendarWidget = initCustomCalendar({
    initialDate: currentDateString,
    onChange: (nextDateStr) => {
        currentDateString = nextDateStr;
        fetchDataAndRefresh(nextDateStr);
    }
});

// Fetch dynamic daily timeline logs via AJAX
function fetchDataAndRefresh(dateStr) {
    if (calendarWidget) {
        calendarWidget.updateDate(dateStr);
    }
    
    // Re-render local structures
    fetch('?date=' + dateStr + '&format=json')
        .then(res => {
            if (!res.ok) throw new Error('Fetch failed');
            return res.json();
        })
        .then(data => {
            globalVoiceData = data;
            
            // Reset slider to mid-day (12:00) on date changes
            sliderPercentage = 0.5;
            
            renderTimelineChart();
            updateTimeView();
        })
        .catch(err => {
            console.error('Error fetching voice intervals data:', err);
        });
}

// Slider guides updates
function updateTimeView() {
    const slider = document.getElementById('timeline-slider');
    if (!slider) return;
    
    // Reposition slider handle
    slider.style.left = `${sliderPercentage * 100}%`;

    // Compute target local timestamp
    const localStart = new Date(`${currentDateString}T00:00:00`);
    const localEnd = new Date(`${currentDateString}T23:59:59.999`);
    const startTs = Math.floor(localStart.getTime() / 1000);
    const endTs = Math.floor(localEnd.getTime() / 1000);
    const selectedTs = startTs + sliderPercentage * (endTs - startTs);

    // Format selected time string
    const dateObj = new Date(selectedTs * 1000);
    const hh = String(dateObj.getHours()).padStart(2, '0');
    const mm = String(dateObj.getMinutes()).padStart(2, '0');
    const ss = String(dateObj.getSeconds()).padStart(2, '0');
    
    const timeLabel = document.getElementById('active-time-label');
    if (timeLabel) timeLabel.innerText = `${hh}:${mm}:${ss}`;

    // Re-render server room tree elements
    renderChannelTree(selectedTs);
}

// Setup interaction handlers on timeline capture block
document.addEventListener('DOMContentLoaded', () => {
    const captureArea = document.getElementById('timeline-event-capture');
    const hoverGuide = document.getElementById('hover-guide-line');
    const graphTooltip = document.getElementById('graph-tooltip');

    if (!captureArea || !hoverGuide || !graphTooltip) return;

    function handleTimelineMove(clientX) {
        const rect = captureArea.getBoundingClientRect();
        let pct = (clientX - rect.left) / rect.width;
        pct = Math.max(0, Math.min(1, pct));

        sliderPercentage = pct;
        updateTimeView();
    }

    captureArea.addEventListener('mousedown', (e) => {
        isDraggingSlider = true;
        handleTimelineMove(e.clientX);
    });

    const timelineSlider = document.getElementById('timeline-slider');
    if (timelineSlider) {
        timelineSlider.addEventListener('mousedown', (e) => {
            if (e.button !== 0) return;
            e.stopPropagation();
            isDraggingSlider = true;
            e.preventDefault();
        });
    }

    document.addEventListener('mousemove', (e) => {
        if (isDraggingSlider) {
            handleTimelineMove(e.clientX);
        }
    });

    document.addEventListener('mouseup', () => {
        isDraggingSlider = false;
    });

    // Guide hover tooltip calculations
    captureArea.addEventListener('mousemove', (e) => {
        if (isDraggingSlider) {
            graphTooltip.classList.add('hidden');
            hoverGuide.classList.add('hidden');
            const marker = document.getElementById('hover-point-marker');
            if (marker) marker.classList.add('hidden');
            return;
        }

        const rect = captureArea.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        const width = rect.width;
        const height = rect.height;

        let pct = mouseX / width;
        pct = Math.max(0, Math.min(1, pct));

        const samplingSteps = 288;
        const s = Math.round(pct * (samplingSteps - 1));

        const localStart = new Date(`${currentDateString}T00:00:00`);
        const localEnd = new Date(`${currentDateString}T23:59:59.999`);
        const startTs = Math.floor(localStart.getTime() / 1000);
        const endTs = Math.floor(localEnd.getTime() / 1000);
        const targetTs = startTs + pct * (endTs - startTs);

        const isToday = currentDateString === todayDateStr;
        const maxDrawTs = window.maxDrawTs || endTs;

        if (isToday && targetTs > maxDrawTs) {
            graphTooltip.classList.add('hidden');
            hoverGuide.classList.add('hidden');
            const marker = document.getElementById('hover-point-marker');
            if (marker) marker.classList.add('hidden');
            unhighlightChannel();
            updateTimeView();
            return;
        }

        // Find the closest channel vertically
        let closestCh = null;
        let minDist = 25; // Hover threshold in pixels
        let closestY = 0;
        let closestX = (s / (samplingSteps - 1)) * width;
        let closestColor = '';
        let closestVal = 0;

        const paddingBottom = 4;
        const paddingTop = 4;
        const chartHeight = height - paddingBottom - paddingTop;

        if (window.timelineChannels && window.timelineValues && window.globalMaxCount) {
            window.timelineChannels.forEach((ch, idx) => {
                const chId = ch.channel_id;
                const values = window.timelineValues[chId];
                if (values && values[s] !== undefined) {
                    const y = height - paddingBottom - (values[s] / window.globalMaxCount) * chartHeight;
                    const dist = Math.abs(mouseY - y);
                    if (dist < minDist) {
                        minDist = dist;
                        closestCh = ch;
                        closestY = y;
                        closestColor = getChannelColor(chId, idx);
                        closestVal = values[s];
                    }
                }
            });
        }

        if (closestCh) {
            // Highlight channel
            highlightChannel(closestCh.channel_id);

            // Position hover guide and tooltip
            hoverGuide.style.left = `${closestX}px`;
            hoverGuide.classList.remove('hidden');

            // Draw hover marker point
            const svg = document.getElementById('timeline-svg-chart');
            let hoverMarker = document.getElementById('hover-point-marker');
            if (!hoverMarker && svg) {
                hoverMarker = document.createElementNS("http://www.w3.org/2000/svg", "circle");
                hoverMarker.setAttribute('id', 'hover-point-marker');
                hoverMarker.setAttribute('r', '4.5');
                hoverMarker.setAttribute('fill', '#ffffff');
                hoverMarker.setAttribute('stroke-width', '2.5');
                hoverMarker.setAttribute('class', 'pointer-events-none');
                svg.appendChild(hoverMarker);
            }
            if (hoverMarker) {
                hoverMarker.setAttribute('cx', closestX);
                hoverMarker.setAttribute('cy', closestY);
                hoverMarker.setAttribute('stroke', closestColor);
                hoverMarker.classList.remove('hidden');
            }

            const dateObj = new Date(targetTs * 1000);
            const timeStr = dateObj.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

            graphTooltip.innerHTML = `
                <div class="font-bold text-indigo-400 text-center border-b border-gray-800/40 pb-1">${timeStr}</div>
                <div class="flex items-center gap-2 mt-1.5 text-xs">
                    <span class="w-2.5 h-2.5 rounded-full" style="background-color: ${closestColor};"></span>
                    <span class="text-gray-300 font-bold">${closestCh.name}</span>
                    <span class="font-bold text-indigo-400 font-mono ml-4">${closestVal} users</span>
                </div>
            `;

            const tooltipRect = graphTooltip.getBoundingClientRect();
            let left = e.clientX - tooltipRect.width / 2;
            let top = e.clientY - tooltipRect.height - 20;

            if (left < 10) left = 10;
            if (left + tooltipRect.width > window.innerWidth - 10) left = window.innerWidth - tooltipRect.width - 10;
            if (top < 10) top = e.clientY + 20;

            graphTooltip.style.left = `${left}px`;
            graphTooltip.style.top = `${top}px`;
            graphTooltip.classList.remove('hidden');
        } else {
            unhighlightChannel();
            graphTooltip.classList.add('hidden');
            hoverGuide.classList.add('hidden');
            const marker = document.getElementById('hover-point-marker');
            if (marker) marker.classList.add('hidden');
            
            updateTimeView();
        }
    });

    captureArea.addEventListener('mouseleave', () => {
        unhighlightChannel();
        graphTooltip.classList.add('hidden');
        hoverGuide.classList.add('hidden');
        const marker = document.getElementById('hover-point-marker');
        if (marker) marker.classList.add('hidden');
        
        updateTimeView();
    });

    // Initialize display and triggers
    initializeDOMRooms();
    renderTimelineChart();
    updateTimeView();
});
