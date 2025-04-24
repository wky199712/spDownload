import tkinter as tk
from tkinter import messagebox
from tkinter.ttk import Progressbar
from tkinter import StringVar
import yt_dlp
import os
import threading
from urllib.request import urlopen
from PIL import Image, ImageTk
import io
import re

# 创建下载文件夹
if not os.path.exists("download"):
    os.makedirs("download")

# 创建主窗口
root = tk.Tk()
# root.overrideredirect(True)  # 注释掉这行
root.geometry("520x600")
root.configure(bg="#f6f7f9")

# 需要无边框时再设置
def set_no_border():
    root.overrideredirect(True)

def unset_no_border():
    root.overrideredirect(False)

# 自定义标题栏
def move_window(event):
    root.geometry(f'+{event.x_root - move_window.x}+{event.y_root - move_window.y}')
def get_pos(event):
    move_window.x = event.x
    move_window.y = event.y

is_maximized = [False]
normal_geometry = [root.geometry()]

def toggle_maximize():
    if not is_maximized[0]:
        normal_geometry[0] = root.geometry()
        root.geometry(f"{root.winfo_screenwidth()}x{root.winfo_screenheight()}+0+0")
        is_maximized[0] = True
    else:
        root.geometry(normal_geometry[0])
        is_maximized[0] = False

title_bar = tk.Frame(root, bg="#00a1d6", relief='raised', bd=0, height=36)
title_bar.pack(fill="x", side="top")

# 可选：加载B站logo
try:
    with urlopen("https://www.bilibili.com/favicon.ico") as u:
        logo_data = u.read()
    logo_img = Image.open(io.BytesIO(logo_data)).resize((20, 20))
    logo_img = ImageTk.PhotoImage(logo_img)
    logo_label = tk.Label(title_bar, image=logo_img, bg="#00a1d6")
    logo_label.image = logo_img
    logo_label.pack(side="left", padx=(8, 4), pady=4)
except Exception:
    logo_label = tk.Label(title_bar, text="B", font=("微软雅黑", 14, "bold"), fg="white", bg="#00a1d6")
    logo_label.pack(side="left", padx=(8, 4), pady=4)

title_label = tk.Label(title_bar, text="Bilibili 视频下载器", font=("微软雅黑", 12, "bold"), bg="#00a1d6", fg="white")
title_label.pack(side="left", padx=4)

# 最小化按钮
def minimize_window():
    unset_no_border()  # 先关闭无边框
    root.iconify()
    root.after(200, set_no_border)  # 恢复无边框（延迟一点点更兼容）
min_btn = tk.Button(title_bar, text="—", command=minimize_window, bg="#00a1d6", fg="white", bd=0, padx=8, pady=0, font=("微软雅黑", 12), activebackground="#0090c6", activeforeground="white")
min_btn.pack(side="right", padx=0)
min_btn.bind("<Enter>", lambda e: min_btn.config(bg="#0090c6"))
min_btn.bind("<Leave>", lambda e: min_btn.config(bg="#00a1d6"))

# 最大化/还原按钮
max_btn = tk.Button(title_bar, text="□", command=toggle_maximize, bg="#00a1d6", fg="white", bd=0, padx=8, pady=0, font=("微软雅黑", 12), activebackground="#0090c6", activeforeground="white")
max_btn.pack(side="right", padx=0)
max_btn.bind("<Enter>", lambda e: max_btn.config(bg="#0090c6"))
max_btn.bind("<Leave>", lambda e: max_btn.config(bg="#00a1d6"))

# 关闭按钮
def close_window():
    root.destroy()
close_btn = tk.Button(title_bar, text="✕", command=close_window, bg="#00a1d6", fg="white", bd=0, padx=8, pady=0, font=("微软雅黑", 12), activebackground="#fb7299", activeforeground="white")
close_btn.pack(side="right", padx=0)
close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#fb7299"))
close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#00a1d6"))

# 支持拖动窗口
title_bar.bind("<Button-1>", get_pos)
title_bar.bind("<B1-Motion>", move_window)
title_label.bind("<Button-1>", get_pos)
title_label.bind("<B1-Motion>", move_window)
logo_label.bind("<Button-1>", get_pos)
logo_label.bind("<B1-Motion>", move_window)
# 下载进度变量
progress_var = tk.DoubleVar()

# 视频标题变量
video_title_var = StringVar()

