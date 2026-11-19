# BÁO CÁO TỔNG HỢP & KẾ HOẠCH TRIỂN KHAI

**Dự án:** Novel Engine — Hybrid Intelligence / Creative RAG / Long-term Story Memory  
**Phiên bản tài liệu:** 1.0 • Ngày: 19/11/2026  
**Định hướng:** AI sáng tác tiểu thuyết tiếng Việt và nhập vai thông minh, điều khiển từ laptop Windows và điện thoại Android  
**Trạng thái:** Đã có V2/V3 Mobile thử nghiệm; báo cáo này là thiết kế nâng cấp, không phải tuyên bố các chức năng tương lai đã hoạt động.

> **Quyết định trọng tâm:** Không cố biến mô hình 8B thành một mô hình cực mạnh chỉ bằng prompt. Dùng AI mạnh để thiết kế và đánh giá; dùng AI cục bộ để viết; duy trì trí nhớ có kiểm soát; chỉ gọi API đám mây khi thật sự cần; đo chất lượng bằng bản thảo thực tế.

## 1. TÓM TẮT ĐIỀU HÀNH

Novel Engine nhằm giải quyết sáu vấn đề: (1) trí thông minh xây dựng cốt truyện, (2) văn phong tiếng Việt mượt và có bản sắc, (3) nhất quán qua nhiều chương, (4) sử dụng kiến thức văn học từ kho truyện mà không sao chép, (5) nhập vai với nhân vật có quyền tự chủ, (6) điều khiển mọi nơi từ laptop/điện thoại.

**Kiến trúc được chọn:** *Hybrid Intelligence* gồm AI mạnh (Planner/Critic), AI nội bộ (Writer), dữ liệu dự án có phiên bản (Story Bible/Canon), Creative RAG, Job Queue, giao diện web tối và cầu nối SillyTavern. Mọi tác vụ chạy **tuần tự** trên GPU 6 GB; không cần cài mô hình lớn đồng thời. Chế độ không dùng API vẫn hoạt động, nhưng chất lượng và tốc độ tùy mô hình cục bộ.

**Ba ưu tiên đầu tiên:**

1. Ổn định nền tảng: sao lưu, dừng/tiếp tục an toàn, lưu trạng thái ở cấp cảnh, bảo vệ truy cập từ xa.
2. Tăng chất lượng văn học: chuẩn dàn ý, Voice Bible, bộ viết–kiểm–biên tập và đánh giá đối chứng.
3. Xây trí nhớ đúng: canon có duyệt, timeline, nhân vật biết/không biết gì, truy xuất thông tin theo từng cảnh.

**Phạm vi không nên làm ngay:** fine-tuning mô hình 8B trên laptop; hệ thống nhiều AI cục bộ chạy song song; tự động nhập mọi sự kiện nhập vai vào canon; kết nối công khai máy chủ AI ra Internet; huấn luyện bằng kho sách bản quyền không có quyền phù hợp.

## 2. MỤC TIÊU, NGƯỜI DÙNG VÀ RÀNG BUỘC

### 2.1. Yêu cầu bắt buộc

| ID | Yêu cầu | Điều kiện hoàn thành |
|---|---|---|
| FR-01 | Dùng AI mạnh lập dàn ý nhiều chương | Nhập JSON/Markdown chuẩn; xem, sửa, xác thực trước khi chạy |
| FR-02 | Viết nhiều chương tự động | Chạy theo cảnh, checkpoint bền vững, tiếp tục sau lỗi/khởi động lại |
| FR-03 | Văn phong tiếng Việt tự nhiên | Có Voice Bible, biên tập chọn lọc, benchmark đọc mù |
| FR-04 | Trí nhớ lâu dài | Canon, timeline, nhân vật, bí mật, quan hệ; có duyệt và hoàn tác |
| FR-05 | Kho truyện “both” | Lưu nguồn gốc + phân tích kỹ thuật + truy xuất thích hợp |
| FR-06 | Tích hợp AI API tùy chọn | Tùy chọn nhà cung cấp theo vai trò, giới hạn chi phí, tự chuyển cục bộ |
| FR-07 | Laptop và Android | Cùng giao diện web tối, tối ưu cảm ứng và máy tính |
| FR-08 | Điều khiển từ mọi nơi | Truy cập riêng qua Tailscale, máy chủ không mở trực tiếp Internet |
| FR-09 | SillyTavern/nhập vai | Đọc chung hồ sơ thế giới; đồng bộ sự kiện có quy tắc duyệt |
| FR-10 | Tự chủ cao | NPC có mục tiêu/kiến thức riêng, tác động hậu trường nhưng không phá canon |
| FR-11 | Quyền kiểm soát của người viết | Xem log, duyệt, sửa, khóa chi tiết và quay lại phiên bản trước |
| FR-12 | Xuất bản thảo | Markdown, TXT; DOCX/EPUB là mục mở rộng sau khi lõi ổn định |

### 2.2. Thiết bị và trải nghiệm

