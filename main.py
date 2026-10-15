# -*- coding: utf-8 -*-
"""
================================================================================
 条码拍照 PDF 生成器  (Barcode PDF Maker)          —— 安卓应用 · 主程序源码
================================================================================

一、这个程序做什么
    1) 拍摄 3 张图片。每张图片都可以二选一：
         · 用手机「相机」现场拍摄
         · 从「本地相册 / 文件管理器」里选择已有图片
    2) 允许其中任意一张是「条码图」（一维条形码或二维码都支持），
       程序会自动识别条码内容；
    3) 识别出的条码文本，自动作为最终 PDF 的「文档名称」（即文件名），
       同时允许用户在界面上手动修改；
    4) 3 张图片按顺序合并输出到「同一个 PDF 文件」中（一页放一张图）；
    5) PDF 的保存目录可以自定义：既可以用预设的常用目录，
       也可以手动输入任意路径；
    6) 界面全中文、简洁易懂；全流程做了异常兜底，尽量避免闪退。

二、运行环境
    目标平台：Android 7.0（API 24）及以上，使用 buildozer + python-for-android 打包。
    同时兼容在电脑（Windows / macOS / Linux）上直接运行，方便先看界面效果：
      在电脑上「拍照」会自动退化为「选择本地图片」，其余逻辑完全一致。

三、依赖的第三方库
    kivy        —— 界面框架
    pillow      —— 图片读取、EXIF 方向校正、把多张图片写成 PDF
    pyzbar      —— 条码识别（底层是 libzbar 库；p4a 官方自带 pyzbar / libzbar 配方）
    cffi        —— pyzbar 的底层依赖

四、代码分区（便于阅读）
    第 1 节  基础导入与全局常量
    第 2 节  通用工具函数（文件名净化 / 图片方向校正 / 缩略图 / 弹窗）
    第 3 节  条码识别引擎
    第 4 节  PDF 生成引擎
    第 5 节  存储路径工具（自定义目录 + 逐级回退）
    第 6 节  平台桥接层（安卓：相机 / 相册 / 权限；电脑：文件选择框）
    第 7 节  界面定义（KV 语言，界面长什么样全在这里）
    第 8 节  界面逻辑类
    第 9 节  应用主类
    第 10 节 程序入口
================================================================================
"""

# ==============================================================================
# 第 1 节  基础导入与全局常量
# ==============================================================================

import os
import re
import sys
import time
import traceback

# ---- Kivy 相关 --------------------------------------------------------------
from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.text import LabelBase
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import (BooleanProperty, ListProperty, NumericProperty,
                             StringProperty)
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen, ScreenManager, SlideTransition
from kivy.utils import platform

# ---- 应用级常量 -------------------------------------------------------------
APP_TITLE = '条码PDF生成器'      # 窗口标题（同时也是 APK 里的应用名，见 buildozer.spec）
IMAGE_COUNT = 3                  # 需要拍摄 / 选择的图片张数
CHINESE_FONT = 'ChineseFont'     # 注册给 Kivy 的中文字体名（见 register_fonts）
MAX_NAME_LEN = 60                # 用条码当文件名时的最大长度

# 判断当前是不是真的跑在安卓手机上
IS_ANDROID = (platform == 'android')

# 安卓相关模块只能在安卓上导入，因此这里做条件导入，保证电脑上也能运行
if IS_ANDROID:
    from jnius import autoclass, cast                    # 调用 Java / 安卓原生接口
    from android import activity as android_activity      # 接收 Activity 返回结果
    from android.permissions import (Permission, check_permission,
                                     request_permissions)
    from android.storage import primary_external_storage_path


# ==============================================================================
# 第 2 节  通用工具函数
# ==============================================================================

# 文件名里不允许出现的字符（Windows / Android 都按最严格的标准来过滤），变量存储一个正则表达式对象，匹配所有非法字符
_ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t\x00-\x1f]')


def sanitize_filename(text, fallback=None):
    """
    把一段文本清洗成「可以安全当作文件名」的字符串。

    条码里可能包含斜杠、冒号、问号等特殊字符（例如网址），
    这些字符不能直接用作文件名，必须先过滤，否则保存时必然报错。

    参数：
        text     —— 待清洗的文本（一般是条码内容）
        fallback —— 清洗后如果变成空字符串，就用它兜底
    返回：
        清洗后的文件名（不含扩展名）
    """
    if not text:
        text = ''
    # 1) 去掉会破坏文件名的字符，替换成下划线
    #调用类里的一个函数扫描`text`文本，删掉所有 ILLEGAL_CHARS 正则匹配到的非法字符，得到清洗后的字符串`cleaned`
    cleaned = _ILLEGAL_CHARS.sub('_', str(text))        
    # 2) 把连续空白压成一个空格，再去掉首尾空白和首尾的点（点开头在 Linux 上是隐藏文件）
    cleaned = re.sub(r'\s+', ' ', cleaned).strip().strip('.')
    # 3) 限制长度，避免文件名过长导致保存失败
    if len(cleaned) > MAX_NAME_LEN:
        cleaned = cleaned[:MAX_NAME_LEN].strip()
    # 4) 还是空的就使用兜底名字（带上时间戳，避免重名）
    if not cleaned:
        cleaned = fallback or ('条码文档_%s' % time.strftime('%Y%m%d_%H%M%S'))
    return cleaned


def unique_file_path(directory, base_name, ext):
    """
    在指定目录下生成一个「不会覆盖已有文件」的完整路径。

    如果 xxx.pdf 已经存在，就依次尝试 xxx(1).pdf、xxx(2).pdf ……
    这样用户反复保存同名文件时，旧的文档不会被悄悄覆盖（防数据丢失）。
    """
    candidate = os.path.join(directory, base_name + ext)
    if not os.path.exists(candidate):
        return candidate
    index = 1
    while index < 1000:
        candidate = os.path.join(directory, '%s(%d)%s' % (base_name, index, ext))
        if not os.path.exists(candidate):
            return candidate
        index += 1
    # 极端情况下（同一个名字出现了 1000 次）直接加时间戳
    return os.path.join(directory, '%s_%s%s' % (base_name, time.strftime('%H%M%S'), ext))


def human_size(num_bytes):
    """把字节数变成人类看得懂的大小文字，例如 1.25 MB。"""
    try:                    #捕获异常，防止输入的 num_bytes 不是数字类型
        num_bytes = float(num_bytes)
        for unit in ('B', 'KB', 'MB', 'GB'):
            if num_bytes < 1024.0:
                return '%.2f %s' % (num_bytes, unit)
            num_bytes /= 1024.0
        return '%.2f TB' % num_bytes
    except Exception:
        return '未知'


def open_image_normalized(path):
    """
    用 Pillow 打开一张图片，并做两件标准化处理：

    1) 按 EXIF 信息自动旋转 —— 手机竖着拍的照片，文件里往往是横着存的，
       只是靠 EXIF 里的「方向」标记告诉查看器要转 90°。
       如果不处理，生成的 PDF 里图片就会躺着。
       ImageOps.exif_transpose() 会真正把像素转正。
    2) 统一转成 RGB 模式 —— PDF 不支持带透明通道的 RGBA 模式，
       直接写入会报错，所以用白底把它压平。

    返回：处理好的 PIL.Image 对象（出错时抛出异常，由调用方兜底）
    """
    from PIL import Image, ImageOps
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)          # 按 EXIF 方向转正
    # 带透明通道的图片：铺一层白底再合成，避免转成 PDF 时报错
    if img.mode in ('RGBA', 'LA', 'P'):
        background = Image.new('RGB', img.size, (255, 255, 255))
        rgba = img.convert('RGBA')
        background.paste(rgba, mask=rgba.split()[-1])
        img = background
    elif img.mode != 'RGB':
        img = img.convert('RGB')
    return img


