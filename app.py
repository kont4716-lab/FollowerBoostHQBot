from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return """
    <!DOCTYPE html>
    <html lang="ar">
    <head>
        <meta charset="UTF-8">
        <title>رفع الصور</title>
    </head>
    <body style="font-family:Arial;text-align:center;margin-top:50px;">

        <h1>رفع صورة</h1>

        <form enctype="multipart/form-data">
            <input type="file" name="image"><br><br>

            <button type="submit">
                رفع الصورة
            </button>
        </form>

    </body>
    </html>
    """

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
