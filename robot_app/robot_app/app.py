from flask import Flask, render_template, Response, jsonify, request
from flask_cors import CORS
import robot     
import database  
import rclpy
import threading
import os

app = Flask(__name__)
CORS(app)

# --- ROS2 초기화 및 노드 생성 ---
rclpy.init()
bot = robot.LibraryRobot()

def ros_spin_thread():
    rclpy.spin(bot)

spin_thread = threading.Thread(target=ros_spin_thread, daemon=True)
spin_thread.start()
# --------------------------------------

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

def gen_frames():
    while True:
        frame_bytes = bot.get_frame()
        if frame_bytes:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/inventory')
def get_inventory():
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM inventory ORDER BY slot_num ASC")
    rows = cur.fetchall()
    conn.close()
    return jsonify(rows)

# --- [통합됨] 1. 스캔 시작, 초기화 등 공통 제어 ---
@app.route('/control/<action>', methods=['POST'])
def control_robot(action):
    if action == 'start':
        print("🚀 전체 스캔 시작! 주행 노드에 출발 명령을 하달합니다.")
        bot.start_routine() # 내부 카메라 노드 스캔 모드 ON
        os.system("""ros2 topic pub --once /scan_command std_msgs/msg/String "{data: 'start'}" """)
        return jsonify({"status": "success", "message": "스캔 시작"})

    elif action == 'reset':
        print("🔄 데이터 초기화 명령 수신! DB 및 로봇 메모리를 리셋합니다.")
        database.init_expected_inventory() # (또는 database.reset_inventory() 사용)
        bot.reset_state() # 토픽 쏠 필요 없이 메모리 다이렉트 초기화!
        return jsonify({"status": "success", "message": "초기화 완료"})

    return jsonify({"status": "unknown action"})

# --- 2. 개별 로봇(AGV, AMR) 목적지 이동 ---
@app.route('/control/move_goal', methods=['POST'])
def move_goal():
    robot_type = request.args.get('robot') # 'agv' 또는 'amr'
    zone = request.args.get('zone')        # 'goal1' 등
    target = request.args.get('target')    # '1', '2', '3', '4' 등
    
    topic_name = f"/{robot_type}/set_goal"
    
    # f-string 안에서 JSON 중괄호는 {{ }} 로 감싸기!
    command = f"""ros2 topic pub --once {topic_name} std_msgs/msg/String "{{data: '{zone}, {target}'}}" """
    
    print(f"🚀 {robot_type.upper()} 이동 명령 하달: {command}")
    os.system(command)
    
    return jsonify({"status": "success"})

# --- 3. 개별 로봇 (스캐너, AGV, AMR) 비상 정지 ---
@app.route('/control/stop_robot', methods=['POST'])
def handle_stop_robot():
    robot_type = request.args.get('robot') # 'scanner', 'agv', 'amr'
    cmd_data = request.args.get('command') # 'stop' 또는 'resume'
    
    # 1. 로봇 종류에 따라 쏠 토픽 이름 결정
    if robot_type == 'scanner':
        topic_name = '/scan_command'
        if cmd_data == 'stop': bot.stop_routine()
        else: bot.start_routine() # 해제 시 다시 스캔 켜기
    elif robot_type == 'agv':
        topic_name = '/agv/stop'
    elif robot_type == 'amr':
        topic_name = '/amr/stop'
    else:
        return jsonify({"status": "error", "message": "알 수 없는 로봇"})

    # 2. 받아온 cmd_data('stop' 또는 'resume')를 f-string으로 동적 할당!
    command = f"""ros2 topic pub --once {topic_name} std_msgs/msg/String "{{data: '{cmd_data}'}}" """

    print(f"🛑 {robot_type.upper()} 상태 변경 명령 하달: {command}")
    os.system(command) # 터미널 실행
    
    return jsonify({"status": "success"})


if __name__ == '__main__':
    try:
        # 서버 시작 시 DB 16칸 세팅
        database.init_expected_inventory() 
        app.run(host='0.0.0.0', port=5000, threaded=True)
    finally:
        bot.destroy_node()
        rclpy.shutdown()