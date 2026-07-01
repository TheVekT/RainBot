// Yearly Activity Heatmap module for RainBot Analytics
function renderHeatmap() {
    const container = document.getElementById('heatmap-container');
    if (!container) return;
    
    container.innerHTML = '';

    const dailyCoefficient = {};

    rawHistory.forEach(item => {
        const stateStr = REVERSE_STATE_MAP[item[0]];
        if (!stateStr || stateStr === 'offline') return;

        const startTs = item[1];
        const endTs = item[2];

        const startDate = new Date(startTs * 1000);
        let current = new Date(startDate);
        current.setHours(0, 0, 0, 0);

        while (current.getTime() / 1000 < endTs) {
            const dayStartTs = Math.floor(current.getTime() / 1000);
            const nextDay = new Date(current);
            nextDay.setDate(nextDay.getDate() + 1);
            const dayEndTs = Math.floor(nextDay.getTime() / 1000);

            const clampedStart = Math.max(startTs, dayStartTs);
            const clampedEnd = Math.min(endTs, dayEndTs);
            const duration = clampedEnd - clampedStart;

            if (duration > 0) {
                const dateKey = getYYYYMMDD(current);
                dailyCoefficient[dateKey] = (dailyCoefficient[dateKey] || 0) + duration;
            }

            current = nextDay;
        }
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

    const datePickerEl = document.getElementById('timeline-date-picker');
    const selectedDateVal = datePickerEl ? datePickerEl.value : '';

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

    if (!svgElement || !lens || !lensGrid) return;

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
                cellDiv.className = 'absolute flex flex-col items-center justify-center rounded text-white text-center shadow-inner leading-none select-none';
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
            if (picker) {
                picker.value = dateStr;
                picker.dispatchEvent(new Event('change'));
            }

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
