/**
 * AI Video Generator - Complete Frontend Logic  
 */

// Global state
let currentTitle = '';
let currentScript = null;
let generatedImages = [];
let manualImages = [];
let manualVideos = [];
let stockFootage = [];
let allMedia = [];
let audioFiles = [];

// ==================== INITIALIZATION ====================

document.addEventListener('DOMContentLoaded', function() {
    console.log('AI Video Generator initialized');
    
    // Set up event listeners
    setupEventListeners();
});

function setupEventListeners() {
    // Radio button listeners would go here
    console.log('Event listeners configured');
}

// ==================== TITLE GENERATION ====================

async function generateTitle() {
    const context = document.getElementById('titleContext').value;
    
    try {
        const response = await fetch('/api/generate-title', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({context})
        });
        
        const data = await response.json();
        
        if (data.success) {
            document.getElementById('generatedTitleText').textContent = data.title;
            document.getElementById('generatedTitleResult').style.display = 'block';
        } else {
            alert('Error: ' + data.error);
        }
    } catch (error) {
        alert('Error generating title: ' + error.message);
    }
}

// Export for use in HTML
window.generateTitle = generateTitle;

console.log('Generator JavaScript loaded successfully');
