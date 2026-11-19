# Phát triển Novel Engine

- Đọc README_VI.md và IMPLEMENTATION_STATUS.md trước khi thay đổi kiến trúc hoặc quy trình chạy.
- Giữ tương thích Python 3.10 trở lên và Windows. Ưu tiên thư viện chuẩn Python. Bảo toàn checkpoint, dữ liệu dự án và API công khai.
- Dùng dữ liệu thử riêng qua NOVEL_DATA_DIR. Giữ mặc định localhost và cloud tắt. Bảo vệ token, khóa API và dữ liệu người dùng.
- Chạy `python -m unittest discover -s tests -v` và `node --check static/app.js`. Thêm bài hồi quy cho lỗi đã tái hiện. Ghi rõ giả lập và nghiệm thu trên thiết bị thật.
- Mở pull request theo từng phạm vi. Ghi lệnh, kết quả và giới hạn kiểm thử. Chờ duyệt trước khi hợp nhất.
