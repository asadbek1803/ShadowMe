"""
Segment-level AI Analysis for Shadowing.
Compares user recording with reference segment using WhisperX ASR + alignment.
"""
import os
import tempfile
import logging
from typing import Dict, List, Optional, Any

from django.conf import settings
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


def analyze_segment_audio(
    recording_path: str,
    reference_segment: Dict,
    language: str = 'en'
) -> Optional[Dict]:
    """
    Analyze user recording against reference segment using SpeechRecognition.
    """
    import speech_recognition as sr
    import difflib
    import subprocess
    
    try:
        # Convert webm/ogg/mp4 to wav for SpeechRecognition
        wav_path = recording_path + ".wav"
        subprocess.run(["ffmpeg", "-y", "-i", recording_path, "-vn", "-ar", "16000", "-ac", "1", wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            
        try:
            # Map our language codes to Google Speech API format (e.g., 'en' -> 'en-US', 'ko' -> 'ko-KR')
            lang_code = 'en-US' if language.startswith('en') else ('ko-KR' if language.startswith('ko') else language)
            user_text = recognizer.recognize_google(audio_data, language=lang_code)
        except sr.UnknownValueError:
            user_text = ""
        except sr.RequestError as e:
            logger.error(f"Could not request results from Google Speech Recognition service; {e}")
            user_text = ""
            
        # Clean up temporary wav file
        try:
            if os.path.exists(wav_path):
                os.remove(wav_path)
        except:
            pass

        ref_text = reference_segment.get("text", "").strip()
        ref_words = reference_segment.get("words", [])
        
        # Compare strings using SequenceMatcher
        def normalize(text):
            import re
            return re.sub(r'[^\w\s]', '', text.lower()).strip()
            
        norm_ref = normalize(ref_text)
        norm_user = normalize(user_text)
        
        matcher = difflib.SequenceMatcher(None, norm_ref.split(), norm_user.split())
        accuracy = matcher.ratio() * 100
        
        # Word level feedback estimation
        phoneme_feedback = []
        correct_count = 0
        total_words = len(ref_words)
        
        if total_words == 0:
            # Fallback if no words array is available
            ref_words_list = norm_ref.split()
            total_words = len(ref_words_list)
            for w in ref_words_list:
                ref_words.append({"word": w, "start": 0, "end": 0})
        
        user_words_list = norm_user.split()
        
        # Opcodes: 'replace', 'delete', 'insert', 'equal'
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                for i in range(i1, i2):
                    if i < len(ref_words):
                        word_data = ref_words[i]
                        correct_count += 1
                        phoneme_feedback.append({
                            "word": word_data.get("word", ""),
                            "status": "correct",
                            "expected": word_data.get("word", ""),
                            "detected": user_words_list[j1 + (i - i1)] if (j1 + (i - i1)) < len(user_words_list) else "",
                            "confidence": 0.99,
                            "timing_diff": 0,
                            "phoneme_errors": []
                        })
            else:
                for i in range(i1, i2):
                    if i < len(ref_words):
                        word_data = ref_words[i]
                        phoneme_feedback.append({
                            "word": word_data.get("word", ""),
                            "status": "mispronounced" if tag == 'replace' else "omitted",
                            "expected": word_data.get("word", ""),
                            "detected": user_words_list[j1] if tag == 'replace' and j1 < len(user_words_list) else "",
                            "confidence": 0.4 if tag == 'replace' else 0,
                            "timing_diff": 0,
                            "phoneme_errors": []
                        })

        fluency = accuracy if len(norm_user) > 0 else 0
        final_score = round(0.7 * accuracy + 0.3 * fluency, 1)
        passed = final_score >= getattr(settings, 'SHADOW_SEGMENT_PASS_THRESHOLD', 70)

        return {
            "score": final_score,
            "accuracy": round(accuracy, 1),
            "fluency": round(fluency, 1),
            "passed": passed,
            "word_feedback": phoneme_feedback,
            "user_transcript": user_text,
            "total_words": total_words,
            "correct_words": correct_count
        }
    except Exception as e:
        logger.exception("Segment analysis failed")
        return None


async def analyze_segment_async(
    recording_file,
    reference_segment: Dict,
    language: str = 'en'
) -> Optional[Dict]:
    """
    Async wrapper for segment analysis.
    recording_file: Django UploadedFile or path
    """
    # Save recording to temp file if needed
    if hasattr(recording_file, 'temporary_file_path'):
        recording_path = recording_file.temporary_file_path()
    elif hasattr(recording_file, 'path'):
        recording_path = recording_file.path
    else:
        # Save uploaded file to temp
        with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as tmp:
            for chunk in recording_file.chunks():
                tmp.write(chunk)
            recording_path = tmp.name

    try:
        # Run analysis in thread pool (CPU-bound)
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            analyze_segment_audio,
            recording_path,
            reference_segment,
            language
        )
        return result
    finally:
        # Cleanup temp file if we created it
        if not hasattr(recording_file, 'temporary_file_path') and not hasattr(recording_file, 'path'):
            try:
                os.unlink(recording_path)
            except:
                pass


def create_segment_attempt(
    session,
    segment_index: int,
    recording_file,
    analysis_result: Dict,
    attempt_number: int
):
    """Create SegmentAttempt record from analysis result."""
    from study.models import SegmentAttempt

    attempt = SegmentAttempt.objects.create(
        session=session,
        segment_index=segment_index,
        recording=recording_file,
        score=analysis_result["score"],
        phoneme_feedback=analysis_result["word_feedback"],
        passed=analysis_result["passed"],
        attempts=attempt_number
    )
    return attempt