def make_thumbnail(src_path, cache_dir, max_edge=1000):
    """
    生成缩略图，返回缩略图路径。

    为什么要这一步？
      手机拍出来的照片动辄 4000×3000 像素，直接交给 Kivy 显示会占掉
      几十 MB 显存，低端机上很容易被系统杀掉（表现为「闪退」）。
      所以界面上只显示缩略图，条码识别也用较小尺寸的图，既快又省内存。

    max_edge 参数：
      · 界面显示用 1000（默认值）就够清晰了；
      · 条码识别会传更大的值（1600），让条码在图中占比更大、更容易认出来。

    缓存文件名里带了「尺寸 + 文件大小 + 原名」作为标识，
    避免两张同名图片（或显示图与识别图）互相覆盖。

    如果生成失败，就原样返回原图路径，保证流程不中断。
    """
    try:
        os.makedirs(cache_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(src_path))[0]
        try:
            file_size = os.path.getsize(src_path)
        except Exception:
            file_size = 0
        dst_path = os.path.join(
            cache_dir, 'thumb_%d_%d_%s.jpg' % (max_edge, file_size, base[-30:]))
        # 已经生成过就直接复用，避免重复计算
        if os.path.exists(dst_path) and os.path.getsize(dst_path) > 0:
            return dst_path
        img = open_image_normalized(src_path)
        img.thumbnail((max_edge, max_edge))
        img.save(dst_path, 'JPEG', quality=85)
        img.close()
        return dst_path
    except Exception:
        traceback.print_exc()
        return src_path


def show_message(title, text):
    """弹出一个简单的提示框（所有出错提示、成功提示都走这里）。"""
    try:
        content = BoxLayout(orientation='vertical', spacing=dp(10),
                            padding=dp(14), size_hint_y=None)
        content.bind(minimum_height=content.setter('height'))
        content.add_widget(MsgLabel(text=text))

        button = PlainButton(text='知道了', size_hint_y=None, height=dp(46))
        content.add_widget(button)

        popup = Popup(title=title, title_font=App.get_running_app().ui_font,
                      content=content, size_hint=(0.88, None), height=dp(280),
                      separator_color=(0.15, 0.53, 0.92, 1))
        button.bind(on_release=popup.dismiss)
        popup.open()
    except Exception:
        # 连弹窗都失败时，至少打印到日志，绝不让异常继续往外抛
        traceback.print_exc()


# ==============================================================================
# 第 3 节  条码识别引擎
# ==============================================================================

def _decode_bytes(raw):
    """
    条码原始数据是 bytes，需要转成文本。
    常见编码是 UTF-8；部分老设备/老码制用 GBK；
    都失败时用 latin-1 兜底（保证一定能出结果，不抛异常）。
    """
    if raw is None:
        return ''
    if isinstance(raw, str):
        return raw
    for encoding in ('utf-8', 'gbk', 'latin-1'):
        try:
            return raw.decode(encoding).strip()
        except Exception:
            continue
    return str(raw)


def _build_scan_variants(gray_image):
    """
    生成多个「扫描变体」。

    条码识别的现实情况：zbar 对「摆正的、足够大的、对比度够的」条码识别率最高。
    而用户拍的照片可能歪了、糊了、太小了。所以这里把同一张图
    做几种变换，逐个尝试，能显著提高识别成功率。

    生成顺序（先试最可能的，命中就返回）：
        1. 原图灰度
        2. 放大 2 倍（针对条码太小的情况）
        3. 依次旋转 90° / 180° / 270°（针对横竖拍反、拍倒的情况）
    """
    from PIL import Image
    yield gray_image                                        # 1. 原图
    width, height = gray_image.size
    if max(width, height) < 2000 and width > 0:             # 2. 放大 2 倍
        try:
            yield gray_image.resize((width * 2, height * 2), Image.LANCZOS)
        except Exception:
            pass
    for angle in (90, 180, 270):                            # 3. 旋转
        try:
            yield gray_image.rotate(angle, expand=True)
        except Exception:
            pass


def decode_barcode(image_path, prefer_size=2000):
    """
    从一张图片里识别条码。

    返回：(条码文本, 码制名称)
        例如 ('6901234567892', 'EAN13')
        识别不到时返回 ('', '')

    说明：
      · 识别引擎是 pyzbar（底层为 libzbar）。如果运行环境里没有装好这个库，
        本函数会老老实实返回空字符串，由界面引导用户手动填写文档名称，
        绝不会因此抛出异常导致应用崩溃。
      · 为了速度，识别前会先把图片等比缩小到 prefer_size 像素以内再扫描。
        这个值不宜太小，否则画面里的条码会被缩得看不清（识别不出来）。
    """
    text, code_type = '', ''
    try:
        from pyzbar.pyzbar import decode as zbar_decode
    except Exception:
        # 运行环境缺少 pyzbar（或它的底层 libzbar）时，安静地返回空结果
        return '', ''

    try:
        from PIL import Image
        # 读图 → 转正 → 转灰度（灰度图识别速度快很多）
        img = open_image_normalized(image_path).convert('L')
        width, height = img.size
        if max(width, height) > prefer_size:
            ratio = float(prefer_size) / float(max(width, height))
            img = img.resize((max(1, int(width * ratio)),
                              max(1, int(height * ratio))), Image.LANCZOS)

        for variant in _build_scan_variants(img):
            try:
                results = zbar_decode(variant)
            except Exception:
                continue
            if results:
                best = results[0]
                text = _decode_bytes(best.data)
                code_type = str(getattr(best, 'type', '') or '')
                if text:
                    return text, code_type
    except Exception:
        traceback.print_exc()
    return text, code_type


def decode_barcode_from_many(paths):
    """
    依次尝试多张图片，只要任意一张能识别出条码就返回。
    （需求里说「其中一张是条码图」，但用户不一定记得是哪一张，
      所以三张都试一遍，体验更好。）

    返回：(条码文本, 码制名称, 命中的图片序号)
    """
    for index, path in enumerate(paths):
        if not path or not os.path.exists(path):
            continue
        text, code_type = decode_barcode(path)
        if text:
            return text, code_type, index
    return '', '', -1


# ==============================================================================
# 第 4 节  PDF 生成引擎
# ==============================================================================

def images_to_pdf(image_paths, pdf_path, max_pixel=3500):
    """
    把多张图片合并写进一个 PDF 文件（一页一张图）。

    参数：
        image_paths —— 图片文件的完整路径列表（按顺序，就是 PDF 的页序）
        pdf_path    —— 输出的 PDF 完整路径
        max_pixel   —— 单张图片最长边的上限。超过就等比缩小，
                       否则 PDF 会非常大、打开很卡。

    实现说明：
        使用 Pillow 的 PDF 保存能力。
        save_all=True + append_images 是 Pillow 写多页 PDF 的标准做法，
        每一页会自动采用该图片自身的像素尺寸作为页面尺寸，
        因此图片保持原始比例、不会变形。
    """
    from PIL import Image

    if not image_paths:
        raise ValueError('没有可用的图片')

    pages = []
    try:
        for path in image_paths:
            img = open_image_normalized(path)
            width, height = img.size
            # 过大的图片等比缩小，兼顾清晰度和文件体积
            if max(width, height) > max_pixel:
                ratio = float(max_pixel) / float(max(width, height))
                img = img.resize((max(1, int(width * ratio)),
                                  max(1, int(height * ratio))), Image.LANCZOS)
            pages.append(img)

        if not pages:
            raise ValueError('没有可用的图片')

        # resolution 表示写入 PDF 时按 150 DPI 计算物理尺寸
        pages[0].save(pdf_path, 'PDF', resolution=150.0,
                      save_all=True, append_images=pages[1:])
    finally:
        # 无论成功失败都及时释放图片对象，避免占用内存
        for page in pages:
            try:
                page.close()
            except Exception:
                pass

    # 双重校验：确认文件真的生成且不是空文件
    if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) <= 0:
        raise IOError('PDF 文件写入失败：%s' % pdf_path)


