from flask import Blueprint, request, jsonify, Response, stream_with_context
import yt_dlp
import os
import tempfile
import subprocess
import json
from urllib.parse import urlparse

video_bp = Blueprint('video', __name__)

def get_video_info(url):
    """استخراج معلومات الفيديو باستخدام yt-dlp"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return info
        except Exception as e:
            raise Exception(f"فشل في استخراج معلومات الفيديو: {str(e)}")

def filter_formats(formats):
    """تصفية وترتيب صيغ الفيديو"""
    if not formats:
        return []
    
    # تصفية الصيغ المفيدة فقط
    filtered = []
    for f in formats:
        # تجاهل الصيغ غير المرغوبة
        if f.get('ext') in ['mhtml', 'html']:
            continue
        
        # إضافة معلومات إضافية
        format_info = {
            'format_id': f.get('format_id'),
            'ext': f.get('ext'),
            'resolution': f.get('resolution'),
            'height': f.get('height'),
            'width': f.get('width'),
            'fps': f.get('fps'),
            'filesize': f.get('filesize'),
            'url': f.get('url'),
            'vcodec': f.get('vcodec'),
            'acodec': f.get('acodec'),
        }
        filtered.append(format_info)
    
    # ترتيب حسب الجودة (الأعلى أولاً)
    filtered.sort(key=lambda x: (x.get('height') or 0), reverse=True)
    
    return filtered

@video_bp.route('/info', methods=['POST'])
def get_info():
    """جلب معلومات الفيديو"""
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({'error': True, 'message': 'الرجاء تقديم رابط صحيح'}), 400
        
        url = data['url'].strip()
        if not url:
            return jsonify({'error': True, 'message': 'الرابط فارغ'}), 400
        
        # التحقق من صحة الرابط
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return jsonify({'error': True, 'message': 'رابط غير صحيح'}), 400
        
        # استخراج معلومات الفيديو
        info = get_video_info(url)
        
        # تحضير البيانات للإرسال
        response_data = {
            'title': info.get('title', 'فيديو بدون عنوان'),
            'uploader': info.get('uploader'),
            'duration': info.get('duration'),
            'thumbnail': info.get('thumbnail'),
            'description': info.get('description'),
            'formats': filter_formats(info.get('formats', []))
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({'error': True, 'message': str(e)}), 500

@video_bp.route('/download', methods=['GET'])
def download_video():
    """تنزيل الفيديو"""
    try:
        url = request.args.get('url')
        format_id = request.args.get('format_id')
        
        if not url or not format_id:
            return jsonify({'error': True, 'message': 'معاملات مفقودة'}), 400
        
        # إنشاء مجلد مؤقت للتنزيل
        temp_dir = tempfile.mkdtemp()
        
        # إعدادات yt-dlp للتنزيل
        ydl_opts = {
            'format': format_id,
            'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # استخراج معلومات الفيديو أولاً
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'video')
            
            # تنزيل الفيديو
            ydl.download([url])
            
            # البحث عن الملف المحمل
            downloaded_files = os.listdir(temp_dir)
            if not downloaded_files:
                return jsonify({'error': True, 'message': 'فشل في تحميل الفيديو'}), 500
            
            file_path = os.path.join(temp_dir, downloaded_files[0])
            file_size = os.path.getsize(file_path)
            
            # تحديد نوع المحتوى
            ext = os.path.splitext(downloaded_files[0])[1].lower()
            content_type = 'video/mp4'
            if ext == '.webm':
                content_type = 'video/webm'
            elif ext == '.mkv':
                content_type = 'video/x-matroska'
            
            def generate():
                try:
                    with open(file_path, 'rb') as f:
                        while True:
                            chunk = f.read(8192)
                            if not chunk:
                                break
                            yield chunk
                finally:
                    # تنظيف الملفات المؤقتة
                    try:
                        os.remove(file_path)
                        os.rmdir(temp_dir)
                    except:
                        pass
            
            # إنشاء اسم ملف آمن للتنزيل
            safe_filename = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
            if not safe_filename:
                safe_filename = "video"
            
            response = Response(
                stream_with_context(generate()),
                content_type=content_type,
                headers={
                    'Content-Disposition': f'attachment; filename="{safe_filename}{ext}"',
                    'Content-Length': str(file_size)
                }
            )
            
            return response
            
    except Exception as e:
        return jsonify({'error': True, 'message': f'خطأ في التنزيل: {str(e)}'}), 500

