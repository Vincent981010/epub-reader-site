import os
from flask import Flask, request, jsonify, render_template, session

app = Flask(__name__)
app.secret_key = 'your_secret_key'
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

books_db = []

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
            books_db.append({"id": str(len(books_db)+1), "title": file.filename, "file_url": f"/static/uploads/{file.filename}"})
    return jsonify({"status": "success"}), 200

@app.route('/books/delete', methods=['POST'])
def delete_books():
    data = request.get_json()
    ids = data.get('ids', [])
    global books_db
    books_db = [b for b in books_db if b['id'] not in ids]
    return jsonify({"status": "deleted"}), 200

@app.route('/user/status', methods=['GET'])
def get_user_status():
    return jsonify(session.get('user', {"logged_in": False}))

if __name__ == '__main__':
    app.run(debug=True)