# ==============================================================================
# 第 5 节  存储路径工具
# ==============================================================================

def app_private_dir():
    """应用私有目录（一定可写，卸载应用时会被清空）。"""
    try:
        return App.get_running_app().user_data_dir
    except Exception:
        return os.path.expanduser('~')


def public_storage_root():
    """公共存储根目录，通常是 /storage/emulated/0（也就是「内部存储」）。"""
    if IS_ANDROID:
        try:
            return primary_external_storage_path()
        except Exception:
            return '/storage/emulated/0'
    # 电脑上：用用户主目录模拟
    return os.path.expanduser('~')


def default_save_dir():
    """
    给出一个「默认的保存目录」。

    策略：优先选用户能找到的公共目录（Documents / Download），
          如果那些目录不可写（安卓 11 以上对公共目录有写入限制），
          就退回到本应用的私有目录，保证「一定保存成功」。
    """
    root = public_storage_root()
    candidates = [
        os.path.join(root, 'Documents'),
        os.path.join(root, 'Download'),
        os.path.join(root, 'BarcodePDF'),
        app_private_dir(),
    ]
    for path in candidates:
        if is_dir_writable(path):
            return path
    return app_private_dir()


def is_dir_writable(path):
    """判断目录是否存在且可写（不存在就尝试创建）。"""
    try:
        if not path:
            return False
        os.makedirs(path, exist_ok=True)
        # 真正写一个小文件测试，比 os.access 更可靠（安卓上尤其如此）
        probe = os.path.join(path, '.bpdf_write_test')
        with open(probe, 'w') as handle:
            handle.write('ok')
        os.remove(probe)
        return True
    except Exception:
        return False


def save_pdf_with_fallback(image_paths, target_dir, base_name):
    """
    生成 PDF 并保存，内部做「逐级回退」，确保不会因为目录不可写而失败。

    尝试顺序：
        1. 用户指定的目录
        2. 公共 Documents 目录
        3. 公共 Download 目录
        4. 应用私有目录（兜底，一定成功）

    返回：(成功时的完整路径, 失败时的错误说明)
        成功 → (path, None)
        失败 → (None, '尝试过的目录及原因……')
    """
    root = public_storage_root()
    fallback_dirs = []
    for path in (target_dir,
                 os.path.join(root, 'Documents'),
                 os.path.join(root, 'Download'),
                 app_private_dir()):
        if path and path not in fallback_dirs:
            fallback_dirs.append(path)

    errors = []
    for directory in fallback_dirs:
        try:
            os.makedirs(directory, exist_ok=True)
            pdf_path = unique_file_path(directory, base_name, '.pdf')
            images_to_pdf(image_paths, pdf_path)
            return pdf_path, None
        except Exception as exc:
            errors.append('%s → %s' % (directory, exc))
            traceback.print_exc()

    return None, '所有目录都无法写入：\n' + '\n'.join(errors)


# ==============================================================================
# 第 6 节  平台桥接层
# ==============================================================================

