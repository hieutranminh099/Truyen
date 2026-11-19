"""Pure adapters from V4.1 backend inputs to the Creative modules."""

from __future__ import annotations

import json
import unicodedata
from dataclasses import asdict, dataclass, field, replace
from sqlite3 import Row
from typing import Callable, Iterable, Mapping

from .memory_rules import MemoryEvent, MemoryRecord, StoryPosition
from .memory_storage import MemoryStorageError, StoredMemory
from .outline_contract import (
    DEFAULT_SCENE_PACKET_BUDGET, OutlineContract, OutlineValidation, ScenePacket, build_scene_packet,
)
from .retrieval_engine import (
    Embedding, RetrievalContext, TechniqueMatch, TechniqueNote, rank_techniques, technique_from_v4_hit,
)
from .voice_engine import VoiceBible, plan_revision


def _label(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


@dataclass(frozen=True, slots=True)
class SceneVoice:
    guidance: str
    _profile: VoiceBible | None = field(default=None, repr=False)

    def revision_payload(
        self,
        draft: str,
        *,
        dialogue_speakers: Mapping[int, str] | None = None,
        max_items: int = 8,
    ) -> list[dict]:
        findings = plan_revision(
            draft, self._profile, dialogue_speakers=dialogue_speakers, max_items=max_items,
        )
        return [asdict(finding) for finding in findings]


def adapt_voice(
    voice: str | VoiceBible,
    *,
    situation: str = "",
    characters: Iterable[str] = (),
) -> SceneVoice:
    """Pass through author Markdown or render the structured profile for a scene."""
    if isinstance(voice, str):
        return SceneVoice(voice)
    names = {_label(name) for name in characters}
    selected = _label(situation)
    profile = replace(
        voice,
        character_voices=tuple(item for item in voice.character_voices if _label(item.name) in names),
        situational_voices=tuple(
            item for item in voice.situational_voices if selected and _label(item.situation) == selected
        ),
    )
    return SceneVoice(profile.to_markdown(), profile)


def outline_review_payload(validation: OutlineValidation) -> dict:
    """Turn the validator result into a JSON-ready response for candidate review."""
    contract = validation.contract
    return {
        "outline": contract.to_v4() if contract is not None else None,
        "layout_id": contract.layout_id if contract is not None else None,
        "issues": [asdict(issue) for issue in validation.issues],
    }


@dataclass(frozen=True, slots=True)
class LegacyMemoryMapping:
    subject: str
    key: str = ""
    value: str | None = None
    scene_id: str | None = None
    beat: int = 0
    scene_revision: int | None = None
    evidence: str = ""
    requires: tuple[str, ...] = ()
    expected_previous: str | None = None


def map_v4_memory_row(
    row: Mapping[str, object] | Row, contract: OutlineContract, mapping: LegacyMemoryMapping,
) -> MemoryRecord | None:
    """Stage a legacy memory item as a proposal with an explicit narrative placement."""
    item = dict(row)
    status = item.get("status")
    if status in ("rejected", "revoked"):
        return None
    if status not in ("pending", "approved"):
        raise ValueError("Trạng thái memory_items không hợp lệ.")
    row_id = item.get("id")
    if type(row_id) is not int or row_id <= 0:
        raise ValueError("memory_items.id phải là số nguyên dương.")
    kind = item.get("kind")
    if kind not in ("fact", "character", "knowledge", "timeline", "thread"):
        raise ValueError("Loại dữ kiện V4 không hợp lệ.")
    source = item.get("source")
    if source not in ("manual", "migration-v3", "model"):
        raise ValueError("Nguồn dữ kiện V4 không hợp lệ.")
    chapter = item.get("chapter")
    if not isinstance(chapter, str):
        raise ValueError("memory_items.chapter phải là chuỗi.")
    if chapter.strip():
        if not mapping.scene_id or mapping.scene_revision is None:
            raise ValueError("Dữ kiện theo chương cần ID cảnh nguồn và phiên bản cảnh.")
        position = contract.scene_position(chapter, mapping.scene_id, beat=mapping.beat)
    else:
        if mapping.scene_id is not None or mapping.scene_revision is not None or mapping.beat != 0:
            raise ValueError("Dữ kiện khởi đầu dùng vị trí truyện 0.")
        position = StoryPosition(0)

    if kind == "knowledge" and mapping.value is None:
        raise ValueError("Cần ánh xạ quyền biết thành known, unknown hoặc suspected.")
    event = MemoryEvent(
        f"v4-memory:{row_id}", position, "canon" if kind == "fact" else kind, mapping.subject,
        item.get("content") if mapping.value is None else mapping.value,
        key=mapping.key, source="model" if source == "model" else "human",
        evidence=mapping.evidence, requires=mapping.requires,
        expected_previous=mapping.expected_previous, scene_revision=mapping.scene_revision,
    )
    return MemoryRecord("propose", event.event_id, event)


@dataclass(frozen=True, slots=True)
class RetrievedTechniques:
    review_matches: tuple[TechniqueMatch, ...]
    writer_matches: tuple[TechniqueMatch, ...]
    skipped_hits: int


def adapt_v4_retrieval(
    context: RetrievalContext,
    hits: Iterable[Mapping[str, object] | Row],
    *,
    reviewed_notes: Iterable[TechniqueNote] = (),
    query_embedding: Embedding | None = None,
    limit: int = 4,
) -> RetrievedTechniques:
    """Accept V4 keyword order and use editor-curated notes for Writer input."""
    legacy = {}
    skipped = 0
    for hit in hits:
        note = technique_from_v4_hit(dict(hit))
        if note is None or note.note_id in legacy:
            skipped += 1
        else:
            legacy[note.note_id] = note
    review = rank_techniques(legacy.values(), context, keyword_order=legacy, limit=limit)
    for_writer = rank_techniques(
        (note for note in reviewed_notes if note.reviewed), context,
        keyword_order=legacy, query_embedding=query_embedding, limit=limit,
    )
    return RetrievedTechniques(review, for_writer, skipped)


@dataclass(frozen=True, slots=True)
class PreparedScene:
    packet: ScenePacket
    memory_revision: int | None

    def as_pipeline_result(self) -> tuple[str, list[dict[str, str]]]:
        """Return the packet and the actual hints that fit in it."""
        payload = json.loads(self.packet.text)
        return self.packet.text, payload.get("literary_hints", [])


class StaleMemorySource(ValueError):
    def __init__(self, event_ids: tuple[str, ...]):
        self.event_ids = event_ids
        super().__init__(f"Cần đối chiếu lại phiên bản cảnh nguồn của {', '.join(event_ids)}.")


def prepare_scene(
    contract: OutlineContract,
    chapter_id: str,
    scene_id: str,
    *,
    project_id: str,
    memory: StoredMemory | None = None,
    scene_revisions: Mapping[StoryPosition, int | None] | None = None,
    voice: SceneVoice | None = None,
    retrieval: RetrievedTechniques | None = None,
    budget: int = DEFAULT_SCENE_PACKET_BUDGET,
    measure: Callable[[str], int] | None = None,
) -> PreparedScene:
    """Compose a V4 pipeline result from reviewed, project-scoped inputs."""
    if memory is not None and (memory.project_id != project_id or memory.layout_id != contract.layout_id):
        raise MemoryStorageError("Bản đọc trí nhớ không khớp dự án hoặc thứ tự cảnh.")
    if memory is not None and scene_revisions is not None:
        before = contract.scene_position(chapter_id, scene_id)
        stale = tuple(
            event.event_id for event in memory.approved_events()
            if event.position < before and event.scene_revision is not None
            and scene_revisions.get(StoryPosition(event.position.chapter, event.position.scene)) != event.scene_revision
        )
        if stale:
            raise StaleMemorySource(stale)
    notes = (match.note for match in retrieval.writer_matches) if retrieval is not None else ()
    packet = build_scene_packet(
        contract, chapter_id, scene_id, memory=memory,
        voice_guidance=voice.guidance if voice is not None else "",
        techniques=notes, budget=budget, measure=measure,
    )
    return PreparedScene(packet, memory.revision if memory is not None else None)
