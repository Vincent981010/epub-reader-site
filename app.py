import os
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

# 設定上傳路徑
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 進入首頁
@app.route('/')
def index():
    return render_template('index.html')

# 取得書籍列表 (回傳範例資料)
@app.route('/books', methods=['GET'])
def get_books():
    # 這裡未來連接你的資料庫
    return jsonify([
        {"id": "1", "title": "測試書籍1.epub", "file_url": "/static/uploads/test1.epub", "series_name": "範例分類"}
    ])

# 多檔案上傳
@app.route('/upload', methods=['POST'])
def upload():
    files = request.files.getlist('file')
    for file in files:
        if file and file.filename.endswith('.epub'):
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], file.filename))
    return jsonify({"message": "success"}), 200

# 批次刪除書籍
@app.route('/books/delete', methods=['POST'])
def delete_books():
    data = request.get_json()
    ids = data.get('ids', [])
    print(f"Server received delete request for IDs: {ids}")
    # 這裡執行資料庫刪除邏輯
    return jsonify({"message": f"Deleted {len(ids)} books"}), 200

# 修改分類
@app.route('/books/update_category', methods=['POST'])
def update_category():
    data = request.get_json()
    # 更新資料庫邏輯
    return jsonify({"message": "updated"}), 200

if __name__ == '__main__':
    app.run(debug=True)