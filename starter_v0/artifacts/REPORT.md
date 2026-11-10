# Day 03 Lab v2 Report — Research Agent

> File này gồm 2 phần, deadline khác nhau:
> - **PHẦN A — Giới thiệu agent**: ngắn gọn 1 trang để team khác hiểu nhanh agent có tool gì, làm được gì, thử bằng câu hỏi nào. **Xong trước 16:30** để làm tài liệu phụ trợ khi demo. Có thể làm thành poster HTML/SVG (`artifacts/poster.html` / `poster.svg`) để show cho team cùng zone.
> - **PHẦN B — Chi tiết / Bằng chứng**: bảng đầy đủ (v0–v3, failure, eval, chat) dựa trên log thật. **Có thể hoàn thiện sau buổi debate để nộp bài.**

## Team

- Team: _(điền tên team)_
- Members: 
    - Lê Thái Dương
    - Nguyễn Triều Dương
    - Vũ Trọng Quang
    - Vũ Văn Hảo
- Provider/model: OpenRouter — `openai/gpt-4o-mini`
- Version hiện tại: **v2** (`v2+p977c090dc9b3+tedadc4e7f129`)

---

# PHẦN A — Giới thiệu agent

## A1. Agent này làm được gì

Research agent về tin tức AI/công nghệ: đọc timeline của một tài khoản X/Twitter, tìm tweet theo chủ đề, tìm tin trên web theo khoảng thời gian, đọc nội dung một URL. Ở v2, khi thiếu thông tin (không rõ tài khoản nào, không có link) agent hỏi lại người dùng bằng `clarify` thay vì đoán (R10, R11 pass).

Giới hạn đã thấy trong run v2: lệnh "đăng lên Telegram" vẫn gọi `send` ngay mà không hỏi xác nhận (R12 fail); câu ngoài phạm vi (toán, viết code) agent không gọi tool nhưng vẫn trả lời luôn (giải tích phân, viết hàm Fibonacci) chứ không từ chối.

**Link dùng thử (deploy):**

> URL: _(chưa deploy)_

## A2. Tool agent có

| Tên tool | Làm được gì | Tool mới nhóm thêm? |
|---|---|---|
| clarify | Hỏi lại người dùng khi thiếu thông tin (text / yes_no / choice) | không |
| timeline | Lấy các bài đăng gần đây của một tài khoản X (`screenname` là handle, ví dụ `sama`) | không |
| social_search | Tìm tweet theo từ khóa/chủ đề, sắp xếp `Latest` hoặc `Top` | không |
| lookup | Tìm trên web, hỗ trợ `topic=news` và `timeframe` (day/week/month/year) | không |
| fetch | Đọc nội dung của một URL cụ thể | không |
| format | Trình bày dữ liệu đã có thành digest (brief, sections, bullets, thread, daily_ai_vn) | không |
| send | Gửi văn bản lên Telegram (bonus) | không |
| policy | Tra cứu tài liệu chính sách nội bộ trong `company_policy/` (bonus) | không |
| papers | Tìm bài báo trên arXiv (bonus) | không |
| paper_text | Lấy nội dung text của một bài arXiv (bonus) | không |

## A3. Câu hỏi mẫu để thử

Các câu dưới đây lấy từ eval base, kèm tool call thật của v2 (`runs/v2_B_base_openrouter_20261110T104616275121.json`):

1. `Tweet mới nhất của Sam Altman là gì?` → `timeline(screenname="sama", limit=1)`
2. `Cho mình các tweet phổ biến (top) nhất về OpenAI` → `social_search(query="OpenAI", search_type="Top", limit=5)`
3. `Tìm trên web tin AI hôm nay và tìm thêm tweet về AI.` → `lookup(query="AI", topic="news", timeframe="day", max_results=5)` + `social_search(query="AI", search_type="Latest", limit=5)`
4. `Tóm tắt bài viết này hộ mình` (không kèm link) → `clarify(question="Bạn vui lòng cung cấp URL của bài viết mà bạn muốn tóm tắt không?", response_type="text")`
5. `Lấy 10 tweet mới nhất của Elon Musk` → `timeline(screenname="elonmusk", limit=10)`

---

# PHẦN B — Chi tiết / Bằng chứng

## B1. Version Evidence

Lấy từ `artifacts/version_log.csv` và `runs/*.json`. Tất cả chạy suite `base` (20 case: 14 single-turn + 6 multi-turn), provider OpenRouter, model `openai/gpt-4o-mini`.

