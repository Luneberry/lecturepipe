# LecturePipe

YouTube 강의 영상 → 자막 추출 → Gemini 한국어 번역 → 시각 캡처 → Obsidian vault 마크다운 저장 파이프라인.

## 주요 기능

- **자막 추출**: youtube-transcript-api (한국어 우선, 영어 fallback)
- **번역**: Gemini 2.0 Flash, 청크 분할 (2000자) 후 한국어 정리
- **요약**: 5분 단위 섹션 자동 분할 + 핵심 정리
- **시각 캡처**: 슬라이드 변경 자동 감지 (PySceneDetect, threshold 0.4) + 이미지 유사도 92% 이상은 중복 제거
- **배치**: URL 목록 파일 일괄 처리, URL 간 2초 지연

## 설치

```bash
git clone https://github.com/Luneberry/lecturepipe.git
cd lecturepipe
pip install -r requirements.txt
export GEMINI_API_KEY=your_key
```

`config.yaml` 의 `vault.path` 가 기본 `~/Desktop/Vault` 로 잡혀 있음. 다른 경로면 수정 또는 `--vault` 옵션.

## 사용

```bash
# 단일 영상
python lecturepipe.py https://www.youtube.com/watch?v=...

# 배치
python lecturepipe.py --batch urls.txt

# 번역 끄고 요약만
python lecturepipe.py --no-translate https://...

# 시각 캡처 끄기
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
    frame-00:01:23.jpg
    frame-00:05:42.jpg
```

마크다운에는 자막 한국어 번역 + 5분 단위 섹션 요약 + 슬라이드 캡처 임베드.

## 라이선스

MIT
