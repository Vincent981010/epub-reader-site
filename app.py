import os
import uuid
from flask import Flask, request, jsonify, render_template_string, session, send_file
from flask_session import Session
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

app = Flask(__name__)

# 配置 Session (儲存於伺服器記憶體中)
app.config["SECRET_KEY"] = os.urandom(24)
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# 模擬資料庫 (實際開發建議改用 SQLite 或 PostgreSQL)
USERS = {
    "admin": {"password": "adminpassword", "is_admin": True},
    "user1": {"password": "user1password", "is_admin": False}
}
BOOKS = []
SERIES = ["預設分類"]

# 讀取剛剛寫好的前端網頁內容
with open("index.html", "r", encoding="utf-8") as f:
    INDEX_HTML = f.read()

@app.route('/')
def index():
    return render_template_string(INDEX_HTML)

# 🔐 會員系統 API
@app.route('/user/status', methods=['GET'])
def user_status():
    if "username" in session:
        return jsonify({
            "logged_in": True,
            "username": session["username"],
            "is_admin": session.get("is_admin", False)
        })
    return jsonify({"logged_in": False})

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    
    user = USERS.get(username)
    if user and user["password"] == password:
        session["username"] = username
        session["is_admin"] = user["is_admin"]
        return "", 200
    return "Unauthorized", 401

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    
    if username in USERS:
        return jsonify({"success": False, "error": "帳號已被註冊"}), 400
        
    USERS[username] = {"password": password, "is_admin": False}
    return jsonify({"success": True})

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return "", 200

# 📥 書籍管理 API
@app.route('/books', methods=['GET'])
def get_books():
    return jsonify(BOOKS)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "沒有檔案"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "未選擇檔案"}), 400
        
    if file and file.filename.endswith('.epub'):
        book_id = str(uuid.uuid4())
        # 安全存檔
        upload_dir = "uploads"
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, f"{book_id}.epub")
        file.save(file_path)
        
        # 解析 EPUB 標題
        try:
            epub_book = epub.read_epub(file_path)
            title = epub_book.get_metadata('DC', 'title')[0][0] if epub_book.get_metadata('DC', 'title') else "未知名稱書籍"
        except Exception:
            title = file.filename.rsplit('.', 1)[0]

        is_logged_in = "username" in session
        new_book = {
            "id": book_id,
            "title": title,
            "series_name": SERIES[0], # 預設歸類到第一個分類
            "is_temporary": not is_logged_in,
            "uploader": session["username"] if is_logged_in else "匿名訪客"
        }
        BOOKS.append(new_book)
        return jsonify({"message": f"書籍《{title}》上傳並解析成功！", "book": new_book})
        
    return jsonify({"error": "不支援的檔案格式，請上傳 EPUB"}), 400

# 📥 一鍵導出 TXT API
@app.route('/books/<book_id>/download/txt', methods=['GET'])
def download_txt(book_id):
    book = next((b for b in BOOKS if b["id"] == book_id), None)
    if not book:
        return "Book not found", 404
        
    file_path = os.path.join("uploads", f"{book_id}.epub")
    txt_path = os.path.join("uploads", f"{book_id}.txt")
    
    try:
        # 讀取 EPUB 並將 HTML 內文清洗成純文字
        epub_book = epub.read_epub(file_path)
        full_text = []
        
        for item in epub_book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                soup = BeautifulSoup(item.get_content(), 'html.parser')
                # 簡單過濾掉腳本與樣式
                for script in soup(["script", "style"]):
                    script.decompose()
                full_text.append(soup.get_text())
                
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"📖 書名：{book['title']}\n")
            f.write(f"分流：{book['series_name']}\n")
            f.write("="*30 + "\n\n")
            f.write("\n\n".join(full_text))
            
        return send_file(txt_path, as_attachment=True, download_name=f"{book['title']}.txt")
    except Exception as e:
        return f"轉換失敗: {str(e)}", 500

# 👑 管理員功能 API
@app.route('/series', methods=['POST'])
def create_series():
    if not session.get("is_admin"):
        return jsonify({"error": "權限不足，您不是管理員！"}), 403
        
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "分類名稱不能為空"}), 400
        
    if name in SERIES:
        return jsonify({"error": "該分類已存在"}), 400
        
    SERIES.append(name)
    return jsonify({"name": name})

if __name__ == '__main__':
    app.run(debug=True, port=5000)