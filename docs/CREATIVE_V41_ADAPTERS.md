# Adapter Creative Intelligence cho backend V4.1

`novelengine.creative.v41_adapters` nhận dữ liệu mà backend đã đọc và dùng các mô-đun Creative của PR #7. `memory_storage` cung cấp một sổ sự kiện riêng có thể mở lại sau khi tiến trình khởi động lại. Các ví dụ dùng thư viện chuẩn và fixture độc lập.

## Hợp đồng Python

| Điểm vào | Đầu vào | Đầu ra |
| --- | --- | --- |
| `adapt_voice(voice, situation=..., characters=...)` | Markdown của `voice_bible.md` hoặc `VoiceBible` có cấu trúc, tên tình huống và nhân vật trong cảnh | `SceneVoice.guidance` cho gói cảnh. `SceneVoice.revision_payload(draft)` trả danh sách nhận xét có `location`, `kind`, `evidence`, `suggestion`, `priority` và `confidence`. |
| `outline_review_payload(validate_outline(value))` | Dict hoặc chuỗi JSON từ dàn ý ứng viên | Dict cho bước duyệt với `outline`, `layout_id`, `issues`. Khi có lỗi chắc chắn, hai trường đầu nhận `None`. |
| `map_v4_memory_row(row, contract, mapping)` | Một dict hoặc `sqlite3.Row` từ `memory_items`, hợp đồng dàn ý và `LegacyMemoryMapping` | `MemoryRecord("propose", ...)` hoặc `None` cho hàng đã bị từ chối hay thu hồi. |
| `adapt_v4_retrieval(context, hits, reviewed_notes=...)` | `RetrievalContext`, các hit từ khóa V4 có `id`, `technique` và `source` tùy chọn, cùng ghi chú do biên tập viên duyệt | `RetrievedTechniques` với `review_matches`, `writer_matches` và số hit lỗi hoặc trùng ID. Có thể thêm `query_embedding` để xếp hạng ghi chú có vector cùng mô hình. |
| `prepare_scene(contract, chapter_id, scene_id, project_id=...)` | Hợp đồng hợp lệ, ID cảnh, ID dự án và các đầu vào tùy chọn `memory`, `scene_revisions`, `voice`, `retrieval`, `budget` và `measure` | `PreparedScene` chứa gói có số đo ngân sách, phần lược bỏ và revision của sổ đã đọc. `as_pipeline_result()` trả `(text, hints)` theo dạng mà `process_scene()` đang nhận. |

Markdown được trả nguyên văn cho bên gọi. Hồ sơ có cấu trúc giữ hướng dẫn chung và chọn thêm giọng nhân vật cùng tình huống được truyền vào. Tên được so theo Unicode chuẩn hóa và bỏ qua khác biệt hoa thường. Vị trí nhận xét dùng chuỗi bản nháp ban đầu. Adapter dàn ý giữ các vấn đề từ validator cho người duyệt, gồm cả cảnh báo khi còn thiếu bằng chứng.

Ánh xạ bộ nhớ cần `id`, `kind`, `status`, `source` và `chapter` của hàng V4. `subject` trong mapping là ID dữ kiện, ID mốc, ID tuyến hoặc tên nhân vật đích. `key` là thuộc tính hoặc ID dữ kiện đối với quyền biết. Với canon, timeline, trạng thái nhân vật và tuyến truyện, có thể dùng `content` làm giá trị. Quyền biết cần giá trị rõ ràng là `known`, `unknown` hoặc `suspected`. Hàng theo chương cần `scene_id` và ID `scene_revision` lấy từ cảnh nguồn. `beat` là số thứ tự trong cảnh, với 0 là đầu cảnh. Hàng có `chapter=""` dùng vị trí khởi đầu. ID sự kiện `v4-memory:<id>` ổn định khi chạy lại. Hàng V4 mang trạng thái `approved` cũng vào sổ dưới dạng đề xuất để người duyệt xác nhận ánh xạ và bằng chứng. Quyền biết trong gói cảnh lấy từ sổ đã duyệt.

