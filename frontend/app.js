// API Endpoints
const API_URL = ''; // Relative path since frontend is served by FastAPI

// DOM Elements
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const fileInfo = document.getElementById('file-info');
const filenameDisplay = document.getElementById('filename-display');
const cancelSelectionBtn = document.getElementById('cancel-selection');
const uploadBtn = document.getElementById('upload-btn');
const progressContainer = document.getElementById('upload-progress-container');
const progressBar = document.getElementById('upload-progress-bar');
const progressPercent = document.getElementById('upload-progress-percent');
const jdInput = document.getElementById('jd-input');

const historyList = document.getElementById('history-list');
const historyCount = document.getElementById('history-count');

// Detail States
const emptyState = document.getElementById('empty-state');
const loadingState = document.getElementById('loading-state');
const errorState = document.getElementById('error-state');
const resultDashboard = document.getElementById('result-dashboard');

const loadingTitle = document.getElementById('loading-title');
const loadingDesc = document.getElementById('loading-desc');
const loadingStatusText = document.getElementById('loading-status-text');
const errorMessageText = document.getElementById('error-message-text');

const resultTitle = document.getElementById('result-title');
const resultDate = document.getElementById('result-date');
const deleteBtn = document.getElementById('delete-btn');

// Tabs & Panels
const tabAnalysis = document.getElementById('tab-analysis');
const tabTranscript = document.getElementById('tab-transcript');
const panelAnalysis = document.getElementById('panel-analysis');
const panelTranscript = document.getElementById('panel-transcript');
const jdDisplayContainer = document.getElementById('jd-display-container');
const jdDisplayText = document.getElementById('jd-display-text');

// Global State
let selectedFile = null;
let currentJobId = null;
let pollInterval = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    fetchHistory();
    setupDragAndDrop();
    setupEventListeners();
});

// Setup drag and drop events
function setupDragAndDrop() {
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropZone.classList.add('border-indigo-500', 'bg-indigo-50/20');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropZone.classList.remove('border-indigo-500', 'bg-indigo-50/20');
        }, false);
    });

    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            handleFileSelect(files[0]);
        }
    });

    dropZone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
        }
    });
}

function handleFileSelect(file) {
    const allowedExtensions = ['.mp3', '.wav', '.m4a', '.webm', '.ogg'];
    const name = file.name;
    const ext = name.slice(name.lastIndexOf('.')).toLowerCase();
    
    if (!allowedExtensions.includes(ext)) {
        alert(`Unsupported file type! Please upload: ${allowedExtensions.join(', ')}`);
        return;
    }
    
    selectedFile = file;
    filenameDisplay.textContent = file.name;
    dropZone.classList.add('hidden');
    fileInfo.classList.remove('hidden');
    uploadBtn.disabled = false;
}

function resetFileUpload() {
    selectedFile = null;
    fileInput.value = '';
    dropZone.classList.remove('hidden');
    fileInfo.classList.add('hidden');
    uploadBtn.disabled = true;
    progressContainer.classList.add('hidden');
    progressBar.style.width = '0%';
    progressPercent.textContent = '0%';
    jdInput.value = '';
}

function setupEventListeners() {
    cancelSelectionBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        resetFileUpload();
    });

    uploadBtn.addEventListener('click', startUpload);

    // Tab switching
    tabAnalysis.addEventListener('click', () => switchTab('analysis'));
    tabTranscript.addEventListener('click', () => switchTab('transcript'));

    // Delete job
    deleteBtn.addEventListener('click', () => {
        if (currentJobId && confirm("Are you sure you want to delete this job and its transcripts/analysis? This action cannot be undone.")) {
            deleteJob(currentJobId);
        }
    });
}

