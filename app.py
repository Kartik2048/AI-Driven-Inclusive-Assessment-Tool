from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from model.evaluate_writing import evaluate_written_answer
from model.evaluate_listening import evaluate_speaking_similarity, generate_speech, transcribe_audio as transcribe_listening_audio
from model.whisper_asr import transcribe_audio as transcribe_speaking_audio
from config.mongodb import questions_collection
from dotenv import load_dotenv
import os
from functools import wraps
from flask import send_from_directory
from werkzeug.utils import secure_filename
import random
import logging
import time
from gtts import gTTS
import hashlib

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Set Flask secret key from environment variable
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    logging.warning("SECRET_KEY not found in environment variables. Using default (not recommended for production)")
    SECRET_KEY = 'default-secret-key'

app.config['SECRET_KEY'] = SECRET_KEY
UPLOAD_FOLDER = "uploads/audio"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Admin credentials from environment variables
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
        try:
            # Validate request data
            if 'audio' not in request.files:
                raise ValueError("No audio file received")
            if 'question' not in request.form:
                raise ValueError("No question received")
                
            audio_file = request.files['audio']
            question = request.form['question']
            
            # Save uploaded audio with timestamp
            timestamp = int(time.time())
            filename = secure_filename(f"recording_{timestamp}.wav")
            audio_path = os.path.join(UPLOAD_FOLDER, filename)
            
            # Ensure upload directory exists
            os.makedirs(os.path.dirname(audio_path), exist_ok=True)
            
            # Save the audio file
            audio_file.save(audio_path)
            logger.debug(f"Saved audio file to: {audio_path}")
            
            # Process the audio
            spoken_text = transcribe_speaking_audio(audio_path)
            if not spoken_text:
                raise ValueError("Failed to transcribe audio")
            
            logger.debug(f"Transcribed text: {spoken_text}")
            
            # Evaluate the answer
            result = evaluate_written_answer(spoken_text, question)
            if not result:
                raise ValueError("Failed to evaluate answer")
                
            # Add transcription to result
            result['transcript'] = spoken_text
            
            # Clean up the audio file
            try:
                os.remove(audio_path)
                logger.debug("Cleaned up audio file")
            except Exception as e:
                logger.warning(f"Failed to clean up audio file: {str(e)}")
            
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"Speaking assessment error: {str(e)}")
            # Clean up audio file if it exists
            if audio_path and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except:
                    pass
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
            
            # Generate unique filename for audio
            audio_filename = f"reference_{hash(reference_text)}.mp3"
            audio_path = os.path.join(app.root_path, 'static', 'audio', audio_filename)
            
            # Ensure audio directory exists
            os.makedirs(os.path.dirname(audio_path), exist_ok=True)
            
            # Generate audio file
            if generate_speech(reference_text, audio_path):
                return render_template("listening.html", 
                                    reference_text=reference_text,
                                    audio_file=f"audio/{audio_filename}")
            else:
                raise Exception("Failed to generate audio file")
                
        except Exception as e:
            logger.error(f"Error in listening GET: {str(e)}")
            return render_template("listening.html", error="Failed to load listening assessment")
    
    if request.method == "POST":
        try:
            audio_file = request.files['audio']
            reference_text = request.form['reference']
            
            # Create unique filename with timestamp
            timestamp = int(time.time())
            filename = secure_filename(f"recording_{timestamp}.wav")
            audio_path = os.path.join(UPLOAD_FOLDER, filename)
            
            # Save uploaded audio
            audio_file.save(audio_path)
            
            try:
                # Transcribe and evaluate
                spoken_text = transcribe_listening_audio(audio_path)
                result = evaluate_speaking_similarity(reference_text, spoken_text)
                
                # Only delete file after successful processing
                os.remove(audio_path)
                
                return jsonify(result)
                
            except Exception as e:
                # Log the error for debugging
                logger.error(f"Processing error: {str(e)}")
                # Clean up file in case of error
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                raise
                
        except Exception as e:
            logger.error(f"Error in listening POST: {str(e)}")
            return jsonify(handle_model_error(e)), 500

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
        text = request.json.get('text')
        if not text:
            return jsonify({"error": "No text provided"}), 400

        # Create audio directory in static folder
        audio_dir = os.path.join(app.static_folder, 'audio')
        os.makedirs(audio_dir, exist_ok=True)

        # Generate unique filename based on text content
        filename = f"speech_{hashlib.md5(text.encode()).hexdigest()[:10]}.mp3"
        audio_path = os.path.join(audio_dir, filename)

        try:
            # Generate audio file if it doesn't exist
            if not os.path.exists(audio_path):
                tts = gTTS(text=text, lang='en', slow=False)
                tts.save(audio_path)

            return jsonify({
                "success": True,
                "audio_url": url_for('static', filename=f'audio/{filename}')
            })

        except Exception as e:
            logger.error(f"gTTS error: {str(e)}")
            return jsonify({
                "error": "Text-to-speech generation failed",
                "details": str(e)
            }), 500

    except Exception as e:
        logger.error(f"Speech generation route error: {str(e)}")
        return jsonify({
            "error": "Server error",
            "details": str(e)
        }), 500

if __name__ == "__main__":
    app.run(debug=True)

