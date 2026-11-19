# Creative Intelligence cho Novel Engine V4

Các mô-đun trong `novelengine.creative` chạy với thư viện chuẩn Python 3.10+. Có thể gọi trực tiếp từ mã Python với dàn ý V4, bản thảo tiếng Việt và dữ liệu thử trong bộ nhớ.

## TASK 06 · Voice Bible và biên tập

| Trường trong `VoiceBible` | Nội dung |
| --- | --- |
| `pov` | Ngôi kể, khoảng cách trần thuật và điều kiện đổi điểm nhìn |
| `sentence_rhythm`, `paragraph_rhythm` | Cách đổi độ dài câu, chuyển đoạn và đặt điểm rơi |
| `description`, `emotional_tone` | Chi tiết nên chọn, mức miêu tả và sắc thái |
| `interiority`, `dialogue_subtext` | Cách bộc lộ nội tâm và tạo ẩn ý khi đối thoại |
| `avoid_words`, `avoid_structures` | Cụm từ và cách mở câu được dò theo chữ |
| `character_voices` | Các `CharacterVoice` có tên, ngữ vực, cách dùng từ và ẩn ý |
| `situational_voices` | Các `SituationVoice` gắn với tình huống và hướng dẫn đổi giọng |

`VoiceBible.to_markdown()` kết xuất hồ sơ theo dạng tệp giọng văn của V4. Mẫu trinh thám tâm lý có thể chỉnh các mục tình huống cho đối thoại tình cảm, miêu tả fantasy, kinh dị, hành động hoặc thương lượng chính trị. [Voice Bible mẫu](../examples/creative/voice_bible_example.md)

```python
from novelengine.creative.voice_engine import VoiceBible, plan_revision

bible = VoiceBible(pov="Ngôi ba giới hạn theo Mai", avoid_words=("vô cùng",))
draft = (
    "Mai cài khóa cửa.\n\n"
    "Chiếc đèn quả trám chao. Chiếc đèn quả trám tắt. Chiếc đèn quả trám nguội. "
    "Mai cảm thấy vô cùng lo lắng."
)
for item in plan_revision(draft, bible):
    location = item.location
    print(location.paragraph, item.kind, item.evidence, item.suggestion)
    print(item.priority, item.confidence, draft[location.start:location.end])
```

Mẫu trên báo cụm «chiếc đèn quả trám» lặp ba lần và đánh dấu «vô cùng» theo hồ sơ. `analyze_style()` tính tín hiệu theo đoạn, gồm lặp từ, lặp cụm, mở câu trùng, gọi tên cảm xúc trực tiếp, mật độ từ nhấn mạnh, câu kết sáo và độ dài câu quá đều. Lời thoại dùng dấu ngoặc kép hoặc gạch đầu dòng. Có thể truyền `dialogue_speakers={2: "Mai", 3: "Hậu"}` khi đã biết người nói để so phần mở lời.

Chỉ số đoạn bắt đầu từ 1 với dòng trống phân cách đoạn. `start:end` là lát cắt trên chuỗi Python gốc, kể cả khi dấu tiếng Việt được biểu diễn bằng ký tự tổ hợp. Ưu tiên 1 dành cho cụm đối chiếu trực tiếp được với hồ sơ. Mức `medium` dùng cho dấu hiệu đếm được và mức `low` dùng cho nhận xét phụ thuộc giọng kể. Mật độ từ nhấn mạnh dùng danh sách từ và cụm thông dụng. Cần đọc lại trong ngữ cảnh để xác định dụng ý và giá trị biên tập.

## TASK 07 · Dàn ý và Scene Packet

`validate_outline(data)` nhận dict hoặc chuỗi JSON. Kết quả có `issues` với mức độ, mã, đường dẫn và bằng chứng. `require_contract()` trả về hợp đồng khi chỉ có cảnh báo hoặc khi kiểm tra sạch. `to_v4()` trả bản sao cho `parse_outline()` của V4. Định danh cảnh duy nhất trong chương. Alias `scene_id` và ID dạng số được chuẩn hóa thành `id` chuỗi. Các trường tùy chọn đã có của V4 được giữ khi xuất, gồm trường hồ sơ thế giới, hồ sơ nhân vật, đường cong cảm xúc, số từ và ghi chú liên tục. `target_words` dạng chuỗi số được đổi thành số nguyên dương. Giá trị rỗng, `null` và 0 được xử lý như chưa đặt số từ.

