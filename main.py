import requests
import base64
import time
import logging
from apscheduler.schedulers.blocking import BlockingScheduler
import ddddocr

from config import lecture_headers, lecture_key

ocr = ddddocr.DdddOcr()
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")

logger = logging.getLogger(__name__)


def parse_verify_code(img):
    """
    解析验证码

    Args:
        img_base64 (bytes): 验证码图片的base64字节码

    Returns:
        str: 解析的验证码
    """

    return ocr.classification(img)


def get_target_lecture(key):
    """
    获取目标讲座信息

    Args:
        key (str): 讲座名称关键词

    Returns:
        dict: 讲座数据
    """

    r = requests.post(
        url=
        'https://ehall.seu.edu.cn/gsapp/sys/yddjzxxtjappseu/modules/hdyy/queryActivityList.do',
        headers=lecture_headers,
    )
    if r.status_code != 200:
        logger.error(f"讲座列表接口响应状态码错误: {r.status_code}")
        return None

    if len(r.text) == 0:
        logger.error("讲座列表接口响应内容为空")
        return None

    try:
        res = r.json()
    except Exception as e:
        logger.error("响应内容不是有效的JSON格式，可能是Cookie失效或被拦截。")
        logger.error(f"响应内容预览: {r.text[:500]}")  # 打印前500个字符查看
        return None

    lecture_list = res['datas']['hdlbList']
    if lecture_list is None or len(lecture_list) == 0:
        logger.info("当前没有任何讲座可预约！")
        return None

    target_list = []
    for item in lecture_list:
        if key in item['JZMC']:
            target_list.append(item)

    if len(target_list) == 0:
        logger.error("当前关键词没有搜索到任何讲座！")
        return None

    if len(target_list) > 1:
        logger.warning("注意！当前关键词可搜索到多个讲座，请指定更详细的关键词，或默认选择匹配的最后一项")

    return target_list[-1]


def get_lecture_verify_code(wid):
    """
   获取指定讲座的验证码

    Args:
        wid (str): 讲座id
        
    Returns:
        bytes: 验证码图片的base64字节码
    """

    r = requests.get(
        url=
        'https://ehall.seu.edu.cn/gsapp/sys/yddjzxxtjappseu/modules/hdyy/vcode.do',
        params={'_': int(time.time() * 1000)},
        headers=lecture_headers,
    )
    res = r.json()

    base64_str = res['datas']
    base64_str = base64_str[(base64_str.index("base64,") + 7):]
    image = base64.b64decode(base64_str)
    return image


def reserve_lecture(wid, verify_code):
    """
   预约指定讲座

    Args:
        wid (str): 讲座id
        verify_code (str): 验证码
    
    Returns:
        bool: 预约结果
    """

    params = {
        'wid': wid,
        'vcode': verify_code,
    }
    r = requests.post(
        url=
        'https://ehall.seu.edu.cn/gsapp/sys/yddjzxxtjappseu/modules/hdyy/addReservation.do',
        data=params,
        headers=lecture_headers,
    )

    res = r.json()
    logger.info('预约接口响应数据: ', res)

    return res['code'] == 0 and res['datas'] == 1


def keep_alive(wid):
    """
    获取指定讲座信息以保活

    Args:
        wid (str): 讲座id
    """

    r = requests.post(
        url=
        'https://ehall.seu.edu.cn/gsapp/sys/yddjzxxtjappseu/modules/hdyy/getActivityDetail.do',
        data={'wid': wid},
        headers=lecture_headers,
    )
    res = r.json()
    if res['code'] != 0:
        logger.error('保活失效，请检查cookie！')

    logger.info('用户身份有效，登录状态保活')


def rob(wid):
    """
    定时抢讲座任务

    Args:
        wid (str): 讲座id
    """

    logger.info("定时预约任务开始, wid: ", wid)
    # 获取验证码图片
    verify_code_img = get_lecture_verify_code(wid)
    # 解析验证码
    verify_code = parse_verify_code(verify_code_img)
    logger.info("解析验证码成功: ", verify_code)
    # 尝试预约讲座
    res = reserve_lecture(wid, verify_code)
    logger.info("预约结果: ", res)


if __name__ == "__main__":
    # 先在config中修改用户cookie和目标讲座名称！

    # 获取目标讲座信息
    lecture = get_target_lecture(lecture_key)
    if lecture is None:
        exit(1)

    logger.info(f'搜索到目标讲座: {lecture['JZMC']}')

    # 立即检查一次保活
    keep_alive(lecture['WID'])

    # 启动定时任务
    scheduler = BlockingScheduler()
    scheduler.add_job(keep_alive,
                      'interval',
                      seconds=30,
                      args=[lecture['WID']])
    scheduler.add_job(rob,
                      'cron',
                      hour=19,
                      minute=0,
                      second=1,
                      args=[lecture['WID']])
    scheduler.start()
