# javbus封面爬取程序 v2.0 - 优化版
# 1. 下载前检测同路径是否已存在对应封面
# 2. 支持递归检索子文件夹内的视频文件
# 3. 优化异常处理，提高程序稳定性
# 4. 优化车牌号提取正则，限制字母和数字长度（字母2-5位，数字2-5位）
# 5. 只匹配字母开头的视频文件
# 6. 增强文件名处理，防止非法字符和过长文件名
# 7. 增加网络请求重试机制
# 8. 优化错误处理和日志记录
import requests
from lxml import etree
import re
import random
import time
import os
import threading
from threading import Semaphore
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 全局计数器和列表
count = 0
count1 = 0
error_list = []
error_files_list = []
sem = Semaphore(2)  # 控制并发线程数


def safe_request(url, headers=None, proxies=None, timeout=15, retry=3):
    """
    安全请求函数，带重试机制
    :param url: 请求URL
    :param headers: 请求头
    :param proxies: 代理设置
    :param timeout: 超时时间
    :param retry: 重试次数
    :return: 请求响应
    """
    for i in range(retry):
        try:
            response = requests.get(url=url, headers=headers, proxies=proxies, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logger.warning(f"请求失败 ({i + 1}/{retry}): {url} - {str(e)}")
            if i == retry - 1:
                raise
            time.sleep(random.randint(2, 5))  # 重试前等待


def download_cover(tag, video_path):
    """
    下载指定车牌号的封面图片到视频所在目录
    :param tag: 车牌号
    :param video_path: 视频文件所在目录
    """
    # 将global声明移到函数开头，解决语法错误
    global count
    global count1

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
        "accept-language": "zh-CN,zh;q=0.9,en-AS;q=0.8,en;q=0.7",
        "referer": f"https://www.javbus.com/{tag}",
        "cookie": "existmag=mag; PHPSESSID=0qcbki5uh1up957tacne1tgqk0"
    }

    proxy = {"http": "socks5h://127.0.0.1:7897", "https": "socks5h://127.0.0.1:7897"}

    print(f'即将开始匹配下载【{tag}】封面图\n')

    try:
        # 访问javbus获取封面信息
        url = f"https://www.javbus.com/{tag}"
        response = safe_request(url=url, headers=headers, proxies=proxy, timeout=20, retry=3)
        response = response.content.decode('utf-8')

        page = etree.HTML(response)

        # 获取封面图片URL
        big_pic_url_list = page.xpath('/html/body/div[5]/div[1]/div[1]/a/img/@src')
        if not big_pic_url_list:
            raise Exception("未找到封面图片URL")

        big_pic_url = 'https://www.javbus.com' + big_pic_url_list[0]
        print(tag, big_pic_url)

        # 获取封面标题
        big_pic_title_list = page.xpath('/html/body/div[5]/h3/text()')
        if not big_pic_title_list:
            raise Exception("未找到封面标题")

        big_pic_title = big_pic_title_list[0]
        print(big_pic_title)

        # 优化文件名处理
        # 1. 移除所有Windows非法字符
        illegal_chars = '[\\/:*?"<>|]'
        clean_title = re.sub(illegal_chars, '_', big_pic_title)
        # 2. 限制文件名长度（Windows限制为255字符，留一些空间给路径）
        max_filename_length = 150
        if len(clean_title) > max_filename_length:
            clean_title = clean_title[:max_filename_length]
        # 3. 确保文件名只包含ASCII字符
        clean_title = clean_title.encode('ascii', 'replace').decode('ascii')
        # 4. 使用车牌号+短标题的格式，提高兼容性
        cover_name = os.path.join(video_path, f'{tag} {clean_title}.jpg')

        # 再次检查封面是否存在（防止多线程竞争）
        if os.path.exists(cover_name):
            print(f'\n【{tag} 封面已存在，跳过下载】\n')
            sem.release()
            return

        # 下载封面图片，增加重试机制
        big_pic = safe_request(url=big_pic_url, headers=headers, proxies=proxy, timeout=20, retry=3)

        with open(cover_name, 'wb') as f:
            f.write(big_pic.content)

        print(f'\n【{tag} 封面大图下载成功】\n')

        with threading.Lock():
            count += 1

        time.sleep(random.randint(3, 6))

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(f'\n【{tag} 错误：404 Not Found - 车牌号不存在或已被删除】\n')
        else:
            print(f'\n【{tag} 错误：HTTP请求失败 - {str(e)}】\n')

        with threading.Lock():
            count1 += 1
            error_list.append((tag, str(e)))

    except requests.exceptions.SSLError as e:
        print(f'\n【{tag} 错误：SSL连接失败 - {str(e)}】\n')
        print("建议检查代理设置或网络连接")

        with threading.Lock():
            count1 += 1
            error_list.append((tag, str(e)))

    except OSError as e:
        if "Invalid argument" in str(e):
            # 如果文件名处理后仍然有问题，使用仅车牌号作为文件名
            simple_cover_name = os.path.join(video_path, f'{tag}.jpg')
            try:
                # 重新下载封面并使用简单文件名
                big_pic = safe_request(url=big_pic_url, headers=headers, proxies=proxy, timeout=20, retry=3)
                with open(simple_cover_name, 'wb') as f:
                    f.write(big_pic.content)
                print(f'\n【{tag} 封面使用简化文件名下载成功】\n')

                with threading.Lock():
                    count += 1
                sem.release()
                return
            except Exception as e2:
                print(f'\n【{tag} 错误：简化文件名后仍下载失败 - {str(e2)}】\n')

                with threading.Lock():
                    count1 += 1
                    error_list.append((tag, str(e2)))
        else:
            print(f'\n【{tag} 错误：文件操作失败 - {str(e)}】\n')

            with threading.Lock():
                count1 += 1
                error_list.append((tag, str(e)))

    except Exception as e:
        print(f'\n【{tag} 错误：{str(e)}】\n')

        with threading.Lock():
            count1 += 1
            error_list.append((tag, str(e)))

    finally:
        sem.release()