Đầu vào RAG dùng thứ tự hit từ khóa V4. Việc ghép hạng do `rank_techniques()` thực hiện. Chỉ ghi chú đã duyệt mới có ở `writer_matches`. `hints` trong kết quả pipeline là các trường kỹ thuật đã thực sự được đưa vào gói theo ngân sách. Lỗi `ScenePacketBudgetError` mang ngân sách và số đơn vị cảnh bắt buộc cần, phục vụ bước báo lỗi trước khi gọi Writer. Mặc định đo byte UTF-8. Khi truyền bộ đếm token, trừ phần dành cho chat template, system prompt, dữ liệu riêng của từng vai trò và đầu ra.

## Sổ bền theo dự án

`SQLiteMemoryStore(project_dir, project_id=..., layout_id=...)` mở `creative-memory.sqlite3` trong thư mục dự án đã tồn tại. Sidecar có định dạng 1 và ràng buộc với ID dự án cùng thứ tự ID chương/cảnh của hợp đồng. `layout_id` đổi khi chèn, xóa, đổi ID hoặc đổi thứ tự chương/cảnh. Sửa văn bản dưới cùng ID dùng kiểm tra phiên bản cảnh. Nếu đổi thứ tự dàn ý, cần đối chiếu lại `StoryPosition` và các quyền biết trước khi tạo sổ cho thứ tự mới.

- Sổ mới được chuẩn bị trong thư mục tạm cùng hệ thống tệp. Sau khi commit và đóng kết nối, một tiến trình công bố tệp hoàn chỉnh bằng thao tác chỉ thành công khi tên đích còn trống. Tiến trình gặp tên đích đã có sẽ kiểm tra sổ đó ở chế độ chỉ đọc.
- Khi mở sổ có sẵn, tệp rỗng, tệp bị cắt, định dạng SQLite sai, lược đồ sai hoặc định danh sai trả `MemoryStorageError`. Kiểm thử đối chiếu từng byte của tệp trước và sau khi mở bị từ chối.
- `read()` trả `StoredMemory` ở một revision đã commit, với `journal`, `status()`, `validate()`, `approved_events()` và `snapshot(before=...)`. Bản đọc dùng được sau khi đóng kết nối.
- `commit(records, expected_revision=...)` nhận một lô đề xuất và quyết định. Giao dịch `BEGIN IMMEDIATE` nạp sổ mới nhất, kiểm tra phụ thuộc và ghi thêm toàn bộ lô. Lỗi khi duyệt hoặc ghi SQLite làm rollback cả lô. Revision là số bản ghi đã commit. Có thể dùng revision lúc mở phiếu duyệt để phát hiện thay đổi đồng thời.
- Thử lại cùng đề xuất và quyết định trên cùng trạng thái giữ nguyên nhật ký. Khi gặp `StaleMemoryRevision`, đọc lại rồi kiểm tra các thay đổi trước khi áp dụng quyết định. `MemoryConflict` giữ thông tin về sự kiện bị ảnh hưởng. Khi mở lại, sổ phục hồi chuỗi quyết định và kiểm tra trạng thái duyệt hiện tại.
- Khi cung cấp `scene_revisions`, dùng khóa `contract.scene_position(chapter_id, scene_id)` và giá trị `MAX(scene_versions.id)` từ V4. Adapter đối chiếu các sự kiện đã duyệt trước cảnh cần viết có gắn phiên bản nguồn. Thiếu mốc hoặc phiên bản khác trả `StaleMemorySource` cùng ID sự kiện để xem xét. `scene_revisions=None` dùng cho bản xem thử độc lập với database dự án.

Ví dụ chạy từ gốc repository với dự án giả lập.

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from novelengine.creative.memory_rules import MemoryRecord
from novelengine.creative.memory_storage import SQLiteMemoryStore
from novelengine.creative.outline_contract import validate_outline
from novelengine.creative.v41_adapters import LegacyMemoryMapping, adapt_voice, map_v4_memory_row, prepare_scene
from novelengine.outline import sample_outline