- Laptop Windows: **RAM 16 GB, GPU NVIDIA RTX 3050 6 GB VRAM**. Mô hình chính khởi điểm `qwen3:8b`; cần đo chất lượng/tốc độ thực tế, có thể thử mô hình nhỏ hơn để so sánh.
- Ollama chạy trên laptop; SillyTavern dùng riêng cho nhập vai; dữ liệu lưu cục bộ, không phụ thuộc nhà cung cấp API.
- Android là **thiết bị điều khiển và đọc/duyệt**, không phải nơi chạy Qwen3 8B. Khi ở xa dùng Internet + Tailscale; laptop bắt buộc bật, có mạng và không Sleep.
- Giao diện ưu tiên **dark mode dịu mắt**, tương phản rõ nhưng không dùng nền trắng chói; chữ dễ đọc, cỡ chữ tùy chỉnh; sử dụng tốt khi cầm điện thoại bằng một tay.

### 2.3. Nguyên tắc kỹ thuật

- *Canon first:* dữ kiện đã duyệt có thẩm quyền cao hơn mô hình.
- *Quality gate:* không đưa bản thảo lỗi logic vào trí nhớ chính thức.
- *One GPU task at a time:* viết, kiểm tra, tạo embedding, phân tích tài liệu chạy theo hàng đợi.
- *Local first; cloud on demand:* dữ liệu chỉ gửi API khi người dùng bật và đúng phạm vi cần thiết.
- *Revision-friendly:* mọi bản thảo, prompt, nhận xét, thay đổi canon và chi phí phải truy vết được.

## 3. KIỂM TRA HIỆN TRẠNG MÃ NGUỒN

Đã đối chiếu các tệp trong `Novel_Engine_Series_v2.zip` và `Novel_Engine_V3_Mobile.zip`, đặc biệt `engine.py`, `webapp.py`, `README_VI.md`.

| Thành phần | Hiện trạng được kiểm tra | Hạn chế cần xử lý |
|---|---|---|
| Engine viết cảnh | Gọi Ollama `/api/chat`; viết nháp → tự kiểm tra JSON → biên tập | Một mô hình tự kiểm và tự sửa, chưa đo chất lượng; không chặn mâu thuẫn chắc chắn |
| Dàn ý | Đọc JSON `chapters[]/scenes[]` và bắt buộc `id`, `goal`, `beats` | Chưa có schema phiên bản, cảnh ràng buộc nâng cao, liên kết các tuyến truyện |
| Bản thảo | Lưu `project/drafts/chapter_*.md`; SQLite ghi draft/edited/review | Chưa có version history, diff, khóa đoạn, undo |
| Trí nhớ | Bảng `canon` đơn giản; tóm tắt chương cần duyệt | Chưa có thực thể nhân vật/timeline/tri thức riêng; tóm tắt đã duyệt mới dùng lại |
| Thư viện | Lưu TXT/MD và FTS5; khi viết chèn tối đa một số ghi chú | Chưa có semantic vector RAG; fallback chèn đầu tài liệu |
| Phân tích văn học | Gọi Ollama phân tích tối đa 10.000 ký tự đầu | Chưa chia cảnh, chưa xử lý đủ toàn tài liệu, chưa kiểm định chất lượng thẻ kỹ thuật |
| Web tối | Python `ThreadingHTTPServer`, trang responsive một tệp | Chưa có hàng đợi bền, API quản lý công việc đầy đủ, pause/cancel an toàn |
| Truy cập | Có access token HTTP header; LAN script nghe trên `0.0.0.0` | Chưa TLS/auth production; cần chỉ nghe loopback khi dùng Tailscale Serve |
| Điện thoại | Mở qua Chrome Android cùng Wi-Fi được về mặt thiết kế | Chưa thử trên thiết bị thật của bạn; truy cập từ xa chưa cấu hình |
| SillyTavern | Có thể kết nối Ollama song song | Chưa có gateway chia sẻ canon/World Info, chưa kiểm thử tích hợp |
| Cloud API | Chưa có | Cần provider adapter, quản lý bí mật, giới hạn ngân sách |

**Nhận định:** V3 phù hợp làm bản thử nghiệm. Việc chuyển thành ứng dụng dùng hằng ngày đòi hỏi tái cấu trúc thành các module rõ ràng, thay vì tiếp tục gắn thêm nhiều chức năng vào `webapp.py`/`engine.py`.

## 4. KIẾN TRÚC MỤC TIÊU

```text
 LAPTOP WINDOWS                                    ĐIỆN THOẠI ANDROID
 ┌──────────────────────────────────────┐          ┌────────────────────┐
 │ Novel Engine Web UI (Dark, PWA)      │◄────────►│ Trình duyệt / PWA  │
 │ API Backend + Auth + Job Queue       │ Tailscale│ Điều khiển từ xa   │
 ├──────────────────────────────────────┤   HTTPS  └────────────────────┘
 │ Project Manager + Story Bible        │
 │ Canon/Timeline/Character State       │
 │ SQLite + FTS5 + Vector Index         │
 ├──────────────────────────────────────┤
 │ Orchestrator (thực thi tuần tự)      │
 │  Planner → Writer → Critic → Editor  │
 │         ↓           ↑                │
 │      Creative RAG / Memory           │
 ├──────────────────────────────────────┤
 │ Ollama: Qwen writer + embedding      │
 │ Optional Cloud API: planner/critic   │
 │ Gateway tương thích SillyTavern      │
 └──────────────────────────────────────┘
```

