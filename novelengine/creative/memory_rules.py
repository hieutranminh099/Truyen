"""In-memory approvals, narrative state and point-of-view knowledge."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from threading import Lock
from types import MappingProxyType
from typing import Iterable, Literal, Mapping


MemoryKind = Literal["canon", "character", "knowledge", "timeline", "thread"]
KnowledgeState = Literal["known", "unknown", "suspected"]
MemoryStatus = Literal["pending", "approved", "rejected", "revoked"]

_DECISION_STATES: dict[str, tuple[MemoryStatus, MemoryStatus]] = {
    "approve": ("pending", "approved"),
    "reject": ("pending", "rejected"),
    "undo": ("approved", "revoked"),
}


@dataclass(frozen=True, order=True, slots=True)
class StoryPosition:
    chapter: int
    scene: int = 0
    beat: int = 0

    def __post_init__(self):
        if any(type(value) is not int or value < 0 for value in (self.chapter, self.scene, self.beat)):
            raise ValueError("Vị trí truyện dùng số thứ tự nguyên không âm.")


@dataclass(frozen=True, slots=True)
class MemoryEvent:
    event_id: str
    position: StoryPosition
    kind: MemoryKind
    subject: str
    value: str
    key: str = ""
    source: Literal["human", "model"] = "human"
    evidence: str = ""
    requires: tuple[str, ...] = ()
    expected_previous: str | None = None
    scene_revision: int | None = None

    def __post_init__(self):
        if not isinstance(self.position, StoryPosition):
            raise ValueError("Cần vị trí StoryPosition.")
        if self.kind not in ("canon", "character", "knowledge", "timeline", "thread"):
            raise ValueError("Lớp trí nhớ không hợp lệ.")
        if self.source not in ("human", "model"):
            raise ValueError("Nguồn sự kiện phải là human hoặc model.")
        for field in ("event_id", "subject", "value"):
            text = getattr(self, field)
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"{field} phải là chuỗi khác rỗng.")
            object.__setattr__(self, field, text.strip())
        if not isinstance(self.key, str) or not isinstance(self.evidence, str):
            raise ValueError("key và evidence phải là chuỗi.")
        object.__setattr__(self, "key", self.key.strip())
        if self.kind in ("character", "knowledge", "thread") and not self.key:
            raise ValueError("Sự kiện nhân vật, quyền biết và tuyến truyện cần key.")
        if self.kind in ("canon", "timeline") and self.key:
            raise ValueError("Dùng subject làm ID dữ kiện hoặc mốc thời gian.")
        if self.kind == "knowledge" and self.value not in ("known", "unknown", "suspected"):
            raise ValueError("Trạng thái biết phải là known, unknown hoặc suspected.")
        if isinstance(self.requires, str):
            raise ValueError("requires phải là một tập hợp ID sự kiện.")
        dependencies = tuple(self.requires)
        if any(not isinstance(value, str) or not value.strip() for value in dependencies):
            raise ValueError("ID sự kiện phụ thuộc phải là chuỗi khác rỗng.")
        object.__setattr__(self, "requires", tuple(dict.fromkeys(value.strip() for value in dependencies)))
        if self.expected_previous is not None and not isinstance(self.expected_previous, str):
            raise ValueError("expected_previous phải là chuỗi hoặc None.")
        if self.scene_revision is not None and (
            type(self.scene_revision) is not int or self.scene_revision <= 0 or self.position.scene == 0
        ):
            raise ValueError("scene_revision phải là ID phiên bản dương của một cảnh.")


@dataclass(frozen=True, slots=True)
class MemoryIssue:
    event_id: str
    code: str
    message: str


class MemoryConflict(ValueError):
    def __init__(self, issues: tuple[MemoryIssue, ...]):
        self.issues = issues
        super().__init__(" ".join(f"[{issue.event_id}/{issue.code}] {issue.message}" for issue in issues))


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    action: Literal["propose", "approve", "reject", "undo"]
    event_id: str
    event: MemoryEvent | None = None
    reason: str = ""

    def __post_init__(self):
        if not isinstance(self.event_id, str) or not self.event_id.strip() or not isinstance(self.reason, str):
            raise ValueError("Bản ghi cần ID sự kiện và lý do dạng chuỗi.")
        if self.action == "propose":
            if not isinstance(self.event, MemoryEvent) or self.event.event_id != self.event_id or self.reason:
                raise ValueError("Đề xuất cần một sự kiện có cùng ID. Dùng evidence cho dẫn chứng.")
        elif self.action not in _DECISION_STATES or self.event is not None:
            raise ValueError("Bản ghi quyết định chỉ nhận hành động, ID sự kiện và lý do.")


@dataclass(frozen=True, slots=True)
class KnownFact:
    fact_id: str
    statement: str


@dataclass(frozen=True, slots=True)
class MemorySnapshot:
    canon: Mapping[str, str]
    characters: Mapping[tuple[str, str], str]
    knowledge: Mapping[tuple[str, str], KnowledgeState]
    timeline: tuple[MemoryEvent, ...]
    threads: Mapping[tuple[str, str], str]

    def knowledge_state(self, character: str, fact_id: str) -> KnowledgeState | None:
        return self.knowledge.get((_character_label(character), fact_id))

    def known_facts(self, character: str) -> tuple[KnownFact, ...]:
        """Project approved statements for this character only."""
        label = _character_label(character)
        return tuple(
            KnownFact(fact_id, self.canon[fact_id])
            for (person, fact_id), state in sorted(self.knowledge.items())
            if person == label and state == "known" and fact_id in self.canon
        )


def _character_label(name: str) -> str:
    return " ".join(unicodedata.normalize("NFC", name).casefold().split())


def _subject(event: MemoryEvent) -> str:
    return _character_label(event.subject) if event.kind in ("character", "knowledge") else event.subject


def _chronological(events: Iterable[MemoryEvent]) -> list[MemoryEvent]:
    return sorted(events, key=lambda event: (event.position, event.event_id))


def _conflicts(events: Mapping[str, MemoryEvent]) -> tuple[MemoryIssue, ...]:
    issues = []
    latest: dict[tuple[str, str, str], MemoryEvent] = {}
    ordered = _chronological(events.values())
    canon = {}
    for event in ordered:
        if event.kind == "canon":
            canon.setdefault(event.subject, event.position)
    for event in ordered:
        witnessed = False
        for event_id in event.requires:
            dependency = events.get(event_id)
            if dependency is None:
                issues.append(MemoryIssue(event.event_id, "unapproved_dependency",
                                          f"Mốc {event_id} chưa được duyệt hoặc đã bị thu hồi."))
            elif dependency.position >= event.position:
                issues.append(MemoryIssue(event.event_id, "timeline_order",
                                          f"Mốc {event_id} phải xảy ra trước sự kiện này."))
            elif dependency.kind == "timeline":
                witnessed = True

        slot = (event.kind, _subject(event), event.key)
        previous = latest.get(slot)
        if previous and previous.position == event.position:
            issues.append(MemoryIssue(event.event_id, "same_position", "Cùng thuộc tính có hai sự kiện tại một mốc."))
        if previous and event.kind in ("canon", "timeline") and previous.value != event.value:
            issues.append(MemoryIssue(event.event_id, "contradictory_fact", f"Nội dung khác sự kiện {previous.event_id}."))
        if event.expected_previous is not None and event.expected_previous != (previous.value if previous else ""):
            issues.append(MemoryIssue(event.event_id, "previous_state_changed", "Giá trị trước sự kiện khác tiền đề đã ghi."))
        if event.kind == "knowledge" and event.value == "known":
            if event.key not in canon or canon[event.key] > event.position:
                issues.append(MemoryIssue(event.event_id, "missing_canon",
                                          f"Dữ kiện canon {event.key} cần được duyệt tại mốc này hoặc trước đó."))
            if not (witnessed or event.evidence.strip()):
                issues.append(MemoryIssue(event.event_id, "verify_learning",
                                          "Cần dẫn chứng đã kiểm tra hoặc liên kết đến mốc học thông tin đã duyệt."))
        latest[slot] = event
    return tuple(issues)


def _project(events: Iterable[MemoryEvent], before: StoryPosition | None) -> MemorySnapshot:
    canon = {}
    characters = {}
    knowledge = {}
    timeline = []
    threads = {}
    for event in _chronological(events):
        if before is not None and event.position >= before:
            break
        if event.kind == "canon":
            canon[event.subject] = event.value
        elif event.kind == "character":
            characters[(_subject(event), event.key)] = event.value
        elif event.kind == "knowledge":
            knowledge[(_subject(event), event.key)] = event.value
        elif event.kind == "timeline":
            timeline.append(event)
        elif event.kind == "thread":
            threads[(event.subject, event.key)] = event.value
    return MemorySnapshot(
        MappingProxyType(canon), MappingProxyType(characters), MappingProxyType(knowledge),
        tuple(timeline), MappingProxyType(threads),
    )


def rebuild_snapshot(
    approved_events: Iterable[MemoryEvent],
    *,
    before: StoryPosition | None = None,
) -> MemorySnapshot:
    """Validate and replay an explicit stream of currently approved events."""
    indexed = {}
    for event in approved_events:
        if event.event_id in indexed:
            raise ValueError(f"Trùng ID sự kiện {event.event_id}.")
        indexed[event.event_id] = event
    if issues := _conflicts(indexed):
        raise MemoryConflict(issues)
    return _project(indexed.values(), before)


class MemoryLedger:
    """An append-only decision history with atomic changes to approved state."""

    def __init__(self):
        self._lock = Lock()
        self._events: dict[str, MemoryEvent] = {}
        self._statuses: dict[str, MemoryStatus] = {}
        self._approved: dict[str, MemoryEvent] = {}
        self._journal: list[MemoryRecord] = []

    @classmethod
    def from_journal(cls, records: Iterable[MemoryRecord]) -> MemoryLedger:
        """Restore recorded transitions in order and check the resulting approved state."""
        ledger = cls()
        for record in records:
            ledger._append_record(record)
        if issues := _conflicts(ledger._approved):
            raise MemoryConflict(issues)
        return ledger

    def _append_record(self, record: MemoryRecord) -> None:
        event_id = record.event_id
        if record.action == "propose":
            if event_id in self._events:
                raise ValueError(f"Trùng đề xuất {event_id} trong nhật ký.")
            assert record.event is not None
            self._events[event_id] = record.event
            self._statuses[event_id] = "pending"
        else:
            previous, status = _DECISION_STATES[record.action]
            if self._statuses.get(event_id) != previous:
                raise ValueError(f"Quyết định {record.action} sai trạng thái cho {event_id}.")
            self._statuses[event_id] = status
            if status == "approved":
                self._approved[event_id] = self._events[event_id]
            elif status == "revoked":
                del self._approved[event_id]
        self._journal.append(record)

    @property
    def journal(self) -> tuple[MemoryRecord, ...]:
        with self._lock:
            return tuple(self._journal)

    def status(self, event_id: str) -> MemoryStatus:
        with self._lock:
            return self._statuses[event_id]

    def propose(self, event: MemoryEvent) -> MemoryStatus:
        with self._lock:
            if event.event_id in self._events:
                if self._events[event.event_id] != event:
                    raise ValueError(f"ID {event.event_id} đã gắn với sự kiện khác.")
                return self._statuses[event.event_id]
            self._append_record(MemoryRecord("propose", event.event_id, event))
            return "pending"

    def _pending(self, event_id: str) -> MemoryEvent:
        if self._statuses[event_id] != "pending":
            raise ValueError(f"Sự kiện {event_id} không còn chờ duyệt.")
        return self._events[event_id]

    def validate(self, event_id: str) -> tuple[MemoryIssue, ...]:
        """Check a pending proposal together with all current approvals."""
        with self._lock:
            event = self._pending(event_id)
            return _conflicts(self._approved | {event_id: event})

    def approve(self, event_id: str, *, reason: str = "") -> None:
        with self._lock:
            if self._statuses[event_id] == "approved":
                return
            event = self._pending(event_id)
            if issues := _conflicts(self._approved | {event_id: event}):
                raise MemoryConflict(issues)
            self._append_record(MemoryRecord("approve", event_id, reason=reason))

    def reject(self, event_id: str, *, reason: str = "") -> None:
        with self._lock:
            if self._statuses[event_id] == "rejected":
                return
            self._pending(event_id)
            self._append_record(MemoryRecord("reject", event_id, reason=reason))

    def undo(self, event_id: str, *, reason: str = "") -> None:
        """Revoke an approval only if the remaining approved history is consistent."""
        with self._lock:
            if self._statuses[event_id] == "revoked":
                return
            if self._statuses[event_id] != "approved":
                raise ValueError(f"Sự kiện {event_id} chưa được duyệt.")
            remaining = self._approved.copy()
            del remaining[event_id]
            if issues := _conflicts(remaining):
                raise MemoryConflict(issues)
            self._append_record(MemoryRecord("undo", event_id, reason=reason))

    def approved_events(self) -> tuple[MemoryEvent, ...]:
        with self._lock:
            events = tuple(self._approved.values())
        return tuple(_chronological(events))

    def snapshot(self, *, before: StoryPosition | None = None) -> MemorySnapshot:
        """Read approved state strictly before the given narrative position."""
        with self._lock:
            events = tuple(self._approved.values())
        return _project(events, before)
