from PySide6.QtCore import QUrl, QObject, Slot, Property, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtCore import (
    Qt,
    Signal,  # PyQt5的pyqtSignal改为Signal
    QObject,
    QPoint,
    QEvent,
    QTimer,
    QUrl,
    QSize,
    QPropertyAnimation,
    QRect,
    QThread,
)
from PySide6.QtGui import (
    QPixmap,
    QImage,
    QIcon,
    QMouseEvent,
    QColor,
    QCursor,
    QFont,
    QPainter,
)
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QProgressBar,
    QMessageBox,
    QFrame,
    QListWidget,
    QListWidgetItem,
    QDialog,
    QSlider,
    QSizePolicy,
    QTabWidget,
    QGridLayout,
    QScrollArea,
    QFileDialog,
    QSpacerItem,
)
import requests
from bs4 import BeautifulSoup
import logging
from dataclasses import dataclass
from typing import Optional
from ctypes import wintypes
import ctypes
import socket
from concurrent.futures import ThreadPoolExecutor
import json
import time
from urllib.request import urlopen
import yt_dlp
import threading
import re
import sys
import os

# OpenGL 相关环境变量设置 - 必须在 PySide6 导入之前
os.environ["QT_OPENGL"] = "software"
os.environ["QT_QUICK_BACKEND"] = "software"
os.environ["QSG_RHI_BACKEND"] = "software"
os.environ["QT_OPENGL_BUGLIST"] = "0"
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"


# 统一使用 PySide6


@dataclass
class VideoState:
    """视频状态记录"""

    last_position: float = 0
    last_url: Optional[str] = None
    is_fullscreen: bool = False
    volume: float = 80
    is_paused: bool = True

    def save_to_file(self, filepath: str):
        """保存状态到文件"""
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "last_position": self.last_position,
                        "last_url": self.last_url,
                        "is_fullscreen": self.is_fullscreen,
                        "volume": self.volume,
                        "is_paused": self.is_paused,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            print(f"保存状态失败: {e}")

    def load_from_file(self, filepath: str) -> bool:
        """从文件加载状态"""
        try:
            if not os.path.exists(filepath):
                return False
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.last_position = data.get("last_position", 0)
                self.last_url = data.get("last_url")
                self.is_fullscreen = data.get("is_fullscreen", False)
                self.volume = data.get("volume", 80)
                self.is_paused = data.get("is_paused", True)
            return True
        except Exception as e:
            print(f"加载状态失败: {e}")
            return False


# 在文件顶部添加
try:
    from mpv import MPV
    import mpv  # <--- 添加这一行

    MPV_AVAILABLE = True
except ImportError:
    MPV_AVAILABLE = False

# 创建下载文件夹
if not os.path.exists("download"):
    os.makedirs("download")


def safe_filename(title):
    return re.sub(r'[\\/:*?"<>|]', "_", title)


def truncate_name(name, max_len):
    """截断文本并添加省略号"""
    if len(name) <= max_len:
        return name
    return name[:max_len] + "…"


