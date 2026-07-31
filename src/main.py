from __future__ import annotations
import argparse, sys
from datetime import datetime
import numpy as np
import sounddevice as sd
from src.audio import AudioConfig, MicrophoneStream
from src.wakeword import WakeWordConfig, WakeWordDetector

def parse_device(v: str): return int(v) if v.strip().isdigit() else v.strip()
def parser():
    p=argparse.ArgumentParser()
    p.add_argument("--list-devices", action="store_true")
    p.add_argument("--device", type=parse_device)
    p.add_argument("--threshold", type=float, default=0.5)
    p.add_argument("--cooldown", type=float, default=2.0)
    return p

def rms(x):
    y=x.astype(np.float32)/32768.0
    return float(np.sqrt(np.mean(y*y)))

def main() -> int:
    args=parser().parse_args()
    if args.list_devices:
        print(MicrophoneStream.list_devices()); return 0
    try:
        mic=MicrophoneStream(AudioConfig(device=args.device))
        info=mic.selected_device_info()
        print("Loading the local Hey Jarvis model...")
        detector=WakeWordDetector(WakeWordConfig(threshold=args.threshold, cooldown_seconds=args.cooldown))
        print(f"Input device : {info['name']}")
        print(f"Capture rate : {mic.input_sample_rate} Hz")
        print("Model input  : 16000 Hz / mono / int16 / 80 ms")
        print('Say "Hey Jarvis". Press Ctrl+C to stop.\n')
        with mic:
            while True:
                frame=mic.read(2.0)
                result=detector.predict(frame.samples)
                print(f"\rscore={result.score:.3f} threshold={args.threshold:.2f} rms={rms(frame.samples):.4f}   ", end="", flush=True)
                if result.detected:
                    print(f"\n[{datetime.now():%H:%M:%S}] WAKE WORD DETECTED | phrase={result.model_name} | score={result.score:.3f}")
                    try:
                        import winsound; winsound.MessageBeep()
                    except ImportError: print("\a", end="")
    except KeyboardInterrupt:
        print("\nStopped by user."); return 0
    except (RuntimeError, ValueError, TimeoutError, sd.PortAudioError) as exc:
        print(f"\nStartup failed: {exc}", file=sys.stderr); return 1

if __name__ == "__main__": raise SystemExit(main())
