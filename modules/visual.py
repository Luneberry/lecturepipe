"""F3: 시각 참조 감지 + 장면 변화 감지 + 프레임 캡처 모듈
   - ffmpeg scene 필터로 화면 변화 감지
   - 키워드 매칭으로 시각 참조 감지
   - 캡처 후 이미지 유사도 비교로 중복 제거
"""

import os
import re
import subprocess
import sys
from PIL import Image
from modules.transcript import TranscriptEntry


def load_keywords(language: str, keywords_dir: str) -> list[str]:
    """키워드 파일에서 키워드 목록을 로드한다."""
    lang = language.split('-')[0]
    filepath = os.path.join(keywords_dir, f"{lang}.txt")
    if not os.path.exists(filepath):
        filepath = os.path.join(keywords_dir, "en.txt")
    if not os.path.exists(filepath):
        return []
    with open(filepath, 'r', encoding='utf-8') as f:
        return [line.strip().lower() for line in f if line.strip()]


def detect_visual_references(entries: list[TranscriptEntry], keywords: list[str],
                             max_captures: int = 100) -> list[float]:
    """키워드 매칭으로 시각 참조 타임스탬프를 감지한다."""
    if not keywords:
        return []

    timestamps = []
    for entry in entries:
        text_lower = entry.text.lower()
        if any(kw in text_lower for kw in keywords):
            timestamps.append(entry.start)

    return timestamps[:max_captures]


def detect_scene_changes(stream_url: str, threshold: float = 0.4,
                         max_captures: int = 100) -> list[float]:
    """ffmpeg scene 필터로 화면이 크게 바뀌는 시점을 감지한다."""
    print(f"  장면 변화 감지 중 (threshold={threshold})...", file=sys.stderr)
    try:
        result = subprocess.run(
            ['ffmpeg', '-i', stream_url,
             '-vf', f"select='gt(scene,{threshold})',showinfo",
             '-vsync', 'vfr', '-f', 'null', '-'],
            capture_output=True, text=True, timeout=300
        )
        timestamps = []
        for line in result.stderr.split('\n'):
            if 'showinfo' in line and 'pts_time' in line:
                match = re.search(r'pts_time:\s*([\d.]+)', line)
                if match:
                    timestamps.append(float(match.group(1)))

        print(f"  장면 변화 {len(timestamps)}개 감지", file=sys.stderr)
        return timestamps[:max_captures]
    except subprocess.TimeoutExpired:
        print(f"  ⚠ 장면 감지 타임아웃", file=sys.stderr)
        return []
    except Exception as e:
        print(f"  ⚠ 장면 감지 실패: {e}", file=sys.stderr)
        return []


def merge_and_deduplicate(timestamps: list[float], min_gap: float = 15.0) -> list[float]:
    """타임스탬프들을 합치고, min_gap(초) 이내 중복을 제거한다."""
    if not timestamps:
        return []

    sorted_ts = sorted(set(timestamps))
    result = [sorted_ts[0]]
    for ts in sorted_ts[1:]:
        if ts - result[-1] >= min_gap:
            result.append(ts)
    return result


def image_similarity(path_a: str, path_b: str) -> float:
    """두 이미지의 유사도를 0.0~1.0으로 반환한다 (1.0 = 동일).
    리사이즈 후 히스토그램 비교 방식."""
    try:
        img_a = Image.open(path_a).resize((160, 90)).convert('RGB')
        img_b = Image.open(path_b).resize((160, 90)).convert('RGB')
        hist_a = img_a.histogram()
        hist_b = img_b.histogram()
        # 히스토그램 교차(intersection) 기반 유사도
        similarity = sum(min(a, b) for a, b in zip(hist_a, hist_b)) / (sum(hist_a) or 1)
        return similarity
    except Exception:
        return 0.0


def remove_duplicate_frames(results: list[tuple[float, str]], base_dir: str,
                            similarity_threshold: float = 0.92) -> list[tuple[float, str]]:
    """연속된 캡처 프레임 중 유사한 것을 제거한다.
    results의 filename은 상대경로(video_id/ts.jpg) 또는 파일명만 올 수 있다.
    base_dir는 파일들이 실제 존재하는 디렉토리."""
    if len(results) <= 1:
        return results

    kept = [results[0]]
    removed_count = 0

    for i in range(1, len(results)):
        curr_file = os.path.basename(results[i][1])
        prev_file = os.path.basename(kept[-1][1])
        curr_path = os.path.join(base_dir, curr_file)
        prev_path = os.path.join(base_dir, prev_file)

        sim = image_similarity(prev_path, curr_path)
        if sim < similarity_threshold:
            kept.append(results[i])
        else:
            # 중복 파일 삭제
            try:
                os.remove(curr_path)
            except OSError:
                pass
            removed_count += 1

    if removed_count > 0:
        print(f"  중복 프레임 {removed_count}개 제거 → {len(kept)}개 유지", file=sys.stderr)
    return kept


