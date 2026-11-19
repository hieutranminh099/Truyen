# Kiểm tra bản thảo trong Writer–Critic–Editor

## Hiện tượng và nguyên nhân

Trong lần chạy Windows do người dùng báo cáo, Qwen3 8B chạm giới hạn 650 token khi tạo nhận xét Critic cho chương đầu. Phản hồi JSON thiếu phần kết thúc. Pipeline cũ lưu phản hồi vào `unparsed`, gọi Editor và ghi trạng thái `edited`. Hai cảnh cuối có 179 và 164 từ với mục tiêu 250 từ. Kiểm tra độ dài trước đây đo số ký tự của kết quả Editor so với bản nháp và có thể lưu lại bản nháp dưới trạng thái `edited`.

## Xác thực phản hồi Critic

Critic trả một JSON object duy nhất. Pipeline chấp nhận JSON thô hoặc JSON nằm trọn trong một khối mã có hàng rào đóng. Cả năm trường `critical`, `style`, `missing`, `strengths` và `fixes` đều phải là mảng chuỗi. Mảng rỗng thể hiện mục đó chưa có nhận xét. Pipeline chỉ chuyển năm trường đã xác thực sang Editor.

Pipeline phân loại phản hồi có dấu hiệu bị cắt, JSON sai cú pháp và JSON sai cấu trúc để báo lỗi phù hợp. Mỗi lần xử lý cảnh nhận tối đa hai phản hồi Critic khi lỗi thuộc nhóm này. Lượt đầu giới hạn ở 650 token, lượt thử lại giới hạn ở 1.000 token và yêu cầu nhận xét ngắn hơn. Cả hai mức đều bị giới hạn bởi cấu hình `NOVEL_TOKENS`. Lỗi kết nối dùng chính sách thử lại hiện có của nhà cung cấp và cơ chế tác vụ `failed` → **Tiếp tục**.

Nếu cả hai phản hồi đều hỏng, tác vụ chuyển sang `failed` với nguyên nhân cụ thể. Editor chỉ chạy sau khi có nhận xét hợp lệ. Khi tiếp tục cảnh chưa hoàn thành, pipeline đọc lại bản nháp đã lưu và tạo lại nhận xét nếu checkpoint cũ chứa `unparsed` hoặc thiếu cấu trúc bắt buộc.

## Kiểm tra độ dài

`NOVEL_SCENE_MIN_RATIO` mặc định là `0.80`. Có thể chọn một tỷ lệ lớn hơn 0 và tối đa 1 trước khi khởi chạy ứng dụng. Dùng lệnh sau trong PowerShell để đặt ngưỡng 85%.

```powershell
$env:NOVEL_SCENE_MIN_RATIO = '0.85'
python -m novelengine serve
```

Pipeline đếm mỗi nhóm ký tự phân cách bằng khoảng trắng có ít nhất một chữ cái hoặc chữ số là một đơn vị. Mức tối thiểu theo dàn ý là mục tiêu nhân với tỷ lệ rồi làm tròn lên. Với cảnh có mục tiêu 250 từ, ngưỡng mặc định là 200 từ. Cảnh chưa có mục tiêu dương vẫn được kiểm tra kết quả rỗng và tỷ lệ độ dài so với bản nháp.

Writer lưu checkpoint ngay khi tạo được bản nháp có nội dung. Tiến độ báo số từ thực tế, mục tiêu và mức tối thiểu nếu bản nháp ngắn. Editor có một lượt biên tập để bổ sung nội dung cần thiết trong phạm vi sự kiện, điểm nhìn, lời thoại và dàn ý. Bản biên tập phải có nội dung, đạt mức tối thiểu theo mục tiêu và đạt ít nhất 45% số từ của bản nháp. Pipeline lưu số đo của bản nháp và bản biên tập đạt ngưỡng trong mục `quality` của JSON nhận xét. Tác vụ báo số đo của bản biên tập bị từ chối trong thông báo lỗi.

