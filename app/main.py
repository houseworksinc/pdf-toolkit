from flask import jsonify
from app import app

# Register blueprints
from app.api import (
    auth_bp,
    pdf_bp,
    logs_bp,
    webhook_bp,
    split_pdf_bp,
    merge_pdf_bp,
    zip_files_bp,
    process_and_merge_bp,
    process_and_zip_bp,
    convert_docx_bp,
    cancel_job_bp,
)

app.register_blueprint(auth_bp)
app.register_blueprint(pdf_bp)
app.register_blueprint(logs_bp)
app.register_blueprint(webhook_bp)
app.register_blueprint(split_pdf_bp)
app.register_blueprint(merge_pdf_bp)
app.register_blueprint(zip_files_bp)
app.register_blueprint(process_and_merge_bp)
app.register_blueprint(process_and_zip_bp)
app.register_blueprint(convert_docx_bp)
app.register_blueprint(cancel_job_bp)


@app.route("/", methods=["GET"])
def hello_world():
    """Health check endpoint"""
    return jsonify({"message": "Hello, World!"})


@app.before_request
def initialize_database():
    """Initialize database on first request"""
    if not hasattr(app, "db_initialized"):
        from app.database import init_db

        init_db()
        app.db_initialized = True


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