class DownloadSignals(QObject):
    progress = Signal(float)  # pyqtSignal改为Signal
    finished = Signal()
    error = Signal(str)


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
            pixmap = QPixmap("icon.ico").scaled(
                20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
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
        self.setFixedSize(1120, 630)  # 设置窗口大小
        self.signals = DownloadSignals()
        self._wasActive = False
        self.is_dark = False  # 主题状态
        self.is_cn = True  # 语言状态
        self.download_queue = []  # [(title, status), ...]
        self.download_path = os.path.abspath("download")  # <--- 添加这一行
        # 添加缺失的数据库相关初始化
        self._db_search_keyword = ""
        self._db_page_size = 20
        self._db_page = 1
        self._db_total_page = 1
        self._db_anime_data = []
        # 添加线程管理
        self.active_threads = []  # 跟踪活动线程
        self._is_closing = False  # 关闭标志

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

    def init_anime_zone_ui(self, widget):
        """初始化动漫专区界面"""

        # 修复布局创建方式
        layout = QVBoxLayout()  # 不传递 widget 参数
        widget.setLayout(layout)  # 然后设置到 widget 上
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 搜索框
        search_layout = QHBoxLayout()
        self.anime_search = QLineEdit()
        self.anime_search.setPlaceholderText("输入动漫名称搜索...")
        self.anime_search.setMinimumHeight(40)
        self.anime_search.setStyleSheet(
            """
            QLineEdit {
                border: 2px solid #00a1d6;
                border-radius: 20px;
                padding: 8px 15px;
                font-size: 14px;
                background: white;
            }
            QLineEdit:focus {
                border-color: #0088cc;
                background: #f8f8f8;
            }
        """
        )
        search_layout.addWidget(self.anime_search)
        layout.addLayout(search_layout)

        # 动漫资源标题 - 居中显示
        title_label = QLabel("动漫资源")
        title_label.setAlignment(Qt.AlignCenter)  # 水平居中
        title_label.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
        title_label.setStyleSheet(
            """
            QLabel {
                color: #00a1d6;
                padding: 10px;
                margin: 10px 0;
            }
        """
        )
        layout.addWidget(title_label)

        # 分页按钮
        page_layout = QHBoxLayout()
        self.prev_btn = QPushButton("上一页")
        self.next_btn = QPushButton("下一页")

        # 设置按钮样式
        button_style = """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 #00a1d6, stop:1 #0088cc);
                color: white;
                border: 2px solid transparent;
                border-radius: 25px;
                padding: 10px 30px;
                font-size: 14px;
                font-weight: bold;
                min-width: 100px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 #0088cc, stop:1 #006699);
                border-color: #e3f1fd;
            }
            QPushButton:pressed {
                background: #006699;
            }
            QPushButton:disabled {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 #cccccc, stop:1 #999999);
                color: #666666;
                border-color: transparent;
            }
        """

        self.prev_btn.setStyleSheet(button_style)
        self.next_btn.setStyleSheet(button_style)

        # 按钮布局 - 左右分布
        page_layout.addWidget(self.prev_btn)
        page_layout.addStretch()  # 添加弹性空间，使按钮分布在两端
        page_layout.addWidget(self.next_btn)
        layout.addLayout(page_layout)

        # 动漫列表滚动区域
        self.anime_scroll = QScrollArea()
        self.anime_scroll.setWidgetResizable(True)
        self.anime_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.anime_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.anime_scroll.setStyleSheet(
            """
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: #f0f0f0;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #00a1d6;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #0088cc;
            }
        """
        )

        # 创建滚动区域的内容组件
        self.anime_container = QWidget()
        self.anime_scroll.setWidget(self.anime_container)
        layout.addWidget(self.anime_scroll)

        # 加载状态标签 - 居中显示
        self.loading_label = QLabel("加载中...")
        self.loading_label.setAlignment(Qt.AlignCenter)  # 水平和垂直居中
        self.loading_label.setFont(QFont("Microsoft YaHei", 16))
        self.loading_label.setStyleSheet(
            """
            QLabel {
                color: #00a1d6;
                background: transparent;
                padding: 50px;
                min-height: 200px;
            }
        """
        )

        # 初始化时显示加载标签
        temp_layout = QVBoxLayout(self.anime_container)
        temp_layout.setAlignment(Qt.AlignCenter)  # 布局也居中
        temp_layout.addWidget(self.loading_label)

        # 绑定事件
        self.prev_btn.clicked.connect(self.prev_page)
        self.next_btn.clicked.connect(self.next_page)
        self.anime_search.textChanged.connect(self.search_anime)

        # 异步加载数据
        self.load_anime_data()

    def show_anime_detail(self, idx):
        try:
            # 获取动漫数据
            if not hasattr(self, "_db_anime_data") or idx >= len(self._db_anime_data):
                QMessageBox.warning(self, "错误", "无效的动漫索引")
                return

            anime_id, name, cover_url = self._db_anime_data[idx]

            # 数据库查询
            import sqlite3

            try:
                conn = sqlite3.connect("anime.db")
                c = conn.cursor()
                c.execute(
                    "SELECT intro, year, area, type, total_eps FROM anime WHERE id=?",
                    (anime_id,),
                )
                row = c.fetchone()
                intro, year, area, type_str, total_eps = (
                    row if row else ("", "", "", "", "")
                )

                c.execute(
                    "SELECT DISTINCT line_id FROM episode WHERE anime_id=? ORDER BY line_id",
                    (anime_id,),
                )
                lines = [r[0] for r in c.fetchall()]

                if not lines:
                    QMessageBox.warning(self, "错误", "该动漫没有可播放的线路")
                    conn.close()
                    return

                current_line = lines[0]
                c.execute(
                    "SELECT title, play_url, real_video_url FROM episode WHERE anime_id=? AND line_id=? ORDER BY id",
                    (anime_id, current_line),
                )
                eps = c.fetchall()
                conn.close()

                if not eps:
                    QMessageBox.warning(self, "错误", "该动漫没有可播放的集数")
                    return

            except Exception as e:
                QMessageBox.critical(self, "数据库错误", f"查询失败: {e}")
                return

            # 创建主窗口 - 修复窗口设置
            dialog = QWidget(None, Qt.Window)
            dialog.setWindowTitle(name)
            dialog.setWindowFlags(
                Qt.Window
                | Qt.WindowCloseButtonHint
                | Qt.WindowMinimizeButtonHint
                | Qt.WindowMaximizeButtonHint
            )

            # 设置初始大小和最小大小
            dialog.resize(1400, 1000)
            dialog.setMinimumSize(1000, 700)  # 设置最小尺寸，允许缩小
            dialog.setMaximumSize(2560, 1440)  # 设置最大尺寸，防止过度拉伸

            dialog.setStyleSheet(self.get_stylesheet())

            # 主布局 - 修复布局设置
            main_layout = QVBoxLayout(dialog)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(0)

            # 视频播放器区域 - 修复大小策略
            video_container = QFrame()
            video_container.setStyleSheet("background: #000000; border: none;")
            video_container.setMinimumHeight(400)  # 降低最小高度
            video_container.setMaximumHeight(800)  # 设置最大高度
            video_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            video_layout = QVBoxLayout(video_container)
            video_layout.setContentsMargins(0, 0, 0, 0)
            video_layout.setSpacing(0)

            # 创建视频播放器组件
            if MPV_AVAILABLE:
                video_widget = self.create_mpv_widget(dialog)
                if video_widget is None:
                    video_widget = self.create_fallback_widget()
            else:
                video_widget = self.create_fallback_widget()

            # 确保视频控件不为空并设置大小策略
            if video_widget is not None:
                video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                video_widget.setMinimumHeight(300)  # 设置最小高度
                video_layout.addWidget(video_widget)
            else:
                error_label = QLabel("视频播放器初始化失败")
                error_label.setAlignment(Qt.AlignCenter)
                error_label.setStyleSheet("color: white; font-size: 18px;")
                error_label.setMinimumHeight(300)
                video_layout.addWidget(error_label)

            # 创建控制栏
            control_bar = self.create_control_bar()
            if control_bar is not None:
                control_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                video_layout.addWidget(control_bar)

            # 内容区域 - 修复滚动和布局
            content_container = QScrollArea()  # 改为滚动区域
            content_container.setWidgetResizable(True)
            content_container.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            content_container.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            content_container.setStyleSheet(
                """
                QScrollArea {
                    background: #f8f9fa;
                    border-top: 1px solid #e9ecef;
                    border: none;
                }
                QScrollBar:vertical {
                    background: #f1f1f1;
                    width: 12px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical {
                    background: #00a1d6;
                    border-radius: 6px;
                    min-height: 30px;
                }
                QScrollBar::handle:vertical:hover {
                    background: #0099cc;
                }
            """
            )

            # 内容容器
            content_widget = QWidget()
            content_layout = QHBoxLayout(content_widget)
            content_layout.setContentsMargins(20, 20, 20, 20)
            content_layout.setSpacing(20)

            video_widget.control_bar = control_bar

            # 处理线路名称
            line_names = []
            for lid in lines:
                if str(lid).startswith("ul_playlist_"):
                    try:
                        num = int(str(lid).replace("ul_playlist_", ""))
                        line_names.append(f"线路{num}")
                    except Exception:
                        line_names.append(str(lid))
                else:
                    line_names.append(str(lid))

            # 左侧：动漫信息 - 修复大小策略
            info_section = self.create_info_section_fixed(
                name, cover_url, intro, year, area, type_str, total_eps, line_names
            )
            if info_section is not None:
                info_section.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
                content_layout.addWidget(info_section)

            # 右侧：分集列表 - 修复大小策略
            episode_section = self.create_episode_section_fixed(eps)
            if episode_section is not None:
                episode_section.setSizePolicy(
                    QSizePolicy.Expanding, QSizePolicy.Expanding
                )
                content_layout.addWidget(episode_section)

            # 设置内容区域
            content_container.setWidget(content_widget)
            content_container.setMinimumHeight(250)  # 设置最小高度
            content_container.setMaximumHeight(600)  # 设置最大高度

            # 添加到主布局 - 修复布局比例
            main_layout.addWidget(video_container, stretch=3)  # 视频区域占3份
            main_layout.addWidget(content_container, stretch=2)  # 内容区域占2份

            # 事件绑定
            if MPV_AVAILABLE and video_widget and hasattr(video_widget, "mpv"):
                try:
                    self.setup_video_events(video_widget, control_bar, dialog)
                    self.setup_episode_events(video_widget, episode_section, eps)
                    self.setup_line_events(
                        video_widget, info_section, anime_id, lines, episode_section
                    )
                    self.setup_state_management(
                        video_widget, anime_id, info_section, episode_section
                    )
                except Exception as e:
                    print(f"事件绑定失败: {e}")

            # 添加窗口大小变化事件处理
            def on_resize_event(event):
                # 确保布局正确更新
                dialog.updateGeometry()
                content_widget.updateGeometry()
                if hasattr(video_widget, "updateGeometry"):
                    video_widget.updateGeometry()
                event.accept()

            dialog.resizeEvent = on_resize_event
            dialog.show()

        except Exception as e:
            print(f"Error in show_anime_detail: {e}")
            import traceback

            traceback.print_exc()
            QMessageBox.critical(self, "错误", f"显示动漫详情时发生错误:\n{e}")

    def show_qml_player(self, video_url):
        app = QGuiApplication.instance()
        if app is None:
            app = QGuiApplication([])
        engine = QQmlApplicationEngine()
        mpv_obj = MpvBridge()
        engine.rootContext().setContextProperty("mpvObj", mpv_obj)
        qml_path = os.path.abspath("player.qml")
        engine.load(qml_path)  # 直接传字符串路径
        if not engine.rootObjects():
            return
        mpv_obj.play(video_url)
        # QML窗口会自动显示并阻塞，关闭即返回

    def create_info_section_fixed(
        self, name, cover_url, intro, year, area, type_str, total_eps, line_names
    ):
        """创建修复的信息区域"""
        info_widget = QFrame()
        info_widget.setStyleSheet(
            """
            QFrame {
                background: #ffffff;
                border: 1px solid #e9ecef;
                border-radius: 12px;
                padding: 15px;
            }
        """
        )
        info_widget.setFixedWidth(380)  # 固定宽度，防止拉伸变形
        info_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        layout = QVBoxLayout(info_widget)
        layout.setSpacing(12)
        layout.setContentsMargins(15, 15, 15, 15)

        # 标题
        title_label = QLabel(name)
        title_label.setStyleSheet(
            """
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #333333;
                background: transparent;
                border: none;
            }
        """
        )
        title_label.setWordWrap(True)
        title_label.setMaximumHeight(60)
        layout.addWidget(title_label)

        # 封面
        cover_label = QLabel()
        cover_label.setFixedSize(180, 240)  # 稍微调整尺寸
        cover_label.setStyleSheet(
            """
            QLabel {
                border: 2px solid #e9ecef;
                border-radius: 8px;
                background: #f8f9fa;
                color: #666666;
                font-size: 14px;
            }
        """
        )
        cover_label.setAlignment(Qt.AlignCenter)

        if cover_url:
            try:
                img_data = urlopen(cover_url).read()
                pixmap = QPixmap()
                pixmap.loadFromData(img_data)
                pixmap = pixmap.scaled(
                    176, 236, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                cover_label.setPixmap(pixmap)
            except Exception:
                cover_label.setText("封面\n加载失败")
        else:
            cover_label.setText("无封面")

        layout.addWidget(cover_label, alignment=Qt.AlignCenter)

        # 信息表格 - 紧凑布局
        info_data = [
            ("年份", year or "未知"),
            ("地区", area or "未知"),
            ("类型", type_str or "未知"),
            ("总集数", total_eps or "未知"),
        ]

        for label_text, value_text in info_data:
            row_widget = QFrame()
            row_widget.setStyleSheet(
                """
                QFrame {
                    background: #f8f9fa;
                    border: 1px solid #e9ecef;
                    border-radius: 6px;
                    padding: 5px;
                }
            """
            )
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(8, 4, 8, 4)
            row_layout.setSpacing(8)

            label = QLabel(f"{label_text}:")
            label.setStyleSheet(
                """
                QLabel {
                    font-weight: bold;
                    color: #495057;
                    min-width: 50px;
                    background: transparent;
                    border: none;
                    font-size: 12px;
                }
            """
            )

            value = QLabel(str(value_text))
            value.setStyleSheet(
                """
                QLabel {
                    color: #212529;
                    background: transparent;
                    border: none;
                    font-size: 12px;
                }
            """
            )
            value.setWordWrap(True)

            row_layout.addWidget(label)
            row_layout.addWidget(value, stretch=1)
            layout.addWidget(row_widget)

        # 线路选择
        if line_names:
            line_label = QLabel("播放线路:")
            line_label.setStyleSheet(
                """
                QLabel {
                    font-weight: bold;
                    color: #495057;
                    background: transparent;
                    border: none;
                    font-size: 13px;
                }
            """
            )
            layout.addWidget(line_label)

            line_combo = QComboBox()
            line_combo.addItems(line_names)
            line_combo.setObjectName("line_selector")
            line_combo.setFixedHeight(30)
            line_combo.setStyleSheet(
                """
                QComboBox {
                    font-size: 12px;
                    padding: 6px 10px;
                    border: 2px solid #00a1d6;
                    border-radius: 6px;
                    background: #ffffff;
                    color: #333333;
                }
                QComboBox::drop-down {
                    border: none;
                    width: 20px;
                }
                QComboBox::down-arrow {
                    image: none;
                    border-left: 4px solid transparent;
                    border-right: 4px solid transparent;
                    border-top: 6px solid #00a1d6;
                }
                QComboBox QAbstractItemView {
                    background: #ffffff;
                    border: 1px solid #00a1d6;
                    selection-background-color: #e3f1fd;
                    color: #333333;
                }
            """
            )
            layout.addWidget(line_combo)

        # 简介 - 紧凑显示
        if intro and intro.strip():
            intro_label = QLabel("简介:")
            intro_label.setStyleSheet(
                """
                QLabel {
                    font-weight: bold;
                    color: #495057;
                    background: transparent;
                    border: none;
                    font-size: 13px;
                }
            """
            )
            layout.addWidget(intro_label)

            intro_scroll = QScrollArea()
            intro_scroll.setWidgetResizable(True)
            intro_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            intro_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            intro_scroll.setFixedHeight(100)  # 固定高度
            intro_scroll.setStyleSheet(
                """
                QScrollArea {
                    border: 1px solid #dee2e6;
                    border-radius: 6px;
                    background: #ffffff;
                }
                QScrollBar:vertical {
                    background: #f8f9fa;
                    width: 8px;
                    border-radius: 4px;
                }
                QScrollBar::handle:vertical {
                    background: #00a1d6;
                    border-radius: 4px;
                    min-height: 20px;
                }
            """
            )

            intro_text = QLabel(intro.strip())
            intro_text.setWordWrap(True)
            intro_text.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            intro_text.setStyleSheet(
                """
                QLabel {
                    color: #212529;
                    padding: 8px;
                    background: transparent;
                    border: none;
                    font-size: 12px;
                    line-height: 1.4;
                }
            """
            )
            intro_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

            intro_scroll.setWidget(intro_text)
            layout.addWidget(intro_scroll)

        return info_widget

    def create_episode_section_fixed(self, episodes):
        """创建修复的分集区域 - 优化样式版本"""
        episode_widget = QFrame()
        episode_widget.setStyleSheet(
            """
            QFrame {
                background: #ffffff;
                border: 1px solid #e9ecef;
                border-radius: 12px;
                padding: 15px;
            }
        """
        )
        episode_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(episode_widget)
        layout.setSpacing(12)
        layout.setContentsMargins(15, 15, 15, 15)

        # 标题
        title_label = QLabel("选集")
        title_label.setStyleSheet(
            """
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #333333;
                background: transparent;
                border: none;
            }
        """
        )
        layout.addWidget(title_label)

        # 滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll_area.setStyleSheet(
            """
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                width: 12px;
                background: #f1f1f1;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #00a1d6;
                border-radius: 6px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #0099cc;
            }
            QScrollBar:horizontal {
                height: 12px;
                background: #f1f1f1;
                border-radius: 6px;
            }
            QScrollBar::handle:horizontal {
                background: #00a1d6;
                border-radius: 6px;
                min-width: 30px;
            }
        """
        )

        # 分集容器
        episode_container = QWidget()
        episode_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        episode_layout = QGridLayout(episode_container)
        episode_layout.setSpacing(8)
        episode_layout.setContentsMargins(5, 5, 5, 5)

        # 创建分集按钮
        episode_buttons = []
        columns = 5  # 每行5个按钮

        for i, (ep_title, play_url, real_url) in enumerate(episodes):
            btn = QPushButton(ep_title)
            btn.setCheckable(True)
            btn.setMinimumSize(100, 45)
            btn.setMaximumSize(150, 55)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setObjectName(f"episode_button_{i}")
            btn.setStyleSheet(
                """
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #ffffff, stop:1 #f8f9fa);
                    border: 2px solid #00a1d6;
                    border-radius: 8px;
                    padding: 8px 12px;
                    color: #00a1d6;
                    font-size: 13px;
                    font-weight: bold;
                    text-align: center;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #e3f1fd, stop:1 #cce7f0);
                    border-color: #0088cc;
                }
                QPushButton:checked {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #00a1d6, stop:1 #0088cc);
                    color: #ffffff;
                    border-color: #0088cc;
                    font-weight: bold;
                }
                QPushButton:checked:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #0088cc, stop:1 #006699);
                }
                QPushButton:pressed {
                    background: #0088cc;
                }
            """
            )
            row = i // columns
            col = i % columns
            episode_layout.addWidget(btn, row, col)
            episode_buttons.append(btn)

        # 设置列拉伸
        for col in range(columns):
            episode_layout.setColumnStretch(col, 1)

        scroll_area.setWidget(episode_container)
        layout.addWidget(scroll_area)

        # 保存按钮引用
        episode_widget.episode_buttons = episode_buttons

        return episode_widget

    def create_mpv_widget(self, parent_dialog):
        """创建 MPV 播放器组件 - 简化版本，避免绘制冲突"""
        if not MPV_AVAILABLE:
            return self.create_fallback_widget()

        try:

            class SafeMpvWidget(QWidget):
                def __init__(self, parent=None):
                    super().__init__(parent)
                    self.parent_dialog = parent
                    self.state = VideoState()
                    self.logger = logging.getLogger(self.__class__.__name__)

                    # 基本设置
                    self.setMinimumSize(800, 450)
                    self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                    self.setStyleSheet("background: #000000;")
                    self.setFocusPolicy(Qt.StrongFocus)
                    self.setMouseTracking(True)

                    # 关键修复：设置正确的属性，避免绘制冲突
                    self.setAttribute(Qt.WA_OpaquePaintEvent, True)
                    self.setAttribute(Qt.WA_NoSystemBackground, True)
                    self.setAttribute(Qt.WA_NativeWindow, True)
                    self.setAttribute(Qt.WA_PaintOnScreen, True)
                    self.setAttribute(Qt.WA_DontCreateNativeAncestors, False)

                    # 播放状态
                    self.duration = 0
                    self.is_playing = False
                    self.is_seeking = False
                    self.loading = False
                    self.mpv = None
                    self._initialized = False

                    # 回调函数
                    self.on_time_update = None
                    self.on_duration_update = None
                    self.on_pause_update = None
                    self.on_volume_update = None
                    self.on_loading_update = None

                    # 控制栏相关
                    self.control_visible = True
                    self.hide_timer = QTimer(self)
                    self.hide_timer.setSingleShot(True)
                    self.hide_timer.timeout.connect(self.auto_hide_controls)

                    # 创建状态标签 - 使用更简单的方式
                    self.status_label = QLabel("正在初始化播放器...", self)
                    self.status_label.setAlignment(Qt.AlignCenter)
                    self.status_label.setStyleSheet(
                        """
                        QLabel {
                            color: #ffffff;
                            font-size: 16px;
                            background: rgba(0, 0, 0, 200);
                            border-radius: 8px;
                            padding: 20px;
                            border: 2px solid #00a1d6;
                        }
                    """
                    )
                    self.status_label.hide()

                    # 延迟初始化 MPV
                    QTimer.singleShot(1000, self.safe_init_mpv)

                def ensure_visible(self):
                    if not self.isVisible():
                        self.show()

                def safe_init_mpv(self):
                    try:
                        self.status_label.setText("正在初始化播放器...")
                        self.status_label.show()

                        # 确保窗口已经完全创建且可见
                        if not self.isVisible():
                            self.show()

                        # 等待窗口完全渲染
                        self.update()
                        QApplication.processEvents()

                        # 多次检查窗口句柄
                        max_attempts = 10
                        for attempt in range(max_attempts):
                            wid = self.winId()
                            if wid and wid != 0:
                                print(f"获取到有效窗口句柄: {wid} (尝试 {attempt + 1})")
                                break
                            else:
                                print(f"窗口句柄无效，等待... (尝试 {attempt + 1})")
                                QTimer.singleShot(200, lambda: None)
                                QApplication.processEvents()
                                if attempt == max_attempts - 1:
                                    raise Exception("无法获取有效的窗口句柄")

                        # 使用简化的MPV配置，移除有问题的选项
                        self.mpv = MPV(
                            wid=str(int(wid)),
                            log_handler=print,
                            loglevel="error",
                            # 基本视频输出设置
                            vo="direct3d,gpu,opengl,software",
                            hwdec="no",
                            # 网络设置 - 使用更简单的配置
                            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                            network_timeout=60,
                            # 移除可能有问题的HTTP头设置，改为通过user-agent处理
                            # 缓存设置
                            cache=True,
                            cache_secs=30,
                            demuxer_max_bytes="50MiB",
                            demuxer_readahead_secs=15,
                            # 基本设置
                            keep_open=True,
                            idle=True,
                            osd_level=0,
                            cursor_autohide=False,
                            # 音频设置
                            audio_device="auto",
                            volume=80,
                            # 渲染设置
                            gpu_context="auto",
                            opengl_es="no",
                            # ytdl设置
                            ytdl=True,
                            ytdl_format="best",
                        )

                        # 绑定事件前先测试MPV是否正常工作
                        try:
                            # 测试基本属性访问
                            _ = self.mpv.volume
                            _ = self.mpv.pause
                        except Exception as e:
                            print(f"MPV基本功能测试失败: {e}")
                            raise

                        # 绑定事件
                        self.mpv.observe_property("duration", self._on_duration)
                        self.mpv.observe_property("time-pos", self._on_timepos)
                        self.mpv.observe_property("pause", self._on_pause)
                        self.mpv.observe_property("volume", self._on_volume)
                        self.mpv.observe_property("core-idle", self._on_core_idle)

                        self.mpv.pause = True
                        self.mpv.volume = 80

                        self._initialized = True
                        self.status_label.setText("播放器就绪")
                        QTimer.singleShot(1500, self.status_label.hide)

                        print("MPV 初始化成功")

                    except Exception as e:
                        self.logger.error(f"MPV 初始化失败: {e}")
                        self.mpv = None
                        self._initialized = False
                        print(f"MPV 初始化失败: {e}")
                        self.show_error_message(f"MPV 初始化失败: {e}")

                def show_error_message(self, message):
                    """显示错误信息 - 改进版本"""
                    self.status_label.setText(f"播放失败")
                    self.status_label.setStyleSheet(
                        """
                        QLabel {
                            color: #ff4444;
                            font-size: 16px;
                            background: rgba(0, 0, 0, 200);
                            border-radius: 8px;
                            padding: 20px;
                            border: 2px solid #ff4444;
                        }
                    """
                    )
                    self.status_label.show()

                    # 5秒后自动隐藏
                    QTimer.singleShot(8000, self.status_label.hide)

                    # 同时在控制台输出详细错误信息
                    print(f"播放错误: {message}")

                def play(self, url):
                    """播放视频 - 修复版本"""
                    if not self.mpv or not self._initialized:
                        print("MPV 播放器未初始化")
                        self.show_error_message("播放器未初始化")
                        return

                    if not url:
                        print("视频链接为空")
                        self.show_error_message("视频链接为空")
                        return

                    try:
                        print(f"开始播放: {url}")

                        # 显示加载状态
                        self.loading = True
                        if self.on_loading_update:
                            self.on_loading_update(True)

                        self.status_label.setText("正在加载视频...")
                        self.status_label.setStyleSheet(
                            """
                            QLabel {
                                color: #ffffff;
                                font-size: 16px;
                                background: rgba(0, 0, 0, 200);
                                border-radius: 8px;
                                padding: 20px;
                                border: 2px solid #00a1d6;
                            }
                        """
                        )
                        self.status_label.show()

                        # 停止当前播放
                        try:
                            self.mpv.stop()
                            # 短暂等待确保停止完成
                            QTimer.singleShot(100, lambda: self._continue_play(url))
                            return
                        except:
                            pass

                        self._continue_play(url)

                    except Exception as e:
                        error_msg = f"播放失败: {e}"
                        print(error_msg)
                        self.show_error_message(error_msg)
                        if self.on_loading_update:
                            self.on_loading_update(False)
                        self.loading = False

                def _continue_play(self, url):
                    """继续播放流程 - 修复HLS流播放"""
                    try:
                        # 处理URL
                        processed_url = self.process_video_url(url)
                        if not processed_url:
                            self.show_error_message("视频链接处理失败")
                            return

                        # 记录播放位置
                        if url != self.state.last_url:
                            self.state.last_position = 0
                        self.state.last_url = url

                        print(f"准备播放: {processed_url}")

                        # 对于HLS流，直接播放，不设置无效属性
                        if processed_url.endswith(".m3u8") or "m3u8" in processed_url:
                            self.status_label.setText("正在加载HLS流...")
                            self.status_label.show()

                            try:
                                # 直接播放HLS流，不设置无效的属性
                                self.mpv.play(processed_url)
                                print(f"开始播放HLS流: {processed_url}")

                            except Exception as e:
                                print(f"HLS流播放失败: {e}")
                                self.show_error_message(
                                    f"HLS流播放失败: {e}\n\n可能原因:\n1. 视频链接已失效\n2. 网络连接问题\n3. 服务器限制访问"
                                )
                                return
                        else:
                            # 普通视频文件播放
                            if self._check_url_validity(processed_url):
                                self.mpv.play(processed_url)
                            else:
                                self.show_error_message(
                                    "视频链接无效或已过期，请重新获取"
                                )
                                return

                        # 延迟隐藏加载标签
                        def hide_loading():
                            if hasattr(self, "status_label"):
                                self.status_label.hide()
                            if self.on_loading_update:
                                self.on_loading_update(False)
                            self.loading = False

                        QTimer.singleShot(5000, hide_loading)

                    except Exception as e:
                        error_msg = f"播放失败: {e}"
                        print(error_msg)
                        self.show_error_message(error_msg)
                        if self.on_loading_update:
                            self.on_loading_update(False)
                        self.loading = False

                def _check_url_validity(self, url):
                    """检查URL有效性 - 特别针对HLS流"""
                    try:
                        import urllib.request
                        import urllib.parse

                        # 对于HLS流，先检查m3u8文件是否可访问
                        if url.endswith(".m3u8") or "m3u8" in url:
                            print(f"检查HLS流: {url}")

                            # 创建请求，使用更完整的请求头
                            req = urllib.request.Request(
                                url,
                                headers={
                                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                                    "Referer": "https://www.yzzy-online.com/",
                                    "Accept": "*/*",
                                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                                    "Accept-Encoding": "gzip, deflate",
                                    "Connection": "keep-alive",
                                    "Sec-Fetch-Dest": "empty",
                                    "Sec-Fetch-Mode": "cors",
                                    "Sec-Fetch-Site": "cross-site",
                                },
                            )

                            try:
                                with urllib.request.urlopen(
                                    req, timeout=15
                                ) as response:
                                    if response.status == 200:
                                        # 读取m3u8内容检查格式
                                        content = response.read().decode("utf-8")
                                        if "#EXTM3U" in content:
                                            print("HLS流格式验证通过")
                                            return True
                                        else:
                                            print("HLS流格式无效")
                                            return False
                                    else:
                                        print(f"HLS流响应状态码: {response.status}")
                                        return False
                            except Exception as e:
                                print(f"HLS流检查失败: {e}")
                                # 对于HLS流，即使检查失败也允许尝试播放
                                return True
                        else:
                            # 普通视频文件的检查
                            req = urllib.request.Request(
                                url,
                                headers={
                                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                                    "Referer": "https://www.douyin.com/",
                                    "Accept": "*/*",
                                },
                            )

                            with urllib.request.urlopen(req, timeout=10) as response:
                                return response.status == 200

                    except Exception as e:
                        print(f"URL有效性检查失败: {e}")
                        return True  # 检查失败时仍然尝试播放

                def process_video_url(self, url):
                    """处理视频URL - 修复版本"""
                    if not url:
                        return url

                    try:
                        # 检查URL是否有效
                        import urllib.request
                        import urllib.parse

                        # 解析URL参数，检查是否过期
                        parsed_url = urllib.parse.urlparse(url)
                        query_params = urllib.parse.parse_qs(parsed_url.query)

                        if "x-expires" in query_params:
                            import time

                            expires = int(query_params["x-expires"][0])
                            current_time = int(time.time())

                            if current_time > expires:
                                print(
                                    f"视频链接已过期，过期时间: {expires}, 当前时间: {current_time}"
                                )
                                self.show_error_message("视频链接已过期，请重新获取")
                                return None

                        # 添加必要的请求头
                        if url.endswith(".m3u8") or "m3u8" in url or "capcut" in url:
                            # 对于特殊流媒体链接，添加用户代理和引用页
                            return url

                        return url

                    except Exception as e:
                        print(f"处理视频URL时出错: {e}")
                        return url

                def seek_to(self, position):
                    """跳转到指定位置 - 改进版本"""
                    if not (hasattr(self, "mpv") and self.mpv and self._initialized):
                        return

                    try:
                        # 确保 MPV 已经加载了视频并且有有效的时长
                        if not hasattr(self.mpv, "duration") or not self.mpv.duration:
                            print("视频尚未加载完成，无法跳转")
                            return

                        # 确保跳转位置在有效范围内
                        duration = self.mpv.duration
                        if position < 0:
                            position = 0
                        elif position > duration:
                            position = duration - 1

                        # 显示跳转状态
                        mins, secs = divmod(int(position), 60)
                        self.status_label.setText(f"跳转到 {mins:02d}:{secs:02d}")
                        self.status_label.show()
                        QTimer.singleShot(2000, self.status_label.hide)

                        # 使用 seek 命令
                        self.mpv.seek(position, reference="absolute")
                        print(f"跳转到: {position:.2f}秒")

                    except Exception as e:
                        print(f"跳转失败: {e}")
                        self.show_error_message(f"跳转失败: {e}")

                def set_pause(self, paused):
                    """设置暂停状态"""
                    if self.mpv and self._initialized:
                        try:
                            self.mpv.pause = paused
                            status = "暂停" if paused else "播放"
                            self.status_label.setText(status)
                            self.status_label.show()
                            QTimer.singleShot(1000, self.status_label.hide)
                        except Exception as e:
                            self.logger.error(f"设置暂停失败: {e}")

                def set_volume(self, volume):
                    """设置音量"""
                    if self.mpv and self._initialized:
                        try:
                            volume = max(0, min(100, volume))
                            self.mpv.volume = volume
                            self.status_label.setText(f"音量: {volume}%")
                            self.status_label.show()
                            QTimer.singleShot(1000, self.status_label.hide)
                        except Exception as e:
                            self.logger.error(f"设置音量失败: {e}")

                # MPV 事件回调

                def _on_duration(self, name, value):
                    if value is not None:
                        self.duration = value
                        if self.on_duration_update:
                            self.on_duration_update(self.duration)

                def _on_timepos(self, name, value):
                    if (
                        self.on_time_update
                        and not self.is_seeking
                        and value is not None
                    ):
                        self.on_time_update(value)

                def _on_pause(self, name, value):
                    if value is not None:
                        self.is_playing = not value
                        if self.on_pause_update:
                            self.on_pause_update(value)

                def _on_volume(self, name, value):
                    if self.on_volume_update and value is not None:
                        self.on_volume_update(int(value))

                def _on_core_idle(self, name, value):
                    if value is not None and value != self.loading:
                        self.loading = value
                        if self.on_loading_update:
                            self.on_loading_update(value)

                # 全屏相关
                def enter_fullscreen(self):
                    """进入全屏 - 修复版本"""
                    if not self.state.is_fullscreen:
                        self.state.is_fullscreen = True

                        # 保存原始状态
                        self._old_parent = self.parent()
                        self._old_geometry = self.geometry()
                        self._old_window_flags = self.windowFlags()

                        # 处理控制栏 - 先隐藏再重新创建为浮动窗口
                        if hasattr(self, "control_bar") and self.control_bar:
                            self.control_bar.hide()
                            self.control_bar.setParent(None)
                            self.control_bar.setWindowFlags(
                                Qt.Tool
                                | Qt.FramelessWindowHint
                                | Qt.WindowStaysOnTopHint
                            )
                            self.control_bar.setAttribute(
                                Qt.WA_TranslucentBackground, True
                            )

                        # 设置视频窗口为全屏
                        self.setParent(None)
                        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
                        self.showFullScreen()

                        # 显示控制栏（浮动）
                        if hasattr(self, "control_bar") and self.control_bar:
                            self.control_bar.show()
                            self.control_bar.raise_()
                            self._update_control_bar_geometry()

                        # 延迟重新绑定MPV，确保窗口完全切换后再绑定
                        QTimer.singleShot(500, self.rebind_mpv)

                        # 设置鼠标自动隐藏
                        self.hide_timer.start(3000)

                def exit_fullscreen(self):
                    """退出全屏 - 修复版本"""
                    if self.state.is_fullscreen:
                        self.state.is_fullscreen = False

                        # 停止自动隐藏定时器
                        if hasattr(self, "hide_timer"):
                            self.hide_timer.stop()

                        # 恢复鼠标
                        self.setCursor(QCursor(Qt.ArrowCursor))

                        # 隐藏浮动控制栏
                        if hasattr(self, "control_bar") and self.control_bar:
                            self.control_bar.hide()
                            self.control_bar.setParent(None)

                        # 恢复窗口
                        if hasattr(self, "_old_window_flags"):
                            self.setWindowFlags(self._old_window_flags)
                        else:
                            self.setWindowFlags(Qt.Widget)

                        if hasattr(self, "_old_parent") and self._old_parent:
                            self.setParent(self._old_parent)
                            if hasattr(self, "_old_geometry"):
                                self.setGeometry(self._old_geometry)

                        self.showNormal()

                        # 恢复控制栏到原位置
                        if hasattr(self, "control_bar") and self.control_bar:
                            # 重新创建控制栏为普通widget
                            if hasattr(self, "_old_parent") and self._old_parent:
                                self.control_bar.setParent(self._old_parent)
                            else:
                                self.control_bar.setParent(self)
                            self.control_bar.setWindowFlags(Qt.Widget)
                            self.control_bar.show()
                            self.control_bar.raise_()
                            self._update_control_bar_geometry()

                        # 延迟重新绑定MPV
                        QTimer.singleShot(500, self.rebind_mpv)

                def resizeEvent(self, event):
                    super().resizeEvent(event)
                    # 居中显示状态标签
                    if hasattr(self, "status_label") and self.status_label:
                        self.status_label.resize(350, 120)
                        center_x = (self.width() - self.status_label.width()) // 2
                        center_y = (self.height() - self.status_label.height()) // 2
                        self.status_label.move(center_x, center_y)
                    # 更新控制栏位置
                    self._update_control_bar_geometry()

                def moveEvent(self, event):
                    super().moveEvent(event)
                    self._update_control_bar_geometry()

                def _update_control_bar_geometry(self):
                    """更新控制栏位置 - 修复版本"""
                    if not (
                        hasattr(self, "control_bar")
                        and self.control_bar
                        and self.control_bar.isVisible()
                    ):
                        return

                    if self.state.is_fullscreen:
                        # 全屏模式：控制栏浮动在屏幕底部
                        if self.control_bar.windowFlags() & Qt.Tool:
                            screen = QApplication.primaryScreen()
                            screen_rect = screen.geometry()
                            control_height = self.control_bar.height()

                            self.control_bar.setGeometry(
                                screen_rect.x(),
                                screen_rect.bottom() - control_height,
                                screen_rect.width(),
                                control_height,
                            )
                    else:
                        # 窗口模式：控制栏在视频窗口底部
                        self.control_bar.setGeometry(
                            0,
                            self.height() - self.control_bar.height(),
                            self.width(),
                            self.control_bar.height(),
                        )

                def rebind_mpv(self):
                    """重新绑定 MPV - 改进版本，避免重复绑定"""
                    if not (hasattr(self, "mpv") and self.mpv and self._initialized):
                        return

                    # 防止重复绑定
                    if hasattr(self, "_rebinding") and self._rebinding:
                        print("MPV正在重新绑定中，跳过此次请求")
                        return

                    self._rebinding = True

                    try:
                        # 确保窗口完全创建
                        wid = self.winId()
                        if not wid or wid == 0:
                            print("窗口句柄无效，延迟重试")
                            QTimer.singleShot(500, self._retry_rebind)
                            return

                        new_wid = str(int(wid))
                        current_wid = getattr(self.mpv, "wid", None)

                        # 如果窗口ID没有变化，不需要重新绑定
                        if current_wid == new_wid:
                            print(f"窗口ID未变化 ({new_wid})，跳过重新绑定")
                            self._rebinding = False
                            return

                        print(f"重新绑定MPV: {current_wid} -> {new_wid}")

                        # 保存当前播放状态
                        was_playing = not getattr(self.mpv, "pause", True)
                        current_pos = getattr(self.mpv, "time_pos", 0) or 0
                        current_vol = getattr(self.mpv, "volume", 80) or 80

                        # 更新窗口ID
                        self.mpv.wid = new_wid

                        # 强制更新
                        self.update()
                        QApplication.processEvents()

                        # 恢复播放状态
                        if was_playing and current_pos > 0:
                            QTimer.singleShot(
                                200, lambda: self._restore_playback_state(current_pos)
                            )

                    except Exception as e:
                        print(f"重新绑定 MPV 失败: {e}")
                        # 如果绑定失败，延迟重试
                        QTimer.singleShot(2000, self._retry_rebind)
                    finally:
                        # 延迟重置绑定标志
                        QTimer.singleShot(
                            1000, lambda: setattr(self, "_rebinding", False)
                        )

                def _retry_rebind(self):
                    """重试重新绑定"""
                    self._rebinding = False
                    self.rebind_mpv()

                def _restore_playback_state(self, position):
                    """恢复播放状态"""
                    try:
                        if hasattr(self, "mpv") and self.mpv:
                            self.mpv.seek(position, reference="absolute")
                    except Exception as e:
                        print(f"恢复播放位置失败: {e}")

                def show_controls(self):
                    """显示控制栏 - 修复版本"""
                    self.control_visible = True
                    if hasattr(self, "control_bar") and self.control_bar:
                        self.control_bar.show()
                        self.control_bar.raise_()
                        self._update_control_bar_geometry()

                    # 全屏时设置自动隐藏
                    if self.state.is_fullscreen:
                        if hasattr(self, "hide_timer"):
                            self.hide_timer.start(3000)

                    self.setCursor(QCursor(Qt.ArrowCursor))

                def auto_hide_controls(self):
                    """自动隐藏控制栏 - 仅在全屏时"""
                    if self.state.is_fullscreen and self.control_visible:
                        self.control_visible = False
                        if hasattr(self, "control_bar") and self.control_bar:
                            self.control_bar.hide()
                        self.setCursor(QCursor(Qt.BlankCursor))

                # 事件处理

                def keyPressEvent(self, event):
                    """键盘事件"""
                    if not self.mpv or not self._initialized:
                        super().keyPressEvent(event)
                        return

                    key = event.key()
                    if key == Qt.Key_Escape and self.state.is_fullscreen:
                        self.exit_fullscreen()
                    elif key == Qt.Key_F or key == Qt.Key_F11:
                        self.toggle_fullscreen()
                    elif key == Qt.Key_Space:
                        self.set_pause(not self.mpv.pause)
                    elif key == Qt.Key_Left:
                        self.mpv.seek(-10, reference="relative")
                        self.status_label.setText("快退 10秒")
                        self.status_label.show()
                        QTimer.singleShot(1000, self.status_label.hide)
                    elif key == Qt.Key_Right:
                        self.mpv.seek(10, reference="relative")
                        self.status_label.setText("快进 10秒")
                        self.status_label.show()
                        QTimer.singleShot(1000, self.status_label.hide)
                    elif key == Qt.Key_Up:
                        new_vol = min(self.mpv.volume + 5, 100)
                        self.set_volume(new_vol)
                    elif key == Qt.Key_Down:
                        new_vol = max(self.mpv.volume - 5, 0)
                        self.set_volume(new_vol)
                    elif key == Qt.Key_M:  # 静音切换
                        current_vol = self.mpv.volume or 0
                        if current_vol > 0:
                            self._last_volume = current_vol
                            self.set_volume(0)
                        else:
                            restore_vol = getattr(self, "_last_volume", 50)
                            self.set_volume(restore_vol)
                    else:
                        super().keyPressEvent(event)

                def show_help_overlay(self):
                    """显示快捷键帮助"""
                    help_text = """
                    快捷键说明：
                    空格 - 播放/暂停
                    F/F11 - 切换全屏
                    ESC - 退出全屏
                    ←/→ - 快进/快退 10秒
                    ↑/↓ - 音量 +/-
                    M - 静音切换
                    H - 显示/隐藏此帮助
                    """
                    QMessageBox.information(self, "快捷键帮助", help_text)

                def mouseDoubleClickEvent(self, event):
                    """鼠标双击事件"""
                    if event.button() == Qt.LeftButton:
                        self.toggle_fullscreen()
                    super().mouseDoubleClickEvent(event)

                # 同时修复鼠标事件处理
                def mouseMoveEvent(self, event):
                    """鼠标移动事件 - 全屏时显示控制栏"""
                    if self.state.is_fullscreen:
                        self.show_controls()
                    super().mouseMoveEvent(event)

                def wheelEvent(self, event):
                    """鼠标滚轮事件"""
                    if self.mpv and self._initialized:
                        delta = event.angleDelta().y()
                        volume_change = 5 if delta > 0 else -5
                        new_volume = max(0, min(100, self.mpv.volume + volume_change))
                        self.set_volume(new_volume)
                    event.accept()

                def toggle_fullscreen(self):
                    """切换全屏状态 - 改进版本"""
                    if self.state.is_fullscreen:
                        self.exit_fullscreen()
                    else:
                        self.enter_fullscreen()

                def closeEvent(self, event):
                    """安全关闭事件"""
                    try:
                        # 停止所有定时器
                        if hasattr(self, "hide_timer"):
                            self.hide_timer.stop()

                        # 清理 MPV
                        if hasattr(self, "mpv") and self.mpv:
                            try:
                                self.mpv.terminate()
                            except:
                                pass
                            self.mpv = None

                        # 清理回调函数
                        self.on_time_update = None
                        self.on_duration_update = None
                        self.on_pause_update = None
                        self.on_volume_update = None
                        self.on_loading_update = None

                    except Exception as e:
                        print(f"MPV 清理出错: {e}")
                    finally:
                        super().closeEvent(event)

            widget = SafeMpvWidget()
            widget.parent_dialog = parent_dialog
            return widget

        except Exception as e:
            print(f"创建 MPV 控件失败: {e}")
            return self.create_fallback_widget()

    def create_fallback_widget(self):
        """创建备用播放器组件"""
        widget = QLabel("未安装 python-mpv，无法播放视频")
        widget.setMinimumSize(800, 450)
        widget.setAlignment(Qt.AlignCenter)
        widget.setStyleSheet(
            """
            background: #000000; 
            color: #ffffff; 
            font-size: 24px; 
            font-weight: bold;
        """
        )
        return widget

    def create_control_bar(self):
        """创建控制栏"""
        control_bar = QFrame()
        control_bar.setObjectName("video_control_bar")
        control_bar.setFixedHeight(70)
        control_bar.setStyleSheet(
            """
            QFrame#video_control_bar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(0,0,0,200), stop:1 rgba(0,0,0,230));
                border: none;
                border-top: 1px solid rgba(255,255,255,20);
            }
            QPushButton {
                background: transparent;
                color: #ffffff;
                font-size: 18px;
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
                min-width: 40px;
                min-height: 40px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255,255,255,30);
            }
            QPushButton:pressed {
                background: rgba(255,255,255,50);
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: rgba(255,255,255,30);
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #00a1d6;
                width: 18px;
                height: 18px;
                border-radius: 9px;
                margin: -6px 0;
                border: 2px solid #ffffff;
            }
            QSlider::handle:horizontal:hover {
                background: #0099cc;
                width: 20px;
                height: 20px;
                border-radius: 10px;
                margin: -7px 0;
            }
            QSlider::sub-page:horizontal {
                background: #00a1d6;
                border-radius: 3px;
            }
            QSlider::add-page:horizontal {
                background: rgba(255,255,255,30);
                border-radius: 3px;
            }
            QLabel {
                color: #ffffff;
                font-size: 14px;
                font-weight: bold;
                padding: 0 8px;
            }
        """
        )

        layout = QHBoxLayout(control_bar)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(15)

        # 播放/暂停按钮
        play_btn = QPushButton("⏸")
        play_btn.setToolTip("播放/暂停 (空格)")
        play_btn.setObjectName("play_button")

        # 时间标签
        current_time = QLabel("00:00")
        current_time.setObjectName("current_time")

        # 进度条
        progress_slider = QSlider(Qt.Horizontal)
        progress_slider.setRange(0, 1000)
        progress_slider.setValue(0)
        progress_slider.setObjectName("progress_slider")
        progress_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # 总时长
        total_time = QLabel("00:00")
        total_time.setObjectName("total_time")

        # 音量按钮
        volume_btn = QPushButton("🔊")
        volume_btn.setToolTip("静音切换")
        volume_btn.setObjectName("volume_button")

        # 音量滑块
        volume_slider = QSlider(Qt.Horizontal)
        volume_slider.setRange(0, 100)
        volume_slider.setValue(80)
        volume_slider.setFixedWidth(100)
        volume_slider.setObjectName("volume_slider")

        # 全屏按钮
        fullscreen_btn = QPushButton("⛶")
        fullscreen_btn.setToolTip("全屏 (F)")
        fullscreen_btn.setObjectName("fullscreen_button")

        # 添加到布局
        layout.addWidget(play_btn)
        layout.addWidget(current_time)
        layout.addWidget(progress_slider, stretch=1)
        layout.addWidget(total_time)
        layout.addWidget(volume_btn)
        layout.addWidget(volume_slider)
        layout.addWidget(fullscreen_btn)

        return control_bar

    def create_info_section(
        self, name, cover_url, intro, year, area, type_str, total_eps, line_names
    ):
        """创建信息区域"""
        info_widget = QFrame()
        info_widget.setStyleSheet(
            """
            QFrame {
                background: #ffffff;
                border: 1px solid #e9ecef;
                border-radius: 12px;
                padding: 20px;
            }
        """
        )
        info_widget.setMaximumWidth(400)
        info_widget.setMinimumWidth(350)  # 设置最小宽度

        layout = QVBoxLayout(info_widget)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 15, 15, 15)  # 设置合适的边距

        # 标题
        title_label = QLabel(name)
        title_label.setStyleSheet(
            """
            QLabel {
                font-size: 20px; 
                font-weight: bold; 
                color: #333333; 
                margin-bottom: 10px;
                background: transparent;
                border: none;
            }
        """
        )
        title_label.setWordWrap(True)
        title_label.setMaximumHeight(80)  # 限制标题高度
        layout.addWidget(title_label)

        # 封面
        cover_label = QLabel()
        cover_label.setFixedSize(200, 280)
        cover_label.setStyleSheet(
            """
            QLabel {
                border: 2px solid #e9ecef; 
                border-radius: 8px;
                background: #f8f9fa;
                color: #666666;
                font-size: 14px;
            }
        """
        )
        cover_label.setAlignment(Qt.AlignCenter)

        if cover_url:
            try:
                img_data = urlopen(cover_url).read()
                pixmap = QPixmap()
                pixmap.loadFromData(img_data)
                pixmap = pixmap.scaled(
                    196, 276, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                cover_label.setPixmap(pixmap)
            except Exception:
                cover_label.setText("封面\n加载失败")
        else:
            cover_label.setText("无封面")

        layout.addWidget(cover_label, alignment=Qt.AlignCenter)

        # 信息表格
        info_container = QFrame()
        info_container.setStyleSheet(
            """
            QFrame {
                background: transparent;
                border: none;
            }
        """
        )
        info_layout = QVBoxLayout(info_container)
        info_layout.setSpacing(8)
        info_layout.setContentsMargins(0, 0, 0, 0)

        info_data = [
            ("年份", year or "未知"),
            ("地区", area or "未知"),
            ("类型", type_str or "未知"),
            ("总集数", total_eps or "未知"),
        ]

        for label_text, value_text in info_data:
            row_widget = QFrame()
            row_widget.setStyleSheet(
                """
                QFrame {
                    background: #f8f9fa;
                    border: 1px solid #e9ecef;
                    border-radius: 6px;
                    padding: 5px;
                }
            """
            )
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(8, 5, 8, 5)
            row_layout.setSpacing(10)

            label = QLabel(f"{label_text}:")
            label.setStyleSheet(
                """
                QLabel {
                    font-weight: bold; 
                    color: #495057; 
                    min-width: 60px;
                    background: transparent;
                    border: none;
                    font-size: 13px;
                }
            """
            )

            value = QLabel(str(value_text))
            value.setStyleSheet(
                """
                QLabel {
                    color: #212529;
                    background: transparent;
                    border: none;
                    font-size: 13px;
                }
            """
            )
            value.setWordWrap(True)

            row_layout.addWidget(label)
            row_layout.addWidget(value, stretch=1)
            info_layout.addWidget(row_widget)

        layout.addWidget(info_container)

        # 线路选择
        if line_names:
            line_container = QFrame()
            line_container.setStyleSheet(
                """
                QFrame {
                    background: transparent;
                    border: none;
                }
            """
            )
            line_layout = QVBoxLayout(line_container)
            line_layout.setSpacing(8)
            line_layout.setContentsMargins(0, 10, 0, 0)

            line_label = QLabel("播放线路:")
            line_label.setStyleSheet(
                """
                QLabel {
                    font-weight: bold; 
                    color: #495057;
                    background: transparent;
                    border: none;
                    font-size: 14px;
                }
            """
            )
            line_layout.addWidget(line_label)

            line_combo = QComboBox()
            line_combo.addItems(line_names)
            line_combo.setObjectName("line_selector")
            line_combo.setStyleSheet(
                """
                QComboBox {
                    font-size: 13px;
                    padding: 8px 12px;
                    border: 2px solid #00a1d6;
                    border-radius: 6px;
                    background: #ffffff;
                    color: #333333;
                    min-height: 20px;
                }
                QComboBox::drop-down {
                    border: none;
                    width: 20px;
                }
                QComboBox::down-arrow {
                    image: none;
                    border-left: 5px solid transparent;
                    border-right: 5px solid transparent;
                    border-top: 8px solid #00a1d6;
                }
                QComboBox QAbstractItemView {
                    background: #ffffff;
                    border: 1px solid #00a1d6;
                    selection-background-color: #e3f1fd;
                    color: #333333;
                }
            """
            )
            line_layout.addWidget(line_combo)
            layout.addWidget(line_container)

        # 简介 - 重点修复这部分
        if intro and intro.strip():
            intro_container = QFrame()
            intro_container.setStyleSheet(
                """
                QFrame {
                    background: transparent;
                    border: none;
                }
            """
            )
            intro_layout = QVBoxLayout(intro_container)
            intro_layout.setSpacing(8)
            intro_layout.setContentsMargins(0, 10, 0, 0)

            intro_label = QLabel("简介:")
            intro_label.setStyleSheet(
                """
                QLabel {
                    font-weight: bold; 
                    color: #495057;
                    background: transparent;
                    border: none;
                    font-size: 14px;
                    margin-bottom: 5px;
                }
            """
            )
            intro_layout.addWidget(intro_label)

            # 创建滚动区域用于简介文本
            intro_scroll = QScrollArea()
            intro_scroll.setWidgetResizable(True)
            intro_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            intro_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            intro_scroll.setFixedHeight(120)  # 固定高度
            intro_scroll.setStyleSheet(
                """
                QScrollArea {
                    border: 1px solid #dee2e6;
                    border-radius: 6px;
                    background: #ffffff;
                }
                QScrollBar:vertical {
                    background: #f8f9fa;
                    width: 8px;
                    border-radius: 4px;
                }
                QScrollBar::handle:vertical {
                    background: #00a1d6;
                    border-radius: 4px;
                    min-height: 20px;
                }
                QScrollBar::handle:vertical:hover {
                    background: #0088cc;
                }
            """
            )

            intro_text = QLabel(intro.strip())
            intro_text.setWordWrap(True)
            intro_text.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            intro_text.setStyleSheet(
                """
                QLabel {
                    color: #212529; 
                    line-height: 1.6;
                    padding: 10px;
                    background: transparent;
                    border: none;
                    font-size: 13px;
                    font-family: 'Microsoft YaHei', sans-serif;
                }
            """
            )
            intro_text.setMinimumHeight(100)  # 设置最小高度
            intro_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            intro_scroll.setWidget(intro_text)
            intro_layout.addWidget(intro_scroll)
            layout.addWidget(intro_container)
        else:
            # 如果没有简介，显示占位文本
            no_intro_label = QLabel("暂无简介")
            no_intro_label.setStyleSheet(
                """
                QLabel {
                    color: #6c757d;
                    font-style: italic;
                    background: transparent;
                    border: none;
                    font-size: 13px;
                    padding: 10px;
                    text-align: center;
                }
            """
            )
            no_intro_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(no_intro_label)

        # 添加弹性空间，但不要太多
        layout.addStretch(1)

        return info_widget

    def create_episode_section(self, episodes):
        """创建分集区域"""
        episode_widget = QFrame()
        episode_widget.setStyleSheet(
            """
            QFrame {
                background: #ffffff;
                border: 1px solid #e9ecef;
                border-radius: 12px;
                padding: 20px;
            }
        """
        )

        layout = QVBoxLayout(episode_widget)
        layout.setSpacing(15)

        # 标题
        title_label = QLabel("选集")
        title_label.setStyleSheet(
            """
            font-size: 18px; 
            font-weight: bold; 
            color: #333333;
            margin-bottom: 10px;
        """
        )
        layout.addWidget(title_label)

        # 滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet(
            """
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                width: 12px;
                background: #f1f1f1;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #00a1d6;
                border-radius: 6px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #0099cc;
            }
            QScrollBar:horizontal {
                height: 12px;
                background: #f1f1f1;
                border-radius: 6px;
            }
            QScrollBar::handle:horizontal {
                background: #00a1d6;
                border-radius: 6px;
                min-width: 30px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #0099cc;
            }
        """
        )

        # 分集容器
        episode_container = QWidget()
        episode_layout = QGridLayout(episode_container)
        episode_layout.setSpacing(8)

        # 创建分集按钮
        episode_buttons = []
        columns = 6  # 每行6个按钮

        for i, (ep_title, play_url, real_url) in enumerate(episodes):
            btn = QPushButton(ep_title)
            btn.setCheckable(True)
            btn.setMinimumSize(120, 50)
            btn.setMaximumSize(150, 60)
            btn.setObjectName(f"episode_button_{i}")
            btn.setStyleSheet(
                """
                QPushButton {
                    background: #ffffff;
                    border: 2px solid #00a1d6;
                    border-radius: 8px;
                    padding: 8px 12px;
                    color: #00a1d6;
                    font-size: 14px;
                    font-weight: bold;
                    text-align: center;
                }
                QPushButton:hover {
                    background: #e3f1fd;
                    border-color: #0088cc;
                }
                QPushButton:checked {
                    background: #00a1d6;
                    color: #ffffff;
                    border-color: #0088cc;
                }
                QPushButton:pressed {
                    background: #0088cc;
                }
            """
            )

            row = i // columns
            col = i % columns
            episode_layout.addWidget(btn, row, col)
            episode_buttons.append(btn)

        scroll_area.setWidget(episode_container)
        layout.addWidget(scroll_area)

        # 保存按钮引用
        episode_widget.episode_buttons = episode_buttons

        return episode_widget

    def setup_video_events(self, video_widget, control_bar, dialog):
        """设置视频播放器事件"""
        # 获取控件引用
        play_btn = control_bar.findChild(QPushButton, "play_button")
        progress_slider = control_bar.findChild(QSlider, "progress_slider")
        current_time_label = control_bar.findChild(QLabel, "current_time")
        total_time_label = control_bar.findChild(QLabel, "total_time")
        volume_btn = control_bar.findChild(QPushButton, "volume_button")
        volume_slider = control_bar.findChild(QSlider, "volume_slider")
        fullscreen_btn = control_bar.findChild(QPushButton, "fullscreen_button")

        if not all(
            [
                play_btn,
                progress_slider,
                current_time_label,
                total_time_label,
                volume_btn,
                volume_slider,
            ]
        ):
            print("Warning: Some control bar elements not found")
            return

        # 添加缺少的函数定义
        def on_slider_pressed():
            video_widget.is_seeking = True

        def update_progress(position):
            if not video_widget.is_seeking and video_widget.duration > 0:
                progress = int((position / video_widget.duration) * 1000)
                progress_slider.setValue(progress)
                current_time_label.setText(format_time(position))

        def update_duration(duration):
            total_time_label.setText(format_time(duration))

        def toggle_play():
            if hasattr(video_widget, "mpv") and video_widget.mpv:
                video_widget.set_pause(not video_widget.mpv.pause)

        def update_play_btn(paused):
            play_btn.setText("▶" if paused else "⏸")

        play_btn.clicked.connect(toggle_play)
        video_widget.on_pause_update = update_play_btn

        # 进度控制
        def format_time(seconds):
            """统一的时间格式化函数"""
            if not seconds:
                return "00:00"
            mins, secs = divmod(int(seconds), 60)
            if mins >= 60:
                hours, mins = divmod(mins, 60)
                return f"{hours:02d}:{mins:02d}:{secs:02d}"
            return f"{mins:02d}:{secs:02d}"

        def on_slider_released():
            if video_widget.duration > 0:
                pos = (progress_slider.value() / 1000) * video_widget.duration
                video_widget.seek_to(pos)
            video_widget.is_seeking = False

        def on_slider_moved(value):
            if video_widget.duration > 0:
                pos = (value / 1000) * video_widget.duration
                current_time_label.setText(format_time(pos))

        progress_slider.sliderPressed.connect(on_slider_pressed)
        progress_slider.sliderReleased.connect(on_slider_released)
        progress_slider.sliderMoved.connect(on_slider_moved)
        video_widget.on_time_update = update_progress
        video_widget.on_duration_update = update_duration

        # 音量控制
        def set_volume(value):
            video_widget.set_volume(value)
            update_volume_icon(value)

        def update_volume_icon(volume):
            if volume == 0:
                volume_btn.setText("🔇")
            elif volume < 30:
                volume_btn.setText("🔈")
            elif volume < 70:
                volume_btn.setText("🔉")
            else:
                volume_btn.setText("🔊")

        def toggle_mute():
            if hasattr(video_widget, "mpv") and video_widget.mpv:
                current_vol = video_widget.mpv.volume or 0
                if current_vol > 0:
                    video_widget._last_volume = current_vol
                    video_widget.set_volume(0)
                    volume_slider.setValue(0)
                else:
                    restore_vol = getattr(video_widget, "_last_volume", 50)
                    video_widget.set_volume(restore_vol)
                    volume_slider.setValue(int(restore_vol))

        volume_slider.valueChanged.connect(set_volume)
        volume_btn.clicked.connect(toggle_mute)

        def on_volume_update(volume):
            volume_slider.setValue(int(volume))
            update_volume_icon(volume)

        video_widget.on_volume_update = on_volume_update

        # 全屏按钮
        if fullscreen_btn:
            fullscreen_btn.clicked.connect(video_widget.toggle_fullscreen)

        def show_loading(loading):
            # 这里可以添加加载指示器的逻辑
            pass

        video_widget.on_loading_update = show_loading

    def setup_episode_events(self, video_widget, episode_section, eps):
        """设置分集事件 - 在当前播放器中播放"""

        def on_episode_clicked(ep_idx_clicked):
            ep_btns = episode_section.episode_buttons  # 在函数内部获取

            # 更新按钮选中状态
            for i, btn_ep in enumerate(ep_btns):
                btn_ep.setChecked(i == ep_idx_clicked)

            # 在当前播放器中播放视频
            if eps and 0 <= ep_idx_clicked < len(eps):
                episode_title, play_url, real_video_url = eps[ep_idx_clicked]

                # 确保视频控件存在且MPV已初始化
                if hasattr(video_widget, "mpv") and video_widget.mpv:
                    try:
                        # 显示加载状态
                        if (
                            hasattr(video_widget, "on_loading_update")
                            and video_widget.on_loading_update
                        ):
                            video_widget.on_loading_update(True)

                        # 播放视频
                        print(f"播放第 {ep_idx_clicked + 1} 集: {episode_title}")
                        print(f"视频链接: {real_video_url}")

                        video_widget.play(real_video_url)

                        # 更新窗口标题（如果有父对话框）
                        if (
                            hasattr(video_widget, "parent_dialog")
                            and video_widget.parent_dialog
                        ):
                            original_title = video_widget.parent_dialog.windowTitle()
                            if " - " in original_title:
                                anime_name = original_title.split(" - ")[0]
                            else:
                                anime_name = original_title
                            video_widget.parent_dialog.setWindowTitle(
                                f"{anime_name} - {episode_title}"
                            )

                    except Exception as e:
                        print(f"播放失败: {e}")
                        QMessageBox.warning(video_widget, "播放错误", f"播放失败: {e}")
                        if (
                            hasattr(video_widget, "on_loading_update")
                            and video_widget.on_loading_update
                        ):
                            video_widget.on_loading_update(False)
                else:
                    QMessageBox.warning(
                        video_widget, "播放器错误", "播放器未就绪，请稍后再试"
                    )

        def create_episode_handler(episode_idx_handler):
            return lambda checked=False: on_episode_clicked(episode_idx_handler)

        # 绑定所有分集按钮的点击事件
        ep_btns = episode_section.episode_buttons
        for i_btn, btn_item in enumerate(ep_btns):
            btn_item.clicked.connect(create_episode_handler(i_btn))

        # 默认播放第一集
        if eps and ep_btns:  # 确保都不为空
            ep_btns[0].setChecked(True)

            # 延迟播放第一集，确保MPV已完全初始化
            def play_first_episode():
                if hasattr(video_widget, "mpv") and video_widget.mpv:
                    try:
                        first_episode = eps[0]
                        print(f"自动播放第一集: {first_episode[0]}")
                        video_widget.play(first_episode[2])

                        # 设置初始音量
                        if hasattr(video_widget, "parent_dialog"):
                            dialog = video_widget.parent_dialog
                            volume_slider = dialog.findChild(QSlider, "volume_slider")
                            if volume_slider:
                                video_widget.set_volume(volume_slider.value())

                    except Exception as e:
                        print(f"自动播放第一集失败: {e}")

            # 延迟2秒后播放，确保MPV完全初始化
            QTimer.singleShot(2000, play_first_episode)

    def setup_line_events(
        self, video_widget, info_section, anime_id, lines, episode_section
    ):
        """设置线路切换事件 - PySide6版本"""
        import sqlite3

        line_combo = info_section.findChild(QComboBox, "line_selector")
        if not line_combo:
            return

        def change_line(line_idx_changed):
            if 0 <= line_idx_changed < len(lines):
                line_id = lines[line_idx_changed]

                try:
                    with sqlite3.connect("anime.db") as conn:
                        c = conn.cursor()
                        c.execute(
                            "SELECT title, play_url, real_video_url FROM episode WHERE anime_id=? AND line_id=? ORDER BY id",
                            (anime_id, line_id),
                        )
                        new_eps = c.fetchall()
                except Exception as e:
                    print(f"数据库查询失败: {e}")
                    return

                # 获取分集容器
                scroll_area = episode_section.findChild(QScrollArea)
                if not scroll_area:
                    return

                episode_container = scroll_area.widget()
                if not episode_container:
                    return

                episode_layout = episode_container.layout()
                if not episode_layout:
                    return

                # 清理旧按钮
                old_buttons = getattr(episode_section, "episode_buttons", [])
                for btn_old in old_buttons:
                    btn_old.setParent(None)
                    btn_old.deleteLater()

                # 创建新按钮列表
                new_buttons = []
                columns = 5

                # 创建新按钮
                for i_new_ep, (ep_title_new, play_url_new, real_url_new) in enumerate(
                    new_eps
                ):
                    btn_new = QPushButton(ep_title_new)
                    btn_new.setCheckable(True)
                    btn_new.setMinimumSize(100, 40)
                    btn_new.setMaximumSize(150, 50)
                    btn_new.setObjectName(f"episode_button_{i_new_ep}")
                    btn_new.setStyleSheet(
                        """
                        QPushButton {
                            background: #ffffff;
                            border: 2px solid #00a1d6;
                            border-radius: 6px;
                            padding: 6px 10px;
                            color: #00a1d6;
                            font-size: 12px;
                            font-weight: bold;
                            text-align: center;
                        }
                        QPushButton:hover {
                            background: #e3f1fd;
                            border-color: #0088cc;
                        }
                        QPushButton:checked {
                            background: #00a1d6;
                            color: #ffffff;
                            border-color: #0088cc;
                        }
                        QPushButton:pressed {
                            background: #0088cc;
                        }
                    """
                    )

                    # 绑定点击事件
                    def create_episode_handler(ep_idx):
                        def on_episode_clicked():
                            # 更新按钮状态
                            for j, btn in enumerate(new_buttons):
                                btn.setChecked(j == ep_idx)
                            # 播放视频
                            if 0 <= ep_idx < len(new_eps):
                                video_widget.play(new_eps[ep_idx][2])

                        return on_episode_clicked

                    btn_new.clicked.connect(create_episode_handler(i_new_ep))

                    # 添加到布局
                    row = i_new_ep // columns
                    col = i_new_ep % columns
                    episode_layout.addWidget(btn_new, row, col)
                    new_buttons.append(btn_new)

                # 更新 episode_section 的按钮引用
                episode_section.episode_buttons = new_buttons

                # 默认选中第一集并播放
                if new_eps and new_buttons:
                    new_buttons[0].setChecked(True)
                    video_widget.play(new_eps[0][2])

        # 连接信号 - PySide6语法
        line_combo.currentIndexChanged.connect(change_line)

    def setup_state_management(
        self, video_widget, anime_id, info_section, episode_section
    ):
        """设置播放状态管理"""
        import sqlite3  # 添加导入

        state_file = f"anime_state_{anime_id}.json"

        line_combo = info_section.findChild(QComboBox, "line_selector")

        def save_state():
            try:
                if not (hasattr(video_widget, "mpv") and video_widget.mpv):
                    return

                # 获取当前选中的分集
                ep_btns = getattr(episode_section, "episode_buttons", [])
                current_ep_idx = next(
                    (i for i, b in enumerate(ep_btns) if b.isChecked()), 0
                )

                state = {
                    "anime_id": anime_id,
                    "line_idx": line_combo.currentIndex() if line_combo else 0,
                    "ep_idx": current_ep_idx,
                    "position": video_widget.mpv.time_pos or 0,
                    "volume": video_widget.mpv.volume or 80,
                }
                with open(state_file, "w", encoding="utf-8") as f:
                    json.dump(state, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"保存状态失败: {e}")

        def load_state():
            try:
                if not (hasattr(video_widget, "mpv") and video_widget.mpv):
                    return False

                if not os.path.exists(state_file):
                    return False

                with open(state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)

                # 恢复线路选择
                if line_combo:
                    line_idx = state.get("line_idx", 0)
                    if 0 <= line_idx < line_combo.count():
                        line_combo.setCurrentIndex(line_idx)

                # 恢复音量
                dialog = (
                    video_widget.parent_dialog
                    if hasattr(video_widget, "parent_dialog")
                    else None
                )
                if dialog:
                    volume_slider = dialog.findChild(QSlider, "volume_slider")
                    if volume_slider:
                        vol = int(state.get("volume", 80))
                        volume_slider.setValue(vol)
                        video_widget.set_volume(vol)

                # 恢复分集选择
                ep_btns = getattr(episode_section, "episode_buttons", [])
                ep_idx = state.get("ep_idx", 0)
                if 0 <= ep_idx < len(ep_btns):
                    ep_btns[ep_idx].setChecked(True)

                    # 改进跳转逻辑 - 等待视频加载完成后再跳转
                    pos = state.get("position", 0)
                    if pos > 5:  # 只有超过5秒才跳转，避免频繁的小幅跳转

                        def try_seek():
                            if hasattr(video_widget, "mpv") and video_widget.mpv:
                                # 检查视频是否已经加载
                                if (
                                    hasattr(video_widget.mpv, "duration")
                                    and video_widget.mpv.duration
                                ):
                                    video_widget.seek_to(pos)
                                else:
                                    # 如果还没加载完成，再等1秒
                                    QTimer.singleShot(1000, try_seek)

                        # 延迟跳转，给视频更多时间加载
                        QTimer.singleShot(3000, try_seek)

                return True

            except Exception as e:
                print(f"加载状态失败: {e}")
                return False

        # 尝试加载状态
        if not load_state():
            # 如果加载失败，播放第一集
            ep_btns = getattr(episode_section, "episode_buttons", [])
            if ep_btns:
                ep_btns[0].setChecked(True)

        def on_dialog_close():
            save_state()
            try:
                if hasattr(video_widget, "mpv") and video_widget.mpv:
                    video_widget.mpv.terminate()
            except Exception as e:
                print(f"关闭 MPV 出错: {e}")

        # 修复关闭事件处理
        def safe_close_event(event):
            try:
                on_dialog_close()
            except Exception as e:
                print(f"关闭时出错: {e}")
            finally:
                event.accept()

        # 获取对话框并设置关闭事件
        dialog = (
            video_widget.parent_dialog
            if hasattr(video_widget, "parent_dialog")
            else None
        )
        if dialog:
            dialog.closeEvent = safe_close_event

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

        content.addSpacerItem(
            QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding)
        )

        # 清晰度选择
        self.quality_box = QComboBox()
        self.quality_box.addItems(["自动(最高)", "仅视频", "仅音频"])
        content.addWidget(self.quality_box)

        # 下载按钮
        self.download_btn = QPushButton("开始下载")
        self.download_btn.setIcon(QIcon("download.png"))
        self.download_btn.setIconSize(QSize(20, 20))
        self.download_btn.clicked.connect(self.on_click_download)
        self.download_btn.pressed.connect(
            lambda: self.animate_button(self.download_btn, 0.95)
        )
        self.download_btn.released.connect(
            lambda: self.animate_button(self.download_btn, 1.0)
        )
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

    def prev_page(self):
        """上一页"""
        if not hasattr(self, "current_page"):
            self.current_page = 1

        if self.current_page > 1:
            self.current_page -= 1
            self.load_anime_data()
            self.update_page_buttons()

    def next_page(self):
        """下一页"""
        if not hasattr(self, "current_page"):
            self.current_page = 1

        if not hasattr(self, "total_pages"):
            self.total_pages = 1

        # 只有当前页小于总页数时才允许翻页
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.load_anime_data()

    def update_page_buttons(self):
        """更新分页按钮状态"""
        if hasattr(self, "prev_btn"):
            self.prev_btn.setEnabled(getattr(self, "current_page", 1) > 1)

        if hasattr(self, "next_btn"):
            current_page = getattr(self, "current_page", 1)
            total_pages = getattr(self, "total_pages", 1)
            self.next_btn.setEnabled(current_page < total_pages)

    def search_anime(self):
        """搜索动漫"""
        search_text = self.anime_search.text().strip()

        # 使用定时器延迟搜索，避免频繁请求
        if hasattr(self, "search_timer"):
            self.search_timer.stop()

        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(lambda: self.perform_search(search_text))
        self.search_timer.start(300)  # 300ms 延迟

    def perform_search(self, search_text):
        """执行搜索"""
        self.current_page = 1  # 重置到第一页
        self.current_search = search_text
        self.load_anime_data()

    def load_anime_data(self):
        """加载动漫数据 - 修复线程管理"""
        if self._is_closing:  # 如果正在关闭，不启动新线程
            return

        from PySide6.QtCore import QThread, Signal

        # 显示加载状态
        self.show_loading_state()

        # 如果有正在运行的加载线程，先停止它
        if hasattr(self, "loader_thread") and self.loader_thread.isRunning():
            self.loader_thread.quit()
            self.loader_thread.wait(1000)

        # 创建新的加载线程
        class AnimeLoader(QThread):
            data_loaded = Signal(list, int)
            error_occurred = Signal(str)

            def __init__(self, page=1, search_text="", parent=None):
                super().__init__(parent)
                self.page = page
                self.search_text = search_text
                self.is_cancelled = False

            def run(self):
                if self.is_cancelled:
                    return

                try:
                    import sqlite3
                    import os

                    # 检查数据库文件是否存在
                    if not os.path.exists("anime.db"):
                        if not self.is_cancelled:
                            self.error_occurred.emit("数据库文件不存在")
                        return

                    conn = sqlite3.connect("anime.db")
                    c = conn.cursor()

                    # 分页参数
                    page_size = 20
                    offset = (self.page - 1) * page_size

                    if self.is_cancelled:
                        conn.close()
                        return

                    # 首先查询总数
                    if self.search_text:
                        c.execute(
                            "SELECT COUNT(*) FROM anime WHERE name LIKE ?",
                            (f"%{self.search_text}%",),
                        )
                    else:
                        c.execute("SELECT COUNT(*) FROM anime")

                    total_count = c.fetchone()[0]

                    if self.is_cancelled:
                        conn.close()
                        return

                    # 然后查询当前页数据
                    if self.search_text:
                        c.execute(
                            """
                            SELECT DISTINCT id, name, cover, intro 
                            FROM anime 
                            WHERE name LIKE ? 
                            ORDER BY id 
                            LIMIT ? OFFSET ?
                        """,
                            (f"%{self.search_text}%", page_size, offset),
                        )
                    else:
                        c.execute(
                            """
                            SELECT DISTINCT id, name, cover, intro 
                            FROM anime 
                            ORDER BY id 
                            LIMIT ? OFFSET ?
                        """,
                            (page_size, offset),
                        )

                    results = c.fetchall()
                    conn.close()

                    if not self.is_cancelled:
                        self.data_loaded.emit(results, total_count)

                except Exception as e:
                    if not self.is_cancelled:
                        self.error_occurred.emit(f"数据库查询失败: {str(e)}")

            def cancel(self):
                self.is_cancelled = True

        # 初始化分页变量
        if not hasattr(self, "current_page"):
            self.current_page = 1

        # 创建并启动加载线程
        search_text = getattr(self, "current_search", "")
        self.loader_thread = AnimeLoader(self.current_page, search_text, self)

        # 连接信号
        self.loader_thread.data_loaded.connect(self.on_anime_data_loaded)
        self.loader_thread.error_occurred.connect(self.on_load_error)

        # 添加到活动线程列表
        self.active_threads.append(self.loader_thread)

        # 线程完成时从列表中移除
        def on_thread_finished():
            if self.loader_thread in self.active_threads:
                self.active_threads.remove(self.loader_thread)

        self.loader_thread.finished.connect(on_thread_finished)
        self.loader_thread.start()

    def show_loading_state(self):
        """显示加载状态"""

        # 检查容器是否存在
        if not hasattr(self, "anime_container") or not self.anime_container:
            return

        # 清除现有内容
        layout = self.anime_container.layout()
        if layout:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
        else:
            layout = QVBoxLayout()  # 修复这里
            self.anime_container.setLayout(layout)  # 设置布局

        # 添加加载标签
        loading_label = QLabel("加载中...")
        loading_label.setAlignment(Qt.AlignCenter)
        loading_label.setFont(QFont("Microsoft YaHei", 16))
        loading_label.setStyleSheet(
            """
            QLabel {
                color: #00a1d6;
                background: transparent;
                padding: 50px;
                min-height: 200px;
            }
        """
        )

        layout.addWidget(loading_label)
        layout.setAlignment(Qt.AlignCenter)

    def on_anime_data_loaded(self, anime_list, total_count):
        """动漫数据加载完成回调"""
        # 计算总页数
        page_size = 20
        self.total_pages = (total_count + page_size - 1) // page_size  # 向上取整

        self.display_anime_grid(anime_list)
        self.update_page_buttons()

    def on_load_error(self, error_msg):
        """加载错误处理回调"""

        if not hasattr(self, "anime_container") or not self.anime_container:
            return

        # 清除现有内容
        layout = self.anime_container.layout()
        if layout:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
        else:
            layout = QVBoxLayout()  # 修复这里
            self.anime_container.setLayout(layout)  # 设置布局

        # 显示错误信息
        error_label = QLabel(f"加载失败: {error_msg}")
        error_label.setAlignment(Qt.AlignCenter)
        error_label.setFont(QFont("Microsoft YaHei", 14))
        error_label.setStyleSheet(
            """
            QLabel {
                color: #ff4444;
                background: transparent;
                padding: 50px;
                min-height: 200px;
            }
        """
        )

        layout.addWidget(error_label)
        layout.setAlignment(Qt.AlignCenter)

    def display_anime_grid(self, anime_list):
        """显示动漫网格"""

        if not hasattr(self, "anime_container") or not self.anime_container:
            return

        # 清除现有内容
        layout = self.anime_container.layout()
        if layout:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
        else:
            layout = QVBoxLayout()  # 修复这里
            self.anime_container.setLayout(layout)
            layout.setAlignment(Qt.AlignTop)

        if not anime_list:
            # 没有数据时显示提示
            no_data_label = QLabel(
                "暂无数据"
                if not hasattr(self, "current_search") or not self.current_search
                else "未找到相关动漫"
            )
            no_data_label.setAlignment(Qt.AlignCenter)
            no_data_label.setFont(QFont("Microsoft YaHei", 14))
            no_data_label.setStyleSheet(
                """
                QLabel {
                    color: #666666;
                    background: transparent;
                    padding: 50px;
                    min-height: 200px;
                }
            """
            )
            layout.addWidget(no_data_label)
            return

        # 保存数据供详情页使用
        self._db_anime_data = [(item[0], item[1], item[2]) for item in anime_list]

        # 创建网格布局
        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setSpacing(15)  # 减少间距
        grid_layout.setContentsMargins(10, 10, 10, 10)  # 减少边距

        # 每行显示4个，确保有足够空间
        columns = 4

        for i, (anime_id, name, cover_url, intro) in enumerate(anime_list):
            row = i // columns
            col = i % columns

            # 创建动漫卡片
            card = self.create_anime_card(anime_id, name, cover_url, intro)
            grid_layout.addWidget(card, row, col)

        # 设置列拉伸，确保均匀分布
        for col in range(columns):
            grid_layout.setColumnStretch(col, 1)

        layout.addWidget(grid_widget)

    def create_anime_card(self, anime_id, name, cover_url, intro):
        """创建动漫卡片 - 修复图片加载线程管理"""
        from urllib.request import urlopen
        import weakref

        if self._is_closing:  # 如果正在关闭，不创建新卡片
            return QWidget()

        card = QWidget()
        card.setFixedSize(200, 280)
        card.setStyleSheet(
            """
            QWidget {
                background: white;
                border-radius: 10px;
                border: 1px solid #e0e0e0;
            }
            QWidget:hover {
                border-color: #00a1d6;
            }
        """
        )

        layout = QVBoxLayout()
        card.setLayout(layout)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        # 封面图片
        poster_label = QLabel()
        poster_label.setFixedSize(180, 200)
        poster_label.setAlignment(Qt.AlignCenter)
        poster_label.setStyleSheet(
            "border: 1px solid #ddd; border-radius: 5px; background: #f5f5f5;"
        )
        poster_label.setText("加载中...")

        layout.addWidget(poster_label)

        # 异步加载图片 - 修复线程管理
        class ImageLoader(QThread):
            image_loaded = Signal(QPixmap)
            load_failed = Signal()

            def __init__(self, url, label_ref, parent_ref):
                super().__init__()
                self.url = url
                self.label_ref = label_ref
                self.parent_ref = parent_ref  # 保存父组件引用
                self.is_cancelled = False

            def run(self):
                try:
                    # 检查父组件是否还存在
                    parent = self.parent_ref()
                    if not parent or parent._is_closing:
                        return

                    if self.is_cancelled or not self.url or not self.url.strip():
                        if not self.is_cancelled:
                            self.load_failed.emit()
                        return

                    import urllib.request

                    req = urllib.request.Request(
                        self.url,
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                            "Referer": "https://www.bilibili.com/",
                            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                        },
                    )

                    with urllib.request.urlopen(req, timeout=10) as response:
                        img_data = response.read()

                    if self.is_cancelled:
                        return

                    pixmap = QPixmap()
                    if pixmap.loadFromData(img_data):
                        scaled_pixmap = pixmap.scaled(
                            176, 196, Qt.KeepAspectRatio, Qt.SmoothTransformation
                        )
                        if not self.is_cancelled:
                            self.image_loaded.emit(scaled_pixmap)
                    else:
                        if not self.is_cancelled:
                            self.load_failed.emit()

                except Exception as e:
                    print(f"加载图片失败: {e}")
                    if not self.is_cancelled:
                        self.load_failed.emit()

            def cancel(self):
                self.is_cancelled = True

        def on_image_loaded(pixmap):
            label = poster_label_ref()
            if label is not None:
                try:
                    label.setPixmap(pixmap)
                    label.setText("")
                except RuntimeError:
                    pass

        def on_load_failed():
            label = poster_label_ref()
            if label is not None:
                try:
                    label.setText("无封面")
                    original_style = label.styleSheet()
                    if "color:" not in original_style:
                        label.setStyleSheet(original_style + "color: #999;")
                except RuntimeError:
                    pass

        if cover_url and not self._is_closing:
            poster_label_ref = weakref.ref(poster_label)
            parent_ref = weakref.ref(self)  # 创建父组件弱引用

            loader = ImageLoader(cover_url, poster_label_ref, parent_ref)
            loader.image_loaded.connect(on_image_loaded)
            loader.load_failed.connect(on_load_failed)

            # 添加到活动线程列表
            self.active_threads.append(loader)

            # 线程完成时清理
            def on_loader_finished():
                if loader in self.active_threads:
                    self.active_threads.remove(loader)

            loader.finished.connect(on_loader_finished)
            loader.start()

            # 保存引用并添加清理机制
            poster_label._image_loader = loader

            # 当卡片被删除时，取消加载线程
            def cleanup():
                if hasattr(poster_label, "_image_loader"):
                    poster_label._image_loader.cancel()
                    poster_label._image_loader.quit()
                    poster_label._image_loader.wait(1000)

            # 重写 card 的 closeEvent
            original_close_event = card.closeEvent

            def enhanced_close_event(event):
                cleanup()
                if original_close_event:
                    original_close_event(event)
                else:
                    event.accept()

            card.closeEvent = enhanced_close_event

        else:
            on_load_failed()

        # 标题
        title_label = QLabel(name)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        title_label.setWordWrap(True)
        title_label.setMaximumHeight(40)
        title_label.setStyleSheet("color: #333; border: none;")
        layout.addWidget(title_label)

        # 点击事件
        def on_card_clicked():
            if hasattr(self, "_db_anime_data"):
                for idx, (aid, aname, acover) in enumerate(self._db_anime_data):
                    if aid == anime_id:
                        self.show_anime_detail(idx)
                        break

        card.mousePressEvent = lambda event: on_card_clicked()
        card.setCursor(Qt.PointingHandCursor)

        return card

    def get_quality_format(self):
        idx = self.quality_box.currentIndex()
        return ["bv*+ba", "bv*", "ba"][idx]

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
                    pixmap = pixmap.scaledToHeight(
                        self.cover_label.height(), Qt.SmoothTransformation
                    )
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
        inputs = re.split(r"[\s,]+", bv_input.strip())
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
                ydl_opts = {"quiet": True, "skip_download": True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info_dict = ydl.extract_info(bv_url, download=False)
                    # 如果是多P合集
                    if "entries" in info_dict:
                        for entry in info_dict["entries"]:
                            all_videos.append(
                                {
                                    "title": entry.get("title", "未知标题"),
                                    "thumbnail": entry.get("thumbnail", None),
                                    "url": entry.get("webpage_url", bv_url),
                                    "uploader": entry.get("uploader", ""),
                                    "upload_date": entry.get("upload_date", ""),
                                }
                            )
                    else:
                        all_videos.append(
                            {
                                "title": info_dict.get("title", "未知标题"),
                                "thumbnail": info_dict.get("thumbnail", None),
                                "url": bv_url,
                                "uploader": info_dict.get("uploader", ""),
                                "upload_date": info_dict.get("upload_date", ""),
                            }
                        )
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
                "format": self.get_quality_format(),
                "outtmpl": os.path.join(self.download_path, f"{safe_title}.%(ext)s"),
                "merge_output_format": "mp4",
                "noplaylist": True,
                "progress_hooks": [self.update_progress],
                "quiet": True,
            }
            if getattr(self, "proxy_url", ""):
                ydl_opts["proxy"] = self.proxy_url
            self.download_queue.append(
                (title, "下载中" if self.is_cn else "Downloading")
            )
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
                            self.download_queue[i] = (
                                t,
                                "已完成" if self.s_cn else "Finished",
                            )
                    self.download_history.append(
                        {
                            "title": title,
                            "url": info["url"],
                            "status": "success",
                        }
                    )
                    self.save_history()
                    break  # 成功则退出重试循环
                except Exception as e:
                    retry += 1
                    if retry >= max_retry:
                        for i, (t, s) in enumerate(self.download_queue):
                            if t == title:
                                self.download_queue[i] = (
                                    t,
                                    "失败" if self.is_cn else "Failed",
                                )
                        self.signals.error.emit(f"下载失败: {e}")
                        self.download_history.append(
                            {
                                "title": title,
                                "url": info["url"],
                                "status": "failed",
                                "error": str(e),
                            }
                        )
                        self.save_history()

    def update_progress(self, d):
        if self._cancel_download:
            raise Exception("用户取消下载")
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            speed = d.get("speed", 0)
            eta = d.get("eta", 0)
            if total:
                percentage = downloaded / total * 100
                self.signals.progress.emit(percentage)
                # 显示详细进度
                speed_str = f"{speed/1024:.1f} KB/s" if speed else "--"
                eta_str = f"{int(eta//60)}:{int(eta % 60):02d}" if eta else "--"
                self.progress_bar.setFormat(
                    f"{percentage:.1f}%  {speed_str}  剩余:{eta_str}"
                )
        elif d["status"] == "finished":
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
        video_files = [
            f
            for f in os.listdir(self.download_path)
            if f.lower().endswith((".mp4", ".flv", ".mkv", ".avi", ".mov"))
        ]
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

        # 播放器 - PySide6版本
        player = QMediaPlayer(dialog)
        player.setVideoOutput(video_widget)

        def play_selected():
            row = list_widget.currentRow()
            if row >= 0:
                path = os.path.join(self.download_path, list_widget.item(row).text())
                # PySide6 方式设置媒体源
                player.setSource(QUrl.fromLocalFile(path))
                player.play()

        play_btn.clicked.connect(play_selected)
        list_widget.itemDoubleClicked.connect(play_selected)
        pause_btn.clicked.connect(player.pause)
        stop_btn.clicked.connect(player.stop)

        dialog.setLayout(layout)
        dialog.exec()  # PySide6中去掉了下划线

    def on_download_error(self, msg):
        reply = QMessageBox.critical(
            self, "错误", msg + "\n是否重试？", QMessageBox.Retry | QMessageBox.Cancel
        )
        if reply == QMessageBox.Retry:
            self.on_click_download()

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
        dialog.exec()

    def check_clipboard(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if text and text != self.last_clipboard:
            # 检测B站链接或BV号
            if re.match(
                r"^(https?://www\.bilibili\.com/video/|BV[0-9A-Za-z]{10,})", text
            ):
                self.last_clipboard = text
                reply = QMessageBox.question(
                    self,
                    "检测到B站链接" if self.is_cn else "Bilibili Link Detected",
                    (
                        f"检测到剪贴板有B站链接：\n{text}\n是否一键下载？"
                        if self.is_cn
                        else f"Detected Bilibili link in clipboard:\n{text}\nDownload now?"
                    ),
                    QMessageBox.Yes | QMessageBox.No,
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
        preview_slider.setStyleSheet(
            """
            QSlider::groove:horizontal {height: 6px; background: #e3f1fd;}
            QSlider::handle:horizontal {background: #00a1d6; width: 12px; border-radius: 6px;}
            QSlider::sub-page:horizontal {background: #00a1d6;}
            QSlider::add-page:horizontal {background: rgba(255,255,255,30);}
        """
        )
        downloaded_layout.addWidget(preview_slider)

        # 时间标签
        time_label = QLabel("00:00 / 00:00")
        time_label.setAlignment(Qt.AlignCenter)
        time_label.setStyleSheet("color:#666;font-size:13px;")
        downloaded_layout.addWidget(time_label)

        # 播放器
        player = QMediaPlayer(dialog)
        #     创建音频输出
        audio_output = QAudioOutput()
        player.setAudioOutput(audio_output)
        # 设置静音
        audio_output.setMuted(True)
        player.setVideoOutput(video_widget)

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
                time_label.setText(
                    f"{format_time(player.position())} / {format_time(dur)}"
                )
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
        video_files = [
            f
            for f in files
            if f.lower().endswith((".mp4", ".flv", ".mkv", ".avi", ".mov"))
        ]
        self._video_items = []
        for f in video_files:
            item = QListWidgetItem(f)
            thumb_path = os.path.join("download", f + ".jpg")
            video_path = os.path.join("download", f)
            if not os.path.exists(thumb_path):
                try:
                    os.system(
                        f'ffmpeg -y -i "{video_path}" -ss 00:00:01 -vframes 1 "{thumb_path}" >nul  2>nul'
                    )
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
        open_folder_btn.clicked.connect(
            lambda: os.startfile(os.path.abspath("download"))
        )
        downloaded_layout.addWidget(open_folder_btn)

        # 分类选择
        folders = [
            f
            for f in os.listdir("download")
            if os.path.isdir(os.path.join("download", f))
        ]
        folders.insert(0, "全部" if self.is_cn else "All")
        folder_box = QComboBox()
        folder_box.addItems(folders)
        downloaded_layout.addWidget(folder_box)

        def refresh_video_list():
            list_widget.clear()
            self._video_items.clear()
            selected_folder = folder_box.currentText()
            if selected_folder == ("全部" if self.is_cn else "All"):
                search_dirs = [
                    os.path.join("download", f)
                    for f in os.listdir("download")
                    if os.path.isdir(os.path.join("download", f))
                ]
                search_dirs.append("download")
            else:
                search_dirs = [os.path.join("download", selected_folder)]
            video_files = []
            for d in search_dirs:
                for f in os.listdir(d):
                    if f.lower().endswith((".mp4", ".flv", ".mkv", ".avi", ".mov")):
                        video_files.append(os.path.join(d, f))
            for path in video_files:
                name = os.path.basename(path)
                item = QListWidgetItem(name)
                thumb_path = path + ".jpg"
                if not os.path.exists(thumb_path):
                    os.system(
                        f'ffmpeg -y -i "{path}" -ss 00:00:01 -vframes 1 "{thumb_path}" >nul 2>nul'
                    )
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
                            path = os.path.abspath(
                                os.path.join("download", item.text())
                            )
                            url = QUrl.fromLocalFile(path)
                            player.setSource(url)
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
        dialog.exec()

    def toggle_theme(self):
        self.is_dark = not self.is_dark
        self.setStyleSheet(self.get_stylesheet())

    def closeEvent(self, event):
        """关闭事件 - 修复线程清理"""
        try:
            # 设置关闭标志
            self._is_closing = True

            # 停止剪贴板监控
            if hasattr(self, "clipboard_timer"):
                self.clipboard_timer.stop()

            # 清理所有活动线程
            for thread in self.active_threads[:]:  # 使用副本避免修改列表时的问题
                if thread and thread.isRunning():
                    thread.quit()
                    if not thread.wait(3000):  # 等待3秒
                        thread.terminate()  # 强制终止
                        thread.wait(1000)  # 再等1秒
                    self.active_threads.remove(thread)

            # 清理动漫加载线程
            if hasattr(self, "loader_thread") and self.loader_thread.isRunning():
                self.loader_thread.quit()
                if not self.loader_thread.wait(3000):
                    self.loader_thread.terminate()
                    self.loader_thread.wait(1000)

            # 清理线程池
            if hasattr(self, "executor"):
                self.executor.shutdown(wait=True)

            # 停止所有定时器
            if hasattr(self, "hide_timer"):
                self.hide_timer.stop()

            # 清理 MPV
            if hasattr(self, "mpv") and self.mpv:
                try:
                    # 保存当前状态
                    if hasattr(self, "state") and self.state:
                        self.state.last_position = getattr(self.mpv, "time_pos", 0) or 0
                        self.state.volume = getattr(self.mpv, "volume", 80) or 80
                        self.state.is_paused = getattr(self.mpv, "pause", True)

                    # 停止播放并清理
                    self.mpv.quit()
                    self.mpv = None
                except Exception as e:
                    print(f"MPV 清理出错: {e}")

            # 清理回调函数
            self.on_time_update = None
            self.on_duration_update = None
            self.on_pause_update = None
            self.on_volume_update = None
            self.on_loading_update = None

        except Exception as e:
            print(f"关闭时清理出错: {e}")
        finally:
            event.accept()

    def toggle_lang(self):
        self.is_cn = not self.is_cn
        # 顶部按钮
        self.theme_btn.setText(
            "切换主题" if self.is_cn else "Toggle Theme"
        )  # ← 增加这一行
        self.lang_btn.setText("English" if self.is_cn else "中文")
        self.settings_btn.setText("设置" if self.is_cn else "Settings")
        self.download_manager_btn.setText("下载管理" if self.is_cn else "Manager")
        self.setWindowTitle(
            "Bilibili 视频下载器" if self.is_cn else "Bilibili Downloader"
        )
        # 主界面标签
        self.label_bv.setText(
            "请输入 Bilibili 视频 BV 号 或 完整 URL："
            if self.is_cn
            else "Enter Bilibili BV or full URL:"
        )
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
                "stylesheet": self.get_stylesheet(),  # 使用当前默认样式
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
                QProgressBar { background: #2d3540; }
                QSlider::handle:horizontal { background: #00a1d6; }
                """,
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
                QProgressBar { background: #ffe6f6; }
                QSlider::handle:horizontal { background: #fb7299; }
                """,
            },
        ]
        theme_list.clear()
        for theme in themes:
            item = QListWidgetItem(
                f"{theme['name']} - 作者: {theme['author']} (下载: {theme['downloads']})"
            )
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
        dialog.exec()

    def download_theme(self, theme_name):
        try:
            # 这里应该是下载主题的代码
            QMessageBox.information(self, "提示", f"主题 {theme_name} 下载成功！")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"下载主题失败: {e}")

    def upload_theme(self):

        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择主题文件", "", "主题文件 (*.theme)"
        )
        if file_path:
            try:
                # 这里应该是上传主题的代码
                QMessageBox.information(self, "提示", "主题上传成功！")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"上传主题失败: {e}")

    def import_theme(self):

        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择主题文件", "", "主题文件 (*.theme)"
        )
        if file_path:
            try:
                # 这里应该是导入主题的代码
                QMessageBox.information(self, "提示", "主题导入成功！")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"导入主题失败：{e}")

    def export_theme(self):

        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存主题文件", "", "主题文件 (*.theme)"
        )
        if file_path:
            try:
                # 这里应该是导出主题的代码
                QMessageBox.information(self, "提示", "主题导出成功！")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"导出主题失败：{e}")

    def apply_custom_color(self, color):
        self.setStyleSheet(
            f"""
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
        """
        )

    def darken_color(self, color, factor=0.8):
        # 将颜色变暗

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

            folder = QFileDialog.getExistingDirectory(
                dialog,
                "选择下载文件夹" if self.is_cn else "Select Download Folder",
                self.download_path,
            )
            if folder:
                path_edit.setText(folder)

        path_btn.clicked.connect(choose_folder)
        path_layout = QHBoxLayout()
        path_layout.addWidget(path_edit)
        path_layout.addWidget(path_btn)
        layout.addWidget(path_label)
        layout.addLayout(path_layout)

        # 并发数设置
        thread_label = QLabel(
            "最大并发下载数：" if self.is_cn else "Max Concurrent Downloads:"
        )
        thread_box = QComboBox()
        thread_box.addItems([str(i) for i in range(1, 9)])
        thread_box.setCurrentIndex(getattr(self, "max_workers", 4) - 1)
        layout.addWidget(thread_label)
        layout.addWidget(thread_box)

        # 文件命名模板
        template_label = QLabel(
            "文件命名模板：" if self.is_cn else "Filename Template:"
        )
        template_edit = QLineEdit(getattr(self, "filename_template", "{title}"))
        template_edit.setPlaceholderText("{title}、{up主}、{date} 可用")
        layout.addWidget(template_label)
        layout.addWidget(template_edit)

        # 代理设置
        proxy_label = QLabel(
            "代理（如 http://127.0.0.1:7890 或 socks5://127.0.0.1:1080）"
            if self.is_cn
            else "Proxy (e.g. http://127.0.0.1:7890 or socks5://127.0.0.1:1080)"
        )
        proxy_edit = QLineEdit(getattr(self, "proxy_url", ""))
        proxy_edit.setPlaceholderText(
            "留空为不使用代理" if self.is_cn else "Leave blank for no proxy"
        )
        layout.addWidget(proxy_label)
        layout.addWidget(proxy_edit)

        # 主题切换
        theme_btn = QPushButton("切换主题" if self.is_cn else "Toggle Theme")
        theme_btn.clicked.connect(self.toggle_theme)
        layout.addWidget(theme_btn)

        #  语言切换

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
        export_btn = QPushButton(
            "导出当前主题" if self.is_cn else "Export Current Theme"
        )
        export_btn.setIcon(QIcon("download.png"))
        export_btn.clicked.connect(self.export_theme)
        theme_layout.addWidget(export_btn)

        # 自定义颜色选择器
        color_label = QLabel("自定义颜色:" if self.is_cn else "Custom Colors:")
        theme_layout.addWidget(color_label)

        color_grid = QWidget()
        color_grid_layout = QGridLayout(color_grid)

        colors = [
            "#00a1d6",
            "#fb7299",
            "#ff9800",
            "#4caf50",
            "#9c27b0",
            "#607d8b",
            "#795548",
            "#f44336",
        ]

        for i, color in enumerate(colors):
            btn = QPushButton()
            btn.setFixedSize(40, 40)
            btn.setStyleSheet(f"background:{color};border:none;")
            btn.clicked.connect(lambda _, c=color: self.apply_custom_color(c))
            color_grid_layout.addWidget(btn, i // 4, i % 4)

        theme_layout.addWidget(color_grid)

        # 添加Tab
        tab_widget.addTab(general_tab, "常规设置" if self.is_cn else "General")
        tab_widget.addTab(theme_tab, "主题" if self.is_cn else "Themes")

        main_layout = QVBoxLayout(dialog)
        main_layout.addWidget(tab_widget)
        dialog.exec()

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
                self.download_queue[row] = (
                    self.download_queue[row][0],
                    "已取消" if self.is_cn else "Canceled",
                )
                list_widget.item(row).setText(
                    f"{self.download_queue[row][0]}  -  {'已取消' if self.is_cn else 'Canceled'}"
                )

        cancel_btn.clicked.connect(cancel_task)
        dialog.exec()

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

    def get_button_style(self, color_primary="#00a1d6", color_hover="#0088cc"):
        """统一的按钮样式"""
        return f"""
        QPushButton {{
            background: {color_primary};
            color: white;
            border: none;
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 14px;
            font-weight: bold;
            text-align: center;
        }}
        QPushButton:hover {{
            background: {color_hover};
        }}
        QPushButton:disabled {{
            background: #cccccc;
            color: #666666;
        }}
    """

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

    def execute_db_query(self, query, params=None, fetch_type="all"):
        """统一的数据库查询方法"""
        try:
            import sqlite3

            if not os.path.exists("anime.db"):
                raise Exception("数据库文件不存在")

            with sqlite3.connect("anime.db") as conn:
                c = conn.cursor()
                if params:
                    c.execute(query, params)
                else:
                    c.execute(query)

                if fetch_type == "one":
                    return c.fetchone()
                elif fetch_type == "all":
                    return c.fetchall()
                else:
                    return None
        except Exception as e:
            print(f"数据库查询失败: {e}")
            return None

    def safe_execute(self, func, error_msg="操作失败", *args, **kwargs):
        """安全执行函数的包装器"""
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"{error_msg}: {e}")
            return None

    def find_controls(self, parent, control_names):
        """批量查找控件"""
        controls = {}
        for name in control_names:
            if isinstance(name, tuple):
                control_type, object_name = name
                controls[object_name] = parent.findChild(control_type, object_name)
            else:
                controls[name] = (
                    parent.findChild(QPushButton, name)
                    or parent.findChild(QSlider, name)
                    or parent.findChild(QLabel, name)
                )
        return controls

    def safe_add_widget(self, layout, widget, *args, **kwargs):
        """安全地添加控件到布局"""
        if widget is not None:
            layout.addWidget(widget, *args, **kwargs)
        else:
            print("Warning: Attempting to add null widget to layout")

    def cleanup_layout(self, layout_or_widget):
        """统一的布局清理方法"""
        if hasattr(layout_or_widget, "layout"):
            layout = layout_or_widget.layout()
        else:
            layout = layout_or_widget

        if layout:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
                elif child.layout():
                    self.cleanup_layout(child.layout())


