# downbili

一个精简的视频下载工具。主入口是 `gui_download_qt.py`，当前版本只保留下载功能，不再加载动漫资源站、数据库或播放器模块。

## 启动

```powershell
py gui_download_qt.py
```

也可以双击 `启动下载器.bat`。

## 功能

- 支持输入 Bilibili 链接或 BV 号
- 支持 yt-dlp 能识别的其他常见视频页面链接
- 粘贴链接后自动解析预览，显示标题、封面、作者、时长、播放/点赞和分 P 数量
- 显示可用格式表，包括格式 ID、类型、分辨率、帧率、编码和估算大小
- 可在格式表中选择一行，作为本次下载格式
- 支持批量下载、下载目录、清晰度、代理、文件名模板
- 支持 cookies.txt，也可以尝试读取 Chrome / Edge / Firefox Cookie
- B 站无 Cookie 遇到 412 时，会自动尝试普通公开视频兜底下载
- 下载完成后会显示本地文件大小、时长、分辨率、帧率和音视频编码

## 依赖

```powershell
py -m pip install -r requirements.txt
```

项目目录下的 `ffmpeg.exe` 会被自动用于合并音视频。

## B 站 Cookie

公开视频通常可以直接下载；如果遇到 412、登录限制、高清不可用、会员内容或仅音频下载，请配置 Cookie。

无 Cookie 的 B 站兜底下载只使用普通公开视频直链，通常只能拿到 720P/360P 单文件；更高清、仅音频、DASH 格式、会员内容等需要 Cookie 和 yt-dlp 正常解析。

推荐方式：

1. 在浏览器登录 B 站
2. 用浏览器扩展导出 `cookies.txt`
3. 在下载器里选择 `cookies.txt 文件`

也可以在下载器里选择读取 Chrome / Edge / Firefox Cookie，但浏览器正在运行或权限不足时可能失败。
