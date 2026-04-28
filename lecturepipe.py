#!/usr/bin/env python3
"""LecturePipe — YouTube 강의 자막 추출·번역·Obsidian 저장 CLI"""

import argparse
import os
import sys
import time

import yaml

from modules.transcript import parse_video_id, fetch_transcript
from modules.translate import should_translate, translate_entries
from modules.visual import capture_all_frames
from modules.obsidian import write_to_vault


def load_config(config_path: str = None) -> dict:
    """설정 파일을 로드한다."""
    if config_path is None:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.yaml')
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    if 'vault' in config and 'path' in config['vault']:
        config['vault']['path'] = os.path.expanduser(config['vault']['path'])
    return config


def process_single(url: str, config: dict, terminal_only: bool = False,
                   no_translate: bool = False, no_summary: bool = False,
                   no_visual: bool = False) -> bool:
    """단일 URL 파이프라인을 실행한다."""
    try:
        # Step 1: 자막 추출
        video_id = parse_video_id(url)
        lang_priority = config.get('transcript', {}).get('language_priority', ['ko', 'en'])
        print(f"  자막 추출 중... (video_id: {video_id})", file=sys.stderr)
        result = fetch_transcript(video_id, lang_priority)
        print(f"  제목: {result.title}", file=sys.stderr)
        print(f"  언어: {result.language} ({len(result.entries)}개 항목)", file=sys.stderr)

        # Step 2: 번역 / 요약
        entries = result.entries
        is_korean = result.language.startswith('ko')

        if no_translate and no_summary:
            print(f"  번역/요약 모두 건너뜀", file=sys.stderr)
        elif no_translate and not no_summary:
            # 요약만 (한국어든 외국어든 원문 기반 한국어 요약)
            print(f"  요약 시작 (Gemini)...", file=sys.stderr)
            entries = translate_entries(entries, result.language, mode='summary', config=config)
            print(f"  요약 완료", file=sys.stderr)
        elif not no_translate and no_summary:
            # 번역만 (외국어→한국어 직역, 한국어면 스킵)
            if not is_korean:
                print(f"  번역 시작 (Gemini)...", file=sys.stderr)
                entries = translate_entries(entries, result.language, mode='translate', config=config)
                print(f"  번역 완료", file=sys.stderr)
            else:
                print(f"  이미 한국어, 번역 건너뜀", file=sys.stderr)
        else:
            # 기본: 번역+요약 (외국어→번역·요약, 한국어→요약)
            action = "요약" if is_korean else "번역·요약"
            print(f"  {action} 시작 (Gemini)...", file=sys.stderr)
            entries = translate_entries(entries, result.language, mode='both', config=config)
            print(f"  {action} 완료", file=sys.stderr)

        # Step 3: 시각 참조 + 장면 변화 캡처
        captured_frames = []
        visual_config = config.get('visual', {})
        if not no_visual and visual_config.get('enabled', True) and not terminal_only:
            assets_dir = os.path.join(config['vault']['path'], config['vault']['assets_folder'])
            captured_frames = capture_all_frames(video_id, result.entries, assets_dir, config)
            print(f"  프레임 {len(captured_frames)}개 캡처 완료", file=sys.stderr)

        # Step 4: 출력
        if terminal_only:
            # 터미널 출력
            print(f"\n{'='*60}")
            print(f"제목: {result.title}")
            print(f"언어: {result.language}")
            print(f"{'='*60}\n")
            for entry in entries:
                minutes = int(entry.start // 60)
                seconds = int(entry.start % 60)
                print(f"[{minutes:02d}:{seconds:02d}] {entry.text}")
        else:
            # Obsidian 저장
            filepath = write_to_vault(result, entries, captured_frames, config)
            print(f"  저장 완료: {filepath}", file=sys.stderr)

        return True

    except Exception as e:
        print(f"  ✗ 오류: {e}", file=sys.stderr)
        return False


def process_batch(batch_file: str, config: dict, delay: float = 2.0, **kwargs) -> None:
    """URL 목록 파일을 순차 처리한다."""
    with open(batch_file, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]

    total = len(urls)
    success = 0
    failed = 0

    print(f"배치 처리 시작: {total}개 URL\n", file=sys.stderr)

    for i, url in enumerate(urls, 1):
        print(f"[{i}/{total}] 처리 중: {url}", file=sys.stderr)
        if process_single(url, config, **kwargs):
            success += 1
        else:
            failed += 1

        if i < total:
            time.sleep(delay)

    print(f"\n{'='*40}", file=sys.stderr)
    print(f"완료: {success}/{total} 성공, {failed} 실패", file=sys.stderr)


def cleanup_orphan_images(config: dict) -> None:
    """마크다운에서 참조되지 않는 고아 이미지를 삭제한다."""
    vault_path = config['vault']['path']
    lecture_folder = config['vault']['lecture_folder']
    assets_folder = config['vault']['assets_folder']
    md_dir = os.path.join(vault_path, lecture_folder)
    assets_dir = os.path.join(vault_path, assets_folder)

    if not os.path.exists(assets_dir):
        print("assets 폴더가 없습니다.", file=sys.stderr)
        return

    # 모든 .md 파일에서 참조되는 이미지 수집
    referenced = set()
    if os.path.exists(md_dir):
        for fname in os.listdir(md_dir):
            if fname.endswith('.md'):
                with open(os.path.join(md_dir, fname), 'r', encoding='utf-8') as f:
                    content = f.read()
                # ![[파일명]] 또는 ![[폴더/파일명]] 패턴
                import re
                for match in re.finditer(r'!\[\[(.+?)\]\]', content):
                    referenced.add(match.group(1))

    # assets 폴더 내 모든 이미지 확인
    orphans = []
    for root, dirs, files in os.walk(assets_dir):
        for fname in files:
            if fname.lower().endswith(('.jpg', '.jpeg', '.png')):
                full_path = os.path.join(root, fname)
                # 상대 경로: video_id/ts.jpg 형태
                rel = os.path.relpath(full_path, assets_dir)
                if rel not in referenced and fname not in referenced:
                    orphans.append(full_path)

    if not orphans:
        print("고아 이미지 없음. 깨끗합니다!", file=sys.stderr)
        return

    print(f"고아 이미지 {len(orphans)}개 발견:", file=sys.stderr)
    for p in orphans:
        print(f"  {os.path.relpath(p, assets_dir)}", file=sys.stderr)

    # 삭제
    for p in orphans:
        os.remove(p)
    print(f"{len(orphans)}개 삭제 완료.", file=sys.stderr)

    # 빈 하위 폴더 정리
    for root, dirs, files in os.walk(assets_dir, topdown=False):
        if root != assets_dir and not os.listdir(root):
            os.rmdir(root)
            print(f"  빈 폴더 삭제: {os.path.relpath(root, assets_dir)}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description='LecturePipe — YouTube 강의 자막 추출·번역·Obsidian 저장',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('url', nargs='?', help='YouTube 영상 URL')
    parser.add_argument('--batch', metavar='FILE', help='URL 목록 파일 (배치 모드)')
    parser.add_argument('--batch-delay', type=float, default=None, help='배치 모드 URL 간 대기 시간(초)')
    parser.add_argument('--vault', help='Obsidian 볼트 경로 (config.yaml 오버라이드)')
    parser.add_argument('--no-translate', action='store_true', help='번역 비활성화 (요약은 유지)')
    parser.add_argument('--no-summary', action='store_true', help='요약 비활성화 (번역은 유지)')
    parser.add_argument('--no-visual', action='store_true', help='시각 참조 캡처 비활성화')
    parser.add_argument('--terminal-only', action='store_true', help='터미널에만 출력 (파일 저장 안 함)')
    parser.add_argument('--cleanup', action='store_true', help='마크다운에서 참조되지 않는 고아 이미지 삭제')
    parser.add_argument('--config', help='설정 파일 경로')

    args = parser.parse_args()

    if not args.url and not args.batch and not args.cleanup:
        parser.print_help()
        sys.exit(1)

    config = load_config(args.config)

    if args.vault:
        config['vault']['path'] = args.vault

    kwargs = {
        'no_translate': args.no_translate,
        'no_summary': args.no_summary,
        'no_visual': args.no_visual,
        'terminal_only': args.terminal_only,
    }

    if args.cleanup:
        cleanup_orphan_images(config)
        return

    if args.batch:
        delay = args.batch_delay or config.get('batch', {}).get('delay_seconds', 2)
        process_batch(args.batch, config, delay=delay, **kwargs)
    else:
        print(f"\nLecturePipe 시작\n", file=sys.stderr)
        success = process_single(args.url, config, **kwargs)
        if success:
            print(f"\n완료!", file=sys.stderr)
        else:
            sys.exit(1)


if __name__ == '__main__':
    main()
