# AutoVietSub Studio

Ứng dụng desktop LOCAL để tự động hóa quy trình vietsub video: quản lý dự án, nhập SRT, OCR hard-sub (tùy môi trường), ASR (tùy model), dịch AI qua API chính thức, kiểm tra từng dòng, TTS provider, đồng bộ và render FFmpeg.

> Đây là **bản nền tảng/MVP có kiến trúc production-oriented**, không giả vờ có các API/model độc quyền chưa được cung cấp. Các provider được tách lớp để có thể bổ sung mà không phá kiến trúc.

## Điểm chính

- Desktop UI bằng PySide6, Simple/Advanced mode.
- Project file JSON + autosave + checkpoint.
- Subtitle editor, SRT parser/writer.
- Translation engine có batch/retry từng dòng và validator.
- AI provider tương thích OpenAI API (không lấy cookie ChatGPT Web).
- OCR/ASR/TTS theo kiểu optional provider; thiếu dependency thì app vẫn mở và báo rõ.
- Video pipeline FFmpeg: aspect ratio, blur regions, subtitle burn-in hooks, export.
- Performance preset Light/Balanced/Strong.
- Vietnamese/English UI scaffold.
- Logging và error handling.

## Chạy nhanh

1. Cài Python 3.11+.
2. Cài dependency:

```powershell
py -m pip install -r requirements.txt
```

3. Chạy:

```powershell
py -m app.main
```

Hoặc chạy `run.bat`.

## FFmpeg

Đặt `ffmpeg.exe` trong `bin/` hoặc để FFmpeg có trong PATH. App sẽ tự phát hiện.

## AI translation

Đặt biến môi trường `OPENAI_API_KEY` hoặc nhập trong Settings. App chỉ sử dụng API chính thức. Không đọc cookie/session của ChatGPT Web.

## Tùy chọn model

- OCR: `pytesseract` + Tesseract OCR nếu cài trên máy.
- ASR: `faster-whisper` nếu cài và tải model.
- TTS: provider interface sẵn sàng để nối local TTS/API TTS.

## Kiến trúc

```text
app/
  core/        domain + parsers + pipeline + persistence
  providers/   AI/OCR/ASR/TTS/video abstraction
  ui/          PySide6 screens
  main.py
```

## Lưu ý

Không có hệ thống nào có thể cam kết “không bao giờ có lỗi” hoặc “dịch đúng 100%”. Thiết kế này ưu tiên checkpoint, validation, retry từng dòng, logs, recovery và test để giảm lỗi và giảm phạm vi ảnh hưởng khi lỗi xảy ra.