class AndroidBridge(object):
    """
    安卓平台桥接层：把「拍照」「选相册」「权限」这些必须调用安卓原生接口的
    操作集中在这一个类里。

    相机是怎么拿到高清原图的？
    --------------------------
    直接调用系统相机（Intent）时，如果不告诉它把照片存到哪里，它只会回传
    一张几百像素的缩略图，条码根本认不出来。
    正确做法是把一个「输出位置」塞进 Intent。但从 Android 7.0 开始，
    不允许再把 file:// 路径直接传给别的应用（会抛 FileUriExposedException）。

    因此这里采用最稳妥的做法：
        先通过 MediaStore 往系统相册库里「插入一条空记录」，
        拿到系统给的 content:// 地址，再把这个地址交给相机去写。
        相机写完后，我们再从同一个地址把图片读出来（或复制到本地）。
    这个方案不需要 FileProvider，也不用改 AndroidManifest，
    在各版本安卓上兼容性最好。
    """

    REQ_CAPTURE = 1001      # 拍照的请求码
    REQ_PICK = 1002         # 相册选择的请求码
    RESULT_OK = -1          # 安卓里 Activity.RESULT_OK 的值就是 -1

    def __init__(self, app):
        self.app = app
        self.pending_index = -1     # 当前这次拍照/选图是给第几张图用的
        self.pending_uri = None     # 相机将要写入的 content:// 地址

    # ---------- 生命周期 ----------
    def bind_activity_result(self):
        """注册 Activity 返回结果监听，这样拍照/选图结束后我们能收到通知。"""
        try:
            android_activity.bind(on_activity_result=self._on_activity_result)
        except Exception:
            traceback.print_exc()

    # ---------- 权限 ----------
    def request_base_permissions(self):
        """申请基础权限（相机、读写存储）。缺权限时应用不会崩，只会功能受限。"""
        names = ('CAMERA', 'READ_EXTERNAL_STORAGE',
                 'WRITE_EXTERNAL_STORAGE', 'READ_MEDIA_IMAGES')
        permissions = []
        for name in names:
            value = getattr(Permission, name, None)
            if value and value not in permissions:
                permissions.append(value)
        try:
            request_permissions(permissions)
        except Exception:
            traceback.print_exc()

    def is_all_files_access_granted(self):
        """
        是否已经拿到「所有文件访问权限」（Android 11+ 才需要）。

        有这个权限，才能把文件保存到用户手动输入的任意路径；
        没有的话，程序仍能正常保存到公共 Documents / Download 或应用私有目录。
        """
        try:
            version = autoclass('android.os.Build$VERSION')
            if version.SDK_INT < 30:
                return True
            Environment = autoclass('android.os.Environment')
            return bool(Environment.isExternalStorageManager())
        except Exception:
            return True

    def request_all_files_access(self):
        """
        跳转到系统设置页，请用户为本应用打开「所有文件访问权限」。
        这是安卓官方允许的方式（不能靠普通权限弹窗申请）。
        """
        try:
            version = autoclass('android.os.Build$VERSION')
            if version.SDK_INT < 30:
                show_message('提示', '当前安卓版本无需此权限。')
                return
            Intent = autoclass('android.content.Intent')
            Uri = autoclass('android.net.Uri')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity

            intent = Intent('android.settings.MANAGE_APP_ALL_FILES_ACCESS_PERMISSION')
            intent.setData(Uri.parse('package:' + activity.getPackageName()))
            activity.startActivity(intent)
        except Exception:
            traceback.print_exc()
            show_message('提示', '无法自动打开设置页，请手动到：\n'
                                 '系统设置 → 应用 → %s → 权限 → 文件和媒体，'
                                 '选择「允许管理所有文件」。' % APP_TITLE)

    # ---------- 拍照 ----------
    def take_photo(self, index):
        """打开系统相机拍照，拍完的照片会通知回第 index 个图片槽位。"""
        self.pending_index = index
        try:
            Intent = autoclass('android.content.Intent')
            MediaStore = autoclass('android.provider.MediaStore')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity

            uri = self._create_output_uri()
            if uri is None:
                show_message('无法拍照', '系统没有返回可用的存储位置，\n请改用「从相册选择」。')
                return
            self.pending_uri = uri

            intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
            intent.putExtra(MediaStore.EXTRA_OUTPUT,
                            cast('android.os.Parcelable', uri))
            intent.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            activity.startActivityForResult(intent, self.REQ_CAPTURE)
        except Exception:
            traceback.print_exc()
            show_message('无法打开相机',
                         '请确认手机上有可用的相机应用，\n或改用「从相册选择」。')

    def _create_output_uri(self):
        """
        通过 MediaStore 申请一个「相机的输出位置」，返回 content:// 地址。
        Android 10(Api 29) 及以上用 relative_path 指定相册子目录；
        更低版本则直接给出文件路径（_data 列）。
        """
        try:
            ContentValues = autoclass('android.content.ContentValues')
            MediaImages = autoclass('android.provider.MediaStore$Images$Media')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity
            resolver = activity.getContentResolver()

            file_name = 'bpdf_%s.jpg' % time.strftime('%Y%m%d_%H%M%S')
            values = ContentValues()
            values.put('_display_name', file_name)
            values.put('mime_type', 'image/jpeg')

            version = autoclass('android.os.Build$VERSION')
            if version.SDK_INT >= 29:
                values.put('relative_path', 'Pictures/BarcodePDF')
            else:
                target_dir = os.path.join(public_storage_root(),
                                          'Pictures', 'BarcodePDF')
                os.makedirs(target_dir, exist_ok=True)
                values.put('_data', os.path.join(target_dir, file_name))

            return resolver.insert(MediaImages.EXTERNAL_CONTENT_URI, values)
        except Exception:
            traceback.print_exc()
            return None

    # ---------- 相册 / 文件选择 ----------
    def pick_gallery(self, index):
        """打开系统相册（文件选择器）让用户挑一张图片。"""
        self.pending_index = index
        try:
            Intent = autoclass('android.content.Intent')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity

            intent = Intent(Intent.ACTION_GET_CONTENT)
            intent.setType('image/*')
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            try:
                chooser = Intent.createChooser(intent, '选择图片')
                activity.startActivityForResult(chooser, self.REQ_PICK)
            except Exception:
                activity.startActivityForResult(intent, self.REQ_PICK)
        except Exception:
            traceback.print_exc()
            show_message('无法打开相册', '请稍后重试，或改用「拍照」。')

    # ---------- 接收返回结果 ----------
    @mainthread
    def _on_activity_result(self, request_code, result_code, intent):
        """系统相机 / 相册返回后，会走到这里。"""
        try:
            if request_code == self.REQ_CAPTURE:
                self._handle_capture(result_code)
            elif request_code == self.REQ_PICK:
                self._handle_pick(result_code, intent)
        except Exception:
            traceback.print_exc()
            show_message('出错了', '处理图片时发生错误，请重试。')

    def _handle_capture(self, result_code):
        """拍照结束：把 content:// 地址转换成可用的本地图片文件。"""
        if result_code != self.RESULT_OK:
            self.pending_uri = None
            return      # 用户取消了拍照，安静地忽略
        uri = self.pending_uri
        self.pending_uri = None
        if uri is None:
            return

        local_path = self._uri_to_local_path(uri, 'camera')
        if not local_path:
            show_message('读取失败', '拍照成功但无法读取照片，\n请重试或改用「从相册选择」。')
            return
        self.app.on_image_ready(self.pending_index, local_path)

    def _handle_pick(self, result_code, intent):
        """相册选择结束：把选中的 content:// 地址转换成可用的本地图片文件。"""
        if result_code != self.RESULT_OK or intent is None:
            return      # 用户取消了选择
        data = intent.getData()
        if data is None:
            return
        local_path = self._uri_to_local_path(data, 'picked')
        if not local_path:
            show_message('读取失败', '无法读取所选图片，请换一张试试。')
            return
        self.app.on_image_ready(self.pending_index, local_path)

    def _uri_to_local_path(self, uri, prefix):
        """
        把一个 content:// 地址变成实实在在的本地文件路径。

        三级策略（能用简单的就用简单的）：
          1. 查询 _data 列 —— 大多数相册图片都能直接拿到真实路径，零拷贝；
          2. 用 android.os.FileUtils.copy 把数据流复制到应用缓存目录（API 29+）；
          3. 用 BitmapFactory 解码后重新压缩保存（兼容所有版本，作为最终兜底）。
        """
        # --- 策略 1：直接查真实路径 ---
        try:
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity
            resolver = activity.getContentResolver()
            cursor = resolver.query(uri, None, None, None, None)
            if cursor is not None:
                try:
                    if cursor.moveToFirst():
                        index = cursor.getColumnIndex('_data')
                        if index >= 0:
                            candidate = cursor.getString(index)
                            if candidate and os.path.exists(candidate):
                                return candidate
                finally:
                    cursor.close()
        except Exception:
            traceback.print_exc()

        # --- 策略 2 / 3：复制到应用缓存目录 ---
        try:
            temp_dir = os.path.join(app_private_dir(), 'pictures')
            os.makedirs(temp_dir, exist_ok=True)
            dest = os.path.join(temp_dir, '%s_%s.jpg'
                                % (prefix, time.strftime('%Y%m%d_%H%M%S')))

            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity
            resolver = activity.getContentResolver()
            stream = resolver.openInputStream(uri)
            if stream is None:
                return ''

            saved = False
            # 策略 2：FileUtils.copy（API 29 及以上）
            try:
                version = autoclass('android.os.Build$VERSION')
                if version.SDK_INT >= 29:
                    FileUtils = autoclass('android.os.FileUtils')
                    FileOutputStream = autoclass('java.io.FileOutputStream')
                    output = FileOutputStream(dest)
                    try:
                        FileUtils.copy(stream, output)
                        saved = True
                    finally:
                        output.close()
            except Exception:
                saved = False

            # 策略 3：解码成位图再重新压缩保存（兜底方案）
            if not saved:
                BitmapFactory = autoclass('android.graphics.BitmapFactory')
                Bitmap = autoclass('android.graphics.Bitmap')
                FileOutputStream = autoclass('java.io.FileOutputStream')
                stream.close()
                stream = resolver.openInputStream(uri)
                bitmap = BitmapFactory.decodeStream(stream)
                if bitmap is None:
                    return ''
                output = FileOutputStream(dest)
                try:
                    bitmap.compress(Bitmap.CompressFormat.JPEG, 92, output)
                    saved = True
                finally:
                    output.close()
                    bitmap.recycle()

            stream.close()
            if saved and os.path.exists(dest) and os.path.getsize(dest) > 0:
                return dest
        except Exception:
            traceback.print_exc()
        return ''


class DesktopBridge(object):
    """
    电脑平台桥接层。

    纯粹为了「不装安卓手机也能先看界面效果」而存在：
      电脑上没有系统相机，于是「拍照」按钮直接弹出文件选择框。
    逻辑与安卓版完全一致，只是取图方式不同。
    """

    def __init__(self, app):
        self.app = app

    def bind_activity_result(self):
        pass

    def request_base_permissions(self):
        pass

    def is_all_files_access_granted(self):
        return True

    def request_all_files_access(self):
        show_message('提示', '该功能仅在安卓手机上需要。')

    def take_photo(self, index):
        self._choose_file(index)

    def pick_gallery(self, index):
        self._choose_file(index)

    def _choose_file(self, index):
        """弹出一个文件选择框，让用户点选一张图片。"""
        try:
            content = BoxLayout(orientation='vertical', spacing=dp(8),
                                padding=dp(10))
            chooser = FileChooserListView(path=os.path.expanduser('~'),
                                          filters=['*.png', '*.jpg', '*.jpeg',
                                                   '*.bmp', '*.webp', '*.gif'])
            content.add_widget(chooser)

            buttons = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(10))
            cancel = PlainButton(text='取消')
            confirm = PlainButton(text='选择这张')
            buttons.add_widget(cancel)
            buttons.add_widget(confirm)
            content.add_widget(buttons)

            popup = Popup(title='选择一张图片', title_font=App.get_running_app().ui_font,
                          content=content, size_hint=(0.92, 0.92))

            def on_confirm(*_args):
                selection = chooser.selection
                popup.dismiss()
                if selection:
                    self.app.on_image_ready(index, selection[0])

            cancel.bind(on_release=popup.dismiss)
            confirm.bind(on_release=on_confirm)
            popup.open()
        except Exception:
            traceback.print_exc()


