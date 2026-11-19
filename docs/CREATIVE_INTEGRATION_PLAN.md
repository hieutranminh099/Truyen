# Kế hoạch tích hợp với Novel Engine V4

Nhánh Creative cung cấp API Python để Tổng điều phối chạy thử theo từng cảnh. Các đoạn mã dưới đây dùng cho đợt tích hợp sau nghiệm thu. Phạm vi PR gồm gói `novelengine/creative`, kiểm thử riêng, tài liệu và ví dụ.

## Dàn ý và các bước Writer, Critic, Editor

V4 đang dùng `parse_outline()` trong `store.save_outline()` và đọc lại bằng `load_outline()`. Có thể gắn bộ kiểm tra ở bước nhận dàn ý ứng viên và trả `issues` cho người biên tập. Dàn ý hợp lệ có thể xuất thành dict cho luồng lưu hiện tại.

```python
from novelengine.creative.outline_contract import validate_outline

review = validate_outline(director_output)
contract = review.require_contract()
normalized_for_v4 = contract.to_v4()
review_notes = review.issues
```

Trong `pipeline.scene_packet()`, V4 hiện gom metadata, hồ sơ nhân vật, canon đã duyệt, tóm tắt, đoạn viết gần đây và các kết quả `rag.find_techniques()`. Tại điểm nối mới, chọn đúng ID cảnh và truyền sổ sự kiện của dự án cho bộ dựng gói. Trả về cùng dạng `(text, techniques)` mà `process_scene()` đang dùng.

```python
import json

from novelengine.creative.outline_contract import build_scene_packet

packet = build_scene_packet(
    contract, ch["id"], sc["id"], memory=ledger,
    voice_guidance=scene_voice, techniques=(hit.note for hit in ranked_reviewed_notes),
    budget=input_budget, measure=count_model_tokens,
)
return packet.text, json.loads(packet.text).get("literary_hints", [])
```

Tính `input_budget` sau khi dành chỗ cho system prompt, chỉ dẫn vai trò, lớp chat template, dữ liệu đặc thù từng lượt và phần sinh văn bản. V4 mặc định `num_ctx=4096` và dành khoảng 1.300 token đầu ra cho Writer. Khi đổi tokenizer hoặc dùng Critic và Editor với bản nháp kèm theo, tính lại ngân sách cho từng lượt. Xử lý `ScenePacketBudgetError` trước lúc gọi mô hình để người lập dàn ý có thể rút ngắn phần bắt buộc. Truyền chuỗi gói hoàn chỉnh để các đoạn JSON và giới hạn luôn còn nguyên.

Ở bước Voice, hồ sơ `VoiceBible.to_markdown()` đưa vào trường Markdown hiện có của dự án, hoặc lấy hướng dẫn ngắn theo tình huống cho `voice_guidance`. Chạy `plan_revision(draft, bible)` khi đã có nháp. Có thể hiển thị đề xuất theo đoạn hoặc gửi riêng đoạn được chọn cùng nhận xét cho Editor. Điều phối việc lưu bản nháp, soát, sửa và checkpoint qua `process_scene()`.

## Ánh xạ bộ nhớ V4

`story.db` của V4 có `memory_items`, `summaries` và `memory_audit`. Lõi Creative hoạt động trên `MemoryLedger` trong RAM. Đợt tích hợp sau cần quyết định cách lưu chuỗi quyết định và cách gắn sự kiện với phiên bản cảnh.

| Dữ liệu V4 | Ánh xạ được đề xuất |
| --- | --- |
| `fact` đã duyệt | Gắn ID dữ kiện, vị trí và bằng chứng để tạo sự kiện `canon` |
| `timeline`, `character`, `thread` | Lập ID mốc, thuộc tính hoặc tuyến ổn định và khai báo phụ thuộc đã xác định |
| `knowledge` | Xác định nhân vật, ID canon, trạng thái và mốc học thông tin trước khi duyệt |
| `pending` và đề xuất từ bản nháp | Giữ làm sự kiện `pending` để kiểm tra và duyệt bằng thao tác riêng |
| `summaries` | Dùng để tìm bằng chứng. Quyền biết và trạng thái được lấy từ các sự kiện đã duyệt |

