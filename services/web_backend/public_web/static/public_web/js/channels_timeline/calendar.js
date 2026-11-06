// Reusable custom popover calendar widget for RainBot Analytics chronology
function initCustomCalendar(options) {
    const monthsEn = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
    
    let currentDateString = options.initialDate;
    let pickerCurrentDate = new Date(currentDateString + 'T12:00:00');

    const pickerTrigger = document.getElementById('custom-date-display');
    const pickerPopup = document.getElementById('custom-calendar-popup');

    if (!pickerTrigger || !pickerPopup) return null;

    function updateTriggerLabel() {
        const dateObj = new Date(currentDateString + 'T12:00:00');
        const labelSpan = pickerTrigger.querySelector('span');
        if (labelSpan) {
            labelSpan.innerText = dateObj.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
        }
    }

    function renderCustomCalendar(year, month) {
        const firstDayOfMonth = new Date(year, month, 1).getDay();
        const daysInMonth = new Date(year, month + 1, 0).getDate();
        const grid = document.getElementById('cal-days-grid');
        if (!grid) return;
        
        grid.innerHTML = '';

        const monthYearLabel = document.getElementById('cal-month-year');
        if (monthYearLabel) {
            monthYearLabel.innerText = `${monthsEn[month]} ${year}`;
        }

        // Empty slots for preceding month wrap
        for (let i = 0; i < firstDayOfMonth; i++) {
            const cell = document.createElement('span');
            cell.className = 'empty-day';
            grid.appendChild(cell);
        }

        // Fill actual month dates
        const parts = currentDateString.split('-');
        const selYear = parseInt(parts[0], 10);
        const selMonth = parseInt(parts[1], 10) - 1;
        const selDay = parseInt(parts[2], 10);

        for (let d = 1; d <= daysInMonth; d++) {
            const button = document.createElement('button');
            button.innerText = d;
            const cellDate = new Date(year, month, d);
            const isSelected = (year === selYear && month === selMonth && d === selDay);

            button.type = 'button';
            button.className = `custom-calendar-day ${isSelected ? 'selected-day' : ''}`;
            button.setAttribute('aria-label', cellDate.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' }));
            button.setAttribute('aria-pressed', String(isSelected));

            button.addEventListener('click', () => {
                const nextDateStr = getYYYYMMDD(cellDate);
                currentDateString = nextDateStr;
                pickerPopup.classList.add('hidden');
                pickerTrigger.setAttribute('aria-expanded', 'false');
                updateTriggerLabel();
                if (typeof options.onChange === 'function') {
                    options.onChange(nextDateStr);
                }
            });

            grid.appendChild(button);
        }
    }

    pickerTrigger.addEventListener('click', (e) => {
        e.stopPropagation();
        pickerPopup.classList.toggle('hidden');
        pickerTrigger.setAttribute('aria-expanded', String(!pickerPopup.classList.contains('hidden')));
        if (!pickerPopup.classList.contains('hidden')) {
            const currentSelected = new Date(currentDateString + 'T12:00:00');
            pickerCurrentDate = new Date(currentSelected);
            renderCustomCalendar(pickerCurrentDate.getFullYear(), pickerCurrentDate.getMonth());
        }
    });

    const prevBtn = document.getElementById('cal-prev-btn');
    if (prevBtn) {
        prevBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            pickerCurrentDate.setMonth(pickerCurrentDate.getMonth() - 1);
            renderCustomCalendar(pickerCurrentDate.getFullYear(), pickerCurrentDate.getMonth());
        });
    }

    const nextBtn = document.getElementById('cal-next-btn');
    if (nextBtn) {
        nextBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            pickerCurrentDate.setMonth(pickerCurrentDate.getMonth() + 1);
            renderCustomCalendar(pickerCurrentDate.getFullYear(), pickerCurrentDate.getMonth());
        });
    }

    document.addEventListener('click', (e) => {
        if (pickerPopup && !pickerPopup.contains(e.target) && e.target !== pickerTrigger && !pickerTrigger.contains(e.target)) {
            pickerPopup.classList.add('hidden');
                pickerTrigger.setAttribute('aria-expanded', 'false');
        }
    });

    pickerPopup.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            pickerPopup.classList.add('hidden');
            pickerTrigger.setAttribute('aria-expanded', 'false');
            pickerTrigger.focus();
        }
    });
    pickerTrigger.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            pickerPopup.classList.add('hidden');
            pickerTrigger.setAttribute('aria-expanded', 'false');
        }
    });

    // Initial label set
    updateTriggerLabel();

    return {
        updateDate: (newDateStr) => {
            currentDateString = newDateStr;
            updateTriggerLabel();
        }
    };
}
