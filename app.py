import os
from flask import Flask, request, jsonify, render_template
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__, template_folder='.')

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    url = DATABASE_URL or "你的_NEON_CONNECTION_STRING_貼在這裡"
    conn = psycopg2.connect(url, sslmode='require')
    return conn

# 初始化升級版資料庫架構
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. 建立「書籍系列」表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS series (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        )
    ''')
    
    # 2. 建立「書籍」表（關聯到系列 id）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS books (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            series_id INTEGER REFERENCES series(id) ON DELETE SET NULL
        )
    ''')
    
    # 3. 建立「章節」表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chapters (
            id SERIAL PRIMARY KEY,
            book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            content TEXT NOT NULL
        )
    ''')
    
    # 建立預設的「未分類」系列
    cursor.execute("INSERT INTO series (name) VALUES ('未分類書籍') ON CONFLICT DO NOTHING")
    
    conn.commit()
    cursor.close()
    conn.close()

@app.route('/')
def index():
    return render_template('index.html')

# === 系列系列 (Series) API ===

# 獲取所有系列標籤頁清單
@app.route('/series', methods=['GET'])
def get_series():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute('SELECT * FROM series ORDER BY id ASC')
    series_list = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(series_list)

# 自訂建立新系列標籤（例如：使用者自己建立「哈利波特」）
@app.route('/series', methods=['POST'])
def create_series():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({"error": "系列名稱不能為空"}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO series (name) VALUES (%s) RETURNING id', (name,))
        series_id = cursor.fetchone()[0]
        conn.commit()
        return jsonify({"id": series_id, "name": name})
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "此系列已存在"}), 400
    finally:
        cursor.close()
        conn.close()

# 編輯修改系列名稱
@app.route('/series/<int:series_id>', methods=['PUT'])
def update_series(series_id):
    data = request.get_json()
    new_name = data.get('name', '').strip()
    if not new_name:
        return jsonify({"error": "系列名稱不能為空"}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE series SET name = %s WHERE id = %s', (new_name, series_id))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True})

# === 書籍 (Books) API ===

# 獲取所有書籍（包含其系列名稱）
@app.route('/books', methods=['GET'])
def get_books():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute('''
        SELECT books.id, books.title, books.series_id, COALESCE(series.name, '未分類書籍') as series_name 
        FROM books 
        LEFT JOIN series ON books.series_id = series.id 
        ORDER BY books.id DESC
    ''')
    books = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(books)

# 更改書籍所屬的系列標籤（自由編輯分類）
@app.route('/books/<int:book_id>/move', methods=['PUT'])
def move_book_series(book_id):
    data = request.get_json()
    series_id = data.get('series_id') # 如果是 null 就代表移到未分類
    
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
    
    cursor.execute('''
        SELECT books.title, COALESCE(series.name, '未分類書籍') as series_name 
        FROM books LEFT JOIN series ON books.series_id = series.id WHERE books.id = %s
    ''', (book_id,))
    book_info = cursor.fetchone()
    
    cursor.execute('SELECT title, content FROM chapters WHERE book_id = %s ORDER BY id ASC', (book_id,))
    chapters = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return jsonify({"title": book_info['title'], "series_name": book_info['series_name'], "chapters": chapters})

# 上傳書籍（預設歸入「未分類書籍」，隨後使用者可在網頁上自由調整）
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
            title = book.get_metadata('DC', 'title')[0][0] if book.get_metadata('DC', 'title') else "未知書籍"
            
            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                    soup = BeautifulSoup(item.get_content(), 'html.parser')
                    title_tag = soup.find(['h1', 'h2', 'h3'])
                    chapter_title = title_tag.get_text() if title_tag else f"章節 {len(chapters_to_save)+1}"
                    chapters_to_save.append((chapter_title.strip(), soup.get_text()))
            
            os.remove(temp_path)
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # 找到「未分類書籍」的 ID 作為預設值
            cursor.execute("SELECT id FROM series WHERE name = '未分類書籍'")
            default_series_id = cursor.fetchone()[0]
            
            cursor.execute('INSERT INTO books (title, series_id) VALUES (%s, %s) RETURNING id', (title, default_series_id))
            book_id = cursor.fetchone()[0]
            
            for ch_title, ch_content in chapters_to_save:
                cursor.execute('INSERT INTO chapters (book_id, title, content) VALUES (%s, %s, %s)', (book_id, ch_title, ch_content))
                
            conn.commit()
            cursor.close()
            conn.close()
            
            return jsonify({"id": book_id, "title": title, "series_id": default_series_id, "series_name": "未分類書籍", "chapters": [{"title": c[0], "content": c[1]} for c in chapters_to_save]})
            
        except Exception as e:
            if os.path.exists(temp_path): os.remove(temp_path)
            return jsonify({"error": f"解析失敗: {str(e)}"}), 500

    return jsonify({"error": "不支援的檔案格式"}), 400

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)