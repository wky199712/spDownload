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
import traceback

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
                    print(f"第{page}页，共{len(items)}个动漫")
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
            name = name.strip()
            href = a.get("href")
            if href:
                href = href.strip()
                if not href.endswith('/'):
                    href += '/'
            img_tag = li.find("img")
            cover = img_tag.get("data-original") or img_tag.get("src") or "" if img_tag else ""
            print(f"当前页码: {page}, 当前动漫: {name}, href: {href}")
            print("查重用name:", repr(name), "href:", repr(href))
            c.execute("SELECT id FROM anime WHERE href=?", (href,))
            row = c.fetchone()
            if row:
                print(f"动漫已采集过，跳过: {name}")
                continue
            # 进入详情页采集简介和分集（只采集一次，不重试）
            detail_url = base_url + href
            try:
                driver.get(detail_url)
                WebDriverWait(driver, 12).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "ul[id^='ul_playlist_']"))
                )
                detail_html = driver.page_source
                detail_soup = BeautifulSoup(detail_html, "html.parser")
                intro_tag = detail_soup.select_one(".info-intro")
                if not intro_tag:
                    intro_tag = detail_soup.select_one(".des2") or detail_soup.select_one(".des1")
                intro_text = intro_tag.text.strip() if intro_tag else ""
                
                # 提取地区、年份、总集数
                area, year, total_eps = "", "", ""
                type_list = []

                for dd in detail_soup.select("div.info dd"):
                    # 只取b标签后的纯文本
                    b_tag = dd.find("b")
                    if b_tag:
                        b_tag.extract()  # 移除b标签本身
                    txt = dd.get_text(strip=True)
                    if "地区" in dd.text:
                        area = txt
                    elif "年代" in dd.text:
                        year = txt
                    elif "更新至" in dd.text and "集" in dd.text:
                        total_eps = txt.replace("更新至", "").replace("集", "").strip()

                # 类型
                type_links = detail_soup.select("div.info a")
                type_list = [a.get_text(strip=True) for a in type_links]
                type_str = ",".join(type_list)

                # 剧情简介
                intro_tag = detail_soup.select_one(".info-intro")
                if not intro_tag:
                    intro_tag = detail_soup.select_one(".des2") or detail_soup.select_one(".des1")
                if intro_tag:
                    # 去掉b标签内容
                    b_tag = intro_tag.find("b")
                    if b_tag:
                        b_tag.extract()
                    intro_text = intro_tag.get_text(strip=True)
                else:
                    intro_text = ""

                # 详情页采集成功后，直接插入anime
                try:
                    c.execute(
                        "INSERT INTO anime (name, href, cover, intro, year, area, type, total_eps) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (name, href, cover, intro_text, year, area, type_str, total_eps)
                    )
                    anime_id = c.lastrowid
                    conn.commit()
                    print("插入anime成功:", name, href)
                except Exception as e:
                    print("插入anime失败:", e, name, href)

                # --------- 分集采集逻辑 ---------
                first_ul = detail_soup.select_one("ul[id^='ul_playlist_']")
                if not first_ul:
                    print("未找到分集ul，跳过")
                    continue  # 跳到下一个li
                ep_links = []
                for ep_a in first_ul.find_all("a"):
                    ep_href = ep_a.get("href")
                    ep_title = ep_a.text.strip()
                    if ep_href:
                        ep_links.append((ep_title, ep_href))

                for ep_title, ep_href in ep_links:
                    play_url = urljoin(base_url, ep_href)
                    driver.get(play_url)
                    WebDriverWait(driver, 8).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "li[id^='tab']"))
                    )
                    tab_lis = driver.find_elements(By.CSS_SELECTOR, "li[id^='tab']")
                    tab_info_list = []
                    for tab_li in tab_lis:
                        tab_id = tab_li.get_attribute("id")
                        tab_name = tab_li.text.strip()
                        tab_info_list.append({"id": tab_id, "name": tab_name})

                    for tab_idx, tab_info in enumerate(tab_info_list):
                        tab_lis = driver.find_elements(By.CSS_SELECTOR, "li[id^='tab']")
                        if (tab_idx >= len(tab_lis)):
                            print(f"未找到ul: tab_idx={tab_idx}")
                            continue
                        tab_li = tab_lis[tab_idx]
                        tab_li.click()
                        time.sleep(1)
                        ul_elems = driver.find_elements(By.CSS_SELECTOR, "ul[id^='ul_playlist_']")
                        if (tab_idx >= len(ul_elems)):
                            print(f"未找到ul: tab_idx={tab_idx}")
                            continue
                        ul_elem = ul_elems[tab_idx]
                        ul_id = ul_elem.get_attribute("id")
                        ep_a_tags = ul_elem.find_elements(By.TAG_NAME, "a")
                        ep_list = []
                        for ep_a in ep_a_tags:
                            ep_title2 = ep_a.text.strip()
                            ep_href2 = ep_a.get_attribute("href")
                            if ep_href2:
                                ep_list.append((ep_title2, ep_href2))

                        for ep_title2, ep_href2 in ep_list:
                            play_url2 = urljoin(base_url, ep_href2)
                            try:
                                driver.get(play_url2)
                                WebDriverWait(driver, 8).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, "iframe#playiframe"))
                                )
                                iframe_elem = driver.find_element(By.CSS_SELECTOR, "iframe#playiframe")
                                driver.switch_to.frame(iframe_elem)
                                try:
                                    inner_iframe_elem = driver.find_element(By.TAG_NAME, "iframe")
                                    driver.switch_to.frame(inner_iframe_elem)
                                except Exception:
                                    pass
                                WebDriverWait(driver, 5).until(
                                    EC.presence_of_element_located((By.TAG_NAME, "video"))
                                )
                                real_video_url = driver.execute_script(
                                    "return document.querySelector('video') && document.querySelector('video').currentSrc;"
                                )
                                driver.switch_to.default_content()
                                print(f"分集:{ep_title2} 线路:{tab_info['name']}({ul_id}) 链接:{play_url2} 视频源:{real_video_url}")

                                # 存库，带上线路名/ul_id
                                try:
                                    c.execute("SELECT id FROM episode WHERE anime_id=? AND title=? AND play_url=? AND line_id=?",
                                              (anime_id, ep_title2, play_url2, ul_id))
                                    if not c.fetchone():
                                        c.execute(
                                            "INSERT INTO episode (anime_id, title, play_url, video_src, real_video_url, line_id) VALUES (?, ?, ?, ?, ?, ?)",
                                            (anime_id, ep_title2, play_url2, real_video_url, real_video_url, ul_id)
                                        )
                                        conn.commit()
                                except Exception as db_e:
                                    print(f"插入episode表出错: {db_e}，anime_id={anime_id}, title={ep_title2}, play_url={play_url2}, line_id={ul_id}")
                            except Exception as e:
                                print(f"采集失败: {tab_info['name']} {ep_title2} {play_url2}，原因: {e}")
                                try:
                                    driver.switch_to.default_content()
                                except Exception:
                                    pass
                                continue  # 只跳过当前分集
                # --------- 分集采集逻辑结束 ---------
            except Exception as e:
                print(f"采集详情页或分集时出错，跳过: {name}，错误：{e}")
                continue  # 跳到下一个li
            time.sleep(1)
        time.sleep(2)
finally:
    try:
        driver.quit()
    except Exception:
        pass
    conn.close()