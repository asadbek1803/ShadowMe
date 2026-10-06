from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("api/verify-otp/", csrf_exempt(views.VerifyOTPView.as_view()), name="verify_otp"),
]
