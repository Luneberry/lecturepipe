# LecturePipe

YouTube 강의 영상 → 자막 추출 → Gemini 한국어 번역 → 시각 캡처 → Obsidian vault 마크다운 저장 파이프라인.

> 🎓 60분짜리 영어 강의 한 편을 5분 단위로 정리된 한국어 마크다운 + 슬라이드 캡처로 받아 vault 에 자동 파일링.

## 주요 기능

- **자막 추출**: youtube-transcript-api (한국어 우선, 영어 fallback)
- **번역**: Gemini 2.0 Flash, 청크 분할 (2000자) 후 한국어 정리
- **요약**: 5분 단위 섹션 자동 분할 + 핵심 정리
- **시각 캡처**: 슬라이드 변경 자동 감지 (PySceneDetect, threshold 0.4) + 이미지 유사도 92% 이상은 중복 제거
- **배치**: URL 목록 파일 일괄 처리, URL 간 2초 지연

## Quick start

```bash
git clone https://github.com/Luneberry/lecturepipe.git
cd lecturepipe
pip install -r requirements.txt
brew install ffmpeg                       # macOS · system dep
export GEMINI_API_KEY=your_key            # https://aistudio.google.com/apikey

# config.yaml 의 vault.path 를 본인 Obsidian 폴더로 수정 (기본 ~/Desktop/Vault)

# 첫 영상 처리
python lecturepipe.py https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

처리는 영상 길이의 ~10–15% 정도 걸려요 (60분 영상 → 7–10분).

## 사용

```bash
# 단일 영상
python lecturepipe.py https://www.youtube.com/watch?v=...

# 배치
python lecturepipe.py --batch urls.txt

# 번역 끄고 요약만
python lecturepipe.py --no-translate https://...

# 시각 캡처 끄기 (자막+번역만 빠르게)
python lecturepipe.py --no-visual https://...

# 터미널 출력만 (vault 저장 안 함)
python lecturepipe.py --terminal-only https://...

# 고아 이미지 정리
python lecturepipe.py --cleanup
```

## 출력 구조

```
<vault>/learning/Lectures/
  2026-04-28-rag-tutorial.md
<vault>/learning/Lectures/assets/
  2026-04-28-rag-tutorial/
    frame-00-01-23.jpg
    frame-00-05-42.jpg
```

마크다운 내부 (실제 출력 예시):

```markdown
---
source: https://www.youtube.com/watch?v=...
title: "Building RAG with LlamaIndex"
original_language: en
output_language: ko
date: 2026-04-28
tags:
  - lecture
  - youtube
---

## 0–5분
RAG 기본 구조 — retriever 가 vector DB 에서 top-k 청크를
가져와 LLM 에 주입하는 패턴을 다룹니다 ...

![슬라이드](assets/2026-04-28-rag-tutorial/frame-00-01-23.jpg)

## 5–10분
청킹 전략 — 고정 크기 vs 의미 단위 ...
```

## 시스템 의존성

- `ffmpeg` (시각 캡처) — `brew install ffmpeg`
- `yt-dlp` (스트림 URL 추출) — pip 로 설치되지만, 시스템에서 직접 사용하려면 `brew install yt-dlp` 권장

## Troubleshooting

| 증상 | 원인 / 해결 |
|---|---|
| `ModuleNotFoundError: google` | `pip install -r requirements.txt` 다시 (구버전 대비 google-genai 추가됨) |
| `ffmpeg: command not found` | `brew install ffmpeg` |
| `자막을 찾을 수 없습니다` | 영상에 한국어/영어 자막 모두 없는 경우. `--no-translate --no-visual` 로 fallback 처리 가능 |
| `429 Too Many Requests` | Gemini rate limit. config.yaml `batch.delay_seconds` 를 5+ 로 |
| 시각 캡처가 너무 많음 | config.yaml `visual.scene_threshold` 를 0.4 → 0.5 (덜 민감) |
| `--vault` 옵션 사용 시 `~` 가 안 풀림 | shell 이 expand 한 절대경로 넘겨주거나, config.yaml 직접 수정 |

## 라이선스

MIT — `LICENSE` 참조.
