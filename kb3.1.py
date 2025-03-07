import json
import os
import time
import hashlib
import smtplib
import logging
import configparser
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from Crypto.Util.py3compat import bchr

# 配置文件
CONFIG_FILE = 'config.ini'
TIMETABLE_FILE = 'timetable.json'
LOG_FILE = 'course_monitor.log'

# 初始化日志
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)
logger = logging.getLogger()

# 密钥
Sw = "qzkj1kjghd=876&*"

# 模拟 U 函数的部分功能（简化实现）
def U(data):
    if isinstance(data, dict):  # 处理字典类型
        result = []
        for key, value in data.items():
            if isinstance(key, str) and not key.isidentifier():  # 检查键是否包含非单词字符
                encoded_key = json.dumps(key)
            else:
                encoded_key = key if isinstance(key, str) else str(key)
            result.append(f"{encoded_key}: {U(value)}")
        return "{" + ", ".join(result) + "}"
    elif isinstance(data, list):  # 处理列表类型
        result = []
        for item in data:
            result.append(U(item))
        return "[" + ", ".join(result) + "]"
    elif isinstance(data, str):  # 处理字符串类型
        return json.dumps(data)
    elif isinstance(data, (int, float)):  # 处理数字类型
        return str(data)
    elif isinstance(data, bool):  # 处理布尔类型
        return "true" if data else "false"
    elif data is None:  # 处理 null
        return "null"
    else:
        return json.dumps(data)

# 加密函数 特别鸣谢onexiaolaji-249663924
def encrypt_password(password, key):
    # 确保密钥长度符合 AES-128 要求（16 字节）
    key = key.ljust(16, bchr(0))[:16]

    # 调用 U 函数处理密码
    processed_password = U(password)

    # 对密码进行 AES-128-ECB 加密，使用 PKCS7 填充
    cipher = AES.new(key, AES.MODE_ECB)
    encrypted = cipher.encrypt(pad(processed_password.encode('utf-8'), AES.block_size))

    # 对加密结果进行 Base64 编码
    base64_encoded = base64.b64encode(encrypted).decode('utf-8')

    # 再次进行 Base64 编码
    final_encoded = base64.b64encode(base64_encoded.encode('utf-8')).decode('utf-8')

    return final_encoded

class ConfigManager:
    @staticmethod
    def init_config():
        config = configparser.ConfigParser(interpolation=None)
        
        if not os.path.exists(CONFIG_FILE):
            print("首次运行需要初始化配置")
            config['USER'] = {
                'user_no': input("请输入userNo: "),
                'pwd': encrypt_password(input("请输入明文密码: "), Sw.encode('utf-8'))
            }
            config['COURSE'] = {
                'xnxq01id': input("请输入学期ID (默认2024-2025-2): ") or "2024-2025-2",
                'kbjcmsid': input("请输入课程ID (默认4674661F7F8B49E792D01C623A83BDD1): ") or "4674661F7F8B49E792D01C623A83BDD1",
                'first_monday': input("请输入第一周周一的日期(YYYY-MM-DD): ")
            }
            config['EMAIL'] = {
                'smtp_server': input("请输入SMTP服务器: "),
                'smtp_port': input("请输入端口: "),
                'sender': input("发件邮箱: "),
                'password': input("邮箱授权码: "),
                'receiver': input("收件邮箱: ")
            }
            
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                config.write(f)
            logger.info("配置文件初始化完成")
        else:
            config.read(CONFIG_FILE, encoding='utf-8')
        return config

