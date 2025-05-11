import sys
import os
import re
import threading
import yt_dlp
from urllib.request import urlopen
import time
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout,
    QHBoxLayout, QComboBox, QProgressBar, QMessageBox, QFrame, QListWidget, QListWidgetItem, QDialog, QSlider,
    QSizePolicy, QTabWidget, QGridLayout  # 添加 QTabWidget 和 QGridLayout
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
import requests
from bs4 import BeautifulSoup

# 在文件顶部添加
try:
    from mpv import MPV
    from PyQt5.QtWidgets import QOpenGLWidget
    MPV_AVAILABLE = True
except ImportError:
    MPV_AVAILABLE = False

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
        # 添加自定义顶部栏
        self.title_bar = TitleBar(self)
        main_layout.addWidget(self.title_bar)
        
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # 动漫资源站Tab
        self.anime_zone_widget = QWidget()
        self.init_anime_zone_ui(self.anime_zone_widget)
        self.tab_widget.addTab(self.anime_zone_widget, "动漫资源站")

        # B站下载器Tab
        self.downloader_widget = QWidget()
        self.init_downloader_ui(self.downloader_widget)
        self.tab_widget.addTab(self.downloader_widget, "B站下载器")

    def init_anime_zone_ui(self, parent):
        from PyQt5.QtWidgets import QGridLayout, QToolButton, QScrollArea, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QDialog, QListWidget, QSizePolicy, QComboBox, QSpacerItem
        from PyQt5.QtCore import Qt, QSize, QTimer
        from PyQt5.QtGui import QMovie

        layout = QVBoxLayout(parent)
        search_box = QLineEdit()
        search_box.setPlaceholderText("输入动漫名称搜索…")
        layout.addWidget(search_box)

        # 改为标题
        title_label = QLabel("动漫资源")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size:22px;font-weight:bold;color:#00a1d6;margin:12px;")
        layout.addWidget(title_label)

        # 分页控件
        page_bar = QHBoxLayout()
        prev_btn = QPushButton("上一页")
        next_btn = QPushButton("下一页")
        page_info = QLabel("")  # 初始不显示
        page_bar.addWidget(prev_btn)
        page_bar.addWidget(page_info)
        page_bar.addWidget(next_btn)
        layout.addLayout(page_bar)

        # 滚动区+网格
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        grid_container = QWidget()
        grid = QGridLayout(grid_container)
        grid.setSpacing(18)

        for i in range(5):  # 假设每行5个
            grid.setColumnStretch(i, 1)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        grid_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        scroll.setWidget(grid_container)
        layout.addWidget(scroll, stretch=1)

        # 加载动画
        loading_label = QLabel()
        loading_label.setAlignment(Qt.AlignCenter)
        loading_movie = QMovie("loading.gif")  # 你需要准备一个 loading.gif 动画文件
        loading_label.setMovie(loading_movie)
        loading_label.setVisible(False)
        layout.addWidget(loading_label, alignment=Qt.AlignCenter)

        self._db_anime_data = []
        self._db_page = 1
        self._db_page_size = 20
        self._db_search_keyword = ""

        def truncate_name(name, maxlen=10):
            return name if len(name) <= maxlen else name[:maxlen] + "..."

        def show_loading(show=True):
            scroll.setVisible(not show)
            loading_label.setVisible(show)
            if show:
                loading_movie.start()
            else:
                loading_movie.stop()
        def load_db_anime_list(page=1, keyword=None):
            show_loading(True)
            if keyword is not None:
                self._db_search_keyword = keyword.strip()
            keyword = self._db_search_keyword
            def do_load():
                import sqlite3
                conn = sqlite3.connect("anime.db")
                c = conn.cursor()
                if keyword:
                    c.execute("SELECT COUNT(*) FROM anime WHERE name LIKE ?", (f"%{keyword}%",))
                else:
                    c.execute("SELECT COUNT(*) FROM anime")
                total = c.fetchone()[0]
                total_page = max(1, (total + self._db_page_size - 1) // self._db_page_size)
                page2 = max(1, min(page, total_page))
                self._db_page = page2
                self._db_total_page = total_page
                offset = (page2 - 1) * self._db_page_size
                if keyword:
                    c.execute("SELECT id, name, cover FROM anime WHERE name LIKE ? ORDER BY id DESC LIMIT ? OFFSET ?", (f"%{keyword}%", self._db_page_size, offset))
                else:
                    c.execute("SELECT id, name, cover FROM anime ORDER BY id DESC LIMIT ? OFFSET ?", (self._db_page_size, offset))
                self._db_anime_data = c.fetchall()
                conn.close()

                def update_ui():
                    # 清空网格
                    for i in reversed(range(grid.count())):
                        w = grid.itemAt(i).widget()
                        if w:
                            w.setParent(None)
                    # 填充网格
                    for idx, (anime_id, name, cover_url) in enumerate(self._db_anime_data):
                        btn = QToolButton()
                        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                        btn.setMinimumSize(120, 150)  # 最小尺寸
                        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                        # btn.setIconSize(QSize(180, 120))  # 图标也可适当变大
                        btn.setText(truncate_name(name, 10))
                        btn.setToolTip(name)
                        btn.setStyleSheet("""
                            QToolButton {
                                border: none;
                                padding: 6px;
                                font-size: 16px;
                                qproperty-iconSize: 120px 90px;
                            }
                            QToolButton::menu-indicator { image: none; }
                        """)
                        # 加载图片
                        if cover_url:
                            try:
                                img_data = urlopen(cover_url).read()
                                pixmap = QPixmap()
                                pixmap.loadFromData(img_data)
                                btn._raw_pixmap = pixmap  # 保存原图
                            except Exception:
                                btn._raw_pixmap = QPixmap("icon.ico")
                        else:
                            btn._raw_pixmap = QPixmap("icon.ico")

                        # 动态调整图片和字体
                        def resizeEvent(event, btn=btn):
                            w, h = btn.width(), btn.height()
                            # 让图片最大贴合按钮上半部分，留10%边距
                            icon_w = int(w * 0.85)
                            icon_h = int(h * 0.55)
                            if hasattr(btn, "_raw_pixmap"):
                                btn.setIcon(QIcon(btn._raw_pixmap.scaled(icon_w, icon_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                                btn.setIconSize(QSize(icon_w, icon_h))
                            # 字体大小随高度变化
                            font = btn.font()
                            font.setPointSize(max(10, int(h * 0.11)))
                            btn.setFont(font)
                            QToolButton.resizeEvent(btn, event)
                        btn.resizeEvent = resizeEvent

                        btn.clicked.connect(lambda _, idx=idx: self.show_anime_detail(idx))
                        grid.addWidget(btn, idx // 5, idx % 5)
                    # 页码只在加载完后显示
                    page_info.setText(f"第 {self._db_page} / {self._db_total_page} 页")
                    show_loading(False)

                QTimer.singleShot(100, update_ui)  # 让动画至少显示一帧

            QTimer.singleShot(100, do_load)  # 模拟异步加载
        def on_search():
            load_db_anime_list(1, search_box.text())

        search_box.returnPressed.connect(on_search)
        search_box.textChanged.connect(lambda: load_db_anime_list(1, search_box.text()) if not search_box.text().strip() else None)

        def prev_page():
            if self._db_page > 1:
                load_db_anime_list(self._db_page - 1)
        def next_page():
            if hasattr(self, "_db_total_page") and self._db_page < self._db_total_page:
                load_db_anime_list(self._db_page + 1)
        prev_btn.clicked.connect(prev_page)
        next_btn.clicked.connect(next_page)

        # 启动时自动加载第一页
        load_db_anime_list(1)

    def show_anime_detail(self,idx):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QScrollArea, QPushButton, QLabel, QWidget, QComboBox, QSizePolicy
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QPixmap, QIcon
        anime_id, name, cover_url = self._db_anime_data[idx]
        import sqlite3
        conn = sqlite3.connect("anime.db")
        c = conn.cursor()
        c.execute("SELECT intro, year, area, type, total_eps FROM anime WHERE id=?", (anime_id,))
        row = c.fetchone()
        intro, year, area, type_str, total_eps = row if row else ("", "", "", "", "")
        c.execute("SELECT DISTINCT line_id FROM episode WHERE anime_id=? ORDER BY line_id", (anime_id,))
        lines = [r[0] for r in c.fetchall()]
        line_names = []
        for lid in lines:
        # 新增：自动编号显示为“线路1”“线路2”...
            if str(lid).startswith("ul_playlist_"):
                try:
                    num = int(str(lid).replace("ul_playlist_", ""))
                    line_names.append(f"线路{num}")
                except Exception:
                    line_names.append(str(lid))
            else:
                line_names.append(str(lid))
        current_line = lines[0] if lines else None
        c.execute("SELECT title, play_url, real_video_url FROM episode WHERE anime_id=? AND line_id=? ORDER BY id", (anime_id, current_line))
        eps = c.fetchall()
        conn.close()

        dialog = QDialog(self)
        dialog.setWindowTitle(name)
        dialog.setMinimumSize(1000, 800)
        dialog.setWindowFlags(Qt.Window | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        main_layout = QVBoxLayout(dialog)

        # 1. 播放器区
        if MPV_AVAILABLE:
            class MpvWidget(QOpenGLWidget):
                clicked = pyqtSignal()
                def __init__(self, parent=None):
                    super().__init__(parent)
                    # 先初始化所有回调属性，防止mpv事件早于这些属性定义
                    self.on_time_update = None
                    self.on_duration_update = None
                    self.on_pause_update = None
                    self.on_volume_update = None

                    self.setMinimumSize(800, 450)
                    self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                    self.mpv = MPV(wid=str(int(self.winId())), log_handler=None, input_default_bindings=True, input_vo_keyboard=True)
                    self.duration = 0
                    self._slider_updating = False
                    self.mpv.observe_property('duration', self._on_duration)
                    self.mpv.observe_property('time-pos', self._on_timepos)
                    self.mpv.observe_property('pause', self._on_pause)
                    self.mpv.observe_property('volume', self._on_volume)
                    self.on_time_update = None
                    self.on_duration_update = None
                    self.on_pause_update = None
                    self.on_volume_update = None

                def play(self, url):
                    self.mpv.play(url)

                def set_position(self, sec):
                    self.mpv.seek(sec, reference='absolute')

                def set_pause(self, pause):
                    self.mpv.pause = pause

                def set_volume(self, vol):
                    self.mpv.volume = vol

                def _on_duration(self, name, value):
                    self.duration = value or 0
                    if self.on_duration_update:
                        self.on_duration_update(self.duration)

                def _on_timepos(self, name, value):
                    if self.on_time_update:
                        self.on_time_update(value or 0)

                def _on_pause(self, name, value):
                    if self.on_pause_update:
                        self.on_pause_update(value)

                def _on_volume(self, name, value):
                    if self.on_volume_update:
                        self.on_volume_update(value)

                def mousePressEvent(self, event):
                    if event.button() == Qt.LeftButton:
                        self.clicked.emit()
                    super().mousePressEvent(event)
                # 监听全屏窗口关闭，自动恢复弹窗
                def video_close_event(event):
                    if is_fullscreen[0]:
                        toggle_fullscreen()
                    event.accept()
                    video_widget.closeEvent = video_close_event
                pass
            video_widget = MpvWidget(dialog)
        else:
            video_widget = QLabel("未安装 python-mpv，无法播放流媒体")
            video_widget.setMinimumSize(480, 270)
        video_widget.setMinimumHeight(420)
        video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout.addWidget(video_widget, stretch=3)
        # 在 video_widget 上覆盖一个 QLabel 作为加载提示
        loading_label = QLabel("加载中...", video_widget)
        loading_label.setStyleSheet("""
            QLabel {
                background: rgba(0,0,0,160);
                color: #fff;
                font-size: 32px;
                border-radius: 16px;
            }
        """)
        loading_label.setAlignment(Qt.AlignCenter)
        loading_label.setGeometry(0, 0, video_widget.width(), video_widget.height())
        loading_label.hide()

        # 保证遮罩随播放器大小变化
        def resize_loading_label(event):
            loading_label.setGeometry(0, 0, video_widget.width(), video_widget.height())
            QOpenGLWidget.resizeEvent(video_widget, event)
        video_widget.resizeEvent = resize_loading_label
        def hide_loading_on_play(pos):
            # 只要有播放进度就说明开始播放了
            if pos and loading_label.isVisible():
                loading_label.hide()
        video_widget.on_time_update = hide_loading_on_play
        # 进度条
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 1000)
        slider.setValue(0)
        slider.setEnabled(False)
        main_layout.addWidget(slider)

        # 时间标签
        time_label = QLabel("00:00 / 00:00")
        main_layout.addWidget(time_label)

        # 控制区
        ctrl_layout = QHBoxLayout()
        play_btn = QPushButton("暂停" if MPV_AVAILABLE else "无")
        min_btn = QPushButton("最小化")
        vol_slider = QSlider(Qt.Horizontal)
        vol_slider.setRange(0, 100)
        vol_slider.setValue(80)
        vol_slider.setFixedWidth(100)
        vol_label = QLabel("音量")
        max_btn = QPushButton("窗口最大化")
        fullscreen_btn = QPushButton("全屏")
        ctrl_layout.addWidget(play_btn)
        ctrl_layout.addWidget(min_btn)
        ctrl_layout.addWidget(vol_label)
        ctrl_layout.addWidget(vol_slider)
        ctrl_layout.addWidget(max_btn)
        ctrl_layout.addWidget(fullscreen_btn)
        main_layout.addLayout(ctrl_layout)

        min_btn.clicked.connect(dialog.showMinimized)

        # 2. 分集按钮区
        ep_scroll = QScrollArea()
        ep_scroll.setWidgetResizable(True)
        ep_scroll.setFixedHeight(60)
        ep_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        ep_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        ep_btn_container = QWidget()
        ep_btn_layout = QHBoxLayout(ep_btn_container)
        ep_btn_layout.setContentsMargins(8, 0, 8, 0)
        ep_btn_layout.setSpacing(12)
        ep_btns = []
        for i, (ep_title, play_url, real_url) in enumerate(eps):
            btn = QPushButton(ep_title)
            btn.setCheckable(True)
            btn.setMinimumWidth(60)
            btn.setStyleSheet("""
                QPushButton {
                    background: #f6f7f9;
                    border: 2px solid #00a1d6;
                    border-radius: 8px;
                    padding: 8px 18px;
                    color: #222;
                    font-size: 18px;
                }
                QPushButton:checked {
                    background: #00a1d6;
                    color: #fff;
                    border: 2px solid #fb7299;
                }
            """)
            ep_btn_layout.addWidget(btn)
            ep_btns.append(btn)
        ep_btn_layout.addStretch(1)
        ep_btn_container.setLayout(ep_btn_layout)
        ep_scroll.setWidget(ep_btn_container)
        main_layout.addWidget(ep_scroll, stretch=0)

        # 默认播放最老一集
        cur_ep_idx = len(eps) - 1 if eps else 0
        if eps and MPV_AVAILABLE:
            video_widget.play(eps[cur_ep_idx][2])
            ep_btns[cur_ep_idx].setChecked(True)
        def on_ep_btn_clicked(idx):
            for i, b in enumerate(ep_btns):
                b.setChecked(i == idx)
            if MPV_AVAILABLE:
                loading_label.show()
                video_widget.play(eps[idx][2])
        for idx, btn in enumerate(ep_btns):
            btn.clicked.connect(lambda _, idx=idx: on_ep_btn_clicked(idx))
        # 3. 信息区
        info_layout = QHBoxLayout()
        # 封面
        cover_label = QLabel()
        cover_label.setFixedSize(220, 160)
        if cover_url:
            try:
                img_data = urlopen(cover_url).read()
                pixmap = QPixmap()
                pixmap.loadFromData(img_data)
                pixmap = pixmap.scaled(220, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                cover_label.setPixmap(pixmap)
            except Exception:
                pass
        info_layout.addWidget(cover_label)

        # 信息右侧
        info_right = QVBoxLayout()
        name_label = QLabel(f"<b>{name}</b>")
        name_label.setStyleSheet("font-size: 22px;")
        info_right.addWidget(name_label)

        # 简介区（可滚动但不显示滚动条）
        intro_scroll = QScrollArea()
        intro_scroll.setWidgetResizable(True)
        intro_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        intro_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        intro_widget = QLabel(f"简介：{intro}")
        intro_widget.setWordWrap(True)
        intro_widget.setStyleSheet("font-size: 18px;")
        intro_scroll.setWidget(intro_widget)
        intro_scroll.setFixedHeight(80)
        intro_scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical, QScrollBar:horizontal { width:0px; height:0px; }
        """)
        info_right.addWidget(intro_scroll)

        # 其他信息
        info_right.addWidget(QLabel(f"<span style='font-size:16px;'>年份：{year}</span>"))
        info_right.addWidget(QLabel(f"<span style='font-size:16px;'>地区：{area}</span>"))
        info_right.addWidget(QLabel(f"<span style='font-size:16px;'>类型：{type_str}</span>"))
        info_right.addWidget(QLabel(f"<span style='font-size:16px;'>总集数：{total_eps}</span>"))
        line_box = QComboBox()
        line_box.addItems(line_names)
        line_box.setStyleSheet("font-size:16px;")
        info_right.addWidget(QLabel("<span style='font-size:16px;'>线路切换</span>"))
        info_right.addWidget(line_box)
        info_right.addStretch()
        info_layout.addLayout(info_right)


        # 用QWidget包裹信息区，方便隐藏/显示
        info_widget = QWidget()
        info_widget.setLayout(info_layout)
        main_layout.addWidget(info_widget, stretch=1)
        # 事件绑定
        if MPV_AVAILABLE:
            is_player_maximized = [False]  # 用列表包裹以便闭包修改

            def toggle_fullscreen():
                if not is_fullscreen[0]:
                    dialog.showMaximized()
                    info_widget.setVisible(False)
                    is_fullscreen[0] = True
                else:
                    dialog.showNormal()
                    info_widget.setVisible(True)
                    is_fullscreen[0] = False

            fullscreen_btn.clicked.connect(toggle_fullscreen)

            def keyPressEvent(event):
                if is_fullscreen[0] and event.key() == Qt.Key_Escape:
                    toggle_fullscreen()
                else:
                    super(type(video_widget), video_widget).keyPressEvent(event)
            video_widget.keyPressEvent = keyPressEvent

            video_widget.setFocusPolicy(Qt.StrongFocus)

            # 播放/暂停
            def toggle_pause():
                video_widget.set_pause(not video_widget.mpv.pause)
            def update_pause_btn(paused):
                play_btn.setText("播放" if paused else "暂停")
            play_btn.clicked.connect(toggle_pause)
            video_widget.on_pause_update = update_pause_btn

            # 点击播放器区域也可暂停/播放
            video_widget.clicked.connect(toggle_pause)

            # 音量
            def set_volume(val):
                video_widget.set_volume(val)
            vol_slider.valueChanged.connect(set_volume)

            # 进度条
            def update_slider(pos):
                if not slider.isSliderDown() and video_widget.duration:
                    slider.setValue(int((pos / video_widget.duration) * 1000))
                # 更新时间标签
                cur = int(pos or 0)
                dur = int(video_widget.duration or 0)
                time_label.setText(f"{cur//60:02d}:{cur%60:02d} / {dur//60:02d}:{dur%60:02d}")
            video_widget.on_time_update = update_slider

            def update_duration(dur):
                if dur:
                    slider.setEnabled(True)
            video_widget.on_duration_update = update_duration

            def slider_released():
                if video_widget.duration:
                    sec = slider.value() / 1000 * video_widget.duration
                    video_widget.set_position(sec)
            slider.sliderReleased.connect(slider_released)

            # 线路切换
            def change_line(idx):
                    lid = lines[idx]
                    import sqlite3
                    conn = sqlite3.connect("anime.db")
                    c = conn.cursor()
                    c.execute("SELECT title, play_url, real_video_url FROM episode WHERE anime_id=? AND line_id=? ORDER BY id", (anime_id, lid))
                    eps2 = c.fetchall()
                    conn.close()
                    # 清空原有按钮
                    for btn in ep_btns:
                        btn.setParent(None)
                    ep_btns.clear()
                    # 重新生成按钮
                    for i, (ep_title, play_url, real_url) in enumerate(eps2):
                        btn = QPushButton(ep_title)
                        btn.setCheckable(True)
                        btn.setMinimumWidth(60)
                        btn.setStyleSheet("""
                            QPushButton {
                                background: #f6f7f9;
                                border: 2px solid #00a1d6;
                                border-radius: 8px;
                                padding: 8px 18px;
                                color: #222;
                                font-size: 18px;
                            }
                            QPushButton:checked {
                                background: #00a1d6;
                                color: #fff;
                                border: 2px solid #fb7299;
                            }
                        """)
                        ep_btn_layout.insertWidget(ep_btn_layout.count() - 1, btn)
                        ep_btns.append(btn)
                        btn.clicked.connect(lambda _, idx=i: on_ep_btn_clicked(idx))
                    # 默认播放最老一集
                    if eps2:
                        video_widget.play(eps2[-1][2])
                        ep_btns[-1].setChecked(True)
            line_box.currentIndexChanged.connect(change_line)

            # 初始化音量
            video_widget.set_volume(vol_slider.value())

            # 关闭弹窗时销毁mpv，防止主程序卡死
            def on_close(_):
                try:
                    video_widget.mpv.terminate()
                except Exception:
                    pass
            dialog.finished.connect(on_close)

            is_fullscreen = [False]

            def toggle_fullscreen():
                if not is_fullscreen[0]:
                    # 伪全屏：最大化弹窗，隐藏右侧信息区
                    dialog.showMaximized()
                    for i in reversed(range(main_layout.count())):
                        item = main_layout.itemAt(i)
                        if item is not None and item.layout() == right:
                            main_layout.takeAt(i)
                    main_layout.setStretch(0, 1)
                    # 控制条悬浮美化
                    ctrl_widget = QWidget()
                    ctrl_widget.setLayout(ctrl_layout)
                    ctrl_widget.setStyleSheet("""
                        QWidget {
                            background: rgba(30,30,30,160);
                            border-radius: 16px;
                        }
                        QPushButton {
                            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00a1d6, stop:1 #7f53ac);
                            color: #fff;
                            border: none;
                            border-radius: 12px;
                            padding: 6px 18px;
                            font-size: 16px;
                        }
                        QPushButton:hover {
                            background: #fb7299;
                        }
                        QSlider::groove:horizontal {
                            height: 8px;
                            border-radius: 4px;
                            background: #444;
                        }
                        QSlider::handle:horizontal {
                            background: #00a1d6;
                            border-radius: 8px;
                            width: 18px;
                            margin: -5px 0;
                        }
                        QSlider::sub-page:horizontal {
                            background: #00a1d6;
                            border-radius: 4px;
                        }
                    """)
                    # 用widget包裹后替换原来的ctrl_layout
                    left.removeItem(ctrl_layout)
                    left.addWidget(ctrl_widget)
                    is_fullscreen.append(ctrl_widget)
                    is_fullscreen[0] = True
                else:
                    # 恢复
                    dialog.showNormal()
                    main_layout.setStretch(0, 2)
                    main_layout.setStretch(1, 1)
                    # 恢复控制条
                    if len(is_fullscreen) > 1:
                        ctrl_widget = is_fullscreen.pop()
                        left.removeWidget(ctrl_widget)
                        ctrl_widget.setParent(None)
                        left.addLayout(ctrl_layout)
                    is_fullscreen[0] = False

            fullscreen_btn.clicked.connect(toggle_fullscreen)

        dialog.exec_()

    def init_downloader_ui(self, widget):
        layout = QVBoxLayout(widget)
        label = QLabel("欢迎来到B站下载器！")
        layout.addWidget(label)

        content = QVBoxLayout()
        content.setContentsMargins(20, 10, 20, 10)
        content.setSpacing(10)

        # 主题、语言、设置按钮并排
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)
        btn_bar.setAlignment(Qt.AlignRight)

        self.player_btn = QPushButton("播放器" if self.is_cn else "Player")
        self.player_btn.setIcon(QIcon("play.png"))
        self.player_btn.setIconSize(QSize(20, 20))
        self.player_btn.clicked.connect(self.show_player)
        btn_bar.addWidget(self.player_btn)

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

        layout.addLayout(content)

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
    def show_player(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("本地播放器" if self.is_cn else "Local Player")
        dialog.setFixedSize(800, 800)
        layout = QVBoxLayout(dialog)

        # 视频列表
        list_widget = QListWidget()
        video_files = [f for f in os.listdir(self.download_path) if f.lower().endswith(('.mp4', '.flv', '.mkv', '.avi', '.mov'))]
        for f in video_files:
            list_widget.addItem(f)
        layout.addWidget(list_widget)

        # 播放区
        video_widget = QVideoWidget()
        layout.addWidget(video_widget, stretch=1)

        # 控制区
        control_layout = QHBoxLayout()
        play_btn = QPushButton("播放" if self.is_cn else "Play")
        pause_btn = QPushButton("暂停" if self.is_cn else "Pause")
        stop_btn = QPushButton("停止" if self.is_cn else "Stop")
        control_layout.addWidget(play_btn)
        control_layout.addWidget(pause_btn)
        control_layout.addWidget(stop_btn)
        layout.addLayout(control_layout)

        # 播放器
        player = QMediaPlayer(dialog)
        player.setVideoOutput(video_widget)

        def play_selected():
            row = list_widget.currentRow()
            if row >= 0:
                path = os.path.join(self.download_path, list_widget.item(row).text())
                player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
                player.play()
        play_btn.clicked.connect(play_selected)
        list_widget.itemDoubleClicked.connect(play_selected)
        pause_btn.clicked.connect(player.pause)
        stop_btn.clicked.connect(player.stop)

        dialog.setLayout(layout)
        dialog.exec_()
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
        if (event.type() == QEvent.WindowActivate):
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

    def show_theme_market(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("主题市场" if self.is_cn else "Theme Market")
        dialog.setFixedSize(600, 500)
        layout = QVBoxLayout(dialog)

        # 主题列表
        theme_list = QListWidget()
        layout.addWidget(theme_list)

        # 主题数据（可扩展为从服务器获取）
        themes = [
            {
                "name": "默认主题",
                "author": "系统",
                "downloads": 1000,
                "is_dark": False,
                "stylesheet": self.get_stylesheet()  # 使用当前默认样式
            },
            {
                "name": "暗黑主题",
                "author": "用户A",
                "downloads": 500,
                "is_dark": True,
                "stylesheet": """
                QWidget { background: #23272e; color: #fff; }
                QPushButton { background: #3a8dde; color: #fff; border-radius: 8px; }
                QPushButton:hover { background: #00a1d6; }
                QLineEdit, QComboBox { background: #23272e; color: #fff; border: 1px solid #00a1d6; }
                """
            },
            {
                "name": "粉色主题",
                "author": "用户B",
                "downloads": 300,
                "is_dark": False,
                "stylesheet": """
                QWidget { background: #fff0f6; color: #fb7299; }
                QPushButton { background: #fb7299; color: #fff; border-radius: 8px; }
                QPushButton:hover { background: #ffb6e6; }
                QLineEdit, QComboBox { background: #fff; color: #fb7299; border: 1px solid #fb7299; }
                """
            }
        ]
        theme_list.clear()
        for theme in themes:
            item = QListWidgetItem(f"{theme['name']} - 作者: {theme['author']} (下载: {theme['downloads']})")
            theme_list.addItem(item)

        # 实时预览
        def preview_theme():
            row = theme_list.currentRow()
            if row >= 0:
                theme = themes[row]
                self.setStyleSheet(theme.get("stylesheet", ""))

        theme_list.currentRowChanged.connect(preview_theme)

        # 下载按钮（应用主题）
        download_btn = QPushButton("应用主题" if self.is_cn else "Apply Theme")
        def apply_theme():
            row = theme_list.currentRow()
            if row >= 0:
                theme = themes[row]
                self.is_dark = theme.get("is_dark", False)
                self.setStyleSheet(theme.get("stylesheet", ""))
                QMessageBox.information(self, "提示", f"主题 {theme['name']} 已应用！")
                dialog.accept()
        download_btn.clicked.connect(apply_theme)
        layout.addWidget(download_btn)

        # 上传按钮
        upload_btn = QPushButton("上传主题" if self.is_cn else "Upload Theme")
        upload_btn.clicked.connect(self.upload_theme)
        layout.addWidget(upload_btn)

        dialog.setLayout(layout)
        dialog.exec_()
        
    def download_theme(self, theme_name):
        try:
            # 这里应该是下载主题的代码
            QMessageBox.information(self, "提示", f"主题 {theme_name} 下载成功！")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"下载主题失败: {e}")
        
    def upload_theme(self):
        from PyQt5.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(self, "选择主题文件", "", "主题文件 (*.theme)")
        if file_path:
            try:
                # 这里应该是上传主题的代码
                QMessageBox.information(self, "提示", "主题上传成功！")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"上传主题失败: {e}")
                
    def import_theme(self):
        from PyQt5.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(self, "选择主题文件", "", "主题文件 (*.theme)")
        if file_path:
            try:
                # 这里应该是导入主题的代码
                QMessageBox.information(self, "提示", "主题导入成功！")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"导入主题失败: {e}")
                
    def export_theme(self):
        from PyQt5.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getSaveFileName(self, "保存主题文件", "", "主题文件 (*.theme)")
        if file_path:
            try:
                # 这里应该是导出主题的代码
                QMessageBox.information(self, "提示", "主题导出成功！")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"导出主题失败: {e}")
                
    def apply_custom_color(self, color):
        self.setStyleSheet(f"""
            QWidget {{
                background: #f5f5f5;
                color: #333;
            }}
            QPushButton {{
                background: {color};
                color: white;
                border: none;
                padding: 5px 10px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background: {self.darken_color(color)};
            }}
            QLineEdit, QComboBox {{
                border: 1px solid #ddd;
                padding: 5px;
                border-radius: 4px;
            }}
        """)
        
    def darken_color(self, color, factor=0.8):
        # 将颜色变暗
        from PyQt5.QtGui import QColor
        c = QColor(color)
        return c.darker(int(255 * factor)).name()
        
    def show_settings_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("设置" if self.is_cn else "Settings")
        dialog.setFixedSize(520, 600)
        tab_widget = QTabWidget(dialog)
        
        # 常规设置 Tab
        general_tab = QWidget()
        layout = QVBoxLayout(general_tab)

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

        # 主题设置 Tab
        theme_tab = QWidget()
        theme_layout = QVBoxLayout(theme_tab)
        
        # 主题市场按钮
        theme_market_btn = QPushButton("主题市场" if self.is_cn else "Theme Market")
        theme_market_btn.setIcon(QIcon("theme.png"))
        theme_market_btn.clicked.connect(self.show_theme_market)
        theme_layout.addWidget(theme_market_btn)
        
        # 导入主题按钮
        import_btn = QPushButton("导入主题" if self.is_cn else "Import Theme")
        import_btn.setIcon(QIcon("folder.png"))
        import_btn.clicked.connect(self.import_theme)
        theme_layout.addWidget(import_btn)
        
        # 导出主题按钮
        export_btn = QPushButton("导出当前主题" if self.is_cn else "Export Current Theme")
        export_btn.setIcon(QIcon("download.png"))
        export_btn.clicked.connect(self.export_theme)
        theme_layout.addWidget(export_btn)
        
        # 自定义颜色选择器
        color_label = QLabel("自定义颜色:" if self.is_cn else "Custom Colors:")
        theme_layout.addWidget(color_label)
        
        color_grid = QWidget()
        color_grid_layout = QGridLayout(color_grid)
        
        colors = ["#00a1d6", "#fb7299", "#ff9800", "#4caf50", 
                 "#9c27b0", "#607d8b", "#795548", "#f44336"]
        
        for i, color in enumerate(colors):
            btn = QPushButton()
            btn.setFixedSize(40, 40)
            btn.setStyleSheet(f"background:{color};border:none;")
            btn.clicked.connect(lambda _, c=color: self.apply_custom_color(c))
            color_grid_layout.addWidget(btn, i//4, i%4)
        
        theme_layout.addWidget(color_grid)
        
        # 添加Tab
        tab_widget.addTab(general_tab, "常规设置" if self.is_cn else "General")
        tab_widget.addTab(theme_tab, "主题" if self.is_cn else "Themes")
        
        main_layout = QVBoxLayout(dialog)
        main_layout.addWidget(tab_widget)
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
