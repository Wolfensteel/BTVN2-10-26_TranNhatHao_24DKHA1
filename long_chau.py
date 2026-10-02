import os
import re
import time
import random
import sqlite3
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ======================================================================
# CẤU HÌNH CÀO TOÀN BỘ DỮ LIỆU
# ======================================================================
BASE_URL = "https://nhathuoclongchau.com.vn"

# Liệt kê các danh mục con cụ thể để tránh lỗi Timeout ở trang danh mục tổng
CATEGORIES = {
    # --- DƯỢC MỸ PHẨM ---
    "Chăm sóc da mặt": f"{BASE_URL}/duoc-my-pham/cham-soc-da-mat",
    "Hỗ trợ điều trị da mặt": f"{BASE_URL}/duoc-my-pham/ho-tro-dieu-tri-da-mat",
    "Chăm sóc cơ thể": f"{BASE_URL}/duoc-my-pham/cham-soc-co-the",
    "Chăm sóc tóc - da đầu": f"{BASE_URL}/duoc-my-pham/cham-soc-toc-da-dau", 
    "Chăm sóc da vùng mắt": f"{BASE_URL}/duoc-my-pham/cham-soc-da-vung-mat",
    "Mỹ phẩm trang điểm": f"{BASE_URL}/duoc-my-pham/my-pham-trang-diem",
    
    # --- THUỐC ---
    "Thuốc kháng sinh": f"{BASE_URL}/thuoc/thuoc-khang-sinh",
    "Thuốc tiêu hóa": f"{BASE_URL}/thuoc/thuoc-tieu-hoa",
    "Thuốc tim mạch": f"{BASE_URL}/thuoc/thuoc-tim-mach",
    "Thuốc da liễu": f"{BASE_URL}/thuoc/thuoc-da-lieu",
    "Thuốc cơ xương khớp": f"{BASE_URL}/thuoc/thuoc-co-xuong-khop",
    "Thuốc thần kinh": f"{BASE_URL}/thuoc/thuoc-than-kinh-tram-cam",
    "Thuốc giảm đau hạ sốt": f"{BASE_URL}/thuoc/thuoc-giam-dau-ha-sot",
    "Thuốc tai mũi họng": f"{BASE_URL}/thuoc/thuoc-tai-mui-hong",
    "Thuốc mắt": f"{BASE_URL}/thuoc/thuoc-mat",
    # Bạn có thể copy và dán thêm các đường dẫn danh mục con khác từ website vào đây...
}

MAX_PRODUCTS_PER_CATEGORY = None  # None = Cào TẤT CẢ sản phẩm có trong danh mục
MAX_LOAD_MORE = 200               # Số lần bấm nút xem thêm tối đa (200 lần x 24 sp ~ 4800 sp/danh mục)
DB_FILE = "products.db"  
DEBUG_DIR = "debug"
HEADLESS = True                   # Chuyển sang True để không mở giao diện, chạy nhanh và nhẹ máy hơn
PAGE_LOAD_TIMEOUT = 60000
ELEMENT_TIMEOUT = 30000
LOAD_MORE_TIMEOUT = 20000
NETWORK_IDLE_TIMEOUT = 10000
DELAY_MIN, DELAY_MAX = 2.0, 4.0   # Giữ nguyên delay để tránh bị Cloudflare chặn
LOAD_MORE_DELAY_MIN, LOAD_MORE_DELAY_MAX = 2.0, 4.0

SECTION = "#category-page__products-section"
CARD_LINK = f'{SECTION} a[href$=".html"]'
API_HINT = "search-product-service"   

JS_DISTINCT = """([sel, n]) =>
    new Set([...document.querySelectorAll(sel)].map(a => a.getAttribute('href'))).size > n"""

