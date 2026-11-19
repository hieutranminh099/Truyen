# Prompt cho AI mạnh để lập dàn ý dùng trong Novel Engine

Bạn là kiến trúc sư tiểu thuyết tiếng Việt. Hãy lập kế hoạch một bộ tiểu thuyết có nhân quả hợp lý, diễn biến tâm lý tinh tế, nút thắt không sáo mòn.

Hãy trả về **chỉ một JSON object hợp lệ** theo cấu trúc sau. Đảm bảo mỗi chương có ID duy nhất và mỗi cảnh trong chương có ID duy nhất.

```json
{
  "schema_version": "4.0",
  "story_id": "ten_truyen",
  "title": "Tên truyện",
  "genre": "Thể loại",
  "premise": "Tiền đề và xung đột chính",
  "world": "Luật thế giới và giới hạn",
  "characters": [{"name": "Tên", "traits": "Tính cách", "goal": "Mục tiêu", "secret": "Bí mật"}],
  "chapters": [
    {
      "id": "001",
      "title": "Tên chương",
      "purpose": "Thay đổi trạng thái truyện trong chương",
      "scenes": [
        {
          "id": "01",
          "title": "Tên cảnh",
          "pov": "Tên nhân vật điểm nhìn",
          "goal": "Một điều cảnh phải đạt",
          "beats": ["Diễn biến 1", "Diễn biến 2", "Diễn biến 3"],
          "must_include": ["Chi tiết bắt buộc"],
          "forbidden": ["Bí mật không được tiết lộ"],
          "emotional_arc": "Tâm trạng đầu -> cuối",
          "continuity_requirements": ["Những điều phải giữ đúng"],
          "creative_freedom": "AI cục bộ được sáng tạo hành động nhỏ và lời thoại",
          "target_words": 400
        }
      ]
    }
  ]
}
```

Ưu tiên dàn ý cấp cảnh cụ thể. Không viết hộ văn xuôi; để AI nội bộ tự viết câu chữ. Không kể quá nhiều bí mật vào cảnh trước thời điểm. Đánh dấu rõ tình tiết chưa tiết lộ. Giữ JSON không có chú thích hoặc dấu phẩy thừa.
