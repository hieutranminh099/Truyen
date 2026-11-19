"""Validate V4 outlines and build small packets for a scene writer."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from itertools import chain
from typing import Callable, Iterable, Literal, Protocol

from ..outline import parse_outline
from .memory_rules import MemorySnapshot, StoryPosition
from .retrieval_engine import TechniqueNote, writer_hints


_SCENE_FIELDS = (
    "pov", "goal", "beats", "must_include", "forbidden", "continuity_requirements",
    "emotional_arc", "creative_freedom", "target_words", "creative",
)
DEFAULT_SCENE_PACKET_BUDGET = 2200


class _SnapshotReader(Protocol):
    def snapshot(self, *, before: StoryPosition | None = None) -> MemorySnapshot: ...


@dataclass(frozen=True, slots=True)
class OutlineIssue:
    severity: Literal["error", "warning"]
    code: str
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class SceneRef:
    chapter_id: str
    scene_id: str


class OutlineContract:
    """Normalized outline with a scene index. Obtain it through validate_outline."""

    def __init__(self, outline: dict, scenes: dict[SceneRef, dict], secret_schedule: dict[str, int]):
        self._outline = outline
        self._scenes = scenes
        self._secret_schedule = secret_schedule
        self._order = {ref: index for index, ref in enumerate(scenes)}
        self._positions = {
            SceneRef(chapter["id"], scene["id"]): StoryPosition(chapter_index, scene_index)
            for chapter_index, chapter in enumerate(outline["chapters"], 1)
            for scene_index, scene in enumerate(chapter["scenes"], 1)
        }
        ordered_ids = [(ref.chapter_id, ref.scene_id) for ref in self._positions]
        self._layout_id = hashlib.sha256(json.dumps(ordered_ids, separators=(",", ":")).encode("ascii")).hexdigest()

    @property
    def layout_id(self) -> str:
        """Identify the ordered chapter and scene IDs used by memory positions."""
        return self._layout_id

    def to_v4(self) -> dict:
        """Return an independent V4-compatible copy, including extension fields."""
        return deepcopy(self._outline)

    def scene_position(self, chapter_id: str, scene_id: str, *, beat: int = 0) -> StoryPosition:
        """Map V4 IDs to narrative position using outline order."""
        ref = SceneRef(str(chapter_id).strip(), str(scene_id).strip())
        start = self._positions[ref]
        position = StoryPosition(start.chapter, start.scene, beat)
        if beat > len(self._scenes[ref]["beats"]):
            raise ValueError("Beat nằm ngoài cảnh trong dàn ý.")
        return position


@dataclass(frozen=True, slots=True)
class OutlineValidation:
    contract: OutlineContract | None
    issues: tuple[OutlineIssue, ...]

    def require_contract(self) -> OutlineContract:
        if self.contract is None:
            issue = next(issue for issue in self.issues if issue.severity == "error")
            raise ValueError(f"{issue.path} [{issue.code}] {issue.message}")
        return self.contract


class _Checks:
    def __init__(self):
        self.issues: list[OutlineIssue] = []

    def add(self, code, path, message, severity="error"):
        self.issues.append(OutlineIssue(severity, code, path, message))

    @property
    def failed(self):
        return any(issue.severity == "error" for issue in self.issues)

    def text_fields(self, obj, fields, path):
        for key in fields:
            if key in obj:
                if isinstance(obj[key], str):
                    obj[key] = obj[key].strip()
                else:
                    self.add("invalid_field", f"{path}.{key}", "Trường này phải là chuỗi.")

    def strings(self, obj, key, path, *, drop_empty=False):
        if key not in obj:
            return []
        values = obj[key]
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            self.add("invalid_list", f"{path}.{key}", "Trường này phải là mảng chuỗi.")
            obj[key] = []
            return []
        values = [value.strip() for value in values]
        if drop_empty:
            values = [value for value in values if value]
        elif "" in values:
            self.add("blank_item", f"{path}.{key}", "Mảng không được chứa chuỗi rỗng.")
        obj[key] = values
        return values

    def records(self, obj, key, path):
        records = obj.get(key, [])
        if not isinstance(records, list):
            self.add("invalid_list", f"{path}.{key}", "Trường này phải là mảng object.")
            return
        for index, record in enumerate(records):
            record_path = f"{path}.{key}[{index}]"
            if isinstance(record, dict):
                yield record_path, record
            else:
                self.add("invalid_record", record_path, "Mục này phải là object.")

    def identifier(self, obj, key, path):
        value = obj.get(key)
        if isinstance(value, (str, int)) and not isinstance(value, bool) and str(value).strip():
            obj[key] = str(value).strip()
            return obj[key]
        self.add("missing_or_invalid_id", f"{path}.{key}", "Cần ID dạng chuỗi hoặc số nguyên.")
        return None


def _normalize_v4(outline: dict, checks: _Checks) -> dict[SceneRef, tuple[str, dict]]:
    checks.text_fields(outline, ("schema_version", "title", "theme", "premise"), "$")
    if "story_id" in outline:
        checks.identifier(outline, "story_id", "$")
    if isinstance(outline.get("genre"), list):
        checks.strings(outline, "genre", "$")
    else:
        checks.text_fields(outline, ("genre",), "$")
    if "world" in outline and not isinstance(outline["world"], dict):
        checks.text_fields(outline, ("world",), "$")

    character_ids = set()
    for path, character in checks.records(outline, "characters", "$"):
        checks.text_fields(character, ("name", "traits", "goal", "secret"), path)
        if "id" in character:
            character_id = checks.identifier(character, "id", path)
            if character_id and character_id in character_ids:
                checks.add("duplicate_character_id", f"{path}.id", f"Trùng ID nhân vật {character_id}.")
            character_ids.add(character_id)

    scenes = {}
    chapter_ids = set()
    for path, chapter in checks.records(outline, "chapters", "$"):
        chapter_id = checks.identifier(chapter, "id", path)
        checks.text_fields(chapter, ("title", "purpose"), path)
        if chapter_id and chapter_id in chapter_ids:
            checks.add("duplicate_chapter_id", f"{path}.id", f"Trùng ID chương {chapter_id}.")
        chapter_ids.add(chapter_id)

        for scene_path, scene in checks.records(chapter, "scenes", path):
            if "id" not in scene and "scene_id" in scene:
                scene["id"] = scene["scene_id"]
            scene_id = checks.identifier(scene, "id", scene_path)
            checks.text_fields(scene, ("title", "pov", "goal", "emotional_arc", "creative_freedom"), scene_path)
            if not isinstance(scene.get("goal"), str) or not scene["goal"]:
                checks.add("missing_scene_goal", f"{scene_path}.goal", "Cảnh cần mục tiêu bằng văn bản.")
            checks.strings(scene, "beats", scene_path)
            for key in ("must_include", "forbidden", "continuity_requirements"):
                checks.strings(scene, key, scene_path, drop_empty=True)
            _normalize_target_words(scene, scene_path, checks)
            if chapter_id and scene_id:
                ref = SceneRef(chapter_id, scene_id)
                if ref in scenes:
                    checks.add("duplicate_scene_id", f"{scene_path}.id", f"Trùng ID cảnh {scene_id} trong chương {chapter_id}.")
                scenes[ref] = (scene_path, scene)
    return scenes


def _normalize_target_words(scene: dict, path: str, checks: _Checks) -> None:
    value = scene.get("target_words")
    try:
        if isinstance(value, str):
            value = int(value) if value.strip() else None
    except ValueError:
        pass
    if value is None or (type(value) is int and value == 0):
        scene.pop("target_words", None)
    elif type(value) is int and value > 0:
        scene["target_words"] = value
    else:
        checks.add("invalid_target_words", f"{path}.target_words", "Số từ mục tiêu phải là số nguyên dương.")


def _creative(obj: dict, path: str, checks: _Checks) -> dict:
    extension = obj.get("creative", {})
    if isinstance(extension, dict):
        return extension
    checks.add("invalid_record", f"{path}.creative", "Trường creative phải là object.")
    return {}


def _scene_reference(ref: dict, path: str, checks: _Checks) -> SceneRef | None:
    chapter_id = checks.identifier(ref, "chapter_id", path)
    scene_id = checks.identifier(ref, "scene_id", path)
    return SceneRef(chapter_id, scene_id) if chapter_id and scene_id else None


def _label(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def _knowledge_key(record: dict, path: str, checks: _Checks) -> tuple[str, str] | None:
    checks.text_fields(record, ("character",), path)
    character = record.get("character")
    if not isinstance(character, str) or not character:
        checks.add("missing_character", f"{path}.character", "Cần nhân vật sử dụng hoặc học thông tin.")
        character = ""
    fact = checks.identifier(record, "fact_id", path)
    return (_label(character), fact) if character and fact else None


def _validate_secret_schedule(root: dict, order: dict[SceneRef, int], checks: _Checks) -> dict[str, int]:
    schedule = {}
    seen = set()
    for path, secret in checks.records(root, "secrets", "$.creative"):
        secret_id = checks.identifier(secret, "id", path)
        if secret_id and secret_id in seen:
            checks.add("duplicate_secret_id", f"{path}.id", f"Trùng ID bí mật {secret_id}.")
        seen.add(secret_id)
        floor = secret.get("reveal_from")
        ref = _scene_reference(floor, f"{path}.reveal_from", checks) if isinstance(floor, dict) else None
        if ref not in order:
            checks.add("invalid_reveal_scene", f"{path}.reveal_from", "Mốc tiết lộ phải là một cảnh trong dàn ý.")
        elif secret_id:
            schedule[secret_id] = order[ref]
    return schedule


def _validate_scene(
    ref: SceneRef, scene: dict, path: str, order: dict[SceneRef, int],
    schedule: dict[str, int], checks: _Checks,
) -> list[tuple[str, dict]]:
    required = {_label(value) for value in scene.get("must_include", ())}
    forbidden = {_label(value) for value in scene.get("forbidden", ())}
    for value in sorted(required & forbidden):
        checks.add("contradictory_constraint", path, f"«{value}» vừa bắt buộc vừa bị cấm.")

    layer = _creative(scene, path, checks)
    path += ".creative"
    for dep_path, dependency in checks.records(layer, "depends_on", path):
        dep = _scene_reference(dependency, dep_path, checks)
        if dep not in order:
            checks.add("unknown_dependency", dep_path, "Mốc phụ thuộc không trỏ đến cảnh trong dàn ý.")
        elif order[dep] >= order[ref]:
            checks.add("future_dependency", dep_path, "Mốc phụ thuộc phải đứng trước cảnh này.")

    forbidden_secrets = set(checks.strings(layer, "forbid_secrets", path))
    for secret in dict.fromkeys(checks.strings(layer, "reveal_secrets", path)):
        reveal_path = f"{path}.reveal_secrets"
        if secret in forbidden_secrets:
            checks.add("contradictory_secret", reveal_path, f"Bí mật {secret} vừa phải lộ vừa bị cấm.")
        if secret not in schedule:
            checks.add("unverified_secret", reveal_path, f"Chưa có mốc tiết lộ cho {secret}.", "warning")
        elif order[ref] < schedule[secret]:
            checks.add("early_reveal", reveal_path, f"Tiết lộ {secret} trước mốc đã khai báo.")

    rules = []
    seen = set()
    for rule_path, rule in checks.records(layer, "beat_rules", path):
        beat = rule.get("beat")
        if type(beat) is not int or not 1 <= beat <= len(scene["beats"]):
            checks.add("invalid_beat", f"{rule_path}.beat", "Số thứ tự beat phải trỏ vào beats[].")
            continue
        if beat in seen:
            checks.add("duplicate_beat_rule", f"{rule_path}.beat", f"Beat {beat} đã có quy tắc.")
            continue
        seen.add(beat)
        for key in ("requires", "establishes"):
            checks.strings(rule, key, rule_path)
        rules.append((rule_path, rule))
    return sorted(rules, key=lambda entry: entry[1]["beat"])


def _validate_story_rules(outline: dict, scenes: dict[SceneRef, tuple[str, dict]], checks: _Checks) -> dict[str, int]:
    order = {ref: index for index, ref in enumerate(scenes)}
    root = _creative(outline, "$", checks)
    established = set(checks.strings(root, "initial_conditions", "$.creative"))
    schedule = _validate_secret_schedule(root, order, checks)
    knowledge: dict[tuple[str, str], str] = {}
    for path, entry in checks.records(root, "initial_knowledge", "$.creative"):
        key = _knowledge_key(entry, path, checks)
        checks.text_fields(entry, ("state",), path)
        state = entry.get("state")
        if state not in ("known", "unknown", "suspected"):
            checks.add("invalid_knowledge_state", f"{path}.state", "Dùng known, unknown hoặc suspected.")
        elif key:
            if key in knowledge and knowledge[key] != state:
                checks.add("contradictory_knowledge", path, "Trạng thái biết ban đầu bị khai báo mâu thuẫn.")
            knowledge[key] = state

    rules = [rule for ref, (path, scene) in scenes.items()
             for rule in _validate_scene(ref, scene, path, order, schedule, checks)]
    declared = established | {condition for _, rule in rules for condition in rule.get("establishes", ())}
    for path, rule in rules:
        for condition in dict.fromkeys(rule.get("requires", ())):
            if condition in established:
                continue
            if condition in declared:
                checks.add("unmet_precondition", f"{path}.requires", f"{condition} chưa được thiết lập trước beat này.")
            else:
                checks.add("undeclared_precondition", f"{path}.requires", f"Chưa khai báo nguồn của {condition}.", "warning")
        for use_path, entry in checks.records(rule, "knowledge_used", path):
            key = _knowledge_key(entry, use_path, checks)
            if key and key not in knowledge:
                checks.add("unverified_knowledge", use_path, f"Chưa xác minh nhân vật biết {key[1]}.", "warning")
            elif key and knowledge[key] != "known":
                checks.add("knowledge_violation", use_path, f"Dữ liệu ghi {key[1]} ở trạng thái {knowledge[key]}.")
        for learn_path, entry in checks.records(rule, "knowledge_learned", path):
            if key := _knowledge_key(entry, learn_path, checks):
                knowledge[key] = "known"
        established.update(rule.get("establishes", ()))
    return schedule


def validate_outline(data: dict | str) -> OutlineValidation:
    """Validate a copy. Warnings leave the normalized contract available."""
    checks = _Checks()
    if isinstance(data, str):
        try:
            data = json.loads(data.removeprefix("\ufeff"))
        except ValueError:
            checks.add("invalid_json", "$", "Dàn ý phải là JSON hợp lệ.")
            return OutlineValidation(None, tuple(checks.issues))
    if not isinstance(data, dict):
        checks.add("invalid_outline", "$", "Dàn ý phải là JSON object.")
        return OutlineValidation(None, tuple(checks.issues))

    outline = deepcopy(data)
    scenes = _normalize_v4(outline, checks)
    contract = None
    if not checks.failed:
        try:
            parse_outline(outline)
        except ValueError as exc:
            checks.add("invalid_v4", "$", str(exc))
        else:
            schedule = _validate_story_rules(outline, scenes, checks)
            if not checks.failed:
                contract = OutlineContract(outline, {ref: scene for ref, (_, scene) in scenes.items()}, schedule)
    return OutlineValidation(contract, tuple(checks.issues))


@dataclass(frozen=True, slots=True)
class ScenePacket:
    text: str
    used: int
    omitted_sections: tuple[str, ...]


class ScenePacketBudgetError(ValueError):
    def __init__(self, required: int, budget: int):
        self.required = required
        self.budget = budget
        super().__init__(f"Ràng buộc cảnh cần {required} đơn vị, ngân sách chỉ có {budget}.")


def _utf8_bytes(text: str) -> int:
    return len(text.encode("utf-8"))


def _packet_rules(layer: dict) -> dict:
    rules = {key: layer[key] for key in ("forbid_secrets", "reveal_secrets") if key in layer}
    if "depends_on" in layer:
        rules["depends_on"] = [
            {"chapter_id": ref["chapter_id"], "scene_id": ref["scene_id"]} for ref in layer["depends_on"]
        ]
    if "beat_rules" in layer:
        beats = []
        for rule in sorted(layer["beat_rules"], key=lambda item: item["beat"]):
            beat = {key: rule[key] for key in ("beat", "requires", "establishes") if key in rule}
            for key in ("knowledge_used", "knowledge_learned"):
                if key in rule:
                    beat[key] = [
                        {"character": entry["character"], "fact_id": entry["fact_id"]} for entry in rule[key]
                    ]
            beats.append(beat)
        rules["beat_rules"] = beats
    return rules


def build_scene_packet(
    contract: OutlineContract,
    chapter_id: str,
    scene_id: str,
    *,
    budget: int = DEFAULT_SCENE_PACKET_BUDGET,
    measure: Callable[[str], int] | None = None,
    memory: _SnapshotReader | None = None,
    approved_pov_context: Iterable[str] = (),
    voice_guidance: str = "",
    techniques: Iterable[TechniqueNote] = (),
) -> ScenePacket:
    """Pack required fields intact, then fit optional items, using UTF-8 bytes by default."""
    if budget <= 0:
        raise ValueError("Ngân sách Scene Packet phải dương.")
    if measure is None:
        measure = _utf8_bytes
    ref = SceneRef(str(chapter_id).strip(), str(scene_id).strip())
    scene = contract._scenes[ref]
    payload = {"chapter_id": ref.chapter_id, "scene_id": ref.scene_id}
    if story_id := contract._outline.get("story_id"):
        payload["story_id"] = story_id
    for key in _SCENE_FIELDS:
        if key in scene and scene[key] != "":
            payload[key] = scene[key]
    if "creative" in payload:
        payload["creative"] = _packet_rules(payload["creative"])

    def encode() -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    text = encode()
    used = measure(text)
    if used > budget:
        raise ScenePacketBudgetError(used, budget)

    omitted = []
    genre = contract._outline.get("genre", "")
    memory_facts = ()
    if memory is not None and scene.get("pov"):
        snapshot = memory.snapshot(before=contract._positions[ref])
        forbidden = set(scene.get("creative", {}).get("forbid_secrets", ()))
        index = contract._order[ref]
        memory_facts = tuple(
            fact.statement for fact in snapshot.known_facts(scene["pov"])
            if fact.fact_id not in forbidden and contract._secret_schedule.get(fact.fact_id, 0) <= index
        )
    optional_sections = (
        ("approved_pov_context", chain(memory_facts, approved_pov_context)),
        ("voice_guidance", (voice_guidance,)),
        ("scene_title", (scene.get("title", ""),)),
        ("genre", (genre,) if isinstance(genre, str) else genre),
        ("literary_hints", writer_hints(techniques)),
    )
    for key, items in optional_sections:
        selected = []
        for item in items:
            if isinstance(item, str):
                item = item.strip()
            if not item:
                continue
            selected.append(item)
            payload[key] = selected
            candidate = encode()
            cost = measure(candidate)
            if cost <= budget:
                text, used = candidate, cost
            else:
                selected.pop()
                if key not in omitted:
                    omitted.append(key)
        if not selected:
            payload.pop(key, None)
    return ScenePacket(text, used, tuple(omitted))
