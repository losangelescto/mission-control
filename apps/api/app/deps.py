from app.task_candidate_extraction import AIExtractionInterface, NullAIExtractor


def get_mail_extraction_extractor() -> AIExtractionInterface:
    """Default: no-op AI; tests override this dependency with a mock extractor."""
    return NullAIExtractor()


def get_call_extraction_extractor() -> AIExtractionInterface:
    """Default: no-op AI for call action extraction; tests may override."""
    return NullAIExtractor()
