from django.db import models
from accounts.models import TelegramUser
from django.utils import timezone
import uuid


class Course(models.Model):
    """Platformadagi til kurslari (Masalan: Koreys tili, Ingliz tili)."""
    title = models.CharField(max_length=100, verbose_name="Kurs nomi")
    description = models.TextField(blank=True, null=True, verbose_name="Ta'rifi")
    image_url = models.URLField(blank=True, null=True, verbose_name="Kurs rasmi URL")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Kurs"
        verbose_name_plural = "Kurslar"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Lesson(models.Model):
    """Bitta dars yoki video material."""
    DIFFICULTY_CHOICES = (
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    )

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lessons", verbose_name="Kurs")
    title = models.CharField(max_length=200, verbose_name="Dars sarlavhasi")
    video_url = models.URLField(blank=True, null=True, verbose_name="YouTube yoki Video URL")
    thumbnail_url = models.URLField(blank=True, null=True, verbose_name="Rasm URL")
    duration_minutes = models.PositiveIntegerField(default=0, verbose_name="Davomiyligi (daqiqa)")
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default='beginner')
    is_premium = models.BooleanField(default=False, verbose_name="Premium (Gold/VIP) darsmi?")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Dars"
        verbose_name_plural = "Darslar"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.course.title})"


class UserStats(models.Model):
    """Foydalanuvchining umumiy statistikasi."""
    user = models.OneToOneField(TelegramUser, on_delete=models.CASCADE, related_name="stats", verbose_name="Foydalanuvchi")
    total_xp = models.PositiveIntegerField(default=0, verbose_name="Jami XP")
    current_streak = models.PositiveIntegerField(default=0, verbose_name="Joriy streak (kunlar)")
    highest_streak = models.PositiveIntegerField(default=0, verbose_name="Eng yuqori streak")
    analyzed_videos_count = models.PositiveIntegerField(default=0, verbose_name="Tahlil qilingan videolar soni")
    last_activity_date = models.DateField(default=timezone.now, verbose_name="Oxirgi faollik sanasi")

    class Meta:
        verbose_name = "Foydalanuvchi statistikasi"
        verbose_name_plural = "Foydalanuvchilar statistikasi"

    def __str__(self):
        return f"{self.user.full_name} Stats"


class AIAnalysisRecord(models.Model):
    """Foydalanuvchi qilib ko'rgan har bir Shadow tahlili."""
    user = models.ForeignKey(TelegramUser, on_delete=models.CASCADE, related_name="analyses")
    lesson = models.ForeignKey(Lesson, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Tegishli dars")
    custom_video_url = models.URLField(blank=True, null=True, verbose_name="Custom video URL (agar tayyor dars bo'lmasa)")
    
    score_percentage = models.FloatField(default=0.0, verbose_name="Umumiy o'rtacha ball (%)")
    feedback_data = models.JSONField(blank=True, null=True, verbose_name="AI tahlil xulosasi (JSON)")
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "AI Tahlil sessiyasi"
        verbose_name_plural = "AI Tahlil sessiyalari"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.full_name} - {self.score_percentage}%"


class UserSettings(models.Model):
    """Foydalanuvchi shaxsiy sozlamalari."""
    user = models.OneToOneField(TelegramUser, on_delete=models.CASCADE, related_name="settings")
    theme = models.CharField(max_length=20, default='dark', choices=(('dark', 'Dark'), ('light', 'Light')))
    notifications_enabled = models.BooleanField(default=True)
    default_language = models.CharField(max_length=10, default='uz')
    
    PLAN_CHOICES = (
        ('free', 'Free'),
        ('gold', 'Gold'),
        ('vip', 'VIP'),
    )
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='free', verbose_name="Ta'rif rejasi")

    class Meta:
        verbose_name = "Foydalanuvchi sozlamasi"
        verbose_name_plural = "Foydalanuvchilar sozlamalari"

    def __str__(self):
        return f"{self.user.full_name} Sozlamalari"


class LessonTranscript(models.Model):
    """Video transkripsiyasi (WhisperX natijalari)."""
    STATUS_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('processing', 'Jarayonda'),
        ('ready', 'Tayyor'),
        ('failed', 'Xato'),
    )
    SOURCE_CHOICES = (
        ('youtube', 'YouTube'),
        ('upload', 'Yuklash'),
        ('premade', 'Tayyor dars'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        TelegramUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transcripts',
        verbose_name="Foydalanuvchi"
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name="transcripts",
        null=True,
        blank=True,
        verbose_name="Dars"
    )
    language = models.CharField(max_length=10, default='en', verbose_name="Til")
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='youtube', verbose_name="Manba turi")
    source_url = models.URLField(blank=True, null=True, verbose_name="Manba URL (YouTube)")
    video_file = models.FileField(upload_to='transcripts/video/', blank=True, null=True, verbose_name="Video fayl")
    audio_file = models.FileField(upload_to='transcripts/audio/', blank=True, null=True, verbose_name="Audio fayl")
    segments_json = models.JSONField(blank=True, null=True, verbose_name="Segmentlar JSON")
    words_json = models.JSONField(blank=True, null=True, verbose_name="So'zlar JSON (karaoke)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Holati")
    error_message = models.TextField(blank=True, null=True, verbose_name="Xato xabari")
    duration_seconds = models.FloatField(default=0, verbose_name="Davomiyligi (soniya)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Yangilangan")

    class Meta:
        verbose_name = "Dars transkriptsiyasi"
        verbose_name_plural = "Dars transkriptsiyalari"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Transcript {self.id} ({self.status})"


