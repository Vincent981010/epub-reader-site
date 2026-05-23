import os
import io
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, session, send_file
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'any_secret_key_for_session_security')

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    url = DATABASE_URL or "你的_NEON_CONNECTION_STRING_貼在這裡"
    conn = psycopg2.connect(url, sslmode='require')
    return conn

# ==========================================
#  🗄️ 資料庫架構升級 (支援使用者、權限與時效)
# ==========================================
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. 建立「使用者」表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_admin BOOLEAN DEFAULT FALSE
        )
    ''')
    
    # 2. 建立「書籍系列」表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS series (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        )
    ''')
    
    # 3. 建立「書籍」表（新增 user_id 歸屬，以及 expires_at 處理過期）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS books (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            series_id INTEGER REFERENCES series(id) ON DELETE SET NULL,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP WITH TIME ZONE
        )
    ''')
    
    # 4. 建立「章節」表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chapters (
            id SERIAL PRIMARY KEY,
            book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            content TEXT NOT NULL
        )
    ''')
    
    # 建立系統基本預設值
    cursor.execute("INSERT INTO series (name) VALUES ('未分類書籍') ON CONFLICT DO NOTHING")
    
    # 🌟 自動建立公開管理員帳號 (帳號: admin / 密碼: admin123)
    admin_username = "admin"
    admin_password = generate_password_hash("admin123")
    cursor.execute('''
        INSERT INTO users (username, password_hash, is_admin)
        VALUES (%s, %s, TRUE)
        ON CONFLICT (username) DO NOTHING
    ''', (admin_username, admin_password))
    
    conn.commit()
    cursor.close()
    conn.close()
    print("[Database] 使用者與權限架構初始化完成！")

init_db()

# 🧼 輔助函式：每次查詢前自動刪除過期（超過24小時且未登入）的訪客書籍
def clear_expired_books(cursor):
    now = datetime.now(timezone.utc)
    cursor.execute('DELETE FROM books WHERE expires_at IS NOT NULL AND expires_at < %s', (now,))

# 🌟 修正後的首頁路由：直接讀取檔案，徹底解決網頁變成純文字顯示的問題
@app.route('/')
def index():
    with open('index.html', 'r', encoding='utf-8') as f:
        return f.read()


# ==========================================
#  🔐 註冊 / 登入機制 API
# ==========================================

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    if not username or not password:
        return jsonify({"error": "帳號密碼不能為空"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        hashed_password = generate_password_hash(password)
        cursor.execute('INSERT INTO users (username, password_hash) VALUES (%s, %s)', (username, hashed_password))
        conn.commit()
        return jsonify({"success": True, "message": "註冊成功！"})
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "這個帳號已經有人註冊囉！"}), 400
    finally:
        cursor.close()
        conn.close()

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if user and check_password_hash(user['password_hash'], password):
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['is_admin'] = user['is_admin']
        return jsonify({
            "success": True, 
            "username": user['username'], 
            "is_admin": user['is_admin']
        })
    return jsonify({"error": "帳號或密碼錯誤"}), 401

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"success": True, "message": "已登出"})

@app.route('/user/status', methods=['GET'])
def user_status():
    if 'user_id' in session:
        return jsonify({
            "logged_in": True, 
            "username": session['username'], 
            "is_admin": session['is_admin']
        })
    return jsonify({"logged_in": False})


# ==========================================
#  📚 書籍清單獲取 (分流權限)
# ==========================================

@app.route('/books', methods=['GET'])
def get_books():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # 先清理資料庫中過期的臨時訪客書籍
    clear_expired_books(cursor)
    
    user_id = session.get('user_id')
    
    # 所有人都可以看到管理員(admin)上傳的公開內容
    # 登入者還能額外看到自己上傳的書籍；未登入者只能看到自己未過期的臨時書籍
    if user_id:
        cursor.execute('''
            SELECT books.id, books.title, books.series_id, COALESCE(series.name, '未分類書籍') as series_name,
                   users.username as uploader, (books.expires_at IS NOT NULL) as is_temporary
            FROM books 
            LEFT JOIN series ON books.series_id = series.id 
            LEFT JOIN users ON books.user_id = users.id
            WHERE books.user_id = %s OR users.is_admin = TRUE
            ORDER BY books.id DESC
        ''', (user_id,))
    else:
        # 未登入狀態：僅看管理員公開書籍
        cursor.execute('''
            SELECT books.id, books.title, books.series_id, COALESCE(series.name, '未分類書籍') as series_name,
                   users.username as uploader, FALSE as is_temporary
            FROM books 
            LEFT JOIN series ON books.series_id = series.id 
            LEFT JOIN users ON books.user_id = users.id
            WHERE users.is_admin = TRUE
            ORDER BY books.id DESC
        ''')
        
    books = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(books)


