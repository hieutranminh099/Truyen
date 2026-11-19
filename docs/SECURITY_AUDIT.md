# Kiểm toán bảo mật P0

| Mức | Vấn đề | Xử lý |
|---|---|---|
| Cao | Kiểm tra tiền tố URL chưa xác thực đúng host loopback. Client cũng có thể đi theo chuyển hướng của nhà cung cấp. | Kiểm tra URL đã phân tích, yêu cầu HTTPS cho cloud ngoài loopback và chặn chuyển hướng. |
| Trung bình | Thông báo HTTP của nhà cung cấp có thể lặp lại dữ liệu riêng tư trong lỗi tác vụ. | Giữ mã trạng thái, bỏ nội dung và chi tiết lỗi kết nối ở phản hồi công khai. |
| Trung bình | Hai tệp XML metadata EPUB chưa giới hạn kích thước trước giải nén. | Giới hạn từng tệp ở 512 kB và từ chối DTD. Vẫn giữ giới hạn XHTML, số tệp và kích thước upload. |
| Trung bình | Sao lưu quét các tệp phụ trong thư mục dự án. | Chỉ thêm DB dự án, dàn ý, Voice Bible và bản thảo Markdown dự kiến. Bỏ liên kết và đường dẫn nằm ngoài thư mục dự án. |
| Thấp | POST chưa kiểm tra Origin khi trình duyệt gửi, số lượng Content-Length hoặc dữ liệu gửi thiếu. | Kiểm tra Origin với Host, xác thực chiều dài và áp dụng thời gian chờ đọc. |

Token giao diện và gateway được kiểm tra riêng. Không cấp CORS. Các ID dự án được kiểm tra trước khi truy xuất đường dẫn. Tệp EPUB được đọc trực tiếp trong ZIP. Kho Git bỏ qua dữ liệu chạy, cơ sở dữ liệu, token và .env.

Dùng Tailscale Serve trong tailnet với ứng dụng bind loopback và giữ quyền truy cập tailnet giới hạn. Quy tắc Origin dựa trên Host được chuyển tiếp, do đó cần kiểm tra khi dùng proxy thực tế. Giữ mã truy cập và API key trong cấu hình cục bộ. Cloud vẫn có thể nhận ngữ cảnh khi người dùng bật tính năng. Giới hạn đọc không thay thế rate limiting cho nhiều kết nối và thư mục dữ liệu cần quyền truy cập cục bộ phù hợp. Chưa nghiệm thu trên Tailscale/Android thật.
