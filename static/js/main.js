// SKN APEX - Main JavaScript

// ============================================
// SOCKET CONNECTION
// ============================================

let socket = io();

socket.on('connect', function() {
    console.log('Connected to server');
});

socket.on('queue_update', function(data) {
    console.log('Queue updated:', data);
});

// ============================================
// AUTHENTICATION HELPERS
// ============================================

function getToken() {
    return localStorage.getItem('token');
}

function isLoggedIn() {
    return !!getToken();
}

function logout() {
    localStorage.removeItem('token');
    window.location.href = '/login';
}

// ============================================
// API HELPERS
// ============================================

async function apiCall(method, endpoint, data = null) {
    const options = {
        method: method,
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${getToken()}`
        }
    };
    
    if (data) {
        options.body = JSON.stringify(data);
    }
    
    const response = await fetch(endpoint, options);
    return await response.json();
}

// ============================================
// UI HELPERS
// ============================================

function showAlert(message, type = 'info') {
    alert(message);
}

function formatCurrency(amount) {
    return '₹' + amount.toFixed(2);
}

function formatDate(date) {
    return new Date(date).toLocaleDateString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric'
    });
}

// ============================================
// DOM READY
// ============================================

document.addEventListener('DOMContentLoaded', function() {
    console.log('SKN APEX loaded');
});
