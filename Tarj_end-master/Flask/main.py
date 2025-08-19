from flask import Flask


app = Flask(__name__)

app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB
from views import *


if __name__ == "__main__":
    app.run(debug=True)