# ==============================================================================
# 第 7 节  界面定义（KV 语言）
# ==============================================================================
# 说明：
#   下面这一整段描述的是「界面长什么样、控件怎么摆」。
#   所有文字都是中文，按钮都做得比较大，方便手指点击。
#   三种颜色：主色蓝 rgb(0.15,0.53,0.92)，文字深灰，背景浅灰白。
# ==============================================================================

KV = r'''
#:import dp kivy.metrics.dp

# ---------------------------------------------------------------- 全局控件样式
# 让所有文本控件都使用注册好的中文字体（否则中文会显示成方框）
<Label>:
    font_name: app.ui_font
    color: 0.18, 0.20, 0.23, 1

<MsgLabel>:
    font_name: app.ui_font
    halign: 'left'
    valign: 'middle'
    color: 0.18, 0.20, 0.23, 1
    text_size: self.width, None
    size_hint_y: None
    height: self.texture_size[1] + dp(6)

# 主按钮（蓝色实心）
<MainButton>:
    font_name: app.ui_font
    font_size: '17sp'
    color: 1, 1, 1, 1
    background_normal: ''
    background_down: ''
    background_color: 0, 0, 0, 0
    canvas.before:
        Color:
            rgba: (0.10, 0.40, 0.72, 1) if self.state == 'down' else (0.15, 0.53, 0.92, 1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(9)]
        Color:
            rgba: 0.55, 0.58, 0.62, 1 if self.disabled else 0
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(9)]

# 次按钮（浅灰描边）
<PlainButton>:
    font_name: app.ui_font
    font_size: '16sp'
    color: 0.15, 0.53, 0.92, 1
    background_normal: ''
    background_down: ''
    background_color: 0, 0, 0, 0
    canvas.before:
        Color:
            rgba: (0.90, 0.94, 0.99, 1) if self.state == 'down' else (0.965, 0.975, 0.99, 1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(9)]
        Color:
            rgba: 0.75, 0.80, 0.86, 1
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, dp(9))
            width: 1

<TextInput>:
    font_name: app.ui_font
    font_size: '16sp'
    multiline: False
    padding: dp(12), dp(14)
    background_color: 0, 0, 0, 0
    foreground_color: 0.14, 0.16, 0.19, 1
    cursor_color: 0.15, 0.53, 0.92, 1
    hint_text_color: 0.62, 0.66, 0.70, 1
    canvas.before:
        Color:
            rgba: 0.75, 0.80, 0.86, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(9)]
        Color:
            rgba: 1, 1, 1, 1
        RoundedRectangle:
            pos: self.x + dp(1), self.y + dp(1)
            size: self.width - dp(2), self.height - dp(2)
            radius: [dp(8)]

<Spinner>:
    font_name: app.ui_font
    font_size: '16sp'
    background_normal: ''
    background_down: ''
    background_color: 0, 0, 0, 0
    color: 0.15, 0.53, 0.92, 1
    canvas.before:
        Color:
            rgba: 0.965, 0.975, 0.99, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(9)]
        Color:
            rgba: 0.75, 0.80, 0.86, 1
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, dp(9))
            width: 1

# ---------------------------------------------------------------- 单张图片卡片
# 每张图片一个卡片：标题 + 状态 + 预览图 + 「拍照」「从相册选择」两个按钮
<ImageSlot>:
    orientation: 'vertical'
    padding: dp(10)
    spacing: dp(8)
    size_hint_y: None
    height: dp(232)
    canvas.before:
        Color:
            rgba: 1, 1, 1, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12)]
        Color:
            rgba: 0.85, 0.88, 0.92, 1
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, dp(12))
            width: 1

    BoxLayout:
        size_hint_y: None
        height: dp(26)
        Label:
            text: root.title_text
            bold: True
            font_size: '16sp'
            halign: 'left'
            valign: 'middle'
            text_size: self.size
        Label:
            text: root.status_text
            font_size: '14sp'
            halign: 'right'
            valign: 'middle'
            text_size: self.size
            color: (0.11, 0.58, 0.33, 1) if root.has_image else (0.85, 0.45, 0.20, 1)

    FloatLayout:
        size_hint_y: None
        height: dp(112)
        canvas.before:
            Color:
                rgba: 0.94, 0.96, 0.98, 1
            RoundedRectangle:
                pos: self.pos
                size: self.size
                radius: [dp(8)]
        Image:
            source: root.thumb_path
            opacity: 1 if root.has_image else 0
            allow_stretch: True
            keep_ratio: True
            size_hint: 1, 1
            pos_hint: {'x': 0, 'y': 0}
        Label:
            text: root.hint_text
            opacity: 0 if root.has_image else 1
            color: 0.60, 0.64, 0.68, 1
            font_size: '15sp'
            halign: 'center'
            valign: 'middle'
            text_size: self.size

    BoxLayout:
        size_hint_y: None
        height: dp(46)
        spacing: dp(10)
        MainButton:
            text: '拍照'
            on_release: root.do_take_photo()
        PlainButton:
            text: '从相册选择'
            on_release: root.do_pick_gallery()

# ---------------------------------------------------------------- 1. 首页
<WelcomeScreen>:
    name: 'welcome'
    BoxLayout:
        orientation: 'vertical'
        padding: dp(24)
        spacing: dp(14)
        canvas.before:
            Color:
                rgba: 0.967, 0.973, 0.98, 1
            Rectangle:
                pos: self.pos
                size: self.size
        Widget:
            size_hint_y: 0.12
        Label:
            text: '条码 PDF 生成器'
            font_size: '29sp'
            bold: True
            size_hint_y: None
            height: dp(46)
        Label:
            text: '拍摄 3 张图片（其中一张为条码图）\n自动读取条码、合并生成 PDF 文档'
            halign: 'center'
            valign: 'middle'
            font_size: '16sp'
            color: 0.40, 0.44, 0.48, 1
            size_hint_y: None
            height: dp(66)
            text_size: self.width, None
        Widget:
            size_hint_y: 0.06
        MainButton:
            text: '开始拍照'
            size_hint_y: None
            height: dp(58)
            on_release: app.start_new_document()
        PlainButton:
            text: '使用说明'
            size_hint_y: None
            height: dp(48)
            on_release: app.show_help()
        Widget:
            size_hint_y: 0.30

# ---------------------------------------------------------------- 2. 拍照页
<CaptureScreen>:
    name: 'capture'
    BoxLayout:
        orientation: 'vertical'
        padding: dp(12)
        spacing: dp(10)
        canvas.before:
            Color:
                rgba: 0.967, 0.973, 0.98, 1
            Rectangle:
                pos: self.pos
                size: self.size

        BoxLayout:
            size_hint_y: None
            height: dp(44)
            spacing: dp(8)
            PlainButton:
                text: '返回'
                size_hint_x: None
                width: dp(84)
                on_release: app.go_home()
            Label:
                text: '第 1 步：准备 3 张图片'
                bold: True
                font_size: '18sp'
                halign: 'center'
                valign: 'middle'
                text_size: self.size

        Label:
            text: root.progress_text
            size_hint_y: None
            height: dp(24)
            font_size: '15sp'
            color: 0.40, 0.44, 0.48, 1
            halign: 'center'
            valign: 'middle'
            text_size: self.size

        ScrollView:
            do_scroll_x: False
            BoxLayout:
                id: slot_box
                orientation: 'vertical'
                spacing: dp(10)
                size_hint_y: None
                height: self.minimum_height

        MainButton:
            text: '下一步：生成 PDF'
            disabled: not root.all_ready
            size_hint_y: None
            height: dp(54)
            on_release: app.go_preview()

# ---------------------------------------------------------------- 3. 预览页
<PreviewScreen>:
    name: 'preview'
    BoxLayout:
        orientation: 'vertical'
        padding: dp(12)
        spacing: dp(10)
        canvas.before:
            Color:
                rgba: 0.967, 0.973, 0.98, 1
            Rectangle:
                pos: self.pos
                size: self.size

        BoxLayout:
            size_hint_y: None
            height: dp(44)
            spacing: dp(8)
            PlainButton:
                text: '返回'
                size_hint_x: None
                width: dp(84)
                on_release: app.go_capture()
            Label:
                text: '第 2 步：确认信息'
                bold: True
                font_size: '18sp'
                halign: 'center'
                valign: 'middle'
                text_size: self.size

        ScrollView:
            do_scroll_x: False
            BoxLayout:
                orientation: 'vertical'
                spacing: dp(12)
                size_hint_y: None
                height: self.minimum_height

                # 三张缩略图
                BoxLayout:
                    id: thumb_box
                    size_hint_y: None
                    height: dp(104)
                    spacing: dp(8)

                # 条码识别结果卡片
                BoxLayout:
                    orientation: 'vertical'
                    size_hint_y: None
                    height: self.minimum_height
                    padding: dp(12)
                    spacing: dp(8)
                    canvas.before:
                        Color:
                            rgba: 1, 1, 1, 1
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(12)]
                    Label:
                        text: '条码识别结果'
                        bold: True
                        font_size: '16sp'
                        halign: 'left'
                        valign: 'middle'
                        text_size: self.size
                        size_hint_y: None
                        height: dp(26)
                    Label:
                        text: root.barcode_status
                        font_size: '15sp'
                        color: 0.30, 0.50, 0.72, 1
                        halign: 'left'
                        valign: 'middle'
                        text_size: self.width, None
                        size_hint_y: None
                        height: self.texture_size[1] + dp(8)
                    BoxLayout:
                        size_hint_y: None
                        height: dp(44)
                        spacing: dp(10)
                        PlainButton:
                            text: '重新识别'
                            on_release: root.start_recognition()
                        PlainButton:
                            text: '手动填写'
                            on_release: root.focus_name_input()

                # 文档名称
                BoxLayout:
                    orientation: 'vertical'
                    size_hint_y: None
                    height: self.minimum_height
                    padding: dp(12)
                    spacing: dp(8)
                    canvas.before:
                        Color:
                            rgba: 1, 1, 1, 1
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(12)]
                    Label:
                        text: '文档名称（就是 PDF 的文件名）'
                        bold: True
                        font_size: '16sp'
                        halign: 'left'
                        valign: 'middle'
                        text_size: self.size
                        size_hint_y: None
                        height: dp(26)
                    TextInput:
                        id: name_input
                        text: root.doc_name
                        hint_text: '请输入文档名称'
                        size_hint_y: None
                        height: dp(48)
                        on_text: root.doc_name = self.text

                # 保存位置
                BoxLayout:
                    orientation: 'vertical'
                    size_hint_y: None
                    height: self.minimum_height
                    padding: dp(12)
                    spacing: dp(8)
                    canvas.before:
                        Color:
                            rgba: 1, 1, 1, 1
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(12)]
                    Label:
                        text: '保存位置（可自定义）'
                        bold: True
                        font_size: '16sp'
                        halign: 'left'
                        valign: 'middle'
                        text_size: self.size
                        size_hint_y: None
                        height: dp(26)
                    Spinner:
                        id: dir_spinner
                        text: '选择常用目录'
                        values: root.preset_labels
                        size_hint_y: None
                        height: dp(46)
                        on_text: root.on_preset_chosen(self.text)
                    TextInput:
                        id: dir_input
                        text: root.save_dir
                        hint_text: '也可以直接输入完整路径'
                        size_hint_y: None
                        height: dp(48)
                        on_text: root.save_dir = self.text
                    Label:
                        text: root.dir_hint
                        font_size: '13sp'
                        color: 0.55, 0.58, 0.62, 1
                        halign: 'left'
                        valign: 'middle'
                        text_size: self.width, None
                        size_hint_y: None
                        height: self.texture_size[1] + dp(6)
                    PlainButton:
                        text: '申请「所有文件访问」权限（安卓11＋可选）'
                        font_size: '14sp'
                        size_hint_y: None
                        height: dp(44)
                        opacity: 1 if root.show_permission_button else 0
                        disabled: not root.show_permission_button
                        on_release: root.request_all_files_access()

        MainButton:
            text: '生成 PDF 文档'
            size_hint_y: None
            height: dp(56)
            on_release: root.do_generate_pdf()

# ---------------------------------------------------------------- 4. 结果页
<ResultScreen>:
    name: 'result'
    BoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(12)
        canvas.before:
            Color:
                rgba: 0.967, 0.973, 0.98, 1
            Rectangle:
                pos: self.pos
                size: self.size
        Widget:
            size_hint_y: 0.08
        Label:
            text: '生成成功'
            font_size: '26sp'
            bold: True
            color: 0.11, 0.58, 0.33, 1
            size_hint_y: None
            height: dp(44)
        Label:
            text: root.result_title
            font_size: '17sp'
            size_hint_y: None
            height: dp(28)
        Label:
            text: '文件保存位置：'
            font_size: '15sp'
            color: 0.40, 0.44, 0.48, 1
            halign: 'left'
            valign: 'middle'
            text_size: self.size
            size_hint_y: None
            height: dp(24)
        TextInput:
            text: root.pdf_path
            readonly: True
            size_hint_y: None
            height: dp(84)
            multiline: True
            font_size: '14sp'
        Label:
            text: root.result_detail
            font_size: '15sp'
            color: 0.40, 0.44, 0.48, 1
            halign: 'left'
            valign: 'middle'
            text_size: self.width, None
            size_hint_y: None
            height: self.texture_size[1] + dp(8)
        Widget:
            size_hint_y: 0.10
        MainButton:
            text: '继续制作下一份'
            size_hint_y: None
            height: dp(54)
            on_release: app.start_new_document()
        PlainButton:
            text: '返回首页'
            size_hint_y: None
            height: dp(48)
            on_release: app.go_home()
        Widget:
            size_hint_y: 0.16
'''


