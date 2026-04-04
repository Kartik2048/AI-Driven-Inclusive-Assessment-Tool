import os
import google.generativeai as genai
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configure Gemini API
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

if not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY not found in environment variables. Please add it to .env file")
    raise ValueError("Missing GEMINI_API_KEY. Please set it in your .env file")

genai.configure(api_key=GEMINI_API_KEY)

def evaluate_written_answer(student_answer, question):
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')

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

        response = model.generate_content(prompt)
        result = response.text.strip()

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

    except Exception as e:
        logger.error(f"Evaluation error: {str(e)}")
        return {
            "score": "N/A",
            "grade": "N/A",
            "feedback": "Unable to evaluate the answer. Please try again.",
            "model_answer": "Not available",
            "word_count": len(student_answer.split())
        }

