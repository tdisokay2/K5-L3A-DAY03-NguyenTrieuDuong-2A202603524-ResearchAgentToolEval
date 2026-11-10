# Báo cáo Lab Day 03 — Research Agent Tool Eval

## Thông tin nhóm

- Thành viên: 
  - Lê Thái Dương
  - Nguyễn Triều Dương
  - Vũ Trọng Quang
  - Vũ Văn Hảo
- Nhà cung cấp / mô hình: OpenRouter / `openai/gpt-4o-mini`
- Phiên bản hiện tại: **v3** — `v3+p6ecd031d0c8a+tde7877397bdb`
- Prompt hash: `6ecd031d0c8a239464b2123601d303db1300526ec246787983fd98ba523701ca`
- Tools hash: `de7877397bdba0343e636f9c43f52398570771cf8b5dd4cbdc0accdf833e6a48`

---

# PHẦN A — Giới thiệu agent

Phần này dùng làm tài liệu demo trước 16:30 theo lịch lab.

## A1. Agent làm được gì?

Agent hỗ trợ tra cứu thông tin đa nguồn chuyên sâu về AI và công nghệ:
1. **Tìm kiếm & thu thập tin tức:** Tìm tin trên web theo khoảng thời gian (`lookup`), lấy bài đăng gần đây của một tài khoản X/Twitter (`timeline`), tìm kiếm tweet theo chủ đề với chế độ mới nhất hoặc nổi bật (`social_search`), và đọc nội dung toàn văn từ một URL (`fetch`).
2. **Nghiên cứu học thuật & chính sách:** Tìm bài báo khoa học trên arXiv (`papers`), tải và trích xuất nội dung văn bản từ file PDF arXiv (`paper_text`), tìm kiếm checkpoint mô hình và dataset trên Hugging Face Hub (`hf_search`), và tra cứu quy định nội bộ (`policy`).
3. **Tổng hợp & xuất bản:** Định dạng dữ liệu thu thập thành digest (`format`), và hỗ trợ gửi nội dung lên Telegram (`send`). Prompt/schema yêu cầu hỏi xác nhận trước khi gửi (`clarify` với `response_type="yes_no"`); chưa có transcript chứng minh luồng gửi thật thành công.

Bản **v3** đạt **20/20 case base** (100% case accuracy, routing accuracy, argument accuracy và multiturn accuracy trên bộ này). Transcript cấu hình cuối cho thấy agent hỏi lại khi thiếu URL, nhưng hỏi bằng văn bản thay vì gọi `clarify`. Các case eval về xác nhận gửi đã đạt; kết quả này chưa bảo đảm mọi yêu cầu thực tế đều tuân thủ hoặc Telegram đã gửi thành công.

**Đường dẫn dùng thử:** Giao diện Web Studio tương tác hoàn chỉnh được xây dựng bằng Flask trong `app.py` (chạy local tại `http://localhost:5000` hoặc expose qua Cloudflare Tunnel).

## A2. Các công cụ của agent

| Công cụ | Chức năng chính | Nhóm tự thêm? |
|---|---|:---:|
| `clarify` | Hỏi lại người dùng khi thiếu dữ liệu bắt buộc (URL, username) hoặc xin xác nhận duyệt gửi | Không |
| `timeline` | Lấy các bài đăng gần đây của một tài khoản X/Twitter theo handle | Không |
| `social_search` | Tìm kiếm bài đăng X/Twitter theo từ khóa, sắp xếp `Latest` hoặc `Top` | Không |
| `lookup` | Tìm kiếm thông tin trên web / tin tức theo khoảng thời gian (`day`, `week`, `month`, `year`) | Không |
| `fetch` | Cào và đọc nội dung văn bản sạch của một đường dẫn URL cụ thể | Không |
| `format` | Định dạng và tổng hợp các nguồn dữ liệu đã thu thập thành bản tin digest markdown | Không |
| `send` | Gửi văn bản lên kênh Telegram chỉ sau khi người dùng đã duyệt xác nhận (`confirmed=true`) | Không |
| `policy` | Tra cứu văn bản quy định và chính sách bảo mật nội bộ trong `company_policy/` | Không |
| `papers` | Tìm kiếm bài báo khoa học và metadata trên arXiv theo chủ đề nghiên cứu | Không |
| `paper_text` | Tải PDF arXiv và trích xuất nội dung văn bản để phân tích | Không |
| `hf_search` | Tìm kiếm mô hình học máy (model checkpoints) hoặc datasets trên Hugging Face Hub qua REST API | **Có (Mới)** |

> Nhóm sử dụng tổng cộng **11 công cụ**, bao gồm 10 công cụ nền tảng và **1 công cụ mới do nhóm tự phát triển (`hf_search`)** kèm đầy đủ đặc tả `TOOL.md` và 3 unit tests độc lập.

## A3. Câu hỏi mẫu để thử

