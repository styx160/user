import cv2 # OpenCV 라이브러리 임포트
print("OpenCV version:", cv2.__version__) # OpenCV 버전 출력

# 1. 하위 폴더(data) 경로를 지정하여 이미지 불러오기
img = cv2.imread("data/lena.jpg", cv2.IMREAD_COLOR)

# 2. 이미지 로드 확인
if img is None:
    print("에러: 'data/lena.jpg' 파일을 찾을 수 없습니다.")
    exit()

# 3. 화면에 이미지 출력
cv2.imshow("Lena Image", img)

# 4. 키 입력 대기 및 창 닫기
cv2.waitKey(0)
cv2.destroyAllWindows()