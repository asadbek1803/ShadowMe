from django.template import Context, Template, RequestContext
from django.http import HttpRequest
import django
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

request = HttpRequest()
request.user = "DjangoUser"
ctx = RequestContext(request, {"user": "TelegramUser"})
print("Template user:", Template("{{ user }}").render(ctx))
