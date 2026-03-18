from __future__ import annotations

import io
import os
import re
import threading
from typing import Dict

import pdfplumber
import pypdfium2
import requests
from bs4 import BeautifulSoup


MODEL_NAME = os.getenv("SUMMARIZER_MODEL_NAME", "facebook/bart-large-cnn")
MAX_INPUT_CHARS = 150000
MODEL_MAX_INPUT_TOKENS = 1024
CHUNK_INPUT_TOKENS = 880


_pipeline_lock = threading.Lock()
_tokenizer = None
_model = None
_device = None
_torch = None


def _transformers_enabled() -> bool:
    mode = os.getenv("USE_TRANSFORMERS", "auto").strip().lower()
    if mode in {"0", "false", "no", "off"}:
        return False
    if mode in {"1", "true", "yes", "on"}:
        return True
    return os.getenv("RENDER", "").strip() == ""


def get_summarizer_model_components():
    global _tokenizer, _model, _device, _torch

    if not _transformers_enabled():
        raise RuntimeError("Transformers summarizer disabled by configuration.")

    if _tokenizer is None or _model is None:
        with _pipeline_lock:
            if _tokenizer is None or _model is None:
                import torch
                from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

                _torch = torch
                _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
                _model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)

                if torch.backends.mps.is_available():
                    _device = torch.device("mps")
                elif torch.cuda.is_available():
                    _device = torch.device("cuda")
                else:
                    _device = torch.device("cpu")

                _model.to(_device)
                _model.eval()
    return _tokenizer, _model, _device


def get_summary_params(length_choice: str) -> Dict[str, float]:
    length_params = {
        "short": {
            "max_new_tokens": 48,
            "min_new_tokens": 14,
            "adaptive_ratio": 0.28,
            "length_penalty": 1.35,
        },
        "medium": {
            "max_new_tokens": 110,
            "min_new_tokens": 30,
            "adaptive_ratio": 0.48,
            "length_penalty": 1.1,
        },
        "detailed": {
            "max_new_tokens": 220,
            "min_new_tokens": 70,
            "adaptive_ratio": 0.82,
            "length_penalty": 0.92,
        },
    }
    return length_params.get(length_choice, length_params["medium"])


def normalize_text(raw_text: str) -> str:
    text = " ".join(raw_text.split())
    return text[:MAX_INPUT_CHARS]


def _get_token_count(tokenizer, text: str) -> int:
    return len(tokenizer(text, add_special_tokens=False)["input_ids"])


def _split_text_into_model_chunks(text: str, tokenizer, max_tokens: int = CHUNK_INPUT_TOKENS) -> list[str]:
    sentences = split_sentences(text)
    if not sentences:
        return [text] if text.strip() else []

    chunks = []
    current_sentences = []
    current_tokens = 0

    for sentence in sentences:
        sentence_tokens = _get_token_count(tokenizer, sentence)

        if sentence_tokens > max_tokens:
            words = sentence.split()
            partial_words = []
            partial_tokens = 0
            for word in words:
                word_tokens = _get_token_count(tokenizer, word)
                if partial_words and partial_tokens + word_tokens > max_tokens:
                    chunks.append(" ".join(partial_words))
                    partial_words = [word]
                    partial_tokens = word_tokens
                else:
                    partial_words.append(word)
                    partial_tokens += word_tokens
            if partial_words:
                chunks.append(" ".join(partial_words))
            continue

        if current_sentences and current_tokens + sentence_tokens > max_tokens:
            chunks.append(" ".join(current_sentences))
            current_sentences = [sentence]
            current_tokens = sentence_tokens
        else:
            current_sentences.append(sentence)
            current_tokens += sentence_tokens

    if current_sentences:
        chunks.append(" ".join(current_sentences))

    return [chunk for chunk in chunks if chunk.strip()]


def _generate_summary_ids(text: str, tokenizer, model, device, max_new_tokens: int, min_new_tokens: int):
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=MODEL_MAX_INPUT_TOKENS,
    )
    inputs = {key: value.to(device) for key, value in inputs.items()}

    input_token_count = int(inputs["input_ids"].shape[1])
    safe_max_new_tokens = min(max_new_tokens, max(16, int(input_token_count * 0.85)))
    safe_min_new_tokens = min(min_new_tokens, max(8, int(safe_max_new_tokens * 0.35)))
    if safe_min_new_tokens >= safe_max_new_tokens:
        safe_min_new_tokens = max(5, safe_max_new_tokens - 5)

    if _torch is None:
        raise RuntimeError("Torch is not initialized.")

    with _torch.no_grad():
        summary_ids = model.generate(
            **inputs,
            max_new_tokens=safe_max_new_tokens,
            min_new_tokens=safe_min_new_tokens,
            num_beams=4,
            no_repeat_ngram_size=3,
            early_stopping=True,
        )
    return summary_ids


