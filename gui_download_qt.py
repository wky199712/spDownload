import sys
import os
import re
import threading
import yt_dlp
from urllib.request import urlopen
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout,
    QHBoxLayout, QComboBox, QProgressBar, QMessageBox, QFrame, QListWidget, QListWidgetItem, QDialog, QSlider,
    QSizePolicy, QTabWidget  # 添加 QTabWidget
)
from PyQt5.QtGui import QPixmap, QImage, QIcon, QMouseEvent, QColor
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QPoint, QEvent, QTimer, QUrl, QSize, QPropertyAnimation
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtWidgets import QGraphicsDropShadowEffect
import ctypes
from ctypes import wintypes
from PyQt5.QtCore import QRect
import socket
from concurrent.futures import ThreadPoolExecutor
import json

# 创建下载文件夹
if not os.path.exists("download"):
    os.makedirs("download")

def safe_filename(title):
    return re.sub(r'[\\/:*?"<>|]', '_', title)

class DownloadSignals(QObject):
    progress = pyqtSignal(float)
    finished = pyqtSignal()
    error = pyqtSignal(str)

class TitleBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setStyleSheet("background:#00a1d6;")
        self.parent = parent
        self.init_ui()
        self.moving = False
        self._drag_pos = None

    def init_ui(self):
        hbox = QHBoxLayout(self)
        hbox.setContentsMargins(0, 0, 0, 0)

        # Logo
        try:
            pixmap = QPixmap("icon.ico").scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.logo = QLabel()
            self.logo.setPixmap(pixmap)
        except Exception:
            self.logo = QLabel("B")
            self.logo.setStyleSheet("color:white;font-size:18px;font-weight:bold;")
        hbox.addWidget(self.logo)
        hbox.addSpacing(4)

        # Title
        self.title = QLabel("自制视频下载器")
        self.title.setStyleSheet("color:white;font-size:14px;font-weight:bold;")
        hbox.addWidget(self.title)
        hbox.addStretch()

        # Minimize
        self.btn_min = QPushButton("—")
        self.btn_min.setObjectName("title_btn_min")
        self.btn_min.setFixedSize(32, 28)
        self.btn_min.setStyleSheet(self.btn_style("#00a1d6"))
        self.btn_min.clicked.connect(self.on_min)
        hbox.addWidget(self.btn_min)

        # Maximize/Restore
        self.btn_max = QPushButton("□")
        self.btn_max.setObjectName("title_btn_max")
        self.btn_max.setFixedSize(32, 28)
        self.btn_max.setStyleSheet(self.btn_style("#00a1d6"))
        self.btn_max.clicked.connect(self.on_max)
        hbox.addWidget(self.btn_max)

        # Close
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("title_btn_close")
        self.btn_close.setFixedSize(32, 28)
        self.btn_close.setStyleSheet(self.btn_style("#00a1d6"))  # 统一悬停色
        self.btn_close.clicked.connect(self.on_close)
        hbox.addWidget(self.btn_close)

    def btn_style(self, bg, hover=None):
        hover = hover or "#0090c6"
        return f"""
        QPushButton {{
            background: {bg};
            color: white;
            border: none;
            font-size: 16px;
            min-width: 0px;
            min-height: 0px;
            padding: 0px 5px;
            border-radius: 0px;
        }}
        QPushButton:hover {{
            background: {hover};
        }}
        """

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.moving = True
            self._drag_pos = event.globalPos() - self.parent.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.moving and event.buttons() & Qt.LeftButton:
            self.parent.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.moving = False
        self._drag_pos = None
        event.accept()

    def on_min(self):
        self.parent.showMinimized()

    def on_max(self):
        if self.parent.isMaximized():
            self.parent.showNormal()
        else:
            self.parent.showMaximized()

    def on_close(self):
        self.parent.close()

