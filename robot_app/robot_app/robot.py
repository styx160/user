import cv2
import cv2.aruco as aruco
import numpy as np
import time
import database
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String
from cv_bridge import CvBridge

class LibraryRobot(Node):
    def __init__(self):
        super().__init__('library_robot_node')
        self.is_running = False       
        
        self.current_camera_frame = None
        self.latest_raw_frame = None      
        self.freeze_frame = None          
        self.freeze_time = 0.0            
        
        self.base_slot = 1  
        self.scanned_history = set() # 이제 개별 책이 아닌 '구역(Zone)' 스캔 여부를 기억합니다.

        self.bridge = CvBridge()
        self.subscription = self.create_subscription(CompressedImage, '/camera_arm/image_raw/compressed', self.image_callback, 10)
        self.stop_subscription = self.create_subscription(String, '/stop_notification', self.stop_callback, 10)
        
        try:
            self.aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_5X5_1000)
            self.aruco_params = aruco.DetectorParameters()
            # 곡면 부착 및 빛 반사를 이겨내는 강력한 파라미터 유지
            self.aruco_params.adaptiveThreshWinSizeMin = 3
            self.aruco_params.adaptiveThreshWinSizeMax = 23
            self.aruco_params.adaptiveThreshWinSizeStep = 10
            self.aruco_params.polygonalApproxAccuracyRate = 0.05 
            self.aruco_detector = aruco.ArucoDetector(self.aruco_dict, self.aruco_params)
        except AttributeError:
            self.aruco_dict = aruco.Dictionary_get(aruco.DICT_5X5_1000)
            self.aruco_params = aruco.DetectorParameters_create()
            self.aruco_params.adaptiveThreshWinSizeMin = 3
            self.aruco_params.adaptiveThreshWinSizeMax = 23
            self.aruco_params.adaptiveThreshWinSizeStep = 10
            self.aruco_params.polygonalApproxAccuracyRate = 0.05 
            self.aruco_detector = None

        self.get_logger().info("📷 스마트 스캔 준비 완료 (구역 단위 집합 판별 알고리즘 🚀)")

    def start_routine(self):
        self.is_running = True
        self.get_logger().info("🤖 스캔 모드 가동!")

    def stop_routine(self):
        self.is_running = False

    def reset_state(self):
        self.scanned_history.clear()
        self.base_slot = 1
        self.get_logger().info("🔄 로봇 메모리 초기화 완료")

    def image_callback(self, msg):
        try:
            frame = self.bridge.compressed_imgmsg_to_cv2(msg, "bgr8")
            self.latest_raw_frame = frame.copy() 
            
            if time.time() - self.freeze_time < 3.0:
                self.current_camera_frame = self.freeze_frame
            else:
                cv2.putText(frame, "LIVE", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                self.current_camera_frame = frame
                
        except Exception as e:
            self.get_logger().error(f"이미지 변환 오류: {e}")

    def stop_callback(self, msg):
        data = msg.data.strip()
        
        if data in ['1', '2', '3', '4'] and self.is_running:
            self.get_logger().info(f"🛑 구역 {data} 정지! -> 📸 구역 전체 판별 시작")
            
            if self.latest_raw_frame is not None:
                if data == '1': self.base_slot = 1   # 미술
                elif data == '2': self.base_slot = 5   # 역사
                elif data == '3': self.base_slot = 13  # 과학
                elif data == '4': self.base_slot = 9   # 문학
                
                processed_frame = self._process_frame(self.latest_raw_frame.copy())
                self.freeze_frame = processed_frame 
                self.freeze_time = time.time()
            else:
                self.get_logger().warn("카메라 프레임이 준비되지 않았습니다.")

    def _process_frame(self, frame):
        try:
            cv2.putText(frame, f"ZONE SCANNED (Base: {self.base_slot})", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if hasattr(self, 'aruco_detector') and self.aruco_detector is not None:
                corners, ids, rejectedImgPoints = self.aruco_detector.detectMarkers(gray)
            else:
                corners, ids, rejectedImgPoints = aruco.detectMarkers(gray, self.aruco_dict, parameters=self.aruco_params)

            if ids is not None:
                valid_ids = {'0', '1', '2', '3', '101', '102', '103', '104', '201', '202', '203', '204', '301', '302', '303', '304', '401', '402', '403', '404'}

                # 현재 구역(Zone)의 정답 책 목록
                expected_ids = []
                if self.base_slot == 1: expected_ids = ['101', '102', '103', '104']
                elif self.base_slot == 5: expected_ids = ['201', '202', '203', '204']
                elif self.base_slot == 9: expected_ids = ['301', '302', '303', '304']
                elif self.base_slot == 13: expected_ids = ['401', '402', '403', '404']

                detected_markers = []
                detected_ids_only = []
                
                # 중복 인식 방지 (동일한 책을 두 번 잡을 경우)
                seen = set()
                for i in range(len(ids)):
                    marker_id = str(int(ids[i][0]))
                    if marker_id in valid_ids and marker_id not in seen:
                        pts = corners[i][0].astype(np.int32)
                        detected_markers.append((marker_id, pts))
                        detected_ids_only.append(marker_id)
                        seen.add(marker_id)

                # --- [핵심] 구역 내 책 채점 및 UI 표시 로직 ---
                for marker_id, pts in detected_markers:
                    x, y = int(pts[0][0]), int(pts[0][1])
                    
                    if marker_id in expected_ids:
                        # 정답 책 (초록색)
                        cv2.polylines(frame, [pts], True, (0, 255, 0), 3)
                        cv2.putText(frame, marker_id, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                    else:
                        # 오배열 엉뚱한 책 (빨간색 경고)
                        cv2.polylines(frame, [pts], True, (0, 0, 255), 4)
                        cv2.putText(frame, f"ALIEN: {marker_id}", (x-10, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

                # --- DB 업데이트 (구역당 딱 1번만 실행) ---
                zone_key = f"zone_{self.base_slot}"
                if zone_key not in self.scanned_history:
                    self.get_logger().info(f"📊 [Zone {self.base_slot}] 구역 전체 판별 결과:")

                    correct_books = [m for m in detected_ids_only if m in expected_ids]
                    alien_books = [m for m in detected_ids_only if m not in expected_ids]
                    missing_books = [e for e in expected_ids if e not in correct_books]

                    # 1. 정답 책 업데이트 (자기 자리 찾아가기)
                    for m_id in correct_books:
                        exact_slot = self.base_slot + expected_ids.index(m_id)
                        database.verify_and_update_book(exact_slot, m_id)
                        self.get_logger().info(f"  ✅ 정상 책: {m_id}")

                    # 2. 오배열 책 업데이트 (웹 UI 에러 표시를 위해 빈 자리에 쑤셔넣기)
                    for alien_id in alien_books:
                        if missing_books:
                            target_missing = missing_books.pop(0) # 남은 빈자리 하나 가져오기
                            exact_slot = self.base_slot + expected_ids.index(target_missing)
                            database.verify_and_update_book(exact_slot, alien_id)
                            self.get_logger().warn(f"  ⚠️ 오배열 책: {alien_id} 발견!")
                        else:
                            self.get_logger().warn(f"  ⚠️ 오배열 책: {alien_id} (자리가 꽉 차서 DB에는 미반영)")

                    # 3. 진짜 없는 빈자리 업데이트
                    for really_missing in missing_books:
                        exact_slot = self.base_slot + expected_ids.index(really_missing)
                        database.verify_and_update_book(exact_slot, '없음') # 웹 UI에서 빨간색 분실로 표시됨
                        self.get_logger().warn(f"  ❌ 분실 책: {really_missing}가 없습니다.")

                    self.scanned_history.add(zone_key) # 구역 채점 완료 도장!

        except Exception as e:
            self.get_logger().error(f"스캔 중 오류: {e}")
            
        return frame

    def get_frame(self):
        if self.current_camera_frame is not None:
            ret, buffer = cv2.imencode('.jpg', self.current_camera_frame)
            return buffer.tobytes()
        return None