# ==============================================================================
# 第 8 节  界面逻辑类
# ==============================================================================

class MsgLabel(Label):
    """弹窗里用的会自动换行、自己撑高的文字控件（样式见 KV 里的 <MsgLabel>）。"""
    pass


class MainButton(Button):
    """
    主按钮（蓝色实心）。

    继承 Kivy 的 Button，但把按钮自带的背景设为透明，
    再在 KV 里用 canvas.before 画一个圆角矩形作为背景
    ——这样在手机上看就是现代感的圆角按钮，而不是系统默认的方块。
    具体的样式（颜色、圆角、按下状态）全部写在 KV 的 <MainButton> 规则里。
    """
    pass


class PlainButton(Button):
    """次按钮（浅灰描边），用于「返回」「重新识别」这类次要操作。"""
    pass


class ImageSlot(BoxLayout):
    """
    一张图片的卡片。三张卡片长得一样，只是编号不同。

    对外提供两个动作：do_take_photo / do_pick_gallery，
    内部转交给当前平台的桥接对象（安卓 → AndroidBridge，电脑 → DesktopBridge）。
    """

    index = NumericProperty(0)
    title_text = StringProperty('图片')
    hint_text = StringProperty('尚未添加图片')
    status_text = StringProperty('未添加')
    image_path = StringProperty('')      # 原图路径（用来生成 PDF）
    thumb_path = StringProperty('')      # 缩略图路径（只用来显示）
    has_image = BooleanProperty(False)

    def do_take_photo(self):
        try:
            app = App.get_running_app()
            app.bridge.take_photo(self.index)
        except Exception:
            traceback.print_exc()

    def do_pick_gallery(self):
        try:
            app = App.get_running_app()
            app.bridge.pick_gallery(self.index)
        except Exception:
            traceback.print_exc()


class WelcomeScreen(Screen):
    """首页：介绍 + 开始按钮。"""
    pass


