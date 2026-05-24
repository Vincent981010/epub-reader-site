import os
from flask import Flask, request, jsonify, render_template, session
from werkzeug.utils import secure_filename

app = Flask(__name__)
# 請確保 secret_key 設定正確以維護 Session 安全
app.secret_key = 'your_secret_key_here' 
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 記憶體資料庫
users = {}  # 格式: {'username': 'password'}
books_db = []

@app.route('/')
def index():
    return render_template('index.html')

# --- 認證與用戶 API ---
@app.route('/user/status', methods=['GET'])
def get_user_status():
    if 'username' in session:
        return jsonify({'logged_in': True, 'username': session['username'], 'is_admin': True})
    return jsonify({'logged_in': False})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    if users.get(username) == password:
        session['username'] = username
        return jsonify({'status': 'success'})
    return jsonify({'error': '帳號或密碼錯誤'}), 401

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    if username in users:
        return jsonify({'error': '帳號已存在'}), 400
    users[username] = password
    return jsonify({'status': 'success'})

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'status': 'success'})

# --- 書籍管理 API ---
@app.route('/books', methods=['GET'])
def get_books():
    return jsonify(books_db)

@app.route('/upload', methods=['POST'])
def upload():
    # 限制僅登入用戶可上傳
    if 'username' not in session:
        return jsonify({'error': '請先登入'}), 401
    
    files = request.files.getlist('file')
    for file in files:
        if file and (file.filename.endswith('.epub') or file.mimetype == 'application/epub+zip'):
            filename = secure_filename(file.filename)
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            # 產生簡單的 ID 供刪除時辨識
            import uuid
            unique_id = str(uuid.uuid4())[:8]
            
            books_db.append({
                "id": unique_id,
                "title": filename,
                "file_url": f"/static/uploads/{filename}",
                "series_name": "預設分類"
            })
    return jsonify({'status': 'success'})

@app.route('/books/<book_id>', methods=['DELETE'])
def delete_book(book_id):
    # 限制僅登入用戶可刪除
    if 'username' not in session:
        return jsonify({'error': '請先登入'}), 401
        
    global books_db
    book_to_delete = next((b for b in books_db if b["id"] == book_id), None)
    
    if book_to_delete:
        # 從資料庫陣列中移除
        books_db = [b for b in books_db if b["id"] != book_id]
        
        # 嘗試從伺服器本機刪除實體檔案以釋放空間
        try:
            # 移除開頭的斜線，將 /static/uploads/... 轉為相對路徑 static/uploads/...
            file_path = book_to_delete["file_url"].lstrip('/')
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"檔案刪除失敗: {e}")
            
        return jsonify({'status': 'success'})
        
    return jsonify({'error': '找不到該書籍'}), 404

if __name__ == '__main__':
    app.run(debug=True)