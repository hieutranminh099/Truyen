"""Run from the repository root with python -m examples.creative.retrieval_example."""

import json
from pathlib import Path

from novelengine.creative.outline_contract import build_scene_packet, validate_outline
from novelengine.creative.retrieval_engine import RetrievalContext, SourceReference, TechniqueNote, rank_techniques


def main():
    context = RetrievalContext(
        scene_type="điều tra", narrative_goal="giữ lại một manh mối", genre="trinh thám",
        character_state="cảnh giác", tension="tăng chậm", style_issue="giải thích trực tiếp",
    )
    source = SourceReference("Sổ ghi chú biên tập minh họa")
    notes = (
        TechniqueNote(
            "object", "Cho đồ vật đổi ý nghĩa",
            purpose="Giữ lại một manh mối để người đọc đối chiếu.",
            situations=("Cảnh điều tra có vật chứng",),
            expected_effect="Người đọc tự nối hai dấu hiệu đã được đặt trong cảnh.",
            limitations="Dành thời gian cho nhân vật kiểm tra vật chứng.",
            source=source, confidence=0.8, genres=("trinh thám",),
            character_states=("cảnh giác",), tension_levels=("tăng chậm",),
            style_issues=("giải thích trực tiếp",), reviewed=True,
        ),
        TechniqueNote(
            "silence", "Để im lặng ngắt nhịp",
            purpose="Cho người nói thời gian cân nhắc trước câu hỏi.",
            situations=("Đối thoại căng thẳng trong cảnh điều tra",),
            expected_effect="Một nhịp chờ làm đổi thế chủ động.",
            source=source, reviewed=True,
        ),
    )
    matches = rank_techniques(notes, context)
    outline_path = Path(__file__).with_name("outline_contract_example.json")
    contract = validate_outline(outline_path.read_text(encoding="utf-8")).require_contract()
    packet = build_scene_packet(contract, "001", "01", techniques=(match.note for match in matches))
    print(json.dumps(json.loads(packet.text), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