def _summarize_long_text(text: str, tokenizer, model, device, params: Dict[str, float], length_choice: str) -> str:
    chunks = _split_text_into_model_chunks(text, tokenizer)
    if not chunks:
        return ""

    chunk_max_new_tokens = min(int(params["max_new_tokens"]), 90)
    chunk_min_new_tokens = min(int(params["min_new_tokens"]), 24)

    chunk_summaries = []
    for chunk in chunks:
        summary_ids = _generate_summary_ids(
            chunk,
            tokenizer,
            model,
            device,
            max_new_tokens=chunk_max_new_tokens,
            min_new_tokens=chunk_min_new_tokens,
        )
        chunk_summary = tokenizer.decode(summary_ids[0], skip_special_tokens=True).strip()
        if chunk_summary:
            chunk_summaries.append(chunk_summary)

    combined = " ".join(chunk_summaries).strip()
    if not combined:
        return ""

    rounds = 0
    while _get_token_count(tokenizer, combined) > CHUNK_INPUT_TOKENS and rounds < 2:
        reduced_chunks = _split_text_into_model_chunks(combined, tokenizer)
        reduced_summaries = []
        for reduced_chunk in reduced_chunks:
            reduced_ids = _generate_summary_ids(
                reduced_chunk,
                tokenizer,
                model,
                device,
                max_new_tokens=max(50, int(params["max_new_tokens"] * 0.75)),
                min_new_tokens=max(14, int(params["min_new_tokens"] * 0.5)),
            )
            reduced_text = tokenizer.decode(reduced_ids[0], skip_special_tokens=True).strip()
            if reduced_text:
                reduced_summaries.append(reduced_text)
        combined = " ".join(reduced_summaries).strip()
        rounds += 1

    if length_choice == "detailed":
        return trim_to_word_limit(combined, 220)

    final_ids = _generate_summary_ids(
        combined,
        tokenizer,
        model,
        device,
        max_new_tokens=int(params["max_new_tokens"]),
        min_new_tokens=int(params["min_new_tokens"]),
    )
    return tokenizer.decode(final_ids[0], skip_special_tokens=True).strip()


def summarize_text(raw_text: str, length_choice: str) -> str:
    text = normalize_text(raw_text)
    if not text:
        raise ValueError("Text cannot be empty.")

    if not _transformers_enabled():
        return format_summary_text(lightweight_summarize_text(text, length_choice))

    try:
        tokenizer, model, device = get_summarizer_model_components()
    except Exception:
        return format_summary_text(lightweight_summarize_text(text, length_choice))

    params = get_summary_params(length_choice)

    token_count = _get_token_count(tokenizer, text)
    if token_count <= CHUNK_INPUT_TOKENS:
        adaptive_cap = max(20, int(token_count * params["adaptive_ratio"]))
        safe_max_new_tokens = min(int(params["max_new_tokens"]), adaptive_cap)
        safe_min_new_tokens = min(int(params["min_new_tokens"]), max(8, int(safe_max_new_tokens * 0.35)))
        if safe_min_new_tokens >= safe_max_new_tokens:
            safe_min_new_tokens = max(5, safe_max_new_tokens - 5)

        summary_ids = _generate_summary_ids(
            text,
            tokenizer,
            model,
            device,
            max_new_tokens=safe_max_new_tokens,
            min_new_tokens=safe_min_new_tokens,
        )
        raw_summary = tokenizer.decode(summary_ids[0], skip_special_tokens=True).strip()
    else:
        raw_summary = _summarize_long_text(text, tokenizer, model, device, params, length_choice)

    adjusted_summary = adjust_summary_by_length(raw_summary, length_choice)
    bounded_summary = enforce_summary_word_range(
        summary_text=adjusted_summary,
        source_text=text,
        length_choice=length_choice,
        tokenizer=tokenizer,
        model=model,
        device=device,
    )
    return format_summary_text(bounded_summary)


