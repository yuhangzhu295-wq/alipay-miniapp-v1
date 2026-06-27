import urllib.request, json, base64
from PIL import Image
from io import BytesIO
img = Image.new('RGB', (100, 100), color = 'red')
buf = BytesIO()
img.save(buf, format='JPEG')
png_data = buf.getvalue()
boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
body = b'--' + boundary.encode() + b'\r\n'
body += b'Content-Disposition: form-data; name="image"; filename="test.jpg"\r\n'
body += b'Content-Type: image/jpeg\r\n\r\n'
body += png_data + b'\r\n'
body += b'--' + boundary.encode() + b'--\r\n'
req = urllib.request.Request('http://114.67.73.44:8000/api/id-photo/prepare', data=body, headers={'Content-Type': 'multipart/form-data; boundary=' + boundary})
try:
    res = urllib.request.urlopen(req)
    print(res.read().decode())
except Exception as e:
    if hasattr(e, 'read'):
        print(e.read().decode())
    else:
        print(e)
