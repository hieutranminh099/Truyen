# Novel Engine Hybrid V4 — bản chạy thử thực tế

**Dành cho:** Windows 10/11, RAM 16GB, NVIDIA RTX 3050 6GB, Python 3.10+, Ollama, SillyTavern, Android qua Tailscale. **Toàn bộ mã nguồn Python/HTML/CSS/JS nằm trong ZIP.** Không cần `pip install` để khởi động lõi. Không có tệp EXE hay APK. Đây là **bản preview tự chạy**, chưa phải bản sản xuất được bảo đảm an toàn và chất lượng.

## 1. Chức năng đã lập trình

- Giao diện tối responsive cho Windows và Android, truy cập qua trình duyệt.
- Nhiều dự án truyện; mỗi dự án một `story.db`, dàn ý, Voice Bible, bản thảo và backup.
- Nhập và xác thực dàn ý JSON nhiều chương, từ AI mạnh hoặc tạo dàn ý **ứng viên** bằng Ollama/API.
- Bộ máy viết từng cảnh bằng Ollama: Writer → Critic → Editor, lưu checkpoint và lịch sử phiên bản.
- Hàng đợi công việc SQLite tuần tự: pause/resume/cancel ở **ranh giới cảnh/đoạn**, tự phục hồi tác vụ `running` sau khi máy chủ được khởi động lại.
- Dừng tại mỗi chương để bạn **duyệt tóm tắt**, sau đó tự chuyển sang chương tiếp theo. Dữ kiện AI đề xuất lưu **pending**, không tự trở thành canon.
- Trí nhớ gồm fact/timeline/character/knowledge/thread, trạng thái duyệt, thu hồi và sổ audit. Các mục `knowledge` mặc định riêng tư và được lọc theo nhân vật điểm nhìn.
- Tải lên TXT/MD/EPUB (không DRM; tệp ≤8MB), lưu nguồn/quyền sử dụng, chia đoạn, phân tích kỹ thuật bằng Ollama theo lô.
- Creative RAG: FTS5 + vector cosine bằng `/api/embed`, sử dụng ghi chú kỹ thuật thay vì sao chép đoạn sách gốc. Khi mô hình embedding chưa tải, có thể dùng FTS5.
- Xuất chương Markdown, chỉnh sửa cảnh trực tiếp, viết lại cảnh, khôi phục phiên bản, đánh dấu tóm tắt không còn hiệu lực nếu thay đổi cảnh.
- API tương thích OpenAI **ở mức thử nghiệm** cho SillyTavern (`/v1/models`, `/v1/chat/completions`; streaming là SSE dạng buffered, chưa stream token trực tiếp). Nhập vai không tự ghi sự kiện vào canon.
- Cloud API (OpenAI-compatible) **chỉ gọi khi bạn bật cấu hình và chọn thao tác**. Khóa API không đưa vào web hoặc mã nguồn.
- Chuyển dự án V3 cũ bằng công cụ migration riêng, giữ nguyên thư mục gốc.
- Test giả lập AI để kiểm chứng logic mà không tiêu tốn API/GPU.

## 2. Cài đặt trên Windows — 5 bước

1. Cài **Python 3.10 hoặc mới hơn**, có lệnh `py -3` hoặc `python`; cài **Ollama cho Windows**: https://ollama.com/download/windows . Khởi động Ollama.
2. Trong CMD/PowerShell chạy:

   ```powershell
   ollama pull qwen3:8b
   ollama pull qwen3-embedding:0.6b
   ollama list
   ```

   Nếu VRAM không đủ, có thể thử mô hình viết nhẹ hơn rồi cấu hình `NOVEL_MODEL`; cần tự kiểm tra văn phong.
3. Giải nén ZIP vào một thư mục, ví dụ `C:\NovelEngineHybrid`. **Không chạy trong ZIP**.
4. Nhấn đúp `START_NOVEL.bat`. Nó sử dụng Python chuẩn, **không cần cài thư viện pip**.
5. Mở `http://127.0.0.1:8765`, nhập **mã truy cập in trong CMD**. Mã cũng có trong `data/browser_token.txt` (cất giữ bí mật). Tại lần chạy đầu, ứng dụng tạo dự án demo có 2 chương.

Nếu nhấn START mà cửa sổ báo lỗi `Address already in use`, bạn đang có V3 chạy ở cổng 8765. Đóng V3 hoặc đặt `NOVEL_PORT=8767` trong môi trường của terminal mới. Nếu Chrome hiển thị lỗi `Failed to fetch`, kiểm tra chương trình có còn chạy hay không.

