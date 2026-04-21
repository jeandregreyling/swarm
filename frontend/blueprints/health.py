import time
from flask import Blueprint, jsonify

health_bp = Blueprint('health', __name__)

_START_TIME = time.time()


@health_bp.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'uptime': round(time.time() - _START_TIME, 1)})
