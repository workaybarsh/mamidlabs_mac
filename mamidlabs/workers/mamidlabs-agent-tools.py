import json
import ipaddress
import re
import socket
import sys
import threading
import urllib.request
from urllib.parse import urlparse


MAX_PAGE_BYTES = 3_000_000
MAX_REFERENCE_BYTES = 20 * 1024 * 1024
MAX_REFERENCE_PIXELS = 40_000_000

# Yavas DNS'te socket.getaddrinfo bloke edebilir; cozumleme ayri bir is
# parcaciginda yapilir ve join(timeout) ile sinirlanir. Bu sure asilirsa
# _pin_resolution OSError yukseltir; cagirici bunu mevcut temiz hata JSON'u
# akisina cevirir (istisna disari sizmaz).
DNS_TIMEOUT_SECONDS = 5
# ddgs birden fazla arama motoru backend'ini kendi icinde denedigi icin
# search_web'in toplam suresi backend x timeout kadar (olculdu: ~60 sn)
# olabiliyordu. Tek bir toplam ust sinir (deadline) uygulanir; asilirsa kalan
# backend'ler beklenmez, elde sonuc varsa o doner, yoksa temiz hata JSON'u.
SEARCH_DEADLINE_SECONDS = 25

# DNS rebinding korumasi: _validate_remote_url hostu bir kez cozup dogruluyordu,
# ama gercek baglanti (urllib/http.client) ayri bir DNS sorgusuyla tekrar
# cozuyordu. Dusuk TTL'li kotu niyetli bir DNS kaydi, dogrulama aninda herkese
# acik bir IP, hemen ardindan gelen baglanti aninda ozel/yerel bir IP donerek
# bu iki cozumleme arasindaki farktan (TOCTOU) yararlanabilirdi. Cozum: her
# hostu dogrulanirken tam olarak hangi adreslere cozuldugunu kaydet, ve
# socket.getaddrinfo'yu bu script suresince o host icin sabitle; boylece
# gercek baglanti da ayni, onceden dogrulanmis adresi kullanmak zorunda kalir.
# Bu script tek bir istegi isleyip cikan tek-atimlik bir surec oldugu icin
# (main() dogrudan tek JSON istegi okur), process-genelinde monkeypatch
# guvenlidir; ayri bir istek/thread'le yarismaz.
_pinned_addresses: dict = {}
_real_getaddrinfo = socket.getaddrinfo


def _pin_resolution(host, port):
    # Cozumlemeyi ayri bir is parcaciginda yapip join(timeout) ile sinirlariz;
    # boylece yavas/askida kalan bir DNS sorgusu bloke etmez. Secilen adresler
    # (pinning) degismez; yalnizca bir sure siniri eklenir.
    outcome = {}

    def _resolve():
        try:
            outcome['results'] = _real_getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except Exception as exc:  # cagirana aynen iletilir
            outcome['error'] = exc

    worker = threading.Thread(target=_resolve, daemon=True)
    worker.start()
    worker.join(DNS_TIMEOUT_SECONDS)
    if worker.is_alive():
        raise OSError('DNS cozumlemesi zaman asimina ugradi.')
    if 'error' in outcome:
        raise outcome['error']
    results = outcome['results']
    _pinned_addresses[host] = results
    return [ipaddress.ip_address(item[4][0]) for item in results]


def _patched_getaddrinfo(host, *args, **kwargs):
    pinned = _pinned_addresses.get(host)
    return pinned if pinned is not None else _real_getaddrinfo(host, *args, **kwargs)


socket.getaddrinfo = _patched_getaddrinfo


def _validate_remote_url(value):
    """Reject local/reserved destinations before urllib can connect to them."""
    parsed = urlparse(str(value))
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise ValueError('Yalnizca gecerli http/https adresleri okunabilir.')
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError('URL kimlik bilgisi veya fragment iceremez.')
    if parsed.port not in (None, 80, 443):
        raise ValueError('Yalnizca 80 ve 443 portlari kullanilabilir.')

    host = parsed.hostname.rstrip('.').lower()
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = _pin_resolution(host, port)
        except (OSError, ValueError):
            raise ValueError('URL hostu cozumlenemedi.')
    if not addresses or any(not address.is_global for address in addresses):
        _pinned_addresses.pop(host, None)
        raise ValueError('Yerel, ozel veya ayrilmis ag adreslerine erisim engellendi.')
    return parsed.geturl()


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Yonlendirilen hostu da ayni sekilde pinler; boylece yonlendirme
        # zincirindeki her adim kendi dogrulanmis adresine baglanir.
        _validate_remote_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_remote_url(url, headers, timeout):
    safe_url = _validate_remote_url(url)
    opener = urllib.request.build_opener(_SafeRedirectHandler())
    return opener.open(urllib.request.Request(safe_url, headers=headers), timeout=timeout)