# ==========================================
#  📥 EPUB 上傳解析與 TXT 下載
# ==========================================

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "沒有上傳檔案"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "未選取檔案"}), 400

    if file and file.filename.endswith('.epub'):
        temp_path = "temp.epub"
        file.save(temp_path)
        
        try:
            book = epub.read_epub(temp_path)
            chapters_to_save = []
            title = "未知書籍"
            
            meta_title = book.get_metadata('DC', 'title')
            if meta_title and len(meta_title) > 0 and len(meta_title[0]) > 0:
                title = meta_title[0][0]
            
            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                    soup = BeautifulSoup(item.get_content(), 'html.parser')
                    title_tag = soup.find(['h1', 'h2', 'h3'])
                    chapter_title = title_tag.get_text() if title_tag else f"章節 {len(chapters_to_save)+1}"
                    
                    paragraphs = [p.get_text().strip() for p in soup.find_all('p') if p.get_text().strip()]
                    chapter_content = "\n\n".join(paragraphs) if paragraphs else soup.get_text()
                    
                    chapters_to_save.append((chapter_title.strip(), chapter_content))
            
            os.remove(temp_path)
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT id FROM series WHERE name = '未分類書籍'")
            default_series_id = cursor.fetchone()[0]
            
            # 判斷登入狀態分配歸屬，未登入設定 24 小時後過期
            current_user_id = session.get('user_id')
            expires_at = None
            if not current_user_id:
                expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
            
            cursor.execute('''
                INSERT INTO books (title, series_id, user_id, expires_at) 
                VALUES (%s, %s, %s, %s) RETURNING id
            ''', (title, default_series_id, current_user_id, expires_at))
            book_id = cursor.fetchone()[0]
            
            for ch_title, ch_content in chapters_to_save:
                cursor.execute('INSERT INTO chapters (book_id, title, content) VALUES (%s, %s, %s)', (book_id, ch_title, ch_content))
                
            conn.commit()
            cursor.close()
            conn.close()
            
            return jsonify({
                "id": book_id, 
                "title": title, 
                "is_temporary": expires_at is not None,
                "message": "上傳成功！未登入書籍將於24小時後自動銷毀。" if not current_user_id else "成功儲存至個人書庫。"
            })
            
        except Exception as e:
            if os.path.exists(temp_path): 
                os.remove(temp_path)
            return jsonify({"error": f"解析失敗: {str(e)}"}), 500

    return jsonify({"error": "不支援的檔案格式"}), 400

# 📥 核心規格：指定書籍轉換下載為符合排版的 TXT 檔
@app.route('/books/<int:book_id>/download/txt', methods=['GET'])
def download_txt(book_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # 抓取書名
    cursor.execute('SELECT title FROM books WHERE id = %s', (book_id,))
    book = cursor.fetchone()
    if not book:
        cursor.close()
        conn.close()
        return "找不到該書籍", 404
        
    # 抓取所有章節
    cursor.execute('SELECT title, content FROM chapters WHERE book_id = %s ORDER BY id ASC', (book_id,))
    chapters = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    # 📊 依照要求格式精準組合：
    # 章節標題
    # 內文
    txt_content = ""
    for ch in chapters:
        txt_content += f"{ch['title']}\n"
        txt_content += f"{ch['content']}\n\n"
        
    # 將文字轉成記憶體串流供 Flask 送出下載
    buffer = io.BytesIO()
    buffer.write(txt_content.encode('utf-8'))
    buffer.seek(0)
    
    filename = f"{book['title']}.txt"
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype='text/plain'
    )


# ==========================================
#  🔧 系列 (Series) 與 書籍移動 API (管理員專屬)
# ==========================================

@app.route('/series', methods=['GET', 'POST'])
def handle_series():
    if request.method == 'GET':
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('SELECT * FROM series ORDER BY id ASC')
        series_list = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(series_list)
        
    elif request.method == 'POST':
        # 👑 保護功能：只有管理員能建立系列分類
        if not session.get('is_admin'):
            return jsonify({"error": "權限不足，只有管理員可以變更系列設定"}), 403
            
        data = request.get_json()
        name = data.get('name', '').strip()
        if not name: return jsonify({"error": "名稱不能為空"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO series (name) VALUES (%s) RETURNING id', (name,))
            series_id = cursor.fetchone()[0]
            conn.commit()
            return jsonify({"id": series_id, "name": name})
        except psycopg2.errors.UniqueViolation:
            return jsonify({"error": "系列已存在"}), 400
        finally:
            cursor.close()
            conn.close()

@app.route('/books/<int:book_id>/move', methods=['PUT'])
def move_book_series(book_id):
    if not session.get('is_admin'):
        return jsonify({"error": "權限不足，只有系統管理員能移動書籍櫃位"}), 403
        
    data = request.get_json()
    series_id = data.get('series_id')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE books SET series_id = %s WHERE id = %s', (series_id, book_id))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True})

@app.route('/books/<int:book_id>', methods=['GET'])
def get_book_detail(book_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute('SELECT title FROM books WHERE id = %s', (book_id,))
    book_info = cursor.fetchone()
    if not book_info:
        cursor.close()
        conn.close()
        return jsonify({"error": "找不到書籍"}), 404
        
    cursor.execute('SELECT title, content FROM chapters WHERE book_id = %s ORDER BY id ASC', (book_id,))
    chapters = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify({"title": book_info['title'], "chapters": chapters})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)