# 在文件顶部导入PySide6 QML组件


class MpvBridge(QObject):
    positionChanged = Signal(float)
    durationChanged = Signal(float)
    pausedChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._player = mpv.MPV(log_handler=print, loglevel="warn")
        self._player.observe_property("time-pos", self._on_position)
        self._player.observe_property("duration", self._on_duration)
        self._player.observe_property("pause", self._on_pause)
        self._position = 0
        self._duration = 0
        self._paused = True

    @Slot(str)
    def play(self, url):
        self._player.play(url)

    @Slot()
    def togglePause(self):
        self._player.pause = not self._player.pause

    @Slot(float)
    def seek(self, pos):
        self._player.seek(pos, reference="absolute")

    @Property(float, notify=positionChanged)
    def position(self):
        return self._position

    @Property(float, notify=durationChanged)
    def duration(self):
        return self._duration

    @Property(bool, notify=pausedChanged)
    def paused(self):
        return self._paused

    def _on_position(self, name, value):
        if value is not None:
            self._position = value
            self.positionChanged.emit(value)

    def _on_duration(self, name, value):
        if value is not None:
            self._duration = value
            self.durationChanged.emit(value)

    def _on_pause(self, name, value):
        if value is not None:
            self._paused = value
            self.pausedChanged.emit(value)