class CourseMonitor:
    def __init__(self, config):
        self.config = config
        self.session = self._create_session()
        self.old_courses = {}
        self.current_week = None

    def _create_session(self):
        session = requests.Session()
        session.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Origin': 'https://zs.hdxy.edu.cn',
            'Referer': 'https://zs.hdxy.edu.cn/jwydd/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'Pragma': 'no-cache'
        }
        session.cookies.update({
            'Hm_lvt_860ecc104b49cb44a1efb948d215a34e': '1735206711',
            'route': 'd02b95f5e89a64dbb0be901fef5ff7f0'
        })
        return session

    def get_token(self):
        for _ in range(3):
            try:
                url = f"https://zs.hdxy.edu.cn/njwhd/login"
                params = {
                    'userNo': self.config['USER']['user_no'],
                    'pwd': self.config['USER']['pwd']
                }
                logger.debug(f"Token请求参数：{params}")
                
                response = self.session.get(url, params=params, timeout=15)
                logger.debug(f"Token响应状态码：{response.status_code}")
                logger.debug(f"Token响应内容：{response.text[:200]}...")
                
                data = response.json()
                if data.get('code') == '1':
                    logger.info("Token获取成功")
                    return data['data']['token']
                logger.error(f"Token获取失败：{data.get('Msg')}")
            except Exception as e:
                logger.error(f"Token请求异常：{str(e)}")
            time.sleep(5)
        return None

    def get_current_week(self):
        try:
            first_day = datetime.strptime(self.config['COURSE']['first_monday'], "%Y-%m-%d")
            now = datetime.now()
            delta = now - first_day
            week = (delta.days // 7) + 1
            
            logger.debug(f"当前日期：{now.strftime('%Y-%m-%d')}")
            logger.debug(f"第一周周一：{first_day.strftime('%Y-%m-%d')}")
            logger.debug(f"相差天数：{delta.days} 天")
            logger.debug(f"计算周数：第{week}周")
            
            return week
        except Exception as e:
            logger.error(f"周数计算错误：{str(e)}")
            return 1

    def fetch_timetable(self, week):
        try:
            token = self.get_token()
            if not token:
                return None
                
            self.session.headers.update({'token': token})
            
            url = "https://zs.hdxy.edu.cn/njwhd/student/curriculum"
            params = {
                'xnxq01id': self.config['COURSE']['xnxq01id'],
                'kbjcmsid': self.config['COURSE']['kbjcmsid'],
                'week': week
            }
            logger.debug(f"课表请求参数：{params}")
            
            response = self.session.get(url, params=params, timeout=15)
            logger.debug(f"课表响应状态码：{response.status_code}")
            logger.debug(f"课表原始响应：{response.text[:500]}...")
            
            if response.status_code != 200:
                logger.error(f"请求失败：HTTP {response.status_code}")
                return None
                
            data = response.json()
            if data.get('code') != '1':
                logger.error(f"API错误：{data.get('Msg')}")
                return None
                
            return self.parse_courses(data)
        except Exception as e:
            logger.error(f"课表请求异常：{str(e)}")
            return None

    def parse_courses(self, raw_data):
        courses = []
        try:
            data_list = raw_data.get('data', [])
            for week_data in data_list:
                
                date_map = {}
                for date_info in week_data.get('date', []):
                    xqmc = date_info.get('xqmc', '')
                    mxrq = date_info.get('mxrq', '')
                    date_map[xqmc] = mxrq  

                
                for item in week_data.get('item', []):
                    class_time = item.get('classTime', '')
                    week_day_code = class_time[:1]  
                    xqmc = self.convert_week_day_code(week_day_code)
                    date_str = date_map.get(xqmc, '')  
                    day_of_week = self.translate_day(week_day_code)
                    class_time_section = class_time[1:3]  
                    time_group, time_description = self.translate_class_time(class_time_section)
                    time_period = f"{item.get('startTime', '')}-{item.get('endTIme', '')}"

                    course = {
                        'name': item.get('courseName', '未命名课程'),
                        'time': time_period,
                        'location': item.get('location', '未知地点'),
                        'teacher': item.get('teacherName', '未知教师'),
                        'dayOfWeek': day_of_week,
                        'timeGroup': time_group,
                        'timeDescription': time_description,
                        'date': date_str,
                        'classTime': class_time
                    }
                    courses.append(course)
            return courses
        except Exception as e:
            logger.error(f"课程解析失败：{str(e)}")
            return None

    def convert_week_day_code(self, week_day_code):
        code_map = {
            '1': '一',
            '2': '二',
            '3': '三',
            '4': '四',
            '5': '五',
            '6': '六',
            '7': '日'
        }
        return code_map.get(week_day_code, '未知')

    def save_timetable(self, courses):
        try:
            if courses:
                with open(TIMETABLE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(courses, f, ensure_ascii=False, indent=4)
                logger.info(f"课程表已保存到 {TIMETABLE_FILE}")
        except Exception as e:
            logger.error(f"保存课表失败：{str(e)}")

    def compare_courses(self, new_courses):
        if not new_courses:
            return False
        
        current_hash = hashlib.md5(json.dumps(new_courses, sort_keys=True).encode()).hexdigest()
        old_hash = self.old_courses.get('hash') if self.old_courses else None
        
        if current_hash != old_hash:
            self.old_courses = {
                'hash': current_hash,
                'courses': new_courses
            }
            logger.info("检测到课表更新")
            return True
        else:
            logger.info("课表无变化")
            return False

    def send_notification(self, courses):
        try:
            msg = MIMEMultipart()
            msg['From'] = self.config['EMAIL']['sender']
            msg['To'] = self.config['EMAIL']['receiver']
            msg['Subject'] = f"课程更新通知 - {datetime.now().strftime('%m/%d')}"

            html = f"""
            <html>
                <style>
                    table {{ border-collapse: collapse; width: 100%; }}
                    th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }}
                    tr:nth-child(even) {{ background-color: #f2f2f2; }}
                    h3 {{ color: #2e86de; }}
                    p {{ margin: 10px 0; }}
                </style>
                <body>
                    <h3>课程更新通知</h3>
                    <p>检测到课程表更新，请查看最新课表：</p>
                    {self.generate_table(courses)}
                </body>
            </html>
            """
            
            msg.attach(MIMEText(html, 'html', 'utf-8'))
            
            with smtplib.SMTP_SSL(self.config['EMAIL']['smtp_server'], 
                                int(self.config['EMAIL']['smtp_port'])) as server:
                server.login(self.config['EMAIL']['sender'], 
                           self.config['EMAIL']['password'])
                server.send_message(msg)
                
            logger.info("通知邮件已发送")
        except Exception as e:
            logger.error(f"邮件发送失败：{str(e)}")

    def generate_table(self, courses):
        courses_sorted = sorted(courses, key=lambda x: (x['date'], x['timeGroup']))
        rows = ["<table>"]
        rows.append("<tr><th>日期</th><th>周几</th><th>时段</th><th>节次</th><th>时间</th><th>课程名称</th><th>地点</th><th>教师</th></tr>")
        for course in courses_sorted:
            rows.append(f"""
                <tr>
                    <td>{course['date']}</td>
                    <td>{course['dayOfWeek']}</td>
                    <td>{course['timeGroup']}</td>
                    <td>{course['timeDescription']}</td>
                    <td>{course['time']}</td>
                    <td>{course['name']}</td>
                    <td>{course['location']}</td>
                    <td>{course['teacher']}</td>
                </tr>
            """)
        rows.append("</table>")
        return "\n".join(rows)

    def run(self):
        logger.info("======== 课程监控启动 ========")
        while True:
            try:
                week = self.get_current_week()
                logger.info(f"当前为第{week}周")
                
                new_courses = self.fetch_timetable(week)
                if not new_courses:
                    logger.warning("获取课表失败，等待重试...")
                    time.sleep(300)
                    continue
                
                self.save_timetable(new_courses)
                
                if self.compare_courses(new_courses):
                    self.send_notification(new_courses)
                else:
                    logger.info("课表无变化")
                
                # 等待一段时间后再次检查
                time.sleep(300)  # 5分钟检查一次
                
            except KeyboardInterrupt:
                logger.info("用户手动终止程序")
                break
            except Exception as e:
                logger.error(f"运行时异常：{str(e)}")
                time.sleep(300)

    def translate_day(self, week_day_code):
        day_map = {
            '1': '周一',
            '2': '周二',
            '3': '周三',
            '4': '周四',
            '5': '周五',
            '6': '周六',
            '7': '周日',
            '日': '周日'
        }
        return day_map.get(week_day_code, '未知')

    def translate_class_time(self, class_time_section):
        time_map = {
            '01': ('上午', '第一大节'),
            '03': ('上午', '第二大节'),
            '05': ('下午', '第一大节'),
            '07': ('下午', '第二大节'),
            '09': ('晚上', '第一节')
        }
        return time_map.get(class_time_section, ('未知时段', '未知节次'))

if __name__ == "__main__":
    config = ConfigManager().init_config()
    CourseMonitor(config).run()