contract = validate_outline(sample_outline()).require_contract()
row = {
    "id": 7, "kind": "fact", "status": "approved", "source": "manual",
    "chapter": "", "content": "Bến đò đóng cửa lúc sáu giờ.",
}
proposal = map_v4_memory_row(row, contract, LegacyMemoryMapping("ben-do-gio-dong"))
with TemporaryDirectory() as directory:
    store = SQLiteMemoryStore(Path(directory), project_id="demo", layout_id=contract.layout_id)
    revision = store.commit([proposal], expected_revision=0)
    assert store.read().status(proposal.event_id) == "pending"
    store.commit(
        [MemoryRecord("approve", proposal.event_id, reason="Đã đối chiếu hồ sơ thế giới.")],
        expected_revision=revision,
    )
    result = prepare_scene(
        contract, "001", "01", project_id="demo", memory=store.read(),
        voice=adapt_voice("Giữ lời thoại ngắn."), scene_revisions={},
    )
    text, hints = result.as_pipeline_result()
    print(result.memory_revision, result.packet.used, len(hints))
```

## Điểm nối đề xuất để Tổng điều phối duyệt

1. Hiển thị kết quả adapter khi người biên tập nhận dàn ý ứng viên và dùng quy trình lưu V4 hiện có khi chấp nhận. Đọc `voice_bible.md` để chuẩn bị gói cảnh. Hiển thị đề xuất biên tập theo đoạn sau bản nháp hoặc bổ sung chúng vào lượt Editor đang có.
2. Sau khi chọn cảnh trong `pipeline.scene_packet()`, nạp một revision của sidecar và các phiên bản cảnh nguồn trong một lượt đọc nhất quán của mỗi kho. Dùng `prepare_scene()` và trả nguyên chuỗi JSON của gói. Dùng các cổng QA-01/QA-02 cho smoke test, kiểm tra phản hồi, ngưỡng độ dài, checkpoint và tóm tắt. Khi lưu, đối chiếu lại revision của sổ và phiên bản cảnh nguồn đã dùng, cùng phiên bản cảnh đích mà V4 đang kiểm tra.
3. Gọi `rag.find_techniques(..., ai=None)` lấy thứ tự từ khóa và truyền hit cùng danh sách ghi chú đã biên tập vào adapter. Chỗ gọi Writer cần truyền quy tắc coi ghi chú là dữ liệu tham khảo và vận dụng thủ pháp bằng tình tiết của truyện hiện tại.
4. Sau khi giao dịch V4 ghi thành công tóm tắt cùng đề xuất, worker đọc lại hàng theo ID và chuẩn bị ánh xạ. Dùng ID ổn định để chạy lại khi tiến trình dừng giữa hai lượt ghi. Chọn sổ Creative làm nguồn quyết định duyệt cho các mục đã ánh xạ trong chế độ thử. Mỗi lần sửa, phục hồi hoặc đổi phiên bản cảnh cần so phiên bản nguồn, rồi trình biên tập viên xét các sự kiện bị ảnh hưởng. V4 và sidecar có giao dịch riêng. Cơ chế đọc lại và đối chiếu cũng cần chạy sau khi khởi động lại.
5. Đưa sidecar vào kế hoạch sao lưu theo dự án bằng SQLite Backup API. Khôi phục cặp bản sao cùng mốc rồi kiểm tra ID, thứ tự và các phiên bản cảnh. Ca thử trong PR dùng thư mục tạm và so sánh nội dung byte của một `story.db` bên cạnh sidecar.

## Kiểm thử độc lập

```sh
python -m unittest discover -s tests -p 'test_creative_*.py' -v
python -m unittest discover -s tests -v
```

Bộ thử adapter dùng hàng V4 giả lập, Markdown, ghi chú tiếng Việt, vector mẫu và tệp SQLite tạm. Nó kiểm tra phối hợp các đầu vào, cách ly dữ kiện theo điểm nhìn và thời điểm, thay đổi phiên bản nguồn, mở lại nhật ký, retry, ghi đồng thời và rollback. [Thiết kế Creative gốc](CREATIVE_INTEGRATION_PLAN.md)