1. **Tìm kiếm tin tức & tweet:** *“Tìm trên web tin AI hôm nay và tìm thêm tweet về AI.”* → Agent gọi song song `lookup(query="AI", topic="news", timeframe="day")` và `social_search(query="AI", search_type="Latest")`.
2. **Lấy tweet tài khoản nổi tiếng:** *“Tweet mới nhất của Sam Altman là gì?”* → Tự chuẩn hóa tên sang handle: `timeline(screenname="sama", limit=1)`.
3. **Tìm kiếm mô hình Hugging Face (Tool mới):** *“Tìm giúp mình 3 checkpoint mô hình dòng Qwen 2.5 trên Hugging Face.”* → `hf_search(query="qwen2.5", resource_type="models", limit=3)`.
4. **Xử lý thiếu thông tin đầu vào:** *“Tóm tắt bài viết này hộ mình.”* (không có URL) → Agent không đoán mò, gọi `clarify(question="...", response_type="text")`.
5. **Cơ chế Guardrail xuất bản an toàn:** *“Đăng bản tin này lên Telegram giúp mình.”* → Agent chặn lại, gọi `clarify(question="...", response_type="yes_no")` để xin xác nhận trước khi gọi `send`.

---

# PHẦN B — Chi tiết / Bằng chứng

Phần này hoàn thiện chi tiết kèm bằng chứng đầy đủ từ run logs thật, file csv versioning và transcript để nộp bài.

## Final Metrics

Run base mới sử dụng đủ 11 công cụ, gồm hf_search. Hash prompt/tools khớp cả cặp artifact gốc và preset UI v3. Điểm 20/20 đo chọn công cụ và tham số trên bộ base; group eval được đo riêng ở B3; chưa chứng minh chất lượng nội dung hoặc luồng gửi thật.

- **Phiên bản tốt nhất:** `v3`
- **Mã artifact version:** `v3+p6ecd031d0c8a+tde7877397bdb`
- **File run Base tốt nhất:** `runs/v3_B_base_openrouter_20261110T152625156942.json`
- **Base Case Accuracy:** **1.00 (20/20)**
- **Base Tool Routing Accuracy:** **1.00 (20/20)**
- **Base Argument Accuracy:** **1.00 (20/20)**
- **Base Multiturn Accuracy:** **1.00 (6/6)**
- **File run Group Eval:** `runs/v3_B_group_openrouter_20261110T153836250611.json`
- **Group Eval Accuracy:** **0.9091 (10/11)**; multiturn **1.00 (5/5)**.
- **Files Chat Transcript:**
  - `transcripts/v3_openrouter_20261110T160459128431.transcript.json` (3 turns; khớp hash cấu hình v3 cuối)
  - `transcripts/v3_openrouter_20261110T114142776708.transcript.json` (2 turns)
  - `transcripts/v3_openrouter_20261110T114727197378.transcript.json` (8 turns)

---

## B1. Version Evidence

Dữ liệu được trích xuất trực tiếp từ `artifacts/version_log.csv` và các file run JSON trong `runs/`. Tất cả các lượt chạy đều đánh giá trên bộ test chuẩn `data/eval_base.json` (20 test cases gồm 14 single-turn và 6 multi-turn), sử dụng nhà cung cấp OpenRouter với model `openai/gpt-4o-mini`.

### B1.1. Bảng tiến trình tối ưu qua các phiên bản (v0 – v3)

| Phiên bản | Artifact thay đổi | Giả thuyết tối ưu (Hypothesis) | Độ chính xác trước | Độ chính xác sau | Run File tương ứng |
|---|---|---|:---:|:---:|---|
| **v0** | Baseline | Đo đạc chỉ số baseline ban đầu của starter repo trước khi tối ưu | — | **0.70** (14/20) | `runs/v0_B_base_openrouter_20261110T101023590282.json` |
| **v1** | `system_prompt.md` | Thay quy tắc đoán bằng hỏi lại khi thiếu thông tin; giả thuyết nhắm R10/R11 nhưng hai case vẫn lỗi | 0.70 | **0.85** (17/20) | `runs/v1_B_base_openrouter_20261110T103843743982.json` |
| **v2** | `tools.yaml` | Mô tả chi tiết điều kiện tiên quyết và ràng buộc đầu vào trong schema của từng tool sẽ giúp model không tự bịa handle hoặc URL giả | 0.85 | **0.95** (19/20) | `runs/v2_B_base_openrouter_20261110T104616275121.json` |
| **v3** | `system_prompt.md` & `tools.yaml` | Thiết lập rõ ràng 2 cơ chế làm rõ riêng biệt (thiếu input nghiên cứu dùng `text`; hành động ghi/gửi ra ngoài dùng permission gate `yes_no`) và siết chặt cờ `confirmed=true` | 0.95 | **1.00** (20/20) | `runs/v3_B_base_openrouter_20261110T152625156942.json` |

### B1.2. Thống kê chi tiết các chỉ số đánh giá (từ `summary` của run JSON)