function switchTab(tab) {
    if (tab === 'analysis') {
        tabAnalysis.className = "border-indigo-600 text-indigo-600 border-b-2 py-4 px-1 text-sm font-semibold flex items-center space-x-2";
        tabTranscript.className = "border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300 border-b-2 py-4 px-1 text-sm font-semibold flex items-center space-x-2";
        panelAnalysis.classList.remove('hidden');
        panelTranscript.classList.add('hidden');
    } else {
        tabTranscript.className = "border-indigo-600 text-indigo-600 border-b-2 py-4 px-1 text-sm font-semibold flex items-center space-x-2";
        tabAnalysis.className = "border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300 border-b-2 py-4 px-1 text-sm font-semibold flex items-center space-x-2";
        panelTranscript.classList.remove('hidden');
        panelAnalysis.classList.add('hidden');
    }
}

// Fetch list of previous jobs
async function fetchHistory() {
    try {
        const response = await fetch('/api/jobs');
        if (!response.ok) throw new Error('Failed to fetch job history');
        const jobs = await response.json();
        
        historyCount.textContent = jobs.length;
        renderHistoryList(jobs);
    } catch (err) {
        console.error('Error fetching history:', err);
    }
}

// Render the list of jobs in history sidebar
function renderHistoryList(jobs) {
    if (jobs.length === 0) {
        historyList.innerHTML = `
            <div class="text-center py-8 text-slate-400 text-sm">
                No interview history found.
            </div>
        `;
        return;
    }

    historyList.innerHTML = jobs.map(job => {
        let statusBadge = '';
        let hoverClass = 'hover:bg-slate-50';
        let activeClass = '';

        if (job.id === currentJobId) {
            activeClass = 'bg-indigo-50/70 border-indigo-200';
            hoverClass = '';
        }

        switch (job.status) {
            case 'PENDING':
                statusBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">Pending</span>';
                break;
            case 'PROCESSING':
                statusBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800 animate-pulse">Processing</span>';
                break;
            case 'COMPLETED':
                statusBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">Completed</span>';
                break;
            case 'FAILED':
                statusBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800">Failed</span>';
                break;
        }

        const date = new Date(job.created_at).toLocaleDateString(undefined, {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });

        return `
            <div onclick="selectJob('${job.id}')" class="p-3 border border-slate-200 rounded-lg cursor-pointer transition-all ${hoverClass} ${activeClass} flex flex-col gap-2">
                <div class="flex items-start justify-between gap-2">
                    <span class="text-sm font-semibold text-slate-800 truncate block w-44" title="${escapeHtml(job.filename)}">${escapeHtml(job.filename)}</span>
                    ${statusBadge}
                </div>
                <div class="text-[11px] text-slate-400 flex items-center justify-between">
                    <span>${date}</span>
                </div>
            </div>
        `;
    }).join('');
}

// Select a job to view details
function selectJob(jobId) {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
    
    currentJobId = jobId;
    
    // Refresh history list to update active highlight styling
    fetchHistory();
    
    showDetailState('loading');
    loadingTitle.textContent = "Loading Interview Data...";
    loadingDesc.textContent = "Fetching transcripts and analysis from database...";
    loadingStatusText.textContent = "Loading";
    
    pollJobStatus(jobId);
}

// Poll status of processing/pending jobs or load completed results
async function pollJobStatus(jobId) {
    const fetchStatus = async () => {
        try {
            const response = await fetch(`/api/jobs/${jobId}`);
            if (!response.ok) {
                if (response.status === 404) {
                    showDetailState('empty');
                    clearInterval(pollInterval);
                }
                throw new Error('Failed to fetch job details');
            }
            const job = await response.json();
            
            // Check if user has switched to a different job in the meantime
            if (currentJobId !== jobId) {
                clearInterval(pollInterval);
                return;
            }

            if (job.status === 'PENDING' || job.status === 'PROCESSING') {
                showDetailState('loading');
                loadingTitle.textContent = job.status === 'PENDING' ? "Waiting in Queue..." : "Transcribing & Analyzing Interview...";
                loadingDesc.textContent = job.status === 'PENDING' 
                    ? "Your audio is queued. Once started, Whisper will transcribe it and the local LLM will provide coaching notes." 
                    : "The Whisper speech-to-text model is converting your audio to text. Then Ollama (llama3.2) will analyze it. This may take a few minutes.";
                loadingStatusText.textContent = job.status;
            } else if (job.status === 'COMPLETED') {
                clearInterval(pollInterval);
                pollInterval = null;
                renderResult(job);
            } else if (job.status === 'FAILED') {
                clearInterval(pollInterval);
                pollInterval = null;
                showDetailState('error');
                errorMessageText.textContent = job.error_message || 'An error occurred during audio transcription or model analysis.';
            }
        } catch (err) {
            console.error('Error fetching job status:', err);
        }
    };
    
    // Run immediately
    await fetchStatus();
    
    // If still active, poll every 5 seconds
    if (currentJobId === jobId && !pollInterval) {
        pollInterval = setInterval(fetchStatus, 5000);
    }
}