def lightweight_summarize_text(raw_text: str, length_choice: str) -> str:
    source_text = normalize_text(raw_text)
    sentences = split_sentences(source_text)
    if not sentences:
        return ""

    source_word_count = len(source_text.split())
    targets = get_length_word_targets(length_choice, source_word_count)
    max_words = targets["max"]

    selected = []
    word_total = 0
    for sentence in sentences:
        words = sentence.split()
        if not words:
            continue

        remaining = max_words - word_total
        if remaining <= 0:
            break

        if len(words) <= remaining:
            selected.append(sentence.strip())
            word_total += len(words)
        else:
            selected.append(" ".join(words[:remaining]).strip())
            word_total += remaining
            break

    summary = " ".join(part for part in selected if part).strip()
    return trim_to_word_limit(summary, max_words)


def summarize_with_points(raw_text: str, length_choice: str) -> Dict[str, object]:
    summary = summarize_text(raw_text, length_choice)
    key_points = extract_key_points(summary, length_choice)
    return {
        "summary": summary,
        "key_points": key_points,
    }


def split_sentences(text: str) -> list[str]:
    normalized = " ".join((text or "").split())
    if not normalized:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", normalized) if part.strip()]


def trim_to_word_limit(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    trimmed = " ".join(words[:max_words]).strip()
    if trimmed and trimmed[-1] not in ".!?":
        trimmed += "."
    return trimmed


def adjust_summary_by_length(summary_text: str, length_choice: str) -> str:
    summary_sentences = split_sentences(summary_text)

    if not summary_sentences:
        return ""

    sentence_limit_map = {
        "short": 2,
        "medium": 4,
        "detailed": 8,
    }
    word_limit_map = {
        "short": 60,
        "medium": 130,
        "detailed": 220,
    }

    chosen_sentence_limit = sentence_limit_map.get(length_choice, 4)
    chosen_word_limit = word_limit_map.get(length_choice, 130)
    selected_text = " ".join(summary_sentences[:chosen_sentence_limit])
    return trim_to_word_limit(selected_text, chosen_word_limit)


def get_length_word_targets(length_choice: str, source_word_count: int) -> Dict[str, int]:
    mode_config = {
        "short": {"min_ratio": 0.28, "max_ratio": 0.42, "abs_max": 50, "abs_min": 14},
        "medium": {"min_ratio": 0.46, "max_ratio": 0.62, "abs_max": 95, "abs_min": 28},
        "detailed": {"min_ratio": 0.68, "max_ratio": 0.84, "abs_max": 160, "abs_min": 45},
    }
    cfg = mode_config.get(length_choice, mode_config["medium"])

    if source_word_count <= 25:
        min_allowed = max(8, int(source_word_count * 0.45))
        max_allowed = max(min_allowed + 4, int(source_word_count * 0.8))
        return {"min": min_allowed, "max": max_allowed}

    max_allowed = min(cfg["abs_max"], max(cfg["abs_min"], int(source_word_count * cfg["max_ratio"])))
    min_allowed = min(max_allowed, max(cfg["abs_min"], int(source_word_count * cfg["min_ratio"])))

    if min_allowed >= max_allowed:
        min_allowed = max(10, max_allowed - 8)

    return {"min": min_allowed, "max": max_allowed}


def _canonical_sentence(sentence: str) -> str:
    return re.sub(r"\W+", " ", sentence.lower()).strip()


def merge_unique_sentences(*texts: str) -> str:
    merged_sentences = []
    seen = set()

    for text in texts:
        for sentence in split_sentences(text):
            stripped = sentence.strip()
            canonical = _canonical_sentence(stripped)
            if not canonical:
                continue

            is_duplicate = False
            for existing in seen:
                if canonical == existing or canonical in existing or existing in canonical:
                    is_duplicate = True
                    break
            if is_duplicate:
                continue

            seen.add(canonical)
            merged_sentences.append(stripped)

    return " ".join(merged_sentences)


def build_extractive_extension(source_text: str, existing_summary: str, max_words_to_add: int) -> str:
    source_sentences = split_sentences(source_text)
    existing_canonicals = {_canonical_sentence(sentence) for sentence in split_sentences(existing_summary)}

    selected_sentences = []
    selected_words = 0
    for sentence in source_sentences:
        cleaned = sentence.strip()
        if len(cleaned.split()) < 6:
            continue

        canonical = _canonical_sentence(cleaned)
        if not canonical:
            continue

        has_overlap = False
        for existing in existing_canonicals:
            if canonical == existing or canonical in existing or existing in canonical:
                has_overlap = True
                break
        if has_overlap:
            continue

        selected_sentences.append(cleaned)
        selected_words += len(cleaned.split())
        existing_canonicals.add(canonical)

        if selected_words >= max_words_to_add:
            break

    return " ".join(selected_sentences)


def enforce_summary_word_range(
    summary_text: str,
    source_text: str,
    length_choice: str,
    tokenizer,
    model,
    device,
) -> str:
    summary = " ".join(summary_text.split()).strip()
    if not summary:
        return summary

    source_word_count = len(source_text.split())
    targets = get_length_word_targets(length_choice, source_word_count)
    min_words = targets["min"]
    max_words = targets["max"]

    current_words = len(summary.split())
    if current_words > max_words:
        return trim_to_word_limit(summary, max_words)

    if current_words >= min_words:
        return summary

    expansion_ids = _generate_summary_ids(
        source_text,
        tokenizer,
        model,
        device,
        max_new_tokens=min(260, max_words + 60),
        min_new_tokens=max(min_words, int(min_words * 1.15)),
    )
    expansion_text = tokenizer.decode(expansion_ids[0], skip_special_tokens=True).strip()

    expanded_summary = merge_unique_sentences(summary, expansion_text)

    expanded_words = len(expanded_summary.split())
    if expanded_words < min_words:
        needed_words = min_words - expanded_words
        extension = build_extractive_extension(source_text, expanded_summary, needed_words + 12)
        if extension:
            expanded_summary = merge_unique_sentences(expanded_summary, extension)

    if len(expanded_summary.split()) > max_words:
        expanded_summary = trim_to_word_limit(expanded_summary, max_words)

    return expanded_summary


def extract_key_points(summary_text: str, length_choice: str) -> list[str]:
    sentences = split_sentences(summary_text)
    max_points_map = {
        "short": 3,
        "medium": 5,
        "detailed": 7,
    }
    max_points = max_points_map.get(length_choice, 5)

    key_points = []
    seen = set()
    for sentence in sentences:
        normalized = sentence.strip().rstrip(".?!")
        if len(normalized.split()) < 5:
            continue

        canonical = normalized.lower()
        if canonical in seen:
            continue

        point = normalized[0].upper() + normalized[1:] if len(normalized) > 1 else normalized.upper()
        key_points.append(point)
        seen.add(canonical)

        if len(key_points) >= max_points:
            break

    if not key_points and summary_text.strip():
        fallback = summary_text.strip().rstrip(".?!")
        if fallback:
            key_points = [fallback[0].upper() + fallback[1:] if len(fallback) > 1 else fallback.upper()]

    return key_points


def format_summary_text(raw_summary: str) -> str:
    text = " ".join((raw_summary or "").split())
    if not text:
        return ""

    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    cleaned_sentences = []
    for sentence in sentences:
        normalized_sentence = sentence[0].upper() + sentence[1:] if len(sentence) > 1 else sentence.upper()
        if normalized_sentence[-1] not in ".!?":
            normalized_sentence = f"{normalized_sentence}."
        cleaned_sentences.append(normalized_sentence)

    if not cleaned_sentences:
        return text

    paragraph_size = 2
    paragraphs = [
        " ".join(cleaned_sentences[index:index + paragraph_size])
        for index in range(0, len(cleaned_sentences), paragraph_size)
    ]
    return "\n\n".join(paragraphs)


def _extract_text_with_pdfplumber(pdf_bytes: bytes) -> str:
    full_text = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            candidates = [
                page.extract_text() or "",
                page.extract_text(layout=True) or "",
            ]

            if not any(candidate.strip() for candidate in candidates):
                words = page.extract_words(use_text_flow=True) or []
                if words:
                    candidates.append(" ".join(word.get("text", "") for word in words if word.get("text")))

            page_text = max(candidates, key=lambda value: len(value.strip()), default="").strip()
            if page_text:
                full_text.append(page_text)

    return normalize_text("\n".join(full_text))


def _extract_text_with_pdfium(pdf_bytes: bytes) -> str:
    full_text = []
    document = pypdfium2.PdfDocument(io.BytesIO(pdf_bytes))
    try:
        for page_index in range(len(document)):
            page = document.get_page(page_index)
            text_page = page.get_textpage()
            try:
                char_count = text_page.count_chars()
                page_text = text_page.get_text_range(0, char_count) if char_count else ""
                if not page_text.strip():
                    page_text = text_page.get_text_bounded()
                if page_text.strip():
                    full_text.append(page_text)
            finally:
                text_page.close()
                page.close()
    finally:
        document.close()

    return normalize_text("\n".join(full_text))


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    primary = _extract_text_with_pdfplumber(pdf_bytes)
    if primary:
        return primary

    fallback = _extract_text_with_pdfium(pdf_bytes)
    if fallback:
        return fallback

    return ""


def extract_text_from_url(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    return normalize_text(text)