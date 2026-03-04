import pymysql

# DB 접속 정보
db_config = {
    'host': 'localhost',
    'port': 3306,
    'user': 'robot',
    'password': 'sw1234',
    'database': 'library_robot_db',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

def get_connection():
    return pymysql.connect(**db_config)

def init_expected_inventory():
    """16개의 정답지(101~104, 201~204 등)를 DB에 미리 세팅합니다."""
    conn = get_connection()
    # 사전 정렬된 16개의 데이터 리스트
    expected_list = [
        101, 102, 103, 104,
        201, 202, 203, 204,
        301, 302, 303, 304,
        401, 402, 403, 404
    ]
    
    try:
        with conn.cursor() as cursor:
            # 기존 테이블 비우기
            cursor.execute("TRUNCATE TABLE inventory")
            
            # 1번부터 16번 슬롯까지 빈자리(scanned_book_id=NULL)로 초기화
            for i, book_id in enumerate(expected_list):
                slot_num = i + 1 
                expected_id = book_id # 예: 101
                
                sql = """
                    INSERT INTO inventory (slot_num, shelf_id, expected_book_id, scanned_book_id, status)
                    VALUES (%s, 'shelf-1', %s, NULL, 'unknown')
                """
                cursor.execute(sql, (slot_num, expected_id))
            conn.commit()
            print("✅ 16개의 사전 정답지 DB 세팅 완료!")
    except Exception as e:
        print(f"❌ DB 초기화 오류: {e}")
    finally:
        conn.close()

def verify_and_update_book(slot_num, scanned_id):
    """로봇이 읽은 마커가 DB의 정답과 일치하는지 확인(채점)합니다."""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT expected_book_id FROM inventory WHERE slot_num = %s", (slot_num,))
            result = cursor.fetchone()
            
            if not result:
                return False, "err" # 16번 슬롯을 초과한 경우

            expected_id = result['expected_book_id']
            status = 'ok' if expected_id == scanned_id else 'err' # 채점!
                
            sql = """
                UPDATE inventory 
                SET scanned_book_id = %s, status = %s, last_updated = CURRENT_TIMESTAMP
                WHERE slot_num = %s
            """
            cursor.execute(sql, (scanned_id, status, slot_num))
            conn.commit()
            return True, status
    except Exception as e:
        print(f"❌ DB 업데이트 오류: {e}")
        return False, "err"
    finally:
        conn.close()