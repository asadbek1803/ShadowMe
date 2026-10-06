"""
accounts/views.py — To'liq async viewlar.
Uvicorn + ASGI bilan ishlaydi.
Barcha ORM va session chaqiruvlari sync_to_async orqali o'ralgan.
"""
import json
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views import View
from django.core.cache import cache
from django.utils import timezone
from asgiref.sync import sync_to_async

from .models import TelegramUser, OTPCode


# ─────────────────────────────────────────────────────────────────────────────
# sync_to_async wrappers — session va ORM
# ─────────────────────────────────────────────────────────────────────────────

@sync_to_async
def _get_session_user_id(request):
    return request.session.get("user_id")


@sync_to_async
def _find_otp(otp_code):
    try:
        return OTPCode.objects.select_related("user").get(
            code=otp_code,
            is_used=False,
        )
    except OTPCode.DoesNotExist:
        return None


@sync_to_async
def _mark_otp_used(otp_obj):
    otp_obj.is_used = True
    otp_obj.save(update_fields=["is_used"])


@sync_to_async
def _set_session(request, user):
    request.session["user_id"]           = user.id
    request.session["telegram_id"]       = user.telegram_id
    request.session["full_name"]         = user.full_name
    request.session["username"]          = user.username or ""
    request.session["profile_image_url"] = user.profile_image_url or ""
    request.session["phone_number"]      = user.phone_number or ""


@sync_to_async
def _flush_session(request):
    request.session.flush()


# ─────────────────────────────────────────────────────────────────────────────
# Cache helpers — sync_to_async orqali (Django cache sync)
# ─────────────────────────────────────────────────────────────────────────────

@sync_to_async
def _cache_get(key):
    return cache.get(key)


@sync_to_async
def _cache_set(key, value, timeout):
    cache.set(key, value, timeout)


@sync_to_async
def _cache_delete(*keys):
    for key in keys:
        cache.delete(key)


@sync_to_async
def _cache_incr_attempt(key, window):
    """Urinish sonini oshirish."""
    val = cache.get(key, 0) + 1
    cache.set(key, val, window)
    return val


# ─────────────────────────────────────────────────────────────────────────────
# IP Rate Limiter (async-safe)
# ─────────────────────────────────────────────────────────────────────────────

class OTPRateLimiter:
    """
    IP manzili asosida OTP verify endpoint uchun rate limiter.
    Qoidalar:
      • 5 ta noto'g'ri urinishdan keyin 15 daqiqa bloklanadi
      • Muvaffaqiyatli kirishdan keyin hisoblagich nolga tushadi
    """
    MAX_ATTEMPTS    = 5
    WINDOW_SECONDS  = 15 * 60   # 15 daqiqa
    LOCKOUT_SECONDS = 15 * 60   # 15 daqiqa

    @staticmethod
    def get_client_ip(request) -> str:
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")

    @classmethod
    def _attempt_key(cls, ip: str) -> str:
        return f"otp_attempts:{ip}"

    @classmethod
    def _lockout_key(cls, ip: str) -> str:
        return f"otp_lockout:{ip}"

    # -- async methods --

    @classmethod
    async def is_locked(cls, ip: str) -> tuple[bool, int]:
        lockout_until = await _cache_get(cls._lockout_key(ip))
        if lockout_until is None:
            return False, 0
        remaining = int((lockout_until - timezone.now()).total_seconds())
        if remaining <= 0:
            await _cache_delete(cls._lockout_key(ip), cls._attempt_key(ip))
            return False, 0
        return True, remaining

    @classmethod
    async def record_failure(cls, ip: str) -> tuple[int, bool]:
        """Noto'g'ri urinishni qayd etish. (attempts_count, is_now_locked) qaytaradi."""
        key = cls._attempt_key(ip)
        attempts = await _cache_incr_attempt(key, cls.WINDOW_SECONDS)

        if attempts >= cls.MAX_ATTEMPTS:
            lockout_until = timezone.now() + timezone.timedelta(seconds=cls.LOCKOUT_SECONDS)
            await _cache_set(cls._lockout_key(ip), lockout_until, cls.LOCKOUT_SECONDS)
            await _cache_delete(key)
            return attempts, True

        return attempts, False

    @classmethod
    async def record_success(cls, ip: str):
        await _cache_delete(cls._attempt_key(ip), cls._lockout_key(ip))


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────