class CaptureScreen(Screen):
    """拍照页：三张图片卡片 + 进度提示 + 下一步。"""

    progress_text = StringProperty('已准备 0 / 3 张图片')
    all_ready = BooleanProperty(False)

    def on_kv_post(self, base_widget):
        """KV 加载完成后，创建三个图片卡片。"""
        try:
            box = self.ids.slot_box
            box.clear_widgets()
            self.slots = []
            for index in range(IMAGE_COUNT):
                slot = ImageSlot(index=index)
                if index == 0:
                    slot.title_text = '第 1 张（建议拍条码）'
                    slot.hint_text = '点下方按钮拍摄条码图片'
                else:
                    slot.title_text = '第 %d 张' % (index + 1)
                    slot.hint_text = '点下方按钮添加图片'
                box.add_widget(slot)
                self.slots.append(slot)
            self.refresh_slots()
        except Exception:
            traceback.print_exc()

    def refresh_slots(self):
        """按当前已准备的图片，刷新卡片显示与进度文字。"""
        try:
            app = App.get_running_app()
            ready = 0
            for index, slot in enumerate(self.slots):
                path = app.images[index] if index < len(app.images) else ''
                if path:
                    slot.image_path = path
                    slot.thumb_path = make_thumbnail(
                        path, os.path.join(app_private_dir(), 'thumbs'))
                    slot.status_text = '已添加'
                    slot.has_image = True
                    ready += 1
                else:
                    slot.image_path = ''
                    slot.thumb_path = ''
                    slot.status_text = '未添加'
                    slot.has_image = False
            self.progress_text = '已准备 %d / %d 张图片' % (ready, IMAGE_COUNT)
            self.all_ready = (ready == IMAGE_COUNT)
        except Exception:
            traceback.print_exc()

    def on_pre_enter(self, *args):
        Clock.schedule_once(lambda _dt: self.refresh_slots(), 0)


class PreviewScreen(Screen):
    """预览页：看图、看/改条码名称、选保存目录、生成 PDF。"""

    barcode_status = StringProperty('等待识别…')
    doc_name = StringProperty('')
    save_dir = StringProperty('')
    dir_hint = StringProperty('')
    preset_labels = ListProperty([])
    show_permission_button = BooleanProperty(False)

    def __init__(self, **kwargs):
        super(PreviewScreen, self).__init__(**kwargs)
        self._preset_map = {}       # 中文标签 → 真实路径
        self._recognized_name = ''  # 自动识别出来的名字（用来判断是否被用户改过）

    # ---------- 进入页面 ----------
    def on_pre_enter(self, *args):
        self.prepare_presets()
        self.refresh_thumbs()
        self.barcode_status = '正在识别条码，请稍候…'
        # 先让界面画出来，再执行识别，避免界面卡住没有反馈
        Clock.schedule_once(lambda _dt: self.start_recognition(), 0.15)

    def prepare_presets(self):
        """准备「常用目录」下拉框，并给出默认保存目录。"""
        try:
            app = App.get_running_app()
            root = public_storage_root()
            presets = [
                ('公共文档 Documents', os.path.join(root, 'Documents')),
                ('公共下载 Download', os.path.join(root, 'Download')),
                ('本应用目录 BarcodePDF', os.path.join(root, 'BarcodePDF')),
                ('应用私有目录（一定可写）', app_private_dir()),
            ]
            self._preset_map = {}
            labels = []
            for label, path in presets:
                self._preset_map[label] = path
                labels.append(label)
            self.preset_labels = labels

            if not self.save_dir:
                self.save_dir = default_save_dir()
            self.dir_hint = self._build_dir_hint()
            self.show_permission_button = (IS_ANDROID and
                                           not app.bridge.is_all_files_access_granted())
        except Exception:
            traceback.print_exc()

    def _build_dir_hint(self):
        """根据当前能否写入，给出不同的提示文字。"""
        try:
            if is_dir_writable(self.save_dir):
                return '该目录可写，文件将保存到这里。'
            return ('该目录当前不可写。安卓 11 及以上若要保存到自选路径，'
                    '请点下方按钮申请「所有文件访问」权限；'
                    '否则程序会自动保存到可写目录。')
        except Exception:
            return ''

    def on_preset_chosen(self, label):
        """用户在下拉框里点了某个常用目录。"""
        try:
            if label in self._preset_map:
                self.save_dir = self._preset_map[label]
                self.dir_hint = self._build_dir_hint()
        except Exception:
            traceback.print_exc()

    def refresh_thumbs(self):
        """刷新页面顶部的三张小缩略图。"""
        try:
            app = App.get_running_app()
            box = self.ids.thumb_box
            box.clear_widgets()
            for path in app.images:
                thumb = BoxLayout(size_hint_x=1)
                if path:
                    image = Image(source=make_thumbnail(
                        path, os.path.join(app_private_dir(), 'thumbs')))
                else:
                    image = Image()
                thumb.add_widget(image)
                box.add_widget(thumb)
        except Exception:
            traceback.print_exc()

    def focus_name_input(self):
        """把光标移到「文档名称」输入框，方便手动填写。"""
        try:
            self.ids.name_input.focus = True
        except Exception:
            traceback.print_exc()

    # ---------- 条码识别 ----------
    def start_recognition(self):
        """
        开始识别条码。

        为了不卡住界面，这里同样先显示「正在识别」，再放到下一帧执行；
        识别时使用的是缩略图（体积小、速度快），识别成功率仍然足够。
        """
        try:
            app = App.get_running_app()
            self.barcode_status = '正在识别条码，请稍候…'

            def do_work(_dt):
                try:
                    scan_paths = []
                    for path in app.images:
                        if not path:
                            continue
                        # 识别用 1600 像素的图（比界面显示用的更清晰，条码更容易认出来）
                        scan_paths.append(make_thumbnail(
                            path, os.path.join(app_private_dir(), 'thumbs'),
                            max_edge=1600))
                    text, code_type, hit = decode_barcode_from_many(scan_paths)

                    if text:
                        app.barcode_text = text
                        app.barcode_type = code_type
                        self._recognized_name = sanitize_filename(text)
                        self.doc_name = self._recognized_name
                        self.barcode_status = ('已识别（第 %d 张，类型 %s）：\n%s'
                                               % (hit + 1, code_type or '未知', text))
                    else:
                        app.barcode_text = ''
                        app.barcode_type = ''
                        fallback = '条码文档_%s' % time.strftime('%Y%m%d_%H%M%S')
                        if not self.doc_name:
                            self.doc_name = fallback
                        self.barcode_status = ('未识别到条码。\n'
                                              '请确认条码图足够清晰、完整，'
                                              '或点「手动填写」直接输入文档名称。')
                except Exception:
                    traceback.print_exc()
                    self.barcode_status = '识别过程出错，可手动填写文档名称。'

            Clock.schedule_once(do_work, 0.05)
        except Exception:
            traceback.print_exc()

    # ---------- 权限 ----------
    def request_all_files_access(self):
        try:
            App.get_running_app().bridge.request_all_files_access()
        except Exception:
            traceback.print_exc()

    # ---------- 生成 PDF ----------
    def do_generate_pdf(self):
        """点击「生成 PDF 文档」后的完整流程。"""
        try:
            app = App.get_running_app()

            # 1) 检查图片是否齐全
            missing = [i + 1 for i, p in enumerate(app.images) if not p]
            if missing:
                show_message('还缺少图片',
                             '第 %s 张图片还没有添加，请返回上一步补齐。'
                             % '、'.join(str(i) for i in missing))
                return

            # 2) 确定文档名称（用户可能改过，以输入框为准）
            name = sanitize_filename(self.doc_name)
            if not name:
                name = '条码文档_%s' % time.strftime('%Y%m%d_%H%M%S')

            # 3) 生成并保存（内部会自动做目录回退，尽量保存成功）
            pdf_path, error = save_pdf_with_fallback(
                list(app.images), self.save_dir, name)

            if not pdf_path:
                show_message('保存失败',
                             '文件无法写入任何目录。\n\n%s' % (error or ''))
                return

            # 4) 跳到结果页展示
            app.show_result(pdf_path, name)
        except Exception:
            traceback.print_exc()
            show_message('生成失败', '生成 PDF 时出现异常，请重试。')


