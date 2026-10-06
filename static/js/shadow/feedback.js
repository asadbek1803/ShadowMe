/**
 * Feedback Display Component.
 * Renders word-level phoneme feedback with color coding.
 */

export class FeedbackDisplay {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.onRetry = null;
        this.onContinue = null;
    }

    render(feedbackData, segmentInfo = {}) {
        if (!this.container) return;

        const { word_feedback, score, passed, accuracy, fluency } = feedbackData;

        let html = `
            <div class="feedback-header">
                <div class="feedback-score ${passed ? 'passed' : 'failed'}">
                    <span class="score-value">${score}%</span>
                    <span class="score-label">${passed ? 'O\'tdi' : 'O\'tmadi'}</span>
                </div>
                <div class="feedback-details">
                    <div class="detail">
                        <span class="detail-value">${accuracy}%</span>
                        <span class="detail-label">Aniqlik</span>
                    </div>
                    <div class="detail">
                        <span class="detail-value">${fluency}%</span>
                        <span class="detail-label">Tekinlik</span>
                    </div>
                </div>
            </div>
            <div class="feedback-words">
        `;

        if (word_feedback && word_feedback.length > 0) {
            word_feedback.forEach((word, index) => {
                const statusClass = word.status || 'unknown';
                const statusLabel = this.getStatusLabel(word.status);
                const confidence = word.confidence !== undefined ? ` (${Math.round(word.confidence * 100)}%)` : '';

                html += `
                    <div class="feedback-word ${statusClass}" data-index="${index}">
                        <span class="word-text">${word.word || word.expected || ''}</span>
                        <div class="word-info">
                            <span class="word-status ${statusClass}">${statusLabel}${confidence}</span>
                            ${word.detected && word.detected !== word.expected ? `<span class="word-detected">Siz: "${word.detected}"</span>` : ''}
                        </div>
                    </div>
                `;
            });
        }

        html += '</div>';
        this.container.innerHTML = html;

        // Add styles if not present
        this.injectStyles();
    }

    getStatusLabel(status) {
        const labels = {
            'correct': 'To\'g\'ri',
            'mispronounced': 'Noto\'g\'ri',
            'omitted': 'O\'tkazib yuborilgan',
            'extra': 'Qo\'shimcha'
        };
        return labels[status] || status;
    }

    showRetryButton(onRetry) {
        this.onRetry = onRetry;
        const retryBtn = document.createElement('button');
        retryBtn.className = 'btn-secondary';
        retryBtn.textContent = 'Qayta urinish';
        retryBtn.onclick = () => onRetry && onRetry();
        this.container.appendChild(retryBtn);
    }

    showContinueButton(onContinue) {
        this.onContinue = onContinue;
        const continueBtn = document.createElement('button');
        continueBtn.className = 'btn-primary';
        continueBtn.textContent = 'Keyingisiga';
        continueBtn.onclick = () => onContinue && onContinue();
        this.container.appendChild(continueBtn);
    }

    injectStyles() {
        if (document.getElementById('feedback-styles')) return;

        const style = document.createElement('style');
        style.id = 'feedback-styles';
        style.textContent = `
            .feedback-header {
                display: flex; justify-content: space-between; align-items: center;
                margin-bottom: 20px; padding-bottom: 16px; border-bottom: 1px solid var(--border);
            }
            .feedback-score {
                display: flex; flex-direction: column; align-items: center;
                padding: 16px 24px; border-radius: 12px;
                min-width: 80px;
            }
            .feedback-score.passed { background: rgba(16,185,129,0.1); }
            .feedback-score.failed { background: rgba(239,68,68,0.1); }
            .score-value { font-size: 28px; font-weight: 800; }
            .score-value.passed { color: #10b981; }
            .score-value.failed { color: #ef4444; }
            .score-label { font-size: 12px; color: var(--text-sec); margin-top: 4px; }
            .feedback-details { display: flex; gap: 24px; }
            .detail { display: flex; flex-direction: column; align-items: center; }
            .detail-value { font-size: 18px; font-weight: 700; color: var(--p3); }
            .detail-label { font-size: 11px; color: var(--text-mut); text-transform: uppercase; }
            .feedback-words { display: flex; flex-direction: column; gap: 8px; max-height: 300px; overflow-y: auto; }
            .feedback-word {
                padding: 12px 16px; border-radius: 10px;
                background: rgba(0,0,0,0.2); border: 1px solid var(--border);
                display: flex; justify-content: space-between; align-items: flex-start;
            }
            .feedback-word.correct { border-color: rgba(16,185,129,0.3); }
            .feedback-word.mispronounced { border-color: rgba(239,68,68,0.4); background: rgba(239,68,68,0.05); }
            .feedback-word.omitted { border-color: rgba(245,158,11,0.4); background: rgba(245,158,11,0.05); }
            .feedback-word.extra { border-color: rgba(99,102,241,0.4); background: rgba(99,102,241,0.05); }
            .word-text { font-size: 16px; font-weight: 600; }
            .word-info { display: flex; flex-direction: column; gap: 4px; text-align: right; }
            .word-status { font-size: 12px; font-weight: 600; }
            .word-status.correct { color: #10b981; }
            .word-status.mispronounced { color: #ef4444; }
            .word-status.omitted { color: #f59e0b; }
            .word-status.extra { color: #6366f1; }
            .word-detected { font-size: 11px; color: var(--text-mut); font-style: italic; }
        `;
        document.head.appendChild(style);
    }

    clear() {
        if (this.container) this.container.innerHTML = '';
    }
}

