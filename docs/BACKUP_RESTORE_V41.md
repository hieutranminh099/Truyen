# Backup & Restore V4.1 — cách dùng và ranh giới bảo đảm

## Tạo bản sao lưu
Qua giao diện (Cài đặt → Tạo sao lưu) hoặc POST có xác thực đến `/api/project/<id>/backup`.

Backend giữ khóa ghi theo dự án trong khi chụp SQLite bằng SQLite Backup API rồi sao chép outline, Voice Bible và các tệp xuất. Tất cả thành phần được kiểm tra trong staging. ZIP có manifest phiên bản 1 gồm:
- `project_id`, `snapshot_id`, cờ `creative_enabled`
- `layout_id`, SHA-256 outline, revision ledger (nếu bật), phiên bản nguồn các cảnh
- dung lượng và SHA-256 mỗi tệp

Bản sao lưu Creative có **cả `story.db` và `creative-memory.sqlite3`**. Sidecar thiếu, sai binding, sai revision hoặc hỏng đều dẫn tới lỗi. Dự án V4 không dùng Creative vẫn được backup thành ZIP hợp lệ với cờ `creative_enabled=false`. Các ZIP V4 cũ không có manifest phải được kiểm định thủ công; hệ thống không tự đoán bản thiếu sidecar là đầy đủ.

## Khôi phục vào vùng dữ liệu riêng

Ví dụ trên Windows, KHÔNG dùng `D:\\Truyen\\data` làm đích thử nghiệm:

```powershell
python -m novelengine restore-zip "D:\\Backups\\backup_20261119T120000000000.zip" my-story --data-root "D:\\Novel-Restore-QA"
```

ID `my-story` phải đúng bằng ID trong manifest. Nếu `D:\\Novel-Restore-QA\\projects\\my-story` đã tồn tại, lệnh dừng. Tiến trình kiểm tra CRC, SHA, SQLite integrity, MemoryLedger replay, project/layout binding, revision và tham chiếu cảnh trước khi công bố dự án đích. Các bản đã lỗi vẫn ở staging và được dọn; không ghi đè dự án hiện có.

Có thể dùng API POST `/api/restore-project?id=my-story` với thân yêu cầu là ZIP và header `X-Novel-Token`. Giới hạn upload 128 MiB và chỉ tạo dự án mới trong data root của app đang chạy. Không dùng API này để ghi đè dự án cũ.

## Bật Creative một cách tường minh

Creative **mặc định tắt**. Với dự án vừa tạo, chưa có cảnh/canon, POST `/api/project/<id>/creative-enable` với JSON `{"confirm":true}`. Chỉ khi outline đã được kiểm tra và sidecar hợp lệ mới ghi cờ bền vững. Dự án đã viết trước đó không được tự chuyển sang Creative: cần migration và duyệt riêng.

## Khóa ghi và giới hạn

Khóa SQLite liên tiến trình được các đường ghi backend sử dụng khi cập nhật HTTP, cảnh/chương, RAG, exports và Creative ledger. Lượt AI suy luận thực hiện bên ngoài khóa. Backend **không thể** ngăn chương trình ngoài (SQLite Browser, ứng dụng bên thứ ba, sync file) ghi trực tiếp vào các file dự án mà không phối hợp.

Thiết kế tách giao dịch: việc sửa cảnh cập nhật `story.db`; quyết định Creative cập nhật **chỉ** ledger. Quyền biết/sự kiện được gắn `scene_revision` và so khi chuẩn bị/ghi Writer; không có một thao tác mới bắt buộc commit vào cả hai kho để hoàn tất một quyết định. Nếu sau này thêm mirrored write xuyên kho thì cần bổ sung journal/operation_id và cơ chế khôi phục idempotent trước khi được phép thực hiện.

Bộ QA dùng temp data root, tạo lỗi giữa hai snapshot, kiểm tra ghi xen, ZIP hỏng và khôi phục. Khi đem vào sản xuất, kiểm tra thêm tải thực trên Windows + backup/restore dữ liệu bản sao, không sửa trực tiếp dữ liệu gốc trước nghiệm thu.
