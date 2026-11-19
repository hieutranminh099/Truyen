# Creative Intelligence V4.1 — chế độ có chủ đích, nguồn dữ liệu được duyệt

## Trạng thái và kích hoạt

V4 và dự án đã có bản thảo **giữ nguyên hành vi hiện có**. Creative mode mặc định tắt. Với một dự án **mới, chưa có scene/canon**, mở Trí nhớ truyện → Creative Intelligence → **Bật Creative** hoặc gọi POST `/api/project/<id>/creative-enable` với `{"confirm":true}`. Không có đường tự động chuyển dữ kiện V4 đã viết vì gán nguồn, quyền biết và thứ tự phải được tác giả đối chiếu.

Sau khi bật, dự án có hai SQLite được backup cùng mốc bằng cơ chế Issue #11; Creative sidecar mất hoặc hỏng khiến ứng dụng từ chối thay vì tạo lại sổ rỗng.

## Các điểm nối runtime

- **Outline Contract:** mỗi lần chuẩn bị Writer, dàn ý phải qua `validate_outline`, giữ nguyên ID/thứ tự cảnh đã gắn ledger. Thay đổi layout bị chặn khi Creative đang bật.
- **Voice Bible:** `adapt_voice` đưa Markdown tác giả vào gói Creative; phân tích phong cách có thể gợi ý thêm cho lượt Editor, không sửa bản thảo trực tiếp.
- **Story Memory:** Writer chỉ nhận sự kiện đã duyệt, thuộc thời điểm thích hợp và đã được nhân vật POV biết. Sự kiện nguồn stale (`scene_versions.id` khác) làm Writer dừng để đối chiếu. Nếu ledger đổi revision trong lúc AI suy luận thì cảnh chưa được commit, giữ checkpoint hợp lệ.
- **Creative RAG:** tài liệu nhập V4 vẫn dùng cho tìm kiếm, nhưng chỉ những ghi chú `TechniqueNote(reviewed=True)` được tác giả thêm ở giao diện Creative mới có thể vào Writer, theo ngân sách Scene Packet. Nội dung tác phẩm tham khảo không vào Writer.
- **Critic/Editor:** tiếp tục dùng bộ kiểm tra JSON Critic, độ dài tối thiểu, `must_include` và cơ chế resume đã qua QA-01/02.

## Duyệt dữ kiện

Trong giao diện tối, tạo một sự kiện (`canon`, `timeline`, `character`, `knowledge`, `thread`), ghi ID chủ thể, key và giá trị; tùy chọn gắn `chapter_id/scene_id` **đã có phiên bản**. Sự kiện phải được **Duyệt** trước khi xuất hiện trong Writer. Quyết định Từ chối/Thu hồi đều được giữ trong nhật ký.

Các đề xuất Summary V4 vẫn được ghi vào `story.db`, nhưng **không tự chuyển thành Canon Creative**. Có thể dùng nút **Nhập để duyệt**: người biên tập chọn scene nguồn, nhập ánh xạ `subject/key/value` nếu cần; sự kiện được ghi vào sidecar ở trạng thái **pending** để kiểm tra lần nữa. API legacy `/memory-action` bị khóa khi Creative enabled để tránh hai nguồn phán quyết trái nhau.

## Thiết kế giao dịch

Một thao tác sửa cảnh cập nhật `story.db`, một quyết định Creative cập nhật **chỉ** `creative-memory.sqlite3`. Không có nhánh mã mới cố commit cả hai DB trong cùng một quyết định: khi đọc cảnh nguồn và commit ledger, dùng khóa ghi theo dự án; tác vụ AI được tính ngoài khóa nhưng đối chiếu revision khi lưu. Với mô hình này không phát sinh giao dịch viết phân tán cần hai pha hoặc operation_id. Nếu thêm mirror giữa hai kho trong tương lai, bắt buộc bổ sung journal và phục hồi idempotent trước khi bật.

## Giới hạn nghiệm thu

Các bài CI chạy FakeAI và HTTP fixture trên Windows/Ubuntu. Không chạy GPU trên laptop và chưa chứng minh chất lượng văn học của Qwen3 8B. Lượt QA thật cần sandbox riêng, không dùng `D:\\Truyen\\data`; đánh giá POV/knowledge, trùng cảnh, tính mạch lạc, backup/restore sau restart và bảo mật Tailscale/Android.

API cho biên tập viên:
- GET `/api/project/<id>/creative`
- POST `/api/project/<id>/creative-propose`
- POST `/api/project/<id>/creative-action`
- POST `/api/project/<id>/creative-import`
- POST `/api/project/<id>/creative-note`

Mọi yêu cầu cần `X-Novel-Token`; cập nhật state qua POST có kiểm tra Origin giống backend V4.
