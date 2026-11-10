# Báo cáo Lab Day 03 — Research Agent Tool Eval

## Thông tin nhóm

- Tên nhóm: Chưa điền.
- Thành viên: Lê Thái Dương, Nguyễn Triều Dương, Vũ Trọng Quang, Vũ Văn Hảo.
- Nhà cung cấp / mô hình: OpenRouter / `openai/gpt-4o-mini`.
- Phiên bản hiện tại: **v3** — `v3+p614d95d13173+t0c628305936a`.

# PHẦN A — Giới thiệu agent

Phần này dùng làm tài liệu demo trước 16:30 theo lịch lab.

## A1. Agent làm được gì?

Agent hỗ trợ tìm tin trên web, tìm bài đăng X/Twitter, đọc một URL và trình bày dữ liệu nghiên cứu thành bản tổng hợp. Agent có các công cụ mở rộng để tìm paper arXiv, đọc paper và tra cứu chính sách nội bộ.

Bản v3 đạt **20/20 case base** về chọn công cụ và tham số; biết hỏi khi thiếu tài khoản/URL và hỏi xác nhận trước yêu cầu đăng Telegram. Kết quả này chưa chứng minh mọi nguồn trả về đều đúng hoặc luồng gửi Telegram đã được kiểm thử đầy đủ.

**Đường dẫn dùng thử:** Chưa có URL công khai. Hiện có mã giao diện Flask trong `app.py`; nhóm cần hoàn tất phương án Streamlit hoặc Vercel theo yêu cầu lab.

## A2. Các công cụ của agent

| Công cụ | Chức năng | Nhóm tự thêm? |
|---|---|---|
| `clarify` | Hỏi thông tin còn thiếu hoặc yêu cầu xác nhận | Không |
| `timeline` | Lấy bài đăng gần đây của một tài khoản X/Twitter | Không |
| `social_search` | Tìm bài đăng theo từ khóa, sắp xếp mới nhất hoặc nổi bật | Không |
| `lookup` | Tìm web hoặc tin tức theo khoảng thời gian | Không |
| `fetch` | Đọc nội dung một URL | Không |
| `format` | Trình bày các mục dữ liệu đã có thành bản tổng hợp | Không |
| `send` | Gửi văn bản lên Telegram sau khi được xác nhận | Không |
| `policy` | Tra cứu chính sách nội bộ | Không |
| `papers` | Tìm bài báo khoa học trên arXiv | Không |
| `paper_text` | Tải và trích văn bản từ paper arXiv | Không |

Nhóm đang sử dụng 10 công cụ có sẵn. **Chưa có công cụ mới do nhóm tự viết** theo yêu cầu bắt buộc.

## A3. Câu hỏi mẫu để thử

1. “Tweet mới nhất của Sam Altman là gì?”
2. “Cho mình các tweet phổ biến nhất về OpenAI.”
3. “Tìm trên web tin AI hôm nay và tìm thêm tweet về AI.”
4. “Tóm tắt bài viết này hộ mình.” — chưa có URL thì agent cần hỏi lại.
5. “Đăng bản tin này lên Telegram giúp mình.” — agent cần hỏi xác nhận.
