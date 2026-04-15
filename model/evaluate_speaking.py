import os
import logging
import azure.cognitiveservices.speech as speechsdk

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def azure_pronunciation_assessment(audio_path, subscription_key, region, reference_text=""):
    """Assess pronunciation, fluency, and accuracy using Azure Speech Service."""
    try:
        if not subscription_key or not region:
            raise ValueError("AZURE_SPEECH_KEY and AZURE_SPEECH_REGION are required")

        speech_config = speechsdk.SpeechConfig(subscription=subscription_key, region=region)
        audio_config = speechsdk.audio.AudioConfig(filename=audio_path)
        pronunciation_config = speechsdk.PronunciationAssessmentConfig(
            reference_text=reference_text or "",
            grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
            granularity=speechsdk.PronunciationAssessmentGranularity.Word
        )
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config,
            language="en-US"
        )
        pronunciation_config.apply_to(recognizer)
        result = recognizer.recognize_once()
        recognized_text = result.text.strip() if getattr(result, "text", None) else ""
        pa_result = speechsdk.PronunciationAssessmentResult(result)
        return {
            "Transcript": recognized_text,
            "Accuracy": pa_result.accuracy_score,
            "Fluency": pa_result.fluency_score,
            "Pronunciation": pa_result.pronunciation_score,
            "Completeness": pa_result.completeness_score,
            "Words": [
                {
                    "word": w.word,
                    "accuracy_score": w.accuracy_score,
                    "error_type": w.error_type,
                    "syllables": getattr(w, "syllables", None),
                    "phonemes": getattr(w, "phonemes", None)
                }
                for w in pa_result.words
            ],
            "Comments": "Scores are based on Azure Speech Pronunciation Assessment."
        }
    except Exception as e:
        logger.error(f"Azure Pronunciation Assessment error: {str(e)}")
        print(f"Azure Pronunciation Assessment error: {e}")
        return {
            "Transcript": "",
            "Accuracy": 0.0,
            "Fluency": 0.0,
            "Pronunciation": 0.0,
            "Completeness": 0.0,
            "Words": [],
            "Comments": "Azure assessment failed."
        }
