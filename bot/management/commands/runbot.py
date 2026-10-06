"""
python manage.py runbot

Telegram botni ishga tushirish buyrug'i (aiogram 3).
"""

import asyncio
import logging
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "ShadowMe Telegram botini ishga tushirish (aiogram 3)"

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS("🤖 ShadowMe Telegram boti ishga tushmoqda...")
        )

        try:
            from bot.bot import start_polling

            self.stdout.write(self.style.SUCCESS("✅ Bot muvaffaqiyatli ishga tushdi!"))
            self.stdout.write("📡 Polling rejimida ishlayapti. To'xtatish uchun Ctrl+C bosing.")

            asyncio.run(start_polling())

        except ValueError as e:
            self.stderr.write(self.style.ERROR(f"❌ Xato: {e}"))
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS("\n🛑 Bot to'xtatildi."))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"❌ Bot xatosi: {e}"))
            raise
