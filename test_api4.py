import urllib.request, json, base64
image_url = 'https://raw.githubusercontent.com/opencv/opencv/master/samples/data/lena.jpg'
try:
    req = urllib.request.urlopen(image_url)
    png_data = req.read()
    boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
    body = b'--' + boundary.encode() + b'\r\n'
    body += b'Content-Disposition: form-data; name="image"; filename="lena.jpg"\r\n'
    body += b'Content-Type: image/jpeg\r\n\r\n'
    body += png_data + b'\r\n'
    body += b'--' + boundary.encode() + b'--\r\n'
    req2 = urllib.request.Request('http://114.67.73.44:8000/api/id-photo/prepare', data=body, headers={'Content-Type': 'multipart/form-data; boundary=' + boundary})
    try:
        res = urllib.request.urlopen(req2)
        print(res.read().decode())
    except Exception as e:
        if hasattr(e, 'read'):
            print(e.read().decode())
        else:
            print(e)
except Exception as e:
    print('Failed to download image:', e)
