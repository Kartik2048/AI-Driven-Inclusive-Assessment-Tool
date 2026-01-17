from sentence_transformers import SentenceTransformer, util
from gtts import gTTS
import os
import whisper
import tempfile

model = SentenceTransformer('all-MiniLM-L6-v2')
asr_model = whisper.load_model("base")

def generate_speech(text, output_path):
    """Generate speech from text and save it"""
    try:
        tts = gTTS(text=text, lang='en')
        tts.save(output_path)
        return True
    except Exception as e:
        print(f"Error generating speech: {str(e)}")
        return False

def transcribe_audio(audio_path):
    """Convert speech to text using Whisper"""
    result = asr_model.transcribe(audio_path)
    return result["text"].strip()

def evaluate_speaking_similarity(ref_text, spoken_text):
    """Compare reference and spoken text similarity"""
    ref_emb = model.encode(ref_text, convert_to_tensor=True)
    spoken_emb = model.encode(spoken_text, convert_to_tensor=True)
    similarity = util.cos_sim(ref_emb, spoken_emb).item()
    
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
