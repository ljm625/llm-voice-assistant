import pyaudio
import webrtcvad
import wave
import requests
import io
from openai import OpenAI
import json
import edge_tts
import subprocess
import yaml
# Audio configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024
frame_duration = 10
# Initialize PyAudio
audio = pyaudio.PyAudio()

# Open stream
stream = audio.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    frames_per_buffer=CHUNK)

messages = []
message_limit=20

# Initialize VAD
vad = webrtcvad.Vad()
vad.set_mode(1)  # 0: Aggressive filtering, 3: Less aggressive

def is_speech(frame, sample_rate):
    # status = webrtcvad.valid_rate_and_frame_length(sample_rate,int(RATE*frame_duration/1000))
    # print(status)
    return vad.is_speech(frame, sample_rate)

def record_audio():
    frames = []
    recording = False

    # print("Listening for speech...")

    while True:
        frame = stream.read(int(RATE*frame_duration/1000),exception_on_overflow=False)
        # print(frame)

        if is_speech(frame, RATE):
            if not recording:
                # print("Recording started.")
                recording = True
            frames.append(frame)
        else:
            if recording:
                # print("Silence detected, stopping recording.")
                break


    return frames

def save_audio(frames, filename="output.wav"):
    wf = wave.open(filename, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(audio.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()
def save_to_memory(frames):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(audio.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
    buffer.seek(0)
    return buffer

def openai_call(input_message):
    global messages
    client = OpenAI(
    base_url = config["openai_endpoint"],
    api_key=config["openai_api_key"]
    )
    cur_messages = []
    cur_messages.append({"role": "system", "content": 'You are a voice assistant, reply in brief. the input text might have typos caused by voice recognize.'})
    # messages.extend(previous_message)
    while len(messages)>message_limit:
        messages.pop(0)
        messages.pop(0)
    if len(messages) <=message_limit:
        cur_messages.extend(messages)
    cur_messages.append({"role":"user", "content":input_message})
    response = client.chat.completions.create(
    model=config["openai_model"],
    messages=cur_messages,
    )
    print(response.choices[0].message.content)
    messages.append({"role":"user", "content":input_message})
    messages.append({"role":"assistant", "content":response.choices[0].message.content})
    return response.choices[0].message.content

def generate_tts(text):
    communicate = edge_tts.Communicate(text, "zh-CN-XiaoyiNeural")
    communicate.save_sync("./temp.mp3")
    return "./temp.mp3"

def play_mp3(file_name):
    with subprocess.Popen(
    [
        "mpv",
        file_name,
    ]
    ) as process:
        process.communicate()
def load_config(name):
    with open(name) as file:
        config = yaml.load(file.read(), Loader=yaml.FullLoader)
        return config



if __name__ == '__main__':
    config = load_config("config.yml")
    try:
        while True:
            frames = record_audio()
            if len(frames)< RATE/100:
                # print("Too short, ignore {}".format(len(frames)))
                continue
            else:
                print("Got your message.")
                wave_data = save_to_memory(frames)
                body = {
                    "file":("output.wav",wave_data,"audio/wav"),
                    "response_format":"json",
                    "temperature": "0.0"
                }
                response = requests.post(config["whisper_cpp_server"],files=body)
                if response.status_code == 200:
                    print(response.text)
                    data = json.loads(response.text)
                    result = openai_call(data["text"])
                    location = generate_tts(result)
                    play_mp3(location)
                else:
                    print(response.status_code)
                    print(response.text)

                # Stop and close the stream
    except Exception as e:
        print(e)
        print("Caught exception, quitting")
        stream.stop_stream()
        stream.close()
        audio.terminate()