# ======================================================================
# HÀM DATABASE
# ======================================================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cosmetics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            url TEXT UNIQUE,
            name TEXT,
            sku TEXT,
            price_text TEXT,
            price INTEGER,
            original_price INTEGER,
            image TEXT,
            error TEXT
        )
    ''')
    conn.commit()
    return conn

def save_to_db(conn, product):
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO cosmetics 
            (category, url, name, sku, price_text, price, original_price, image, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            product.get("category"), product.get("url"), product.get("name"), 
            product.get("sku"), product.get("price_text"), product.get("price"), 
            product.get("original_price"), product.get("image"), product.get("error")
        ))
        conn.commit()
    except Exception as e:
        print(f"Lỗi khi lưu DB: {e}")

# ======================================================================
# HÀM TIỆN ÍCH & CHE GIẤU BOT
# ======================================================================
def apply_stealth(page):
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
        Object.defineProperty(navigator, 'languages', { get: () => ['vi-VN', 'en-US', 'en'] });
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
    """)

def get_text(page, selector):
    element = page.locator(selector)
    if element.count() == 0: return None
    return element.first.inner_text().strip()

def get_attribute(page, selector, attribute):
    element = page.locator(selector)
    if element.count() == 0: return None
    return element.first.get_attribute(attribute)

def parse_price(text):
    if not text: return None
    digits = re.sub(r"[^\d]", "", text.split("/")[0])
    return int(digits) if digits else None

def wait_page_ready(page):
    page.wait_for_load_state("load", timeout=PAGE_LOAD_TIMEOUT)
    try: page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT)
    except PWTimeout: pass

def random_sleep(low, high):
    time.sleep(random.uniform(low, high))

def human_scroll(page):
    page.evaluate("window.scrollBy(0, window.innerHeight / 2)")
    random_sleep(0.3, 0.8)
    page.evaluate("window.scrollBy(0, -window.innerHeight / 4)")

def save_debug(page, name):
    os.makedirs(DEBUG_DIR, exist_ok=True)
    path = os.path.join(DEBUG_DIR, f"{name}_{int(time.time())}.png")
    try: page.screenshot(path=path, full_page=True)
    except Exception: pass

def extract_slugs(data, out):
    if isinstance(data, dict):
        slug = data.get("slug")
        if isinstance(slug, str) and slug.endswith(".html"): out.append(slug)
        for v in data.values(): extract_slugs(v, out)
    elif isinstance(data, list):
        for v in data: extract_slugs(v, out)

def launch_browser(playwright):
    browser = playwright.chromium.launch(headless=HEADLESS, args=["--disable-blink-features=AutomationControlled"])
    context = browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
    page = context.new_page()
    apply_stealth(page)
    return browser, context, page

# ======================================================================
# THU THẬP LINK & CÀO CHI TIẾT
# ======================================================================
def collect_product_links(page, category_url, max_products):
    links = {}        
    api_slugs = []

    def on_response(resp):
        if API_HINT in resp.url:
            try: extract_slugs(resp.json(), api_slugs)
            except Exception: pass  

    page.on("response", on_response)

    def harvest():
        try: hrefs = page.locator(CARD_LINK).evaluate_all("els => els.map(e => e.getAttribute('href'))")
        except Exception: hrefs = []
        for h in hrefs:
            if h: links.setdefault(urljoin(BASE_URL, h.strip()), None)
        for s in api_slugs: links.setdefault(urljoin(BASE_URL + "/", s.lstrip("/")), None)
        return len(links)

    def dom_distinct():
        return page.evaluate("sel => new Set([...document.querySelectorAll(sel)].map(a => a.getAttribute('href'))).size", CARD_LINK)

    try:
        page.goto(category_url, timeout=PAGE_LOAD_TIMEOUT)
        wait_page_ready(page)
        page.locator(CARD_LINK).first.wait_for(timeout=ELEMENT_TIMEOUT)

        for round_no in range(1, MAX_LOAD_MORE + 1):
            total = harvest()
            print(f"  Vòng {round_no}: đã tìm thấy {total} link...")
            if max_products and total >= max_products: break
            
            human_scroll(page)
            load_more = page.locator(f"{SECTION} button", has_text=re.compile(r"Xem thêm\s*\d+\s*sản phẩm"))
            if load_more.count() == 0: 
                print("  Hết nút 'Xem thêm'. Đã tải toàn bộ danh mục này.")
                break
            
            before_dom = dom_distinct()
            btn = load_more.first
            btn.scroll_into_view_if_needed()
            random_sleep(0.5, 1.0)
            btn.click()
            
            try: 
                page.wait_for_function(JS_DISTINCT, arg=[CARD_LINK, before_dom], timeout=LOAD_MORE_TIMEOUT)
            except PWTimeout:
                if harvest() <= total: 
                    print("  Không tải thêm được, chuyển sang cào chi tiết.")
                    break
            random_sleep(LOAD_MORE_DELAY_MIN, LOAD_MORE_DELAY_MAX)
            
        harvest()  
    finally:
        page.remove_listener("response", on_response)

    result = list(links)
    return result[:max_products] if max_products else result

def scrape_product(page, url):
    page.goto(url, timeout=PAGE_LOAD_TIMEOUT)
    wait_page_ready(page)
    try: page.locator('[data-test="product_name"]').first.wait_for(timeout=ELEMENT_TIMEOUT)
    except PWTimeout:
        save_debug(page, "product_fail")
        raise
    human_scroll(page)
    price_text = get_text(page, '[data-test="price"]')
    original_text = get_text(page, '[data-test="strike_price"]')

    return {
        "url": page.url,
        "name": get_text(page, '[data-test="product_name"]') or get_text(page, "h1"),
        "sku": get_text(page, '[data-test-id="sku"]'),
        "price_text": price_text,
        "price": parse_price(price_text),
        "original_price": parse_price(original_text),
        "image": get_attribute(page, 'meta[property="og:image"]', "content"),
        "error": None,
    }

# ======================================================================
# CHƯƠNG TRÌNH CHÍNH
# ======================================================================
def main():
    db_conn = init_db()
    
    with sync_playwright() as p:
        print("BƯỚC 1: THU THẬP LINK TẤT CẢ SẢN PHẨM (Có thể mất nhiều thời gian)...")
        all_links_with_category = []
        
        for category_name, category_url in CATEGORIES.items():
            print(f"\n--- Đang xử lý: {category_name} ---")
            browser, context, page = launch_browser(p)
            try:
                cat_links = collect_product_links(page, category_url, MAX_PRODUCTS_PER_CATEGORY)
                for link in cat_links:
                    all_links_with_category.append((link, category_name))
                print(f"-> Chốt {len(cat_links)} link từ {category_name}")
            except Exception as e:
                print(f"-> Lỗi danh mục {category_name}: {e}")
            finally:
                browser.close()

        total_links = len(all_links_with_category)
        print(f"\n✅ TỔNG CỘNG: {total_links} sản phẩm cần cào dữ liệu.\n")

        print("BƯỚC 2: CÀO CHI TIẾT TỪNG SẢN PHẨM VÀ LƯU DATABASE...")
        for i, (url, category_name) in enumerate(all_links_with_category, start=1):
            brw = None
            try:
                brw, ctx, pg = launch_browser(p)
                product = scrape_product(pg, url)
                product["category"] = category_name 
                save_to_db(db_conn, product)  
                
                name = product["name"] or ""
                print(f"[{i}/{total_links}] [{category_name}] Đã lưu - {name[:40]}")
            except Exception as e:
                product = {"category": category_name, "url": url, "error": str(e)[:200]}
                save_to_db(db_conn, product)
                print(f"[{i}/{total_links}] [{category_name}] LỖI - {url}")
            finally:
                if brw: brw.close()
            
            # Cực kỳ quan trọng: Giữ delay để tránh bị khóa IP khi cào hàng nghìn link
            random_sleep(DELAY_MIN, DELAY_MAX)

    db_conn.close()
    print(f"\n✅ Hoàn thành toàn bộ tiến trình! Dữ liệu nằm trong {DB_FILE}")

if __name__ == "__main__":
    main()