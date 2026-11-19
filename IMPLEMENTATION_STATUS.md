# Tiến độ mã nguồn Novel Engine Hybrid V4 Preview

Ngày tạo: 19/11/2026

| Phân hệ | Có mã nguồn | Kiểm thử giả lập | Mức sẵn sàng |
|---|---|---|---|
| Outline parser v4 + backward compatibility | Có | Có | Dùng thử |
| Writer-Critic-Editor local | Có | Có | Dùng thử / cần đánh giá văn phong |
| SQLite persistent jobs + pause/resume/cancel | Có | Có | Dùng thử |
| Scene history + restore/manual edit | Có | Có (khôi phục, lỗi khi viết lại, sửa đồng thời) | Dùng thử |
| Approved summaries / fact timeline knowledge | Có | Có | Dùng thử / chưa có logic formal |
| TXT MD EPUB source import + legal acknowledgment | Có | Có | Dùng thử |
| Ollama technique distillation + FTS5 + embeddings | Có | Có (FakeAI) | Cần tải model embedding |
| Dark responsive UI | Có | Chromium máy tính và mô phỏng điện thoại | Chưa kiểm tra trên Android thật |
| Optional OpenAI-compatible cloud | Có | Cấu trúc request | Chưa thử các provider thật |
| SillyTavern OpenAI-compatible gateway | Có | HTTP/SSE và Ollama HTTP giả lập | Experimental, no live stream |
| Backup zip, V3 migration | Có | Migration dry-run/apply | Dùng thử, cần sao lưu thủ công trước |
| Model A/B benchmark | Có | Compile | Cần máy người dùng |
| Remote via Tailscale Serve | Hướng dẫn | Chưa | Người dùng tự kết nối |
| Semantic formal logic/proven consistency | Chưa | Chưa | Công việc tương lai |
| True event sourcing with computed state rollback | Chưa | Chưa | Công việc tương lai |
| Automatic SillyTavern World Info synchronization | Chưa | Chưa | Công việc tương lai |
| PWA offline / phone APK | Chưa | Chưa | Công việc tương lai |
| Cloud budget metering/ceiling | Chưa | Chưa | Công việc tương lai |

Nội dung chạy với FakeAI xác nhận đúng luồng phần mềm, KHÔNG xác nhận chất lượng văn chương mô hình trên GPU thật. Đọc README_VI.md trước khi dùng.

## Kiểm tra trên Codex Cloud

- 20 kiểm thử tự động, bao gồm duyệt sớm, xung đột khi tạo tóm tắt, chặn hai worker và hủy viết lại.
- Kịch bản tích hợp qua Chromium và Ollama HTTP giả lập chạy 3 chương / 12 cảnh. Đã kiểm tra khởi động lại giữa cảnh, lỗi HTTP 503, tiếp tục, tạm dừng, duyệt trên màn hình điện thoại mô phỏng, 24 phiên bản cảnh, xuất Markdown và mở lại snapshot SQLite từ ZIP.
- Kiểm tra bổ sung gồm chuyển dự án khi sửa cảnh, nhập và phân tích tài liệu, tạo embedding, cùng luồng SSE gateway chờ lượt gọi Ollama.
- Trạng thái vẫn là Preview. Windows, Ollama/Qwen trên RTX 3050 và Android qua Tailscale cần nghiệm thu trên thiết bị thật.
