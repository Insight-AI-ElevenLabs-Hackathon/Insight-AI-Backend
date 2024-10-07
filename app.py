from flask import Flask, jsonify
from info import process_bill_url
from urllib.parse import unquote
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/info/<path:url>', methods=['GET'])
def info(url):

    decoded_url = unquote(url)

    result = process_bill_url(decoded_url)

    if 'error' in result:
        return jsonify(result), 500
    else:
        return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True)