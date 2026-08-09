import { Chart, registerables } from 'chart.js';

// Register Chart.js components globally if not already registered
// Note: It's safe to call register multiple times
Chart.register(...registerables);

/**
 * Generates a Base64 image URL from a Chart.js configuration
 * @param {Object} chartConfig - The Chart.js configuration object
 * @param {number} width - Width of the generated image (default: 600)
 * @param {number} height - Height of the generated image (default: 400)
 * @returns {Promise<string>} - Resolves with data URL of the chart image
 */
export const renderChartToImage = (chartConfig, width = 600, height = 400) => {
    return new Promise((resolve, reject) => {
        try {
            // Create hidden canvas
            const canvas = document.createElement('canvas');
            canvas.width = width;
            canvas.height = height;

            // Render chart
            const chartInstance = new Chart(canvas, {
                ...chartConfig,
                options: {
                    ...chartConfig.options,
                    animation: false, // Disable animation for immediate capture
                    responsive: false,
                    devicePixelRatio: 2 // High quality
                }
            });

            // Wait a tick to ensure rendering is complete (Chart.js is synchronous but sometimes needs a tick)
            setTimeout(() => {
                try {
                    const dataUrl = canvas.toDataURL('image/png');
                    chartInstance.destroy();
                    resolve(dataUrl);
                } catch (innerErr) {
                    reject(innerErr);
                }
            }, 0);

        } catch (err) {
            console.error('Chart render error:', err);
            reject(err);
        }
    });
};
