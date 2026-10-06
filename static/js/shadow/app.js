/**
 * Main Shadowing Application.
 * Orchestrates state machine, video player, recorder, and API calls.
 */

import { ShadowStateMachine, ShadowStep, createInitialState } from './state.js';
import { VideoPlayer } from './videoPlayer.js';
import { SegmentRecorder, checkMicrophonePermission, requestMicrophonePermission } from './recorder.js';
import { FeedbackDisplay, SegmentFeedbackSummary } from './feedback.js';
import {
    startSession, getSession, advanceSession,
    analyzeSegment, completeSession, getSessionProgress
} from './api.js';

// ── State ─────────────────────────────────────────────────────────────────────
let stateMachine = null;
let videoPlayer = null;
let recorder = null;
let feedbackDisplay = null;
let segmentSummary = null;

let currentSessionId = null;
let currentLessonId = null;
let isProcessing = false;

// ── DOM Elements ──────────────────────────────────────────────────────────────
const elements = {
    lessonTitle: document.getElementById('lesson-title'),
    stepBadge: document.getElementById('step-badge'),
    progressText: document.getElementById('progress-text'),
    videoWrapper: document.getElementById('video-wrapper'),
    karaokeText: document.getElementById('karaoke-text'),
    playerControls: document.getElementById('player-controls'),
    recordingStatus: document.getElementById('recording-status'),
    feedbackContainer: document.getElementById('feedback-container'),
    finalScore: document.getElementById('final-score'),
    btnRecord: document.getElementById('btn-record'),
    btnSubmit: document.getElementById('btn-submit'),
    segmentCurrent: document.getElementById('segment-current'),
};

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    // Get lesson_id and session_id from DOM
    const container = document.querySelector('.shadow-player-container');
    if (!container) {
        showError('Player container not found');
        return;
    }

    currentLessonId = container.dataset.lessonId;
    currentSessionId = container.dataset.sessionId;

    if (!currentLessonId) {
        showError('Lesson ID not found');
        return;
    }

    // Initialize components
    initComponents();

    // Load or create session
    await loadOrCreateSession();

    // Check microphone permission
    await checkMicPermission();
});

async function loadOrCreateSession() {
    // If we have a session_id, load it
    if (currentSessionId) {
        await loadSession();
        return;
    }

    // Otherwise, start a new session
    try {
        showRecordingStatus('Sessiya yaratilmoqda...', 'info');
        const data = await startSession(currentLessonId);
        currentSessionId = data.session_id;

        // Update URL without reload
        const url = new URL(window.location.href);
        url.searchParams.set('session_id', currentSessionId);
        window.history.replaceState({}, '', url);

        await loadSession();
    } catch (error) {
        console.error('Failed to create session:', error);
        showError('Sessiya yaratilmadi: ' + error.message);
    }
}

function initComponents() {
    // Feedback display
    feedbackDisplay = new FeedbackDisplay('feedback-container');

    // Segment feedback summary
    segmentSummary = new SegmentFeedbackSummary('feedback-container');

    // Recorder
    recorder = new SegmentRecorder({
        onStart: () => onRecordingStart(),
        onStop: (blob) => onRecordingStop(blob),
        onError: (error) => onRecordingError(error)
    });
}

async function checkMicPermission() {
    const status = await checkMicrophonePermission();
    if (status === 'denied') {
        showRecordingStatus('Mikrofon ruxsati berilmagan. Brauzer sozlamalaridan ruxsat bering.', 'error');
    }
}

// ── Session Loading ───────────────────────────────────────────────────────────
async function loadSession() {
    try {
        const data = await getSession(currentSessionId);
        currentLessonId = data.lesson_id || null;

        // Initialize state machine
        stateMachine = new ShadowStateMachine(data);

        // Update UI
        updateStepUI(data.step);
        updateProgress(data.progress, data.average_score);

        // Setup video player if segments available
        if (data.segments && data.words) {
            setupVideoPlayer(data);
        }

        // Load lesson title
        if (elements.lessonTitle) {
            const container = document.querySelector('.shadow-player-container');
            const lessonTitle = container?.dataset.lessonTitle || '';
            if (lessonTitle) {
                elements.lessonTitle.textContent = lessonTitle;
            }
        }

    } catch (error) {
        console.error('Failed to load session:', error);
        showError('Sessiya yuklanmadi: ' + error.message);
    }
}

