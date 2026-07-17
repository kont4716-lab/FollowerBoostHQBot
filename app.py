from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return """
    <h1>مرحباً بك</h1>
    <p>هذا أول موقع لنا.</p>
    """

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=10000
    )
