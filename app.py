import os
from flask import Flask, request, jsonify, render_template, session
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # 請更換為更安全的密碼
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 模擬資料庫
users = {}  # {username: password}
books_db = []

@app.route('/')
def index():
    return render_template('index.html')

# --- 認證 API ---
@app.route('/user/status', methods=['GET'])
def get_user_status():
    if 'username' in session:
        return jsonify({'logged_in': True, 'username': session['username']})
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

# --- 書籍 API ---
@app.route('/books', methods=['GET'])
def get_books():
    return jsonify(books_db)

@app.route('/upload', methods=['POST'])
def upload():
    if 'username' not in session:
        return jsonify({'error': '未登入'}), 401
    
    files = request.files.getlist('file')
    for file in files:
        if file and file.filename.endswith('.epub'):
            filename = secure_filename(file.filename)
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            books_db.append({
                "id": str(len(books_db) + 1),
                "title": filename,
                "file_url": f"/static/uploads/{filename}",
                "series_name": "預設分類"
            })
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    app.run(debug=True)