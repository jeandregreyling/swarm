from flask import Flask, Blueprint, jsonify

bp = Blueprint('test', __name__)

@bp.route('/api/test')
def test():
    return jsonify({'ok': True, 'msg': 'Blueprint works'})

app = Flask(__name__)
app.register_blueprint(bp)

@app.route('/')
def root():
    return jsonify({'ok': True, 'msg': 'Root works'})

if __name__ == '__main__':
    app.run(port=5051, debug=True)