JSON Schema mô tả dữ liệu sau chuẩn hóa. `parse_outline()` áp dụng giới hạn chương và cảnh của V4. Python kiểm tra thêm thứ tự và liên kết giữa các trường. [Schema](../examples/creative/outline_contract.schema.json) · [Dàn ý dùng thử với V4 và bộ kiểm tra](../examples/creative/outline_contract_example.json)

| Vị trí | Trường bổ sung |
| --- | --- |
| Gốc `creative` | `initial_conditions`, `initial_knowledge` và `secrets` |
| `initial_knowledge[]` | `character`, `fact_id` và `state` là `known`, `unknown` hoặc `suspected` |
| `secrets[]` | `id` và `reveal_from` gồm `chapter_id` và `scene_id` |
| `scenes[].creative` | `depends_on`, `reveal_secrets`, `forbid_secrets` và `beat_rules` |
| `beat_rules[]` | `beat` đánh số từ 1 trong `beats`, `requires`, `establishes`, `knowledge_used` và `knowledge_learned` |

`depends_on` trỏ tới cảnh xuất hiện trước theo thứ tự mảng, kể cả với ID chương phi số. Trong mỗi beat, bộ kiểm tra xét tiền đề và quyền biết trước, sau đó mới áp dụng điều kiện được thiết lập và kiến thức mới. Mâu thuẫn xác định được gồm mục vừa bắt buộc vừa cấm, mốc ở tương lai, dùng thông tin có trạng thái `unknown` hoặc `suspected` và mở bí mật trước lịch. Thiếu khai báo nguồn tiền đề, quyền biết hay mốc mở bí mật sinh cảnh báo. Kiểm tra nhân quả dựa vào liên kết có cấu trúc do người lập dàn ý cung cấp.

```python
from pathlib import Path

from novelengine.creative.outline_contract import build_scene_packet, validate_outline

source = Path("examples/creative/outline_contract_example.json").read_text(encoding="utf-8")
result = validate_outline(source)
contract = result.require_contract()
packet = build_scene_packet(contract, "001", "01", budget=2200)
print(packet.text, packet.used, packet.omitted_sections)
```

Packet giữ nguyên mục tiêu, các beat, danh sách cần có và cấm, cùng các ràng buộc đã khai báo cho cảnh. Hồ sơ nhân vật và lịch bí mật ở cấp truyện phục vụ kiểm tra. Gói cho Writer chỉ lấy các trường được phép ở cấp cảnh và siêu dữ liệu gọn. Dùng ID bí mật dạng mã để Writer không nhận nội dung qua tên ID.

Ngân sách mặc định 2.200 byte UTF-8 được tính trên chuỗi JSON gửi đi. Có thể truyền `measure` dùng tokenizer của mô hình, kèm `budget` tính theo token. Phần bắt buộc quá ngân sách báo `ScenePacketBudgetError` cùng mức cần thiết. Theo thứ tự, dữ liệu bổ sung gồm tri thức điểm nhìn, giọng văn, tiêu đề cảnh, thể loại và ghi chú kỹ thuật. Mỗi mục bổ sung được giữ nguyên hoặc bỏ hẳn. `omitted_sections` cho biết các mục đã bị rút bớt.

## TASK 08 · Bộ nhớ sự kiện

Một `MemoryEvent` mang ID, `StoryPosition`, lớp dữ liệu, đối tượng và giá trị. Bổ sung `source` để theo dấu người hoặc mô hình, `evidence` để dẫn chứng và `requires` để khai báo các sự kiện đã duyệt phải có trước. `expected_previous` ghi giá trị mà lần chuyển trạng thái phụ thuộc. Dùng chuỗi rỗng khi yêu cầu trước đó chưa có giá trị.

| `kind` | Cách đặt `subject`, `key` và `value` |
| --- | --- |
| `canon` | ID dữ kiện, key rỗng, phát biểu đã xác minh |
| `character` | Nhân vật, thuộc tính như trạng thái, mục tiêu hoặc quan hệ, giá trị mới |
| `knowledge` | Nhân vật, ID dữ kiện, `known`, `unknown` hoặc `suspected` |
| `timeline` | ID mốc, key rỗng, sự việc diễn ra ở vị trí đã ghi |
| `thread` | ID tuyến, thuộc tính như lời hứa hoặc trạng thái, nội dung mới |

`StoryPosition(chapter, scene, beat)` sắp theo thứ tự kể. Vị trí 0 dùng cho trạng thái ban đầu. `contract.scene_position()` ánh xạ ID V4 sang thứ tự chương và cảnh. `snapshot(before=...)` lấy trạng thái ở ngay trước mốc, kể cả khi sự kiện đến sau đã được duyệt trong sổ.

