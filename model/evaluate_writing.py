import os
import google.generativeai as genai
from dotenv import load_dotenv
import logging
import time
import random
import hashlib
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables from project root and override stale shell values.
ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=ROOT_DIR / ".env", override=True)


def _normalize_api_key(raw_value):
    if not raw_value:
        return ""
    return raw_value.strip().strip('"').strip("'")


# Configure Gemini API (support either variable name).
GEMINI_API_KEY = _normalize_api_key(
    os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
)

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    logger.warning("Gemini API key is not set. Writing evaluation will fail until it is configured.")

# Avoid repeated Gemini requests for identical inputs in the same process.
_EVALUATION_CACHE = {}


def _is_rate_limited_error(error):
    error_text = str(error).lower()
    return (
        "429" in error_text
        or "too many requests" in error_text
        or "resource exhausted" in error_text
        or "quota" in error_text
    )


def _is_invalid_api_key_error(error):
    error_text = str(error).lower()
    return (
        "api key not found" in error_text
        or "api_key_invalid" in error_text
        or "api key invalid" in error_text
        or "invalid api key" in error_text
        or "permission denied" in error_text
    )


def _parse_evaluation_result(result, student_answer):
    # Parse the response more robustly
    lines = result.splitlines()

    # Extract score and grade
    score_line = next((line for line in lines if "Score:" in line), "Score: N/A")
    grade_line = next((line for line in lines if "Grade:" in line), "Grade: N/A")

    # Find section indices
    grade_index = lines.index(grade_line) if grade_line in lines else -1
    model_answer_index = next((i for i, line in enumerate(lines) if "Model Answer:" in line), -1)

    # Extract feedback and model answer with fallbacks
    if grade_index != -1 and model_answer_index != -1:
        feedback = "\n".join(lines[grade_index + 1:model_answer_index]).strip()
        model_answer = "\n".join(lines[model_answer_index + 1:]).strip()
    elif grade_index != -1:
        feedback = "\n".join(lines[grade_index + 1:]).strip()
        model_answer = "Model answer not available"
    else:
        feedback = "Feedback not available"
        model_answer = "Model answer not available"

    # Remove section headers from feedback
    feedback = feedback.replace("Feedback:", "").strip()

    return {
        "score": score_line.replace("Score:", "").strip(),
        "grade": grade_line.replace("Grade:", "").strip(),
        "feedback": feedback,
        "model_answer": model_answer,
        "word_count": len(student_answer.split())
    }

def evaluate_written_answer(student_answer, question):
    try:
        if not GEMINI_API_KEY:
            raise ValueError("Gemini API key is not configured")

        cache_key = hashlib.sha256(f"{question}||{student_answer}".encode("utf-8")).hexdigest()
        if cache_key in _EVALUATION_CACHE:
            return _EVALUATION_CACHE[cache_key]

        model = genai.GenerativeModel('gemini-2.5-flash')

        # Update prompt to be more explicit about required format
        prompt = (
            f"You are an AI tutor evaluating a student's spoken or written answer. "
            f"Here is the question:\n\n{question}\n\n"
            f"Here is the student's answer:\n\n{student_answer}\n\n"
            f"Please evaluate and provide ALL of the following sections:\n"
            f"1. A score out of 100 based on relevance, completeness, and clarity.\n"
            f"2. A grade (A+, A, B, C, D, or F).\n"
            f"3. Specific feedback for improvement.\n"
            f"4. A model answer.\n\n"
            f"You must format your response exactly like this:\n"
            f"Score: <score>/100\n"
            f"Grade: <grade>\n"
            f"Feedback: <feedback text>\n"
            f"Model Answer: <model answer>"
        )

        last_error = None
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = model.generate_content(prompt)
                result_text = (response.text or "").strip()
                parsed_result = _parse_evaluation_result(result_text, student_answer)
                _EVALUATION_CACHE[cache_key] = parsed_result
                return parsed_result
            except Exception as e:
                last_error = e
                if not _is_rate_limited_error(e):
                    raise

                if attempt < max_attempts - 1:
                    # Exponential backoff with small jitter for transient 429s.
                    backoff_seconds = (2 ** attempt) + random.uniform(0.1, 0.5)
                    logger.warning(f"Gemini rate-limited, retrying in {backoff_seconds:.2f}s")
                    time.sleep(backoff_seconds)

        raise last_error

    except Exception as e:
        logger.error(f"Evaluation error: {str(e)}")
        if _is_rate_limited_error(e):
            feedback_message = (
                "Gemini API rate limit reached (429 Too Many Requests). "
                "Please wait a minute and try again, or use a key/project with higher quota."
            )
        elif _is_invalid_api_key_error(e):
            feedback_message = (
                "Gemini API key is invalid or unavailable for this project. "
                "Update GEMINI_API_KEY in .env with a valid AI Studio key and restart the app."
            )
        else:
            feedback_message = "Unable to evaluate the answer. Please try again."

        return {
            "score": "N/A",
            "grade": "N/A",
            "feedback": feedback_message,
            "model_answer": "Not available",
            "word_count": len(student_answer.split())
        }
