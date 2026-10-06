"""
Management command for running WhisperX transcription pipeline.

Usage:
    python manage.py transcribe --lesson <lesson_id>     # Transcribe specific lesson
    python manage.py transcribe --transcript <id>        # Transcribe specific transcript
    python manage.py transcribe --pending                # Process all pending transcripts
    python manage.py transcribe --all                    # Process all transcripts (retry failed)
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from study.models import LessonTranscript, Lesson
from study.services.transcription import run_transcription_sync

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run WhisperX transcription for lessons/transcripts"

    def add_arguments(self, parser):
        parser.add_argument(
            '--lesson',
            type=int,
            help='Lesson ID to transcribe (creates transcript if not exists)'
        )
        parser.add_argument(
            '--transcript',
            type=str,
            help='Transcript UUID to process'
        )
        parser.add_argument(
            '--pending',
            action='store_true',
            help='Process all pending transcripts'
        )
        parser.add_argument(
            '--failed',
            action='store_true',
            help='Retry all failed transcripts'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Process all transcripts (pending + failed)'
        )
        parser.add_argument(
            '--language',
            type=str,
            default='en',
            help='Language code (default: en)'
        )

    def handle(self, *args, **options):
        lesson_id = options.get('lesson')
        transcript_id = options.get('transcript')
        pending = options.get('pending')
        failed = options.get('failed')
        all_transcripts = options.get('all')
        language = options.get('language')

        if not any([lesson_id, transcript_id, pending, failed, all_transcripts]):
            raise CommandError("Please specify --lesson, --transcript, --pending, --failed, or --all")

        transcripts_to_process = []

        if lesson_id:
            try:
                lesson = Lesson.objects.get(id=lesson_id)
                # Get or create transcript
                transcript, created = LessonTranscript.objects.get_or_create(
                    lesson=lesson,
                    defaults={'language': language}
                )
                if created or transcript.status in ['pending', 'failed']:
                    transcripts_to_process.append(transcript)
                    if created:
                        self.stdout.write(f"Created new transcript for lesson {lesson_id}")
                else:
                    self.stdout.write(f"Transcript for lesson {lesson_id} already {transcript.status}")

            except Lesson.DoesNotExist:
                raise CommandError(f"Lesson {lesson_id} not found")

        if transcript_id:
            try:
                transcript = LessonTranscript.objects.get(id=transcript_id)
                transcripts_to_process.append(transcript)
            except LessonTranscript.DoesNotExist:
                raise CommandError(f"Transcript {transcript_id} not found")

        if pending:
            transcripts_to_process.extend(
                LessonTranscript.objects.filter(status='pending')
            )

        if failed:
            transcripts_to_process.extend(
                LessonTranscript.objects.filter(status='failed')
            )

        if all_transcripts:
            transcripts_to_process.extend(
                LessonTranscript.objects.filter(status__in=['pending', 'failed'])
            )

        # Deduplicate
        seen = set()
        unique_transcripts = []
        for t in transcripts_to_process:
            if t.id not in seen:
                seen.add(t.id)
                unique_transcripts.append(t)

        if not unique_transcripts:
            self.stdout.write(self.style.WARNING("No transcripts to process"))
            return

        self.stdout.write(f"Processing {len(unique_transcripts)} transcript(s)...")

        success_count = 0
        fail_count = 0

        for transcript in unique_transcripts:
            self.stdout.write(f"  Processing {transcript.id} (lesson: {transcript.lesson_id})...")

            # Update language if provided
            if language and transcript.language != language:
                transcript.language = language
                transcript.save(update_fields=['language'])

            # Run transcription
            success = run_transcription_sync(str(transcript.id))

            if success:
                self.stdout.write(self.style.SUCCESS(f"    �� Completed"))
                success_count += 1
            else:
                self.stdout.write(self.style.ERROR(f"    �� Failed"))
                fail_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nDone: {success_count} succeeded, {fail_count} failed"
        ))