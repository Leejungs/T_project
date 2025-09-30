-- ✅ 0. 기존 테이블 초기화 (있다면 삭제)
DROP TABLE IF EXISTS student;
DROP TABLE IF EXISTS department;
DROP TABLE IF EXISTS faculty;

-- ✅ 1. DB 생성 및 선택
CREATE DATABASE IF NOT EXISTS dmu
  CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
USE dmu;

-- ✅ 2. 학부 테이블
CREATE TABLE faculty (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL UNIQUE
) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;

-- ✅ 3. 학과 테이블
CREATE TABLE department (
  id INT AUTO_INCREMENT PRIMARY KEY,
  faculty_id INT NOT NULL,
  name VARCHAR(100) NOT NULL,
  program_length ENUM('2년제','3년제') NULL,
  UNIQUE KEY uq_dept (faculty_id, name),
  CONSTRAINT fk_dept_faculty FOREIGN KEY (faculty_id) REFERENCES faculty(id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;

-- ✅ 4. 학생 테이블
CREATE TABLE student (
  user_id VARCHAR(30) PRIMARY KEY,              -- 아이디 (로그인용)
  password_hash VARCHAR(100) NOT NULL,          -- 비밀번호 (해시 저장 권장)
  name VARCHAR(50) NOT NULL,                    -- 이름
  student_no VARCHAR(20) NOT NULL UNIQUE,       -- 학번
  status ENUM('재학','휴학') NOT NULL,          -- 상태
  dept_id INT,                                  -- 학과 ID (FK)
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_student_dept FOREIGN KEY (dept_id) REFERENCES department(id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;

-- ✅ 5. 학부 데이터 입력
INSERT INTO faculty (name) VALUES
('기계공학부'),
('로봇자동화공학부'),
('전기전자통신공학부'),
('컴퓨터공학부'),
('생활환경공학부'),
('경영학부'),
('자유전공학부');

-- ✅ 6. 학과 데이터 입력
INSERT INTO department (faculty_id, name, program_length) VALUES
-- 기계공학부 (2년제)
(1, '기계공학과', '2년제'),
(1, '기계설계공학과', '2년제'),

-- 로봇자동화공학부 (3년제)
(2, '자동화공학과', '3년제'),
(2, '로봇소프트웨어과', '3년제'),

-- 전기전자통신공학부 (정보통신공학과만 3년제)
(3, '전기공학과', '2년제'),
(3, '반도체전자공학과', '2년제'),
(3, '정보통신공학과', '3년제'),
(3, '소방안전관리과', '2년제'),

-- 컴퓨터공학부 (3년제)
(4, '웹응용소프트웨어공학과', '3년제'),
(4, '컴퓨터소프트웨어공학과', '3년제'),
(4, '인공지능소프트웨어학과', '3년제'),

-- 생활환경공학부 (건축/실내건축디자인과만 3년제)
(5, '생명화학공학과', '2년제'),
(5, '바이오융합공학과', '2년제'),
(5, '건축과', '3년제'),
(5, '실내건축디자인과', '3년제'),
(5, '시각디자인과', '2년제'),
(5, 'AR·VR콘텐츠디자인과', '2년제'),

-- 경영학부 (2년제)
(6, '경영학과', '2년제'),
(6, '세무회계학과', '2년제'),
(6, '유통마케팅학과', '2년제'),
(6, '호텔관광과', '2년제'),
(6, '경영정보과', '2년제'),
(6, '빅데이터경영과', '2년제'),

-- 자유전공학부 (년제 없음)
(7, '자유전공학부', NULL);

-- ✅ 7. 학생 데이터 (예시)
INSERT INTO student (user_id, password_hash, name, student_no, status, dept_id) VALUES
('kim01', 'pass1234', '김가람', '202312345', '재학', (SELECT id FROM department WHERE name='인공지능소프트웨어학과')),
('lee02', 'test0000', '이보미', '202312346', '휴학', (SELECT id FROM department WHERE name='경영학과')),
('park03', 'qwer!234', '박준서', '202312347', '재학', (SELECT id FROM department WHERE name='건축과'));

-- ✅ 8. 데이터 확인용 조회 쿼리
SELECT
  s.user_id,
  s.name,
  s.student_no,
  s.status,
  f.name AS faculty,
  d.name AS department,
  d.program_length
FROM student s
JOIN department d ON s.dept_id = d.id
JOIN faculty f ON d.faculty_id = f.id
ORDER BY s.student_no;
