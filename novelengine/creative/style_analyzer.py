"""Evidence-based editing suggestions with intentionally conservative confidence."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import chain
from statistics import pstdev
from typing import Iterable, Iterator, Literal, Mapping


_WORD = re.compile(r"[^\W\d_]+")
_PARAGRAPH_BREAK = re.compile(r"(?:\r\n|\r(?!\n)|\n)(?:[^\S\r\n]*(?:\r\n|\r(?!\n)|\n))+")
_SENTENCE = re.compile(r"[^.!?…\r\n]+[.!?…]*")
_DIALOGUE = re.compile(r'^[^\S\r\n]*[—–-][^\S\r\n]+[^\r\n]+|“[^”\r\n]+”|«[^»\r\n]+»|"[^"\r\n]+"', re.M)
_COMMON = frozenset(
    "anh cô em chị ông bà cậu họ người nó tôi ta mình một và với của có đã đang sẽ là "
    "được thì mà khi để từ ở trong trên không những các lại đó này rất cũng vẫn như đi về".split()
)
_EMOTION = re.compile(
    r"\bcảm thấy\s+(?:(?:rất|vô cùng|hết sức|thật sự)\s+)?"
    r"(?:buồn(?: bã)?|sợ hãi|tức giận|đau khổ|hạnh phúc|lo lắng|bất an|thất vọng|cô đơn|xấu hổ)\b"
)
_MODIFIER = re.compile(
    r"\b(?:vô cùng|cực kỳ|hết sức|thật sự|thực sự|quá đỗi|hoàn toàn|tuyệt đối|rất|"
    r"lộng lẫy|tuyệt đẹp|kinh khủng|khủng khiếp|ghê gớm)\b"
)
_CLICHE = re.compile(
    r"\b(?:mọi thứ (?:đều )?đã thay đổi|không gì còn như trước|"
    r"không có gì còn như trước|đó (?:chỉ )?là khởi đầu của mọi chuyện|"
    r"mọi chuyện chỉ mới bắt đầu)\b"
)


@dataclass(frozen=True, slots=True)
class TextLocation:
    paragraph: int
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class StyleFinding:
    location: TextLocation
    kind: str
    evidence: str
    suggestion: str
    priority: int
    confidence: Literal["low", "medium"]


def _normalized(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def _paragraphs(text: str) -> Iterator[tuple[TextLocation, str]]:
    start = 0
    number = 0
    breaks = (match.span() for match in _PARAGRAPH_BREAK.finditer(text))
    for end, next_start in chain(breaks, ((len(text), len(text)),)):
        chunk = text[start:end]
        if block := chunk.strip():
            number += 1
            left = start + len(chunk) - len(chunk.lstrip())
            yield TextLocation(number, left, left + len(block)), block
        start = next_start


def _repeated_phrase(sentences: list[tuple[str, list[str]]]) -> tuple[str, int] | None:
    for width in (4, 3):
        counts: Counter[tuple[str, ...]] = Counter()
        for _, words in sentences:
            last_end: dict[tuple[str, ...], int] = {}
            for start in range(len(words) - width + 1):
                phrase = tuple(words[start:start + width])
                if start >= last_end.get(phrase, 0) and any(word not in _COMMON for word in phrase):
                    counts[phrase] += 1
                    last_end[phrase] = start + width
        if counts:
            phrase, count = counts.most_common(1)[0]
            if count >= 3:
                return " ".join(phrase), count
    return None


def _prose_findings(
    location: TextLocation,
    prose: str,
    restricted_words: tuple[tuple[str, ...], ...],
    restricted_openers: tuple[tuple[str, ...], ...],
) -> Iterator[StyleFinding]:
    normalized = _normalized(prose)
    sentences = [(match.group(), _WORD.findall(match.group())) for match in _SENTENCE.finditer(normalized)]
    sentences = [(sentence, words) for sentence, words in sentences if words]
    words = [word for _, sentence_words in sentences for word in sentence_words]
    if not words:
        return

    if repeated := _repeated_phrase(sentences):
        phrase, count = repeated
        yield StyleFinding(location, "phrase_repetition", f"«{phrase}» lặp {count} lần.",
                           "Giữ lại lần lặp có dụng ý và xem có thể lược bớt những lần còn lại.", 2, "medium")
    counts = Counter(word for word in words if word not in _COMMON and len(word) > 1)
    if counts:
        word, count = counts.most_common(1)[0]
        if count >= 3 and count * 10 >= len(words):
            yield StyleFinding(location, "word_repetition", f"«{word}» xuất hiện {count}/{len(words)} lượt từ.",
                               "Xem lại các chỗ lặp gần nhau. Có thể lược danh từ nếu ngữ cảnh đã rõ.", 3, "medium")

    openers = Counter(tuple(parts[:3]) for _, parts in sentences if len(parts) >= 4)
    if openers:
        opening, count = openers.most_common(1)[0]
        if count >= 3:
            yield StyleFinding(location, "repeated_opening", f"{count} câu mở bằng «{' '.join(opening)}».",
                               "Thử thay điểm đặt thông tin ở một câu hoặc nối hai câu cùng chủ thể.", 2, "medium")

    if match := _EMOTION.search(normalized):
        yield StyleFinding(location, "direct_emotion", match.group(),
                           "Cân nhắc để một cử chỉ hoặc lựa chọn bộc lộ cảm xúc tại chỗ này.", 3, "low")
    modifiers = _MODIFIER.findall(normalized)
    if len(modifiers) >= 3 and len(modifiers) * 14 >= len(words):
        yield StyleFinding(location, "modifier_density",
                           f"{len(modifiers)} từ hoặc cụm nhấn mạnh, gồm «{'», «'.join(modifiers[:4])}».",
                           "Thử bỏ từ chỉ mức độ ở chỗ động từ hoặc chi tiết cụ thể đã đủ rõ.", 3, "low")
    if match := _CLICHE.search(sentences[-1][0]):
        yield StyleFinding(location, "stock_ending", match.group(),
                           "Thử kết đoạn bằng một chi tiết hoặc hệ quả cụ thể của cảnh.", 2, "low")

    lengths = [len(parts) for sentence, parts in sentences if sentence.endswith((".", "!", "?", "…"))]
    if len(lengths) >= 5 and min(lengths) >= 4 and pstdev(lengths) <= 0.10 * sum(lengths) / len(lengths):
        yield StyleFinding(location, "uniform_rhythm",
                           f"{len(lengths)} câu có độ dài gần nhau ({min(lengths)}–{max(lengths)} lượt từ).",
                           "Thử đổi độ dài ở một nhịp chuyển hoặc một câu cần điểm rơi.", 3, "low")

    for phrase in restricted_words:
        length = len(phrase)
        if any(tuple(parts[index:index + length]) == phrase
               for _, parts in sentences for index in range(len(parts) - length + 1)):
            yield StyleFinding(location, "restricted_word", " ".join(phrase),
                               "Đối chiếu cụm này với mục từ nên hạn chế trong hồ sơ giọng văn.", 1, "medium")
            break
    for phrase in restricted_openers:
        if any(tuple(parts[:len(phrase)]) == phrase for _, parts in sentences):
            yield StyleFinding(location, "restricted_opening", " ".join(phrase),
                               "Xem lại cách mở câu theo hồ sơ giọng văn.", 1, "medium")
            break


def analyze_style(
    text: str,
    *,
    avoid_words: Iterable[str] = (),
    avoid_structures: Iterable[str] = (),
    dialogue_speakers: Mapping[int, str] | None = None,
) -> tuple[StyleFinding, ...]:
    """Return inspectable hints. Paragraph numbers are one-based, offsets are half-open."""
    restricted_words = tuple(parts for term in avoid_words if (parts := tuple(_WORD.findall(_normalized(term)))))
    restricted_openers = tuple(parts for term in avoid_structures if (parts := tuple(_WORD.findall(_normalized(term)))))
    speakers = dialogue_speakers or {}
    findings: list[StyleFinding] = []
    turns: dict[tuple[str, ...], list[TextLocation]] = defaultdict(list)
    for location, block in _paragraphs(text):
        for match in _DIALOGUE.finditer(block):
            words = _WORD.findall(_normalized(match.group()))
            if len(words) >= 4:
                turns[tuple(words[:4])].append(location)
        prose = _DIALOGUE.sub(lambda match: " " * len(match.group()), block)
        findings.extend(_prose_findings(location, prose, restricted_words, restricted_openers))

    for opening, locations in turns.items():
        paragraphs = {location.paragraph for location in locations}
        distinct_speakers = {speakers[number] for number in paragraphs if speakers.get(number)}
        if len(distinct_speakers) >= 2 or len(paragraphs) >= 3:
            basis = (f"{len(distinct_speakers)} người nói đã xác định"
                     if len(distinct_speakers) >= 2 else f"{len(paragraphs)} đoạn thoại")
            findings.append(StyleFinding(
                locations[-1], "similar_dialogue", f"«{' '.join(opening)}» mở lời ở {basis}.",
                "Đối chiếu nhịp và cách chọn từ của từng người. Giữ lặp lại nếu đó là dụng ý.", 3, "low",
            ))
    return tuple(sorted(findings, key=lambda item: (item.location.start, item.kind)))
