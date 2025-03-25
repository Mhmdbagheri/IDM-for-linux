import sys
import os
import requests
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QTableWidget, QTableWidgetItem, QPushButton, QLineEdit,
                             QMessageBox, QFileDialog, QDialog, QLabel, QComboBox,
                             QTimeEdit, QProgressBar, QTextEdit, QSpinBox)
from PyQt5.QtCore import Qt, QTimer, QTime
from PyQt5.QtGui import QColor

class DownloadSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Download Settings" if parent.language == "en" else "تنظیمات دانلود")
        self.setGeometry(200, 200, 400, 300)
        self.save_path = ""
        self.start_time = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        save_label = QLabel("Save Location:" if self.parent().language == "en" else "محل ذخیره‌سازی:")
        layout.addWidget(save_label)
        self.save_button = QPushButton("Choose..." if self.parent().language == "en" else "انتخاب...")
        self.save_button.clicked.connect(self.choose_save_path)
        layout.addWidget(self.save_button)

        time_label = QLabel("Start Time (Optional):" if self.parent().language == "en" else "زمان شروع (اختیاری):")
        layout.addWidget(time_label)
        self.time_edit = QTimeEdit()
        self.time_edit.setTime(QTime.currentTime())
        layout.addWidget(self.time_edit)

        confirm_button = QPushButton("Start Download" if self.parent().language == "en" else "شروع دانلود")
        confirm_button.clicked.connect(self.accept)
        layout.addWidget(confirm_button)

        self.setLayout(layout)

    def choose_save_path(self):
        self.save_path = QFileDialog.getExistingDirectory(self, "Select Save Location" if self.parent().language == "en" else "محل ذخیره‌سازی را انتخاب کنید")
        if self.save_path:
            self.save_button.setText(self.save_path)

    def get_settings(self):
        return self.save_path, self.time_edit.time()

class DownloadDetailsDialog(QDialog):
    def __init__(self, download, parent=None):
        super().__init__(parent)
        self.download = download
        self.setWindowTitle(f"Details: {download['filename']}")
        self.setGeometry(300, 300, 500, 400)
        self.init_ui()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(500)

    def init_ui(self):
        layout = QVBoxLayout()

        self.status_label = QLabel()
        layout.addWidget(self.status_label)

        self.size_label = QLabel()
        layout.addWidget(self.size_label)

        self.downloaded_label = QLabel()
        layout.addWidget(self.downloaded_label)

        self.speed_label = QLabel()
        layout.addWidget(self.speed_label)

        self.time_left_label = QLabel()
        layout.addWidget(self.time_left_label)

        self.parts_layout = QVBoxLayout()
        self.part_bars = []
        for i, part in enumerate(self.download["parts"]):
            part_label = QLabel(f"Part {i + 1}:")
            self.parts_layout.addWidget(part_label)
            bar = QProgressBar()
            bar.setStyleSheet("QProgressBar::chunk { background-color: #00cc00; }")
            self.part_bars.append(bar)
            self.parts_layout.addWidget(bar)

        layout.addLayout(self.parts_layout)

        cancel_button = QPushButton("Cancel Download" if self.parent().language == "en" else "لغو دانلود")
        cancel_button.clicked.connect(self.cancel_download)
        layout.addWidget(cancel_button)

        self.setLayout(layout)
        self.update_ui()

    def update_ui(self):
        self.status_label.setText(f"Status: {self.download['status']}")
        self.size_label.setText(f"Size: {self.download['size']:.2f} MB")
        downloaded_mb = self.download["downloaded"] / (1024 * 1024)
        self.downloaded_label.setText(f"Downloaded: {downloaded_mb:.2f} MB")
        self.speed_label.setText(f"Speed: {self.download['speed']:.2f} KB/s")

        remaining_bytes = (self.download["size"] * 1024 * 1024) - self.download["downloaded"]
        time_left = remaining_bytes / (self.download["speed"] * 1024) if self.download["speed"] > 0 else 0
        self.time_left_label.setText(f"Time Left: {int(time_left)} sec")

        for i, part in enumerate(self.download["parts"]):
            self.part_bars[i].setMaximum(part["end"] - part["start"] + 1)
            self.part_bars[i].setValue(part["downloaded"])

    def cancel_download(self):
        self.download["cancelled"] = True
        self.download["status"] = "لغو شده" if self.parent().language == "fa" else "Cancelled"
        self.close()

class DownloadManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.language = "fa"
        self.setWindowTitle("دانلود منیجر پیشرفته (IDM لینوکس)" if self.language == "fa" else "Advanced Download Manager (Linux IDM)")
        self.setGeometry(100, 100, 900, 600)
        self.downloads = []
        self.active_downloads = 0
        self.max_concurrent_downloads = 2
        self.download_queue = []
        self.network_speed = 0
        self.init_ui()
        self.measure_network_speed()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        lang_layout = QHBoxLayout()
        lang_label = QLabel("زبان | Language:")
        lang_layout.addWidget(lang_label)
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["فارسی", "English"])
        self.lang_combo.currentTextChanged.connect(self.change_language)
        lang_layout.addWidget(self.lang_combo)
        layout.addLayout(lang_layout)

        concurrent_layout = QHBoxLayout()
        concurrent_label = QLabel("حداکثر دانلود همزمان | Max Concurrent Downloads:")
        concurrent_layout.addWidget(concurrent_label)
        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 10)
        self.concurrent_spin.setValue(self.max_concurrent_downloads)
        self.concurrent_spin.valueChanged.connect(self.update_concurrent_downloads)
        concurrent_layout.addWidget(self.concurrent_spin)
        layout.addLayout(concurrent_layout)

        self.url_input = QTextEdit()
        self.url_input.setPlaceholderText("لینک‌ها را وارد کنید (هر لینک در یک خط)...\n" if self.language == "fa" else "Enter links (one per line)...\n")
        layout.addWidget(self.url_input)

        add_button = QPushButton("اضافه کردن دانلود" if self.language == "fa" else "Add Downloads")
        add_button.clicked.connect(self.add_downloads)
        layout.addWidget(add_button)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.update_table_headers()
        self.table.setRowCount(0)
        self.table.cellDoubleClicked.connect(self.show_details)
        layout.addWidget(self.table)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_table)
        self.timer.start(500)

        self.queue_timer = QTimer()
        self.queue_timer.timeout.connect(self.process_queue)
        self.queue_timer.start(1000)

    def measure_network_speed(self):
        test_url = "http://speedtest.tele2.net/1MB.zip"
        try:
            start_time = time.time()
            response = requests.get(test_url, stream=True)
            total_downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    total_downloaded += len(chunk)
            elapsed = time.time() - start_time
            self.network_speed = (total_downloaded / 1024) / elapsed if elapsed > 0 else 1000
            print(f"Network speed: {self.network_speed:.2f} KB/s")
        except Exception as e:
            self.network_speed = 1000
            print(f"Error measuring network speed: {e}")

    def update_concurrent_downloads(self):
        self.max_concurrent_downloads = self.concurrent_spin.value()

    def update_table_headers(self):
        headers = ["نام فایل", "اندازه (MB)", "پیشرفت", "سرعت (KB/s)", "وضعیت", "عملیات"] if self.language == "fa" else \
                  ["File Name", "Size (MB)", "Progress", "Speed (KB/s)", "Status", "Actions"]
        self.table.setHorizontalHeaderLabels(headers)

    def change_language(self, lang):
        self.language = "en" if lang == "English" else "fa"
        self.setWindowTitle("دانلود منیجر پیشرفته (IDM لینوکس)" if self.language == "fa" else "Advanced Download Manager (Linux IDM)")
        self.url_input.setPlaceholderText("لینک‌ها را وارد کنید (هر لینک در یک خط)...\n" if self.language == "fa" else "Enter links (one per line)...\n")
        self.update_table_headers()
        self.update_table()

    def add_downloads(self):
        urls = self.url_input.toPlainText().strip().split("\n")
        if not urls or all(not url.strip() for url in urls):
            QMessageBox.critical(self, "خطا" if self.language == "fa" else "Error", 
                                "لطفاً حداقل یک لینک وارد کنید!" if self.language == "fa" else "Please enter at least one link!")
            return

        settings_dialog = DownloadSettingsDialog(self)
        if settings_dialog.exec_():
            save_path, start_time = settings_dialog.get_settings()
            if not save_path:
                QMessageBox.warning(self, "هشدار" if self.language == "fa" else "Warning", 
                                   "محل ذخیره‌سازی انتخاب نشد!" if self.language == "fa" else "Save location not selected!")
                return

            for url in urls:
                url = url.strip()
                if not url:
                    continue
                filename = url.split("/")[-1] or "unknown_file"
                full_path = os.path.join(save_path, filename)
                download_info = {
                    "url": url,
                    "filename": filename,
                    "full_path": full_path,
                    "size": 0,
                    "downloaded": 0,
                    "speed": 0,
                    "status": "در انتظار" if self.language == "fa" else "Pending",
                    "parts": [],
                    "pause": False,
                    "cancelled": False,
                    "start_time": start_time,
                    "total_size": 0,
                    "estimated_time": 0
                }
                self.downloads.append(download_info)
                self.download_queue.append(len(self.downloads) - 1)
                print(f"Added to queue: {url}")

            self.update_table()

    def process_queue(self):
        if self.active_downloads >= self.max_concurrent_downloads:
            print(f"Active downloads: {self.active_downloads}, Max: {self.max_concurrent_downloads}, Queue: {len(self.download_queue)}")
            return

        for index in self.download_queue[:]:
            download = self.downloads[index]
            current_time = QTime.currentTime()
            if download["start_time"] <= current_time:
                print(f"Starting download for: {download['url']}")
                self.download_queue.remove(index)
                self.active_downloads += 1
                threading.Thread(target=self.start_download, args=(index,)).start()
            else:
                print(f"Waiting for start time: {download['start_time'].toString()} (Current: {current_time.toString()})")

    def start_download(self, index):
        download = self.downloads[index]
        download["status"] = "در حال دانلود" if self.language == "fa" else "Downloading"
        print(f"Starting download: {download['url']}")
        try:
            response = requests.head(download["url"], allow_redirects=True)
            total_size = int(response.headers.get("content-length", 0))
            if total_size == 0:
                raise ValueError("Could not determine file size")
            download["total_size"] = total_size
            download["size"] = total_size / (1024 * 1024)

            download["estimated_time"] = (total_size / 1024) / self.network_speed if self.network_speed > 0 else 0

            num_parts = min(16, max(4, int(total_size / (1024 * 1024 * 10))))
            accept_ranges = response.headers.get("accept-ranges", "none") == "bytes"
            print(f"Accept-Ranges: {accept_ranges}, Total Size: {total_size}, Parts: {num_parts}")
            if accept_ranges and total_size > 0:
                part_size = total_size // num_parts
                download["parts"] = [{"start": i * part_size, "end": (i + 1) * part_size - 1 if i < num_parts - 1 else total_size - 1, "downloaded": 0} for i in range(num_parts)]
                with ThreadPoolExecutor(max_workers=num_parts) as executor:
                    futures = [executor.submit(self.download_part, index, i) for i in range(num_parts)]
                    for future in futures:
                        future.result()
            else:
                download["parts"] = [{"start": 0, "end": total_size - 1, "downloaded": 0}]
                self.download_part(index, 0)

            if download["cancelled"]:
                return

            if all(p["downloaded"] >= (p["end"] - p["start"] + 1) for p in download["parts"]):
                with open(download["full_path"], "wb") as f:
                    for i in range(len(download["parts"])):
                        with open(f"{download['full_path']}.part{i}", "rb") as pf:
                            f.write(pf.read())
                        os.remove(f"{download['full_path']}.part{i}")
                download["status"] = "تمام شده" if self.language == "fa" else "Completed"
                print(f"Download completed: {download['url']}")
        except Exception as e:
            download["status"] = f"خطا: {str(e)}" if self.language == "fa" else f"Error: {str(e)}"
            print(f"Download error: {str(e)}")
        finally:
            self.active_downloads -= 1
            print(f"Download finished, Active downloads: {self.active_downloads}")

    def download_part(self, index, part_idx):
        download = self.downloads[index]
        part = download["parts"][part_idx]
        headers = {"Range": f"bytes={part['start']}-{part['end']}"}
        try:
            response = requests.get(download["url"], headers=headers, stream=True)
            response.raise_for_status()
            with open(f"{download['full_path']}.part{part_idx}", "wb") as f:
                start_time = time.time()
                for chunk in response.iter_content(chunk_size=8192):
                    if download["cancelled"]:
                        break
                    if download["pause"]:
                        download["status"] = "متوقف" if self.language == "fa" else "Paused"
                        while download["pause"] and not download["cancelled"]:
                            time.sleep(1)
                        download["status"] = "در حال دانلود" if self.language == "fa" else "Downloading"
                    if chunk:
                        f.write(chunk)
                        part["downloaded"] += len(chunk)
                        download["downloaded"] += len(chunk)
                        elapsed = time.time() - start_time
                        download["speed"] = (download["downloaded"] / 1024) / elapsed if elapsed > 0 else 0

            if download["cancelled"]:
                if os.path.exists(f"{download['full_path']}.part{part_idx}"):
                    os.remove(f"{download['full_path']}.part{part_idx}")
                return
        except Exception as e:
            download["status"] = f"خطا: {str(e)}" if self.language == "fa" else f"Error: {str(e)}"
            print(f"Part {part_idx} error: {str(e)}")

    def update_table(self):
        self.table.setRowCount(len(self.downloads))
        for i, download in enumerate(self.downloads):
            self.table.setItem(i, 0, QTableWidgetItem(download["filename"]))
            self.table.setItem(i, 1, QTableWidgetItem(f"{download['size']:.2f}"))
            progress = (download["downloaded"] / download["total_size"] * 100) if download["total_size"] > 0 else 0
            self.table.setItem(i, 2, QTableWidgetItem(f"{progress:.1f}%"))
            self.table.setItem(i, 3, QTableWidgetItem(f"{download['speed']:.2f}"))
            self.table.setItem(i, 4, QTableWidgetItem(download["status"]))

            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            pause_btn = QPushButton("توقف" if download["status"] == ("در حال دانلود" if self.language == "fa" else "Downloading") else "ادامه")
            pause_btn.clicked.connect(lambda _, idx=i: self.toggle_pause(idx))
            btn_layout.addWidget(pause_btn)

            cancel_btn = QPushButton("لغو" if self.language == "fa" else "Cancel")
            cancel_btn.clicked.connect(lambda _, idx=i: self.cancel_download(idx))
            btn_layout.addWidget(cancel_btn)

            self.table.setCellWidget(i, 5, btn_widget)

    def show_details(self, row, column):
        if row < 0 or row >= len(self.downloads):
            return
        download = self.downloads[row]
        details_dialog = DownloadDetailsDialog(download, self)
        details_dialog.exec_()

    def toggle_pause(self, index):
        download = self.downloads[index]
        if download["status"] in ["در حال دانلود", "متوقف", "Downloading", "Paused"]:
            download["pause"] = not download["pause"]

    def cancel_download(self, index):
        download = self.downloads[index]
        download["cancelled"] = True
        download["status"] = "لغو شده" if self.language == "fa" else "Cancelled"
        for i in range(len(download["parts"])):
            part_file = f"{download['full_path']}.part{i}"
            if os.path.exists(part_file):
                os.remove(part_file)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DownloadManager()
    window.show()
    sys.exit(app.exec_())