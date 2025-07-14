from flask import Flask, jsonify, request
import sqlite3
import json

app = Flask(__name__)
DB_PATH = 'trees.db'

@app.route('/api/trees', methods=['GET'])
def get_trees():
    user_id = request.args.get('user_id')
    # Реальная реализация: проверка прав, фильтрация по районам
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM trees')
    trees = cursor.fetchall()
    conn.close()
    
    # Преобразование в JSON
    return jsonify([dict(tree) for tree in trees])

@app.route('/api/trees/<tree_id>', methods=['PATCH'])
def update_tree(tree_id):
    data = request.json
    # Реальная реализация: проверка прав
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE trees SET status = ? WHERE id = ?', 
                  (data['status'], tree_id))
    conn.commit()
    conn.close()
    
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(port=5000)