class HomeView(View):
    """Landing page."""

    async def get(self, request):
        user_id = await _get_session_user_id(request)
        if user_id:
            return redirect("/dashboard/")
        return render(request, "home.html")


class LoginView(View):
    """Login sahifasi — 6 xonali OTP kiritish."""

    async def get(self, request):
        user_id = await _get_session_user_id(request)
        if user_id:
            redirect_url = request.GET.get("redirect", "/dashboard/")
            return redirect(redirect_url)

        return render(request, "accounts/login.html", {
            "bot_username": "ShadowMeLoginBot",
            "redirect": request.GET.get("redirect", "/dashboard/"),
        })


class VerifyOTPView(View):
    """OTP tekshirish API — AJAX POST, IP rate limiting bilan."""

    async def post(self, request):
        ip = OTPRateLimiter.get_client_ip(request)

        # 1. Bloklanganmi?
        locked, remaining = await OTPRateLimiter.is_locked(ip)
        if locked:
            mins = remaining // 60
            secs = remaining % 60
            time_str = f"{mins} daqiqa {secs} soniya" if mins > 0 else f"{secs} soniya"
            return JsonResponse({
                "success": False,
                "message": f"Juda ko'p noto'g'ri urinish. {time_str} dan keyin qayta urinib ko'ring.",
                "locked": True,
                "retry_after": remaining,
            }, status=429)

        # 2. So'rovni olish
        try:
            data = json.loads(request.body)
            otp_code = data.get("otp", "").strip()
        except (json.JSONDecodeError, AttributeError):
            otp_code = request.POST.get("otp", "").strip()

        if not otp_code or len(otp_code) != 6 or not otp_code.isdigit():
            return JsonResponse({
                "success": False,
                "message": "OTP kodi 6 xonali raqam bo'lishi kerak.",
            }, status=400)

        # 3. OTPni topish
        otp_obj = await _find_otp(otp_code)
        if otp_obj is None:
            attempts, now_locked = await OTPRateLimiter.record_failure(ip)
            remaining_tries = max(0, OTPRateLimiter.MAX_ATTEMPTS - attempts)

            if now_locked:
                return JsonResponse({
                    "success": False,
                    "message": (
                        f"Juda ko'p noto'g'ri urinish! "
                        f"{OTPRateLimiter.LOCKOUT_SECONDS // 60} daqiqa bloklandingiz."
                    ),
                    "locked": True,
                    "retry_after": OTPRateLimiter.LOCKOUT_SECONDS,
                }, status=429)

            return JsonResponse({
                "success": False,
                "message": (
                    f"OTP kodi noto'g'ri yoki allaqachon ishlatilgan. "
                    f"({remaining_tries} ta urinish qoldi)"
                    if remaining_tries > 0
                    else "OTP kodi noto'g'ri yoki allaqachon ishlatilgan."
                ),
            }, status=400)

        # 4. Muddatini tekshirish
        if not otp_obj.is_valid:
            await OTPRateLimiter.record_failure(ip)
            return JsonResponse({
                "success": False,
                "message": "OTP kodining amal qilish muddati tugagan. Botdan yangisini oling.",
            }, status=400)

        # 5. Muvaffaqiyatli
        await _mark_otp_used(otp_obj)
        await OTPRateLimiter.record_success(ip)

        user = otp_obj.user
        await _set_session(request, user)

        redirect_url = request.GET.get("redirect", "/dashboard/")
        return JsonResponse({
            "success": True,
            "message": f"Xush kelibsiz, {user.full_name}!",
            "redirect": redirect_url,
            "user": {
                "full_name":         user.full_name,
                "username":          user.username,
                "profile_image_url": user.profile_image_url,
            },
        })


class LogoutView(View):
    """Chiqish — sessionni tozalash."""

    async def get(self, request):
        await _flush_session(request)
        return redirect("/login/")