### 4.1. Luồng viết một chương

1. Nhập dàn ý AI mạnh (`outline.json`) → xác thực schema, mục tiêu, POV, tiết lộ, ràng buộc.
2. Đọc **Voice Bible**, trạng thái nhân vật, canon, timeline và 3–5 kỹ thuật liên quan từ Creative RAG.
3. Tạo *scene packet* nhỏ, rõ nhiệm vụ, phù hợp giới hạn context của GPU.
4. AI cục bộ viết bản nháp **không giải thích dàn ý**.
5. Kiểm tra tự động: điều bắt buộc, điều cấm, nhân vật biết gì, thứ tự thời gian, nhân vật xuất hiện, độ dài và lặp từ.
6. AI biên tập sửa **đúng những đoạn cần sửa**; giữ giọng văn. Lỗi lớn được chuyển sang AI mạnh nếu bật API hoặc đưa vào hàng chờ duyệt.
7. Lưu phiên bản bản thảo và các đề xuất cập nhật trạng thái; **chưa tự động coi tất cả là canon**.
8. Khi chương hoàn thành: kiểm tra liên chương → duyệt hoặc xử lý theo chính sách đã chọn → commit canon/timeline → tạo checkpoint → xuất Markdown.

### 4.2. Dàn ý do AI mạnh cung cấp

Đề xuất schema có `schema_version`, `story_id`, `world`, `premise`, `voice_profile`, `characters`, `plot_arcs`, `chapters` và `scenes`. Mỗi cảnh gồm `scene_id`, `pov`, `goal`, `beats`, `must_include`, `forbidden`, `foreshadow`, `emotional_arc`, `continuity_requirements`, `creative_freedom`, `target_words`.

**Tầng quyền hạn:** AI mạnh quyết định nhân quả và bước ngoặt; AI nội bộ được sáng tạo lời thoại, hành vi vi mô, nhịp kể và hình ảnh, nhưng không được làm sai các chi tiết khóa. Mọi thay đổi cốt truyện lớn phải được đề xuất và ghi log trước khi áp dụng.

## 5. BỘ MÁY NÂNG CHẤT LƯỢNG VĂN PHONG

### 5.1. Voice Bible theo dự án

Hồ sơ gồm: điểm nhìn, thì kể, tiết tấu câu, mật độ miêu tả, ngôn ngữ đối thoại, mức độ ẩn ý, tỷ lệ hành động/nội tâm, biểu tượng lặp có chủ đích, từ ngữ và cấu trúc sáo mòn cần tránh, khác biệt giọng của từng nhân vật. Nên lưu 2–4 đoạn **do người dùng viết hoặc có quyền dùng** làm mục tiêu phong cách, không sao chép tác giả bên ngoài.

### 5.2. Viết–soát–sửa có giới hạn

- *Writer:* tập trung chuyển beats thành văn xuôi, không vừa viết vừa tự phê bình.
- *Rule checker:* kiểm tra các ràng buộc có thể xác định (must_include/forbidden, nhân vật tồn tại, cảnh đã có, độ dài). Lưu ý kiểm tra từ khóa không thể thay thế hiểu ngữ nghĩa.
- *Critic:* nêu lỗi có vị trí và dẫn chứng, đánh giá mức nghiêm trọng, không chỉ chấm điểm mơ hồ.
- *Editor:* sửa cục bộ nơi cần thiết; tối đa hai lượt tự động mỗi cảnh, không làm phẳng văn phong.
- *Escalation:* chỉ gọi AI mạnh khi mâu thuẫn nghiêm trọng, điểm chất lượng thấp hoặc tác giả yêu cầu.

### 5.3. Đánh giá so sánh trước khi chọn mô hình

Chuẩn bị **12 cảnh** đại diện: đối thoại, nội tâm, hành động, phản bội, tâm lý nhiều lớp, xây thế giới, tình cảm, điều tra, cảnh nối tiếp, kết chương, góc nhìn nhân vật khác, cảnh cần nhớ chi tiết cũ. Viết bằng `qwen3:8b` và ít nhất một cấu hình thay thế với **cùng scene packet**. Chấm đọc mù theo thang 1–5 cho: tự nhiên tiếng Việt, cá tính lời thoại, chiều sâu tâm lý, mạch kể, tính mới và đúng ràng buộc. Ghi tốc độ/tài nguyên; lựa chọn dựa trên thực nghiệm chứ không chỉ kích thước mô hình.

## 6. BỘ NHỚ DÀI HẠN VÀ TRÁNH MÂU THUẪN

### 6.1. Các lớp dữ liệu

