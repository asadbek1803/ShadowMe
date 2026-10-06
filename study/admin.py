from django.contrib import admin
from .models import Course, Lesson, UserStats, AIAnalysisRecord, UserSettings, LessonTranscript, ShadowSession, SegmentAttempt


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ["title", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["title", "description"]


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ["title", "course", "difficulty", "is_premium", "duration_minutes", "created_at"]
    list_filter = ["course", "difficulty", "is_premium"]
    search_fields = ["title", "description"]


@admin.register(UserStats)
class UserStatsAdmin(admin.ModelAdmin):
    list_display = ["user", "total_xp", "current_streak", "highest_streak", "analyzed_videos_count", "last_activity_date"]
    search_fields = ["user__full_name", "user__telegram_id"]


@admin.register(AIAnalysisRecord)
class AIAnalysisRecordAdmin(admin.ModelAdmin):
    list_display = ["user", "lesson", "score_percentage", "created_at"]
    list_filter = ["lesson"]
    search_fields = ["user__full_name"]
    readonly_fields = ["created_at"]


@admin.register(UserSettings)
class UserSettingsAdmin(admin.ModelAdmin):
    list_display = ["user", "theme", "plan", "notifications_enabled", "default_language"]
    list_filter = ["theme", "plan", "notifications_enabled"]


@admin.register(LessonTranscript)
class LessonTranscriptAdmin(admin.ModelAdmin):
    list_display = ["id", "lesson", "source_type", "language", "status", "duration_seconds", "created_at"]
    list_filter = ["source_type", "language", "status"]
    search_fields = ["lesson__title", "source_url"]
    readonly_fields = ["id", "created_at", "updated_at", "segments_json", "words_json"]
    ordering = ["-created_at"]


@admin.register(ShadowSession)
class ShadowSessionAdmin(admin.ModelAdmin):
    list_display = ["user", "lesson", "step", "current_segment", "progress", "score", "status", "started_at"]
    list_filter = ["step", "status"]
    search_fields = ["user__full_name", "lesson__title"]
    readonly_fields = ["started_at", "completed_at"]
    ordering = ["-started_at"]


@admin.register(SegmentAttempt)
class SegmentAttemptAdmin(admin.ModelAdmin):
    list_display = ["session", "segment_index", "attempts", "score", "passed", "created_at"]
    list_filter = ["passed"]
    search_fields = ["session__user__full_name", "session__lesson__title"]
    readonly_fields = ["created_at"]
    ordering = ["-created_at"]