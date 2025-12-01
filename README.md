# 맛집 고객만족도 통합 분석 AI 서비스

# 프로젝트 배경
+ 리뷰는 맛집 선택에 있어 큰 비중 차지
+ SNS 매체에는 광고성 글 다수 차지
+ 사이트 별 리뷰의 전반적인 분위기 차이 큼

# 프로젝트 목표
+ 리뷰를 통합 수집후 LLM이 요약하여 한줄평, 별점, 아쉬운 점을 제공
+ 단순한 일발성, 휘발성 악플은 걸러주는 평가

# 사용한 기술
+ Selenium
+ ThreadPoolExecutor
+ SQLite
+ Docker
+ Streamlit
+ Folium
+ Ollama
+ LangChain

# 실행 방법
+ streamlit run mobile_lunch_hg.py
