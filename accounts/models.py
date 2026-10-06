from django.db import models
from django.utils import timezone
import random
import string


class TelegramUser(models.Model):
    """Telegram bot orqali ro'yxatdan o'tgan foydalanuvchi."""
    telegram_id = models.BigIntegerField(unique=True, verbose_name="Telegram ID")
    full_name = models.CharField(max_length=255, verbose_name="To'liq ism")
    username = models.CharField(max_length=100, blank=True, null=True, verbose_name="Telegram username")
    phone_number = models.CharField(max_length=20, blank=True, null=True, verbose_name="Telefon raqami")
    profile_image_url = models.URLField(blank=True, null=True, verbose_name="Profil rasmi URL")
    study_lang = models.CharField(max_length=10, blank=True, null=True, verbose_name="O'rganilayotgan til")
    is_active = models.BooleanField(default=True, verbose_name="Faol")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Ro'yxatdan o'tgan vaqt")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Yangilangan vaqt")

    class Meta:
        verbose_name = "Telegram foydalanuvchi"
        verbose_name_plural = "Telegram foydalanuvchilar"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name} ({self.telegram_id})"

    def can_request_otp(self):
        """1 daqiqada 1 marta OTP so'rash mumkin."""
        one_minute_ago = timezone.now() - timezone.timedelta(minutes=1)
        recent_otp = self.otp_codes.filter(created_at__gte=one_minute_ago).first()
        return recent_otp is None

    def get_last_otp_wait_seconds(self):
        """Keyingi OTP so'rash uchun qancha soniya kutish kerak (1 daqiqa limit)."""
        one_minute_ago = timezone.now() - timezone.timedelta(minutes=1)
        recent_otp = self.otp_codes.filter(created_at__gte=one_minute_ago).first()
        if recent_otp:
            elapsed = (timezone.now() - recent_otp.created_at).total_seconds()
            return max(0, int(60 - elapsed))
        return 0

    def get_active_otp(self):
        """Hali amal qiladigan (ishlatilmagan va muddati o'tmagan) OTP ni qaytaradi."""
        return self.otp_codes.filter(
            is_used=False,
            expires_at__gt=timezone.now()
        ).order_by("-created_at").first()

    def get_active_otp_remaining_seconds(self):
        """Faol OTP ning qolgan amal qilish vaqti (soniyalarda)."""
        active = self.get_active_otp()
        if active:
            remaining = (active.expires_at - timezone.now()).total_seconds()
            return max(0, int(remaining))
        return 0


class OTPCode(models.Model):
    """6 xonali OTP kodi."""
    user = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name="otp_codes",
        verbose_name="Foydalanuvchi"
    )
    code = models.CharField(max_length=6, verbose_name="OTP kodi")
    is_used = models.BooleanField(default=False, verbose_name="Ishlatilganmi")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan vaqt")
    expires_at = models.DateTimeField(verbose_name="Amal qilish muddati")

    class Meta:
        verbose_name = "OTP kodi"
        verbose_name_plural = "OTP kodlari"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.full_name} — {self.code} ({'ishlatilgan' if self.is_used else 'aktiv'})"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(minutes=10)
        super().save(*args, **kwargs)

    @property
    def is_valid(self):
        """OTP hali amal qiladimi va ishlatilmaganmi."""
        return not self.is_used and timezone.now() <= self.expires_at

    @staticmethod
    def generate_code():
        """6 xonali tasodifiy raqam generatsiya qilish."""
        return ''.join(random.choices(string.digits, k=6))

    @classmethod
    def create_for_user(cls, user):
        """Foydalanuvchi uchun yangi OTP yaratish."""
        # Avvalgi ishlatilmagan OTPlarni bekor qilish
        cls.objects.filter(user=user, is_used=False).update(is_used=True)
        
        code = cls.generate_code()
        otp = cls.objects.create(
            user=user,
            code=code,
            expires_at=timezone.now() + timezone.timedelta(minutes=10)
        )
        return otp