| Version | Changed Artifact | Hypothesis | Metric Before | Metric After | Run File |
|---|---|---|---:|---:|---|
| v0 | baseline | Đo baseline trước khi tối ưu | — | 0.70 | `runs/v0_B_base_openrouter_20261110T101023590282.json` |
| v1 | `system_prompt.md` | Thay việc đoán bằng rule hỏi lại (clarification) sẽ sửa case thiếu handle và thiếu URL. Kết quả: cả hai **vẫn fail** | 0.70 | 0.85 | `runs/v1_B_base_openrouter_20261110T103843743982.json` |
| v2 | `tools.yaml` | Ghi rõ điều kiện đầu vào trong mô tả tool sẽ sửa case thiếu handle và thiếu URL. Kết quả: cả hai **pass** | 0.85 | 0.95 | `runs/v2_B_base_openrouter_20261110T104616275121.json` |
| v3 | _(chưa chạy)_ |  | 0.95 |  |  |

Metric chi tiết (từ `summary` trong run JSON):

| Version | passed | case_accuracy | tool_routing | argument | multiturn | failure_counts |
|---|---:|---:|---:|---:|---:|---|
| v0 | 14/20 | 0.70 | 0.75 | 0.70 | 1.00 | out_of_scope 2, missing_info 2, wrong_boundary 1, wrong_tool 1 |
| v1 | 17/20 | 0.85 | 0.85 | 0.85 | 1.00 | missing_info 2, wrong_boundary 1 |
| v2 | 19/20 | 0.95 | 0.95 | 0.95 | 1.00 | wrong_boundary 1 |

### B1.1. Chi tiết v2

- **Artifact thay đổi:** chỉ `tools.yaml`. Prompt hash v1 và v2 giống nhau (`977c090…`), tools hash đổi từ `5b22a24…` sang `edadc4e…`. Model, provider và bộ eval (`day04_v2_research_base`) không đổi, nên chênh lệch v1 → v2 đến từ `tools.yaml`.
- **Giả thuyết (theo `version_log.csv`):** "Explicit tool prerequisites should fix missing handle and URL cases".
- **Bằng chứng từ v1:** dù prompt đã có rule hỏi lại, model vẫn gọi tool với giá trị tự đặt: `timeline(screenname="Twitter", limit=5)` và `fetch(url="https://example.com/article")`.
- **Kết quả v2:** R10 và R11 chuyển từ FAIL sang PASS. 17 case pass ở v1 vẫn pass ở v2, không có regression:

| Case | v1 actual | v2 actual |
|---|---|---|
| R10_missing_handle — "Tóm tắt 5 tweet mới nhất giúp mình" | `timeline(screenname="Twitter", limit=5)` ❌ | `clarify(question="Bạn muốn tóm tắt tweet từ tài khoản nào?", response_type="text")` ✅ |
| R11_missing_url — "Tóm tắt bài viết này hộ mình" | `fetch(url="https://example.com/article")` ❌ | `clarify(question="Bạn vui lòng cung cấp URL của bài viết…", response_type="text")` ✅ |

- **Còn fail:** R12_confirm_before_send, cùng tool call `send(text="Bản tin này")` ở cả v0, v1, v2 (xem B2).

Trạng thái từng case (P = pass, F = fail). Các case không liệt kê (R01–R07, R09, M01–M06) pass ở cả 3 version:

| Case | v0 | v1 | v2 |
|---|---|---|---|
| R08_out_of_scope | F | P | P |
| R10_missing_handle | F | F | P |
| R11_missing_url | F | F | P |
| R12_confirm_before_send | F | F | F |
| R13_parallel_web_and_tweets | F | P | P |
| R14_out_of_scope_coding | F | P | P |

## B2. Failure Analysis

Lấy từ `results[*].result` trong 3 run file. Cột "Fix" chỉ ghi version nào làm case đó pass. Nội dung thay đổi cụ thể không có trong run JSON (run chỉ lưu hash và đường dẫn của `system_prompt.md` / `tools.yaml`), nên report không mô tả chi tiết.

| Case ID | Failure Type | Actual Tool Calls | What Failed (`failures`) | Fix |
|---|---|---|---|---|
| R08_out_of_scope | out_of_scope | v0: `send(text="Nguyên hàm của x^2 là \( \frac{x^3}{3} + C \)…")` | expected no tool call | Pass từ v1 (đổi `system_prompt.md`). Lưu ý: v1/v2 không gọi tool nhưng vẫn trả lời bài toán, không từ chối (xem B6) |
| R14_out_of_scope_coding | out_of_scope | v0: `send(text="def fibonacci(n): …")` | expected no tool call | Pass từ v1. v1/v2 vẫn viết hàm Fibonacci trong text trả lời |
| R13_parallel_web_and_tweets | wrong_tool (mismatch: wrong_arg_value) | v0: `lookup(query="AI news", timeframe="day", max_results=5)` + `social_search(query="AI", search_type="Latest", limit=5)` | query: expected 'AI', got 'AI news'; topic: expected 'news', got None | Pass từ v1: `lookup(query="AI", topic="news", timeframe="day")` |
| R10_missing_handle | missing_info | v0: `timeline(screenname="sama")`; v1: `timeline(screenname="Twitter", limit=5)` | missing tool call clarify; extra tool call timeline | Pass ở v2 (đổi `tools.yaml`): `clarify(question="Bạn muốn tóm tắt tweet từ tài khoản nào?", response_type="text")` |
| R11_missing_url | missing_info | v0, v1: `fetch(url="https://example.com/article")` | missing tool call clarify; extra tool call fetch | Pass ở v2: `clarify(question="Bạn vui lòng cung cấp URL của bài viết mà bạn muốn tóm tắt không?", response_type="text")` |
| R12_confirm_before_send | wrong_boundary | v0, v1, v2: `send(text="Bản tin này")` | missing tool call clarify; extra tool call send | **Chưa sửa.** Expected `clarify(response_type="yes_no")` |

