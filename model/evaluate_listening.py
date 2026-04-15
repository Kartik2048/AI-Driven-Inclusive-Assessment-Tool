from sentence_transformers import SentenceTransformer, util
from gtts import gTTS
from faster_whisper import WhisperModel

model = None
asr_model = None


def get_similarity_model():
    global model

    if model is None:
        model = SentenceTransformer('all-MiniLM-L6-v2')

    return model


def get_asr_model():
    global asr_model

    if asr_model is None:
        asr_model = WhisperModel("base")

    return asr_model

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
    segments, _ = get_asr_model().transcribe(audio_path)
    return " ".join(seg.text for seg in segments).strip()

def evaluate_speaking_similarity(ref_text, spoken_text):
    """Compare reference and spoken text similarity"""
    similarity_model = get_similarity_model()
    ref_emb = similarity_model.encode(ref_text, convert_to_tensor=True)
    spoken_emb = similarity_model.encode(spoken_text, convert_to_tensor=True)
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
