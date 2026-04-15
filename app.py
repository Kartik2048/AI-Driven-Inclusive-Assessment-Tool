from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, send_from_directory
from model.evaluate_writing import evaluate_written_answer
from model.evaluate_speaking import azure_pronunciation_assessment
from model.evaluate_listening import evaluate_speaking_similarity, generate_speech
from config.mongodb import questions_collection
import os
from functools import wraps
from werkzeug.utils import secure_filename
import random
import logging
import time
import hashlib
import subprocess
import tempfile
import shutil

def convert_to_wav(input_path, output_path):
    try:
        # If the input is already WAV, reuse it directly.
        if os.path.splitext(input_path)[1].lower() == ".wav":
            shutil.copyfile(input_path, output_path)
            return True

        # Use ffmpeg to convert any audio format to wav (mono, 16kHz)
        command = [
            "ffmpeg", "-y", "-i", input_path,
            "-ac", "1", "-ar", "16000", output_path
        ]
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except FileNotFoundError:
        logger.error("ffmpeg is not installed or not available in PATH")
        return False
    except subprocess.CalledProcessError as e:
        stderr_text = e.stderr.decode("utf-8", errors="ignore") if e.stderr else str(e)
        logger.error(f"ffmpeg conversion failed: {stderr_text}")
        return False
    except Exception as e:
        logger.error(f"Audio conversion error: {e}")
        return False

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-secret-key')
UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), "ai-assessment", "uploads", "audio")
TTS_FOLDER = os.path.join(tempfile.gettempdir(), "ai-assessment", "tts")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TTS_FOLDER, exist_ok=True)

# Admin credentials
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Suppress PyMongo debug logs
logging.getLogger("pymongo").setLevel(logging.WARNING)

def handle_model_error(error):
    return {"error": str(error), "message": "Model currently unavailable. Please try again later."}

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            flash('Please login first')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
    
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['is_admin'] = True
            flash('Login successful!')
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials')
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash('Logged out successfully')
    return redirect(url_for('index'))

@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin_dashboard():
    if request.method == "POST":
        try:
            new_question = {
                "question": request.form['question'],
                "type": request.form['type'],
                "topic": request.form['topic'],
                "difficulty": request.form['difficulty'],
                "created_at": time.time()
            }
            questions_collection.insert_one(new_question)
            flash(f"Question added successfully to {new_question['type']} assessment!")
        except Exception as e:
            flash(f"Error adding question: {str(e)}", "error")
    return render_template("admin.html")

def get_random_question_with_fallback():
    """Get random question with fallback to sample questions if MongoDB is unavailable"""
    if questions_collection is None:
        # Fallback questions if MongoDB is unavailable
        fallback_questions = [
            "Describe the importance of renewable energy in modern society.",
            "What are the benefits of exercise for mental health?",
            "How has technology changed education in the last decade?",
            "Discuss the impact of social media on society.",
            "What are the most effective ways to reduce stress?"
        ]
        return {"question": random.choice(fallback_questions)}
    
    try:
        question = questions_collection.aggregate([{ "$sample": { "size": 1 } }])
        return next(question, {"question": "No questions available"})
    except Exception as e:
        logger.error(f"Error fetching question from MongoDB: {str(e)}")
        return {"question": "An error occurred while fetching the question. Please try again."}

@app.route("/writing", methods=["GET", "POST"])
def writing():
    if request.method == "POST":
        try:
            answer = request.form.get("answer")
            question = request.form.get("question")
            if not answer or not question:
                raise ValueError("Answer and question are required")
            
            result = evaluate_written_answer(answer, question)
            return render_template("writing.html", 
                                answer=answer,
                                result=result,
                                current_question=question)
        except Exception as e:
            error_response = handle_model_error(e)
            return render_template("writing.html", error=error_response)
    
    try:
        question = get_random_question_with_fallback()
        return render_template("writing.html", current_question=question["question"])
    except Exception as e:
        error_response = handle_model_error(e)
        return render_template("writing.html", error=error_response)

