/* AI Interview Prep - Main JavaScript */

// HTMX configuration
document.body.addEventListener('htmx:configRequest', (event) => {
    // Add CSRF token to all HTMX requests
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
    if (csrfToken) {
        event.detail.headers['X-CSRFToken'] = csrfToken.value;
    }
});

// Flash message auto-dismiss
document.addEventListener('DOMContentLoaded', () => {
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach((message) => {
        setTimeout(() => {
            message.style.transition = 'opacity 0.5s';
            message.style.opacity = '0';
            setTimeout(() => message.remove(), 500);
        }, 5000);
    });
});

// Timer utility for lightning mode
class CountdownTimer {
    constructor(element, seconds, onComplete) {
        this.element = element;
        this.totalSeconds = seconds;
        this.remainingSeconds = seconds;
        this.onComplete = onComplete;
        this.interval = null;
    }

    start() {
        this.interval = setInterval(() => this.tick(), 1000);
        this.render();
    }

    tick() {
        this.remainingSeconds--;
        this.render();

        if (this.remainingSeconds <= 0) {
            this.stop();
            if (this.onComplete) {
                this.onComplete();
            }
        }
    }

    stop() {
        if (this.interval) {
            clearInterval(this.interval);
            this.interval = null;
        }
    }

    render() {
        const minutes = Math.floor(Math.max(0, this.remainingSeconds) / 60);
        const seconds = Math.max(0, this.remainingSeconds) % 60;
        this.element.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;

        // Add warning/danger classes
        this.element.classList.remove('warning', 'danger');
        if (this.remainingSeconds <= 30) {
            this.element.classList.add('danger');
        } else if (this.remainingSeconds <= 60) {
            this.element.classList.add('warning');
        }
    }
}

// Export for use in templates
window.CountdownTimer = CountdownTimer;
