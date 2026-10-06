from django.contrib import admin
from .models import TelegramUser, OTPCode


@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    list_display = ["full_name", "telegram_id", "username", "phone_number", "is_active", "created_at"]
    list_filter = ["is_active", "created_at"]
    search_fields = ["full_name", "telegram_id", "username", "phone_number"]
    readonly_fields = ["telegram_id", "created_at", "updated_at"]
    ordering = ["-created_at"]


@admin.register(OTPCode)
class OTPCodeAdmin(admin.ModelAdmin):
    list_display = ["user", "code", "is_used", "created_at", "expires_at", "is_valid_display"]
    list_filter = ["is_used", "created_at"]
    search_fields = ["user__full_name", "code"]
    readonly_fields = ["created_at"]
    ordering = ["-created_at"]

    @admin.display(description="Amal qiladimi", boolean=True)
    def is_valid_display(self, obj):
        return obj.is_valid
