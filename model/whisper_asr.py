from faster_whisper import WhisperModel

model = WhisperModel("base")

def transcribe_audio(file_path):
    segments, _ = model.transcribe(file_path)
    return " ".join([seg.text for seg in segments])