/**
 * Segment Feedback Summary for step 5 (Feedback screen)
 */
export class SegmentFeedbackSummary {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
    }

    render(segments, passedSegments, failedSegments) {
        if (!this.container) return;

        let html = '<div class="segment-summary">';

        segments.forEach((segment, index) => {
            const isPassed = passedSegments.includes(index);
            const isFailed = failedSegments.includes(index);

            html += `
                <div class="segment-summary-item ${isPassed ? 'passed' : (isFailed ? 'failed' : 'pending')}">
                    <span class="segment-number">${index + 1}</span>
                    <span class="segment-text">${segment.text.substring(0, 50)}${segment.text.length > 50 ? '...' : ''}</span>
                    <span class="segment-status">
                        ${isPassed ? '��� O\'tdi' : isFailed ? '��� Qayta' : '��� Kutilmoqda'}
                    </span>
                </div>
            `;
        });

        html += '</div>';
        this.container.innerHTML = html;
        this.injectStyles();
    }

    injectStyles() {
        if (document.getElementById('segment-summary-styles')) return;

        const style = document.createElement('style');
        style.id = 'segment-summary-styles';
        style.textContent = `
            .segment-summary { display: flex; flex-direction: column; gap: 8px; }
            .segment-summary-item {
                display: flex; align-items: center; gap: 12px;
                padding: 12px 16px; border-radius: 10px;
                background: rgba(0,0,0,0.2); border: 1px solid var(--border);
            }
            .segment-summary-item.passed { border-color: rgba(16,185,129,0.3); }
            .segment-summary-item.failed { border-color: rgba(239,68,68,0.4); background: rgba(239,68,68,0.05); }
            .segment-summary-item.pending { opacity: 0.6; }
            .segment-number { width: 28px; height: 28px; border-radius: 50%;
                background: var(--p1); color: #fff; font-size: 12px; font-weight: 700;
                display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
            .segment-summary-item.passed .segment-number { background: #10b981; }
            .segment-summary-item.failed .segment-number { background: #ef4444; }
            .segment-text { flex: 1; font-size: 14px; }
            .segment-status { font-size: 12px; font-weight: 600; }
            .segment-summary-item.passed .segment-status { color: #10b981; }
            .segment-summary-item.failed .segment-status { color: #ef4444; }
            .segment-summary-item.pending .segment-status { color: var(--text-mut); }
        `;
        document.head.appendChild(style);
    }
}