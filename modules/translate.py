"""F2: 자막 요약·번역 모듈 — Gemini LLM 기반

mode:
  'both'      — 번역 + 요약 (기본값. 외국어→한국어 번역·요약, 한국어→요약)
  'translate' — 번역만 (외국어→한국어 직역)
  'summary'   — 요약만 (원문 언어 기반 한국어 요약, 한국어면 한국어 요약)
"""

import os
import sys
import time
from google import genai
from modules.transcript import TranscriptEntry


def should_translate(language: str) -> bool:
    """한국어면 번역 불필요 (but 요약은 필요할 수 있음)."""
    return not language.startswith('ko')


def get_gemini_client(config: dict) -> genai.Client:
    """Gemini API 클라이언트를 생성한다."""
    api_key = config.get('translation', {}).get('gemini_api_key') or os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise RuntimeError(
            "Gemini API 키가 필요합니다. config.yaml의 translation.gemini_api_key 또는 "
            "환경변수 GEMINI_API_KEY를 설정하세요."
        )
    return genai.Client(api_key=api_key)


def group_into_sections(entries: list[TranscriptEntry], interval_minutes: int = 5) -> list[list[TranscriptEntry]]:
    """자막 항목들을 시간 구간별로 묶는다."""
    if not entries:
        return []

    interval_sec = interval_minutes * 60
    sections = []
    current = []
    current_section_idx = -1

    for entry in entries:
        section_idx = int(entry.start // interval_sec)
        if section_idx != current_section_idx and current:
            sections.append(current)
            current = []
        current_section_idx = section_idx
        current.append(entry)

    if current:
        sections.append(current)
    return sections


def format_section_text(entries: list[TranscriptEntry]) -> str:
    """섹션 내 자막을 하나의 텍스트로 합친다."""
    return ' '.join(e.text for e in entries)


def split_into_chunks(entries: list[TranscriptEntry], chunk_size: int) -> list[list[TranscriptEntry]]:
    """섹션 내 entries 를 합산 길이가 chunk_size 글자 이하인 그룹으로 분할한다."""
    if chunk_size <= 0:
        return [entries] if entries else []
    chunks: list[list[TranscriptEntry]] = []
    current: list[TranscriptEntry] = []
    current_size = 0
    for entry in entries:
        text_len = len(entry.text) + 1
        if current and current_size + text_len > chunk_size:
            chunks.append(current)
            current = []
            current_size = 0
        current.append(entry)
        current_size += text_len
    if current:
        chunks.append(current)
    return chunks


PROMPTS = {
    # 번역+요약: 외국어
    'both_foreign': """다음은 {source_lang} 강의 자막의 한 단락입니다. 아래 규칙에 따라 한국어로 번역·정리해주세요.

## 규칙
- **내용을 절대 누락하지 마세요.** 강의에서 언급된 모든 개념, 예시, 설명을 빠짐없이 포함하세요.
- 개념적인 설명이 있다면, 중학생에게 설명하듯이 쉽고 자세하게 풀어서 적으세요.
- 불필요한 반복, 말더듬, 간투사("uh", "um", "so basically" 등)는 제거하세요.
- 문어체로 깔끔하게 정리하세요.
- 전문 용어는 영어 원문을 병기하세요 (예: 역전파(Backpropagation))
- 여러 화자가 대화하는 내용이라면, 화자를 구분해서 **화자A:**, **화자B:** 등으로 표시하세요. 이름이 언급되면 이름을 사용하세요.

## 자막
{text}""",

    # 번역+요약: 한국어 (=요약만)
    'both_korean': """다음은 강의 자막의 한 단락입니다. 아래 규칙에 따라 한국어로 정리해주세요.

## 규칙
- **내용을 절대 누락하지 마세요.** 강의에서 언급된 모든 개념, 예시, 설명을 빠짐없이 포함하세요.
- 개념적인 설명이 있다면, 중학생에게 설명하듯이 쉽고 자세하게 풀어서 적으세요.
- 불필요한 반복, 말더듬, 간투사("어", "음", "그래서 이제" 등)는 제거하세요.
- 문어체로 깔끔하게 정리하세요.
- 원문의 전문 용어는 그대로 유지하세요.
- 여러 화자가 대화하는 내용이라면, 화자를 구분해서 **화자A:**, **화자B:** 등으로 표시하세요. 이름이 언급되면 이름을 사용하세요.

## 자막
{text}""",

    # 번역만 (직역)
    'translate': """다음은 {source_lang} 강의 자막의 한 단락입니다. 자연스러운 한국어로 번역해주세요.

## 규칙
- 원문의 의미를 충실히 번역하세요. 내용을 생략하거나 요약하지 마세요.
- 전문 용어는 영어 원문을 병기하세요 (예: 역전파(Backpropagation))
- 자연스러운 한국어 문장으로 작성하세요.
- 여러 화자가 대화하는 내용이라면, 화자를 구분해서 **화자A:**, **화자B:** 등으로 표시하세요. 이름이 언급되면 이름을 사용하세요.

## 자막
{text}""",

    # 요약만 (외국어 원문 기반)
    'summary_foreign': """다음은 {source_lang} 강의 자막의 한 단락입니다. 아래 규칙에 따라 한국어로 요약해주세요.

## 규칙
- **내용을 절대 누락하지 마세요.** 강의에서 언급된 모든 개념, 예시, 설명을 빠짐없이 포함하세요.
- 개념적인 설명이 있다면, 중학생에게 설명하듯이 쉽고 자세하게 풀어서 적으세요.
- 불필요한 반복, 말더듬, 간투사는 제거하세요.
- 문어체로 깔끔하게 정리하세요.
- 전문 용어는 영어 원문을 병기하세요 (예: 역전파(Backpropagation))
- 여러 화자가 대화하는 내용이라면, 화자를 구분해서 **화자A:**, **화자B:** 등으로 표시하세요. 이름이 언급되면 이름을 사용하세요.

## 자막
{text}""",

    # 요약만 (한국어)
    'summary_korean': """다음은 강의 자막의 한 단락입니다. 아래 규칙에 따라 한국어로 정리해주세요.

## 규칙
- **내용을 절대 누락하지 마세요.** 강의에서 언급된 모든 개념, 예시, 설명을 빠짐없이 포함하세요.
- 개념적인 설명이 있다면, 중학생에게 설명하듯이 쉽고 자세하게 풀어서 적으세요.
- 불필요한 반복, 말더듬, 간투사("어", "음", "그래서 이제" 등)는 제거하세요.
- 문어체로 깔끔하게 정리하세요.
- 원문의 전문 용어는 그대로 유지하세요.
- 여러 화자가 대화하는 내용이라면, 화자를 구분해서 **화자A:**, **화자B:** 등으로 표시하세요. 이름이 언급되면 이름을 사용하세요.

## 자막
{text}""",
}


def get_prompt(mode: str, is_korean: bool, source_lang: str, text: str) -> str:
    """모드와 언어에 맞는 프롬프트를 반환한다."""
    if mode == 'translate':
        key = 'translate'
    elif mode == 'summary':
        key = 'summary_korean' if is_korean else 'summary_foreign'
    else:  # 'both'
        key = 'both_korean' if is_korean else 'both_foreign'

    return PROMPTS[key].format(source_lang=source_lang, text=text)


def call_gemini(client: genai.Client, prompt: str, model: str) -> str:
    """Gemini API를 호출한다."""
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text.strip()


def translate_entries(entries: list[TranscriptEntry], source_lang: str,
                      target_lang: str = 'ko', chunk_size: int = 4000,
                      mode: str = 'both', config: dict = None) -> list[TranscriptEntry]:
    """자막을 단락별로 LLM 처리한다.

    mode: 'both' (번역+요약), 'translate' (번역만), 'summary' (요약만)
    """
    if config is None:
        config = {}

    translation_config = config.get('translation', {})
    model = translation_config.get('gemini_model', 'gemini-2.0-flash')
    effective_chunk_size = translation_config.get('chunk_size', chunk_size)
    interval = config.get('output', {}).get('section_interval_minutes', 5)
    is_korean = source_lang.startswith('ko')

    client = get_gemini_client(config)
    sections = group_into_sections(entries, interval)
    results = []
    total = len(sections)

    mode_label = {'both': '번역·요약', 'translate': '번역', 'summary': '요약'}
    label = mode_label.get(mode, mode)

    for i, section in enumerate(sections, 1):
        start = section[0].start
        duration = (section[-1].start + section[-1].duration) - start

        minutes_start = int(start // 60)
        minutes_end = int((start + duration) // 60)
        chunks = split_into_chunks(section, effective_chunk_size)
        chunk_count = len(chunks)
        chunk_suffix = f" · {chunk_count}청크" if chunk_count > 1 else ""
        print(f"  {label} 중... [{i}/{total}] ({minutes_start}분~{minutes_end}분{chunk_suffix})", file=sys.stderr)

        chunk_outputs = []
        max_retries = 3
        for c_idx, chunk in enumerate(chunks, 1):
            chunk_text = format_section_text(chunk)
            prompt = get_prompt(mode, is_korean, source_lang, chunk_text)

            chunk_result = None
            for attempt in range(1, max_retries + 1):
                try:
                    chunk_result = call_gemini(client, prompt, model)
                    break
                except Exception as e:
                    print(f"\n  ⚠ {label} 실패 (섹션 {i}, 청크 {c_idx}/{chunk_count}, 시도 {attempt}/{max_retries}): {e}", file=sys.stderr)
                    if attempt < max_retries:
                        wait = 2 ** attempt
                        print(f"  {wait}초 후 재시도...", file=sys.stderr)
                        time.sleep(wait)

            if chunk_result:
                chunk_outputs.append(chunk_result)
            else:
                print(f"  ✗ 섹션 {i} 청크 {c_idx} 최종 실패, 원문 유지", file=sys.stderr)
                chunk_outputs.append(chunk_text)

            if c_idx < chunk_count:
                time.sleep(0.5)

        combined = "\n\n".join(chunk_outputs)
        results.append(TranscriptEntry(text=combined, start=start, duration=duration))

        # Rate limit 방지
        if i < total:
            time.sleep(1)

    print("", file=sys.stderr)
    return results