class ShadowSession(models.Model):
    """Shadowing dars sessiyasi (6-bosqichli)."""
    STATUS_CHOICES = (
        ('active', 'Faol'),
        ('completed', 'Tugallangan'),
        ('abandoned', 'Tashlab yuborilgan'),
    )
    STEP_CHOICES = (
        (1, 'Watch (No Text)'),
        (2, 'Watch (With Text)'),
        (3, 'Practice Segments'),
        (4, 'AI Analysis'),
        (5, 'Feedback'),
        (6, 'Replay Errors'),
        (7, 'Completed'),
    )

    user = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name="shadow_sessions",
        verbose_name="Foydalanuvchi"
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name="shadow_sessions",
        verbose_name="Dars"
    )
    transcript = models.ForeignKey(
        LessonTranscript,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shadow_sessions",
        verbose_name="Transkript"
    )
    step = models.IntegerField(choices=STEP_CHOICES, default=1, verbose_name="Bosqich")
    current_segment = models.IntegerField(default=0, verbose_name="Joriy segment")
    progress = models.FloatField(default=0, verbose_name="Progress (%)")
    score = models.FloatField(default=0, verbose_name="O'rtacha ball")
    attempts_count = models.IntegerField(default=0, verbose_name="Urinishlar soni")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', verbose_name="Holati")
    started_at = models.DateTimeField(auto_now_add=True, verbose_name="Boshlangan")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Tugallangan")

    class Meta:
        verbose_name = "Shadow sessiyasi"
        verbose_name_plural = "Shadow sessiyalari"
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.user.full_name} - {self.lesson.title} (Step {self.step})"

    @classmethod
    def get_active_for(cls, user, lesson):
        """Foydalanuvchi va dars uchun faol sessiyani olish yoki yaratish."""
        session, created = cls.objects.get_or_create(
            user=user,
            lesson=lesson,
            status='active',
            defaults={'transcript': lesson.transcripts.filter(status='ready').first()}
        )
        return session, created

    def recompute_progress(self):
        """Progress va score ni qayta hisoblash."""
        total = self.transcript.segments_json.__len__() if self.transcript and self.transcript.segments_json else 0
        if total == 0:
            self.progress = 0
            self.score = 0
            return
        passed_attempts = self.segment_attempts.filter(passed=True)
        passed_count = passed_attempts.values('segment_index').distinct().count()
        self.progress = (passed_count / total) * 100
        if passed_count > 0:
            self.score = passed_attempts.order_by('segment_index').last().score if passed_attempts.exists() else 0
        self.save(update_fields=['progress', 'score'])

    def advance_step(self, new_step):
        """Bosqichni o'tkazish validatsiyasi bilan."""
        valid_transitions = {
            1: [2],
            2: [3],
            3: [3, 4, 5],  # can stay, go to analysis, or feedback
            4: [5],
            5: [3, 6, 7],  # if failed segments -> 6, else -> completed
            6: [3],        # back to practice
            7: [],         # completed - no further transitions
        }
        if new_step in valid_transitions.get(self.step, []):
            self.step = new_step
            self.save(update_fields=['step'])
            return True
        return False


class SegmentAttempt(models.Model):
    """Har bir segment uchun urinish tarixi."""
    session = models.ForeignKey(
        ShadowSession,
        on_delete=models.CASCADE,
        related_name="segment_attempts",
        verbose_name="Sessiya"
    )
    segment_index = models.IntegerField(verbose_name="Segment indeksi")
    recording = models.FileField(upload_to='recordings/', blank=True, null=True, verbose_name="Yozuv")
    score = models.FloatField(default=0, verbose_name="Ball")
    phoneme_feedback = models.JSONField(blank=True, null=True, verbose_name="Fonema feedback")
    passed = models.BooleanField(default=False, verbose_name="O'tdi")
    attempts = models.IntegerField(default=1, verbose_name="Urinish raqami")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan")

    class Meta:
        verbose_name = "Segment urinishi"
        verbose_name_plural = "Segment urinishlari"
        ordering = ["segment_index", "attempts"]
        unique_together = ['session', 'segment_index', 'attempts']

    def __str__(self):
        return f"Segment {self.segment_index} - Attempt {self.attempts} ({'Passed' if self.passed else 'Failed'})"