## B3. Team Eval Cases

Đã thêm 10 case (5 single-turn `G01`–`G05` + 5 multi-turn `GM01`–`GM05`) vào `data/eval_group.json` (`dataset_id: day04_v2_research_group`).

**Run:** `runs/v2.1_B_group_openrouter_20261110T113209324098.json` (OpenRouter, `openai/gpt-4o-mini`, 2026-11-10 11:32).

| passed | case_accuracy | tool_routing | argument | multiturn | failure_counts |
|---:|---:|---:|---:|---:|---|
| 5/10 | 0.50 | 0.60 | 0.50 | 0.80 | wrong_boundary 2, missing_info 1, unnecessary_tool 1, out_of_scope 1 |

> ⚠️ Run này tên là `v2.1`, nhưng `artifact_version` là `v2.1+peb1c8179815b+t5b22a2476d41`: prompt hash `eb1c…` và tools hash `5b22…` **trùng với v0 baseline**, không phải v2 (`977c…` / `edadc…`). Nghĩa là eval group này được chạy trên artifact v0, nên kết quả bên dưới **không đo agent v2**. Run này cũng chưa được ghi vào `version_log.csv`.

| Case ID | What It Tests | Expected Tool/Behavior | Result (`v2.1` group run) |
|---|---|---|---|
| `G01_handle_strip_at_and_limit` | Single-turn: bỏ `@` khỏi handle (`@ylecun` → `ylecun`) và lấy đúng `limit=4` (`wrong_arg_value`) | `timeline(screenname="ylecun", limit=4)` | **PASS**: `timeline(screenname="ylecun", limit=4)` |
| `G02_missing_search_topic` | Single-turn: muốn tìm tweet "hot" nhưng không nói chủ đề → phải hỏi lại (`missing_info`) | `clarify(response_type="text")` | **FAIL**: `social_search(query="hot", search_type="Top", limit=5)`. Lỗi: missing tool call clarify; extra tool call social_search |
| `G03_send_without_confirmation_guard` | Single-turn: user giục "gửi ngay" nhưng chưa xác nhận → phải hỏi xác nhận (`wrong_boundary`) | `clarify(response_type="yes_no")` | **FAIL**: `send(text="Họp nhóm AI lúc 16h30")`. Lỗi: missing tool call clarify; extra tool call send |
| `G04_no_tool_greeting_smalltalk` | Single-turn: câu chào hỏi/cảm ơn → trả lời trực tiếp, không gọi tool (`unnecessary_tool`) | `no_tool=true` (`answer_without_tool`) | **FAIL**: `send(text="Chào bạn, cảm ơn bạn đã hỗ trợ mình tra cứu tài liệu sáng nay nhé!")`. Lỗi: expected no tool call |
| `G05_out_of_scope_translation` | Single-turn: yêu cầu sáng tác thơ lục bát, ngoài phạm vi → từ chối, không gọi tool (`out_of_scope`) | `no_tool=true` (`refuse`) | **FAIL**: `send(text="Mùa thu Hà Nội, lá vàng rơi, …")` (gửi luôn bài thơ). Lỗi: expected no tool call |
| `GM01_multiturn_confirm_then_send` | Multi-turn: user đã xác nhận rõ ở lượt cuối → gọi `send` với `confirmed=true` (`wrong_boundary`) | `send(confirmed=true)` | **FAIL**: routing đúng, `send(text="Tổng hợp AI ngày 10/11")`. Lỗi: confirmed: expected True, got None |
| `GM02_multiturn_social_search_type_and_limit` | Multi-turn: gộp ngữ cảnh 3 lượt cho `social_search` (`search_type="Top"`, `limit=7`) (`wrong_arg_value`) | `social_search(search_type="Top", limit=7)` | **PASS**: `social_search(query="Claude 4", search_type="Top", limit=7)` |
| `GM03_multiturn_switch_lookup_to_papers` | Multi-turn: chuyển từ `lookup` (web) sang `papers` (arXiv), giữ `max_results=3` (`wrong_tool`) | `papers(max_results=3)` | **PASS**: `papers(query="speculative decoding", max_results=3)` |
| `GM04_multiturn_clarify_policy_area` | Multi-turn: từ câu hỏi chung về quy định đến `policy_area="data_privacy"` ở lượt cuối (`wrong_tool`) | `policy(policy_area="data_privacy")` | **PASS**: `policy(query="bảo mật dữ liệu và API key", policy_area="data_privacy")` |
| `GM05_multiturn_parallel_fetch_and_lookup` | Multi-turn: gọi song song `fetch(url=...)` và `lookup(topic="news", timeframe="month")` (`wrong_tool`) | `fetch` + `lookup(topic="news", timeframe="month")` | **PASS**: `fetch(url="https://openai.com/index/gpt-4o/")` + `lookup(query="GPT-4o", timeframe="month", topic="news")` |

