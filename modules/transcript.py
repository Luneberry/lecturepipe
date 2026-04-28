"""F1: YouTube 자막 추출 모듈"""

import re
import subprocess
from dataclasses import dataclass, field
from youtube_transcript_api import YouTubeTranscriptApi


@dataclass
class TranscriptEntry:
    text: str
    start: float
    duration: float


@dataclass
class TranscriptResult:
    entries: list[TranscriptEntry]
    language: str
    video_id: str
    title: str


def parse_video_id(url: str) -> str:
    """다양한 YouTube URL 형식에서 video_id를 추출한다."""
    patterns = [
        r'(?:youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com/watch\?v=)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com/live/)([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    # url 자체가 video_id인 경우
    if re.match(r'^[a-zA-Z0-9_-]{11}$', url):
        return url
    raise ValueError(f"유효한 YouTube URL이 아닙니다: {url}")


def get_video_title(video_id: str) -> str:
    """yt-dlp로 영상 제목을 가져온다."""
    try:
        result = subprocess.run(
            ['yt-dlp', '--get-title', '--no-warnings', f'https://www.youtube.com/watch?v={video_id}'],
            capture_output=True, text=True, timeout=30
        )
        title = result.stdout.strip()
        return title if title else video_id
    except Exception:
        return video_id


def fetch_transcript(video_id: str, language_priority: list[str] = None) -> TranscriptResult:
    """자막을 추출한다. language_priority 순서로 시도."""
    if language_priority is None:
        language_priority = ['ko', 'en']

    title = get_video_title(video_id)
    ytt_api = YouTubeTranscriptApi()
    transcript_list = ytt_api.list(video_id)

    # 1) 수동 자막 우선 시도
    for lang in language_priority:
        try:
            transcript = transcript_list.find_transcript([lang])
            raw = transcript.fetch()
            entries = [TranscriptEntry(text=s.text, start=s.start, duration=s.duration) for s in raw]
            return TranscriptResult(entries=entries, language=lang, video_id=video_id, title=title)
        except Exception:
            continue

    # 2) 자동 생성 자막 시도
    for lang in language_priority:
        try:
            transcript = transcript_list.find_generated_transcript([lang])
            raw = transcript.fetch()
            entries = [TranscriptEntry(text=s.text, start=s.start, duration=s.duration) for s in raw]
            return TranscriptResult(entries=entries, language=f"{lang}-auto", video_id=video_id, title=title)
        except Exception:
            continue

    # 3) 아무 자막이나 가져오기
    for transcript in transcript_list:
        raw = transcript.fetch()
        entries = [TranscriptEntry(text=s.text, start=s.start, duration=s.duration) for s in raw]
        return TranscriptResult(entries=entries, language=transcript.language_code, video_id=video_id, title=title)

    raise RuntimeError(f"자막을 찾을 수 없습니다: {video_id}")
