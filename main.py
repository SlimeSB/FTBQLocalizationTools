#本脚本更替思路受项目https://github.com/djacu/ftbquests_converter启发，并在其框架基础上进行了大量更新与优化，对标当前最新ftbquest的任务生成格式
from hashlib import md5
from pathlib import Path
import re
import random
from typing import Tuple
import requests
from config import *

MAGIC_WORD = r'{xdawned}'
def get_text_fields(quest: str) -> Tuple[str]:
    '''
    截取翻译区域
    :param quest: 任务文本
    :return: 截取到的title,subtitle,description,text文本指针
    '''
    title_line=re.findall(r'\stitle: "(.*)"', quest)
    subtitle_line=re.findall(r'\ssubtitle: "(.*)"', quest)

    # decription_search = re.search(r'\sdescription: \[\n([^]]*)\]', quest)
    # decription_lines = re.findall(r'"(.+)"', decription_search.group(1)) if decription_search else ()#去掉双引号
    decription_lines=re.findall(r'\sdescription: \[[\n]*([^]]*)\]', quest)#先指定以关键字打头，再进一步匹配到左括号略过换行再截取所有右括号前字符，下同
    decription_lines=[re.findall(r'"(.+)"', x) for x in decription_lines]
    decription_lines=[token for t in decription_lines for token in t]#双层遍历降维

    text_search = re.search(r'\stext: \[[\n]*([^]]*)\]', quest)
    text_lines = re.findall(r'"(.+)"', text_search.group(1)) if text_search else ()

    return (*title_line, *subtitle_line, *decription_lines, *text_lines)


def translate_line(line: str) -> str:
    '''
    翻译送来的字符串
    :param line:字符串
    :return:翻译结果字符串
    '''
    try:
        # 关于语言选项参考文档 `https://api.fanyi.baidu.com/doc/21`
        # 百度appid/appkey.（PS：密钥随IP绑定，设置密钥时候注意设置正确的IP否则无法使用！！！）
        appid = APPID  # 请注册你自己的密钥
        appkey = APPKEY  # 请注册你自己的密钥
        from_lang = 'en'
        to_lang = 'zh'
        endpoint = 'http://api.fanyi.baidu.com'
        path = '/api/trans/vip/translate'
        url = endpoint + path

        def make_md5(s, encoding='utf-8'):
            return md5(s.encode(encoding)).hexdigest()

        salt = random.randint(32768, 65536)
        sign = make_md5(appid + line + str(salt) + appkey)

        # Build request
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        payload = {'appid': appid, 'q': line, 'from': from_lang, 'to': to_lang, 'salt': salt,
                   'sign': sign, 'action': 1}

        # Send request
        r = requests.post(url, params=payload, headers=headers)
        result = r.json()
        return result.get('trans_result')[0].get('dst')


    except TypeError:
        '''
        TypeError: 'NoneType' object is not subscriptable
        八成是appid和appkey不正确或申请的服务中绑定的IP设置错误，小概率网络波动原因
        '''
        print("api调用出错")
        return line
        #return translate_line(line)

# magic方法，这样似乎就可以让baidu不翻译颜色代码
def bracket(m: re.Match):
    return "[&"+m.group(0)+"]"
def debracket(m: re.Match):
    return m.group(0)[2:-1]

def pre_process(line:str):
    ## 情景1：图片介绍
    if line.find('.jpg') + line.find('.png') != -2:
        return line  # 新版ftbquest可以展示图片，遇到图片则略过
    ## 情景2：彩色区域
    # 彩色格式保留，碰到&.彩色格式在后方则加入空格分割来辅助百度api优化翻译效果（比如Hello &5world改为Hello &5 world）
    # 强烈建议在术语库中手动添加术语保留&.，否则可能文本格式错误。（目前已知的彩色格式只有a~f,0~9全部依次录入即可）百度api大多可以返回包含&.的汉化结果。
    pattern = re.compile(r'&([a-z,0-9]|#[0-9,A-F]{6})')
    line = pattern.sub(bracket,line)
    print("检测到包含彩色标识的任务,处理为" + line)
    ## 情景3：物品引用
    # 比如#minecraft:coals需要保留,打破此格式将会导致此章任务无法读取！！！
    # 这里给出的方案是先将引用替换为临时词‘xdawned’，术语库中设置xdawned-xdawned来保留此关键词，然后借此在翻译后的句子中定位xdawned用先前引用词换回
    line = re.sub(r'#\w+:\w+\b', MAGIC_WORD , re.sub(r'\\"', '\"',line)) # 辅助忽略转义符
    return line


def post_process(line,translate):
    # 将方括号替换回来
    pattern = re.compile(r'\[&&([a-z,0-9]|#[0-9,A-F]{6})\]')
    translate = pattern.sub(debracket,translate)
    # 将物品引用换回
    quotes=re.findall(r'#\w+:\w+\b', line)#找出所有引用词

    if len(quotes)>0:
        print('在此行找到引用',quotes)
        count=0
        # 找出xdawned出现的所有位置并替换为对应引用词
        index=translate.find(MAGIC_WORD)
        while index!=-1:
            translate=re.sub(MAGIC_WORD,quotes[count],translate,1)
            count=count+1
            index = translate.find(MAGIC_WORD)
        print(translate)
    replacement = translate + "[--" + line + "--]"  # 原文保留
    return replacement

def update_quest(quest: str, text_fields: Tuple[str]) -> str:
    '''
    更新任务中需要汉化的区域
    :param quest:任务
    :param text_fields:摘取出的替换文本
    :return:汉化后任务
    '''
    for line in text_fields:
        pre_processed_line = pre_process(line)
        translate = translate_line(pre_processed_line)
        replacement = post_process(line, translate)
        print("替换中：" + replacement)
        quest = quest.replace('\"' + line + '\"','\"' + replacement + '\"')  # 用双引号卡一下因为多处文本可能相同，防止重复替换替换到其它位置；处理过的就为 "原文[--*--]" 不再参与替换
    return quest


def update_quest_file(input_path: Path, output_path: Path) -> None:
    '''
    更新文件，将处理完的文本写回
    :param input_path:输入目录
    :param output_path:输输出目录
    :return:无
    '''
    with open(input_path, 'r', encoding="utf-8") as fin:
        quest = fin.read()
        text_fields = get_text_fields(quest)# 截取翻译内容
        if not text_fields:
            print(f'无需翻译，未找到截取关键词 {input_path}.')
            print(quest)
        else:
            print(f'开始翻译 {input_path}.')
        new_text = update_quest(quest, text_fields)

    with open(output_path, 'w', encoding="utf-8") as fout:
        fout.write(new_text)


def make_output_path(path: Path) -> Path:
    '''
    生成输出目录，为原文件夹+trans
    :param path:输入目录路径
    :return:自动生成的输出目录路径
    '''
    parts = list(path.parts)
    parts[0] = parts[0] + "-trans"
    output_path = Path(*parts)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def main():
    quest_path = Path(WORK_PATH)#要翻译的目录
    for input_path in quest_path.rglob("*.snbt"):
        output_path = make_output_path(input_path)#生成输出目录路径
        update_quest_file(input_path, output_path)#更新任务文件

if __name__ == '__main__':
    main()#需要先在config.py中填入百度api密钥