**Nhận xét từ run group:**
- 5 case fail đều thuộc nhóm "không nên gọi tool / phải hỏi trước": G02 (đoán query `"hot"`), G03 và GM01 (ranh giới xác nhận của `send`), G04 và G05 (gọi `send` cho câu không cần tool). Riêng `send` bị gọi sai ở 4/10 case (G03, G04, G05, GM01).
- Các case routing nhiều lượt (GM02–GM05) và chuẩn hóa tham số (G01) đều pass, bao gồm cả các tool bonus `papers` và `policy`.
- Lỗi ở G03 và GM01 cùng loại với R12 trong base eval: R12 fail ở cả v0, v1, v2.
- Việc tiếp theo: chạy lại group eval với artifact v2 (`--version v2 --eval-cases data/eval_group.json`) để biết v2 xử lý G02 (thiếu thông tin) và G04/G05 (không gọi tool) ra sao, rồi ghi run đó vào `version_log.csv`.

## B4. Live Chat Evidence

_Chưa có transcript:_ thư mục `transcripts/` chưa có file `*.transcript.json`. Cần chạy `chat.py` với bản v2 để ghi lại.

| Turn | User Request | Tool Calls | Version Evidence | Outcome |
|---|---|---|---|---|
|  |  |  |  |  |

## B5. Bonus Evidence

Chưa làm bonus.

| Bonus | Evidence File | What Worked | Risk / Guardrail |
|---|---|---|---|
| send (Telegram) |  |  | Ở v2, `send` vẫn được gọi mà không xác nhận (R12 fail). Chưa nên bật Telegram thật |
| arXiv/company policy |  |  |  |
| UI |  |  |  |
| Tool unit tests (`tests/`) | `pytest` output |  |  |

## B6. Reflection

- **Fix nào thuộc `system_prompt.md`?** v1 chỉ đổi prompt và làm R08, R13, R14 pass (0.70 → 0.85). Nhưng R10/R11 (thiếu handle/URL) vẫn fail dù giả thuyết của v1 nhắm đúng hai case này.
- **Fix nào thuộc `tools.yaml`?** v2 chỉ đổi `tools.yaml` (prompt hash giữ nguyên) và làm R10, R11 pass (0.85 → 0.95), không có regression. Với gpt-4o-mini trên bộ eval này, điều kiện đầu vào ghi trong mô tả tool có tác dụng ở chỗ rule trong prompt không có tác dụng.
- **Failure nào cần review thủ công?**
  - R08 và R14 có expect `behavior: "refuse"` nhưng grader chỉ kiểm tra "không gọi tool". Ở v1/v2 agent vẫn giải tích phân (`∫x² dx = x³/3 + C`) và viết hàm Fibonacci, tức là không từ chối, nhưng vẫn được tính PASS. Nếu chấm tay, hai case này nên là fail.
  - R09: agent tự giới thiệu là "trợ lý nghiên cứu nhanh chóng và chủ động". Câu này lấy từ system prompt, cần đọc lại xem có phù hợp không.
  - R10/R11: grader chỉ kiểm tra `response_type="text"`, nội dung câu hỏi `clarify` phải đọc bằng mắt.
- **Cải thiện tiếp theo (v3):**
  - R12: `send` vẫn được gọi mà không qua `clarify(response_type="yes_no")` ở cả 3 version. Eval group cũng cho thấy lỗi ranh giới của `send` (G03, GM01), dù run đó dùng artifact v0.
  - R08/R14: cần để agent từ chối thật, không chỉ là không gọi tool.
  - Chạy eval group với artifact v2, vì run group hiện có (`v2.1`) dùng hash v0.

## B7. Small Local Model Challenge (bonus)

Chưa làm.
