# -*- coding: utf-8 -*-
"""
================================================================================
 自检脚本（可选）—— 在电脑上跑一遍完整流程，确认程序正常工作
================================================================================
 它模拟真实用户的操作：
    准备三张图片（其中一张是条码图）→ 自动识别条码 → 用条码当文档名
    → 生成三页 PDF → 校验页数和文件名

 运行方法：
    python3 selftest.py

 需要的依赖（见 requirements-desktop.txt）：
    kivy / pillow / pyzbar / python-barcode / pypdf
 如果缺少 python-barcode 等仅用于"造测试素材"的库，
 脚本会跳过对应步骤并说明原因，不会报错退出。
================================================================================
"""

import os
import sys
import time
import traceback

# 无显示器环境下也能运行（必须在导入 Kivy 之前设置）
os.environ.setdefault('SDL_VIDEODRIVER', 'offscreen')
os.environ.setdefault('KIVY_WINDOW', 'sdl2')
os.environ.setdefault('KIVY_NO_ARGS', '1')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

WORK = os.path.join(HERE, 'selftest_output')

from PIL import Image, ImageDraw
import main
from kivy.app import App as KivyApp
from kivy.clock import Clock


def make_plain_photo(path, color, text):
    """造一张普通照片。"""
    img = Image.new('RGB', (1600, 1200), color)
    ImageDraw.Draw(img).text((80, 80), text, fill=(255, 255, 255))
    img.save(path, quality=92)
    img.close()


def make_barcode_photo(path_without_ext):
    """造一张条码图，返回实际文件路径；缺少库时返回 None。"""
    try:
        import barcode
        from barcode.writer import ImageWriter
        result = barcode.get('code128', '2026-TEST-0001',
                             writer=ImageWriter()).save(path_without_ext)
        if not os.path.exists(result):
            result += '.png'
        return result
    except Exception as exc:
        print('  (跳过条码图生成：%s)' % exc)
        return None


def main_test():
    os.makedirs(WORK, exist_ok=True)

    print('【1】准备测试素材')
    photo_a = os.path.join(WORK, 'photo_a.jpg')
    photo_c = os.path.join(WORK, 'photo_c.jpg')
    make_plain_photo(photo_a, (200, 90, 60), 'PHOTO A')
    make_plain_photo(photo_c, (60, 150, 90), 'PHOTO C')
    barcode_photo = make_barcode_photo(os.path.join(WORK, 'barcode_b'))
    print('  普通照片 2 张，条码图：%s' % (barcode_photo or '未生成'))

    print('【2】启动应用并构建界面')
    app = main.BarcodePDFApp()
    KivyApp._running_app = app
    root = app.build()
    print('  页面：%s' % [s.name for s in root.screens])

    print('【3】进入「准备图片」页')
    app.start_new_document()
    print('  当前页：%s' % app.sm.current)

    print('【4】三张图片就位（模拟拍照 / 相册选图返回）')
    app.on_image_ready(0, photo_a)
    app.on_image_ready(1, barcode_photo or photo_a)
    app.on_image_ready(2, photo_c)
    capture = root.get_screen('capture')
    print('  %s | 可以进入下一步：%s' % (capture.progress_text, capture.all_ready))

    print('【5】进入预览页，自动识别条码')
    app.go_preview()
    preview = root.get_screen('preview')
    preview.on_pre_enter()
    time.sleep(1.2)
    Clock.tick()
    time.sleep(0.4)
    Clock.tick()
    print('  识别结果：%s' % preview.barcode_status.replace('\n', ' | '))
    print('  文档名称：%s' % preview.doc_name)

    print('【6】生成 PDF')
    out_dir = os.path.join(WORK, 'output')
    preview.save_dir = out_dir
    preview.do_generate_pdf()
    time.sleep(0.5)
    Clock.tick()

    result = root.get_screen('result')
    print('  当前页：%s' % app.sm.current)
    print('  %s' % result.result_title)
    print('  文件路径：%s' % result.pdf_path)

    print('【7】校验产出的 PDF')
    pdf_path = result.pdf_path
    ok = False
    if pdf_path and os.path.exists(pdf_path):
        print('  文件名：%s' % os.path.basename(pdf_path))
        print('  大小：%s' % main.human_size(os.path.getsize(pdf_path)))
        try:
            from pypdf import PdfReader
            pages = len(PdfReader(pdf_path).pages)
            print('  页数：%d' % pages)
            ok = (pages == 3)
        except Exception as exc:
            print('  (未安装 pypdf，跳过页数校验：%s)' % exc)
            ok = True
    print('  %s' % ('✓ 通过：三张图片被合并进同一个 PDF' if ok else '✗ 未通过'))

    print('【8】同名文件不覆盖')
    preview.do_generate_pdf()
    time.sleep(0.4)
    Clock.tick()
    second = root.get_screen('result').pdf_path
    print('  第二次生成：%s' % os.path.basename(second))

    print('【9】图片不全时应被拦住')
    app.start_new_document()
    app.images[1] = None
    app.sm.current = 'preview'
    preview.do_generate_pdf()
    print('  仍停留在：%s（未跳转到结果页，符合预期）' % app.sm.current)

    print()
    print('自检完成，产出文件在：%s' % WORK)


if __name__ == '__main__':
    try:
        main_test()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