| Lớp | Mục đích | Quy tắc |
|---|---|---|
| Story Bible | Luật thế giới và đặc điểm nền | Được duyệt, có phiên bản |
| Canon Fact | Sự thật không được tùy tiện thay đổi | Ghi nguồn cảnh/chương và trạng thái |
| Event Ledger | Nhật ký sự kiện bất biến có thứ tự | Sửa bằng sự kiện đảo ngược, không xóa âm thầm |
| Character State | Mục tiêu, cảm xúc, quan hệ, nơi ở, vật sở hữu | Phát sinh từ sự kiện được commit |
| Knowledge Graph | Ai biết/không biết bí mật nào, biết từ khi nào | Không tiết lộ thông tin ngoài kiến thức nhân vật |
| Open Threads | Lời hứa, câu hỏi chưa giải, gài chi tiết | Theo dõi hạn, vị trí đã nhắc |
| Scene/Chapter Summary | Tóm tắt để truy xuất nhanh | Không thay thế sổ sự kiện |
| Literary Lessons | Lỗi văn phong đã gặp, cách tránh | Có ví dụ nội bộ và đánh giá hiệu quả |

### 6.2. Quy trình ghi nhớ

Sau cảnh, AI trả **đề xuất delta** có cấu trúc: `events_created`, `character_changes`, `facts_proposed`, `secrets_revealed_to`, `open_threads_updated`, `source_scene_id`, `confidence`. Kiểm tra schema và đối chiếu canon; không cập nhật trực tiếp từ văn bản tự do. Khi duyệt, ghi `revision_id` và tạo snapshot; khi viết lại cảnh, tính lại trạng thái từ checkpoint trước đó. Tránh lỗi chương sau nhớ một bản thảo đã bị xóa.

### 6.3. Tự chủ NPC

Mỗi NPC có mục tiêu riêng, động cơ kín, mức độ hiểu biết, mối quan hệ và mức cho phép hành động hậu trường. Hệ thống chỉ đề xuất hành động theo lượt/cột mốc; những hành động đổi canon phải qua bộ kiểm tra/duyệt. Không bắt buộc chạy một mô hình riêng cho từng NPC, vì GPU 6 GB không phù hợp đa mô hình đồng thời.

## 7. KHO TRUYỆN “BOTH” VÀ CREATIVE RAG

### 7.1. Pipeline dữ liệu

`Nhập TXT/MD/EPUB hợp pháp → chuẩn hóa và nhận diện chương → chia cảnh/đoạn → lưu nguồn và giấy phép → phân tích kỹ thuật từng đoạn → tạo embedding → lập chỉ mục → tìm kiếm kết hợp → chọn ghi chú → đưa vào Writer.`

- **Kho nguồn:** giữ văn bản, nguồn, quyền sử dụng, tác giả, thể loại, hash, số chương; không mặc định đưa nguyên tác vào prompt.
- **Kho kỹ thuật:** các thẻ `technique_id`, `problem_solved`, `when_to_use`, `anti_patterns`, `summary`, `source_refs`, `confidence`.
- **Tìm kiếm:** kết hợp FTS5 tiếng Việt, vector embedding, bộ lọc thể loại/tình huống và xếp hạng. Khi chưa đủ điều kiện cài vector, FTS5 là phương án dự phòng.
- **Đầu ra:** ưu tiên 3–5 *ghi chú kỹ thuật đã trừu tượng hóa*, không phải đoạn sao chép tác phẩm.
- **Bản quyền:** chỉ nhập tài liệu có quyền sử dụng phù hợp; tránh tái hiện đoạn dài, tránh bắt chước quá sát một tác giả đương đại cụ thể; đánh dấu nguồn tham khảo.

### 7.2. Cấu hình phần cứng

Đề xuất embedding `qwen3-embedding:0.6b` chạy theo lô và **không cùng lúc** với mô hình viết. Bắt đầu bằng SQLite FTS5 + lưu vector cục bộ; chỉ thêm cơ sở vector riêng khi khối lượng dữ liệu yêu cầu. Đo RAM thực tế trước khi chọn FAISS/ChromaDB để tránh lãng phí và lỗi cài đặt Windows.

## 8. TÍCH HỢP AI MẠNH VÀ CHI PHÍ

### 8.1. Hai chế độ

**Thủ công (miễn phí API):** Người dùng sử dụng AI mạnh trong giao diện trò chuyện để sinh dàn ý JSON và nhập vào Novel Engine. Phần viết/kiểm tra tiếp tục chạy hoàn toàn cục bộ.

**Tự động (có API):** Backend dùng một lớp `ProviderAdapter` với cấu hình `provider`, `base_url`, `model`, `timeout`, `retry`, `capabilities`. Planner và Critic có thể dùng các API khác nhau; API khóa được lưu qua biến môi trường/secret store của Windows, không nhúng vào JavaScript hoặc lưu trong dự án.

### 8.2. Chính sách gọi AI mạnh

- **Bắt buộc:** không có cuộc gọi đám mây tự động khi người dùng chưa bật chế độ.
- **Ưu tiên:** lập dàn ý phần/chương, kiểm tra các bước ngoặt lớn, biên tập cảnh có chất lượng thấp, soát logic sau chương.
- **Không cần:** sửa chính tả đơn giản, viết mọi câu/đoạn ngắn, tạo mọi embedding.
- **Bảo vệ chi phí:** giới hạn tiền mỗi chương/tháng, hiển thị ước lượng theo bảng giá thực tế, log tokens, cảnh báo trước khi vượt hạn mức, khả năng chạy lại cục bộ.
- **Bảo vệ riêng tư:** màn hình xem trước dữ liệu gửi lên cloud; mặc định không gửi nguyên kho sách, khóa API, nhật ký riêng tư hoặc thông tin cá nhân.