### Hiệu năng máy RAM 16GB / GPU 6GB

- Mặc định `qwen3:8b`, `num_ctx=4096`, `num_predict=1300`, chạy **tuần tự**.
- Mô hình 8B ở lượng tử hóa ~5GB có thể phải offload một phần sang CPU do overhead/KV cache; không thể cam kết chạy 100% GPU. Dùng `ollama ps` để kiểm tra thiết bị xử lý.
- Lúc phân tích/tạo embedding, nên chạy **khi không viết truyện**. Novel Engine xử lý từng yêu cầu Ollama một, kể cả yêu cầu nhập vai qua gateway của ứng dụng. Nếu SillyTavern hay phần mềm khác gọi Ollama trực tiếp, yêu cầu đó nằm ngoài hàng đợi của Novel Engine.
- `NOVEL_TOKENS` lớn hơn có thể làm cảnh dài hơn nhưng dễ tăng tải và thời gian chờ.
- Khi đóng CMD, Novel Engine ngừng nhận lệnh. Sau khi chạy lại, các bản nháp đã lưu và hàng đợi vẫn còn.

## 3. Quy trình viết truyện nhiều chương

1. Trong mục **Dàn ý**, dán JSON AI mạnh tạo ra. Dùng `examples/planner_prompt_VI.md` để yêu cầu AI mạnh xuất JSON chuẩn. Chỉnh **Voice Bible** theo chất văn mong muốn.
2. Chọn **Viết tự động → Viết/tiếp tục toàn bộ truyện**. Ứng dụng tạo job trong `data/queue.db`.
3. Qwen viết cảnh, tự soát, biên tập và xuất Markdown vào `data/projects/<id>/exports/`.
4. Sau mỗi chương, job chuyển trạng thái `waiting_approval`. Vào **Trí nhớ truyện**, đọc tóm tắt, bấm duyệt để job tự tiếp tục. Dữ kiện canon AI đề xuất cần **duyệt riêng**; không tự áp dụng.
5. Trong **Bản thảo**, đọc, sửa thủ công, viết lại hoặc khôi phục phiên bản cũ. Bản sửa làm tóm tắt chương mất hiệu lực; phải duyệt lại trước khi dùng vào chương sau.
6. Trong **Kho truyện**, nhập tài liệu hợp pháp, phân tích từng lô 20 đoạn. Nếu muốn tìm kiếm ngữ nghĩa, nhấn **Tạo tối đa 30 embedding** (cần tải model embedding).

Khi viết lại cảnh, ứng dụng giữ bản hiện tại và trí nhớ đã duyệt cho đến khi lưu được bản mới. Nếu Ollama lỗi, tác vụ có thể chạy lại từ hàng đợi. Nếu bạn lưu một bản sửa tay trong lúc AI đang xử lý, ứng dụng giữ phiên bản vừa lưu và báo xung đột.

> Lưu ý: Kiểm tra tự động từ khóa và đánh giá bằng chính mô hình là **hỗ trợ biên tập**, không chứng minh bản thảo không mâu thuẫn, hay đã đạt văn phong xuất bản. Không tự động đăng truyện lên website.

## 4. Android 4G/5G ở bất cứ đâu

1. Cài Tailscale cho Windows và Android: https://tailscale.com/download ; đăng nhập **cùng tailnet**.
2. Trên laptop chạy `START_NOVEL.bat`, giữ nguyên `NOVEL_HOST=127.0.0.1` (mặc định).
3. Trên **Windows Terminal (Admin)** chạy `tailscale serve --bg 8765` hoặc tệp `START_TAILSCALE_SERVE.bat` với quyền Administrator.
4. Tailscale trả về địa chỉ HTTPS dạng `https://ten-may.tailnet.ts.net`. Trên điện thoại bật Tailscale, mở địa chỉ này bằng Chrome, nhập mã Novel Engine ở cửa sổ CMD.
5. Thử tắt Wi-Fi điện thoại và mở bằng 4G/5G. Laptop **phải đang bật, không Sleep, còn mạng**, Ollama đang hoạt động.

**Không dùng `tailscale funnel`, không mở cổng 8765 hay 11434 trên router**, không để Ollama lắng nghe `0.0.0.0`. Tailscale Serve có thể cần bật HTTPS và MagicDNS cho tailnet. Tắt chia sẻ: `tailscale serve off`. Nhà phát triển ứng dụng không kiểm soát được quyền truy cập khi bạn chia sẻ token: hãy giữ mã bí mật.

