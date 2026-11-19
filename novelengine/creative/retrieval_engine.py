"""Rank abstract literary techniques without reading or sending source passages."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Iterator, Mapping


_TOKEN = re.compile(r"[^\W_]+")
_COMMON = frozenset("va cua la cho voi cac nhung mot co khi de trong tren da dang thi ma duoc".split())
_CONTEXT_WEIGHTS = {
    "scene_type": 2, "narrative_goal": 3, "genre": 1,
    "character_state": 2, "tension": 1, "style_issue": 2,
}
_HINT_LIMITS = {"name": 96, "purpose": 200, "expected_effect": 200, "limitations": 200}


@dataclass(frozen=True, slots=True)
class SourceReference:
    title: str
    document_id: str = ""
    locator: str = ""


@dataclass(frozen=True, slots=True)
class Embedding:
    model: str
    values: tuple[float, ...]

    def __post_init__(self):
        object.__setattr__(self, "values", tuple(self.values))


@dataclass(frozen=True, slots=True)
class TechniqueNote:
    note_id: str
    name: str
    purpose: str = ""
    situations: tuple[str, ...] = ()
    expected_effect: str = ""
    limitations: str = ""
    source: SourceReference | None = None
    confidence: float | None = None
    scene_types: tuple[str, ...] = ()
    genres: tuple[str, ...] = ()
    character_states: tuple[str, ...] = ()
    tension_levels: tuple[str, ...] = ()
    style_issues: tuple[str, ...] = ()
    concept_id: str = ""
    embedding: Embedding | None = None
    reviewed: bool = False

    def __post_init__(self):
        if not self.note_id.strip() or not self.name.strip():
            raise ValueError("Ghi chú cần ID và tên kỹ thuật.")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("Độ tin cậy phải nằm trong [0, 1] hoặc là None.")
        if type(self.reviewed) is not bool:
            raise ValueError("reviewed phải là giá trị boolean.")
        if self.reviewed:
            for key, limit in _HINT_LIMITS.items():
                value = getattr(self, key)
                if len(value) > limit or len(value.splitlines()) > 1:
                    raise ValueError(f"Gợi ý {key} phải nằm trên một dòng, tối đa {limit} ký tự.")

    def writer_hint(self) -> dict[str, str] | None:
        """Send only concise fields explicitly reviewed for use by the writer."""
        if not self.reviewed:
            return None
        return {key: getattr(self, key).strip() for key in _HINT_LIMITS if getattr(self, key).strip()}


@dataclass(frozen=True, slots=True)
class RetrievalContext:
    scene_type: str = ""
    narrative_goal: str = ""
    genre: str = ""
    character_state: str = ""
    tension: str = ""
    style_issue: str = ""

    def query_text(self) -> str:
        return " ".join(value for key in _CONTEXT_WEIGHTS if (value := getattr(self, key).strip()))


@dataclass(frozen=True, slots=True)
class TechniqueMatch:
    note: TechniqueNote
    score: float
    context_rank: int | None
    semantic_rank: int | None
    fts_rank: int | None


def technique_from_v4_hit(hit: Mapping[str, object]) -> TechniqueNote | None:
    """Adapt an unreviewed legacy hit. Ignore source prose and generated examples."""
    note_id = hit.get("id")
    raw = hit.get("technique")
    if type(note_id) not in (int, str) or not str(note_id).strip() or not isinstance(raw, str):
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None

    def text(key):
        value = data.get(key)
        return value.strip() if isinstance(value, str) else ""

    name = text("technique")
    if not name:
        return None
    source = hit.get("source")
    when = text("when_to_use")
    return TechniqueNote(
        str(note_id).strip(), name, situations=(when,) if when else (), limitations=text("pitfall"),
        source=SourceReference(source.strip()) if isinstance(source, str) and source.strip() else None,
    )


def _words(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text.casefold().replace("đ", "d"))
    return _TOKEN.findall("".join(char for char in folded if not unicodedata.combining(char)))


def _terms(text: str) -> set[str]:
    words = [word for word in _words(text) if word not in _COMMON]
    return set(words) | {f"{first} {second}" for first, second in zip(words, words[1:])}


def _context_score(note: TechniqueNote, query: dict[str, set[str]]) -> float:
    fields = {
        "scene_type": (note.name, *note.scene_types, *note.situations),
        "narrative_goal": (note.name, note.purpose, note.expected_effect, *note.situations),
        "genre": note.genres,
        "character_state": (*note.character_states, *note.situations),
        "tension": note.tension_levels,
        "style_issue": (note.name, note.purpose, *note.style_issues),
    }
    return sum(
        _CONTEXT_WEIGHTS[key] * len(terms & _terms(" ".join(fields[key]))) / len(terms)
        for key, terms in query.items()
    )


def _unit_vector(embedding: Embedding) -> tuple[float, ...]:
    if not embedding.values or any(type(value) not in (int, float) for value in embedding.values):
        return ()
    try:
        vector = tuple(float(value) for value in embedding.values)
    except OverflowError:
        return ()
    if not all(math.isfinite(value) for value in vector):
        return ()
    scale = max(map(abs, vector))
    if not scale:
        return ()
    scaled = tuple(value / scale for value in vector)
    norm = math.sqrt(math.fsum(value * value for value in scaled))
    return tuple(value / norm for value in scaled)


def _ranks(scores: dict[str, float]) -> dict[str, int]:
    ranks = {}
    previous = None
    rank = 0
    for index, (note_id, score) in enumerate(sorted(scores.items(), key=lambda item: (-item[1], item[0])), 1):
        if score != previous:
            rank = index
        ranks[note_id] = rank
        previous = score
    return ranks


def _distinct(notes: Iterable[TechniqueNote]) -> Iterator[TechniqueNote]:
    selected = []
    for note in notes:
        name = tuple(_words(note.name))
        terms = _terms(" ".join((note.name, note.purpose, note.expected_effect)))
        for other_concept, other_name, other_terms in selected:
            if note.concept_id and other_concept:
                if note.concept_id == other_concept:
                    break
                continue
            overlap = len(terms & other_terms)
            if (name and name == other_name) or (overlap >= 4 and overlap >= 0.8 * len(terms | other_terms)):
                break
        else:
            selected.append((note.concept_id, name, terms))
            yield note


def writer_hints(notes: Iterable[TechniqueNote]) -> Iterator[dict[str, str]]:
    for note in _distinct(note for note in notes if note.reviewed):
        if hint := note.writer_hint():
            yield hint


def rank_techniques(
    notes: Iterable[TechniqueNote],
    context: RetrievalContext,
    *,
    query_embedding: Embedding | None = None,
    keyword_order: Iterable[str] = (),
    limit: int = 4,
) -> tuple[TechniqueMatch, ...]:
    """Fuse contextual, cosine and optional FTS ranks using reciprocal ranks."""
    if limit < 0:
        raise ValueError("limit phải không âm.")
    if not limit:
        return ()
    by_id = {}
    for note in notes:
        previous = by_id.setdefault(note.note_id, note)
        if previous != note:
            raise ValueError(f"Trùng ID ghi chú {note.note_id}.")

    query = {key: terms for key in _CONTEXT_WEIGHTS if (terms := _terms(getattr(context, key)))}
    lexical_scores = {}
    semantic_scores = {}
    query_vector = _unit_vector(query_embedding) if query_embedding and query_embedding.model.strip() else ()
    for note in by_id.values():
        if lexical := _context_score(note, query):
            lexical_scores[note.note_id] = lexical
        embedding = note.embedding
        if query_vector and embedding and embedding.model == query_embedding.model:
            vector = _unit_vector(embedding)
            if len(vector) == len(query_vector):
                cosine = math.fsum(first * second for first, second in zip(query_vector, vector))
                if cosine > 0:
                    semantic_scores[note.note_id] = cosine

    lexical_ranks = _ranks(lexical_scores)
    semantic_ranks = _ranks(semantic_scores)
    fts_ranks = {
        note_id: index
        for index, note_id in enumerate((key for key in dict.fromkeys(keyword_order) if key in by_id), 1)
    }
    fused = {}
    for note_id in lexical_ranks.keys() | semantic_ranks.keys() | fts_ranks.keys():
        lexical, semantic, fts = (ranks.get(note_id) for ranks in (lexical_ranks, semantic_ranks, fts_ranks))
        score = sum(weight / (60 + rank) for weight, rank in ((1, lexical), (1, semantic), (0.5, fts)) if rank is not None)
        fused[note_id] = TechniqueMatch(by_id[note_id], score, lexical, semantic, fts)
    ranked = sorted(fused.values(), key=lambda match: (
        -match.score, -(match.note.confidence if match.note.confidence is not None else -1), match.note.note_id,
    ))
    result = []
    for note in _distinct(match.note for match in ranked):
        result.append(fused[note.note_id])
        if len(result) == limit:
            break
    return tuple(result)
