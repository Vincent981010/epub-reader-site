import os
from flask import Flask, request, jsonify, render_template, session

app = Flask(__name__)
app.secret_key = 'your_secret_key' # 請自行更換為複雜字串
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 模擬資料庫 (建議換成實際資料庫)
books_db = [
    {"id": "1", "title": "範例書籍.epub", "file_url": "/static/uploads/test.epub", "series_name": "預設分類"}
]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/books', methods=['GET'])
def get_books():
    return jsonify(books_db)

@app.route('/upload', methods=['POST'])
def upload():
    files = request.files.getlist('file')
    for file in files:
        if file and file.filename.endswith('.epub'):
            file.save(os.path.join(UPLOAD_FOLDER, file.filename))
            books_db.append({"id": str(len(books_db)+1), "title": file.filename, "file_url": f"/static/uploads/{file.filename}", "series_name": "預設分類"})
    return jsonify({"status": "success"}), 200

@app.route('/books/delete', methods=['POST'])
def delete_books():
    data = request.get_json()
    ids_to_delete = data.get('ids', [])
    global books_db
    # 過濾掉被選取的書籍
    books_db = [b for b in books_db if b['id'] not in ids_to_delete]
    return jsonify({"status": "deleted"}), 200

# 用戶狀態與認證 (配合前端邏輯)
@app.route('/user/status', methods=['GET'])
def get_user_status():
    return jsonify(session.get('user', {"logged_in": False}))

@app.route('/login', methods=['POST'])
def login():
    session['user'] = {"logged_in": True, "username": "User"}
    return jsonify({"status": "success"})

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user', None)
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(debug=True)