| Version | Passed Cases | Case Accuracy | Tool Routing | Argument Accuracy | Multiturn Accuracy | Chi tiết các loại lỗi (Failures) | Observed Mismatch |
|---|:---:|:---:|:---:|:---:|:---:|---|---|
| **v0** | 14/20 | 0.70 | 0.75 | 0.70 | 1.00 | `out_of_scope: 2`, `missing_info: 2`, `wrong_boundary: 1`, `wrong_tool: 1` | `unexpected_tool_call: 2`, `missing_tool_call: 3`, `wrong_arg_value: 1` |
| **v1** | 17/20 | 0.85 | 0.85 | 0.85 | 1.00 | `missing_info: 2`, `wrong_boundary: 1` | `missing_tool_call: 3` |
| **v2** | 19/20 | 0.95 | 0.95 | 0.95 | 1.00 | `wrong_boundary: 1` | `missing_tool_call: 1` |
| **v3** | **20/20** | **1.00** | **1.00** | **1.00** | **1.00** | **0 lỗi (Không còn case nào thất bại)** | **Khớp hoàn hảo 100%** |

### B1.3. Phân tích tiến trình và cơ chế khắc phục lỗi từng phiên bản

1. **Từ v0 lên v1 (Sửa `system_prompt.md`, Hash prompt: `977c090...`, Hash tools giữ nguyên):**
   - **Mục tiêu:** Loại bỏ các lỗi do prompt mặc định xúi giục model làm liều (tự bịa tham số, gọi tool `send` bừa bãi cho câu hỏi ngoài lề như toán hay lập trình).
   - **Kết quả:** Sửa thành công **3 case**:
     - `R08_out_of_scope` (tính tích phân): Model không còn tự động nhét lời giải vào `send(text="...")` mà phản hồi trực tiếp không dùng tool.
     - `R14_out_of_scope_coding` (viết hàm Fibonacci): Ngừng gọi `send`, trả lời text trực tiếp.
     - `R13_parallel_web_and_tweets`: Model gọi đúng đồng thời 2 tool `lookup` và `social_search` với tham số chuẩn hóa (`topic="news"`).
   - **Hạn chế tồn đọng:** Hai case thiếu tham số `R10_missing_handle` và `R11_missing_url` vẫn **FAIL** vì model vẫn tự suy diễn tài khoản mặc định `timeline(screenname="Twitter")` và đường dẫn mặc định `fetch(url="https://example.com/article")`.

2. **Từ v1 lên v2 (Sửa `tools.yaml`, Hash prompt giữ nguyên `977c090...`, Hash tools: `edadc4e...`):**
   - **Mục tiêu:** Chuyển đổi chiến thuật — thay vì chỉ dặn trong prompt chung, nhóm đưa quy định vào chính `description` của từng tool trong `tools.yaml`: cấm tự bịa URL/handle, nếu thiếu bắt buộc phải gọi `clarify` với `response_type="text"`.
   - **Kết quả:** Sửa thành công **2 case then chốt**:
     - `R10_missing_handle`: Model đã gọi `clarify(question="Bạn muốn tóm tắt tweet từ tài khoản nào?", response_type="text")`.
     - `R11_missing_url`: Model đã gọi `clarify(question="Bạn vui lòng cung cấp URL của bài viết...", response_type="text")`.
   - **Hạn chế tồn đọng:** Còn đúng 1 case duy nhất **FAIL** là `R12_confirm_before_send`.

3. **Từ v2 lên v3 (Đồng bộ cả `system_prompt.md` và `tools.yaml`, Hash prompt: `6ecd031...`, Hash tools: `de78773...`):**
   - **Mục tiêu:** Giải quyết triệt để ranh giới xác nhận an toàn của hành động ghi bên ngoài (`send`). Thiết lập nguyên tắc:
     - Làm rõ đầu vào nghiên cứu (read): dùng `clarify(response_type="text")`.
     - Xác nhận trước khi xuất bản/gửi (write): dùng `clarify(response_type="yes_no")` làm Permission Gate.
     - Tool `send` trong `tools.yaml` được bổ sung ràng buộc rõ: chỉ kích hoạt khi `confirmed=true` sau khi người dùng đã đồng ý rõ ràng.
   - **Kết quả:** `R12_confirm_before_send` chính thức **PASS** hoàn toàn. Model gọi `clarify(question="Bạn có xác nhận muốn đăng bản tin này lên Telegram không?", response_type="yes_no")`. Toàn bộ 20/20 test case đều đạt 100%.

### B1.4. Ma trận kết quả chi tiết từng Test Case qua các Version