Ghi chú: ChatGPT Plus và OpenAI API có cơ chế thanh toán riêng; không giả định gói thuê bao đã bao gồm ngân sách API.

## 9. ĐIỆN THOẠI, BẢO MẬT VÀ SILLYTAVERN

### 9.1. Truy cập từ bất cứ đâu

**Khuyến nghị:** Web UI chạy tại `127.0.0.1:8765` trên Windows → **Tailscale Serve** cung cấp địa chỉ HTTPS chỉ truy cập trong tailnet → Android dùng Chrome/PWA. Không cần router port forwarding, IP công khai hoặc Tailscale Funnel. Laptop phải bật, có mạng, không Sleep.

Điều chỉnh **bắt buộc** so với V3 LAN script hiện tại: **không dùng `NOVEL_HOST=0.0.0.0` làm mặc định khi truy cập qua Tailscale Serve**; chỉ nghe trên loopback. Có xác thực ứng dụng riêng, không đưa token lên URL, không lưu API key phía trình duyệt, giới hạn kích thước tải lên, kiểm tra đường dẫn tệp, logging bảo mật và chính sách sao lưu. Sau đó mới triển khai truy cập xa.

### 9.2. Giao diện tối trên desktop và mobile

Sáu trang chính: **Dashboard**, **Dàn ý/Planner**, **Viết & Hàng đợi**, **Bản thảo/So sánh phiên bản**, **Kho truyện/RAG**, **Trí nhớ/Nhân vật**. Phần cài đặt quản lý API, mô hình, quyền riêng tư và sao lưu.

Mobile cần các nút lớn, thanh điều hướng gọn, chế độ đọc toàn màn hình, điều chỉnh kích thước chữ, thông báo lỗi rõ ràng, hiển thị tiến độ thực chứ không chỉ “đang chạy”, sửa và duyệt một cảnh trên điện thoại. PWA cài biểu tượng là **mở rộng**, không đồng nghĩa AI chạy offline.

### 9.3. SillyTavern

Thiết kế gateway cục bộ tương thích **OpenAI Chat Completions**; SillyTavern gửi lời thoại → Gateway truy xuất nhân vật/địa điểm/trí nhớ phù hợp → Ollama tạo phản hồi → trả kết quả. Gateway bắt buộc kiểm thử JSON request, streaming, tên mô hình, dừng sinh, token budget và xử lý lỗi. Chỉ **đề xuất** cập nhật canon từ các phiên nhập vai; người dùng duyệt trước khi áp dụng. V3 hiện chưa có chức năng này.

## 10. CẤU TRÚC THƯ MỤC ĐỀ XUẤT

```text
novel-engine/
  app/
    api/              # API HTTP, xác thực, kiểm tra dữ liệu
    jobs/             # Hàng đợi, trạng thái, retry, pause/resume
    agents/           # Planner, Writer, Critic, Editor
    providers/        # Ollama, cloud API adapters
    memory/           # Canon, timeline, nhân vật, event ledger
    rag/              # Import, phân tích kỹ thuật, tìm kiếm
    integrations/     # SillyTavern gateway
    exporters/        # Markdown, TXT, sau đó DOCX/EPUB
  ui/                 # Giao diện tối cho laptop/điện thoại
  tests/              # Unit/integration/evaluation
  projects/<story_id>/
    outline.json
    voice_bible.md
    story.db
    drafts/
    exports/
    backups/
  config.example.toml # Không chứa khóa thật
  README_VI.md
```

**Lưu ý:** Tách dữ liệu theo `story_id`; tuyệt đối tránh đưa trí nhớ của dự án A sang dự án B. Di chuyển V3 cần script migration có backup và kiểm tra số bản thảo trước/sau.

## 11. DANH SÁCH NHIỆM VỤ CẦN LÀM (WORK BREAKDOWN)

Thứ tự ưu tiên dùng P0 = bắt buộc trước dùng thật, P1 = tăng chất lượng cốt lõi, P2 = mở rộng thông minh, P3 = tích hợp nâng cao. Đầu ra cần kiểm chứng bằng bài thử, không đánh dấu “hoàn thành” chỉ vì đã viết mã.

### Gói A — Ổn định nền tảng và an toàn dữ liệu (P0)

| ID | Nhiệm vụ | Đầu ra / tiêu chí nghiệm thu |
|---|---|---|
| A01 | Chốt cấu hình, chạy benchmark Ollama trên máy thật | Tốc độ, VRAM/RAM, context tối ưu và log lỗi |
| A02 | Sao lưu toàn bộ project trước khi nâng cấp | Backup phục hồi được, bao gồm outline/SQLite/drafts |
| A03 | Tách backend thành module; tạo cấu hình theo môi trường | Không hard-code đường dẫn/khóa, có bản chạy local |
| A04 | Thiết kế job queue lưu SQLite | Sau crash biết cảnh nào đang viết, lỗi, hoàn tất |
| A05 | Pause/resume/cancel tại ranh giới cảnh | Dừng an toàn, không làm hỏng bản thảo |
| A06 | Versioning bản thảo và rollback | Xem diff, chọn phiên bản, khôi phục được |
| A07 | Gia cố truy cập: bind localhost, auth, Tailscale Serve | Android 4G truy cập HTTPS riêng; không public port |
| A08 | Test recovery và bảo mật tối thiểu | Khởi động lại giữa job; lỗi API; upload xấu không làm mất dữ liệu |

