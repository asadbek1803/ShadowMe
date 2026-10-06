"""
study/views_shadow.py — Shadowing API async viewlar.
Uvicorn + ASGI bilan ishlaydi.
Barcha ORM chaqiruvlari sync_to_async orqali o'ralgan.
"""
import json
import uuid
import asyncio
import threading
import logging
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect
from asgiref.sync import sync_to_async

from .models import (
    Lesson, LessonTranscript, ShadowSession,
    SegmentAttempt, AIAnalysisRecord, UserStats, UserSettings
)
from accounts.models import TelegramUser
from .views import _check_auth
from .services.session_machine import (
    ShadowStateMachine, ShadowStep,
    create_initial_state,
)
from .services.analysis import analyze_segment_async
from .services.transcription import run_transcription_for_transcript

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# CSRF exempt wrapper for async API views
# ─────────────────────────────────────────────────────────────────────────────

def csrf_exempt_async(view_func):
    """Async viewlar uchun CSRF exempt decorator."""
    async def wrapper(request, *args, **kwargs):
        request._dont_enforce_csrf_checks = True
        return await view_func(request, *args, **kwargs)
    wrapper.csrf_exempt = True
    return wrapper


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers — barchasi sync_to_async bilan o'ralgan
# ─────────────────────────────────────────────────────────────────────────────

@sync_to_async
def _get_lesson(lesson_id):
    try:
        return Lesson.objects.get(id=lesson_id)
    except Lesson.DoesNotExist:
        return None


@sync_to_async
def _get_transcript(transcript_id):
    try:
        return LessonTranscript.objects.get(id=transcript_id)
    except LessonTranscript.DoesNotExist:
        return None


@sync_to_async
def _get_session(session_id):
    try:
        return ShadowSession.objects.select_related(
            'user', 'lesson', 'transcript'
        ).get(id=session_id)
    except ShadowSession.DoesNotExist:
        return None


@sync_to_async
def _get_lesson_player_data(user, lesson_id, session_id=None):
    """Lesson player sahifasi uchun ma'lumotlar."""
    lesson = Lesson.objects.select_related('course').filter(id=lesson_id).first()
    if not lesson:
        return None

    stats, _ = UserStats.objects.get_or_create(user=user)
    user_settings, _ = UserSettings.objects.get_or_create(user=user)
    transcript = lesson.transcripts.filter(status='ready').first()

    session = None
    if session_id:
        session = ShadowSession.objects.filter(
            id=session_id, user=user, status='active'
        ).select_related('transcript').first()
    else:
        session = ShadowSession.objects.filter(
            user=user, lesson=lesson, status='active'
        ).select_related('transcript').order_by('-started_at').first()

    return {
        'lesson': lesson,
        'stats': stats,
        'settings': user_settings,
        'transcript': transcript,
        'session': session,
    }


@sync_to_async
def _create_transcript_from_url(user, lesson, url, language):
    return LessonTranscript.objects.create(
        user=user,
        lesson=lesson,
        source_type='youtube',
        source_url=url,
        language=language,
        status='pending'
    )


@sync_to_async
def _create_transcript_from_upload(user, lesson, video_file, language):
    return LessonTranscript.objects.create(
        user=user,
        lesson=lesson,
        source_type='upload',
        video_file=video_file,
        language=language,
        status='pending'
    )


@sync_to_async
def _create_transcript_from_url_no_lesson(user, url, language):
    from .models import Course, Lesson
    course, _ = Course.objects.get_or_create(title='Foydalanuvchi videolari', defaults={'description': 'Foydalanuvchilar tomonidan yuklangan videolar'})
    lesson = Lesson.objects.create(course=course, title='Maxsus video (YouTube)', video_url=url)
    return LessonTranscript.objects.create(
        user=user,
        lesson=lesson,
        source_type='youtube',
        source_url=url,
        language=language,
        status='pending'
    )


@sync_to_async
def _create_transcript_from_upload_no_lesson(user, video_file, language):
    from .models import Course, Lesson
    course, _ = Course.objects.get_or_create(title='Foydalanuvchi videolari', defaults={'description': 'Foydalanuvchilar tomonidan yuklangan videolar'})
    lesson = Lesson.objects.create(course=course, title=f'Maxsus video ({video_file.name})')
    return LessonTranscript.objects.create(
        user=user,
        lesson=lesson,
        source_type='upload',
        video_file=video_file,
        language=language,
        status='pending'
    )


@sync_to_async
def _get_or_create_active_session(user, lesson):
    """Faol sessiyani olish yoki yaratish."""
    session, created = ShadowSession.get_active_for(user, lesson)
    return session, created


