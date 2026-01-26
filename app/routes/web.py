# app/routes/web.py
from flask import Blueprint, render_template, request

web = Blueprint("web", __name__)

@web.get("/")
def index():
    # index.html sẽ dùng app.js để tạo job và upload
    return render_template("index.html")

@web.get("/editor")
def editor():
    # job_id lấy từ query (?job=...)
    job_id = request.args.get("job", "")
    return render_template("editor.html", job_id=job_id)

@web.get("/result")
def result():
    job_id = request.args.get("job", "")
    return render_template("result.html", job_id=job_id)
