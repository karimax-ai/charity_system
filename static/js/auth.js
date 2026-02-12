// Authentication JavaScript Functions

// Password Strength Checker
function checkPasswordStrength(password) {
    let strength = 0;
    const strengthText = document.getElementById('strengthText');
    const strengthFill = document.getElementById('strengthFill');

    if (!password) {
        strengthFill.style.width = '0%';
        strengthFill.style.backgroundColor = '#e9ecef';
        strengthText.textContent = '';
        return;
    }

    // Check length
    if (password.length >= 8) strength++;
    if (password.length >= 12) strength++;

    // Check for lowercase
    if (/[a-z]/.test(password)) strength++;

    // Check for uppercase
    if (/[A-Z]/.test(password)) strength++;

    // Check for numbers
    if (/[0-9]/.test(password)) strength++;

    // Check for special characters
    if (/[^A-Za-z0-9]/.test(password)) strength++;

    // Update strength meter
    let width, color, text;

    switch (true) {
        case (strength <= 2):
            width = '33%';
            color = '#dc3545';
            text = 'ضعیف';
            break;
        case (strength <= 4):
            width = '66%';
            color = '#ffc107';
            text = 'متوسط';
            break;
        default:
            width = '100%';
            color = '#198754';
            text = 'قوی';
    }

    strengthFill.style.width = width;
    strengthFill.style.backgroundColor = color;
    strengthText.textContent = text;
    strengthText.style.color = color;
}

// OTP Input Auto Focus
function setupOTPInputs() {
    const otpInputs = document.querySelectorAll('.otp-input');

    otpInputs.forEach((input, index) => {
        input.addEventListener('input', (e) => {
            if (e.target.value.length === 1) {
                if (index < otpInputs.length - 1) {
                    otpInputs[index + 1].focus();
                }
            }
        });

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Backspace' && !e.target.value) {
                if (index > 0) {
                    otpInputs[index - 1].focus();
                }
            }
        });
    });
}

// Countdown Timer
function startCountdown(seconds, displayElementId) {
    const display = document.getElementById(displayElementId);
    let remaining = seconds;

    const timer = setInterval(() => {
        const minutes = Math.floor(remaining / 60);
        const secs = remaining % 60;

        display.textContent = `${minutes}:${secs.toString().padStart(2, '0')}`;

        if (remaining <= 0) {
            clearInterval(timer);
            display.textContent = 'منقضی شد';
            display.style.color = '#dc3545';

            // Enable resend button
            const resendBtn = document.querySelector('.resend-btn');
            if (resendBtn) {
                resendBtn.disabled = false;
                resendBtn.textContent = 'ارسال مجدد';
            }
        }

        remaining--;
    }, 1000);
}

// Form Validation Helper
function validateForm(formId) {
    const form = document.getElementById(formId);
    const inputs = form.querySelectorAll('[required]');
    let isValid = true;

    inputs.forEach(input => {
        if (!input.value.trim()) {
            input.classList.add('is-invalid');
            isValid = false;
        } else {
            input.classList.remove('is-invalid');
        }
    });

    return isValid;
}

// Show Loading Overlay
function showLoading(message = 'در حال پردازش...') {
    const overlay = document.createElement('div');
    overlay.className = 'loading-overlay';
    overlay.innerHTML = `
        <div class="text-center">
            <div class="loading-spinner mb-3"></div>
            <p class="text-muted">${message}</p>
        </div>
    `;
    document.body.appendChild(overlay);
}

// Hide Loading Overlay
function hideLoading() {
    const overlay = document.querySelector('.loading-overlay');
    if (overlay) {
        overlay.remove();
    }
}

// Show Toast Message
function showToast(message, type = 'info') {
    const toastEl = document.getElementById('liveToast');
    const toastBody = toastEl.querySelector('.toast-body');
    const toast = new bootstrap.Toast(toastEl);

    toastBody.textContent = message;

    // Set color based on type
    const types = {
        'success': 'alert-success',
        'error': 'alert-danger',
        'warning': 'alert-warning',
        'info': 'alert-info'
    };

    toastEl.className = `toast ${types[type] || 'alert-info'}`;
    toast.show();
}

// Copy to Clipboard
function copyToClipboard(text, message = 'کپی شد!') {
    navigator.clipboard.writeText(text).then(() => {
        showToast(message, 'success');
    }).catch(err => {
        console.error('Could not copy text: ', err);
        showToast('خطا در کپی کردن', 'error');
    });
}

// Format Phone Number
function formatPhoneNumber(phone) {
    phone = phone.replace(/\D/g, '');

    if (phone.startsWith('98')) {
        phone = phone.substring(2);
    }

    if (phone.startsWith('0')) {
        phone = phone.substring(1);
    }

    if (phone.length === 10) {
        return `0${phone.substring(0, 3)} ${phone.substring(3, 6)} ${phone.substring(6, 10)}`;
    }

    return phone;
}

// Check if user is logged in
function isLoggedIn() {
    return document.cookie.includes('access_token');
}

// Get user token from cookies
function getToken() {
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'access_token') {
            return value;
        }
    }
    return null;
}

// Make authenticated API call
async function makeAuthRequest(url, method = 'GET', data = null) {
    const token = getToken();

    if (!token) {
        window.location.href = '/login';
        return;
    }

    const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
    };

    const options = {
        method,
        headers
    };

    if (data && (method === 'POST' || method === 'PUT')) {
        options.body = JSON.stringify(data);
    }

    try {
        showLoading('در حال ارسال درخواست...');
        const response = await fetch(`/api/v1${url}`, options);
        hideLoading();

        if (response.status === 401) {
            // Token expired
            showToast('لطفاً مجدداً وارد شوید', 'warning');
            window.location.href = '/login';
            return null;
        }

        return await response.json();
    } catch (error) {
        hideLoading();
        showToast('خطا در ارتباط با سرور', 'error');
        console.error('API Error:', error);
        return null;
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Auto focus first input in forms
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        const firstInput = form.querySelector('input:not([type="hidden"])');
        if (firstInput) {
            firstInput.focus();
        }
    });

    // Setup OTP inputs if present
    if (document.querySelector('.otp-input')) {
        setupOTPInputs();
    }

    // Password strength checker
    const passwordInput = document.getElementById('password');
    if (passwordInput) {
        passwordInput.addEventListener('input', function() {
            checkPasswordStrength(this.value);
        });
    }

    // Start countdown if timer element exists
    const timerElement = document.getElementById('countdownTimer');
    if (timerElement) {
        const seconds = parseInt(timerElement.dataset.seconds || 300);
        startCountdown(seconds, 'countdownTimer');
    }

    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});