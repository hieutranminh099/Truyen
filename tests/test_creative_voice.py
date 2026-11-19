import unicodedata
import unittest

from novelengine.creative.style_analyzer import analyze_style
from novelengine.creative.voice_engine import CharacterVoice, SituationVoice, VoiceBible, plan_revision


class VoiceTests(unittest.TestCase):
    def test_repetition_locations_and_confidence_in_vietnamese(self):
        draft = (
            "  An đặt bát.\r\n\r\n"
            "  Chiếc đèn quả trám chao. Chiếc đèn quả trám tắt. Chiếc đèn quả trám nguội.  "
        )
        findings = {item.kind: item for item in analyze_style(draft)}
        self.assertEqual(set(findings), {"phrase_repetition", "word_repetition", "repeated_opening"})
        for item in findings.values():
            self.assertEqual(item.location.paragraph, 2)
            self.assertTrue(draft[item.location.start:item.location.end].startswith("Chiếc"))
            self.assertTrue(draft[item.location.start:item.location.end].endswith("nguội."))
            self.assertIn(item.confidence, {"low", "medium"})
        self.assertIn("lặp 3 lần", findings["phrase_repetition"].evidence)

    def test_emotion_modifiers_and_cliche_are_low_confidence(self):
        draft = (
            "An cảm thấy rất buồn. Căn phòng vô cùng tối. "
            "Chiếc đồng hồ thực sự im ắng. Không gì còn như trước."
        )
        findings = {item.kind: item for item in analyze_style(draft)}
        for kind in ("direct_emotion", "modifier_density", "stock_ending"):
            self.assertEqual(findings[kind].confidence, "low")
            self.assertTrue(findings[kind].suggestion)

    def test_rhythm_requires_several_complete_prose_sentences(self):
        draft = "An kéo then cửa. Tấm ván nứt đôi. Mưa gõ vào hiên. Gió lùa qua tóc. Con mèo chạy mất."
        self.assertIn("uniform_rhythm", {item.kind for item in analyze_style(draft)})
        self.assertFalse(analyze_style("An nhấc ấm. Nước tràn qua miệng chén."))
        self.assertFalse(analyze_style("— Tôi cảm thấy rất buồn."))

    def test_similar_dialogue_uses_attribution_when_available(self):
        draft = '“Tôi không biết phải làm gì.”\n\n— Tôi không biết phải đi đâu.'
        self.assertFalse(analyze_style(draft))
        findings = analyze_style(draft, dialogue_speakers={1: "An", 2: "Linh"})
        self.assertEqual([item.kind for item in findings], ["similar_dialogue"])
        self.assertIn("2 người nói", findings[0].evidence)
        third = draft + '\n\n“ Tôi không biết phải tin ai.”'
        self.assertIn("similar_dialogue", {item.kind for item in analyze_style(third)})

    def test_voice_profile_rendering_and_revision_order(self):
        bible = VoiceBible(
            "Ngôi ba giới hạn", sentence_rhythm="Đổi nhịp khi căng thẳng",
            avoid_words=("chiếc đèn",), avoid_structures=("từ giây phút đó",),
            character_voices=(CharacterVoice("An", "Thân mật", "Gọi bạn bằng tên"),),
            situational_voices=(SituationVoice("Điều tra", "Ghi nhận vật chứng cụ thể"),),
        )
        text = unicodedata.normalize("NFD", "Từ giây phút đó, An nhìn chiếc đèn.")
        plan = plan_revision(text, bible, max_items=1)
        self.assertEqual([item.kind for item in plan], ["restricted_opening"])
        self.assertEqual(plan[0].priority, 1)
        self.assertEqual(text[plan[0].location.start:plan[0].location.end], text)
        self.assertIn("restricted_word", {item.kind for item in plan_revision(text, bible)})
        self.assertIn("**An**", bible.to_markdown())
        self.assertIn("**Điều tra**", bible.to_markdown())
        self.assertEqual(plan_revision(" \n "), ())
