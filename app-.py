from flask import Flask
app=Flask(__name__)

@app.route("/")
def home():
    return """
    <h1>Video Storage Starter</h1>
    <p>This is a starter single-file Flask app.</p>
    """

if __name__=="__main__":
    app.run(debug=True)