def get_stream_url(video_id: str) -> str:
    """yt-dlp로 스트림 URL을 가져온다 (다운로드 없이)."""
    result = subprocess.run(
        ['yt-dlp', '-g', '-f', 'best[height<=720]', '--no-warnings',
         f'https://www.youtube.com/watch?v={video_id}'],
        capture_output=True, text=True, timeout=30
    )
    url = result.stdout.strip().split('\n')[0]
    if not url:
        raise RuntimeError(f"스트림 URL을 가져올 수 없습니다: {video_id}")
    return url


def format_timestamp_filename(timestamp: float) -> str:
    """타임스탬프를 파일명용 문자열로 변환한다."""
    minutes = int(timestamp // 60)
    seconds = int(timestamp % 60)
    return f"{minutes:02d}m{seconds:02d}s"


def capture_frame(stream_url: str, timestamp: float, output_path: str) -> bool:
    """ffmpeg로 특정 타임스탬프의 프레임을 캡처한다."""
    try:
        result = subprocess.run(
            ['ffmpeg', '-ss', str(timestamp), '-i', stream_url,
             '-frames:v', '1', '-q:v', '2', '-y', output_path],
            capture_output=True, text=True, timeout=30
        )
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception:
        return False


def capture_all_frames(video_id: str, entries: list[TranscriptEntry],
                       assets_dir: str, config: dict) -> list[tuple[float, str]]:
    """키워드 + 장면 변화 기반으로 프레임을 캡처한다. 중복 자동 제거."""
    visual_config = config.get('visual', {})
    max_captures = visual_config.get('max_captures', 100)
    scene_threshold = visual_config.get('scene_threshold', 0.4)
    min_gap = visual_config.get('min_gap_seconds', 15)
    keywords_dir = visual_config.get('keywords_dir', 'keywords')
    similarity_threshold = visual_config.get('similarity_threshold', 0.92)

    # 스트림 URL 가져오기
    print(f"  스트림 URL 가져오는 중...", file=sys.stderr)
    try:
        stream_url = get_stream_url(video_id)
    except Exception as e:
        print(f"  ⚠ 스트림 URL 실패: {e}", file=sys.stderr)
        return []

    video_assets_dir = os.path.join(assets_dir, video_id)
    os.makedirs(video_assets_dir, exist_ok=True)
    all_timestamps = []

    # 1) 장면 변화 감지
    if visual_config.get('scene_detection', True):
        scene_ts = detect_scene_changes(stream_url, threshold=scene_threshold,
                                        max_captures=max_captures)
        all_timestamps.extend(scene_ts)

    # 2) 키워드 기반 감지
    keywords_dir_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                     keywords_dir)
    language = 'en'
    if entries and any(ord(c) >= 0xAC00 and ord(c) <= 0xD7A3 for c in entries[0].text):
        language = 'ko'
    keywords = load_keywords(language, keywords_dir_path)
    keyword_ts = detect_visual_references(entries, keywords, max_captures)
    all_timestamps.extend(keyword_ts)

    # 합치기 + 시간 간격 중복 제거
    final_timestamps = merge_and_deduplicate(all_timestamps, min_gap=min_gap)
    if len(final_timestamps) > max_captures:
        final_timestamps = final_timestamps[:max_captures]

    print(f"  총 캡처 대상: {len(final_timestamps)}개 (장면변화 + 키워드)", file=sys.stderr)

    # 프레임 캡처
    results = []
    total = len(final_timestamps)
    for i, ts in enumerate(final_timestamps, 1):
        ts_str = format_timestamp_filename(ts)
        filename = f"{ts_str}.jpg"
        rel_path = f"{video_id}/{filename}"
        output_path = os.path.join(video_assets_dir, filename)
        minutes = int(ts // 60)
        seconds = int(ts % 60)
        print(f"  [{i}/{total}] 프레임 캡처: {minutes:02d}:{seconds:02d}...", file=sys.stderr)

        if capture_frame(stream_url, ts, output_path):
            results.append((ts, rel_path))
        else:
            print(f"  ⚠ 캡처 실패: {minutes:02d}:{seconds:02d}", file=sys.stderr)

    # 이미지 유사도 기반 중복 제거
    results = remove_duplicate_frames(results, video_assets_dir, similarity_threshold)

    return results