function setupVideoPlayer(sessionData) {
    const videoWrapper = elements.videoWrapper;
    const karaokeEl = elements.karaokeText;

    // Get video URL and source type from the wrapper
    const videoUrl = videoWrapper.dataset.videoUrl || '';
    const sourceType = videoWrapper.dataset.sourceType || (videoUrl.includes('youtube') ? 'youtube' : 'html5');

    videoPlayer = new VideoPlayer('video-wrapper', {
        sourceType: sourceType,
        videoUrl: videoUrl,
        segments: sessionData.segments,
        words: sessionData.words,
        language: sessionData.transcript_language || 'en',
        onTimeUpdate: (time) => onVideoTimeUpdate(time),
        onSegmentEnd: (segIndex) => onSegmentEnd(segIndex),
        onReady: () => onPlayerReady()
    });

    videoPlayer.setKaraokeElement(karaokeEl);
    videoPlayer.init().catch(console.error);
}

function onPlayerReady() {
    console.log('Player ready');
    // Auto-play based on step
    const currentStep = stateMachine?.step;
    if (currentStep === ShadowStep.WATCH_NO_TEXT || currentStep === ShadowStep.WATCH_WITH_TEXT) {
        videoPlayer?.play();
    } else if (currentStep === ShadowStep.PRACTICE) {
        // Automatically play the current segment when page loads in Practice mode
        if (stateMachine && videoPlayer) {
            const nextSeg = stateMachine.current_segment;
            if (nextSeg !== null) {
                videoPlayer.playSegment(nextSeg);
            }
        }
    }
}

function onVideoTimeUpdate(currentTime) {
    // Update progress ring if needed
}

function onSegmentEnd(segmentIndex) {
    console.log('Segment ended:', segmentIndex);
    // Could auto-advance in practice mode
}

// ── Step UI Management ────────────────────────────────────────────────────────
function updateStepUI(step) {
    // Hide all step UIs
    document.querySelectorAll('.step-ui').forEach(el => el.style.display = 'none');

    // Show current step UI
    const stepEl = document.getElementById(`step-${step}`);
    if (stepEl) stepEl.style.display = 'flex';

    // Update badge
    if (elements.stepBadge) elements.stepBadge.textContent = step;

    // Step-specific logic
    switch (step) {
        case ShadowStep.WATCH_NO_TEXT:
            // Video plays without karaoke (already handled by video player)
            break;
        case ShadowStep.WATCH_WITH_TEXT:
            // Video plays with karaoke (already shown)
            break;
        case ShadowStep.PRACTICE:
            initPracticeMode();
            break;
        case ShadowStep.AI_ANALYSIS:
            // Handled by server, just wait
            break;
        case ShadowStep.FEEDBACK:
            renderFeedback();
            break;
        case ShadowStep.REPLAY_ERRORS:
            initReplayErrors();
            break;
        case ShadowStep.COMPLETED:
            renderCompletion();
            break;
    }
}

function updateProgress(progress, avgScore) {
    if (elements.progressText) {
        elements.progressText.textContent = `${progress}%`;
    }

    // Update conic gradient
    const progressRing = document.querySelector('.progress-ring');
    if (progressRing) {
        const degrees = (progress / 100) * 360;
        progressRing.style.background = `conic-gradient(var(--p3) ${degrees}deg, rgba(255,255,255,0.05) ${degrees}deg)`;
    }
}

function initPracticeMode() {
    if (!stateMachine) return;

    const nextSeg = stateMachine.getNextSegmentToPractice();
    if (nextSeg === null) {
        // All passed, advance to analysis
        advanceToAnalysis();
        return;
    }

    stateMachine.current_segment = nextSeg;
    updateSegmentInfo();

    // Play the segment for reference
    if (videoPlayer) {
        videoPlayer.playSegment(nextSeg);
    }
}