@app.route("/speaking", methods=["GET", "POST"])
def speaking():
    if request.method == "POST":
        audio_path = None
        converted_path = None
        try:
            if 'audio' not in request.files:
                return jsonify({"error": True, "message": "No audio file received"}), 400
            if 'question' not in request.form:
                return jsonify({"error": True, "message": "No question received"}), 400

            audio_file = request.files['audio']
            question = request.form['question']
            if not audio_file.filename:
                return jsonify({"error": True, "message": "Empty audio file"}), 400

            timestamp = int(time.time())
            source_ext = os.path.splitext(audio_file.filename)[1].lower()
            if source_ext not in {".wav", ".webm", ".mp3", ".m4a", ".ogg", ".mp4"}:
                source_ext = ".webm"

            original_filename = secure_filename(f"original_{timestamp}{source_ext}")
            audio_path = os.path.join(UPLOAD_FOLDER, original_filename)
            os.makedirs(os.path.dirname(audio_path), exist_ok=True)
            audio_file.save(audio_path)

            converted_filename = f"recording_{timestamp}.wav"
            converted_path = os.path.join(UPLOAD_FOLDER, converted_filename)
            if not convert_to_wav(audio_path, converted_path):
                raise ValueError("Failed to convert audio to WAV format")

            # --- Azure Pronunciation Assessment ---
            azure_key = os.environ.get("AZURE_SPEECH_KEY")
            azure_region = os.environ.get("AZURE_SPEECH_REGION")
            if not azure_key or not azure_region:
                raise ValueError("Azure Speech credentials are missing on this deployment")

            speaking_evaluation = azure_pronunciation_assessment(
                converted_path, azure_key, azure_region
            )
            if not speaking_evaluation:
                raise ValueError("Failed to evaluate speaking quality")

            spoken_text = speaking_evaluation.get("Transcript", "")
            if not spoken_text:
                azure_error = speaking_evaluation.get("Error") or speaking_evaluation.get("Comments")
                raise ValueError(f"Failed to transcribe audio. {azure_error}")

            from model.evaluate_writing import evaluate_written_answer
            content_evaluation = evaluate_written_answer(spoken_text, question)

            # Map Azure scores to frontend fields
            result = {
                "transcript": spoken_text,
                "speaking_metrics": {
                    "Fluency and Coherence": speaking_evaluation.get("Fluency", 0.0),
                    "Pronunciation": speaking_evaluation.get("Pronunciation", 0.0),
                    "Overall Band": round(
                        (speaking_evaluation.get("Fluency", 0.0) +
                         speaking_evaluation.get("Pronunciation", 0.0) +
                         speaking_evaluation.get("Accuracy", 0.0) +
                         speaking_evaluation.get("Completeness", 0.0)) / 4, 1
                    ),
                    "Comments": speaking_evaluation.get("Comments", "")
                },
                "content_evaluation": content_evaluation,
                "grade": speaking_evaluation.get("Pronunciation", "N/A"),
                "score": speaking_evaluation.get("Pronunciation", 0)
            }

            # Clean up files
            for path in [audio_path, converted_path]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception as cleanup_error:
                        logger.error(f"Failed to clean up audio file: {cleanup_error}")

            return jsonify(result)

        except Exception as e:
            logger.error(f"Speaking assessment error: {str(e)}")
            for path in [audio_path, converted_path]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception as cleanup_error:
                        logger.error(f"Failed to clean up audio file: {cleanup_error}")
            return jsonify({
                "error": True,
                "message": str(e),
                "details": "Failed to process recording"
            }), 500

    # GET request - return question
    try:
        question = get_random_question_with_fallback()
        return render_template("speaking.html",
                               current_question=question["question"],
                               max_time=90)
    except Exception as e:
        logger.error(f"Error loading speaking assessment: {str(e)}")
        return render_template("speaking.html",
                               error="Failed to load speaking assessment",
                               current_question="Tell me about your favorite book.")

def get_random_listening_question():
    """Get random listening question from MongoDB"""
    try:
        question = questions_collection.aggregate([
            {"$match": {"type": "listening"}},
            {"$sample": {"size": 1}}
        ])
        return next(question, None)
    except Exception as e:
        logger.error(f"Error fetching listening question: {str(e)}")
        return None