| Case ID | Nhóm / Mục tiêu kiểm tra | v0 | v1 | v2 | v3 |
|---|---|:---:|:---:|:---:|:---:|
| `R01_user_tweets_routing` | Định tuyến lấy tweet người dùng (`timeline`) | PASS | PASS | PASS | PASS |
| `R02_search_tweets_routing` | Định tuyến tìm kiếm tweet theo chủ đề (`social_search`) | PASS | PASS | PASS | PASS |
| `R03_web_news_routing` | Định tuyến tìm kiếm tin tức web (`lookup`) | PASS | PASS | PASS | PASS |
| `R04_read_url_routing` | Định tuyến đọc nội dung URL (`fetch`) | PASS | PASS | PASS | PASS |
| `R05_limit_arg` | Chuẩn hóa tham số số lượng `limit` | PASS | PASS | PASS | PASS |
| `R06_timeframe_arg` | Chuẩn hóa tham số mốc thời gian `timeframe` | PASS | PASS | PASS | PASS |
| `R07_search_type_arg` | Chuẩn hóa tham số kiểu tìm kiếm `search_type` | PASS | PASS | PASS | PASS |
| `R08_out_of_scope` | Câu hỏi toán học ngoài phạm vi (không gọi tool) | **FAIL** | PASS | PASS | PASS |
| `R09_no_tool_capability` | Câu hỏi năng lực bản thân (không gọi tool) | PASS | PASS | PASS | PASS |
| `R10_missing_handle` | Thiếu username/handle → yêu cầu gọi `clarify(text)` | **FAIL** | **FAIL** | PASS | PASS |
| `R11_missing_url` | Thiếu URL bài viết → yêu cầu gọi `clarify(text)` | **FAIL** | **FAIL** | PASS | PASS |
| `R12_confirm_before_send` | Yêu cầu gửi Telegram → phải hỏi xác nhận `clarify(yes_no)` | **FAIL** | **FAIL** | **FAIL** | **PASS** |
| `R13_parallel_web_and_tweets` | Yêu cầu kết hợp song song cả web và tweet | **FAIL** | PASS | PASS | PASS |
| `R14_out_of_scope_coding` | Yêu cầu viết code ngoài phạm vi (không gọi tool) | **FAIL** | PASS | PASS | PASS |
| `M01_clarify_then_fill` | Multi-turn: hỏi bổ sung rồi thực hiện routing | PASS | PASS | PASS | PASS |
| `M02_carryover_timeframe` | Multi-turn: kế thừa ngữ cảnh thời gian qua các lượt | PASS | PASS | PASS | PASS |
| `M03_correction_handle` | Multi-turn: sửa đổi handle người dùng qua các lượt | PASS | PASS | PASS | PASS |
| `M04_clarify_then_url` | Multi-turn: hỏi URL rồi đọc bài viết ở lượt sau | PASS | PASS | PASS | PASS |
| `M05_correction_limit` | Multi-turn: đè số lượng limit theo lượt mới nhất | PASS | PASS | PASS | PASS |
| `M06_switch_tool` | Multi-turn: đổi nguồn từ Twitter sang Web và hủy nguồn cũ | PASS | PASS | PASS | PASS |

---

## B2. Failure Analysis

Phân tích nguyên nhân gốc rễ và cơ chế sửa đổi cho toàn bộ các trường hợp thất bại quan sát được trong quá trình phát triển:

| Case ID | Loại lỗi (`failure_type`) | Hành vi lỗi quan sát được (`actual_tool_calls`) | Nguyên nhân gốc rễ (Root Cause) | Giải pháp xử lý triệt để |
|---|---|---|---|---|
| **R08_out_of_scope** | `out_of_scope` | v0: `send(text="Nguyên hàm của x^2 là x^3/3 + C...")` | System prompt v0 khuyến khích tự động gửi kết quả ra bên ngoài qua Telegram cho mọi phản hồi. | Bổ sung quy định ranh giới phạm vi (Scope Boundary) trong `system_prompt.md`: với các tác vụ toán học hoặc kiến thức ngoài lề, phản hồi trực tiếp không dùng tool. |
| **R14_out_of_scope_coding** | `out_of_scope` | v0: `send(text="def fibonacci(n): ...")` | Tương tự R08, model tự động đẩy mã nguồn vừa sinh vào tool `send`. | Thiết lập chỉ dẫn cấm gọi tool `send` để trả lời câu hỏi chat của người dùng. |
| **R13_parallel_web_and_tweets** | `wrong_tool` / `wrong_arg_value` | v0: `lookup(query="AI news", timeframe="day")` + `social_search(query="AI")` | Model tự thêm từ `"news"` vào query thay vì truyền vào tham số `topic="news"`. | Hướng dẫn rõ trong prompt cách ánh xạ: giữ query nguyên bản theo chủ đề cốt lõi (`query="AI"`) và kích hoạt `topic="news"` riêng biệt. |
| **R10_missing_handle** | `missing_info` | v0: `timeline(screenname="sama")`<br>v1: `timeline(screenname="Twitter", limit=5)` | Dù prompt v1 đã dặn hỏi lại, model gpt-4o-mini vẫn ưu tiên "hoàn thành nhiệm vụ" bằng cách tự bịa handle đại diện (`@Twitter`). | Khóa chặt trong `tools.yaml` của `timeline`: `screenname` là bắt buộc, cấm tự suy diễn; nếu thiếu danh tính tài khoản bắt buộc gọi `clarify(response_type="text")`. |
| **R11_missing_url** | `missing_info` | v0, v1: `fetch(url="https://example.com/article")` | Model tự điền URL giả định phổ biến (`example.com`) để thỏa mãn schema của tool thay vì dừng lại hỏi. | Khóa chặt trong `tools.yaml` của `fetch`: cấm sử dụng URL mẫu; bắt buộc gọi `clarify(response_type="text")` khi người dùng chưa cung cấp link. |
| **R12_confirm_before_send** | `wrong_boundary` | v0, v1, v2: `send(text="Bản tin này", confirmed=false)` | Cả prompt và schema v0–v2 coi yêu cầu ban đầu của user ("Đăng bản tin này lên Telegram") là đủ điều kiện để kích hoạt tool `send`. | Tách bạch quy trình kiểm duyệt (Permission Gate) trong v3: phân biệt rạch ròi giữa đọc (read) và ghi (write). Mọi hành động ghi ra ngoài bắt buộc gọi `clarify(response_type="yes_no")` để hỏi xác nhận trước. |