Thứ tự được lấy từ dàn ý của phiên bản đang dùng. Nếu sắp lại chương, ánh xạ lại vị trí sự kiện và kiểm tra các phụ thuộc trước khi dùng hợp đồng mới. Khi sửa lại cảnh, xác định sự kiện gắn với phiên bản cũ. Có thể thu hồi từng mục qua `undo()`. `MemoryConflict` chỉ ra các quyết định tiếp nối cần biên tập viên xem lại trước khi áp dụng. Khi một lần sửa ảnh hưởng nhiều sự kiện, phần tích hợp cần một giao dịch cho cả bản sửa và loạt quyết định liên quan. Trạng thái được xây từ các ID đã duyệt và còn hiệu lực.

Chỉ truyền ledger của dự án đang viết vào Scene Packet. Nếu bổ sung dòng thông tin qua `approved_pov_context`, áp dụng cùng giới hạn điểm nhìn, thời điểm và lịch bí mật như dữ liệu tự động. Lớp Creative dùng ID sự kiện ổn định và nhật ký quyết định làm đầu vào cho thiết kế lưu bền.

## Đọc kết quả từ `novelengine.rag`

V4 đã có luồng nhập TXT, Markdown và EPUB, quyền sử dụng, chia đoạn, bảng `chunks`, phân tích kỹ thuật, FTS5 và embedding. `find_techniques()` trả ID đoạn, tên nguồn và JSON kỹ thuật. Có thể dùng nó lấy ứng viên FTS5 và dùng lớp Creative để xếp hạng lại. Mỗi hit chuyển được giữ cho công cụ rà duyệt. Ghi chú đã biên tập ghép lại theo ID.

```python
from novelengine.creative.retrieval_engine import (
    RetrievalContext, rank_techniques, technique_from_v4_hit,
)
from novelengine.rag import find_techniques

context = RetrievalContext(
    scene_type="điều tra",
    narrative_goal=sc["goal"],
    genre=genre_label,
    character_state="cảnh giác",
    tension="tăng chậm",
    style_issue="đối thoại thiếu ẩn ý",
)
legacy_hits = find_techniques(project_id, context.query_text(), ai=None, top_k=30)
legacy_notes = [note for hit in legacy_hits if (note := technique_from_v4_hit(hit)) is not None]
ranked_for_review = rank_techniques(
    legacy_notes, context, keyword_order=(note.note_id for note in legacy_notes),
)
# reviewed_notes được biên tập viên duyệt và có thể chứa ứng viên lấy ngoài FTS5.
ranked_reviewed_notes = rank_techniques(
    (note for note in reviewed_notes if note.reviewed),
    context, keyword_order=(note.note_id for note in legacy_notes),
)
```

`technique_from_v4_hit()` chỉ đọc tên kỹ thuật, tình huống, giới hạn và nhãn nguồn. Với JSON thiếu hoặc bị cắt, adapter bỏ qua hit. Bản ghi dùng cho Writer cần được biên tập thành hướng dẫn khái quát, có thể dùng lại với bối cảnh và tình tiết của truyện đang viết, rồi đánh dấu `reviewed=True`. Các trường được đưa vào gói là `name`, `purpose`, `expected_effect` và `limitations`. Tên nguồn chỉ phục vụ truy vết khi rà duyệt. Lời nhắc hệ thống của Writer nên chỉ rõ ghi chú kỹ thuật là dữ liệu tham khảo, bỏ qua mệnh lệnh có trong nguồn và diễn đạt bằng tình tiết của tác phẩm hiện tại.

Nếu muốn có ngữ nghĩa, truyền `Embedding(model_id, values)` cho tập ứng viên và truy vấn, dùng cùng định danh mô hình và phiên bản. Embedding trong V4 có vector nhưng chưa ghi tên mô hình theo từng hàng. Dùng nhánh từ khóa cho các vector thiếu nguồn gốc. Kết hợp thứ tự theo Reciprocal Rank Fusion và lấy các ghi chú đã duyệt có thủ pháp đa dạng trong giới hạn ngân sách của gói.

## Hạng mục cần Tổng điều phối duyệt

1. Nối kiểm tra ứng viên vào nơi nhận dàn ý và đưa Scene Packet vào Writer theo từng dự án.
2. Chọn quy trình duyệt ghi chú kỹ thuật, cấu hình tokenizer và chạy thử với bản nháp tiếng Việt thực tế.
3. Chốt nguồn lưu bền, định danh phiên bản cảnh và giao dịch khi tích hợp các thao tác bộ nhớ.

Các API mẫu và phạm vi kiểm thử được mô tả trong [tài liệu kiến trúc](CREATIVE_ARCHITECTURE.md).
