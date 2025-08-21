#html을 텍스트로 넣으면 리뷰 링크를 뱉고 저장
import re


def parse_kakao_place_ids(filename):
    # 텍스트 파일 읽기
    with open(filename, "r", encoding="utf-8") as f:
        text = f.read()

    # 숫자만 추출 (정규식)
    ids = re.findall(r'https://place\.map\.kakao\.com/(\d+)#review', text)

    return ids

review_address = []

if __name__ == "__main__":
    for i in range(1,35):
        file_path = "html_data/" + str(i) + "page" + ".txt"  # <- 여기 파일명만 바꿔주면 됩니다
        place_ids = parse_kakao_place_ids(file_path)

        print("총 개수:", len(place_ids))
        print("추출된 숫자 리스트:", place_ids)

        review_address += place_ids

    with open("kakao_review_address.txt", "w", encoding="utf-8") as f:
        for pid in review_address:
            f.write(pid + "\n")