// Render completed job details
function renderResult(job) {
    showDetailState('result');
    resultTitle.textContent = job.filename;
    resultTitle.title = job.filename;
    
    const date = new Date(job.created_at).toLocaleDateString(undefined, {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
    resultDate.textContent = `Processed on ${date}`;

    // Render LLM analysis using Marked (markdown to html)
    if (job.analysis) {
        panelAnalysis.innerHTML = marked.parse(job.analysis);
    } else {
        panelAnalysis.innerHTML = `<div class="text-slate-400 italic">No feedback analysis available.</div>`;
    }

    // Render Transcript
    if (job.transcript) {
        panelTranscript.textContent = job.transcript;
    } else {
        panelTranscript.textContent = "No transcript content found.";
    }

    // Render Job Description if present
    if (job.job_description) {
        jdDisplayContainer.classList.remove('hidden');
        jdDisplayText.textContent = job.job_description;
    } else {
        jdDisplayContainer.classList.add('hidden');
    }

    // Default to analysis tab
    switchTab('analysis');
}

// Helper to switch right-hand panels
function showDetailState(state) {
    emptyState.classList.add('hidden');
    loadingState.classList.add('hidden');
    errorState.classList.add('hidden');
    resultDashboard.classList.add('hidden');

    if (state === 'empty') emptyState.classList.remove('hidden');
    else if (state === 'loading') loadingState.classList.remove('hidden');
    else if (state === 'error') errorState.classList.remove('hidden');
    else if (state === 'result') resultDashboard.classList.remove('hidden');
}

// Start audio file upload using XMLHttpRequest for progress reporting
function startUpload() {
    if (!selectedFile) return;

    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('job_description', jdInput.value ? jdInput.value.trim() : '');

    const xhr = new XMLHttpRequest();
    
    // Set up upload progress events
    xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
            const percentComplete = Math.round((e.loaded / e.total) * 100);
            progressContainer.classList.remove('hidden');
            progressBar.style.width = `${percentComplete}%`;
            progressPercent.textContent = `${percentComplete}%`;
            uploadBtn.disabled = true;
        }
    });

    xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
            try {
                const response = JSON.parse(xhr.responseText);
                resetFileUpload();
                
                // Fetch list and auto-select the newly created job
                fetchHistory().then(() => {
                    selectJob(response.job_id);
                });
            } catch (err) {
                alert('Upload succeeded but server response couldn\'t be parsed.');
                resetFileUpload();
            }
        } else {
            let errorMsg = 'Upload failed.';
            try {
                const errorData = JSON.parse(xhr.responseText);
                errorMsg += ` ${errorData.detail || ''}`;
            } catch(e) {}
            alert(errorMsg);
            resetFileUpload();
        }
    });

    xhr.addEventListener('error', () => {
        alert('An network error occurred while uploading.');
        resetFileUpload();
    });

    xhr.open('POST', '/api/upload');
    xhr.send(formData);
}

// Delete job call
async function deleteJob(jobId) {
    try {
        const response = await fetch(`/api/jobs/${jobId}`, {
            method: 'DELETE'
        });
        if (!response.ok) throw new Error('Failed to delete job');
        
        if (currentJobId === jobId) {
            currentJobId = null;
            showDetailState('empty');
        }
        
        fetchHistory();
    } catch (err) {
        console.error('Error deleting job:', err);
        alert('Could not delete job.');
    }
}

// Escape HTML utility
function escapeHtml(text) {
    if (!text) return '';
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