## 5. Tích hợp API AI mạnh (tùy chọn)

Mặc định **Cloud OFF**. Có hai cách dùng AI mạnh:

- **Không cần khóa API:** nhờ ChatGPT/AI mạnh tạo dàn ý JSON trên giao diện riêng, dán vào Novel Engine.
- **Tự động:** dùng dịch vụ có endpoint tương thích OpenAI Chat Completions qua `NOVEL_CLOUD_URL`, `NOVEL_CLOUD_MODEL`, `NOVEL_CLOUD_API_KEY` và `NOVEL_CLOUD_ENABLED=1`.

Ví dụ PowerShell (*chạy trong chính cửa sổ sẽ mở Novel Engine; thay model bằng tên nhà cung cấp đang hỗ trợ*):

```powershell
cd C:\NovelEngineHybrid
$env:NOVEL_CLOUD_ENABLED = "1"
$env:NOVEL_CLOUD_URL = "https://api.openai.com/v1"
$env:NOVEL_CLOUD_MODEL = "<model-ho-tro-chat-completions>"
$env:NOVEL_CLOUD_API_KEY = Read-Host "Nhập API key (không chia sẻ)"
python -m novelengine serve
```

Sau đó ở mục Dàn ý chọn **Dùng API đám mây** khi tạo dàn ý; hoặc ở Viết tự động chọn **Biên tập đánh giá bằng API đám mây**. Chi phí tùy nhà cung cấp. Trong bản preview **chưa có tự tính tiền/giới hạn chi phí**, không bật API khi không muốn phát sinh phí; không mặc định đẩy nguyên kho sách lên mạng.

**Lưu ý tương thích:** API riêng của Claude/Gemini không nhất thiết theo OpenAI Chat Completions; hãy dùng endpoint có lớp tương thích được nhà cung cấp công bố hoặc viết thêm adapter tương ứng. Một số model chỉ hỗ trợ `max_completion_tokens` thay vì `max_tokens`; cần chỉnh adapter `novelengine/ai.py` nếu provider yêu cầu. Không lưu khóa API trong JS, outline hay kho truyện.

## 6. SillyTavern

Có gateway thử nghiệm để chat nhập vai với một phần canon đã duyệt. Trên laptop:

- Trong SillyTavern chọn **Chat Completion → Custom (OpenAI-compatible)**.
- Endpoint thử: `http://127.0.0.1:8765/v1`.
- Model: `novel-demo` (hoặc `novel-<id-du-an>`).
- API key: `data/gateway_token.txt`, khác với mã đăng nhập giao diện. **Đừng dán khóa này ở nơi công khai.**
- Tắt Streaming trước khi thử, vì stream của bản preview chỉ gửi kết quả sau khi Ollama chạy xong. Nếu SillyTavern không chấp nhận gateway, bạn vẫn có thể kết nối SillyTavern trực tiếp với Ollama như trước.

**Chưa có đồng bộ World Info tự động**, chưa có streaming thời gian thực, chưa có theo dõi đầy đủ ai biết gì trong phiên nhập vai. Gateway không tự cập nhật canon.

## 7. Chuyển dữ liệu từ V3 Mobile

Đừng xóa thư mục V3. Dùng công cụ ở trạng thái xem trước (không ghi đè):

```powershell
python migrate_from_v3.py "C:\AI\Novel_Engine_V3_Mobile" --id truyen-cu
```

Để thực hiện:

```powershell
python migrate_from_v3.py "C:\AI\Novel_Engine_V3_Mobile" --id truyen-cu --apply
```

Nếu bạn sở hữu quyền sử dụng tài liệu thư viện V3 và muốn chuyển thư viện: thêm `--confirm-rights`. Công cụ tạo dự án V4 **mới**, không sửa tệp V3. Thử khôi phục từ bản sao trên máy khác trước khi xóa hoặc di chuyển dữ liệu cũ. Khi migration gặp ID trùng, chọn ID mới.

## 8. Dữ liệu và sao lưu

