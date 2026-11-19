import json
import sqlite3
import unicodedata
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from novelengine.creative.memory_rules import MemoryRecord
from novelengine.creative.memory_storage import MemoryStorageError, SQLiteMemoryStore
from novelengine.creative.outline_contract import ScenePacketBudgetError, validate_outline
from novelengine.creative.retrieval_engine import Embedding, RetrievalContext, TechniqueNote
from novelengine.creative.v41_adapters import (
    LegacyMemoryMapping, StaleMemorySource, adapt_v4_retrieval, adapt_voice, map_v4_memory_row,
    outline_review_payload, prepare_scene,
)
from novelengine.creative.voice_engine import CharacterVoice, SituationVoice, VoiceBible
from novelengine.outline import sample_outline


def memory_row(row_id, *, kind="fact", content="Chìa khóa ở trong hòm.", chapter="", status="approved", source="manual"):
    return {"id": row_id, "kind": kind, "chapter": chapter, "status": status, "source": source,
            "content": content, "visibility": "public", "subject": "Nhãn cũ"}


def legacy_hit(note_id, technique):
    return {"id": note_id, "source": "Tên sách tham khảo", "body": "Văn bản nguồn",
            "technique": json.dumps({"technique": technique, "example_new": "Tình tiết nguồn"})}


