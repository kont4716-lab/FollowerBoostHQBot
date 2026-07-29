from flask import Flask, jsonify
from playwright.sync_api import sync_playwright

app = Flask(__name__)

URL = "https://example.com/login"   # غيّر إلى رابط موقعك
PHONE = "0555123456"
PASSWORD = "123456"

@app.route("/")
def home():
    return "Automation Server Running"

@app.route("/run")
def run():
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            page.goto(URL, wait_until="networkidle")

            # عدّل المحددات لتناسب صفحة موقعك
            page.fill('input[name="phone"]', PHONE)
            page.fill('input[name="password"]', PASSWORD)

            page.click('button[type="submit"]')

            page.wait_for_timeout(3000)

            browser.close()

        return jsonify({"success": True})

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
