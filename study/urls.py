from django.urls import path
from . import views, views_shadow

app_name = 'study'

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('courses/', views.courses_view, name='courses'),
    path('analysis/', views.analysis_view, name='analysis'),
    path('stats/', views.stats_view, name='stats'),
    path('settings/', views.settings_view, name='settings'),
    path('pricing/', views.pricing_view, name='pricing'),
    path('upgrade/', views.upgrade_plan_view, name='upgrade_plan'),
    path('shadow/', views.shadow_dashboard_view, name='shadow_dashboard'),
    path('shadow/lesson/<int:lesson_id>/', views_shadow.lesson_player_view, name='lesson_player'),

    # Shadowing API endpoints (CSRF exempt for API calls from JS)
    path('api/transcript/', views_shadow.create_transcript_view, name='create_transcript'),
    path('api/active-transcripts/', views_shadow.active_transcripts_view, name='active_transcripts'),
    path('api/transcript/<str:transcript_id>/', views_shadow.get_transcript_status_view, name='get_transcript_status'),
    path('api/session/start/', views_shadow.start_session_view, name='start_session'),
    path('api/session/<str:session_id>/', views_shadow.get_session_view, name='get_session'),
    path('api/session/<str:session_id>/advance/', views_shadow.advance_session_view, name='advance_session'),
    path('api/session/<str:session_id>/segment/', views_shadow.analyze_segment_view, name='analyze_segment'),
    path('api/session/<str:session_id>/progress/', views_shadow.get_session_progress_view, name='get_session_progress'),
    path('api/session/<str:session_id>/complete/', views_shadow.complete_session_view, name='complete_session'),
    path('api/set-language/', views.set_language_view, name='set_language'),
]
