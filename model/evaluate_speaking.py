import os
import logging
import azure.cognitiveservices.speech as speechsdk

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def azure_transcribe_audio(audio_path, subscription_key, region):
    """Transcribe audio using plain speech recognition (no reference text guidance)."""
    try:
        if not subscription_key or not region:
            raise ValueError("AZURE_SPEECH_KEY and AZURE_SPEECH_REGION are required")
        if not os.path.exists(audio_path):
            raise ValueError(f"Audio file not found: {audio_path}")
        if os.path.getsize(audio_path) == 0:
            raise ValueError("Audio file is empty")

        speech_config = speechsdk.SpeechConfig(subscription=subscription_key, region=region)
        audio_config = speechsdk.audio.AudioConfig(filename=audio_path)
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config,
            language="en-US"
        )
        result = recognizer.recognize_once()

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            return {
                "Transcript": (result.text or "").strip(),
                "Error": ""
            }

        if result.reason == speechsdk.ResultReason.NoMatch:
            return {
                "Transcript": "",
                "Error": "Azure could not recognize any speech from the audio."
            }

        if result.reason == speechsdk.ResultReason.Canceled:
            cancellation = speechsdk.CancellationDetails(result)
            return {
                "Transcript": "",
                "Error": (
                    f"Azure canceled transcription. reason={cancellation.reason}, "
                    f"code={cancellation.error_code}, details={cancellation.error_details}"
                )
            }

        return {
            "Transcript": "",
            "Error": f"Unexpected Azure result reason: {result.reason}"
        }
    except Exception as e:
        logger.error(f"Azure transcription error: {str(e)}")
        return {
            "Transcript": "",
            "Error": str(e)
        }

def azure_pronunciation_assessment(audio_path, subscription_key, region, reference_text=""):
    """Assess pronunciation, fluency, and accuracy using Azure Speech Service."""
    try:
        if not subscription_key or not region:
            raise ValueError("AZURE_SPEECH_KEY and AZURE_SPEECH_REGION are required")
        if not os.path.exists(audio_path):
            raise ValueError(f"Audio file not found: {audio_path}")
        if os.path.getsize(audio_path) == 0:
            raise ValueError("Audio file is empty")

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

        error_details = ""
        comments = "Scores are based on Azure Speech Pronunciation Assessment."
        if result.reason == speechsdk.ResultReason.Canceled:
            cancellation = speechsdk.CancellationDetails(result)
            error_details = (
                f"Azure canceled recognition. reason={cancellation.reason}, "
                f"code={cancellation.error_code}, details={cancellation.error_details}"
            )
            comments = error_details
        elif result.reason == speechsdk.ResultReason.NoMatch:
            error_details = "Azure could not recognize any speech from the audio."
            comments = error_details

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
            "Comments": comments,
            "Error": error_details
        }
    except Exception as e:
        logger.error(f"Azure Pronunciation Assessment error: {str(e)}")
        return {
            "Transcript": "",
            "Accuracy": 0.0,
            "Fluency": 0.0,
            "Pronunciation": 0.0,
            "Completeness": 0.0,
            "Words": [],
            "Comments": "Azure assessment failed.",
            "Error": str(e)
        }