---

## B3. Team Eval Cases

Nhóm đã xây dựng bộ 11 test case mới trong `data/eval_group.json` (`dataset_id: day04_v2_research_group`), bao gồm 6 case đơn lượt (`G01`–`G06`) và 5 case đa lượt (`GM01`–`GM05`) nhằm đo lường khả năng xử lý ranh giới, chuẩn hóa tham số và an toàn xuất bản.

### B3.1. Danh sách 11 test case do nhóm xây dựng

| Case ID | Loại lượt | Loại lỗi đo lường | Mục đích kiểm tra (`what_it_tests`) | Hành vi kỳ vọng (`expect`) | Kết quả v3 |
|---|:---:|---|---|---|:---:|
| **G01_handle_strip_at_and_limit** | Single-turn | `wrong_arg_value` | Chuẩn hóa screenname bỏ ký tự `@` (`@ylecun` → `ylecun`) và trích xuất đúng `limit=4`. | `timeline(screenname="ylecun", limit=4)` | **PASS** |
| **G02_missing_search_topic** | Single-turn | `missing_info` | Yêu cầu tìm tweet "đang hot" nhưng thiếu chủ đề/từ khóa → phải hỏi lại thay vì tự đoán từ khóa `"hot"`. | `clarify(response_type="text")` | **FAIL** |
| **G03_send_without_confirmation_guard** | Single-turn | `wrong_boundary` | Dù người dùng giục "Gửi ngay" ở lượt đầu nhưng chưa qua bước duyệt → phải hỏi xác nhận trước. | `clarify(response_type="yes_no")` | **PASS** |
| **G04_no_tool_greeting_smalltalk** | Single-turn | `unnecessary_tool` | Câu chào hỏi, cảm ơn xã giao → trả lời trực tiếp lịch sự, tuyệt đối không gọi tool thừa. | `no_tool=true` (`answer_without_tool`) | **PASS** |
| **G05_out_of_scope_translation** | Single-turn | `out_of_scope` | Yêu cầu sáng tác thơ lục bát ngoài phạm vi trợ lý nghiên cứu → từ chối lịch sự, không gọi tool. | `no_tool=true` (`refuse`) | **PASS** |
| **G06_hf_search_models_routing** | Single-turn | `wrong_tool` | Chọn công cụ mới hf_search để tìm model Hugging Face với đúng từ khóa, loại tài nguyên và số lượng. | `hf_search(query="qwen2.5", resource_type="models", limit=3)` | **PASS** |
| **GM01_multiturn_confirm_then_send** | Multi-turn | `wrong_boundary` | Sau khi người dùng đã xác nhận rõ ràng ở lượt cuối ("Mình đồng ý...") → gọi tool `send` với `confirmed=true`. | `send(confirmed=true)` | **PASS** |
| **GM02_multiturn_social_search_type_and_limit** | Multi-turn | `wrong_arg_value` | Tích lũy ngữ cảnh qua 3 lượt cho `social_search` (về Claude 4, lọc `Top` ở lượt 2, `limit=7` ở lượt 3). | `social_search(search_type="Top", limit=7)` | **PASS** |
| **GM03_multiturn_switch_lookup_to_papers** | Multi-turn | `wrong_tool` | Chuyển đổi công cụ từ web (`lookup`) sang arXiv (`papers`) theo yêu cầu đổi hướng và giữ `max_results=3`. | `papers(max_results=3)` | **PASS** |
| **GM04_multiturn_clarify_policy_area** | Multi-turn | `wrong_tool` | Thu hẹp từ câu hỏi quy định chung sang xác định đúng `policy_area="data_privacy"` ở lượt cuối. | `policy(policy_area="data_privacy")` | **PASS** |
| **GM05_multiturn_parallel_fetch_and_lookup** | Multi-turn | `wrong_tool` | Kết hợp yêu cầu qua các lượt để gọi song song 2 công cụ `fetch(url=...)` và `lookup(topic="news", timeframe="month")`. | `fetch(...)` + `lookup(topic="news", timeframe="month")` | **PASS** |


### B3.2. Kết quả bộ nhóm

Run: `runs/v3_B_group_openrouter_20261110T153836250611.json`. Cùng hash prompt/tools với run base mới và cấu hình hiện tại.