# 获取视频信息函数
def get_video_info(bv_input):
    if bv_input.startswith("https://www.bilibili.com/video/"):
        bv_url = bv_input
    elif bv_input.startswith("BV"):
        bv_url = f"https://www.bilibili.com/video/{bv_input}"
    else:
        return None

    try:
        ydl_opts = {'quiet': True, 'skip_download': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(bv_url, download=False)
            title = info_dict.get("title", "未知标题")
            thumbnail = info_dict.get("thumbnail", None)
            return {"title": title, "thumbnail": thumbnail, "url": bv_url}
    except yt_dlp.utils.DownloadError as e:
        # 处理 404 错误（或者其他下载相关的错误）
        if 'HTTP Error 404' in str(e):
            return None  # 404 错误不弹出提示框，而是返回 None
        else:
            return None  # 其他下载错误也返回 None
    except Exception as e:
        return None  # 其他错误返回 None

# 显示标题和封面图函数
def show_video_info():
    bv_input = entry_bv.get().strip()
    if len(bv_input) < 12:  # 如果 BV 号长度小于 12，不进行请求
        clear_video_info()
        return None

    if bv_input:
        info = get_video_info(bv_input)
        if info:
            video_title_var.set(info["title"])
            try:
                with urlopen(info["thumbnail"]) as u:
                    raw_data = u.read()
                im = Image.open(io.BytesIO(raw_data))
                im = im.resize((360, 200))
                thumbnail_image = ImageTk.PhotoImage(im)
                cover_label.configure(image=thumbnail_image)
                cover_label.image = thumbnail_image
            except Exception as e:
                print(f"封面图加载失败: {e}")
            return info["url"]
        else:
            clear_video_info()
            return None

# 清空视频标题和封面图
def clear_video_info():
    video_title_var.set("")  # 清空标题
    cover_label.configure(image='')  # 清空封面图
    cover_label.image = None  # 清空封面图引用

# 安全文件名函数
def safe_filename(title):
    return re.sub(r'[\\/:*?"<>|]', '_', title)

# 下载函数（子线程中运行）
def start_download():
    root.after(0, progress_var.set, 0)  # 下载前归零
    bv_url = show_video_info()
    if not bv_url:
        messagebox.showerror("错误", "获取视频信息失败，请检查链接或网络！")
        return

    title = video_title_var.get()
    safe_title = safe_filename(title)

    ydl_opts = {
        'format': get_quality_format(),
        'outtmpl': f'download/{safe_title}.%(ext)s',
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'progress_hooks': [update_progress],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([bv_url])
        progress_var.set(100)
        messagebox.showinfo("下载完成", "视频下载完成！")
    except yt_dlp.utils.DownloadError as e:
        # 处理 404 错误（或者其他下载相关的错误）
        if 'HTTP Error 404' in str(e):
            messagebox.showerror("视频未找到", "该视频无法下载，可能不存在或链接错误！")
        else:
            messagebox.showerror("下载失败", f"下载失败: {e}")
    except Exception as e:
        messagebox.showerror("下载失败", f"下载失败: {e}")

# 更新下载进度条
def update_progress(d):
    if d['status'] == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate')
        downloaded = d.get('downloaded_bytes', 0)
        if total:
            percentage = downloaded / total * 100
            root.after(0, progress_var.set, percentage)
    elif d['status'] == 'finished':
        root.after(0, progress_var.set, 100)

# 输入框变动时自动更新视频信息
debounce_id = None

def on_bv_input_change(event=None):
    global debounce_id
    if debounce_id:
        root.after_cancel(debounce_id)
    debounce_id = root.after(500, show_video_info)  # 500ms防抖

# BV号输入框
entry_bv = tk.Entry(root, font=("Comic Sans MS", 12), width=45, bg="#ffccff")
entry_bv.pack(pady=5)

# 设置监听事件，当用户输入时触发显示标题和封面图
entry_bv.bind("<KeyRelease>", on_bv_input_change)

# 点击下载按钮
def on_click_download():
    threading.Thread(target=start_download, daemon=True).start()

# 设置 GUI 元素
label_bv = tk.Label(root, text="请输入 Bilibili 视频 BV 号 或 完整 URL：", font=("微软雅黑", 12),
                    fg="#00a1d6", bg="#f6f7f9")
label_bv.pack(pady=10)

# 显示视频标题
title_label = tk.Label(root, textvariable=video_title_var, font=("微软雅黑", 14, "bold"), bg="#f6f7f9", fg="#222")
title_label.pack(pady=10)

# 封面图展示区域
cover_label = tk.Label(root, bg="#f6f7f9", bd=2, relief="groove", width=360, height=200)
cover_label.pack(pady=5)

# 下载按钮
def on_enter(e):
    download_button.config(bg="#00a1d6")
def on_leave(e):
    download_button.config(bg="#fb7299")

download_button = tk.Button(root, text="开始下载", command=on_click_download,
                            font=("微软雅黑", 12), bg="#fb7299", fg="white", activebackground="#00a1d6", activeforeground="white", relief="flat", bd=0, padx=30, pady=8, cursor="hand2")
download_button.pack(pady=15)
download_button.bind("<Enter>", on_enter)
download_button.bind("<Leave>", on_leave)

# 进度条
style = tk.ttk.Style()
style.theme_use('default')
style.configure("TProgressbar", thickness=10, troughcolor="#e3f1fd", background="#00a1d6", bordercolor="#e3f1fd", lightcolor="#00a1d6", darkcolor="#00a1d6")
progress_bar = Progressbar(root, variable=progress_var, length=400, maximum=100, style="TProgressbar")
progress_bar.pack(pady=10)

quality_var = tk.StringVar(value='bv*+ba')
quality_options = [
    ('自动(最高)', 'bv*+ba'),
    ('仅视频', 'bv*'),
    ('仅音频', 'ba')
]
quality_menu = tk.OptionMenu(root, quality_var, *[q[0] for q in quality_options])
quality_menu.config(font=("微软雅黑", 12), bg="#e3f1fd", fg="#222", activebackground="#00a1d6", relief="flat", bd=0, highlightthickness=1, highlightbackground="#00a1d6")
quality_menu["menu"].config(font=("微软雅黑", 12), bg="#fff", fg="#222")
quality_menu.pack(pady=5)

def get_quality_format():
    mapping = {q[0]: q[1] for q in quality_options}
    return mapping.get(quality_var.get(), 'bv*+ba')

# 运行主程序
root.mainloop()