function updateSegmentInfo() {
    if (elements.segmentCurrent && stateMachine) {
        elements.segmentCurrent.textContent = `Segment ${stateMachine.current_segment + 1} / ${stateMachine.total_segments}`;
    }
}

async function advanceToAnalysis() {
    // Advance session to step 4 on server
    try {
        await advanceSession(currentSessionId, ShadowStep.AI_ANALYSIS);
        // Reload session to get updated state
        await loadSession();
    } catch (error) {
        console.error('Failed to advance to analysis:', error);
    }
}

// ── Recording ─────────────────────────────────────────────────────────────────
async function toggleRecording() {
    if (recorder.isRecording) {
        stopRecording();
    } else {
        await startRecording();
    }
}

async function startRecording() {
    if (!stateMachine) return;

    const hasPermission = await requestMicrophonePermission();
    if (!hasPermission) {
        showRecordingStatus('Mikrofon ruxsati kerak. Brauzer sozlamalaridan ruxsat bering.', 'error');
        return;
    }

    try {
        await recorder.start();
    } catch (error) {
        showRecordingStatus('Yozishni boshlashda xato: ' + error.message, 'error');
    }
}

function stopRecording() {
    recorder.stop();
}

function onRecordingStart() {
    if (elements.btnRecord) {
        elements.btnRecord.classList.add('recording');
        elements.btnRecord.innerHTML = '<span class="rec-icon"></span> Yozilmoqda... (To\'xtatish uchun bosing)';
    }
    if (elements.btnSubmit) elements.btnSubmit.disabled = true;
    showRecordingStatus('���� Yozilmoqda... Gapiring', 'recording');
}

function onRecordingStop(blob) {
    if (elements.btnRecord) {
        elements.btnRecord.classList.remove('recording');
        elements.btnRecord.innerHTML = '<span class="rec-icon"></span> Yozishni boshlash';
    }
    if (elements.btnSubmit) elements.btnSubmit.disabled = false;
    showRecordingStatus('��� Yozuv tayyor. Yuborish tugmasini bosing.', 'success');
}

function onRecordingError(error) {
    showRecordingStatus('Xato: ' + error.message, 'error');
    if (elements.btnRecord) {
        elements.btnRecord.classList.remove('recording');
        elements.btnRecord.innerHTML = '<span class="rec-icon"></span> Yozishni boshlash';
    }
}

async function submitRecording() {
    if (!stateMachine || !recorder) return;

    const blob = await recorder.getBlob();
    if (!blob) {
        showRecordingStatus('Yozuv topilmadi', 'error');
        return;
    }

    const segmentIndex = stateMachine.current_segment;
    isProcessing = true;

    showRecordingStatus('AI tahlil qilmoqda...', 'info');

    try {
        const result = await analyzeSegment(currentSessionId, segmentIndex, blob);

        if (result.passed) {
            // Mark segment as passed in local state
            stateMachine.markSegmentPassed(segmentIndex, result.score);

            // Check if there are more segments to practice
            const nextSegment = stateMachine.getNextSegmentToPractice();

            if (nextSegment === null) {
                // All segments passed - advance to AI_ANALYSIS then FEEDBACK
                stateMachine.advance(ShadowStep.AI_ANALYSIS);
                await advanceSession(currentSessionId, ShadowStep.AI_ANALYSIS);

                // Auto-advance to FEEDBACK
                stateMachine.advance(ShadowStep.FEEDBACK);
                await advanceSession(currentSessionId, ShadowStep.FEEDBACK);

                showRecordingStatus(`O'tdingiz! Ball: ${result.score}%`, 'success');
            } else {
                // More segments to practice - stay in PRACTICE
                stateMachine.advance(ShadowStep.PRACTICE);
                await advanceSession(currentSessionId, ShadowStep.PRACTICE);

                showRecordingStatus(`O'tdingiz! Ball: ${result.score}% - Keyingi segment`, 'success');
            }

            // Reload session to sync
            setTimeout(async () => {
                await loadSession();
            }, 1500);
        } else {
            // Failed - show feedback with retry option
            stateMachine.advance(ShadowStep.FEEDBACK);
            await advanceSession(currentSessionId, ShadowStep.FEEDBACK);
            await loadSession(); // Will show feedback
        }
    } catch (error) {
        console.error('Analysis error:', error);
        showRecordingStatus('Xato: ' + error.message, 'error');
    } finally {
        isProcessing = false;
    }
}