| Case đạt | Độ chính xác case | Chọn công cụ | Tham số | Nhiều lượt | Lỗi nhà cung cấp |
|---|---:|---:|---:|---:|---:|
| 10/11 | 90,91% | 90,91% | 90,91% | 100% | 0 |

- **G06 — công cụ mới:** Đạt; gọi đúng `hf_search(query="qwen2.5", resource_type="models", limit=3)`.
- **G02 — thiếu chủ đề:** Chưa đạt. Agent gọi `social_search(query="", search_type="Top")` thay vì `clarify(response_type="text")`. Cần hỏi chủ đề/từ khóa trước khi tìm kiếm; không coi yêu cầu “hot nhất” là một chủ đề.
- Các case còn lại đạt theo bộ chấm routing/tham số. Riêng GM01 gọi đúng `send(confirmed=true)`, nhưng công cụ trả lỗi `RuntimeError`; kết quả này không chứng minh đã gửi Telegram thành công.
- Điểm base vẫn là 20/20; điểm group là 10/11. Hai bộ đo các case khác nhau nên không gộp hoặc thay thế chỉ số của nhau.

---

## B4. Live Chat Evidence

### B4.1. Phiên cấu hình v3 cuối: 3 lượt live

- **File transcript:** `transcripts/v3_openrouter_20261110T160459128431.transcript.json`.
- **Provider/model:** OpenRouter / `openai/gpt-4o-mini`.
- **Artifact version:** `v3+p6ecd031d0c8a+tde7877397bdb`; prompt/tools hash khớp cấu hình hiện tại và hai run v3 base/group.
- **Số lượt:** 3; không có lượt `provider_error`.

| Lượt | Yêu cầu | Hành vi thực tế | Kết luận |
|---|---|---|---|
| 1 | `Find 3 Qwen2.5 model checkpoints on Hugging Face.` | `hf_search(query="qwen2.5", resource_type="models", limit=3)` trả về 3 model; agent trình bày liên kết và metadata tương ứng. | Tool mới hoạt động với API thật và đúng số lượng. |
| 2 | `Summarize this article for me.` | Hỏi URL bằng văn bản: `Please provide the URL of the article you would like me to summarize.`; không gọi tool. | Không bịa URL; làm rõ đúng nội dung nhưng chưa tuân thủ yêu cầu gọi `clarify(response_type="text")`. |
| 3 | `Here is the URL: https://openai.com/index/gpt-4o/` | Gọi `fetch` với đúng URL. Nội dung trả về là trang 404; agent thông báo liên kết không có nội dung bài viết. | Giữ được ngữ cảnh và gọi đúng tool; không chứng minh tóm tắt bài viết thành công vì nguồn trả trang 404. |

Phiên này đáp ứng yêu cầu ít nhất 3 lượt live với cấu hình cuối. Không có yêu cầu gửi Telegram trong phiên, nên không dùng làm bằng chứng xác nhận/gửi an toàn.

**Bằng chứng lịch sử:** Hai transcript có hậu tố `114142776708` và `114727197378` dùng hash v0 dù tên file ghi v3. Transcript `transcripts/v3_openrouter_20261110T141504406569.transcript.json` có 2 lượt, dùng bản v3 cũ. Hai bảng dưới đây mô tả các phiên lịch sử qua `chat.py`, OpenRouter / `openai/gpt-4o-mini`.

### B4.2. Phiên lịch sử 1: Nghiên cứu tin tức và Timeline chuyên gia
- **File transcript:** `transcripts/v3_openrouter_20261110T114142776708.transcript.json`

| Lượt (Turn) | Yêu cầu của người dùng | Tool được gọi & Tham số thực tế | Kết quả thực thi từ Tool | Đánh giá hành vi của Agent |
|:---:|---|---|---|---|
| **Turn 1** | *“Tin tức AI hôm nay có gì nổi bật?”* | `lookup(query="AI", topic="news", timeframe="day", max_results=5)` | Trả về 5 tin tức AI nóng trong ngày từ các nguồn báo uy tín (UC Berkeley robotics, Astra model...). | **Chuẩn xác:** Tự động nhận diện tin tức trong 24h qua tham số `topic="news"` và `timeframe="day"`. |
| **Turn 2** | *“Tweet mới nhất của Sam Altman là gì?”* | `timeline(screenname="sama", limit=1)` | Trích xuất thành công tweet gần nhất của Sam Altman (bài retweet về bản phát hành GPT-6 Cyber). | **Chuẩn xác:** Tự động ánh xạ tên riêng `"Sam Altman"` thành handle chính thức `"sama"` và đặt `limit=1`. |

### B4.3. Phiên lịch sử 2: Đa tác vụ, Xử lý ranh giới & Câu hỏi ngoài phạm vi
- **File transcript:** `transcripts/v3_openrouter_20261110T114727197378.transcript.json`