class BiliDownloader(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setWindowTitle("Bilibili 视频下载器")
        self.setFixedSize(1120, 630)   # 设置窗口大小
        self.signals = DownloadSignals()
        self._wasActive = False
        self.is_dark = False  # 主题状态
        self.is_cn = True     # 语言状态
        self.download_queue = []  # [(title, status), ...]
        self.download_path = os.path.abspath("download")  # <--- 添加这一行
        self.init_ui()
        self.signals.progress.connect(lambda v: self.progress_bar.setValue(int(v)))
        self.signals.finished.connect(self.on_download_finished)
        self.signals.error.connect(self.on_download_error)
        self.executor = ThreadPoolExecutor(max_workers=4)
        # 全局美化
        self.setStyleSheet(self.get_stylesheet())
        self.load_history()  # 加载历史记录
        # 监控剪贴板
        self.last_clipboard = ""
        self.clipboard_timer = QTimer(self)
        self.clipboard_timer.timeout.connect(self.check_clipboard)
        self.clipboard_timer.start(1500)  # 每1.5秒检测一次

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 自定义标题栏
        self.title_bar = TitleBar(self)
        main_layout.addWidget(self.title_bar)

        content = QVBoxLayout()
        content.setContentsMargins(20, 10, 20, 10)
        content.setSpacing(10)

        # 主题、语言、设置按钮并排
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)
        btn_bar.setAlignment(Qt.AlignRight)

        self.theme_btn = QPushButton("切换主题")
        self.theme_btn.setIcon(QIcon("theme.png"))
        self.theme_btn.setIconSize(QSize(18, 18))
        self.theme_btn.clicked.connect(self.toggle_theme)
        btn_bar.addWidget(self.theme_btn)

        self.lang_btn = QPushButton("English")
        self.lang_btn.setIcon(QIcon("lang.png"))
        self.lang_btn.setIconSize(QSize(18, 18))
        self.lang_btn.clicked.connect(self.toggle_lang)
        btn_bar.addWidget(self.lang_btn)

        self.settings_btn = QPushButton("设置" if self.is_cn else "Settings")
        self.settings_btn.setIcon(QIcon("settings.png"))
        self.settings_btn.setIconSize(QSize(18, 18))
        self.settings_btn.clicked.connect(self.show_settings_dialog)
        btn_bar.addWidget(self.settings_btn)

        content.addLayout(btn_bar)

        self.label_bv = QLabel("请输入 Bilibili 视频 BV 号 或 完整 URL：")
        content.addWidget(self.label_bv)

        self.entry_bv = QLineEdit()
        self.entry_bv.setPlaceholderText("BV号或完整链接")
        content.addWidget(self.entry_bv)
        self.entry_bv.textChanged.connect(self.show_video_info)

        self.title_label = QLabel("")
        content.addWidget(self.title_label)

        self.cover_label = QLabel()
        self.cover_label.setFixedHeight(220)  # 固定高度
        self.cover_label.setAlignment(Qt.AlignCenter)
        content.addWidget(self.cover_label, alignment=Qt.AlignCenter)

        # 加一个弹性空间，推开下方按钮
        from PyQt5.QtWidgets import QSpacerItem, QSizePolicy
        content.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))

        # 清晰度选择
        self.quality_box = QComboBox()
        self.quality_box.addItems(["自动(最高)", "仅视频", "仅音频"])
        content.addWidget(self.quality_box)

        # 下载按钮
        self.download_btn = QPushButton("开始下载")
        self.download_btn.setIcon(QIcon("download.png"))
        self.download_btn.setIconSize(QSize(20, 20))
        self.download_btn.clicked.connect(self.on_click_download)
        self.download_btn.pressed.connect(lambda: self.animate_button(self.download_btn, 0.95))
        self.download_btn.released.connect(lambda: self.animate_button(self.download_btn, 1.0))
        content.addWidget(self.download_btn)

        # 下载队列按钮
        self.queue_btn = QPushButton("下载队列" if self.is_cn else "Queue")
        self.queue_btn.setIcon(QIcon("queue.png"))
        self.queue_btn.setIconSize(QSize(20, 20))
        self.queue_btn.clicked.connect(self.show_download_queue)
        content.addWidget(self.queue_btn)  

        # 设置按钮
        self.download_manager_btn = QPushButton("下载管理" if self.is_cn else "Manager")
        self.download_manager_btn.setIcon(QIcon("folder.png"))  # 使用folder.png图标
        self.download_manager_btn.setIconSize(QSize(20, 20))
        self.download_manager_btn.clicked.connect(self.show_download_manager)
        content.addWidget(self.download_manager_btn)
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        content.addWidget(self.progress_bar)

        main_layout.addLayout(content)

    def get_quality_format(self):
        idx = self.quality_box.currentIndex()
        return ['bv*+ba', 'bv*', 'ba'][idx]

    def load_history(self):
        self.history_path = os.path.join(self.download_path, "history.json")
        if os.path.exists(self.history_path):
            try:
                with open(self.history_path, "r", encoding="utf-8") as f:
                    self.download_history = json.load(f)
            except Exception:
                self.download_history = []
        else:
            self.download_history = []

    def save_history(self):
        try:
            with open(self.history_path, "w", encoding="utf-8") as f:
                json.dump(self.download_history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def show_video_info(self):
        bv_input = self.entry_bv.text().strip()
        if len(bv_input) < 2:
            self.title_label.setText("")
            self.cover_label.clear()
            return

        def fetch_info():
            infos = self.get_video_info(bv_input)
            if infos:
                info = infos[0]
                self.title_label.setText(info["title"])
                try:
                    with urlopen(info["thumbnail"]) as u:
                        raw_data = u.read()
                    image = QImage.fromData(raw_data)
                    pixmap = QPixmap.fromImage(image)
                    pixmap = pixmap.scaledToHeight(self.cover_label.height(), Qt.SmoothTransformation)
                    self.cover_label.setPixmap(pixmap)
                except Exception as e:
                    self.cover_label.clear()
                    QMessageBox.warning(self, "提示", f"封面加载失败：{e}")
            else:
                self.title_label.setText("")
                self.cover_label.clear()

        self.executor.submit(fetch_info)

    def get_video_info(self, bv_input):
        # 支持多个BV号或URL（用空格、换行、逗号分隔）
        inputs = re.split(r'[\s,]+', bv_input.strip())
        all_videos = []
        for single_input in inputs:
            if not single_input:
                continue
            if single_input.startswith("https://www.bilibili.com/video/"):
                bv_url = single_input
            elif single_input.startswith("BV"):
                bv_url = f"https://www.bilibili.com/video/{single_input}"
            else:
                continue
            try:
                ydl_opts = {'quiet': True, 'skip_download': True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info_dict = ydl.extract_info(bv_url, download=False)
                    # 如果是多P合集
                    if "entries" in info_dict:
                        for entry in info_dict["entries"]:
                            all_videos.append({
                                "title": entry.get("title", "未知标题"),
                                "thumbnail": entry.get("thumbnail", None),
                                "url": entry.get("webpage_url", bv_url),
                                "uploader": entry.get("uploader", ""),
                                "upload_date": entry.get("upload_date", ""),
                            })
                    else:
                        all_videos.append({
                            "title": info_dict.get("title", "未知标题"),
                            "thumbnail": info_dict.get("thumbnail", None),
                            "url": bv_url,
                            "uploader": info_dict.get("uploader", ""),
                            "upload_date": info_dict.get("upload_date", ""),
                        })
            except Exception:
                continue
        return all_videos

    def on_click_download(self):
        self.executor.submit(self.start_download)

    def start_download(self):
        self._cancel_download = False
        self.signals.progress.emit(0)
        bv_input = self.entry_bv.text().strip()
        if not is_network_available():
            self.signals.error.emit("网络不可用，请检查您的网络连接！")
            return
        infos = self.get_video_info(bv_input)
        if not infos:
            self.signals.error.emit("获取视频信息失败，请检查链接或网络！")
            return
        for info in infos:
            title = info["title"]
            up = info.get("uploader", "UP主")
            date = info.get("upload_date", "")
            # 应用模板
            template = getattr(self, "filename_template", "{title}")
            filename = template.format(title=title, up主=up, date=date)
            safe_title = safe_filename(filename)
            ydl_opts = {
                'format': self.get_quality_format(),
                'outtmpl': os.path.join(self.download_path, f'{safe_title}.%(ext)s'),
                'merge_output_format': 'mp4',
                'noplaylist': True,
                'progress_hooks': [self.update_progress],
                'quiet': True,
            }
            if getattr(self, "proxy_url", ""):
                ydl_opts['proxy'] = self.proxy_url
            self.download_queue.append((title, "下载中" if self.is_cn else "Downloading"))
            retry = 0
            max_retry = 3
            while retry < max_retry:
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([info["url"]])
                    self.signals.progress.emit(100)
                    self.signals.finished.emit()
                    for i, (t, s) in enumerate(self.download_queue):
                        if t == title:
                            self.download_queue[i] = (t, "已完成" if self.is_cn else "Finished")
                    self.download_history.append({
                        "title": title,
                        "url": info["url"],
                        "status": "success",
                    })
                    self.save_history()
                    break  # 成功则退出重试循环
                except Exception as e:
                    retry += 1
                    if retry >= max_retry:
                        for i, (t, s) in enumerate(self.download_queue):
                            if t == title:
                                self.download_queue[i] = (t, "失败" if self.is_cn else "Failed")
                        self.signals.error.emit(f"下载失败: {e}")
                        self.download_history.append({
                            "title": title,
                            "url": info["url"],
                            "status": "failed",
                            "error": str(e)
                        })
                        self.save_history()
    def update_progress(self, d):
        if self._cancel_download:
            raise Exception("用户取消下载")
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            downloaded = d.get('downloaded_bytes', 0)
            speed = d.get('speed', 0)
            eta = d.get('eta', 0)
            if total:
                percentage = downloaded / total * 100
                self.signals.progress.emit(percentage)
                # 显示详细进度
                speed_str = f"{speed/1024:.1f} KB/s" if speed else "--"
                eta_str = f"{int(eta//60)}:{int(eta%60):02d}" if eta else "--"
                self.progress_bar.setFormat(f"{percentage:.1f}%  {speed_str}  剩余:{eta_str}")
        elif d['status'] == 'finished':
            self.signals.progress.emit(100)
            self.progress_bar.setFormat("100%")

    def on_download_finished(self):
        QMessageBox.information(self, "下载完成", "视频下载完成！")

    def on_download_error(self, msg):
        reply = QMessageBox.critical(self, "错误", msg + "\n是否重试？", QMessageBox.Retry | QMessageBox.Cancel)
        if reply == QMessageBox.Retry:
            self.on_click_download()

    # 支持窗口拖动
    # def mousePressEvent(self, event):
    #     if event.button() == Qt.LeftButton:
    #         self.dragPos = event.globalPos() - self.frameGeometry().topLeft()
    #         event.accept()

    # def mouseMoveEvent(self, event):
    #     if event.buttons() == Qt.LeftButton:
    #         self.move(event.globalPos() - self.dragPos)
    #         event.accept()

    def event(self, event):
        # 监听窗口激活事件
        if event.type() == QEvent.WindowActivate:
            if self._wasActive:
                # 如果已经激活，再次激活说明是任务栏点击
                if self.isMinimized():
                    self.showNormal()
                else:
                    self.showMinimized()
                return True
            self._wasActive = True
        elif event.type() == QEvent.WindowDeactivate:
            self._wasActive = False
        return super().event(event)

    def show_history_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("历史记录" if self.is_cn else "Download History")
        dialog.setFixedSize(480, 400)
        layout = QVBoxLayout(dialog)
        list_widget = QListWidget()
        for item in self.download_history:
            status = "成功" if item.get("status") == "success" else "失败"
            text = f"{item['title']}  -  {status}"
            list_item = QListWidgetItem(text)
            list_widget.addItem(list_item)
        layout.addWidget(list_widget)

        # 重新下载按钮
        redownload_btn = QPushButton("重新下载" if self.is_cn else "Redownload")
        layout.addWidget(redownload_btn)

        def redownload():
            row = list_widget.currentRow()
            if row >= 0:
                url = self.download_history[row]["url"]
                self.entry_bv.setText(url)
                self.on_click_download()
                dialog.accept()

        redownload_btn.clicked.connect(redownload)
        dialog.exec_()

    def check_clipboard(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if text and text != self.last_clipboard:
            # 检测B站链接或BV号
            if re.match(r"^(https?://www\.bilibili\.com/video/|BV[0-9A-Za-z]{10,})", text):
                self.last_clipboard = text
                reply = QMessageBox.question(
                    self,
                    "检测到B站链接" if self.is_cn else "Bilibili Link Detected",
                    f"检测到剪贴板有B站链接：\n{text}\n是否一键下载？" if self.is_cn else f"Detected Bilibili link in clipboard:\n{text}\nDownload now?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self.entry_bv.setText(text)
                    self.on_click_download()
            else:
                self.last_clipboard = text

    def show_download_manager(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("下载管理" if self.is_cn else "Download Manager")
        dialog.setFixedSize(520, 600)
        tab_widget = QTabWidget(dialog)

        # 已下载视频 Tab
        downloaded_tab = QWidget()
        downloaded_layout = QVBoxLayout(downloaded_tab)

        # 视频预览窗口
        video_widget = QVideoWidget()
        video_widget.setFixedSize(400, 225)
        downloaded_layout.addWidget(video_widget, alignment=Qt.AlignCenter)

        # 预览进度条
        preview_slider = QSlider(Qt.Horizontal)
        preview_slider.setRange(0, 100)
        preview_slider.setValue(0)
        preview_slider.setStyleSheet("""
            QSlider::groove:horizontal {height: 6px; background: #e3f1fd;}
            QSlider::handle:horizontal {background: #00a1d6; width: 12px; border-radius: 6px;}
            QSlider::sub-page:horizontal {background: #00a1d6;}
        """)
        downloaded_layout.addWidget(preview_slider)

        # 时间标签
        time_label = QLabel("00:00 / 00:00")
        time_label.setAlignment(Qt.AlignCenter)
        time_label.setStyleSheet("color:#666;font-size:13px;")
        downloaded_layout.addWidget(time_label)

        # 播放器
        player = QMediaPlayer(dialog)
        player.setVideoOutput(video_widget)
        player.setMuted(True)  # 预览静音

        def format_time(ms):
            s = int(ms / 1000)
            m, s = divmod(s, 60)
            return f"{m:02d}:{s:02d}"

        def on_position_changed(pos):
            dur = player.duration()
            if dur > 0:
                preview_slider.setValue(int(pos / dur * 100))
                time_label.setText(f"{format_time(pos)} / {format_time(dur)}")
            else:
                preview_slider.setValue(0)
                time_label.setText("00:00 / 00:00")

        def on_duration_changed(dur):
            if dur > 0:
                preview_slider.setEnabled(True)
                time_label.setText(f"{format_time(player.position())} / {format_time(dur)}")
            else:
                preview_slider.setEnabled(False)
                time_label.setText("00:00 / 00:00")

        player.positionChanged.connect(on_position_changed)
        player.durationChanged.connect(on_duration_changed)

        # 搜索框
        search_box = QLineEdit()
        if self.is_cn:
            search_box.setPlaceholderText("搜索已下载视频…")
            open_folder_btn = QPushButton("打开文件夹")
        else:
            search_box.setPlaceholderText("Search downloads…")
            open_folder_btn = QPushButton("Open Folder")
        downloaded_layout.addWidget(search_box)
        # 列表（带缩略图）
        list_widget = QListWidget()
        list_widget.setIconSize(QSize(120, 68))
        files = os.listdir("download")
        video_files = [f for f in files if f.lower().endswith(('.mp4', '.flv', '.mkv', '.avi', '.mov'))]
        self._video_items = []
        for f in video_files:
            item = QListWidgetItem(f)
            thumb_path = os.path.join("download", f + ".jpg")
            video_path = os.path.join("download", f)
            if not os.path.exists(thumb_path):
                try:
                    os.system(f'ffmpeg -y -i "{video_path}" -ss 00:00:01 -vframes 1 "{thumb_path}" >nul 2>nul')
                except Exception as e:
                    QMessageBox.warning(self, "提示", f"缩略图生成失败：{e}")
            if os.path.exists(thumb_path):
                item.setIcon(QIcon(thumb_path))
            else:
                item.setIcon(QIcon("icon.ico"))
            list_widget.addItem(item)
            self._video_items.append((f, item))
        downloaded_layout.addWidget(list_widget)

        def filter_list():
            keyword = search_box.text().strip().lower()
            for name, item in self._video_items:
                item.setHidden(keyword not in name.lower())

        search_box.textChanged.connect(filter_list)
        open_folder_btn.clicked.connect(lambda: os.startfile(os.path.abspath("download")))
        downloaded_layout.addWidget(open_folder_btn)

        # 分类选择
        folders = [f for f in os.listdir("download") if os.path.isdir(os.path.join("download", f))]
        folders.insert(0, "全部" if self.is_cn else "All")
        folder_box = QComboBox()
        folder_box.addItems(folders)
        downloaded_layout.addWidget(folder_box)

        def refresh_video_list():
            list_widget.clear()
            self._video_items.clear()
            selected_folder = folder_box.currentText()
            if selected_folder == ("全部" if self.is_cn else "All"):
                search_dirs = [os.path.join("download", f) for f in os.listdir("download") if os.path.isdir(os.path.join("download", f))]
                search_dirs.append("download")
            else:
                search_dirs = [os.path.join("download", selected_folder)]
            video_files = []
            for d in search_dirs:
                for f in os.listdir(d):
                    if f.lower().endswith(('.mp4', '.flv', '.mkv', '.avi', '.mov')):
                        video_files.append(os.path.join(d, f))
            for path in video_files:
                name = os.path.basename(path)
                item = QListWidgetItem(name)
                thumb_path = path + ".jpg"
                if not os.path.exists(thumb_path):
                    os.system(f'ffmpeg -y -i "{path}" -ss 00:00:01 -vframes 1 "{thumb_path}" >nul 2>nul')
                if os.path.exists(thumb_path):
                    item.setIcon(QIcon(thumb_path))
                else:
                    item.setIcon(QIcon("icon.ico"))
                list_widget.addItem(item)
                self._video_items.append((name, item))
            filter_list()  # 保持搜索过滤

        folder_box.currentIndexChanged.connect(refresh_video_list)

        # 事件过滤器
        class HoverFilter(QObject):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.last_row = -1

            def eventFilter(self, obj, event):
                if event.type() == QEvent.MouseMove:
                    pos = event.pos()
                    item = list_widget.itemAt(pos)
                    if item:
                        row = list_widget.row(item)
                        if row != self.last_row:
                            self.last_row = row
                            path = os.path.abspath(os.path.join("download", item.text()))
                            url = QMediaContent(QUrl.fromLocalFile(path))
                            player.setMedia(url)
                            player.setPosition(0)
                            player.play()
                    else:
                        self.last_row = -1
                        player.stop()
                elif event.type() == QEvent.Leave:
                    self.last_row = -1
                    player.stop()
                return super().eventFilter(obj, event)

        list_widget.setMouseTracking(True)
        hover_filter = HoverFilter(list_widget)
        list_widget.viewport().installEventFilter(hover_filter)

        tab_widget.addTab(downloaded_tab, "已下载视频" if self.is_cn else "Downloaded")

        # 历史记录 Tab
        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)
        history_list = QListWidget()
        for item in self.download_history:
            status = "成功" if item.get("status") == "success" else "失败"
            text = f"{item['title']}  -  {status}"
            list_item = QListWidgetItem(text)
            history_list.addItem(list_item)
        history_layout.addWidget(history_list)

        # 重新下载按钮
        redownload_btn = QPushButton("重新下载" if self.is_cn else "Redownload")
        history_layout.addWidget(redownload_btn)

        def redownload():
            row = history_list.currentRow()
            if row >= 0:
                url = self.download_history[row]["url"]
                self.entry_bv.setText(url)
                self.on_click_download()
                dialog.accept()

        redownload_btn.clicked.connect(redownload)

        tab_widget.addTab(history_tab, "历史记录" if self.is_cn else "History")

        layout = QVBoxLayout(dialog)
        layout.addWidget(tab_widget)

        if self.is_dark:
            dialog.setStyleSheet("background:#23272e; color:#fff;")
        else:
            dialog.setStyleSheet("background:#fff; color:#222;")

        refresh_video_list()
        dialog.exec_()
    def toggle_theme(self):
        self.is_dark = not self.is_dark
        self.setStyleSheet(self.get_stylesheet())
    def closeEvent(self, event):
        self.executor.shutdown(wait=False)
        event.accept()
    def toggle_lang(self):
        self.is_cn = not self.is_cn
        # 顶部按钮
        self.theme_btn.setText("切换主题" if self.is_cn else "Toggle Theme")  # ← 增加这一行
        self.lang_btn.setText("English" if self.is_cn else "中文")
        self.settings_btn.setText("设置" if self.is_cn else "Settings")
        self.download_manager_btn.setText("下载管理" if self.is_cn else "Manager")
        self.setWindowTitle("Bilibili 视频下载器" if self.is_cn else "Bilibili Downloader")
        # 主界面标签
        self.label_bv.setText("请输入 Bilibili 视频 BV 号 或 完整 URL：" if self.is_cn else "Enter Bilibili BV or full URL:")
        self.download_btn.setText("开始下载" if self.is_cn else "Download")
        # 清晰度下拉框
        self.quality_box.clear()
        if self.is_cn:
            self.quality_box.addItems(["自动(最高)", "仅视频", "仅音频"])
        else:
            self.quality_box.addItems(["Auto (Best)", "Video Only", "Audio Only"])
        self.setStyleSheet(self.get_stylesheet())

    def show_settings_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("设置" if self.is_cn else "Settings")
        dialog.setFixedSize(420, 440)
        layout = QVBoxLayout(dialog)

        # 下载路径
        path_label = QLabel("下载路径：" if self.is_cn else "Download Path:")
        path_edit = QLineEdit(self.download_path)
        path_edit.setReadOnly(True)
        path_btn = QPushButton("选择文件夹" if self.is_cn else "Browse")
        def choose_folder():
            from PyQt5.QtWidgets import QFileDialog
            folder = QFileDialog.getExistingDirectory(dialog, "选择下载文件夹" if self.is_cn else "Select Download Folder", self.download_path)
            if folder:
                path_edit.setText(folder)
        path_btn.clicked.connect(choose_folder)
        path_layout = QHBoxLayout()
        path_layout.addWidget(path_edit)
        path_layout.addWidget(path_btn)
        layout.addWidget(path_label)
        layout.addLayout(path_layout)

        # 并发数设置
        thread_label = QLabel("最大并发下载数：" if self.is_cn else "Max Concurrent Downloads:")
        thread_box = QComboBox()
        thread_box.addItems([str(i) for i in range(1, 9)])
        thread_box.setCurrentIndex(getattr(self, "max_workers", 4) - 1)
        layout.addWidget(thread_label)
        layout.addWidget(thread_box)

        # 文件命名模板
        template_label = QLabel("文件命名模板：" if self.is_cn else "Filename Template:")
        template_edit = QLineEdit(getattr(self, "filename_template", "{title}"))
        template_edit.setPlaceholderText("{title}、{up主}、{date} 可用")
        layout.addWidget(template_label)
        layout.addWidget(template_edit)

        # 代理设置
        proxy_label = QLabel("代理（如 http://127.0.0.1:7890 或 socks5://127.0.0.1:1080）" if self.is_cn else "Proxy (e.g. http://127.0.0.1:7890 or socks5://127.0.0.1:1080)")
        proxy_edit = QLineEdit(getattr(self, "proxy_url", ""))
        proxy_edit.setPlaceholderText("留空为不使用代理" if self.is_cn else "Leave blank for no proxy")
        layout.addWidget(proxy_label)
        layout.addWidget(proxy_edit)

        # 主题切换
        theme_btn = QPushButton("切换主题" if self.is_cn else "Toggle Theme")
        theme_btn.clicked.connect(self.toggle_theme)
        layout.addWidget(theme_btn)

        # 语言切换
        lang_btn = QPushButton("切换为English" if self.is_cn else "Switch to 中文")
        def lang_toggle():
            self.toggle_lang()
            dialog.accept()
        lang_btn.clicked.connect(lang_toggle)
        layout.addWidget(lang_btn)

        # 保存按钮
        save_btn = QPushButton("保存" if self.is_cn else "Save")
        def save_settings():
            self.download_path = path_edit.text()
            self.max_workers = int(thread_box.currentText())
            self.executor._max_workers = self.max_workers
            self.filename_template = template_edit.text().strip() or "{title}"
            self.proxy_url = proxy_edit.text().strip()
            dialog.accept()
        save_btn.clicked.connect(save_settings)
        layout.addWidget(save_btn)

        dialog.setLayout(layout)
        dialog.exec_()
    def show_download_queue(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("下载队列" if self.is_cn else "Download Queue")
        dialog.setFixedSize(480, 400)
        layout = QVBoxLayout(dialog)
        list_widget = QListWidget()
        for title, status in self.download_queue:
            text = f"{title}  -  {status}"
            list_item = QListWidgetItem(text)
            list_widget.addItem(list_item)
        layout.addWidget(list_widget)

        # 取消任务按钮
        cancel_btn = QPushButton("取消任务" if self.is_cn else "Cancel Task")
        layout.addWidget(cancel_btn)

        def cancel_task():
            row = list_widget.currentRow()
            if row >= 0:
                # 简单实现：直接标记为取消，下次进度回调时中断
                self._cancel_download = True
                self.download_queue[row] = (self.download_queue[row][0], "已取消" if self.is_cn else "Canceled")
                list_widget.item(row).setText(f"{self.download_queue[row][0]}  -  {'已取消' if self.is_cn else 'Canceled'}")

        cancel_btn.clicked.connect(cancel_task)
        dialog.exec_()
    def animate_button(self, btn, scale):
        anim = QPropertyAnimation(btn, b"geometry")
        rect = btn.geometry()
        w, h = rect.width(), rect.height()
        center = rect.center()
        new_w, new_h = int(w * scale), int(h * scale)
        new_rect = QRect(center.x() - new_w // 2, center.y() - new_h // 2, new_w, new_h)
        anim.setDuration(100)
        anim.setStartValue(rect)
        anim.setEndValue(new_rect)
        anim.start(QPropertyAnimation.DeleteWhenStopped)

    def get_stylesheet(self):
        if self.is_dark:
            return """
            QWidget {
                font-family: 'ZCOOL KuaiLe', 'Microsoft YaHei', '微软雅黑', Arial, sans-serif;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #23272e, stop:1 #2d3540);
                color: #fff;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3a8dde, stop:1 #7f53ac);
                color: #fff;
                border: 2px solid #00a1d6;
                border-radius: 16px;
                padding: 10px 28px;
                font-size: 18px;
                font-family: 'ZCOOL KuaiLe', 'Microsoft YaHei', '微软雅黑', Arial, sans-serif;
                font-weight: bold;
                letter-spacing: 2px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00a1d6, stop:1 #7f53ac);
                color: #fff;
                border: 2px solid #3a8dde;
            }
            QLineEdit, QComboBox {
                background: #23272e;
                border: 2px solid #00a1d6;
                border-radius: 10px;
                padding: 8px 12px;
                font-size: 16px;
                color: #fff;
            }
            QComboBox QAbstractItemView {
                background: #23272e;
                selection-background-color: #3a8dde;
                color: #fff;
            }
            QProgressBar {
                background: #2d3540;
                height: 18px;
                border-radius: 9px;
            }
            QProgressBar::chunk {
                background: #00a1d6;
                border-radius: 9px;
            }
            QListWidget {
                background: #23272e;
                border: 2px solid #00a1d6;
                border-radius: 10px;
                color: #fff;
            }
            QDialog {
                background: #23272e;
                color: #fff;
            }
            QLabel {
                color: #fff;
            }
            """
        else:
            return """
            QWidget {
                font-family: 'ZCOOL KuaiLe', 'Microsoft YaHei', '微软雅黑', Arial, sans-serif;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f6f7f9, stop:1 #e3f1fd);
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ffb6e6, stop:1 #aeefff);
                color: #fff;
                border: 2px solid #fb7299;
                border-radius: 16px;
                padding: 10px 28px;
                font-size: 18px;
                font-family: 'ZCOOL KuaiLe', 'Microsoft YaHei', '微软雅黑', Arial, sans-serif;
                font-weight: bold;
                letter-spacing: 2px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #fb7299, stop:1 #aeefff);
                color: #fff;
                border: 2px solid #ffb6e6;
            }
            QLineEdit, QComboBox {
                background: #fff;
                border: 2px solid #fb7299;
                border-radius: 10px;
                padding: 8px 12px;
                font-size: 16px;
            }
            QComboBox QAbstractItemView {
                background: #fff;
                selection-background-color: #ffb6e6;
            }
            QProgressBar {
                background: #ffe6f6;
                height: 18px;
                border-radius: 9px;
            }
            QProgressBar::chunk {
                background: #fb7299;
                border-radius: 9px;
            }
            QListWidget {
                background: #fff;
                border: 2px solid #fb7299;
                border-radius: 10px;
            }
            QDialog {
                background: #fff;
            }
            """

def enable_blur(hwnd):
    # Windows 10/11 毛玻璃效果
    accent_policy = ctypes.c_int * 4
    class ACCENTPOLICY(ctypes.Structure):
        _fields_ = [("AccentState", ctypes.c_int),
                    ("AccentFlags", ctypes.c_int),
                    ("GradientColor", ctypes.c_int),
                    ("AnimationId", ctypes.c_int)]
    class WINCOMPATTRDATA(ctypes.Structure):
        _fields_ = [("Attribute", ctypes.c_int),
                    ("Data", ctypes.POINTER(ACCENTPOLICY)),
                    ("SizeOfData", ctypes.c_size_t)]
    accent = ACCENTPOLICY()
    accent.AccentState = 3  # ACCENT_ENABLE_BLURBEHIND
    accent.AccentFlags = 2
    accent.GradientColor = 0x99FFFFFF  # 透明度+白色
    accent.AnimationId = 0
    data = WINCOMPATTRDATA()
    data.Attribute = 19
    data.Data = ctypes.cast(ctypes.pointer(accent), ctypes.POINTER(ACCENTPOLICY))
    data.SizeOfData = ctypes.sizeof(accent)
    hwnd = int(hwnd)
    ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))

def is_network_available():
    try:
        socket.create_connection(("www.bilibili.com", 80), timeout=3)
        return True
    except OSError:
        return False

if __name__ == "__main__":
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("bili.downloader.qt")  # 任务栏图标
    app = QApplication(sys.argv)
    window = BiliDownloader()
    window.setWindowIcon(QIcon("icon.ico"))  # 设置任务栏图标
    window.show()
    sys.exit(app.exec_())
