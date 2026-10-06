"""
Shadowing Session State Machine.
Implements the 6-step flow: Watch → Watch+Text → Practice → Analysis → Feedback → Replay Errors.
"""
from enum import IntEnum
from dataclasses import dataclass
from typing import Optional, List, Dict, Any


class ShadowStep(IntEnum):
    """6 steps of the shadowing flow."""
    WATCH_NO_TEXT = 1      # Video only, no captions
    WATCH_WITH_TEXT = 2    # Video + karaoke text
    PRACTICE = 3           # Per-segment recording loop
    AI_ANALYSIS = 4        # Aggregation screen
    FEEDBACK = 5           # Per-segment phoneme results
    REPLAY_ERRORS = 6      # Re-record failed segments
    COMPLETED = 7          # 100% - all passed


# Valid transitions: current_step -> [allowed_next_steps]
VALID_TRANSITIONS = {
    ShadowStep.WATCH_NO_TEXT: [ShadowStep.WATCH_WITH_TEXT],
    ShadowStep.WATCH_WITH_TEXT: [ShadowStep.PRACTICE],
    ShadowStep.PRACTICE: [ShadowStep.PRACTICE, ShadowStep.AI_ANALYSIS, ShadowStep.FEEDBACK],
    ShadowStep.AI_ANALYSIS: [ShadowStep.FEEDBACK],
    ShadowStep.FEEDBACK: [ShadowStep.PRACTICE, ShadowStep.REPLAY_ERRORS, ShadowStep.COMPLETED],
    ShadowStep.REPLAY_ERRORS: [ShadowStep.PRACTICE],
    ShadowStep.COMPLETED: [],
}

# Human-readable step names
STEP_NAMES = {
    ShadowStep.WATCH_NO_TEXT: "Watch (No Text)",
    ShadowStep.WATCH_WITH_TEXT: "Watch (With Text)",
    ShadowStep.PRACTICE: "Practice Segments",
    ShadowStep.AI_ANALYSIS: "AI Analysis",
    ShadowStep.FEEDBACK: "Feedback",
    ShadowStep.REPLAY_ERRORS: "Replay Errors",
    ShadowStep.COMPLETED: "Completed",
}

# Step descriptions for UI
STEP_DESCRIPTIONS = {
    ShadowStep.WATCH_NO_TEXT: "Videoni matnsiz ko'ring va eshitib oling",
    ShadowStep.WATCH_WITH_TEXT: "Videoni karaoke matni bilan ko'ring",
    ShadowStep.PRACTICE: "Har bir segmentni eshitib, o'zingiz gapiring",
    ShadowStep.AI_ANALYSIS: "AI tahlil natijalari yig'ilmoqda...",
    ShadowStep.FEEDBACK: "Xatolarni ko'ring va to'g'rilang",
    ShadowStep.REPLAY_ERRORS: "Xatolik bor qismlarni qayta gapiring",
    ShadowStep.COMPLETED: "Tabriklaymiz! Dars 100% tugallandi",
}


@dataclass
class StepState:
    """Current state of a step."""
    step: ShadowStep
    can_advance: bool
    next_steps: List[ShadowStep]
    description: str
    name: str


