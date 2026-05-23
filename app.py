import os
from flask import Flask, request, jsonify, render_template
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

app = Flask(__name__, template_folder='.')

# 簡單的分類演算法
def auto_classify(text):
    combined_text = text[:3000].lower() # 讀取前 3000 字大綱
    category_keywords = {
        "資訊科學": ["程式", "python", "演算法", "網頁", "code", "編程"],
        "文學小說": ["故事", "主角", "回憶", "轉身", "帝國", "宇宙", "小說"],
        "商業理財": ["投資", "股票", "市場", "管理", "行銷", "資產", "理財"]
    }
    scores = {cat: 0 for cat in category_keywords}
    for cat, keywords in category_keywords.items():
        for word in keywords:
            scores[cat] += combined_text.count(word)
    max_cat = max(scores, key=scores.get)
    return max_cat if scores[max_cat] > 0 else "其他/未分類"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "沒有上傳檔案"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "未選取檔案"}), 400

    if file and file.filename.endswith('.epub'):
        # 暫存檔案以供讀取
        temp_path = "temp.epub"
        file.save(temp_path)
        
        try:
            book = epub.read_epub(temp_path)
            chapters = []
            full_text = ""
            
            title = book.get_metadata('DC', 'title')[0][0] if book.get_metadata('DC', 'title') else "未知書籍"
            
            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                    soup = BeautifulSoup(item.get_content(), 'html.parser')
                    title_tag = soup.find(['h1', 'h2', 'h3'])
                    chapter_title = title_tag.get_text() if title_tag else f"章節 {len(chapters)+1}"
                    
                    chapter_content = soup.get_text()
                    full_text += chapter_content
                    
                    chapters.append({
                        "title": chapter_title.strip(),
                        "content": chapter_content
                    })
            
            category = auto_classify(full_text)
            os.remove(temp_path) # 刪除暫存檔
            
            return jsonify({
                "title": title,
                "category": category,
                "chapters": chapters
            })
            
        except Exception as e:
            if os.path.exists(temp_path): os.remove(temp_path)
            return jsonify({"error": f"解析失敗: {str(e)}"}), 500

    return jsonify({"error": "不支援的檔案格式"}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)