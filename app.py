from flask import Flask, jsonify, request
from src.info import process_bill_url
from src.dub import dub
from urllib.parse import unquote
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

@app.route('/info/<path:url>', methods=['GET'])
def info(url):

    print(url)
    decoded_url = unquote(url)

    print(decoded_url)

    result = process_bill_url(decoded_url)

    if 'error' in result:
        return jsonify(result), 500
    else:
        return jsonify(result)

@app.route('/dub', methods=['POST'])
def dub_endpoint():
    try:
        data = request.get_json()
        file_url = data['file_url']
        name = data['name']
        target_lang = data['target_lang']

        dub(file_url,name,target_lang)

        return jsonify({'status': 'ok'})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)