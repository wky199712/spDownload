"""gui_download_qt 纯函数单元测试。

运行方式:
    pytest test_utils.py -v
"""

import sys
from pathlib import Path

# 确保能导入项目主模块
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gui_download_qt import (
    extract_aid,
    extract_bvid,
    extract_video_id,
    format_bytes,
    format_duration,
    format_error,
    is_bilibili_url,
    normalize_input,
    sanitize_filename,
    selected_page_number,
    split_inputs,
)


# ---------- split_inputs ----------

class TestSplitInputs:
    def test_empty(self):
        assert split_inputs("") == []
        assert split_inputs(None) == []

    def test_single(self):
        assert split_inputs("https://bilibili.com/video/BV1xx") == [
            "https://bilibili.com/video/BV1xx"
        ]

    def test_newline_separated(self):
        text = "BV1abc\nBV2def\nBV3ghi"
        assert split_inputs(text) == ["BV1abc", "BV2def", "BV3ghi"]

    def test_mixed_separators(self):
        text = "BV1abc, BV2def\nBV3ghi BV4jkl，BV5mno"
        assert split_inputs(text) == ["BV1abc", "BV2def", "BV3ghi", "BV4jkl", "BV5mno"]

    def test_whitespace_only(self):
        assert split_inputs("   \n\t  ") == []


# ---------- extract_bvid ----------

class TestExtractBvid:
    def test_standard_url(self):
        url = "https://www.bilibili.com/video/BV1xx411c7mD"
        assert extract_bvid(url) == "BV1xx411c7mD"

    def test_b23_short(self):
        url = "https://b23.tv/BV1xx411c7mD"
        assert extract_bvid(url) == "BV1xx411c7mD"

    def test_with_query(self):
        url = "https://www.bilibili.com/video/BV1xx411c7mD?p=2&t=30"
        assert extract_bvid(url) == "BV1xx411c7mD"

    def test_no_bvid(self):
        assert extract_bvid("https://www.youtube.com/watch?v=abc") == ""

    def test_bare_bvid(self):
        assert extract_bvid("BV1xx411c7mD") == "BV1xx411c7mD"


# ---------- extract_aid ----------

class TestExtractAid:
    def test_standard(self):
        assert extract_aid("https://www.bilibili.com/video/av170001") == "170001"

    def test_uppercase(self):
        assert extract_aid("https://www.bilibili.com/video/AV170001") == "170001"

    def test_no_aid(self):
        assert extract_aid("https://www.bilibili.com/video/BV1xx411c7mD") == ""


# ---------- extract_video_id ----------

class TestExtractVideoId:
    def test_bvid(self):
        kind, vid = extract_video_id("https://bilibili.com/video/BV1xx411c7mD")
        assert kind == "bvid"
        assert vid == "BV1xx411c7mD"

    def test_aid(self):
        kind, vid = extract_video_id("https://bilibili.com/video/av170001")
        assert kind == "aid"
        assert vid == "170001"

    def test_none(self):
        kind, vid = extract_video_id("https://youtube.com/watch?v=abc")
        assert kind is None
        assert vid is None


# ---------- normalize_input ----------

class TestNormalizeInput:
    def test_bvid_completion(self):
        assert normalize_input("BV1xx411c7mD") == "https://www.bilibili.com/video/BV1xx411c7mD"

    def test_av_completion(self):
        assert normalize_input("av170001") == "https://www.bilibili.com/video/av170001"

    def test_AV_uppercase(self):
        assert normalize_input("AV170001") == "https://www.bilibili.com/video/av170001"

    def test_full_url_unchanged(self):
        url = "https://www.bilibili.com/video/BV1xx411c7mD?p=2"
        assert normalize_input(url) == url

    def test_empty(self):
        assert normalize_input("") == ""
        assert normalize_input(None) == ""

    def test_other_url_unchanged(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert normalize_input(url) == url


# ---------- is_bilibili_url ----------

class TestIsBilibiliUrl:
    def test_bilibili_com(self):
        assert is_bilibili_url("https://www.bilibili.com/video/BV1xx411c7mD")

    def test_b23_tv(self):
        assert is_bilibili_url("https://b23.tv/abc")

    def test_bare_bvid(self):
        assert is_bilibili_url("BV1xx411c7mD")

    def test_bare_av(self):
        assert is_bilibili_url("av170001")

    def test_other(self):
        assert not is_bilibili_url("https://youtube.com/watch?v=abc")


# ---------- selected_page_number ----------

class TestSelectedPageNumber:
    def test_default(self):
        assert selected_page_number("https://bilibili.com/video/BV1xx") == 1

    def test_explicit(self):
        assert selected_page_number("https://bilibili.com/video/BV1xx?p=3") == 3

    def test_invalid(self):
        assert selected_page_number("https://bilibili.com/video/BV1xx?p=abc") == 1


# ---------- sanitize_filename ----------

class TestSanitizeFilename:
    def test_normal(self):
        assert sanitize_filename("我的视频") == "我的视频"

    def test_special_chars(self):
        assert sanitize_filename("a/b:c*d?e\"f<g>h|i") == "a_b_c_d_e_f_g_h_i"

    def test_empty(self):
        assert sanitize_filename("") == "video"
        assert sanitize_filename(None) == "video"

    def test_max_len(self):
        name = "a" * 200
        assert len(sanitize_filename(name, max_len=50)) == 50


# ---------- format_duration ----------

class TestFormatDuration:
    def test_seconds(self):
        assert format_duration(45) == "0:45"

    def test_minutes(self):
        assert format_duration(125) == "2:05"

    def test_hours(self):
        assert format_duration(3661) == "1:01:01"

    def test_zero(self):
        assert format_duration(0) == "-"

    def test_negative(self):
        assert format_duration(-5) == "-"

    def test_invalid(self):
        assert format_duration("abc") == "-"


# ---------- format_bytes ----------

class TestFormatBytes:
    def test_bytes(self):
        assert format_bytes(512) == "512.0 B"

    def test_kb(self):
        assert format_bytes(2048) == "2.0 KB"

    def test_mb(self):
        assert format_bytes(1048576) == "1.0 MB"

    def test_gb(self):
        assert format_bytes(1073741824) == "1.0 GB"

    def test_zero(self):
        assert format_bytes(0) == "-"

    def test_negative(self):
        assert format_bytes(-100) == "-"

    def test_invalid(self):
        assert format_bytes("abc") == "-"


# ---------- format_error ----------

class TestFormatError:
    def test_with_message(self):
        assert format_error(ValueError("test message")) == "test message"

    def test_empty_message(self):
        exc = ValueError()
        assert format_error(exc) == "ValueError"