class ShadowStateMachine:
    """
    State machine for shadowing session.
    Pure Python - no Django dependencies for testability.
    """

    def __init__(self, session_data: Dict[str, Any]):
        """
        Initialize with session data.

        session_data should contain:
        - step: int (1-7)
        - current_segment: int
        - total_segments: int
        - passed_segments: List[int] (segment indices that passed)
        - segment_scores: Dict[int, float] (segment_index -> score)
        """
        self.step = ShadowStep(session_data.get('step', 1))
        self.current_segment = session_data.get('current_segment', 0)
        self.total_segments = session_data.get('total_segments', 0)
        self.passed_segments = set(session_data.get('passed_segments', []))
        self.segment_scores = session_data.get('segment_scores', {})

    def get_current_state(self) -> StepState:
        """Get current step state with valid transitions."""
        return StepState(
            step=self.step,
            can_advance=self.can_advance(),
            next_steps=self.get_valid_next_steps(),
            description=STEP_DESCRIPTIONS.get(self.step, ""),
            name=STEP_NAMES.get(self.step, "Unknown"),
        )

    def get_valid_next_steps(self) -> List[ShadowStep]:
        """Get valid next steps from current step."""
        return VALID_TRANSITIONS.get(self.step, [])

    def can_advance(self, target_step: Optional[ShadowStep] = None) -> bool:
        """Check if can advance to target_step (or any valid next step)."""
        valid_next = self.get_valid_next_steps()
        if target_step:
            return target_step in valid_next
        return len(valid_next) > 0

    def advance(self, target_step: ShadowStep) -> bool:
        """Advance to target step if valid."""
        if self.can_advance(target_step):
            self.step = target_step
            return True
        return False

    def auto_advance(self) -> Optional[ShadowStep]:
        """
        Automatically determine next step based on progress.
        Returns new step if advanced, None if should stay.
        """
        if self.step == ShadowStep.PRACTICE:
            # Check if all segments attempted
            if self.current_segment >= self.total_segments - 1:
                return ShadowStep.AI_ANALYSIS

        elif self.step == ShadowStep.FEEDBACK:
            # Check if any failed segments
            failed_segments = self.get_failed_segments()
            if failed_segments:
                return ShadowStep.REPLAY_ERRORS
            else:
                return ShadowStep.COMPLETED

        elif self.step == ShadowStep.REPLAY_ERRORS:
            # After replay, go back to practice for failed segments
            return ShadowStep.PRACTICE

        # For other steps, use first valid transition
        valid = self.get_valid_next_steps()
        if valid:
            return valid[0]
        return None

    def get_failed_segments(self) -> List[int]:
        """Get list of segment indices that haven't passed."""
        all_segments = set(range(self.total_segments))
        return sorted(all_segments - self.passed_segments)

    def get_next_segment_to_practice(self) -> Optional[int]:
        """Get the next segment index that needs practice."""
        failed = self.get_failed_segments()
        if failed:
            return failed[0]

        # If all passed, return None
        if len(self.passed_segments) >= self.total_segments:
            return None

        # Otherwise return current segment if not passed
        if self.current_segment not in self.passed_segments:
            return self.current_segment

        # Find next unpassed
        for i in range(self.current_segment + 1, self.total_segments):
            if i not in self.passed_segments:
                return i
        return None

    def mark_segment_passed(self, segment_index: int, score: float):
        """Mark a segment as passed with its score."""
        self.passed_segments.add(segment_index)
        self.segment_scores[segment_index] = score
        # Move to next segment
        next_seg = self.get_next_segment_to_practice()
        if next_seg is not None:
            self.current_segment = next_seg

    def get_progress(self) -> float:
        """Calculate progress percentage (0-100)."""
        if self.total_segments == 0:
            return 0.0
        return round((len(self.passed_segments) / self.total_segments) * 100, 1)

    def get_average_score(self) -> float:
        """Calculate average score of passed segments."""
        if not self.segment_scores:
            return 0.0
        return round(sum(self.segment_scores.values()) / len(self.segment_scores), 1)

    def is_completed(self) -> bool:
        """Check if all segments passed."""
        return len(self.passed_segments) >= self.total_segments and self.total_segments > 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state for storage/API."""
        return {
            'step': int(self.step),
            'current_segment': self.current_segment,
            'total_segments': self.total_segments,
            'passed_segments': sorted(list(self.passed_segments)),
            'segment_scores': self.segment_scores,
            'progress': self.get_progress(),
            'average_score': self.get_average_score(),
        }


def create_initial_state(total_segments: int) -> Dict[str, Any]:
    """Create initial state dict for a new session."""
    return {
        'step': int(ShadowStep.WATCH_NO_TEXT),
        'current_segment': 0,
        'total_segments': total_segments,
        'passed_segments': [],
        'segment_scores': {},
        'progress': 0.0,
        'average_score': 0.0,
    }


def load_state_from_session(session) -> ShadowStateMachine:
    """Load state machine from ShadowSession model instance."""
    # Get passed segments from SegmentAttempt records
    passed = set()
    scores = {}
    for attempt in session.segment_attempts.filter(passed=True).order_by('segment_index', '-attempts'):
        if attempt.segment_index not in passed:
            passed.add(attempt.segment_index)
            scores[attempt.segment_index] = attempt.score

    return ShadowStateMachine({
        'step': session.step,
        'current_segment': session.current_segment,
        'total_segments': len(session.transcript.segments_json) if session.transcript and session.transcript.segments_json else 0,
        'passed_segments': list(passed),
        'segment_scores': scores,
    })