```text
Novel_Engine_Hybrid_V4/
  novelengine/       modules Python (store, outline, ai, rag, pipeline, jobs, server)
  static/            index.html, app.css, app.js
  examples/          prompt dàn ý JSON
  tests/             unit/integration tests mock AI
  data/              tạo khi chạy, KHÔNG nằm trong bộ ZIP phát hành
    browser_token.txt
    gateway_token.txt
    queue.db
    projects/<id>/
      story.db
      outline.json
      voice_bible.md
      exports/chapter_001.md
      backups/backup_*.zip
  START_NOVEL.bat
  START_TAILSCALE_SERVE.bat
  STOP_TAILSCALE_SERVE.bat
  RUN_TESTS.bat
  migrate_from_v3.py
  benchmark_models.py
```

Mục **Cài đặt → Tạo sao lưu** tạo ZIP gồm `story.db`, outline, Voice Bible và exports của dự án. Queue là dữ liệu **toàn cục**, không có trong bản backup riêng dự án. Khi sao lưu đầy đủ để di chuyển máy, phải sao chép cả thư mục `data/` khi đã dừng ứng dụng (bao gồm queue.db, bí mật; bảo vệ bản sao này). Tệp backup riêng từng dự án được lưu trong `data/projects/<id>/backups/`.

## 9. Kiểm thử và benchmark

Chạy `RUN_TESTS.bat` hoặc:

```powershell
python -m unittest discover -s tests -v
```

CI chạy trên Ubuntu và Windows với Python 3.10 và 3.14. Để tái hiện kiểm tra cấu hình, đặt `NOVEL_DATA_DIR` thành một thư mục tạm mới, giữ `NOVEL_HOST=127.0.0.1` và `NOVEL_CLOUD_ENABLED=0`, rồi chạy các lệnh sau.

```powershell
python -m compileall -q novelengine tests benchmark_models.py migrate_from_v3.py
python -m novelengine --help
python -m novelengine projects
python benchmark_models.py --help
python migrate_from_v3.py --help
node --check static/app.js
```

CI dùng FakeAI và các kiểm thử HTTP cục bộ. Nghiệm thu trên Windows với Ollama, RTX 3050 và Android cần thiết bị thật.

Kiểm thử sử dụng **FakeAI** nên chạy được không cần Ollama hoặc API, không chứng minh văn xuôi thực sự hay. Để so sánh hai mô hình cùng scene packet:

```powershell
ollama pull qwen3.5:4b
python benchmark_models.py --project demo --models qwen3:8b,qwen3.5:4b --scenes 5
```

Ứng dụng lưu bản A/B và khóa đối chiếu riêng. Đọc mù rồi tự chấm tự nhiên tiếng Việt, lời thoại, tâm lý, logic và tình tiết. **Benchmark dùng Ollama thật và có thể chạy lâu trên GPU 6GB.**

## 10. Giới hạn chưa hoàn thành

- Chưa thử chất lượng văn tiếng Việt với GPU RTX 3050 thực tế; phải benchmark tại máy của bạn.
- Chưa có tự kiểm mâu thuẫn bằng bộ luật hình thức, chưa có trích xuất entity/knowledge graph đầy đủ, chưa quản lý biết/không biết theo từng lời thoại. Trí nhớ V4 là các bản ghi có duyệt và tóm tắt, không phải một thế giới giả lập toàn diện.
- Review do AI trả về có thể sai; kiểm tra từ khóa chỉ là tín hiệu, không phải kiểm định ngữ nghĩa.
- Không có số đo token/cost cloud; có thể bị tính phí ngoài dự kiến nếu bật.
- API Gateway cho SillyTavern chỉ thử nghiệm, stream là buffered SSE, chưa bảo đảm với mọi phiên bản ST.
- Chưa có EPUB/DOCX export, chỉnh sửa rich text, đồng bộ nhập vai tự động, PWA/offline, hoặc ứng dụng Android APK.
- Tailscale phải được **chính bạn cài và kết nối** trên thiết bị thật; phần mềm không tự cấu hình router/VPN.
- Chưa kiểm thử chịu tải, tấn công mạng nâng cao; chỉ được dùng qua localhost hoặc Tailscale riêng tư.
- Cần thư viện nguồn hợp pháp. Không dùng chức năng phân tích để tái tạo đoạn dài tác phẩm bản quyền.

## 11. Tài liệu tham khảo chính thức

- Ollama: https://docs.ollama.com/ ; https://ollama.com/library/qwen3
- Tailscale Serve: https://tailscale.com/docs/features/tailscale-serve
- SillyTavern Custom OpenAI: https://docs.sillytavern.app/usage/api-connections/openai/

*Đây là mã nguồn mở để bạn tự vận hành và nâng cấp, không phải dịch vụ cloud đang chạy cho bạn.*
