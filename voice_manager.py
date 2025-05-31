
import speech_recognition as sr
import pyttsx3
import time

class VoiceHandler:
    def __init__(self):
        self.engine = None
        try:
            self.engine = pyttsx3.init()
            voices = self.engine.getProperty('voices')
        except Exception as e:
            print(f"Error initializing TTS engine: {e}. Text-to-speech might not work.")
        
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self._calibrate_microphone()

    def _calibrate_microphone(self):
        with self.microphone as source:
            print("Calibrating microphone for ambient noise...")
            try:
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                print("Calibration complete.")
            except Exception as e:
                print(f"Could not calibrate microphone: {e}")

    def speak(self, text):
        if not text:
            return
        print(f"Assistant: {text}")
        if self.engine:
            try:
                self.engine.say(text)
                self.engine.runAndWait()
            except Exception as e:
                print(f"TTS Error: {e}")
        else:
            print("(TTS Engine not available for speaking)")

    def listen(self, prompt,timeout_seconds=10, phrase_time_limit_seconds=5):
        self.speak(prompt)
        with self.microphone as source:
            print("Listening...")
            try:
                audio = self.recognizer.listen(source, timeout=timeout_seconds, phrase_time_limit=phrase_time_limit_seconds)
                command = self.recognizer.recognize_google(audio)
                print(f"You said: {command}")
                return command.lower()
            except sr.WaitTimeoutError:
                print("No speech detected within timeout.")
                return None
            except sr.UnknownValueError:
                print("Could not understand audio.")
                return None
            except sr.RequestError as e:
                self.speak(f"Could not request results from Google Speech Recognition service; {e}")
                print(f"API Error: {e}")
                return None
            except Exception as e:
                print(f"An unexpected error occurred during listening: {e}")
                return None