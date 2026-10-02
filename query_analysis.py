import sqlite3
import pandas as pd

# Cấu hình Pandas hiển thị đẹp trên terminal
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)
pd.set_option('display.max_colwidth', 60)

DB_FILE = "products.db"

def run_query(title, query, conn, params=()):
    """Hàm chạy truy vấn SQL và in kết quả"""
    print(f"\n{'-'*80}")
    print(f"📌 {title.upper()}")
    print(f"{'-'*80}")
    try:
        # Truyền tham số params để chống SQL Injection và nhận giá trị người dùng nhập
        df = pd.read_sql_query(query, conn, params=params)
        if df.empty:
            print("(Không tìm thấy kết quả phù hợp)")
        else:
            print(df)
    except Exception as e:
        print(f"Lỗi SQL: {e}")

def main():
    conn = sqlite3.connect(DB_FILE)
    
    while True:
        print("\n" + "="*80)
        print("          HỆ THỐNG TRUY VẤN DỮ LIỆU SẢN PHẨM (MENU TƯƠNG TÁC)")
        print("="*80)
        print("1. Tra tên sản phẩm theo ký tự")
        print("2. Lọc sản phẩm theo giá tăng dần")
        print("3. Lọc sản phẩm theo giá giảm dần")
        print("4. Xem số lượng hàng có sẵn của một mặt hàng/thương hiệu")
        print("5. Xem các sản phẩm có giá trong khoảng [A -> B]")
        print("6. Xem các sản phẩm có giá DƯỚI mức [A]")
        print("7. Xem các sản phẩm Đắt nhất / Rẻ nhất trong mỗi danh mục")
        print("0. Thoát chương trình")
        print("="*80)
        
        choice = input("👉 Hãy chọn một chức năng (0-7): ").strip()
        
        if choice == '0':
            print("Đã thoát chương trình. Tạm biệt!")
            break
            
        elif choice == '1':
            keyword = input("Nhập ký tự hoặc tên sản phẩm cần tìm: ").strip()
            q = """
                SELECT category, name, price 
                FROM cosmetics 
                WHERE name LIKE ? AND price IS NOT NULL
                ORDER BY name;
            """
            run_query(f"Kết quả tìm kiếm cho: '{keyword}'", q, conn, (f'%{keyword}%',))
            
        elif choice == '2':
            limit = input("Bạn muốn xem bao nhiêu sản phẩm? (VD: 20): ").strip()
            limit = int(limit) if limit.isdigit() else 20
            q = """
                SELECT name, category, price 
                FROM cosmetics 
                WHERE price IS NOT NULL 
                ORDER BY price ASC 
                LIMIT ?;
            """
            run_query(f"Top {limit} sản phẩm giá TĂNG DẦN (Rẻ nhất)", q, conn, (limit,))
            
        elif choice == '3':
            limit = input("Bạn muốn xem bao nhiêu sản phẩm? (VD: 20): ").strip()
            limit = int(limit) if limit.isdigit() else 20
            q = """
                SELECT name, category, price 
                FROM cosmetics 
                WHERE price IS NOT NULL 
                ORDER BY price DESC 
                LIMIT ?;
            """
            run_query(f"Top {limit} sản phẩm giá GIẢM DẦN (Đắt nhất)", q, conn, (limit,))
            
        elif choice == '4':
            keyword = input("Nhập tên mặt hàng/thương hiệu cần kiểm tra số lượng: ").strip()
            # Đếm những sản phẩm có chứa từ khóa và đang có giá (có sẵn để bán)
            q = """
                SELECT 
                    ? AS tu_khoa_tim_kiem,
                    COUNT(id) AS so_luong_san_pham_co_san
                FROM cosmetics 
                WHERE name LIKE ? AND price IS NOT NULL;
            """
            run_query(f"Kiểm tra số lượng mặt hàng", q, conn, (keyword, f'%{keyword}%'))
            
        elif choice == '5':
            try:
                price_a = int(input("Nhập giá thấp nhất (A): "))
                price_b = int(input("Nhập giá cao nhất (B): "))
                
                # Đảo ngược lại nếu người dùng nhập A lớn hơn B
                if price_a > price_b:
                    price_a, price_b = price_b, price_a
                    
                q = """
                    SELECT name, category, price 
                    FROM cosmetics 
                    WHERE price BETWEEN ? AND ?
                    ORDER BY price ASC;
                """
                run_query(f"Sản phẩm có giá từ {price_a:,}đ đến {price_b:,}đ", q, conn, (price_a, price_b))
            except ValueError:
                print("⚠️ Lỗi: Vui lòng chỉ nhập số (VD: 150000)!")
                
        elif choice == '6':
            try:
                price_a = int(input("Nhập mức giá tối đa (A): "))
                q = """
                    SELECT name, category, price 
                    FROM cosmetics 
                    WHERE price < ? AND price IS NOT NULL
                    ORDER BY price DESC;
                """
                run_query(f"Sản phẩm có giá DƯỚI {price_a:,}đ", q, conn, (price_a,))
            except ValueError:
                print("⚠️ Lỗi: Vui lòng chỉ nhập số!")
                
        elif choice == '7':
            # Gom nhóm bằng GROUP BY và lấy MIN/MAX giá trị để tìm sản phẩm Đắt/Rẻ nhất
            q = """
                SELECT category, 'Sản phẩm Rẻ nhất' AS phan_loai, name, MIN(price) AS price 
                FROM cosmetics 
                WHERE price IS NOT NULL 
                GROUP BY category
                
                UNION ALL
                
                SELECT category, 'Sản phẩm Đắt nhất' AS phan_loai, name, MAX(price) AS price 
                FROM cosmetics 
                WHERE price IS NOT NULL 
                GROUP BY category
                
                ORDER BY category, price;
            """
            run_query("Sản phẩm Đắt nhất / Rẻ nhất theo từng danh mục", q, conn)
            
        else:
            print("⚠️ Lựa chọn không hợp lệ, vui lòng chọn lại (0-7)!")
            
        input("\nẤn Enter để tiếp tục...")

    conn.close()

if __name__ == "__main__":
    main()