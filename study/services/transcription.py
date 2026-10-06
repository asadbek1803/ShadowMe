"""
WhisperX/FasterWhisper Transcription Pipeline for Shadowing Feature.
Converts video/audio to word-level timestamped transcripts (karaoke JSON).

faster-whisper ishlatiladi (CPU da ham ishlaydi, GPU bo'lsa tezlashadi).
"""
import os
import sys
import subprocess
import json
import tempfile
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from django.conf import settings
from django.utils import timezone
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Audio helpers
# ─────────────────────────────────────────────────────────────────────────────

def extract_audio(video_path: str, output_path: str) -> bool:
    """
    Extract 16kHz mono WAV from video using ffmpeg.
    """
    try:
        cmd = [
            'ffmpeg', '-y', '-i', video_path,
            '-vn', '-ac', '1', '-ar', '16000',
            '-acodec', 'pcm_s16le',
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            logger.error(f"ffmpeg failed: {result.stderr[-300:]}")
            return False
        return True
    except FileNotFoundError:
        logger.error("ffmpeg topilmadi. PATH ga qo'shing: https://ffmpeg.org/download.html")
        return False
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg timeout (5 min)")
        return False
    except Exception as e:
        logger.error(f"extract_audio xato: {e}")
        return False


def download_youtube_video(url: str, output_dir: str) -> Optional[dict]:
    """
    YouTube dan video (mp4) yuklab olish — RapidAPI youtube-info-download-api orqali.
    """
    import requests
    import time
    
    try:
        logger.info(f"RapidAPI orqali video yuklanmoqda: {url}")
        
        api_url = "https://youtube-info-download-api.p.rapidapi.com/ajax/download.php"
        querystring = {
            "format": "360",
            "add_info": "1",
            "url": url
        }
        headers = {
            "x-rapidapi-key": "022e4eb3f2msha1f7931fb9addfcp113296jsn597d9f47e3d2",
            "x-rapidapi-host": "youtube-info-download-api.p.rapidapi.com",
            "Content-Type": "application/json"
        }
        
        response = requests.get(api_url, headers=headers, params=querystring, timeout=30)
        data = response.json()
        
        progress_url = data.get("progress_url")
        if not progress_url:
            logger.error(f"RapidAPI dan progress_url olinmadi: {data}")
            return None
            
        download_url = None
        max_retries = 60 # wait up to 2 minutes
        for _ in range(max_retries):
            time.sleep(2)
            poll_resp = requests.get(progress_url, timeout=30)
            poll_data = poll_resp.json()
            
            if poll_data.get("success") == 1 and poll_data.get("download_url"):
                download_url = poll_data.get("download_url")
                break
                
        if not download_url:
            logger.error("Video download URL olinmadi (timeout).")
            return None
            
        logger.info(f"Download URL olindi: {download_url}")
        
        # Faylni yuklab olish
        out_path = os.path.join(output_dir, f"video_{int(time.time())}.mp4")
        with requests.get(download_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(out_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): 
                    f.write(chunk)
                    
        return {
            "path": out_path,
            "title": data.get("title"),
            "thumbnail_url": data.get("thumbnail_url")
        }
    except Exception as e:
        logger.error(f"YouTube video yuklashda xato: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Transcription (faster-whisper)
# ─────────────────────────────────────────────────────────────────────────────

def transcribe_with_faster_whisper(audio_path: str, language: str = 'en') -> Optional[Dict]:
    """
    faster-whisper bilan transkripsiya. Word-level timestamp bilan.
    CPU va GPU da ishlaydi.
    """
    try:
        from faster_whisper import WhisperModel

        # Model tanlash: CPU da 'small' tez, 'medium' aniqroq
        model_size = getattr(settings, 'WHISPER_MODEL_SIZE', 'small')
        device = "auto"  # GPU bo'lsa GPU, bo'lmasa CPU
        compute_type = "int8"  # CPU da eng tez

        logger.info(f"faster-whisper modeli yuklanmoqda: {model_size} ({device}/{compute_type})")
        model = WhisperModel(model_size, device=device, compute_type=compute_type)

        logger.info(f"Transkripsiya boshlanmoqda: {audio_path}")
        segments_iter, info = model.transcribe(
            audio_path,
            language=language,
            word_timestamps=True,  # So'z darajasida timestamp
            beam_size=5,
            vad_filter=True,       # Ovozli faollik aniqlash — tezlashtiradi
        )

        logger.info(f"Til aniqlandi: {info.language} (ishonch: {info.language_probability:.2f})")

        # Segmentlarni yig'ish
        raw_segments = []
        for seg in segments_iter:
            words = []
            if seg.words:
                for w in seg.words:
                    words.append({
                        "word":  w.word.strip(),
                        "start": round(w.start, 3),
                        "end":   round(w.end, 3),
                    })
            raw_segments.append({
                "start": round(seg.start, 3),
                "end":   round(seg.end, 3),
                "text":  seg.text.strip(),
                "words": words,
            })

        return {"segments": raw_segments, "language": info.language}

    except ImportError:
        logger.error("faster-whisper o'rnatilmagan: pip install faster-whisper")
        return None
    except Exception as e:
        logger.exception(f"Transkripsiya xato: {e}")
        return None


def build_karaoke_json(result: Dict) -> Tuple[List[Dict], List[Dict]]:
    """
    faster-whisper natijasini karaoke JSON formatiga o'girish.

    Returns:
        segments_json: [{id, start, end, text, words:[{word,start,end}]}]
        words_json:    [{word, start, end, segment_id}]
    """
    segments_json: List[Dict] = []
    words_json:    List[Dict] = []

    for seg_idx, segment in enumerate(result.get("segments", [])):
        seg_start = segment.get("start", 0)
        seg_end   = segment.get("end", 0)
        seg_text  = segment.get("text", "").strip()

        words = []
        for word_data in segment.get("words", []):
            word = word_data.get("word", "").strip()
            if not word:
                continue
            w_start = round(word_data.get("start", seg_start), 3)
            w_end   = round(word_data.get("end",   seg_end),   3)
            words.append({"word": word, "start": w_start, "end": w_end})
            words_json.append({"word": word, "start": w_start, "end": w_end, "segment_id": seg_idx})

        if words:
            segments_json.append({
                "id":    seg_idx,
                "start": round(seg_start, 3),
                "end":   round(seg_end, 3),
                "text":  seg_text,
                "words": words,
            })

    return segments_json, words_json


# ─────────────────────────────────────────────────────────────────────────────
# Full pipeline
# ─────────────────────────────────────────────────────────────────────────────

async def run_transcription_for_transcript(transcript_id: str) -> bool:
    """
    To'liq pipeline: video/url → audio → faster-whisper → karaoke JSON → DB saqlash.
    Background threaddan chaqiriladi.
    """
    from study.models import LessonTranscript

    @sync_to_async
    def get_transcript():
        return LessonTranscript.objects.select_related('lesson').get(id=transcript_id)

    @sync_to_async
    def update_transcript(transcript, **fields):
        for k, v in fields.items():
            setattr(transcript, k, v)
        save_fields = list(fields.keys())
        if 'updated_at' not in save_fields:
            pass  # auto_now=True bo'lsa qo'shmasa ham bo'ladi
        transcript.save(update_fields=save_fields)

    @sync_to_async
    def update_lesson_metadata(transcript, **fields):
        if not transcript.lesson_id:
            return
        lesson = transcript.lesson
        for k, v in fields.items():
            setattr(lesson, k, v)
        lesson.save(update_fields=list(fields.keys()))

    @sync_to_async
    def save_video_to_transcript(transcript_obj, video_path_str):
        from django.core.files import File
        import os
        if video_path_str and os.path.exists(video_path_str):
            with open(video_path_str, 'rb') as f:
                transcript_obj.video_file.save(os.path.basename(video_path_str), File(f), save=True)
            if transcript_obj.lesson:
                transcript_obj.lesson.video_url = transcript_obj.video_file.url
                transcript_obj.lesson.save()

    try:
        transcript = await get_transcript()
    except Exception as e:
        logger.error(f"Transcript topilmadi {transcript_id}: {e}")
        return False

    try:
        await update_transcript(transcript, status='processing')
        logger.info(f"[{transcript_id}] Status: processing")

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path: Optional[str] = None

            # ── Manba ──────────────────────────────────────────────────────────
            if transcript.source_type == 'youtube':
                video_info = download_youtube_video(transcript.source_url, tmpdir)
                if not video_info or not video_info.get("path"):
                    raise Exception("YouTube video yuklab olinmadi (RapidAPI xato)")
                
                video_path = video_info["path"]
                # Save metadata to lesson
                if transcript.lesson_id:
                    updates = {}
                    if video_info.get("title"):
                        updates["title"] = video_info["title"]
                    if video_info.get("thumbnail_url"):
                        updates["thumbnail_url"] = video_info["thumbnail_url"]
                    if updates:
                        await update_lesson_metadata(transcript, **updates)
                
                # DB ga videoni saqlash (shunda iframe o'rniga HTML5 video ishlashi mumkin)
                await save_video_to_transcript(transcript, video_path)

                # Videodan audio ajratib olish (whisper uchun)
                wav_path = os.path.join(tmpdir, 'audio.wav')
                ok = extract_audio(video_path, wav_path)
                if not ok:
                    raise Exception("YouTube videodan audio ajratilmadi (ffmpeg xato)")
                audio_path = wav_path

            elif transcript.video_file:
                wav_path = os.path.join(tmpdir, 'audio.wav')
                ok = extract_audio(transcript.video_file.path, wav_path)
                if not ok:
                    raise Exception("Videodan audio ajratilmadi (ffmpeg xato)")
                audio_path = wav_path

            elif transcript.audio_file:
                audio_path = transcript.audio_file.path

            else:
                raise Exception("Audio manba topilmadi")

            if not audio_path or not os.path.exists(audio_path):
                raise Exception(f"Audio fayl topilmadi: {audio_path}")

            audio_size_mb = os.path.getsize(audio_path) / 1_048_576
            logger.info(f"[{transcript_id}] Audio tayyor: {audio_size_mb:.1f} MB")

            # ── Transkripsiya ─────────────────────────────────────────────────
            result = transcribe_with_faster_whisper(audio_path, transcript.language)
            if not result:
                raise Exception("faster-whisper transkripsiya muvaffaqiyatsiz")

            segments_json, words_json = build_karaoke_json(result)
            if not segments_json:
                raise Exception("Segmentlar bo'sh — audio aniqlanmadi")

            duration = max((s["end"] for s in segments_json), default=0)
            logger.info(f"[{transcript_id}] {len(segments_json)} segment, {duration:.1f}s")
            
            if transcript.lesson_id:
                await update_lesson_metadata(transcript, duration_minutes=int(duration // 60))

            # ── Saqlash ───────────────────────────────────────────────────────
            await update_transcript(
                transcript,
                status='ready',
                segments_json=segments_json,
                words_json=words_json,
                duration_seconds=duration,
                error_message=None,
            )
            logger.info(f"[{transcript_id}] Tayyor!")
            return True

    except Exception as e:
        logger.exception(f"[{transcript_id}] Pipeline xato: {e}")
        try:
            await update_transcript(transcript, status='failed', error_message=str(e))
        except Exception:
            pass
        return False


def run_transcription_sync(transcript_id: str) -> bool:
    """Management command uchun sync wrapper."""
    import asyncio
    return asyncio.run(run_transcription_for_transcript(transcript_id))