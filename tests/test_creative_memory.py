import unittest
from concurrent.futures import ThreadPoolExecutor

from novelengine.creative.memory_rules import MemoryConflict, MemoryEvent, MemoryLedger, StoryPosition, rebuild_snapshot
from novelengine.creative.outline_contract import build_scene_packet, validate_outline


SECRET = "Hậu đã thay ca trực cho chị mình."


class MemoryRulesTests(unittest.TestCase):
    def setUp(self):
        self.ledger = MemoryLedger()

    def approve(self, event):
        self.ledger.propose(event)
        self.ledger.approve(event.event_id)

    def initialize_secret(self):
        self.approve(MemoryEvent("secret", StoryPosition(0), "canon", "X", SECRET))
        self.approve(MemoryEvent("a-knows", StoryPosition(0), "knowledge", "A", "known", key="X",
                                 evidence="Hồ sơ nhân vật xác nhận A có mặt."))
        self.approve(MemoryEvent("b-unaware", StoryPosition(0), "knowledge", "B", "unknown", key="X"))

    def test_point_of_view_packet_excludes_other_character_and_future_knowledge(self):
        self.initialize_secret()
        data = {"chapters": [
            {"id": str(index), "title": f"Chương {index}", "scenes": [
                {"id": "01", "pov": pov, "goal": "Kiểm tra hồi chuông", "beats": ["Dừng trước cửa"]}
            ]}
            for index, pov in enumerate(("A", "B", "B", "B"), 1)
        ]}
        contract = validate_outline(data).require_contract()
        before = contract.scene_position("3", "01")
        self.approve(MemoryEvent("letter", StoryPosition(before.chapter, before.scene, 1),
                                 "timeline", "letter", "B nhận thư của A."))
        self.approve(MemoryEvent("b-learns", StoryPosition(before.chapter, before.scene, 2),
                                 "knowledge", "B", "known", key="X", requires=("letter",),
                                 expected_previous="unknown"))
        for chapter, visible in (("1", True), ("2", False), ("3", False), ("4", True)):
            with self.subTest(chapter=chapter):
                packet = build_scene_packet(contract, chapter, "01", memory=self.ledger)
                self.assertEqual(SECRET in packet.text, visible)
        self.assertEqual(self.ledger.snapshot(before=before).knowledge_state("b", "X"), "unknown")
        self.assertIsNone(self.ledger.snapshot().knowledge_state("C", "X"))

    def test_embargo_and_scene_secret_exclusion_apply_to_known_facts(self):
        self.initialize_secret()
        source = {
            "creative": {"secrets": [{"id": "X", "reveal_from": {"chapter_id": "1", "scene_id": "2"}}]},
            "chapters": [{"id": "1", "title": "Đổi ca", "scenes": [
                {"id": "1", "pov": "A", "goal": "Giữ lời", "beats": ["Gập tờ phiếu"]},
                {"id": "2", "pov": "A", "goal": "Chờ", "beats": ["Nhìn đồng hồ"],
                 "creative": {"forbid_secrets": ["X"]}},
                {"id": "3", "pov": "A", "goal": "Kể", "beats": ["Mở tờ phiếu"]},
            ]}],
        }
        contract = validate_outline(source).require_contract()
        for scene, visible in (("1", False), ("2", False), ("3", True)):
            packet = build_scene_packet(contract, "1", scene, memory=self.ledger)
            self.assertEqual(SECRET in packet.text, visible)

    def test_model_guess_and_unwitnessed_learning_require_review(self):
        self.initialize_secret()
        suspect = MemoryEvent("guess", StoryPosition(2, 1), "knowledge", "B", "suspected",
                              key="X", source="model")
        self.assertEqual(self.ledger.propose(suspect), "pending")
        self.assertEqual(self.ledger.snapshot().knowledge_state("B", "X"), "unknown")
        self.ledger.approve("guess", reason="Cảnh chỉ thể hiện nghi ngờ.")
        self.assertEqual(self.ledger.snapshot().knowledge_state("B", "X"), "suspected")
        self.assertEqual(self.ledger.snapshot().known_facts("B"), ())
        unverified = MemoryEvent("unverified", StoryPosition(3), "knowledge", "B", "known",
                                 key="X", source="model")
        self.ledger.propose(unverified)
        self.assertEqual([item.code for item in self.ledger.validate("unverified")], ["verify_learning"])
        with self.assertRaises(MemoryConflict):
            self.ledger.approve("unverified")
        self.ledger.reject("unverified", reason="Chưa có cảnh B nhận tin.")
        self.assertEqual(self.ledger.status("unverified"), "rejected")

    def test_undo_preserves_history_and_independent_approved_chapters(self):
        early = MemoryEvent("wet-coat", StoryPosition(1, 1), "character", "Mai", "ướt", key="áo")
        later = MemoryEvent("open-thread", StoryPosition(230, 1), "thread", "letter", "đang mở", key="trạng thái")
        self.approve(early)
        self.approve(later)
        old_snapshot = self.ledger.snapshot()
        self.ledger.undo(early.event_id, reason="Đã sửa cảnh mưa.")
        self.ledger.undo(early.event_id)
        self.assertEqual(self.ledger.status(early.event_id), "revoked")
        self.assertEqual(len(self.ledger.journal), 5)
        self.assertEqual(self.ledger.journal[0].event, early)
        self.assertEqual(self.ledger.journal[-1].action, "undo")
        self.assertEqual(old_snapshot.characters[("mai", "áo")], "ướt")
        new_snapshot = self.ledger.snapshot()
        self.assertFalse(new_snapshot.characters)
        self.assertEqual(new_snapshot.threads, old_snapshot.threads)
        self.assertEqual(new_snapshot, rebuild_snapshot(reversed(self.ledger.approved_events())))

    def test_rollback_and_retcon_cannot_invalidate_later_approved_state(self):
        initial = MemoryEvent("brass", StoryPosition(1), "character", "Mai", "đồng", key="chìa khóa")
        self.approve(initial)
        self.approve(MemoryEvent("iron", StoryPosition(3), "character", "Mai", "sắt", key="chìa khóa",
                                 requires=("brass",), expected_previous="đồng"))
        self.ledger.propose(MemoryEvent("wood", StoryPosition(2), "character", "Mai", "gỗ", key="chìa khóa"))
        before = self.ledger.snapshot()
        with self.assertRaises(MemoryConflict) as rollback:
            self.ledger.undo(initial.event_id)
        self.assertIn("unapproved_dependency", {item.code for item in rollback.exception.issues})
        with self.assertRaises(MemoryConflict) as retcon:
            self.ledger.approve("wood")
        self.assertEqual([(item.event_id, item.code) for item in retcon.exception.issues],
                         [("iron", "previous_state_changed")])
        self.assertEqual(self.ledger.snapshot(), before)
        self.assertEqual(self.ledger.status("wood"), "pending")
        self.assertEqual(len(self.ledger.journal), 5)

    def test_conflicting_canon_and_future_dependencies_are_detected(self):
        self.initialize_secret()
        self.ledger.propose(MemoryEvent("bad-fact", StoryPosition(2), "canon", "X", "Nội dung khác"))
        self.assertEqual(self.ledger.validate("bad-fact")[0].code, "contradictory_fact")
        with self.assertRaises(MemoryConflict) as issued:
            self.ledger.undo("secret")
        self.assertEqual(issued.exception.issues[0].code, "missing_canon")
        self.approve(MemoryEvent("late", StoryPosition(5), "timeline", "late", "Cửa đài mở."))
        self.ledger.propose(MemoryEvent("early", StoryPosition(2), "timeline", "early", "Mai vào đài.",
                                        requires=("late",)))
        self.assertEqual(self.ledger.validate("early")[0].code, "timeline_order")

    def test_concurrent_approval_rechecks_current_state_and_retries_are_idempotent(self):
        time = StoryPosition(1, 1)
        for event_id, value in (("one", "Có chìa"), ("two", "Mất chìa")):
            self.ledger.propose(MemoryEvent(event_id, time, "character", "Mai", value, key="chìa"))
            self.assertEqual(self.ledger.validate(event_id), ())

        def attempt(event_id):
            try:
                self.ledger.approve(event_id)
            except MemoryConflict:
                return None
            return event_id

        with ThreadPoolExecutor(max_workers=2) as pool:
            approvals = [result for result in pool.map(attempt, ("one", "two")) if result]
        self.assertEqual(len(approvals), 1)
        self.ledger.approve(approvals[0])
        self.assertEqual(len(self.ledger.journal), 3)
