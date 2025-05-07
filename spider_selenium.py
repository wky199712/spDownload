import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import sqlite3
from urllib.parse import urljoin

# 1. 用 requests 获取 PHPSESSID
base_url = "http://www.yhdm95.com"
session = requests.Session()
resp = session.get(f"{base_url}/acg/0/0/japan/1.html", timeout=10)
phpsessid = session.cookies.get("PHPSESSID")
print("requests 获取到 PHPSESSID:", phpsessid)

# 2. 启动 selenium，注入 cookie
chrome_options = Options()
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--window-size=1920,1080')
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
chrome_options.add_experimental_option('useAutomationExtension', False)
chrome_options.add_argument('--ignore-certificate-errors')
chrome_options.add_argument("--user-data-dir=C:/Temp/selenium_profile_cookie_test")
# chrome_options.add_argument('--host-resolver-rules=MAP www.yhdm95.com 127.0.0.1,EXCLUDE localhost')  # 删除或注释掉这一行
chrome_options.add_argument('--ignore-urlfetcher-cert-requests')
chrome_options.add_argument('--disable-features=StrictOriginIsolation,UpgradeInsecureRequests,BlockInsecurePrivateNetworkRequests,HTTPS-First-Mode')
chrome_options.add_argument('--disable-web-security')
chrome_options.add_argument('--allow-running-insecure-content')
chrome_options.add_argument('--disable-site-isolation-trials')

driver = webdriver.Chrome(options=chrome_options)
driver.get("http://www.yhdm95.com")  # 必须先访问目标域名
# 注入 cookie
if phpsessid:
    driver.add_cookie({
        'name': 'PHPSESSID',
        'value': phpsessid,
        'domain': 'www.yhdm95.com',
        'path': '/',
    })

conn = sqlite3.connect("anime.db")
c = conn.cursor()

