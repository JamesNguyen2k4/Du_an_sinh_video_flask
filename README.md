1. Cài đặt Python (phiên bản tương thích)
Cài Python 3.10 64-bit
Kiểm tra phiên bản: python --version
2. Cài đặt thư viện phụ thuộc
Chạy lệnh trong thư mục dự án:
pip install --upgrade pip
pip install -r requirements.txt
3. Tải các model checkpoint và file lớn
Vì checkpoints/ bị ignore, người dùng phải tải riêng các file model.
cd scripts
bash download_models.sh
4. Cài đặt và cấu hình ffmpeg
Tải ffmpeg và thêm vào biến môi trường PATH
Kiểm tra ffmpeg -version và ffprobe -version
5. Chạy dự án
Chạy lệnh
python app_sadtalker_simple.py
6. Cập nhật mã nguồn
Khi có cập nhật mới: chạy lệnh
git pull origin main