@sync_to_async
def _get_ready_transcript_for_lesson(lesson):
    return lesson.transcripts.filter(status='ready').first()


@sync_to_async
def _load_state_from_session(session):
    """
    ShadowStateMachine ni DB dan yuklab qaytaradi.
    Bu sync ORM operatsiyalarini o'z ichiga oladi.
    """
    from .services.session_machine import ShadowStateMachine
    passed = set()
    scores = {}
    for attempt in session.segment_attempts.filter(passed=True).order_by('segment_index', '-attempts'):
        if attempt.segment_index not in passed:
            passed.add(attempt.segment_index)
            scores[attempt.segment_index] = attempt.score

    total_segments = (
        len(session.transcript.segments_json)
        if session.transcript and session.transcript.segments_json
        else 0
    )

    return ShadowStateMachine({
        'step': session.step,
        'current_segment': session.current_segment,
        'total_segments': total_segments,
        'passed_segments': list(passed),
        'segment_scores': scores,
    })


@sync_to_async
def _save_session_step(session, step, current_segment=None):
    session.step = step
    if current_segment is not None:
        session.current_segment = current_segment
    session.save(update_fields=['step', 'current_segment'])


@sync_to_async
def _get_attempt_number(session, segment_index):
    last = session.segment_attempts.filter(
        segment_index=segment_index
    ).order_by('-attempts').first()
    return (last.attempts + 1) if last else 1


@sync_to_async
def _save_segment_attempt(session, segment_index, recording_file, analysis_result, attempt_number):
    attempt = SegmentAttempt.objects.create(
        session=session,
        segment_index=segment_index,
        recording=recording_file,
        score=analysis_result["score"],
        phoneme_feedback=analysis_result["word_feedback"],
        passed=analysis_result["passed"],
        attempts=attempt_number
    )
    # Update session progress
    session.recompute_progress()
    return attempt


@sync_to_async
def _update_session_segment(session, segment_index):
    session.current_segment = segment_index
    session.save(update_fields=['current_segment'])


@sync_to_async
def _complete_session(session):
    from django.utils import timezone
    session.status = 'completed'
    session.step = 7  # COMPLETED
    session.completed_at = timezone.now()
    session.save(update_fields=['status', 'step', 'completed_at'])


@sync_to_async
def _create_analysis_record(user, lesson, score):
    return AIAnalysisRecord.objects.create(
        user=user,
        lesson=lesson,
        score_percentage=score,
        feedback_data={}
    )


@sync_to_async
def _update_user_stats(user, score):
    from django.utils import timezone
    stats, _ = UserStats.objects.get_or_create(user=user)
    stats.total_xp += round(score)
    stats.analyzed_videos_count += 1
    stats.last_activity_date = timezone.now().date()
    stats.save(update_fields=['total_xp', 'analyzed_videos_count', 'last_activity_date'])


# ─────────────────────────────────────────────────────────────────────────────
# Page views
# ─────────────────────────────────────────────────────────────────────────────

async def lesson_player_view(request, lesson_id):
    """Shadowing lesson player asosiy sahifasi."""
    user = await _check_auth(request)
    if not user:
        return redirect('accounts:login')

    session_id = request.GET.get('session_id')
    data = await _get_lesson_player_data(user, lesson_id, session_id)
    if not data:
        return redirect('study:shadow_dashboard')

    lesson = data['lesson']
    transcript = data['transcript']
    session = data['session']

    return render(request, 'study/lesson_player.html', {
        'user': user,
        'stats': data['stats'],
        'settings': data['settings'],
        'lesson': lesson,
        'transcript': transcript,
        'session': session,
        'has_transcript': transcript is not None,
        'video_url': lesson.video_url or (transcript.source_url if transcript else ''),
    })


# ─────────────────────────────────────────────────────────────────────────────
# API views
# ─────────────────────────────────────────────────────────────────────────────


