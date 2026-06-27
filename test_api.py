import urllib.request, json, base64
img = b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
png_data = base64.b64decode(img)
boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
body = b'--' + boundary.encode() + b'\r\n'
body += b'Content-Disposition: form-data; name="image"; filename="test.png"\r\n'
body += b'Content-Type: image/png\r\n\r\n'
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
