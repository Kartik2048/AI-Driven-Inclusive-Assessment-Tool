from faster_whisper import WhisperModel

model = None


def get_model():
    global model

    if model is None:
        model = WhisperModel("base")

    return model

def transcribe_audio(file_path):
    segments, _ = get_model().transcribe(file_path)
    return " ".join([seg.text for seg in segments])