```python
from novelengine.creative.memory_rules import MemoryEvent, MemoryLedger, StoryPosition, rebuild_snapshot

ledger = MemoryLedger()
ledger.propose(MemoryEvent("fact-x", StoryPosition(0), "canon", "X", "Hậu đã đổi ca trực."))
ledger.approve("fact-x")
ledger.propose(MemoryEvent(
    "mai-knows-x", StoryPosition(2, 1, 2), "knowledge", "Mai", "known", key="X",
    source="model", evidence="Beat 1 ghi Mai nhận ra chữ ký của Hậu.",
))
if not ledger.validate("mai-knows-x"):
    ledger.approve("mai-knows-x", reason="Đã đối chiếu tờ phiếu trong cảnh.")
assert ledger.snapshot(before=StoryPosition(2, 1)).known_facts("Mai") == ()
assert rebuild_snapshot(ledger.approved_events()) == ledger.snapshot()
```

`propose()` ghi trạng thái `pending`. `validate()` trả vấn đề cần xử lý. `approve()` kiểm lại trên trạng thái mới nhất dưới khóa trước khi áp dụng. Dữ kiện `known` cần canon đang có hiệu lực và một dẫn chứng được người duyệt xác minh hoặc một mốc học thông tin đã duyệt. `reject()` ghi lý do từ chối. `undo()` ghi quyết định thu hồi vào `journal` sau khi kiểm lại những sự kiện còn hiệu lực. Nếu thay đổi làm thiếu mốc đã duyệt hoặc đổi tiền đề của sự kiện sau, thao tác trả `MemoryConflict` với ID sự kiện bị ảnh hưởng. Bản chụp là dữ liệu chỉ đọc. `rebuild_snapshot()` chiếu lại chuỗi sự kiện đã duyệt.

Khi truyền `memory=ledger` cho `build_scene_packet()`, gói lấy phát biểu canon mà nhân vật điểm nhìn đã biết trước cảnh. Lịch bí mật và `forbid_secrets` còn giới hạn các dữ kiện có thể đưa vào gói. Dữ liệu gốc thuộc sổ trong RAM. Việc ánh xạ lịch sử V4 và lưu bền nằm trong kế hoạch tích hợp.

## TASK 09 · Truy xuất kỹ thuật

`TechniqueNote` lưu tên, mục đích, tình huống, hiệu quả, giới hạn, nguồn và độ tin cậy tùy chọn. Thuộc tính `scene_types`, `genres`, `character_states`, `tension_levels` và `style_issues` làm rõ ngữ cảnh. `SourceReference` ghi xuất xứ cho biên tập viên. Ghi chú có thể gắn `concept_id` để hợp nhất các cách gọi cùng thủ pháp.

`rank_techniques()` xếp hạng từ khóa theo bối cảnh tiếng Việt, chấp nhận truy vấn có dấu hoặc không dấu. Các trường mục tiêu, loại cảnh, tâm lý và vấn đề văn phong có trọng số cao hơn thể loại và nhịp căng. Cosine được xếp hạng riêng khi vector cùng mô hình, cùng chiều và hữu hạn. Thứ tự ứng viên FTS5 có thể truyền vào `keyword_order`. Reciprocal Rank Fusion cộng `weight / (60 + rank)` với trọng số 1 cho từ khóa ngữ cảnh, 1 cho ngữ nghĩa và 0,5 cho thứ tự FTS5. Các kênh có dữ liệu tiếp tục hoạt động khi thiếu vector. Độ tin cậy và ID ổn định thứ tự khi điểm hợp nhất bằng nhau.

Các kỹ thuật cùng `concept_id`, cùng tên chuẩn hóa hoặc có từ vựng rất gần nhau được chọn đại diện. Người biên tập có thể gắn hai ID khái niệm khác nhau cho hai kỹ thuật dễ bị lẫn. Ghi chú V4 mới nhập ở trạng thái chưa duyệt. Chỉ các trường ngắn của ghi chú đã duyệt mới đi vào `literary_hints`. Ví dụ có thể chạy bằng `python -m examples.creative.retrieval_example`. [Ví dụ truy xuất tiếng Việt](../examples/creative/retrieval_example.py)

## Kiểm thử

```sh
python -m unittest discover -s tests -v
python -m unittest discover -s tests -p "test_creative_*.py" -v
```

Bộ thử Creative dùng dữ liệu trong bộ nhớ và vector mẫu. Kết quả xác nhận hành vi phần mềm và việc giữ ràng buộc. Đánh giá văn phong cần đọc bản thảo thực tế. [Kế hoạch nối vào V4](CREATIVE_INTEGRATION_PLAN.md)
