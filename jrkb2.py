import json
import smtplib
import logging
import time
import schedule
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from configparser import ConfigParser
from apscheduler.schedulers.blocking import BlockingScheduler

# 配置日志记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('rz.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def load_config():
    """加载配置文件"""
    config = ConfigParser()
    config.read('config.ini', encoding='utf-8')
    
    email_config = {
        'smtp_server': config.get('EMAIL', 'smtp_server'),
        'smtp_port': config.getint('EMAIL', 'smtp_port'),
        'sender': config.get('EMAIL', 'sender'),
        'password': config.get('EMAIL', 'password')
    }
    
    return email_config

def get_receivers():
    """获取收件人列表"""
    with open('email.txt', 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def get_today_courses():
    """获取当天课程并排序"""
    # 获取当前星期
    weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    today = datetime.now().weekday()
    today_cn = weekdays[today]
    
    # 读取课程数据
    with open('timetable.json', 'r', encoding='utf-8') as f:
        all_courses = json.load(f)
    
    # 过滤当天课程并按时间排序
    today_courses = [c for c in all_courses if c['dayOfWeek'] == today_cn]
    return sorted(today_courses, key=lambda x: x['time'])

def generate_email_content(courses):
    """生成邮件内容"""
    if not courses:
        return "<h3>今日没有课程安排</h3>"
    
    html = """
    <html>
        <body>
            <h2>今日课表（按时间排序）</h2>
            <table border="1" cellpadding="5">
                <tr>
                    <th>课程名称</th>
                    <th>时间</th>
                    <th>地点</th>
                    <th>教师</th>
                </tr>
    """
    
    for course in courses:
        html += f"""
        <tr>
            <td>{course['name']}</td>
            <td>{course['time']}</td>
            <td>{course['location']}</td>
            <td>{course['teacher']}</td>
        </tr>
        """
    
    html += "</table></body></html>"
    return html

def send_email():
    """发送邮件主函数"""
    try:
        # 每次发送前重新加载数据
        email_config = load_config()
        receivers = get_receivers()
        courses = get_today_courses()
        content = generate_email_content(courses)
        
        # 构建邮件
        msg = MIMEText(content, 'html')
        msg['Subject'] = f'今日课表通知 - {datetime.now().strftime("%Y-%m-%d")}'
        msg['From'] = email_config['sender']
        msg['To'] = ', '.join(receivers)
        
        # 发送邮件
        with smtplib.SMTP_SSL(email_config['smtp_server'], email_config['smtp_port']) as server:
            server.login(email_config['sender'], email_config['password'])
            server.sendmail(email_config['sender'], receivers, msg.as_string())
        
        logging.info(f"邮件发送成功，收件人数量：{len(receivers)}")
    except Exception as e:
        logging.error(f"邮件发送失败：{str(e)}")

def main():
    """主调度程序"""
    scheduler = BlockingScheduler(timezone='Asia/Shanghai')
    
    # 添加定时任务
    scheduler.add_job(send_email, 'cron', hour=6, minute=0)
    scheduler.add_job(send_email, 'cron', hour=14, minute=50)
    
    logging.info("课表邮件服务已启动...")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("服务已停止")

if __name__ == '__main__':
    main()