def _read_limited(response, limit):
    chunks = []
    total = 0
    while True:
        chunk = response.read(min(1024 * 1024, limit - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise ValueError('Uzak yanit boyut sinirini asti.')
        chunks.append(chunk)
    return b''.join(chunks)


def search_web(request):
    from ddgs import DDGS
    query = str(request.get('query', ''))[:500]
    count = max(1, min(int(request.get('count', 5)), 8))
    collected = []
    failure = {}

    def _search():
        try:
            # Ulasilamayan bir arama motoru isi dakikalarca bekletmesin.
            # Degerlendirme backend'leri sirayla/paralel denedigi icin toplam
            # sureyi dis taraftaki deadline sinirlar.
            for item in DDGS(timeout=15).text(query, max_results=count):
                collected.append(item)
        except Exception as exc:
            failure['error'] = exc

    worker = threading.Thread(target=_search, daemon=True)
    worker.start()
    worker.join(SEARCH_DEADLINE_SECONDS)
    if worker.is_alive():
        # Toplam sure siniri asildi: kalan backend'leri beklemeyi birak. Elde
        # edilmis sonuc varsa onlari, yoksa gecerli bir hata JSON'u dondur.
        if collected:
            return json.dumps(collected, ensure_ascii=False)
        return json.dumps({'error': 'Web aramasi zaman asimina ugradi: sonuc yok.'}, ensure_ascii=False)
    if 'error' in failure:
        return json.dumps({'error': f'Web aramasi basarisiz: {failure["error"]}'}, ensure_ascii=False)
    return json.dumps(collected, ensure_ascii=False)


def fetch_page(request):
    url = str(request.get('url', ''))
    try:
        safe_url = _validate_remote_url(url)
        with _open_remote_url(safe_url, {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) MamidLabs/1.0'}, 25) as response:
            charset = response.headers.get_content_charset() or 'utf-8'
            raw = _read_limited(response, MAX_PAGE_BYTES).decode(charset, errors='replace')
    except Exception as exc:
        return json.dumps({'error': str(exc)}, ensure_ascii=False)
    raw = re.sub(r'(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>', ' ', raw)
    raw = re.sub(r'(?s)<!--.*?-->', ' ', raw)
    text = re.sub(r'(?s)<[^>]+>', ' ', raw)
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&quot;', '"').replace('&#39;', "'")
    text = re.sub(r'[ \t\r\f\v]+', ' ', text)
    text = re.sub(r'\n\s*\n\s*', '\n', text).strip()
    if len(text) > 20000:
        text = text[:20000] + '\n[sayfa 20K karakterde kesildi]'
    return json.dumps({'url': url, 'text': text}, ensure_ascii=False)


def find_reference_image(request):
    """Web'de gorsel arar, ilk uygun olani indirir ve yerel yolunu dondurur."""
    import os
    import urllib.request
    from ddgs import DDGS

    query = str(request.get('query', ''))[:300]
    # The model only needs the application-owned reference directory. Never let
    # a tool argument turn this downloader into an arbitrary file writer.
    # Kurulum kokunu ortam degiskeninden oku (bkz. _root.py); paket site-packages'te
    # olabilecegi icin kendi konumundan turetmek yanlis olur.
    from _root import install_root

    root = str(install_root())
    out_dir = os.path.join(root, 'outputs', 'refs')
    os.makedirs(out_dir, exist_ok=True)

    try:
        # Gorsel aramasi da search_web ile ayni sekilde acik timeout almali;
        # aksi halde ddgs varsayilanina bagli kalip isi uzun sure bekletir.
        results = list(DDGS(timeout=15).images(query, max_results=8))
    except Exception as exc:
        return json.dumps({'error': 'gorsel aramasi basarisiz: %s' % exc}, ensure_ascii=False)

    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) MamidLabs/1.0'}
    for item in results:
        url = item.get('image') or item.get('thumbnail')
        if not url:
            continue
        try:
            _validate_remote_url(url)
            with _open_remote_url(url, headers, 20) as response:
                ctype = (response.headers.get('Content-Type') or '').lower()
                if 'image' not in ctype:
                    continue
                data = _read_limited(response, MAX_REFERENCE_BYTES)
        except Exception:
            continue

        ext = '.png' if 'png' in ctype else ('.webp' if 'webp' in ctype else '.jpg')
        safe = re.sub(r'[^a-zA-Z0-9]+', '-', query)[:40].strip('-') or 'ref'
        path = os.path.join(out_dir, 'ref-%s-%d%s' % (safe, abs(hash(url)) % 100000, ext))
        try:
            with open(path, 'wb') as handle:
                handle.write(data)
            from PIL import Image
            Image.MAX_IMAGE_PIXELS = MAX_REFERENCE_PIXELS
            with Image.open(path) as img:
                img.verify()
            with Image.open(path) as img:
                if img.width * img.height > MAX_REFERENCE_PIXELS:
                    raise ValueError('Gorsel piksel sinirini asti.')
                width, height = img.size
                if width < 256 or height < 256:
                    os.remove(path)
                    continue
                if ext != '.png':
                    png_path = os.path.splitext(path)[0] + '.png'
                    Image.open(path).convert('RGB').save(png_path)
                    os.remove(path)
                    path = png_path
        except Exception:
            try:
                os.remove(path)
            except Exception:
                pass
            continue

        return json.dumps({
            'path': path, 'width': width, 'height': height,
            'source': item.get('url') or url, 'title': item.get('title', ''),
        }, ensure_ascii=False)

    return json.dumps({'error': 'uygun gorsel bulunamadi'}, ensure_ascii=False)


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stdin.reconfigure(encoding='utf-8')
    except Exception:
        pass
    request = json.loads(sys.stdin.read() or '{}')
    action = request.get('action')
    if action == 'search_web':
        print(search_web(request))
        return
    if action == 'fetch_page':
        print(fetch_page(request))
        return
    if action == 'find_reference_image':
        print(find_reference_image(request))
        return
    print(json.dumps({'error': 'unknown action'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