### Gói B — Chất lượng sáng tác và dàn ý (P1)

| ID | Nhiệm vụ | Đầu ra / tiêu chí nghiệm thu |
|---|---|---|
| B01 | Chuẩn hóa schema dàn ý có phiên bản | Validator báo lỗi rõ ràng, có mẫu JSON hợp lệ |
| B02 | Thiết kế Voice Bible và profiles nhân vật | Có thư viện thiết lập giọng văn, chọn theo dự án |
| B03 | Xây scene packet có token budget | Ngữ cảnh không tràn; ưu tiên canon và scene goal |
| B04 | Tách Writer, Critic, Editor theo đầu ra có schema | Log từng bước và prompt version |
| B05 | Kiểm tra điều cấm/điều bắt buộc/continuity | Báo lỗi kèm bằng chứng trong bản thảo |
| B06 | Sửa cục bộ, giới hạn số vòng biên tập | So sánh trước/sau, không tự viết lại vô hạn |
| B07 | Benchmark 12 cảnh và đánh giá đọc mù | Bộ rubrics và bảng kết quả có thể tái lập |
| B08 | Xuất Markdown/TXT; duyệt từng cảnh/chương | Không mất chỉnh sửa thủ công khi chạy lại |

### Gói C — Bộ nhớ dài hạn và mô phỏng NPC (P1)

| ID | Nhiệm vụ | Đầu ra / tiêu chí nghiệm thu |
|---|---|---|
| C01 | Thiết kế Canon Fact, Event Ledger, Character State | Schema có source, timestamp, revision, status |
| C02 | Tạo delta sự kiện sau mỗi cảnh | JSON được kiểm định, có thể duyệt hoặc bỏ |
| C03 | Timeline và phụ thuộc nhân quả | Tìm sự kiện theo chương/thời gian/nhân vật |
| C04 | Knowledge State của từng nhân vật | NPC không tự biết bí mật chưa được tiết lộ |
| C05 | Quản lý tuyến truyện và foreshadowing | Open threads có trạng thái và chương liên quan |
| C06 | Commit/rollback canon theo checkpoint | Sửa chương cũ không làm trí nhớ “ma” tồn tại |
| C07 | Retrieval nhớ lại theo cảnh | Đưa đúng sự kiện liên quan, có provenance |
| C08 | Mô phỏng NPC hậu trường có giới hạn | Hành động đề xuất không tự thay đổi canon |

### Gói D — Kho truyện thông minh / Creative RAG (P2)

| ID | Nhiệm vụ | Đầu ra / tiêu chí nghiệm thu |
|---|---|---|
| D01 | Import TXT/MD theo lô; EPUB sau | Kiểm tra định dạng, mã hóa, quyền sử dụng |
| D02 | Chia chương/cảnh, khử trùng lặp, metadata nguồn | Không chỉ đọc 10.000 ký tự đầu sách |
| D03 | Phân tích từng cảnh thành thẻ kỹ thuật | Tóm tắt kỹ thuật có dẫn xuất nguồn, không chép đoạn dài |
| D04 | Chạy embedding 0.6B theo lô có thể tiếp tục | Không chiếm GPU khi Writer đang làm việc |
| D05 | Hybrid FTS5 + vector search | Tìm đúng kỹ thuật bằng câu hỏi tiếng Việt |
| D06 | Rerank, lọc theo thể loại/độ liên quan | Chỉ gửi ghi chú hữu ích vào prompt |
| D07 | Kiểm tra sao chép và provenance | Nhận diện đoạn nghi quá giống nguồn; đưa cảnh báo |
| D08 | Đo tác động RAG so với không RAG | Tối thiểu 12 cảnh đối chứng, không chỉ dựa vào cảm giác |

### Gói E — API AI mạnh, mobile và SillyTavern (P2–P3)

| ID | Nhiệm vụ | Đầu ra / tiêu chí nghiệm thu |
|---|---|---|
| E01 | Provider adapters và chọn mô hình theo vai trò | Planner/Critic chạy cloud hoặc local theo cấu hình |
| E02 | Nhập dàn ý từ AI mạnh thủ công và qua API | JSON import/export round-trip không lỗi |
| E03 | Quản lý API key, chi phí, retry/backoff | Không lộ khóa trong UI/log; giới hạn ngân sách |
| E04 | Dashboard tối responsive, đọc bản thảo trên Android | Thao tác được trên màn hình nhỏ và laptop |
| E05 | Giao diện hàng đợi, pause/resume, chấp thuận | Tiến độ per-scene, xem thông báo lỗi |
| E06 | Tailscale Serve + tài liệu kết nối từ xa | Android dùng 4G/5G vẫn truy cập riêng tư |
| E07 | Gateway tương thích SillyTavern | Test chat completions, streaming và lỗi |
| E08 | Đồng bộ trạng thái nhân vật với chế độ phê duyệt | Roleplay không vô tình sửa canon tiểu thuyết |