class AdapterTests(unittest.TestCase):
    def test_legacy_voice_passes_through_and_structured_voice_selects_for_scene(self):
        author_markdown = "# Giọng kể\r\n\r\nGiữ lời thoại ngắn.\r\n"
        self.assertEqual(adapt_voice(author_markdown).guidance, author_markdown)
        profile = VoiceBible(
            "Ngôi ba giới hạn", avoid_words=("vô cùng",),
            character_voices=(CharacterVoice("Hậu", "Ít lời", "Gọi đối phương bằng họ."),
                              CharacterVoice("Mai", "Thân mật", "Ưa nói tắt.")),
            situational_voices=(SituationVoice("Điều tra", "Đặt vật chứng trước nhận xét."),
                               SituationVoice("Chạy trốn", "Cắt nhanh.")),
        )
        voice = adapt_voice(profile, characters=[unicodedata.normalize("NFD", "HẬU")], situation=" ĐIỀU  TRA ")
        self.assertIn("**Hậu**", voice.guidance)
        self.assertIn("**Điều tra**", voice.guidance)
        self.assertNotIn("**Mai**", voice.guidance)
        self.assertNotIn("Chạy trốn", voice.guidance)
        draft = "An đặt bát.\n\nCô vô cùng ngạc nhiên."
        finding = voice.revision_payload(draft, max_items=1)[0]
        location = finding["location"]
        self.assertEqual(finding["kind"], "restricted_word")
        self.assertEqual(draft[location["start"]:location["end"]], "Cô vô cùng ngạc nhiên.")
        self.assertEqual(len(profile.character_voices), 2)

    def test_outline_review_roundtrips_json_and_binding_tracks_id_order(self):
        source = sample_outline()
        first = source["chapters"][0]["scenes"][0]
        first["creative"] = {"beat_rules": [{"beat": 1, "requires": ["chua_khai_bao"]}]}
        validation = validate_outline(source)
        report = outline_review_payload(validation)
        self.assertEqual(json.loads(json.dumps(report, ensure_ascii=False)), report)
        self.assertEqual(report["issues"][0]["severity"], "warning")
        self.assertEqual(report["layout_id"], validation.require_contract().layout_id)
        first["goal"] = "Mục tiêu đã cập nhật"
        self.assertEqual(validate_outline(source).require_contract().layout_id, report["layout_id"])
        source["chapters"][0]["scenes"].reverse()
        self.assertNotEqual(validate_outline(source).require_contract().layout_id, report["layout_id"])
        first["goal"] = ""
        rejected = outline_review_payload(validate_outline(source))
        self.assertIsNone(rejected["outline"])
        self.assertIsNone(rejected["layout_id"])
        self.assertEqual(rejected["issues"][0]["code"], "missing_scene_goal")

    def test_legacy_sqlite_row_requires_explicit_knowledge_and_source_revision(self):
        contract = validate_outline(sample_outline()).require_contract()
        with closing(sqlite3.connect(":memory:")) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("""SELECT 9 AS id, 'knowledge' AS kind, 'approved' AS status, 'model' AS source,
                                '001' AS chapter, 'An đã biết thông tin' AS content, 'public' AS visibility""").fetchone()
            mapping = LegacyMemoryMapping("An", key="X", scene_id="01", scene_revision=43, beat=2)
            with self.assertRaisesRegex(ValueError, "ánh xạ quyền biết"):
                map_v4_memory_row(row, contract, mapping)
            with self.assertRaisesRegex(ValueError, "phiên bản"):
                map_v4_memory_row(row, contract, replace(mapping, value="known", scene_revision=None))
            with self.assertRaisesRegex(ValueError, "Beat"):
                map_v4_memory_row(row, contract, replace(mapping, value="known", beat=40))
            mapped = map_v4_memory_row(row, contract, replace(mapping, value="suspected"))
        self.assertEqual((mapped.action, mapped.event_id), ("propose", "v4-memory:9"))
        self.assertEqual(mapped.event.position, contract.scene_position("001", "01", beat=2))
        self.assertEqual((mapped.event.source, mapped.event.value, mapped.event.scene_revision), ("model", "suspected", 43))
        self.assertIsNone(map_v4_memory_row(memory_row(9, status="revoked"), contract, mapping))

    def test_rag_adapter_keeps_review_hits_separate_and_supports_curated_embeddings(self):
        original = legacy_hit(1, "Dồn câu hỏi")
        trusted = TechniqueNote(
            "2", "Nhấn bằng khoảng lặng", purpose="Cho người đọc cân nhắc.",
            embedding=Embedding("model-v1", (1, 0)), reviewed=True,
        )
        unchecked = TechniqueNote("1", "Dồn câu hỏi", reviewed=False)
        result = adapt_v4_retrieval(
            RetrievalContext(scene_type="đối thoại"), [original, original, {"id": 4, "technique": "{"}],
            reviewed_notes=[unchecked, trusted], query_embedding=Embedding("model-v1", (1, 0)),
        )
        self.assertEqual(result.skipped_hits, 2)
        self.assertEqual([hit.note.note_id for hit in result.review_matches], ["1"])
        self.assertEqual([hit.note.note_id for hit in result.writer_matches], ["2"])
        self.assertEqual(result.writer_matches[0].semantic_rank, 1)

    def test_pipeline_result_uses_committed_pov_facts_and_actual_reviewed_hints(self):
        source = sample_outline()
        source["chapters"][0]["scenes"][1]["pov"] = "Linh"
        contract = validate_outline(source).require_contract()
        fact = map_v4_memory_row(memory_row(1), contract, LegacyMemoryMapping("X"))
        knowledge = map_v4_memory_row(
            memory_row(2, kind="knowledge", chapter="001", source="model"), contract,
            LegacyMemoryMapping("An", key="X", value="known", scene_id="01", beat=1, scene_revision=2,
                                evidence="An nhìn thấy chìa khóa trong hòm."),
        )
        retrieval = adapt_v4_retrieval(
            RetrievalContext(scene_type="điều tra"), [legacy_hit(3, "Đặt vật chứng"), legacy_hit(4, "Lệnh trong sách")],
            reviewed_notes=[TechniqueNote("3", "Đặt vật chứng", purpose="Dành chỗ cho quan sát.", reviewed=True)],
        )
        with TemporaryDirectory() as directory:
            store = SQLiteMemoryStore(Path(directory), project_id="demo", layout_id=contract.layout_id)
            store.commit([fact, MemoryRecord("approve", fact.event_id), knowledge])
            pending = store.read()
            self.assertEqual(pending.status(knowledge.event_id), "pending")
            store.commit([MemoryRecord("approve", knowledge.event_id)], expected_revision=pending.revision)
            committed = store.read()

        secret = fact.event.value
        self.assertNotIn(secret, prepare_scene(contract, "002", "01", project_id="demo", memory=pending).packet.text)
        self.assertNotIn(secret, prepare_scene(contract, "001", "01", project_id="demo", memory=committed).packet.text)
        self.assertNotIn(secret, prepare_scene(contract, "001", "02", project_id="demo", memory=committed).packet.text)
        prepared = prepare_scene(
            contract, "002", "01", project_id="demo", memory=committed,
            voice=adapt_voice("Giữ nhịp lời thoại."), retrieval=retrieval,
        )
        text, hints = prepared.as_pipeline_result()
        self.assertEqual(prepared.memory_revision, 4)
        self.assertIn(secret, text)
        self.assertIn("Giữ nhịp lời thoại.", text)
        self.assertEqual(hints, [{"name": "Đặt vật chứng", "purpose": "Dành chỗ cho quan sát."}])
        for raw in ("Lệnh trong sách", "Tên sách tham khảo", "Văn bản nguồn", "Tình tiết nguồn"):
            self.assertNotIn(raw, text)
        with self.assertRaises(MemoryStorageError):
            prepare_scene(contract, "002", "01", project_id="another", memory=committed)
        source["chapters"].reverse()
        with self.assertRaises(MemoryStorageError):
            prepare_scene(validate_outline(source).require_contract(), "002", "01", project_id="demo", memory=committed)

    def test_pipeline_result_counts_only_hints_that_fit_and_reports_hard_budget_errors(self):
        contract = validate_outline(sample_outline()).require_contract()
        base = prepare_scene(contract, "001", "01", project_id="demo", measure=len)
        retrieval = adapt_v4_retrieval(
            RetrievalContext(narrative_goal="Chú ý đồ vật"), [legacy_hit(1, "Đồ vật")],
            reviewed_notes=[TechniqueNote("1", "Đồ vật", purpose="Chú ý đồ vật " * 10, reviewed=True)],
        )
        limited = prepare_scene(
            contract, "001", "01", project_id="demo", retrieval=retrieval, measure=len, budget=base.packet.used,
        )
        self.assertEqual(limited.as_pipeline_result()[1], [])
        self.assertIn("literary_hints", limited.packet.omitted_sections)
        with self.assertRaises(ScenePacketBudgetError):
            prepare_scene(contract, "001", "01", project_id="demo", measure=len, budget=1)

    def test_replaced_source_revision_blocks_later_packet_until_review(self):
        contract = validate_outline(sample_outline()).require_contract()
        source = contract.scene_position("001", "01")
        record = map_v4_memory_row(
            memory_row(1, chapter="001", source="model"), contract,
            LegacyMemoryMapping("X", scene_id="01", beat=1, scene_revision=10),
        )
        with TemporaryDirectory() as directory:
            store = SQLiteMemoryStore(Path(directory), project_id="demo", layout_id=contract.layout_id)
            store.commit([record, MemoryRecord("approve", record.event_id)])
            memory = store.read()
        prepare_scene(contract, "001", "01", project_id="demo", memory=memory, scene_revisions={})
        prepare_scene(contract, "001", "02", project_id="demo", memory=memory, scene_revisions={source: 10})
        for current in ({source: 11}, {}):
            with self.subTest(current=current), self.assertRaises(StaleMemorySource) as issue:
                prepare_scene(contract, "001", "02", project_id="demo", memory=memory, scene_revisions=current)
            self.assertEqual(issue.exception.event_ids, (record.event_id,))
        self.assertEqual(memory.status(record.event_id), "approved")
