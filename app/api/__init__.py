from app.api.auth import auth_bp
from app.api.pdf_generation import pdf_bp
from app.api.logs import logs_bp
from app.api.webhook import webhook_bp
from app.api.split_pdf import split_pdf_bp
from app.api.merge_pdf import merge_pdf_bp
from app.api.zip_files import zip_files_bp
from app.api.process_and_merge import process_and_merge_bp
from app.api.process_and_zip import process_and_zip_bp
from app.api.convert_docx import convert_docx_bp
from app.api.cancel_job import cancel_job_bp

__all__ = [
    "auth_bp",
    "pdf_bp",
    "logs_bp",
    "webhook_bp",
    "split_pdf_bp",
    "merge_pdf_bp",
    "zip_files_bp",
    "process_and_merge_bp",
    "process_and_zip_bp",
    "convert_docx_bp",
    "cancel_job_bp",
]