### Gói F — Hoàn thiện và phát hành nội bộ (P3)

| ID | Nhiệm vụ | Đầu ra / tiêu chí nghiệm thu |
|---|---|---|
| F01 | Unit test + integration test dùng Ollama giả lập | Chạy offline, tái lập lỗi, bao phủ luồng chính |
| F02 | End-to-end 3 chương / ≥12 cảnh | Không mất dữ liệu, xuất bản thảo đủ cảnh |
| F03 | Benchmark RAM/VRAM/nhiệt độ/tốc độ | Không treo máy do tải nhiều mô hình cùng lúc |
| F04 | Thử an toàn dữ liệu và khôi phục backup | Khôi phục được bản thảo trước lỗi |
| F05 | Kiểm thử mobile với 4G, mất kết nối, kết nối lại | Không nhân đôi lệnh khi tải lại trang |
| F06 | Bộ cài Windows, tài liệu tiếng Việt | Cài từ ZIP, một bước khởi động, gỡ cài không mất dự án |

## 12. MỐC PHÁT HÀNH VÀ PHỤ THUỘC

| Mốc | Phạm vi | Điều kiện chấp nhận |
|---|---|---|
| V3.1 — Stable Core | A01–A08 + B01 cơ bản | Chạy/tiếp tục/rollback an toàn, truy cập riêng tư |
| V3.2 — Writing Quality | B01–B08 | Văn phong được đánh giá đối chứng; không mất bản sửa |
| V4.0 — Story Memory | C01–C08 | Canon, timeline, NPC knowledge nhất quán qua nhiều chương |
| V4.1 — Literary Library | D01–D08 | Nhập đủ tài liệu, tìm kỹ thuật có nguồn, so sánh A/B |
| V5.0 — Hybrid & Roleplay | E01–E08, F01–F06 | API có quota, mobile remote, SillyTavern đã test |

**Chuỗi phụ thuộc quan trọng:** A02 trước migration; A04–A06 trước chạy series lớn; B01/B03 trước benchmarking; C01–C07 trước tự đồng bộ nhập vai; D02/D03 trước vector indexing; E03 trước bật API cloud; A07 trước mở điện thoại ngoài nhà.

## 13. KIỂM THỬ, CHỈ SỐ CHẤT LƯỢNG VÀ TIÊU CHÍ NGHIỆM THU

### 13.1. Tiêu chí kỹ thuật (đề xuất)

- Viết liên tục thử **3 chương, tối thiểu 12 cảnh**; mỗi cảnh có bản nháp, nhận xét, bản biên tập và trạng thái.
- Ngắt tiến trình bất kỳ rồi chạy lại: **không mất cảnh đã commit, không xuất trùng**, không ghi đè bản đã chỉnh tay.
- Mọi thay đổi canon có nguồn, trạng thái duyệt và đường hoàn tác.
- Người dùng có thể tạm dừng tại ranh giới cảnh, theo dõi tiến độ từ Android và duyệt một chương.
- Kiểm tra truy cập từ 4G Android qua Tailscale: hoạt động khi laptop bật; khi VPN ngắt thì không truy cập được từ Internet công khai.
- Không có API key trong mã nguồn, kho lưu công khai, HTML/JavaScript hay gói ZIP phát hành.

### 13.2. Tiêu chí văn học (đề xuất)

- Mỗi cảnh chấm 1–5 trên 6 tiêu chí: tự nhiên, lời thoại, tâm lý, nhịp, sáng tạo, nhất quán.
- Mục tiêu thử nghiệm: ít nhất **80%** cảnh đạt **≥4/5** cho tự nhiên tiếng Việt và không có mâu thuẫn canon nghiêm trọng trong bộ nghiệm thu (do người đọc kiểm tra). Đây là **đích thử nghiệm**, không phải cam kết mô hình sẽ đạt.
- Đánh giá A/B: local only, local + Voice Bible, local + RAG, local + cloud Critic. Ghi chi phí/lượt, số vòng chỉnh sửa và đánh giá đọc mù.
- Không dùng điểm tự chấm của chính mô hình làm thước đo duy nhất.

## 14. RỦI RO VÀ PHƯƠNG ÁN GIẢM THIỂU

| Rủi ro | Ảnh hưởng | Biện pháp |
|---|---|---|
| 8B viết sáo rỗng | Cao | Voice Bible, scene packet, biên tập có căn cứ, so sánh mô hình |
| Quên/sai chi tiết sau hàng chục chương | Rất cao | Canon có revision, timeline, knowledge state, retrieval có nguồn |
| Quá tải RTX 3050 6 GB | Cao | Một tác vụ AI/lần, context thận trọng, benchmark thực tế |
| API cloud tốn phí | Trung bình–cao | Quota chương/tháng, duyệt khi gửi, local fallback |
| Mất dữ liệu do crash/viết lại | Rất cao | Transaction, checkpoint, backup, versioning |
| Lộ dữ liệu qua truy cập xa | Rất cao | Bind localhost, Tailscale Serve, HTTPS, token riêng, không mở port |
| Dữ liệu kho truyện có bản quyền | Cao | Nguồn hợp pháp, ghi nguồn, chỉ trừu tượng hóa kỹ thuật |
| RAG đưa nhầm kỹ thuật | Trung bình | Hybrid retrieval, rerank, evaluation trên cảnh thật |
| AI tự sửa làm mất giọng văn | Cao | Diff, sửa cục bộ, tối đa 2 vòng, duyệt |
| NPC làm lệch cốt truyện | Trung bình–cao | Kiến thức riêng, luật canon, duyệt thay đổi lớn |

