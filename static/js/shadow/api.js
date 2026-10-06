/**
 * API wrapper for Shadowing endpoints.
 * Handles CSRF tokens and JSON requests.
 */

const API_BASE = '/dashboard/api';

function getCsrfToken() {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, 'csrftoken'.length + 1) === ('csrftoken' + '=')) {
                cookieValue = decodeURIComponent(cookie.substring('csrftoken'.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

async function apiRequest(endpoint, options = {}) {
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        }
    };

    const mergedOptions = {
        ...defaultOptions,
        ...options,
        headers: {
            ...defaultOptions.headers,
            ...(options.headers || {})
        }
    };

    const response = await fetch(`${API_BASE}${endpoint}`, mergedOptions);
    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.error || `API error: ${response.status}`);
    }

    return data;
}

// Transcript API
export async function createTranscript({ lesson_id, youtube_url, video_file, language = 'en' }) {
    if (video_file) {
        const formData = new FormData();
        formData.append('lesson_id', lesson_id);
        formData.append('video_file', video_file);
        formData.append('language', language);

        const response = await fetch(`${API_BASE}/transcript/`, {
            method: 'POST',
            headers: { 'X-CSRFToken': getCsrfToken() },
            body: formData
        });
        return response.json();
    } else {
        return apiRequest('/transcript/', {
            method: 'POST',
            body: JSON.stringify({ lesson_id, youtube_url, language })
        });
    }
}

export async function getTranscriptStatus(transcript_id) {
    return apiRequest(`/transcript/${transcript_id}/`);
}

// Session API
export async function startSession(lesson_id) {
    return apiRequest('/session/start/', {
        method: 'POST',
        body: JSON.stringify({ lesson_id })
    });
}

export async function getSession(session_id) {
    return apiRequest(`/session/${session_id}/`);
}

export async function advanceSession(session_id, step) {
    return apiRequest(`/session/${session_id}/advance/`, {
        method: 'POST',
        body: JSON.stringify({ step })
    });
}

export async function analyzeSegment(session_id, segment_index, recording_blob) {
    const formData = new FormData();
    formData.append('segment_index', segment_index);
    formData.append('recording', recording_blob, `segment_${segment_index}.webm`);

    const response = await fetch(`${API_BASE}/session/${session_id}/segment/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCsrfToken() },
        body: formData
    });
    return response.json();
}

export async function getSessionProgress(session_id) {
    return apiRequest(`/session/${session_id}/progress/`);
}

export async function completeSession(session_id) {
    return apiRequest(`/session/${session_id}/complete/`, {
        method: 'POST'
    });
}