def extract_tag(file_name):
    """
    从文件名中提取车牌号（如ABC-123）
    :param file_name: 文件名
    :return: 提取的车牌号或None
    """
    try:
        # 优化正则表达式：字母2-5位，数字2-5位，且必须以字母开头
        match = re.search(r'^([a-zA-Z]{2,5})-(\d{2,5})', file_name, re.IGNORECASE)
        if match:
            return f"{match.group(1)}-{match.group(2)}".upper()
        return None
    except Exception:
        return None


def traverse_directory(root_dir):
    """
    递归遍历目录及其子目录，提取视频文件的车牌号
    :param root_dir: 根目录路径
    :return: 字典，键为车牌号，值为视频所在目录
    """
    video_tags = {}
    video_extensions = ['.mp4', '.mkv', '.avi']

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # 检查当前目录下的所有文件
        for file in filenames:
            if file.endswith(tuple(video_extensions)):
                tag = extract_tag(file)
                if tag:
                    # 检查当前目录下是否已存在对应封面
                    cover_exists = False
                    for pic_file in filenames:
                        if pic_file.endswith('.jpg') and tag in pic_file.upper():
                            cover_exists = True
                            break

                    if not cover_exists:
                        video_tags[tag] = dirpath
                    else:
                        print(f'【{tag} 封面已存在于 {dirpath}，跳过下载】')

    return video_tags


def main():
    """
    主函数
    """
    # 设置根目录
    root_path = "X:/JAV/"

    if not os.path.exists(root_path):
        print(f"目录 {root_path} 不存在，请检查路径设置")
        return

    print(f"开始遍历目录：{root_path}\n")

    # 递归遍历目录，获取需要下载封面的视频信息
    video_tags = traverse_directory(root_path)

    print(f"\n共发现 {len(video_tags)} 个需要下载封面的视频\n")

    if not video_tags:
        print("没有需要下载封面的视频，程序结束")
        return

    print("待下载封面列表：")
    for tag, path in video_tags.items():
        print(f"{tag} - 目录：{path}")

    print(f"\n{'=' * 50}\n")

    # 使用多线程下载封面
    threads = []

    for tag, path in video_tags.items():
        sem.acquire()
        thread = threading.Thread(target=download_cover, args=(tag, path))
        thread.start()
        threads.append(thread)
        time.sleep(0.1)  # 稍微延迟，避免同时发起过多请求

    # 等待所有线程完成
    for t in threads:
        t.join()

    # 打印结果统计
    print(f"\n{'=' * 50}\n")
    print(f"本次任务完成，成功下载封面 {count} 张，失败 {count1} 张\n")

    if error_list:
        print("下载失败列表：")
        for tag, error in error_list:
            print(f"{tag} - 错误：{error}")

    print(f"\n程序执行完毕")


if __name__ == "__main__":
    main()