function showRecordingStatus(message, type = 'info') {
    if (!elements.recordingStatus) return;

    const colors = {
        info: 'var(--p3)',
        success: '#10b981',
        error: '#ef4444',
        recording: '#ef4444'
    };

    elements.recordingStatus.textContent = message;
    elements.recordingStatus.style.color = colors[type] || 'var(--text-sec)';
}

// ── Feedback Rendering ────────────────────────────────────────────────────────
async function renderFeedback() {
    // Get latest segment attempt for current segment
    try {
        const sessionData = await getSession(currentSessionId);

        // Find latest attempt for current segment
        const currentSeg = stateMachine?.current_segment || 0;

        // We'd need to get the attempt data - for now show summary
        if (segmentSummary && sessionData.segments) {
            const passed = sessionData.passed_segments || [];
            const failed = sessionData.failed_segments || [];
            segmentSummary.render(sessionData.segments, passed, failed);
        }

        // Set up buttons based on failed segments
        const failedSegments = sessionData.failed_segments || [];
        const feedbackActions = document.querySelector('.feedback-actions');

        if (feedbackActions) {
            feedbackActions.innerHTML = '';

            if (failedSegments.length > 0) {
                // Has failed segments - show retry and continue to replay errors
                const retryBtn = document.createElement('button');
                retryBtn.className = 'btn-primary';
                retryBtn.textContent = 'Xato qismni qayta gapirish';
                retryBtn.onclick = () => handleRetryFailed();
                feedbackActions.appendChild(retryBtn);
            } else {
                // All passed - complete
                const completeBtn = document.createElement('button');
                completeBtn.className = 'btn-primary';
                completeBtn.textContent = 'Darsni tugatish';
                completeBtn.onclick = () => handleComplete();
                feedbackActions.appendChild(completeBtn);
            }
        }
    } catch (error) {
        console.error('Failed to render feedback:', error);
    }
}

function handleRetryFailed() {
    // Go back to practice mode for failed segments
    advanceSession(currentSessionId, ShadowStep.PRACTICE).then(() => loadSession());
}

async function handleComplete() {
    try {
        const result = await completeSession(currentSessionId);
        if (result.status === 'completed') {
            stateMachine.advance(ShadowStep.COMPLETED);
            updateStepUI(ShadowStep.COMPLETED);
        }
    } catch (error) {
        console.error('Complete error:', error);
    }
}

function initReplayErrors() {
    // Similar to practice but only for failed segments
    initPracticeMode();
}

function renderCompletion() {
    if (elements.finalScore && stateMachine) {
        elements.finalScore.textContent = `${stateMachine.average_score}%`;
    }
}

// ── Navigation ────────────────────────────────────────────────────────────────
window.advanceStep = async function(step) {
    if (!stateMachine || !stateMachine.canAdvance(step)) return;

    try {
        await advanceSession(currentSessionId, step);
        stateMachine.advance(step);
        updateStepUI(step);
    } catch (error) {
        console.error('Advance step error:', error);
        alert('Bosqichni o\'tkazib bo\'lmadi: ' + error.message);
    }
};

window.playCurrentSegment = function() {
    if (videoPlayer && stateMachine) {
        videoPlayer.playSegment(stateMachine.current_segment);
    }
};

window.toggleRecording = toggleRecording;
window.submitRecording = submitRecording;

window.goBack = function() {
    window.history.back();
};

window.handleFeedbackAction = function() {
    // Handled by renderFeedback buttons
};

function showError(message) {
    const container = document.querySelector('.shadow-player-container');
    if (container) {
        container.innerHTML = `
            <div style="text-align: center; padding: 60px; color: #ef4444;">
                <h2>Xato</h2>
                <p>${message}</p>
                <button class="btn-primary" onclick="goBack()">Orqaga qaytish</button>
            </div>
        `;
    }
}