let supportClickCount = 0;
let supportClickTimer = null;

const supportIcon = document.getElementById('supportIcon');
const tooltip = document.getElementById('supportTooltip');

const supportUrl = supportIcon.dataset.supportUrl;

supportIcon.addEventListener('click', function () {
    supportClickCount++;

    if (supportClickCount === 1) {
        tooltip.classList.remove('hidden');

        supportClickTimer = setTimeout(() => {
            supportClickCount = 0;
            tooltip.classList.add('hidden');
        }, 3000);
    } else if (supportClickCount === 2) {
        clearTimeout(supportClickTimer);
        window.location.href = supportUrl;
    }
});