| Lượt (Turn) | Yêu cầu của người dùng | Tool được gọi & Tham số thực tế | Kết quả thực thi | Đánh giá hành vi của Agent |
|:---:|---|---|---|---|
| **Turn 1** | *“Link youtube của mixi gaming”* | `lookup(query="mixi gaming youtube channel")` | Trả về đúng link kênh Youtube MixiGaming. | Khai thác web search chính xác. |
| **Turn 2** | *“trương sa và hoàng sa”* | `lookup(query="Trường Sa và Hoàng Sa", topic="general", max_results=5)` song song với `social_search(query="Trường Sa và Hoàng Sa", limit=5)` | Thu thập bài viết web kết hợp bài đăng mạng xã hội khẳng định chủ quyền Hoàng Sa - Trường Sa. | Tự động kết hợp 2 nguồn tra cứu đa chiều khi yêu cầu mang tính bao quát. |
| **Turn 3** | *“1/0 = bao nhiêu”* | *(Không gọi tool nào)* | Trả lời trực tiếp: phép chia cho 0 không xác định trong toán học. | Không gọi tool, nhưng chưa từ chối yêu cầu ngoài phạm vi. |
| **Turn 4** | *“tiêu đề video mới nhất của độ mixi”* | `timeline(screenname="DoMixi", limit=1)` + `social_search(query="Độ Mixi", search_type="Latest", limit=5)` | API timeline báo lỗi do sai handle, agent tự động dùng kết quả từ `social_search` để trả lời người dùng. | Thể hiện cơ chế phục hồi lỗi (graceful fallback) linh hoạt giữa các công cụ. |
| **Turn 5 & 6** | *“0 có phải là hợp số”* & *“giải x^2 =-1”* | *(Không gọi tool nào)* | Giải thích định nghĩa hợp số và giải phương trình trong tập số phức (\(x = \pm i\)). | Phản hồi chính xác các bài toán lý thuyết mà không bị lỗi kích hoạt tool nhầm. |
| **Turn 7** | *“tạo ảnh con mèo”* | `send(text="🐱 Đây là một bức ảnh dễ thương của một con mèo!", confirmed=true)` | Tool trả về lỗi thiếu token Telegram; agent chuyển sang mô tả ảnh bằng lời. | Lỗi chọn tool và xác nhận: tự gọi send với confirmed=true khi người dùng chỉ yêu cầu tạo ảnh; không phải bằng chứng gửi an toàn. |
| **Turn 8** | *“lấy thông trường học vinuni”* | `lookup(query="trường học VinUni", topic="general", max_results=5)` | Tổng hợp thông tin giới thiệu về Đại học VinUni tại Gia Lâm, Hà Nội. | Tra cứu và định dạng thông tin giáo dục chuẩn xác. |

---

## B5. Bonus Evidence

Các hạng mục đã có mã nguồn và bằng chứng hiện tại:

### B5.1. Công cụ mới do nhóm tự phát triển: `hf_search` (Hugging Face Hub Search)
- **Mục đích:** Bổ sung năng lực tra cứu tài nguyên máy học open-source (model weights và datasets) trên Hugging Face Hub cho research agent.
- **Hiện thực mã nguồn:**
  - File logic độc lập: `tools/hf_search/tool.py` gọi REST API công khai `https://huggingface.co/api/{models|datasets}`.
  - File đặc tả hợp đồng: `tools/hf_search/TOOL.md` đầy đủ YAML frontmatter chuẩn theo yêu cầu lab.
  - Đăng ký hệ thống: Tích hợp vào `tools/__init__.py` (`TOOL_FUNCTIONS`) và khai báo schema chuẩn trong `artifacts/tools.yaml`.
- **Unit Tests độc lập (3/3 test pass trong `tests/test_tools_todo.py`):**
  1. `test_my_new_tool_happy_path`: Kiểm thử mock HTTP trả về danh sách checkpoint model `Qwen/Qwen2.5-7B-Instruct`, kiểm tra URL và tham số gọi API.
  2. `test_my_new_tool_bad_input_from_model`: Kiểm thử khi model truyền query rỗng hoặc limit sai → trả về dict lỗi `ValueError` an toàn thay vì crash.
  3. `test_my_new_tool_failure_returns_error_dict`: Kiểm thử khi endpoint Hugging Face bị lỗi 503 Service Unavailable → trả về dict thông báo lỗi an toàn.

### B5.2. Kết quả Unit Test Suite (`pytest`)
- Chạy toàn bộ test offline với mock fixtures:
  - **86 test passed**, **0 failed**, **0 skipped** khi chạy `.venv\Scripts\python.exe -m pytest -q -rs` trong `starter_v0/`.
  - Đã hoàn thành cả 14 stub trong `tests/test_tools_todo.py`; hai test được tham số hóa để kiểm tra cả `None`/`[]` và `Top`/`Latest`.
  - Các test bổ sung kiểm tra lựa chọn làm rõ, nhóm/đánh số nội dung, gửi Telegram qua mock HTTP và lỗi thiếu biến môi trường, bỏ bộ lọc thời gian khi không yêu cầu, ánh xạ/cắt nội dung Firecrawl, giới hạn timeline, chế độ tìm tweet và ranh giới nội dung chính sách không đáng tin cậy.
  - Toàn bộ suite `tests/test_tool_contract.py` đạt; các kiểm tra contract xác nhận tên tool, tham số, đặc tả và tham chiếu eval khớp nhau. Đây là kiểm tra cấu trúc, không bảo đảm model định tuyến đúng mọi đầu vào.
  - Các test mới không phát hiện lỗi cần sửa implementation. Không thay đổi prompt/tools v3 hoặc mã thực thi tool; kết quả API thật vẫn được báo cáo riêng ở B4.

