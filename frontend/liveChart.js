document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('liveTempChart');

    if (!canvas) {
        console.error('liveChart: canvas element not found');
        return;
    }
    const ctx = canvas.getContext('2d');
    const MAX_POINTS = 60;

    const temperatureChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [], // timestamps
            datasets: [{
                label: 'Live Temperature Reading',
                data: [], // Initial empty data
                borderColor: 'rgb(75, 192, 192)',
                tension: 0.1
            }]
        },
        options: {
            animation: false,
            scales: {
                x: { display: true },
                y: {
                    min: 20,
                    max: 27,
                    ticks: { stepSize: 0.5},
                }
            }
            // Configure scales, animations, etc.
        }
    });

    function pushTemp(value) {
        if (typeof value !== 'number' || Number.isNaN(value)) return;
        if (value < 10 || value > 60) return;

        const label = new Date().toLocaleTimeString();
        temperatureChart.data.labels.push(label);
        temperatureChart.data.datasets[0].data.push(value);

        while (temperatureChart.data.labels.length > MAX_POINTS) {
            temperatureChart.data.labels.shift();
            temperatureChart.data.datasets[0].data.shift();
        }
        temperatureChart.update('none'); // update without animation

        const el = document.getElementById('temp');
        if (el) el.textContent = value.toFixed(2);
    }

    const es = new EventSource('/stream');

    es.onmessage = (ev) => {
        const raw = ev.data;
        const v = parseFloat(raw);
        if (!Number.isNaN(v)) {
            pushTemp(v);
        } else {
            console.warn('liveChart: non-numeric SSE payload:', raw);
        }
    };
    es.onerror = (err) => {
        console.error('liveChart: SSE error', err);
    };
});


