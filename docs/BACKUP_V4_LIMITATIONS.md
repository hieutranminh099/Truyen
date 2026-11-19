# Giới hạn backup V4 khi chưa tích hợp Creative Memory

Backup hiện tại chỉ bảo vệ dữ liệu **V4 truyền thống**. Bản ZIP gồm snapshot SQLite `story.db`, dàn ý, Voice Bible và các bản xuất Markdown; không phải bản backup Creative V4.1 đầy đủ.

## Hành vi an toàn trước khi hoàn thành Issue #11

- Nếu dự án chứa `creative-memory.sqlite3` (kể cả tệp rỗng/bị hỏng), API backup V4 **từ chối và báo lỗi**. Không bao giờ phát hành một ZIP thiếu sidecar mà người dùng tưởng là đầy đủ.
- ZIP V4 được đóng trong staging cùng hệ thống tệp và chỉ được chuyển thành tên backup chính thức sau khi kiểm tra CRC. Lỗi ghi không công bố tệp ZIP dở dang.
- Vì chưa có cơ chế khóa ghi theo dự án cho mọi đường cập nhật, không được xem ZIP V4 là ảnh chụp nhất quán của **hai** kho hoặc là bản backup có thể phục hồi Creative.
- Chưa có REST/CLI restore của cả dự án từ ZIP. Endpoint `/restore` hiện chỉ khôi phục **một phiên bản cảnh**, không phải phục hồi backup ZIP.

## Trước khi bật Creative cho dự án thật

Hoàn thành [Issue #11](https://github.com/hieutranminh099/Truyen/issues/11): cờ Creative bền vững, khóa ghi liên tiến trình, phục hồi thao tác xuyên kho, manifest/hashes, snapshot đồng bộ bằng SQLite Backup API và restore sang thư mục mới sau khi kiểm tra toàn bộ nội dung. Dùng thư mục QA tách biệt để thử lỗi dừng tiến trình, ZIP hỏng và ghi đồng thời.
