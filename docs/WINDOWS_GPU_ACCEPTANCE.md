# Nghiệm thu Windows và Ollama

**Trạng thái: Chưa nghiệm thu trên RTX 3050 thực tế.**

Chạy từ thư mục mã nguồn bằng Python 3.10 trở lên. Trong CMD hoặc PowerShell, dùng `python smoke_windows.py` để kiểm tra offline. Script tạo một thư mục tạm riêng và dùng Ollama HTTP giả lập. Nó xác minh lỗi HTTP 503, tiếp tục cùng tác vụ, lưu nháp/nhận xét/biên tập trong SQLite và đối chiếu Markdown đã xuất.

Để thử trên Windows với mô hình thật, bật Ollama và chạy:

```powershell
ollama pull qwen3:8b
ollama list
nvidia-smi
$env:NOVEL_MODEL = 'qwen3:8b'
python smoke_windows.py --real
ollama ps
```

Trong CMD có thể dùng `set NOVEL_MODEL=qwen3:8b`. Kiểm tra đúng GPU và mức GPU/CPU trong `ollama ps`. Báo cáo JSON ghi hệ điều hành, Python, NVIDIA nếu có, mô hình, giới hạn sinh, thời gian gồm tóm tắt và độ dài cảnh. Thời gian giả lập chỉ phục vụ kiểm tra phần mềm. Lưu kết quả ngoài kho mã. Smoke test không dùng dự án và khóa đang có, đồng thời tắt cloud.

Nghiệm thu giao diện riêng trên Android bằng địa chỉ HTTPS của Tailscale Serve. Dùng mạng di động, kiểm tra mở giao diện, duyệt một cảnh, mất kết nối rồi trở lại. Sau đó dừng Tailscale trên điện thoại để xác nhận địa chỉ nội bộ không truy cập được qua Internet công khai.
