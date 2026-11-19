import json
import unittest
from copy import deepcopy
from pathlib import Path

from novelengine.creative.outline_contract import ScenePacketBudgetError, build_scene_packet, validate_outline
from novelengine.outline import parse_outline, sample_outline


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "creative" / "outline_contract_example.json"


class OutlineContractTests(unittest.TestCase):
    def setUp(self):
        self.example = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def test_sample_and_extended_outline_are_v4_compatible(self):
        for source in (sample_outline(), self.example, EXAMPLE.read_text(encoding="utf-8")):
            with self.subTest(source_type=type(source)):
                report = validate_outline(source)
                self.assertEqual(report.issues, ())
                exported = report.require_contract().to_v4()
                self.assertEqual(parse_outline(exported), exported)

    def test_normalization_preserves_input_and_legacy_local_scene_ids(self):
        source = {"chapters": [
            {"id": 2, "title": " Tên chương ", "scenes": [
                {"scene_id": 1, "goal": " Tìm dấu vết ", "beats": [" Kiểm tra cửa "], "target_words": " 350 "}
            ]},
            {"id": 1, "title": "Sau đó", "scenes": [{"id": 1, "goal": "Rời đi", "beats": ["Đóng cửa"]}]},
        ]}
        original = deepcopy(source)
        contract = validate_outline(source).require_contract()
        normalized = contract.to_v4()
        first = normalized["chapters"][0]["scenes"][0]
        self.assertEqual((first["id"], first["goal"], first["beats"], first["target_words"]),
                         ("1", "Tìm dấu vết", ["Kiểm tra cửa"], 350))
        self.assertEqual(source, original)
        first["goal"] = "Sửa ngoài hợp đồng"
        self.assertEqual(json.loads(build_scene_packet(contract, "2", "1").text)["goal"], "Tìm dấu vết")

    def test_duplicate_ids_missing_goal_and_bad_word_target(self):
        chapter = self.example["chapters"][0]
        duplicate = deepcopy(chapter["scenes"][0])
        duplicate.update(goal=" ", target_words=-5)
        chapter["scenes"].append(duplicate)
        self.example["chapters"][1]["id"] = chapter["id"]
        report = validate_outline(self.example)
        self.assertIsNone(report.contract)
        self.assertTrue({"duplicate_chapter_id", "duplicate_scene_id", "missing_scene_goal", "invalid_target_words"}
                        .issubset({issue.code for issue in report.issues}))
        with self.assertRaises(ValueError):
            report.require_contract()

    def test_knowledge_preconditions_and_reveals_are_checked_in_order(self):
        first = self.example["chapters"][0]["scenes"][0]
        first["must_include"].append(" TÊN   NGƯỜI ĐÃ ĐỔI CA ")
        first["creative"]["reveal_secrets"] = ["X01"]
        first["creative"]["depends_on"] = [{"chapter_id": "002", "scene_id": "01"}]
        first["creative"]["beat_rules"][0].update(
            requires=["mai_co_phieu"],
            knowledge_used=[{"character": "mai", "fact_id": "X01"}],
        )
        report = validate_outline(self.example)
        errors = {issue.code for issue in report.issues if issue.severity == "error"}
        self.assertTrue({"contradictory_constraint", "contradictory_secret", "early_reveal",
                         "future_dependency", "unmet_precondition", "knowledge_violation"}.issubset(errors))
        self.assertIsNone(report.contract)

    def test_unverified_conditions_and_knowledge_are_warnings(self):
        first_rule = self.example["chapters"][0]["scenes"][0]["creative"]["beat_rules"][0]
        first_rule["requires"].append("thay_den")
        first_rule["knowledge_used"] = [{"character": "Mai", "fact_id": "X02"}]
        report = validate_outline(self.example)
        self.assertIsNotNone(report.contract)
        self.assertEqual({(item.code, item.severity) for item in report.issues},
                         {("undeclared_precondition", "warning"), ("unverified_knowledge", "warning")})

    def test_learning_occurs_after_knowledge_use_in_same_beat(self):
        rule = self.example["chapters"][1]["scenes"][0]["creative"]["beat_rules"][0]
        rule["knowledge_used"] = list(rule["knowledge_learned"])
        self.assertIn("knowledge_violation", {item.code for item in validate_outline(self.example).issues})

    def test_bad_shapes_do_not_raise_from_validator(self):
        sources = ("{[", "[]", {"chapters": False}, deepcopy(self.example))
        sources[-1]["chapters"][0]["scenes"][0]["creative"]["beat_rules"][1]["establishes"] = 4
        for source in sources:
            with self.subTest(source=type(source)):
                self.assertIsNone(validate_outline(source).contract)

    def test_packet_budget_and_allowlist_keep_constraints_intact(self):
        second = self.example["chapters"][1]["scenes"][0]
        rule = second["creative"]["beat_rules"][0]
        rule["knowledge_learned"][0]["private_note"] = "chi tiết chưa công bố"
        contract = validate_outline(self.example).require_contract()
        baseline = build_scene_packet(contract, "002", "01")
        packet = build_scene_packet(
            contract, "002", "01", budget=baseline.used + 100,
            approved_pov_context=["x" * 2500, "Tờ phiếu đã được duyệt."], voice_guidance="y" * 2500,
        )
        data = json.loads(packet.text)
        self.assertEqual(data["must_include"], second["must_include"])
        self.assertEqual(data["continuity_requirements"], second["continuity_requirements"])
        self.assertEqual(data["creative"]["reveal_secrets"], ["X01"])
        self.assertEqual(data["approved_pov_context"], ["Tờ phiếu đã được duyệt."])
        self.assertEqual(set(packet.omitted_sections), {"approved_pov_context", "voice_guidance"})
        self.assertEqual(packet.used, len(packet.text.encode("utf-8")))
        self.assertLessEqual(packet.used, baseline.used + 100)
        for private in ("private_note", "initial_knowledge", "Đã đổi ca trực cho chị mình"):
            self.assertNotIn(private, packet.text)
        with self.assertRaises(ScenePacketBudgetError) as raised:
            build_scene_packet(contract, "002", "01", budget=1, measure=len)
        self.assertGreater(raised.exception.required, 1)
