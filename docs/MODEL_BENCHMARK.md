# Đọc mù và benchmark mô hình

Khởi tạo dự án thử bằng `python -m novelengine projects`. Kiểm tra mô hình có trong `ollama list`, rồi chạy:

```powershell
python benchmark_models.py --project demo --models qwen3:8b,qwen3.5:4b --scenes 12 --seed 457191
```

`qwen3.5:4b` chỉ dùng khi Ollama hiện tại hỗ trợ và đã tải. Dùng `--mock` để kiểm tra xuất tệp mà không gọi mô hình. Dùng `--output` nếu muốn đặt kết quả bên ngoài thư mục dự án. Lần chạy mới luôn tạo thư mục riêng. Dự án dùng cho phép đo nên giữ nguyên dàn ý, Voice Bible và canon trong suốt lần chạy.

Mọi mô hình nhận cùng prompt cho một cảnh và cùng seed, giới hạn ngữ cảnh, độ dài sinh và nhiệt độ. Thứ tự được hoán đổi theo cảnh. Cùng seed hỗ trợ tái chạy, song phiên bản mô hình, Ollama và thiết bị có thể làm đầu ra khác. Thời gian bao gồm yêu cầu sinh văn và có thể gồm nạp mô hình. VRAM là thông số Ollama trả về sau khi sinh, không phải giá trị đỉnh. Bản riêng lưu thời gian, số từ, VRAM nếu có và hash prompt.

Chỉ đưa tệp cảnh và `scores.csv` cho người đọc. Giữ riêng các tệp có chữ `RIENG`. Bảng điểm dùng mã người đọc và 7 tiêu chí: tiếng Việt tự nhiên, lời thoại đúng tính cách, tâm lý, nhân quả, sáng tạo, bám dàn ý, tránh lặp và sáo ngữ. Điểm 1 là có lỗi lớn, 3 là đọc được nhưng cần sửa, 5 là đạt rõ ràng. Dùng điểm 2 và 4 cho mức trung gian. Mỗi người chấm mọi bản của một cảnh. Nếu có thêm người đọc, thêm các dòng cùng cảnh và nhãn với mã người đọc khác.

```powershell
python benchmark_models.py --summarize "đường-dẫn-tới-lần-chạy"
```

Báo cáo JSON/CSV chỉ dùng điểm người nhập và những cảnh đã chấm cho mọi mô hình. Điểm mỗi cảnh là trung bình người đọc. Độ lệch chuẩn mẫu xuất hiện khi có từ hai cảnh chung. Chế độ mô phỏng vẫn giữ nhãn `mock` trong báo cáo. Chưa có kết luận về mô hình tốt nhất trên RTX 3050.
