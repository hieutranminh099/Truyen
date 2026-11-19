# Bộ cảnh chuẩn tiếng Việt

Bộ dữ liệu gồm 12 tình huống độc lập, nguyên bản, do dự án tạo cho đánh giá văn học.

## Schema phiên bản 1

Gốc có `schema_version` (số nguyên 1), `title` và `scenes` (1–1500 cảnh). Một cảnh có:

| Trường | Kiểu và ý nghĩa |
|---|---|
| id | ID ASCII chữ thường, số, gạch nối và duy nhất |
| title, genre, setting, goal, voice | Tên, loại tình huống, bối cảnh, mục tiêu và giọng văn |
| characters, beats, required, withheld, constraints | Danh sách mô tả nhân vật, diễn biến, chi tiết bắt buộc, điều phải giữ kín và ràng buộc |
| target_words | Số từ dự kiến, số nguyên từ 100 tới 5000 |
| criteria | Danh sách dấu hiệu riêng để người đọc đánh giá |

## Xác thực và nhập

```powershell
python evaluation_scenes.py
python evaluation_scenes.py --output canh-chuan.json
python evaluation_scenes.py --scene trinh-tham --output canh-trinh-tham.json
```

Script chỉ tạo tệp mới theo đường dẫn bạn chọn. Tạo **dự án thử mới** trong Novel Engine và dán JSON vào phần **Dàn ý**. Mỗi cảnh thành một chương độc lập. Khi so mô hình, dùng dàn ý cố định và giữ dự án thử sạch, tránh duyệt canon từ một tình huống vào tình huống khác. Không nhập bộ cảnh vào dự án đang sáng tác.

## Chấm thủ công

Đưa dàn ý và bản văn đã ẩn danh cho ít nhất hai người đọc nếu có thể. Chấm từng bản trước khi trao đổi. Dùng thang 1–5 cho tiếng Việt, lời thoại, chiều sâu tâm lý, logic nhân quả, sáng tạo, bám dàn ý và tránh lặp/sáo ngữ. Điểm 1 là lỗi lớn, 3 là đọc được nhưng cần sửa, 5 là đạt rõ ràng. Dùng `criteria` để ghi dẫn chứng riêng cho cảnh, đồng thời đánh dấu thiếu chi tiết bắt buộc, lộ bí mật hoặc vi phạm ràng buộc. Giữ cả điểm cá nhân và dẫn chứng trước khi xem tên mô hình.
