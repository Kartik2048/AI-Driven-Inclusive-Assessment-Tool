from difflib import SequenceMatcher
from gtts import gTTS
import logging
import os

logger = logging.getLogger(__name__)

def generate_speech(text, output_path):
    """Generate speech from text and save it"""
    try:
        tts = gTTS(text=text, lang='en')
        tts.save(output_path)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        logger.error(f"Error generating speech: {str(e)}")
        return False

def evaluate_speaking_similarity(ref_text, spoken_text):
    """Compare reference and spoken text similarity"""
    similarity = SequenceMatcher(None, ref_text.lower().strip(), spoken_text.lower().strip()).ratio()
    
    # Convert similarity to percentage and grade
    score = round(similarity * 100, 2)
    
    if score >= 90:
        grade = "Excellent"
        feedback = "Outstanding pronunciation and accuracy!"
    elif score >= 75:
        grade = "Good"
        feedback = "Good pronunciation with minor improvements needed."
    elif score >= 60:
        grade = "Satisfactory"
        feedback = "Acceptable, but needs practice for better clarity."
    else:
        grade = "Needs Improvement"
        feedback = "Focus on pronunciation and speaking clearly."
    
    return {
        "score": score,
        "grade": grade,
        "feedback": feedback,
        "reference": ref_text,
        "spoken": spoken_text
    }