Ví dụ, cảnh mục tiêu 250 từ mà Editor chỉ trả 179 hoặc 164 từ sẽ báo lỗi dưới ngưỡng 200. Tác vụ giữ bản nháp và nhận xét hợp lệ để tiếp tục từ Editor. Nếu Editor trả 210 từ và đạt ngưỡng tương đối so với bản nháp, cảnh có thể qua kiểm tra kỹ thuật. Nhận xét chất lượng văn học cần người đọc đánh giá riêng.

## Checkpoint và hoàn thành cảnh

- Luồng tự động chuyển cảnh mới sang `edited` sau khi nhận xét hợp lệ, bản biên tập qua ngưỡng và phiên bản cảnh khớp với phiên bản khi bắt đầu xử lý.
- Với cảnh mới, SQLite giữ bản nháp khi Critic lỗi và giữ cả nhận xét hợp lệ khi Editor lỗi hoặc trả bản quá ngắn. **Tiếp tục** hoặc phục hồi hàng đợi sau khi khởi động lại sẽ đọc checkpoint đã lưu.
- Khi người dùng lưu sửa tay trong lúc AI đang làm việc, kiểm tra phiên bản trước khi ghi phát hiện xung đột và giữ bản người dùng vừa lưu.
- Viết lại một cảnh chỉ thay thế bản cũ trong giao dịch lưu bản mới hợp lệ. Nếu Writer, Critic hoặc Editor thất bại trong lượt viết lại, dữ liệu cảnh, lịch sử phiên bản và canon đã duyệt của bản trước vẫn dùng được. Khi tiếp tục tác vụ viết lại bị lỗi, hệ thống chạy lại từ Writer.
- Cảnh vốn đã ở trạng thái `edited`, kể cả cảnh sửa tay, được giữ theo quy trình hiện có. Bản mới dùng các cột SQLite và trạng thái hàng đợi hiện có.

## Tóm tắt chương

Summary phải trả một object JSON với hai trường bắt buộc. `summary` là chuỗi có nội dung. `proposals` là mảng có thể để trống và chứa tối đa 12 đề xuất. Mỗi đề xuất là object có `kind` thuộc nhóm `fact`, `timeline`, `character`, `knowledge`, `thread`, cùng `subject` và `content` là chuỗi có nội dung. Có thể gửi JSON thô hoặc một khối mã JSON hoàn chỉnh.

Pipeline kiểm tra toàn bộ phản hồi trước giao dịch ghi tóm tắt. Lỗi định dạng hoặc sai schema đưa tác vụ về `failed` và giữ nguyên các cảnh, tệp Markdown, tóm tắt cũ và canon đã lưu. **Tiếp tục** tạo lại Summary cho chương từ các cảnh đã hoàn tất. Tóm tắt và đề xuất hợp lệ mới được ghi `pending` để chờ người dùng duyệt.

## Chi phí chạy và nghiệm thu

Đường chạy thông thường gồm một lượt Writer, một lượt Critic và một lượt Editor. Lượt Critic thứ hai chỉ phát sinh khi phản hồi đầu thiếu hoặc sai định dạng. Bản nháp ngắn tận dụng lượt Editor sẵn có. Mỗi lần người dùng tiếp tục sau lỗi là một lần chạy mới có giới hạn tương tự.

Chạy bộ kiểm thử P0-06 và các bài hiện có bằng lệnh sau:

```powershell
python -m unittest discover -s tests -p "test_pipeline_quality.py" -v
python -m unittest discover -s tests -v
```

Các kiểm thử dùng phản hồi giả lập. Cần đo lại số lần thử, thời gian và độ dài đầu ra với Ollama/Qwen3 8B trên RTX 3050 6 GB. Kết quả nghiệm thu Windows trước đó mô tả lỗi ở bản cũ. Chất lượng hành văn, tên riêng, lựa chọn từ ngữ và sự lặp hình ảnh cần đánh giá riêng.

PR #3 cập nhật fixture smoke trên nhánh hiện có để trả đủ năm trường Critic, cung cấp một phản hồi Summary riêng và tạo bản Editor đạt ít nhất 280 từ với mục tiêu 350. Chạy `python smoke_windows.py` trên bản ghép để kiểm tra HTTP 503, tiếp tục tác vụ, SQLite và Markdown.
