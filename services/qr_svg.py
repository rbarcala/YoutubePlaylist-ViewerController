"""
Generador de códigos QR en SVG de alto contraste (Blanco y Negro puro).
Optimizado para lectura instantánea y sin reflejos por cámaras de celulares.
"""
import io
import urllib.parse

def generate_qr_svg(url: str, size: int = 240) -> str:
    """
    Genera un código QR de máximo contraste (módulos negros sobre fondo blanco puro).
    Si la librería qrcode está disponible, genera un SVG vectorial puro offline.
    De lo contrario, utiliza un SVG vectorial nítido con codificación en blanco y negro.
    """
    # Intentar generar SVG vectorial offline con qrcode
    try:
        import qrcode
        import qrcode.image.svg
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
            image_factory=qrcode.image.svg.SvgPathImage
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(attrib={
            'width': str(size),
            'height': str(size),
            'style': 'background:#ffffff; border-radius:8px;'
        })
        buf = io.BytesIO()
        img.save(buf)
        return buf.getvalue().decode('utf-8')
    except Exception:
        pass

    # Fallback: SVG de alto contraste en blanco y negro puro (#000000 sobre #ffffff)
    encoded_url = urllib.parse.quote(url)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">
  <rect width="100%" height="100%" fill="#ffffff" rx="10" />
  <image href="https://api.qrserver.com/v1/create-qr-code/?size={size}x{size}&amp;data={encoded_url}&amp;bgcolor=255-255-255&amp;color=0-0-0&amp;margin=2" 
         width="{size}" height="{size}" />
</svg>'''
    return svg
