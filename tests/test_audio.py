import wave

from voice_agent_eval_lab import audio


def test_synth_speech_writes_playable_wav(tmp_path):
    path = tmp_path / "turn.wav"
    duration_ms = audio.synth_speech("Hello there, how can I help?", path, voice="cascade")

    assert path.is_file()
    with wave.open(str(path), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getframerate() == audio.SAMPLE_RATE
        actual_ms = 1000 * wav_file.getnframes() / wav_file.getframerate()
        assert abs(actual_ms - duration_ms) < 1.0


def test_synth_speech_is_deterministic(tmp_path):
    path_a = tmp_path / "a.wav"
    path_b = tmp_path / "b.wav"
    audio.synth_speech("Same text", path_a, voice="cascade")
    audio.synth_speech("Same text", path_b, voice="cascade")
    assert path_a.read_bytes() == path_b.read_bytes()


def test_longer_text_yields_longer_audio():
    short = audio.estimate_duration_ms("Hi")
    long = audio.estimate_duration_ms("This is a much longer sentence than the other one.")
    assert long > short
