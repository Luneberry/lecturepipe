"""F4: Obsidian 마크다운 저장 모듈"""

import os
import re
from datetime import datetime
from modules.transcript import TranscriptEntry, TranscriptResult


def sanitize_filename(title: str) -> str:
    """파일명에 사용할 수 없는 문자를 제거한다. 한글은 유지."""
    # 파일시스템 금지 문자 제거
    sanitized = re.sub(r'[\\/:*?"<>|]', '', title)
    # 연속 공백 정리
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    # 너무 길면 자르기
    if len(sanitized) > 80:
        sanitized = sanitized[:80].strip()
    return sanitized


def format_timestamp(seconds: float) -> str:
    """초를 HH:MM:SS 또는 MM:SS 형식으로 변환한다."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def make_youtube_link(video_id: str, timestamp: float) -> str:
    """타임스탬프 링크가 포함된 YouTube URL을 생성한다."""
    t = int(timestamp)
    return f"https://www.youtube.com/watch?v={video_id}&t={t}s"


def _yaml_escape(value: str) -> str:
    """YAML double-quoted scalar 안에 안전하게 넣을 수 있도록 escape 한다."""
    return value.replace('\\', '\\\\').replace('"', '\\"')


def generate_frontmatter(result: TranscriptResult, language: str) -> str:
    """YAML 프론트매터를 생성한다."""
    today = datetime.now().strftime('%Y-%m-%d')
    safe_title = _yaml_escape(result.title or "")
    return f"""---
source: https://www.youtube.com/watch?v={result.video_id}
title: "{safe_title}"
original_language: {result.language}
output_language: {language}
date: {today}
tags:
  - lecture
  - youtube
---
"""


def group_by_time_sections(entries: list[TranscriptEntry], interval_minutes: int = 5) -> list[tuple[str, list[TranscriptEntry]]]:
    """항목들을 시간 구간별로 그룹화한다."""
    if not entries:
        return []

    sections = []
    interval_sec = interval_minutes * 60
    current_start = 0
    current_entries = []

    for entry in entries:
        section_idx = int(entry.start // interval_sec)
        section_start = section_idx * interval_sec

        if section_start != current_start and current_entries:
            label = f"{format_timestamp(current_start)} ~ {format_timestamp(current_start + interval_sec)}"
            sections.append((label, current_entries))
            current_entries = []
            current_start = section_start
        elif not current_entries:
            current_start = section_start

        current_entries.append(entry)

    if current_entries:
        label = f"{format_timestamp(current_start)} ~ {format_timestamp(current_start + interval_sec)}"
        sections.append((label, current_entries))

    return sections


def format_markdown(result: TranscriptResult, entries: list[TranscriptEntry],
                    captured_frames: list[tuple[float, str]],
                    config: dict) -> str:
    """전체 마크다운 문서를 조립한다."""
    target_lang = config.get('translation', {}).get('target_language', 'ko')
    interval = config.get('output', {}).get('section_interval_minutes', 5)

    lines = []
    lines.append(generate_frontmatter(result, target_lang))
    lines.append(f"# {result.title}\n")
    lines.append(f"> 원본: [YouTube]({make_youtube_link(result.video_id, 0)})")
    lines.append(f"> 원본 언어: {result.language}\n")

    # 프레임 타임스탬프 → 파일명 매핑
    frame_map = {}
    for ts, filename in captured_frames:
        frame_map[ts] = filename

    sections = group_by_time_sections(entries, interval)

    for label, section_entries in sections:
        lines.append(f"\n## {label}\n")
        for entry in section_entries:
            ts = format_timestamp(entry.start)
            yt_link = make_youtube_link(result.video_id, entry.start)
            lines.append(f"[{ts}]({yt_link}) {entry.text}")

            # 이 항목의 시간 범위에 해당하는 캡처 프레임 삽입
            entry_end = entry.start + entry.duration
            for frame_ts in sorted(frame_map.keys()):
                if entry.start <= frame_ts < entry_end:
                    lines.append(f"\n![[{frame_map[frame_ts]}]]\n")

    return '\n'.join(lines) + '\n'


def write_to_vault(result: TranscriptResult, entries: list[TranscriptEntry],
                   captured_frames: list[tuple[float, str]],
                   config: dict) -> str:
    """마크다운 파일을 Obsidian 볼트에 저장한다."""
    vault_path = config['vault']['path']
    lecture_folder = config['vault']['lecture_folder']
    output_dir = os.path.join(vault_path, lecture_folder)
    os.makedirs(output_dir, exist_ok=True)

    today = datetime.now().strftime('%Y-%m-%d')
    safe_title = sanitize_filename(result.title)
    filename = f"{today}_{safe_title}.md"
    filepath = os.path.join(output_dir, filename)

    content = format_markdown(result, entries, captured_frames, config)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    return filepath
