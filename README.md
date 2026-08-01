# LLM Agent — Step 7.1: Edge Neural TTS

기존 Windows SAPI5 음성을 제거하고 Microsoft Edge의 자연스러운 신경망
TTS로 교체했습니다.

## 기본 음성

```text
ko-KR-InJoonNeural
```

한국어 남성 음성으로, 기존 `Microsoft Heami Desktop`보다 자연스러운
음성 출력을 목표로 합니다.

## 전체 흐름

```text
"Hey Jarvis"
→ 음성 명령 인식
→ GPT 추론 및 도구 호출
→ 필요하면 화면 캡처·분석
→ GPT 최종 답변
→ Edge Neural TTS 생성 및 재생
→ 다시 웨이크워드 대기
```

## 중요한 차이

Edge TTS는 로컬 SAPI와 달리 인터넷 연결이 필요합니다.

- 별도의 Azure API 키: 필요 없음
- OpenAI TTS 비용: 발생하지 않음
- 인터넷 연결: 필요
- 음질: Windows 기본 SAPI보다 자연스러운 편
- 재생: Windows에서는 `edge-playback`의 기본 재생 기능 사용

## 설치

```powershell
python -m pip install -r requirements.txt
```

## 실행

```powershell
python -m src.main
```

## 한국어 보이스 목록 확인

```powershell
python -m src.main --list-tts-voices
```

사용 가능한 보이스 목록은 온라인 서비스에서 불러오기 때문에 인터넷 연결이
필요합니다.

대표적인 한국어 음성 예시:

```text
ko-KR-InJoonNeural
ko-KR-SunHiNeural
ko-KR-HyunsuNeural
ko-KR-BongJinNeural
ko-KR-GookMinNeural
ko-KR-JiMinNeural
ko-KR-SeoHyeonNeural
ko-KR-SoonBokNeural
ko-KR-YuJinNeural
```

실제 사용 가능 여부는 `--list-tts-voices` 출력이 기준입니다.

## 보이스 변경

여성 음성:

```powershell
python -m src.main --tts-voice "ko-KR-SunHiNeural"
```

다른 남성 음성:

```powershell
python -m src.main --tts-voice "ko-KR-HyunsuNeural"
```

## 속도·음량·피치

조금 빠르고 낮은 목소리:

```powershell
python -m src.main --tts-rate 8 --tts-pitch -8
```

조금 느리게:

```powershell
python -m src.main --tts-rate -8
```

음량 낮추기:

```powershell
python -m src.main --tts-volume 80
```

설정 범위:

```text
rate   : -100 ~ 100%
volume : 0 ~ 100
pitch  : -100 ~ 100 Hz
```

## 실행 중 음성 출력 전환

```text
음성 출력 꺼줘
음성 출력 켜줘
TTS 꺼줘
TTS 켜줘
```

## 추천 기본 조합

자비스처럼 조금 차분한 남성 음성:

```powershell
python -m src.main `
  --tts-voice "ko-KR-InJoonNeural" `
  --tts-rate 4 `
  --tts-pitch -6
```

## 커밋 메시지

```bash
git commit -m "Replace Windows SAPI with Edge neural TTS"
```
