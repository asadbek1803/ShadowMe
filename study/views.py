"""
study/views.py — To'liq async viewlar.
Uvicorn + ASGI bilan ishlaydi.
Barcha ORM chaqiruvlari sync_to_async orqali o'ralgan.
"""
from django.shortcuts import render, redirect
from django.db.models import Q, Count
from asgiref.sync import sync_to_async

from .models import Course, Lesson, UserStats, AIAnalysisRecord, UserSettings, ShadowSession
from accounts.models import TelegramUser


# ─────────────────────────────────────────────────────────────────────────────
# Auth helper
# ─────────────────────────────────────────────────────────────────────────────

@sync_to_async
def _check_auth(request):
    """Session'dan user_id olib TelegramUser qaytaradi."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    try:
        return TelegramUser.objects.get(id=user_id)
    except TelegramUser.DoesNotExist:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# DB helper wrappers
# ─────────────────────────────────────────────────────────────────────────────

@sync_to_async
def _get_dashboard_data(user):
    stats, _ = UserStats.objects.get_or_create(user=user)
    user_settings, _ = UserSettings.objects.get_or_create(user=user)
    if hasattr(Lesson, 'is_active'):
        lessons = list(Lesson.objects.select_related("course").filter(is_active=True))
    else:
        lessons = list(Lesson.objects.select_related("course").all()[:3])
    active_session = (
        ShadowSession.objects
        .select_related('lesson', 'lesson__course')
        .filter(user=user, status='active')
        .order_by('-started_at')
        .first()
    )
    return stats, user_settings, lessons, active_session


@sync_to_async
def _get_courses_data(user):
    stats, _ = UserStats.objects.get_or_create(user=user)
    user_settings, _ = UserSettings.objects.get_or_create(user=user)
    # annotate — lesson_count ni DB da hisoblaydi, templateda .count() kerak emas
    courses = list(
        Course.objects.filter(is_active=True)
        .annotate(lesson_count=Count('lessons'))
    )
    return stats, user_settings, courses


@sync_to_async
def _get_analysis_data(user):
    from .models import LessonTranscript
    stats, _ = UserStats.objects.get_or_create(user=user)
    user_settings, _ = UserSettings.objects.get_or_create(user=user)
    records = list(LessonTranscript.objects.select_related('lesson').filter(user=user).order_by('-created_at')[:10])
    shadow_sessions = list(
        ShadowSession.objects
        .select_related('lesson')
        .filter(user=user, status='completed')
        .order_by('-completed_at')[:10]
    )
    return stats, user_settings, records, shadow_sessions


@sync_to_async
def _get_user_data(user):
    stats, _ = UserStats.objects.get_or_create(user=user)
    user_settings, _ = UserSettings.objects.get_or_create(user=user)
    return stats, user_settings


@sync_to_async
def _save_settings(settings_obj, theme, default_language, notifications):
    settings_obj.theme = theme
    settings_obj.default_language = default_language
    settings_obj.notifications_enabled = notifications
    settings_obj.save()


@sync_to_async
def _update_user_plan(user, plan):
    _, user_settings = UserSettings.objects.get_or_create(user=user)
    user_settings.plan = plan
    user_settings.save(update_fields=['plan'])


@sync_to_async
def _get_shadow_dashboard_data(user):
    stats, _ = UserStats.objects.get_or_create(user=user)
    user_settings, _ = UserSettings.objects.get_or_create(user=user)
    active_sessions = list(
        ShadowSession.objects
        .select_related('lesson', 'lesson__course', 'transcript')
        .filter(user=user, status='active')
        .order_by('-started_at')[:5]
    )
    completed_sessions = list(
        ShadowSession.objects
        .select_related('lesson', 'lesson__course')
        .filter(user=user, status='completed')
        .order_by('-completed_at')[:10]
    )
    ready_lessons = list(
        Lesson.objects
        .select_related('course')
        .filter(transcripts__status='ready')
        .distinct()[:10]
    )
    return stats, user_settings, active_sessions, completed_sessions, ready_lessons


# ─────────────────────────────────────────────────────────────────────────────
# Async views
# ─────────────────────────────────────────────────────────────────────────────

async def dashboard_view(request):
    user = await _check_auth(request)
    if not user:
        return redirect('accounts:login')

    stats, user_settings, recommended_lessons, active_session = await _get_dashboard_data(user)

    return render(request, 'study/dashboard.html', {
        'user': user,
        'stats': stats,
        'settings': user_settings,
        'recommended_lessons': recommended_lessons,
        'active_shadow_session': active_session,
    })


async def courses_view(request):
    user = await _check_auth(request)
    if not user:
        return redirect('accounts:login')

    stats, user_settings, courses = await _get_courses_data(user)

    return render(request, 'study/courses.html', {
        'user': user,
        'stats': stats,
        'settings': user_settings,
        'courses': courses,
    })


async def analysis_view(request):
    user = await _check_auth(request)
    if not user:
        return redirect('accounts:login')

    stats, user_settings, records, shadow_sessions = await _get_analysis_data(user)

    return render(request, 'study/analysis.html', {
        'user': user,
        'study_lang': user.study_lang,
        'stats': stats,
        'settings': user_settings,
        'analysis_records': records,
        'shadow_sessions': shadow_sessions,
    })


async def stats_view(request):
    user = await _check_auth(request)
    if not user:
        return redirect('accounts:login')

    stats, user_settings = await _get_user_data(user)

    return render(request, 'study/stats.html', {
        'user': user,
        'stats': stats,
        'settings': user_settings,
    })


async def settings_view(request):
    user = await _check_auth(request)
    if not user:
        return redirect('accounts:login')

    stats, user_settings = await _get_user_data(user)

    if request.method == "POST":
        theme = request.POST.get('theme', 'dark')
        default_language = request.POST.get('default_language', 'uz')
        notifications = request.POST.get('notifications') == 'on'
        await _save_settings(user_settings, theme, default_language, notifications)
        return redirect('study:settings')

    return render(request, 'study/settings.html', {
        'user': user,
        'stats': stats,
        'settings': user_settings,
    })


async def pricing_view(request):
    user = await _check_auth(request)
    if not user:
        return redirect('accounts:login')

    stats, user_settings = await _get_user_data(user)

    return render(request, 'study/pricing.html', {
        'user': user,
        'stats': stats,
        'settings': user_settings,
    })


async def upgrade_plan_view(request):
    if request.method != "POST":
        return redirect('study:pricing')

    user = await _check_auth(request)
    if not user:
        return redirect('accounts:login')

    plan = request.POST.get('plan')
    if plan in ('free', 'gold', 'vip'):
        await _update_user_plan(user, plan)

    return redirect('study:dashboard')


async def shadow_dashboard_view(request):
    user = await _check_auth(request)
    if not user:
        return redirect('accounts:login')

    stats, user_settings, active_sessions, completed_sessions, ready_lessons = \
        await _get_shadow_dashboard_data(user)

    return render(request, 'study/shadow_dashboard.html', {
        'user': user,
        'stats': stats,
        'settings': user_settings,
        'active_sessions': active_sessions,
        'completed_sessions': completed_sessions,
        'ready_lessons': ready_lessons,
    })

def csrf_exempt_async(view_func):
    """Async viewlar uchun maxsus csrf_exempt"""
    async def wrapper(request, *args, **kwargs):
        request._dont_enforce_csrf_checks = True
        return await view_func(request, *args, **kwargs)
    wrapper.csrf_exempt = True
    return wrapper

@csrf_exempt_async
async def set_language_view(request):
    import json
    from django.http import JsonResponse
    from asgiref.sync import sync_to_async

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    user = await _check_auth(request)
    if not user:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        data = json.loads(request.body)
        lang = data.get("language")
        
        if lang not in ["en", "ko"]:
            return JsonResponse({"error": "Noma'lum til"}, status=400)

        @sync_to_async
        def _save_lang():
            user.study_lang = lang
            user.save(update_fields=['study_lang'])

        await _save_lang()
        return JsonResponse({"status": "success", "language": lang})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
