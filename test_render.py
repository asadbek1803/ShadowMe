from django.template import Context, Template, RequestContext
from django.template.loader import render_to_string
from django.http import HttpRequest
import django
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

request = HttpRequest()
request.user = "DjangoUser"
res = render_to_string("study/analysis.html", {"user": "TelegramUser"}, request=request)
print("Is TelegramUser in output?", "TelegramUser" in res)