@app.route("/listening", methods=["GET", "POST"])
def listening():
    if request.method == "GET":
        try:
            # Get question from MongoDB
            db_question = get_random_listening_question()
            
            # Fallback questions if no MongoDB question found
            if not db_question:
                sample_sentences = [
                    "The quick brown fox jumps over the lazy dog.",
                    "Practice makes perfect.",
                    "Actions speak louder than words.",
                    "Time heals all wounds.",
                    "Better late than never."
                ]
                reference_text = random.choice(sample_sentences)
            else:
                reference_text = db_question["question"]
            
            return render_template("listening.html", reference_text=reference_text)
                
        except Exception as e:
            logger.error(f"Error in listening GET: {str(e)}")
            return render_template("listening.html", error="Failed to load listening assessment")
    
    if request.method == "POST":
        audio_path = None
        converted_path = None
        try:
            if 'audio' not in request.files:
                return jsonify({"error": True, "message": "No audio file received"}), 400
            if 'reference' not in request.form:
                return jsonify({"error": True, "message": "No reference text received"}), 400

            audio_file = request.files['audio']
            reference_text = request.form['reference']
            if not audio_file.filename:
                return jsonify({"error": True, "message": "Empty audio file"}), 400

            timestamp = int(time.time())
            source_ext = os.path.splitext(audio_file.filename)[1].lower()
            if source_ext not in {".wav", ".webm", ".mp3", ".m4a", ".ogg", ".mp4"}:
                source_ext = ".webm"

            original_filename = secure_filename(f"listening_original_{timestamp}{source_ext}")
            audio_path = os.path.join(UPLOAD_FOLDER, original_filename)
            audio_file.save(audio_path)

            converted_filename = secure_filename(f"listening_recording_{timestamp}.wav")
            converted_path = os.path.join(UPLOAD_FOLDER, converted_filename)
            if not convert_to_wav(audio_path, converted_path):
                raise ValueError("Failed to convert listening audio to WAV format")
            
            try:
                azure_key = os.environ.get("AZURE_SPEECH_KEY")
                azure_region = os.environ.get("AZURE_SPEECH_REGION")
                if not azure_key or not azure_region:
                    raise ValueError("Azure Speech credentials are missing on this deployment")

                listening_evaluation = azure_pronunciation_assessment(
                    converted_path,
                    azure_key,
                    azure_region,
                    reference_text
                )
                spoken_text = listening_evaluation.get("Transcript", "")
                if not spoken_text:
                    azure_error = listening_evaluation.get("Error") or listening_evaluation.get("Comments")
                    raise ValueError(f"Azure could not transcribe the audio. {azure_error}")

                result = evaluate_speaking_similarity(reference_text, spoken_text)
                result["azure_metrics"] = {
                    "Accuracy": listening_evaluation.get("Accuracy", 0.0),
                    "Fluency": listening_evaluation.get("Fluency", 0.0),
                    "Pronunciation": listening_evaluation.get("Pronunciation", 0.0),
                    "Completeness": listening_evaluation.get("Completeness", 0.0)
                }
                result["azure_comments"] = listening_evaluation.get("Comments", "")
                
                # Only delete file after successful processing
                for path in [audio_path, converted_path]:
                    if path and os.path.exists(path):
                        os.remove(path)
                
                return jsonify(result)
                
            except Exception as e:
                # Log the error for debugging
                logger.error(f"Processing error: {str(e)}")
                # Clean up file in case of error
                for path in [audio_path, converted_path]:
                    if path and os.path.exists(path):
                        os.remove(path)
                raise
                
        except Exception as e:
            logger.error(f"Error in listening POST: {str(e)}")
            return jsonify({
                "error": True,
                "message": str(e),
                "details": "Failed to process listening recording"
            }), 500

@app.route("/get-random-question")
def get_random_question():
    try:
        question = get_random_question_with_fallback()
        return jsonify({"question": question["question"]})
    except Exception as e:
        return jsonify(handle_model_error(e))

@app.route("/generate-speech", methods=["POST"])
def generate_speech_route():
    try:
        payload = request.get_json(silent=True) or {}
        text = (payload.get('text') or '').strip()
        if not text:
            return jsonify({"error": "No text provided"}), 400

        # Keep TTS input bounded to avoid provider-side failures on long payloads.
        if len(text) > 500:
            text = text[:500]

        # Generate unique filename based on text content
        filename = f"speech_{hashlib.md5(text.encode()).hexdigest()[:10]}.mp3"
        audio_path = os.path.join(TTS_FOLDER, filename)

        try:
            # Generate audio file if it doesn't exist
            if not os.path.exists(audio_path):
                if not generate_speech(text, audio_path):
                    raise RuntimeError("TTS provider failed to create audio")

            if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
                raise RuntimeError("Generated audio file is missing or empty")

            return jsonify({
                "success": True,
                "audio_url": url_for('serve_temp_audio', filename=filename)
            })

        except Exception as e:
            logger.error(f"gTTS error: {str(e)}")
            return jsonify({
                "error": "Text-to-speech generation failed",
                "details": "Unable to generate audio right now. Please retry in a few seconds."
            }), 500

    except Exception as e:
        logger.error(f"Speech generation route error: {str(e)}")
        return jsonify({
            "error": "Server error",
            "details": str(e)
        }), 500

@app.route('/temp-audio/<path:filename>')
def serve_temp_audio(filename):
    return send_from_directory(TTS_FOLDER, filename)

if __name__ == "__main__":
    app.run(debug=True)