def is_network_available():
    """检查网络连接"""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False


if __name__ == "__main__":
    try:
        # 在创建QApplication之前设置属性 - PySide6版本
        QApplication.setAttribute(Qt.AA_UseSoftwareOpenGL, True)
        QApplication.setAttribute(Qt.AA_UseDesktopOpenGL, False)
        QApplication.setAttribute(Qt.AA_UseOpenGLES, False)

        # 现在创建 QApplication 实例
        app = QApplication(sys.argv)

        # 设置应用程序信息
        app.setApplicationName("Bilibili 视频下载器")
        app.setApplicationVersion("1.0")
        app.setOrganizationName("YourCompany")

        # 创建主窗口
        window = BiliDownloader()

        # 显示窗口
        window.show()

        # 启动事件循环 - PySide6中exec()没有下划线
        sys.exit(app.exec())

    except Exception as e:
        print(f"程序启动失败: {e}")
        import traceback

        traceback.print_exc()

        # 如果GUI启动失败，显示错误对话框
        try:
            if not QApplication.instance():
                QApplication.setAttribute(Qt.AA_UseSoftwareOpenGL, True)
                error_app = QApplication(sys.argv)
            else:
                error_app = QApplication.instance()

            QMessageBox.critical(None, "启动错误", f"程序启动失败:\n{e}")
        except:
            print("无法显示错误对话框")

        sys.exit(1)
