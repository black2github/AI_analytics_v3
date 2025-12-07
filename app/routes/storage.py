# app/routes/storage.py
import logging

from fastapi import APIRouter

from app.utils.find_huge_documents import find_huge_documents, analyze_document_distribution

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/storage/analyze-sizes")
def analyze_document_sizes():
    """Анализ размеров документов в хранилище"""
    logger.info("[analyze_document_sizes] <-.")
    try:
        # Вызываем функцию и захватываем вывод
        import io
        import sys

        captured_output = io.StringIO()
        sys.stdout = captured_output

        large_docs = find_huge_documents(min_chars=10000, top_n=20)
        analyze_document_distribution()

        sys.stdout = sys.__stdout__
        output = captured_output.getvalue()
        logger.info("[analyze_document_sizes] -> ...")
        return {
            "status": "success",
            "large_documents": large_docs,
            "console_output": output
        }
    except Exception as e:
        logger.error("[analyze_document_sizes] %s", str(e))
        return {"status": "error", "message": str(e)}