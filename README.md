\# 🍽 PickPlace — 맛집 고객만족도 통합 분석 AI 서비스



> 구글·네이버·카카오 3개 플랫폼의 리뷰를 통합 수집하고,  

> LLM이 한줄평·별점·아쉬운 점을 요약해주는 AI 서비스



!\[Python](https://img.shields.io/badge/Python-3776AB?style=flat\&logo=python\&logoColor=white)

!\[LangChain](https://img.shields.io/badge/LangChain-000000?style=flat)

!\[Docker](https://img.shields.io/badge/Docker-2496ED?style=flat\&logo=docker\&logoColor=white)

!\[Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=flat\&logo=streamlit\&logoColor=white)



\---



\## 📌 문제 정의



\- 플랫폼마다 리뷰 형식과 평가 기준이 달라 사용자가 여러 곳을 직접 비교해야 하는 불편함

\- 단순 평점이나 키워드 정렬 방식으로는 실제 이용 경험을 정확히 파악하기 어려움

\- 단발성 부정 리뷰가 전체 평가를 왜곡하는 문제



\## 🏗 서비스 아키텍처



Selenium 크롤러 (구글·카카오·네이버)

↓ 병렬 수집 (ThreadPoolExecutor)

SQLite DB (재크롤링 로직 포함)

↓ 저장된 리뷰 조회

LangChain + Llama 3.1 요약 파이프라인

↓ 한줄평·별점·아쉬운 점 생성

Streamlit 웹 서비스 (도메인 배포)



\## ⚡ 핵심 성과



| 항목 | 개선 전 | 개선 후 | 개선율 |

|------|--------|--------|-------|

| 리뷰 수집 시간 | 90초 | 27초 | \*\*70% 단축\*\* |



\- ThreadPoolExecutor 병렬 처리로 3개 플랫폼 동시 수집 구현

\- SQLite 재크롤링 로직으로 데이터 최신성 자동 유지

\- GPT → Llama 3.1 전환으로 비용·성능 트레이드오프 최적화

\- Docker 컨테이너화 및 도메인 기반 외부 배포 완료



\## 🛠 기술 스택



| 분류 | 기술 |

|------|------|

| 크롤링 | Selenium, ThreadPoolExecutor |

| DB | SQLite |

| AI 파이프라인 | LangChain, Llama 3.1 (Ollama) |

| 서비스 | Streamlit, Folium |

| 배포 | Docker, docker-compose |



\## 🔍 주요 구현 내용



\*\*1. 병렬 크롤링 시스템\*\*

\- 3개 플랫폼을 순차 수집에서 ThreadPoolExecutor 기반 병렬 수집으로 전환

\- 수집 시간 90초 → 27초 단축 (70% 개선)



\*\*2. 데이터 최신성 관리\*\*

\- 수집 시각 기록 후 일정 시간 경과 시 자동 재크롤링

\- 단발성 리뷰 필터링 및 중복 제거 로직 구현



\*\*3. LLM 요약 파이프라인\*\*

\- 한줄평 / 별점 / 아쉬운 점 분리 요약 구조 설계

\- 긍정 편향 문제를 프롬프트 엔지니어링으로 개선



\## 🚀 실행 방법



```bash

git clone https://github.com/Kim-gami/review\_project

cd review\_project

docker-compose up

\# 또는

streamlit run mobile\_lunch\_hg.py

```



\## 👥 팀 구성



\- 5인 팀 | 본인 담당: 크롤링 시스템·DB 설계·LangChain 파이프라인·Streamlit 기능·Docker 배포