## 15. CHI PHÍ VẬN HÀNH VÀ PHƯƠNG ÁN CHỌN

| Cấp | Đặc điểm | Phù hợp |
|---|---|---|
| **Local** | Chỉ Ollama; không phí API theo token | Thử nghiệm, riêng tư tối đa; chất lượng giới hạn bởi GPU/mô hình |
| **Hybrid tiết kiệm** | AI mạnh tạo dàn ý thủ công; local viết; cloud critic có chọn lọc | **Khuyến nghị bắt đầu** |
| **Hybrid tự động** | AI mạnh planner/critic qua API; local writer; có quota | Khi quy trình đã ổn định và cần tiết kiệm thao tác |
| **Cloud quality-first** | AI mạnh viết/chỉnh nhiều cảnh hơn | Khi ưu tiên chất lượng hơn riêng tư/chi phí |

Không ghi mức tiền cứng vào thiết kế vì giá API thay đổi; hệ thống phải lấy bảng giá do người dùng cấu hình hoặc kiểm chứng trực tiếp từ nhà cung cấp. Chi phí điện, phần cứng và kết nối mạng vẫn tồn tại ở chế độ local.

## 16. VIỆC CẦN LÀM NGAY — THỨ TỰ ĐỀ XUẤT

**Phía bạn (người sử dụng):**

1. Sao lưu thư mục `project` của Novel Engine hiện tại, đặc biệt SQLite và `drafts`.
2. Chọn **một ý tưởng tiểu thuyết chuẩn** để thử nghiệm; chưa chạy ngay bộ truyện hàng trăm chương.
3. Cung cấp hoặc tự tạo 12 cảnh thử + một Voice Bible mẫu; lưu thành dữ liệu kiểm thử.
4. Chạy `ollama ps` sau khi gọi Qwen3 8B, đo tốc độ và tình trạng CPU/GPU thật.
5. Chọn quy tắc duyệt: **duyệt mỗi chương** hoặc **duyệt khi phát hiện mâu thuẫn lớn**; khuyến nghị duyệt mỗi chương lúc đầu.
6. Xác định có dùng API cloud hay chỉ nhập dàn ý thủ công; không cần mua API khi chưa đánh giá nền tảng.

**Phía phát triển phần mềm:**

1. Hoàn tất A02/A03/A04: backup, tách module, hàng đợi bền vững.
2. Hoàn tất A05/A06: pause/resume và versioning.
3. Chuẩn hóa dàn ý B01 và bộ Voice Bible B02.
4. Xây baseline 12 cảnh B03–B07 để **đo rõ cải thiện**.
5. Thiết kế canon/versioning C01–C07 trước khi tăng mức tự chủ NPC.
6. Sau khi có benchmark và trí nhớ ổn định, thêm D01–D08 và tích hợp cloud/SillyTavern.

### Quyết định cần chốt trước khi lập trình bản ổn định

- **Định dạng dàn ý chính:** JSON có schema; Markdown dùng để hiển thị/sửa.
- **Điểm phê duyệt:** mặc định dừng ở cuối chương cho người dùng duyệt canon.
- **Quy tắc dữ liệu cloud:** mặc định tắt; bật riêng theo từng dự án/tác vụ.
- **Sao lưu:** bản sao định kỳ + trước mọi migration/force rewrite; kiểm tra khôi phục.
- **Cách điều khiển xa:** Tailscale Serve HTTPS riêng, không cổng công khai.

## 17. TÀI LIỆU KỸ THUẬT THAM KHẢO

- Ollama — thư viện Qwen3 8B: https://ollama.com/library/qwen3
- Ollama — embedding Qwen3: https://ollama.com/library/qwen3-embedding
- Ollama — API: https://docs.ollama.com/api
- Tailscale Serve: https://tailscale.com/docs/features/tailscale-serve
- Tailscale HTTPS: https://tailscale.com/docs/how-to/set-up-https-certificates
- SillyTavern Custom OpenAI-compatible: https://docs.sillytavern.app/usage/api-connections/openai/
- OpenAI — API billing và ChatGPT tách riêng: https://help.openai.com/en/articles/9039756-managing-billing-for-chatgpt-and-the-api-platform

**Kết luận cuối:** Thành công của Novel Engine sẽ đến chủ yếu từ **quy trình sáng tác có cấu trúc + bộ nhớ đáng tin + biên tập đo được chất lượng**, không đến từ việc thêm thật nhiều AI hoặc thật nhiều sách. Ưu tiên chuyển V3 từ bản thử nghiệm sang nền tảng ổn định trước, rồi từng bước tăng chất lượng, trí nhớ, Creative RAG và tự động hóa API.