class ResultScreen(Screen):
    """结果页：显示文件位置和大小。"""

    pdf_path = StringProperty('')
    result_title = StringProperty('')
    result_detail = StringProperty('')

    def load(self, pdf_path, name):
        """由外部调用，把结果填进界面。"""
        try:
            self.pdf_path = pdf_path
            self.result_title = '文档名称：%s' % name
            size = os.path.getsize(pdf_path) if os.path.exists(pdf_path) else 0
            self.result_detail = ('文件大小：%s\n'
                                  '已包含 3 张图片（每页一张）。\n'
                                  '可以用手机自带的文件管理器打开这个位置查看。'
                                  % human_size(size))
        except Exception:
            traceback.print_exc()


# ==============================================================================
# 第 9 节  应用主类
# ==============================================================================

class BarcodePDFApp(App):
    """
    应用主类。

    负责：
      · 注册中文字体
      · 创建四个页面并交给页面管理器
      · 保存三张图片的路径（供各页面共享）
      · 选择平台桥接对象（安卓 or 电脑）
    """

    ui_font = StringProperty('Roboto')   # 界面字体名，注册成功后会被替换成中文字体
    title = APP_TITLE

    def __init__(self, **kwargs):
        super(BarcodePDFApp, self).__init__(**kwargs)
        # 三张图片的路径，None 表示还没添加
        self.images = [None] * IMAGE_COUNT
        self.barcode_text = ''
        self.barcode_type = ''
        self.bridge = None

    # ---------- 构建界面 ----------
    def build(self):
        register_fonts(self)
        Builder.load_string(KV)

        # 安卓上：软键盘弹出时把界面往上推，避免输入框被键盘挡住
        if IS_ANDROID:
            try:
                from kivy.core.window import Window
                Window.softinput_mode = 'below_target'
            except Exception:
                traceback.print_exc()

        self.sm = ScreenManager(transition=SlideTransition())
        self.sm.add_widget(WelcomeScreen())
        self.sm.add_widget(CaptureScreen())
        self.sm.add_widget(PreviewScreen())
        self.sm.add_widget(ResultScreen())

        # 选择平台桥接：安卓用真机接口，电脑用文件选择框
        self.bridge = AndroidBridge(self) if IS_ANDROID else DesktopBridge(self)
        self.bridge.bind_activity_result()
        self.bridge.request_base_permissions()

        return self.sm

    # ---------- 应用前后台切换 ----------
    # 这一对方法非常关键：
    #   拍照 / 从相册选图时，系统相机会盖在应用上面，我们的应用会切到后台，
    #   此时安卓会调用 on_pause()。
    #   如果这里返回 False（Kivy 的默认行为），系统会把应用彻底停掉，
    #   回来时应用重新启动，用户之前拍好的图片就全没了。
    #   返回 True 则表示「只是暂停，别销毁」，这样回到应用时进度都还在。
    def on_pause(self):
        return True

    def on_resume(self):
        # 回到前台时不需要做额外处理，进度保存在内存里，界面会保持原样
        pass

    # ---------- 页面跳转 ----------
    def go_home(self):
        try:
            self.images = [None] * IMAGE_COUNT
            self.sm.transition.direction = 'right'
            self.sm.current = 'welcome'
        except Exception:
            traceback.print_exc()

    def start_new_document(self):
        """开始制作一份新文档：清空上次的图片，进入拍照页。"""
        try:
            self.images = [None] * IMAGE_COUNT
            self.barcode_text = ''
            self.barcode_type = ''
            # 再确认一次权限（用户第一次进入时补上，确保相机/存储可用）
            if self.bridge:
                self.bridge.request_base_permissions()
            self.sm.transition.direction = 'left'
            self.sm.current = 'capture'
        except Exception:
            traceback.print_exc()

    def go_capture(self):
        try:
            self.sm.transition.direction = 'right'
            self.sm.current = 'capture'
        except Exception:
            traceback.print_exc()

    def go_preview(self):
        """进入预览页（生成 PDF 前的确认界面）。"""
        try:
            self.sm.transition.direction = 'left'
            self.sm.current = 'preview'
        except Exception:
            traceback.print_exc()

    def show_result(self, pdf_path, name):
        """展示生成结果。"""
        try:
            screen = self.sm.get_screen('result')
            screen.load(pdf_path, name)
            self.sm.transition.direction = 'left'
            self.sm.current = 'result'
        except Exception:
            traceback.print_exc()

    def show_help(self):
        show_message('使用说明',
                     '1. 点「开始拍照」，依次准备 3 张图片；\n'
                     '   每张都可以选「拍照」或「从相册选择」。\n\n'
                     '2. 建议其中一张拍条码（条形码、二维码都行），\n'
                     '   程序会自动读取条码内容。\n\n'
                     '3. 在预览页确认「文档名称」（可手动修改），\n'
                     '   再选好保存位置，点「生成 PDF 文档」。\n\n'
                     '4. 成功后可以在结果页看到文件的完整保存路径。')

    # ---------- 收到新图片 ----------
    def on_image_ready(self, index, path):
        """
        平台桥接层拿到图片后回调到这里：记录路径并刷新界面。

        注意：这里做了越界保护与存在性校验，避免任何意外把应用搞崩。
        """
        try:
            if not path or not os.path.exists(path):
                show_message('图片无效', '没有读到有效的图片，请重试。')
                return
            if index is None or index < 0 or index >= IMAGE_COUNT:
                return
            self.images[index] = path
            screen = self.sm.get_screen('capture')
            screen.refresh_slots()
        except Exception:
            traceback.print_exc()


# ==============================================================================
# 第 10 节  程序入口
# ==============================================================================

# 中文字体候选清单：
#   前几个是「随应用打包的字体」（把字体文件放进项目的 fonts 目录即可，
#   可以在 buildozer.spec 的 source.include_exts 里带上 otf/ttf）；
#   后面几个是安卓系统自带的中文字体，绝大多数手机上都能找到。
FONT_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 'fonts', 'NotoSansSC-Regular.otf'),
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 'fonts', 'NotoSansCJKsc-Regular.otf'),
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 'fonts', 'SourceHanSansCN-Regular.otf'),
    '/system/fonts/NotoSansCJK-Regular.ttc',
    '/system/fonts/NotoSansCJKsc-Regular.otf',
    '/system/fonts/NotoSansSC-Regular.otf',
    '/system/fonts/DroidSansFallbackFull.ttf',
    '/system/fonts/DroidSansFallback.ttf',
]


def register_fonts(app):
    """
    注册中文字体。

    Kivy 自带的默认字体（Roboto）不包含汉字，若不处理，界面上所有中文
    都会显示成方框。这里从候选清单里找一个可用的字体文件注册进去，
    并把 app.ui_font 指向它，界面所有文本控件都会自动使用。
    """
    try:
        for path in FONT_CANDIDATES:
            try:
                if path and os.path.exists(path):
                    LabelBase.register(name=CHINESE_FONT, fn_regular=path)
                    app.ui_font = CHINESE_FONT
                    return True
            except Exception:
                continue
    except Exception:
        traceback.print_exc()
    return False


def main():
    """程序入口：注册好异常兜底后启动应用。"""
    try:
        BarcodePDFApp().run()
    except Exception:
        # 最外层兜底：即使真的出问题，也把错误打印出来，方便定位
        traceback.print_exc()


if __name__ == '__main__':
    main()