def _start_transcription_background(transcript_id: str):
    """
    Transcript ID ni background threadda qayta ishlash.
    Threading ishlatiladi — uvicorn event loop ga bog'liq emas,
    shuning uchun barcha muhitlarda ishlaydi.
    """
    def _run():
        import asyncio
        import django
        django.setup()
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                run_transcription_for_transcript(transcript_id)
            )
            loop.close()
            if result:
                logger.info(f"[Transcription] ✅ Completed: {transcript_id}")
            else:
                logger.error(f"[Transcription] ❌ Failed: {transcript_id}")
        except Exception as e:
            logger.exception(f"[Transcription] Background thread error for {transcript_id}: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    logger.info(f"[Transcription] 🚀 Started background thread for {transcript_id}")


@csrf_exempt_async
async def create_transcript_view(request):
    """
    POST /dashboard/api/transcript/
    Ikki rejim:
      1) JSON body:  { youtube_url, language?, lesson_id? }
      2) Multipart:  video_file + language + lesson_id? (form-data)
    Transcript yaratilgandan keyin DARHOL background threadda qayta ishlash boshlanadi.
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    user = await _check_auth(request)
    if not user:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    content_type = request.content_type or ""

    def validate_language(lang):
        # Agar user til tanlagan bo'lsa, va u tanlangan til videoniki bilan mos kelmasa, error beramiz
        if user.study_lang and user.study_lang != lang:
            return False
        return True

    # ── Multipart (file upload) ───────────────────────────────────────────────
    if "multipart/form-data" in content_type:
        lesson_id = request.POST.get("lesson_id")
        language  = request.POST.get("language", "en")

        if not validate_language(language):
            return JsonResponse({"error": f"Kechirasiz, siz {user.study_lang} tilini o'rganishni tanlagansiz. Iltimos o'zingizning profilingizdagi tildagi videoni yuklang."}, status=400)

        lesson = None
        if lesson_id:
            lesson = await _get_lesson(lesson_id)
            if not lesson:
                return JsonResponse({"error": "Lesson topilmadi"}, status=404)

        video_file = request.FILES.get("video_file")
        if not video_file:
            return JsonResponse({"error": "video_file kerak"}, status=400)

        if lesson:
            transcript = await _create_transcript_from_upload(user, lesson, video_file, language)
        else:
            transcript = await _create_transcript_from_upload_no_lesson(user, video_file, language)

        # Background da darhol ishga tushir
        _start_transcription_background(str(transcript.id))

        return JsonResponse({
            "transcript_id": str(transcript.id),
            "status": "processing",
            "message": "Video yuklandi, transkriptsiya boshlanmoqda..."
        })

    # ── JSON body (YouTube URL yoki boshqa) ───────────────────────────────────
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError, Exception):
        return JsonResponse({"error": "JSON yoki multipart/form-data formatida jo'nating"}, status=400)

    lesson_id   = body.get("lesson_id")
    language    = body.get("language", "en")
    youtube_url = body.get("youtube_url", "").strip()

    if not validate_language(language):
        return JsonResponse({"error": f"Kechirasiz, siz {user.study_lang} tilini o'rganishni tanlagansiz. Iltimos o'zingizning profilingizdagi tildagi videoni yuklang."}, status=400)

    lesson = None
    if lesson_id:
        lesson = await _get_lesson(lesson_id)
        if not lesson:
            return JsonResponse({"error": "Lesson topilmadi"}, status=404)

    if not youtube_url:
        return JsonResponse({"error": "youtube_url yoki video_file (multipart) kerak"}, status=400)

    # YouTube URL validatsiya
    if "youtube.com" not in youtube_url and "youtu.be" not in youtube_url:
        return JsonResponse({"error": "Faqat YouTube havolalari qabul qilinadi"}, status=400)

    if lesson:
        transcript = await _create_transcript_from_url(user, lesson, youtube_url, language)
    else:
        transcript = await _create_transcript_from_url_no_lesson(user, youtube_url, language)

    # Background da darhol ishga tushir
    _start_transcription_background(str(transcript.id))

    return JsonResponse({
        "transcript_id": str(transcript.id),
        "status": "processing",
        "message": "YouTube video yuklab olinmoqda va transkriptsiya boshlanmoqda..."
    })


async def get_transcript_status_view(request, transcript_id):
    """GET /dashboard/api/transcript/<id>/"""
    if request.method != "GET":
        return HttpResponseBadRequest("GET required")

    user = await _check_auth(request)
    if not user:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        uuid.UUID(transcript_id)
    except ValueError:
        return JsonResponse({"error": "Noto'g'ri transcript_id"}, status=400)

    transcript = await _get_transcript(transcript_id)
    if not transcript:
        return JsonResponse({"error": "Transcript topilmadi"}, status=404)

    response = {
        "transcript_id": str(transcript.id),
        "status": transcript.status,
        "language": transcript.language,
        "source_type": transcript.source_type,
        "duration_seconds": transcript.duration_seconds,
    }

    if transcript.status == 'ready':
        response.update({
            "segments_json": transcript.segments_json,
            "words_json": transcript.words_json,
        })
    elif transcript.status == 'failed':
        response["error_message"] = transcript.error_message

    return JsonResponse(response)


async def start_session_view(request):
    """
    POST /dashboard/api/session/start/
    Body: {lesson_id}
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    user = await _check_auth(request)
    if not user:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        data = json.loads(request.body)
        lesson_id = data.get("lesson_id")
    except (json.JSONDecodeError, AttributeError):
        lesson_id = request.POST.get("lesson_id")

    if not lesson_id:
        return JsonResponse({"error": "lesson_id kerak"}, status=400)

    lesson = await _get_lesson(lesson_id)
    if not lesson:
        return JsonResponse({"error": "Dars topilmadi"}, status=404)

    session, created = await _get_or_create_active_session(user, lesson)

    # Transcript tekshirish
    transcript = None
    if session.transcript and session.transcript.status == 'ready':
        transcript = session.transcript
    if not transcript:
        transcript = await _get_ready_transcript_for_lesson(lesson)

    if not transcript:
        return JsonResponse({
            "error": "Transcript tayyor emas. Avval transcript yarating.",
            "session_id": str(session.id),
            "transcript_status": session.transcript.status if session.transcript else "none"
        }, status=409)

    state = await _load_state_from_session(session)

    return JsonResponse({
        "session_id": str(session.id),
        "created": created,
        "step": int(state.step),
        "step_name": state.get_current_state().name,
        "step_description": state.get_current_state().description,
        "current_segment": state.current_segment,
        "total_segments": state.total_segments,
        "progress": state.get_progress(),
        "average_score": state.get_average_score(),
        "segments": transcript.segments_json,
        "words": transcript.words_json,
        "transcript_language": transcript.language,
        "valid_next_steps": [int(s) for s in state.get_valid_next_steps()],
    })


async def get_session_view(request, session_id):
    """GET /dashboard/api/session/<id>/"""
    if request.method != "GET":
        return HttpResponseBadRequest("GET required")

    user = await _check_auth(request)
    if not user:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        int(session_id)
    except ValueError:
        return JsonResponse({"error": "Noto'g'ri session_id"}, status=400)

    session = await _get_session(session_id)
    if not session:
        return JsonResponse({"error": "Sessiya topilmadi"}, status=404)

    state = await _load_state_from_session(session)
    transcript = session.transcript

    return JsonResponse({
        "session_id": str(session.id),
        "step": int(state.step),
        "step_name": state.get_current_state().name,
        "step_description": state.get_current_state().description,
        "current_segment": state.current_segment,
        "total_segments": state.total_segments,
        "progress": state.get_progress(),
        "average_score": state.get_average_score(),
        "passed_segments": sorted(list(state.passed_segments)),
        "failed_segments": state.get_failed_segments(),
        "is_completed": state.is_completed(),
        "segments": transcript.segments_json if transcript else None,
        "words": transcript.words_json if transcript else None,
        "transcript_language": transcript.language if transcript else "en",
        "valid_next_steps": [int(s) for s in state.get_valid_next_steps()],
    })


@csrf_exempt_async
async def advance_session_view(request, session_id):
    """POST /dashboard/api/session/<id>/advance/  Body: {step: int}"""
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    user = await _check_auth(request)
    if not user:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        int(session_id)
    except ValueError:
        return JsonResponse({"error": "Noto'g'ri session_id"}, status=400)

    session = await _get_session(session_id)
    if not session:
        return JsonResponse({"error": "Sessiya topilmadi"}, status=404)

    try:
        data = json.loads(request.body)
        target_step = data.get("step")
    except (json.JSONDecodeError, AttributeError):
        target_step = request.POST.get("step")

    try:
        target_step = ShadowStep(int(target_step))
    except (ValueError, TypeError):
        return JsonResponse({"error": "Noto'g'ri step qiymati"}, status=400)

    state = await _load_state_from_session(session)

    if not state.advance(target_step):
        return JsonResponse({
            "error": f"{int(state.step)}-stepdan {int(target_step)}-stepga o'tib bo'lmaydi",
            "current_step": int(state.step),
            "valid_next_steps": [int(s) for s in state.get_valid_next_steps()]
        }, status=400)

    await _save_session_step(session, int(target_step), state.current_segment)

    return JsonResponse({
        "session_id": str(session.id),
        "step": int(target_step),
        "step_name": state.get_current_state().name,
        "step_description": state.get_current_state().description,
        "message": "Step muvaffaqiyatli o'zgartirildi"
    })


@csrf_exempt_async
async def analyze_segment_view(request, session_id):
    """POST /dashboard/api/session/<id>/segment/  Multipart: segment_index + recording"""
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    user = await _check_auth(request)
    if not user:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        int(session_id)
    except ValueError:
        return JsonResponse({"error": "Noto'g'ri session_id"}, status=400)

    session = await _get_session(session_id)
    if not session:
        return JsonResponse({"error": "Sessiya topilmadi"}, status=404)

    segment_index = request.POST.get("segment_index")
    recording = request.FILES.get("recording")

    if segment_index is None or not recording:
        return JsonResponse({"error": "segment_index va recording kerak"}, status=400)

    try:
        segment_index = int(segment_index)
    except ValueError:
        return JsonResponse({"error": "Noto'g'ri segment_index"}, status=400)

    transcript = session.transcript
    if not transcript or not transcript.segments_json:
        return JsonResponse({"error": "Transcript segmentlari mavjud emas"}, status=400)

    segments = transcript.segments_json
    if segment_index < 0 or segment_index >= len(segments):
        return JsonResponse({"error": "Segment indeksi chegaradan tashqari"}, status=400)

    reference_segment = segments[segment_index]
    attempt_number = await _get_attempt_number(session, segment_index)

    try:
        analysis_result = await analyze_segment_async(
            recording, reference_segment, transcript.language
        )
    except Exception as e:
        return JsonResponse({"error": f"Tahlil muvaffaqiyatsiz: {str(e)}"}, status=500)

    if not analysis_result:
        return JsonResponse({"error": "Tahlil natijasi qaytmadi"}, status=500)

    await _save_segment_attempt(session, segment_index, recording, analysis_result, attempt_number)

    if analysis_result["passed"]:
        await _update_session_segment(session, segment_index)

    return JsonResponse({
        "session_id": str(session.id),
        "segment_index": segment_index,
        "attempt_number": attempt_number,
        "score": analysis_result["score"],
        "passed": analysis_result["passed"],
        "accuracy": analysis_result["accuracy"],
        "fluency": analysis_result["fluency"],
        "word_feedback": analysis_result["word_feedback"],
        "user_transcript": analysis_result["user_transcript"],
        "total_words": analysis_result["total_words"],
        "correct_words": analysis_result["correct_words"],
    })


async def get_session_progress_view(request, session_id):
    """GET /dashboard/api/session/<id>/progress/"""
    if request.method != "GET":
        return HttpResponseBadRequest("GET required")

    user = await _check_auth(request)
    if not user:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        int(session_id)
    except ValueError:
        return JsonResponse({"error": "Noto'g'ri session_id"}, status=400)

    session = await _get_session(session_id)
    if not session:
        return JsonResponse({"error": "Sessiya topilmadi"}, status=404)

    state = await _load_state_from_session(session)

    return JsonResponse({
        "session_id": str(session.id),
        "progress": state.get_progress(),
        "average_score": state.get_average_score(),
        "passed_segments": sorted(list(state.passed_segments)),
        "failed_segments": state.get_failed_segments(),
        "is_completed": state.is_completed(),
        "current_step": int(state.step),
    })


@csrf_exempt_async
async def complete_session_view(request, session_id):
    """POST /dashboard/api/session/<id>/complete/"""
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    user = await _check_auth(request)
    if not user:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        int(session_id)
    except ValueError:
        return JsonResponse({"error": "Noto'g'ri session_id"}, status=400)

    session = await _get_session(session_id)
    if not session:
        return JsonResponse({"error": "Sessiya topilmadi"}, status=404)

    state = await _load_state_from_session(session)

    if not state.is_completed():
        return JsonResponse({
            "error": "Sessiya to'liq tugallanmagan. Ba'zi segmentlar o'tilmagan.",
            "progress": state.get_progress(),
            "failed_segments": state.get_failed_segments()
        }, status=400)

    await _complete_session(session)

    avg_score = state.get_average_score()
    await _create_analysis_record(user, session.lesson, avg_score)
    await _update_user_stats(user, avg_score)

    return JsonResponse({
        "session_id": str(session.id),
        "status": "completed",
        "average_score": avg_score,
        "progress": 100.0,
        "message": "Tabriklaymiz! Dars 100% tugallandi! 🎉"
    })


async def active_transcripts_view(request):
    """GET /dashboard/api/active-transcripts/"""
    if request.method != "GET":
        return HttpResponseBadRequest("GET required")

    user = await _check_auth(request)
    if not user:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    from asgiref.sync import sync_to_async
    @sync_to_async
    def get_transcripts():
        transcripts = LessonTranscript.objects.filter(user=user).order_by('-created_at')[:5]
        active = []
        for t in transcripts:
            active.append({
                "id": str(t.id),
                "title": t.lesson.title if t.lesson else "Maxsus video",
                "status": t.status,
                "lesson_id": str(t.lesson.id) if t.lesson else None
            })
        return active
    
    data = await get_transcripts()
    return JsonResponse({"transcripts": data})