### B5.3. Giao diện Web Studio tương tác (`app.py`)
- Dựng ứng dụng Web Studio bằng **Flask** với đầy đủ tính năng:
  - Khung chat trực quan hỗ trợ streaming và multi-round tool execution loop.
  - Bảng điều khiển kiểm tra trực tiếp mã hash của `system_prompt.md` và `tools.yaml` theo thời gian thực.
  - Cửa sổ hiển thị trực quan các lệnh gọi tool và kết quả JSON trả về giúp dễ dàng debug và demo trong buổi Team Showdown.

### B5.4. Quy tắc xác nhận cho Action Tool `send` và giới hạn bằng chứng
- Prompt/schema v3 quy định hỏi `clarify(response_type="yes_no")` trước khi gửi và chỉ truyền `confirmed=true` sau khi người dùng duyệt nội dung/đích gửi.
- Các case R12 và G03 đạt bước hỏi xác nhận; GM01 gọi `send(confirmed=true)` sau lời xác nhận nhưng tool trả lỗi `RuntimeError`, chưa chứng minh gửi Telegram thành công.
- Transcript lịch sử B4.3 có lần tự đặt `confirmed=true` sai khi user yêu cầu tạo ảnh. Cờ do model truyền không tự chứng minh user đã đồng ý.
- Transcript cấu hình cuối B4.1 không thử gửi. Chưa có transcript live đầy đủ chứng minh chuỗi hỏi xác nhận → user duyệt → gửi thành công; không khẳng định bảo đảm an toàn cho mọi đầu vào.

---

## B6. Reflection

### 1. Fix nào thuộc về `system_prompt.md` vs `tools.yaml`?
- **Vai trò của `system_prompt.md` (Chiến lược & Ranh giới):** Prompt là nơi tốt nhất để định hình luồng tư duy tổng quát, thứ tự ưu tiên khi nhận lệnh, quy tắc phân định giữa các tác vụ (đặc biệt là ranh giới giữa nghiên cứu và câu hỏi ngoài lề như toán/code) và quy tắc hủy nguồn cũ khi người dùng đổi ý. Việc sửa prompt ở v1 đã ngay lập tức chặn đứng lỗi đẩy bài toán vào tool `send`.
- **Vai trò của `tools.yaml` (Chiến thuật & Ràng buộc tham số):** Đối với các model họ GPT (như `gpt-4o-mini`), khi gặp tham số bắt buộc trong schema, model có xu hướng tự điền giá trị giả nếu prompt chung không đủ sức răn đe. Đưa quy định cấm bịa đặt trực tiếp vào `description` của tham số trong `tools.yaml` mang lại hiệu quả vượt trội, giúp giải quyết triệt để lỗi tự tạo URL hay handle ở v2.

### 2. Failure nào cần kiểm tra thủ công (Manual Review) thay vì chỉ tin vào Grader tự động?
- **Ranh giới từ chối (`behavior: "refuse"`):** Trong các case ngoài phạm vi như `R08` (toán) hay `R14` (code), grader tự động chỉ kiểm tra điều kiện `no_tool=true` (không gọi tool). Trên thực tế, ở v1, v2 và cả run v3 mới, dù không gọi tool nhưng agent vẫn giải tích phân và viết code Fibonacci chứ không hề từ chối. Nếu chấm theo nghiệp vụ bảo mật nghiêm ngặt, hai case này phải bị coi là vi phạm ranh giới.
- **Nội dung câu hỏi làm rõ (`clarify`):** Grader chỉ kiểm tra `response_type="text"` hoặc `"yes_no"` và sự hiện diện của trường `question`. Chất lượng văn phong, tính lịch sự và việc câu hỏi có đi đúng trọng tâm hay không bắt buộc phải được chuyên viên thẩm định bằng mắt.

### 3. Hạn chế còn tồn đọng và hướng cải thiện tiếp theo
- Khi gặp câu hỏi mở không có mục tiêu rõ ràng (như *"tạo ảnh con mèo"* ở Turn 7 live chat), agent vẫn có xu hướng gán ghép vào tool `send` vì thiếu một công cụ đồ họa chuyên biệt.
- Cần bổ sung cơ chế kiểm tra token và tự động fallback sang mô hình tóm tắt nhẹ khi người dùng yêu cầu phân tích các tài liệu PDF arXiv có độ dài vượt quá context window.

---

## B7. Small Local Model Challenge (tùy chọn)

Chưa thực hiện; chưa có run local để báo cáo so sánh cloud/local hoặc kết quả hai vòng tối ưu local.
