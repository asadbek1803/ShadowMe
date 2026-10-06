from pytubefix import YouTube

print("======================================================")
print("YouTube autentifikatsiyasini amalga oshiramiz.")
print("Bu qadam YouTube bot-check xatolarini oldini olish uchun kerak.")
print("======================================================")
try:
    print("Oauth2 keshini yangilash uchun ulanmoqdamiz...")
    # use_oauth=True va allow_oauth_cache=True keshni ishlatishga ruxsat beradi
    yt = YouTube('https://www.youtube.com/watch?v=DxBm-P9f0k0', use_oauth=True, allow_oauth_cache=True)
    stream = yt.streams.get_audio_only()
    print("✅ Muvaffaqiyatli autentifikatsiya qilindi!")
    print("Endi ShadowMe loyihasi YouTube dan videolarni xatosiz yuklay oladi.")
except Exception as e:
    print(f"Xato yuz berdi: {e}")
