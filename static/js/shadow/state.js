/**
 * Shadowing State Machine - Client-side mirror of server state machine.
 * Steps: 1=WatchNoText, 2=WatchWithText, 3=Practice, 4=AIAnalysis, 5=Feedback, 6=ReplayErrors, 7=Completed
 */

export const ShadowStep = {
    WATCH_NO_TEXT: 1,
    WATCH_WITH_TEXT: 2,
    PRACTICE: 3,
    AI_ANALYSIS: 4,
    FEEDBACK: 5,
    REPLAY_ERRORS: 6,
    COMPLETED: 7
};

export const STEP_NAMES = {
    [ShadowStep.WATCH_NO_TEXT]: 'Watch (No Text)',
    [ShadowStep.WATCH_WITH_TEXT]: 'Watch (With Text)',
    [ShadowStep.PRACTICE]: 'Practice Segments',
    [ShadowStep.AI_ANALYSIS]: 'AI Analysis',
    [ShadowStep.FEEDBACK]: 'Feedback',
    [ShadowStep.REPLAY_ERRORS]: 'Replay Errors',
    [ShadowStep.COMPLETED]: 'Completed'
};

export const STEP_DESCRIPTIONS = {
    [ShadowStep.WATCH_NO_TEXT]: 'Videoni matnsiz ko\'ring va eshitib oling',
    [ShadowStep.WATCH_WITH_TEXT]: 'Videoni karaoke matni bilan ko\'ring',
    [ShadowStep.PRACTICE]: 'Har bir segmentni eshitib, o\'zingiz gapiring',
    [ShadowStep.AI_ANALYSIS]: 'AI tahlil natijalari yig\'ilmoqda...',
    [ShadowStep.FEEDBACK]: 'Xatolarni ko\'ring va to\'g\'rilang',
    [ShadowStep.REPLAY_ERRORS]: 'Xatolik bor qismlarni qayta gapiring',
    [ShadowStep.COMPLETED]: 'Tabriklaymiz! Dars 100% tugallandi'
};

export const VALID_TRANSITIONS = {
    [ShadowStep.WATCH_NO_TEXT]: [ShadowStep.WATCH_WITH_TEXT],
    [ShadowStep.WATCH_WITH_TEXT]: [ShadowStep.PRACTICE],
    [ShadowStep.PRACTICE]: [ShadowStep.PRACTICE, ShadowStep.AI_ANALYSIS, ShadowStep.FEEDBACK],
    [ShadowStep.AI_ANALYSIS]: [ShadowStep.FEEDBACK],
    [ShadowStep.FEEDBACK]: [ShadowStep.PRACTICE, ShadowStep.REPLAY_ERRORS, ShadowStep.COMPLETED],
    [ShadowStep.REPLAY_ERRORS]: [ShadowStep.PRACTICE],
    [ShadowStep.COMPLETED]: []
};

/**
 * Client-side State Machine for UI rendering
 */
export class ShadowStateMachine {
    constructor(initialState = {}) {
        this.step = initialState.step || ShadowStep.WATCH_NO_TEXT;
        this.current_segment = initialState.current_segment || 0;
        this.total_segments = initialState.total_segments || 0;
        this.passed_segments = new Set(initialState.passed_segments || []);
        this.segment_scores = initialState.segment_scores || {};
        this.progress = initialState.progress || 0;
        this.average_score = initialState.average_score || 0;
    }

    getCurrentState() {
        return {
            step: this.step,
            name: STEP_NAMES[this.step],
            description: STEP_DESCRIPTIONS[this.step],
            can_advance: this.canAdvance(),
            next_steps: this.getValidNextSteps()
        };
    }

    getValidNextSteps() {
        return VALID_TRANSITIONS[this.step] || [];
    }

    canAdvance(targetStep = null) {
        const valid = this.getValidNextSteps();
        if (targetStep) return valid.includes(targetStep);
        return valid.length > 0;
    }

    advance(targetStep) {
        if (this.canAdvance(targetStep)) {
            this.step = targetStep;
            return true;
        }
        return false;
    }

    markSegmentPassed(segmentIndex, score) {
        this.passed_segments.add(segmentIndex);
        this.segment_scores[segmentIndex] = score;
        this.recomputeProgress();
    }

    getFailedSegments() {
        const all = new Set(Array.from({ length: this.total_segments }, (_, i) => i));
        return [...all].filter(i => !this.passed_segments.has(i));
    }

    getNextSegmentToPractice() {
        const failed = this.getFailedSegments();
        if (failed.length > 0) return failed[0];

        // All passed
        if (this.passed_segments.size >= this.total_segments) return null;

        // Current if not passed
        if (!this.passed_segments.has(this.current_segment)) return this.current_segment;

        // Next unpassed
        for (let i = this.current_segment + 1; i < this.total_segments; i++) {
            if (!this.passed_segments.has(i)) return i;
        }
        return null;
    }

    recomputeProgress() {
        if (this.total_segments === 0) {
            this.progress = 0;
            this.average_score = 0;
            return;
        }
        this.progress = Math.round((this.passed_segments.size / this.total_segments) * 100 * 10) / 10;
        if (Object.keys(this.segment_scores).length > 0) {
            const scores = Object.values(this.segment_scores);
            this.average_score = Math.round((scores.reduce((a, b) => a + b, 0) / scores.length) * 10) / 10;
        }
    }

    isCompleted() {
        return this.passed_segments.size >= this.total_segments && this.total_segments > 0;
    }

    // Sync from server response
    updateFromServer(serverState) {
        this.step = serverState.step || this.step;
        this.current_segment = serverState.current_segment || this.current_segment;
        this.total_segments = serverState.total_segments || this.total_segments;
        this.passed_segments = new Set(serverState.passed_segments || []);
        this.segment_scores = serverState.segment_scores || {};
        this.progress = serverState.progress || this.progress;
        this.average_score = serverState.average_score || this.average_score;
    }

    toDict() {
        return {
            step: this.step,
            current_segment: this.current_segment,
            total_segments: this.total_segments,
            passed_segments: [...this.passed_segments],
            segment_scores: this.segment_scores,
            progress: this.progress,
            average_score: this.average_score
        };
    }
}

export function createInitialState(totalSegments) {
    return {
        step: ShadowStep.WATCH_NO_TEXT,
        current_segment: 0,
        total_segments: totalSegments,
        passed_segments: [],
        segment_scores: {},
        progress: 0,
        average_score: 0
    };
}