try:
    for page in range(1, 100):  # 假设最多100页
        url = f"{base_url}/acg/0/0/japan/{page}.html"
        driver.get(url)
        print("当前页面URL：", driver.current_url)
        for attempt in range(5):  # 最多刷新5次
            print(f"第{attempt+1}次尝试加载页面...")
            try:
                WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".main li"))
                )
                html = driver.page_source
                soup = BeautifulSoup(html, "html.parser")
                items = soup.select(".main li")
                if items:
                    print(f"第{page}页项目数：", len(items))
                    break
            except Exception as e:
                print(f"第{attempt+1}次加载失败，重试...")
                time.sleep(2)
        else:
            print("多次刷新后仍无内容，跳过本页。")
            continue
        # 处理本页所有动漫
        for li in items:
            a = li.find("a")
            if not a:
                continue
            name = a.get("title") or a.text.strip()
            href = a.get("href")
            img_tag = li.find("img")
            cover = img_tag.get("data-original") or img_tag.get("src") or "" if img_tag else ""
            # 进入详情页采集简介和分集
            detail_url = base_url + href
            for detail_attempt in range(5):
                driver.get(detail_url)
                try:
                    # 等待分集ul出现，而不是只等简介
                    WebDriverWait(driver, 12).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "ul[id^='ul_playlist_']"))
                    )
                    detail_html = driver.page_source
                    # 可选：调试用，保存源码
                    # with open("debug_detail.html", "w", encoding="utf-8") as f:
                    #     f.write(detail_html)
                    detail_soup = BeautifulSoup(detail_html, "html.parser")
                    intro_tag = detail_soup.select_one(".info-intro")
                    if not intro_tag:
                        intro_tag = detail_soup.select_one(".des2") or detail_soup.select_one(".des1")
                    intro_text = intro_tag.text.strip() if intro_tag else ""
                    
                    # 提取地区、年份、总集数
                    area, year, total_eps = "", "", ""
                    type_list = []

                    # 地区和年份
                    for dd in detail_soup.select("div.info dd"):
                        txt = dd.get_text(strip=True)
                        if "地区：" in txt:
                            area = txt.split("地区：")[1].split()[0]
                        if "年代：" in txt:
                            year = txt.split("年代：")[1].split()[0]
                        if "更新至" in txt and "集" in txt:
                            total_eps = txt.replace("更新至", "").replace("集", "").strip()

                    # 类型
                    type_links = detail_soup.select("div.info a")
                    type_list = [a.get_text(strip=True) for a in type_links]
                    type_str = ",".join(type_list)

                    # 查重动漫
                    c.execute("SELECT id FROM anime WHERE name=? AND cover=?", (name, cover))
                    row = c.fetchone()
                    if row:
                        anime_id = row[0]
                    else:
                        c.execute(
                            "INSERT INTO anime (name, cover, intro, year, area, type, total_eps) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (name, cover, intro_text, year, area, type_str, total_eps)
                        )
                        anime_id = c.lastrowid
                    # 分集采集
                    # 在采集分集时，进入每个分集播放页，提取 video_src
                    for ul in detail_soup.find_all("ul"):
                        ul_id = ul.get("id", "")
                        if ul_id.startswith("ul_playlist_"):
                            for ep in ul.find_all("a"):
                                ep_title = ep.text.strip()
                                ep_href = ep.get("href")
                                play_url = base_url + ep_href if ep_href.startswith("/") else base_url + "/" + ep_href

                                # 进入分集播放页
                                driver.get(play_url)
                                WebDriverWait(driver, 8).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, "iframe#playiframe"))
                                )
                                iframe_elem = driver.find_element(By.CSS_SELECTOR, "iframe#playiframe")
                                driver.switch_to.frame(iframe_elem)

                                # 可选：如果还有第二层iframe，再切换
                                try:
                                    inner_iframe_elem = driver.find_element(By.TAG_NAME, "iframe")
                                    driver.switch_to.frame(inner_iframe_elem)
                                except Exception:
                                    pass  # 没有第二层iframe就跳过

                                # 等待video标签出现
                                WebDriverWait(driver, 10).until(
                                    EC.presence_of_element_located((By.TAG_NAME, "video"))
                                )
                                real_video_url = driver.execute_script(
                                    "return document.querySelector('video') && document.querySelector('video').currentSrc;"
                                )
                                print(f"最终视频直链: {real_video_url}")

                                # 切回主文档，避免影响后续操作
                                driver.switch_to.default_content()

                                print(f"线路:{ul_id} 集数:{ep_title} 链接:{play_url} 视频源:{real_video_url}")

                                with open("debug_iframe.html", "w", encoding="utf-8") as f:
                                    f.write(driver.page_source)

                                # 存库时可多加一列 real_video_url
                                # 需要先 ALTER TABLE episode ADD COLUMN real_video_url TEXT;
                                try:
                                    c.execute("SELECT id FROM episode WHERE anime_id=? AND title=? AND play_url=?", (anime_id, ep_title, play_url))
                                    if not c.fetchone():
                                        c.execute(
                                            "INSERT INTO episode (anime_id, title, play_url, video_src, real_video_url, line_id) VALUES (?, ?, ?, ?, ?, ?)",
                                            (anime_id, ep_title, play_url, real_video_url, real_video_url, ul_id)
                                        )
                                    conn.commit()
                                except Exception as db_e:
                                    print(f"插入episode表出错: {db_e}，anime_id={anime_id}, title={ep_title}, play_url={play_url}")
                    # 在采集分集播放页 detail_html 后
                    play_soup = BeautifulSoup(detail_html, "html.parser")
                    iframe = play_soup.find("iframe", id="playiframe")
                    video_src = iframe.get("src") if iframe else ""
                    print(f"分集视频iframe src: {video_src}")
                    # 你可以把 video_src 存入 episode 表，或单独保存
                    conn.commit()
                    break
                except Exception as e:
                    print(f"详情页第{detail_attempt+1}次加载失败，重试...")
                    time.sleep(2)
            else:
                print("详情页多次刷新仍失败，跳过。")
                continue
            time.sleep(1)
        time.sleep(2)
finally:
    try:
        driver.quit()
    except Exception:
        pass
    conn.close()