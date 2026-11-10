"""실행될 수 있는 파일을 실행하지 않고 미리보기. 파일은 데이터로만 읽는다."""

import ctypes as c
import json
import os
import struct
import subprocess
import time

# 열면 실행되는 형식
BINARY = set('.exe .com .msi .msp .scr .pif .cpl .jar'.split())  # 버전 정보·디지털 서명을 보여 줌
SHORTCUT = {'.lnk'}  # 실제로 실행할 대상과 인수를 보여 줌
SCRIPT = set(
    '.bat .cmd .ps1 .psm1 .vbs .vbe .js .jse .wsf .wsh .reg .url .hta .msc .appref-ms .application .settingcontent-ms'.split()
)  # 텍스트 내용 앞부분을 보여 줌
EXECUTABLE = BINARY | SHORTCUT | SCRIPT
SIGNED = {'.exe', '.com', '.msi', '.msp', '.scr', '.cpl', '.ps1', '.psm1', '.vbs', '.js'}
DOCUMENT = set('.pdf .doc .docx .hwp .hwpx .xls .xlsx .ppt .pptx .txt .jpg .jpeg .png .gif .mp4 .mp3 .zip'.split())
VERSION_FIELDS = (
    ('ProductName', '제품명'),
    ('CompanyName', '제작사'),
    ('FileDescription', '설명'),
    ('FileVersion', '버전'),
)
SIGNATURE_STATUS = {
    'Valid': '유효한 서명',
    'NotSigned': '서명 없음 · 출처를 확인할 수 없어요',
    'HashMismatch': '서명 이후 파일이 변조됐어요 · 실행하지 마세요',
    'NotTrusted': '신뢰할 수 없는 서명',
    'UnknownError': '서명을 확인하지 못했어요',
}
TEXT_LINES = 15


def describe(p):
    """미리보기 창에 넣을 여러 줄 설명."""
    suffix = p.suffix.lower()
    st = p.stat()
    lines = [f'크기 {st.st_size:,} 바이트 · 수정 {time.strftime("%Y.%m.%d %H:%M", time.localtime(st.st_mtime))}']
    hidden = os.path.splitext(p.stem)[1].lower()
    if hidden in DOCUMENT:
        lines.append(f'⚠ 이름이 {hidden} 파일처럼 보이지만 실제로는 {suffix} 형식이에요. 실행하지 마세요.')
    if suffix in BINARY:
        if suffix in {'.exe', '.com', '.scr', '.cpl', '.pif'} and head(p, 2) != b'MZ':
            lines.append('⚠ Windows 실행 파일 형식(PE)이 아니에요.')
        info = version_info(p)
        lines += [f'{label}: {info[key]}' for key, label in VERSION_FIELDS if info.get(key)] or ['버전 정보 없음']
    if suffix in SIGNED:
        lines.append('디지털 서명: ' + signature(p))
    if suffix in SHORTCUT:
        target = shortcut(p)
        lines += [f'실행 대상: {target.get("TargetPath") or "확인 불가"}', f'인수: {target.get("Arguments") or "없음"}']
    if suffix in SCRIPT:
        lines += ['', '── 내용 앞부분 ──', text_head(p)]
    return '\n'.join(lines)


def version_info(p):
    """PE 버전 리소스. GetFileVersionInfo는 파일을 데이터로만 매핑하므로 코드가 실행되지 않는다."""
    if os.name != 'nt':
        return {}
    v = c.WinDLL('version')
    v.GetFileVersionInfoSizeW.argtypes = [c.c_wchar_p, c.c_void_p]
    v.GetFileVersionInfoSizeW.restype = c.c_uint32
    v.GetFileVersionInfoW.argtypes = [c.c_wchar_p, c.c_uint32, c.c_uint32, c.c_void_p]
    v.GetFileVersionInfoW.restype = c.c_bool
    v.VerQueryValueW.argtypes = [c.c_void_p, c.c_wchar_p, c.POINTER(c.c_void_p), c.POINTER(c.c_uint32)]
    v.VerQueryValueW.restype = c.c_bool
    size = v.GetFileVersionInfoSizeW(str(p), None)
    buf = c.create_string_buffer(size or 1)
    if not size or not v.GetFileVersionInfoW(str(p), 0, size, buf):
        return {}
    ptr, n = c.c_void_p(), c.c_uint32()
    langs = ['041204b0', '040904b0', '040904e4']  # 한국어, 영어(유니코드), 영어(ANSI)
    if v.VerQueryValueW(buf, '\\VarFileInfo\\Translation', c.byref(ptr), c.byref(n)) and n.value >= 4:
        lang, codepage = struct.unpack('<HH', c.string_at(ptr, 4))
        langs.insert(0, f'{lang:04x}{codepage:04x}')
    out = {}
    for key, _ in VERSION_FIELDS:
        for lang in langs:
            if v.VerQueryValueW(buf, f'\\StringFileInfo\\{lang}\\{key}', c.byref(ptr), c.byref(n)) and n.value:
                out[key] = c.wstring_at(ptr, n.value).rstrip('\0').strip()
                break
    return out


def powershell(script, path):
    """경로는 환경 변수로 넘겨 명령 주입을 막는다. 실패하면 None."""
    try:
        r = subprocess.run(
            [
                'powershell.exe',
                '-NoProfile',
                '-NonInteractive',
                '-Command',
                '[Console]::OutputEncoding=[Text.Encoding]::UTF8;' + script + ' | ConvertTo-Json -Compress',
            ],
            env={**os.environ, 'SSEUK_PREVIEW_PATH': str(path)},
            capture_output=True,
            timeout=20,
            creationflags=0x08000000,  # CREATE_NO_WINDOW: 콘솔 창을 띄우지 않음
        )
        return json.loads(r.stdout.decode('utf-8')) if r.returncode == 0 and r.stdout.strip() else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def signature(p):
    result = powershell(
        '$s=Get-AuthenticodeSignature -LiteralPath $env:SSEUK_PREVIEW_PATH;'
        '@{status=[string]$s.Status;signer=[string]$s.SignerCertificate.Subject}',
        p,
    )
    if not result:
        return '확인 불가'
    text = SIGNATURE_STATUS.get(result.get('status'), result.get('status') or '확인 불가')
    signer = next((x.strip()[3:] for x in (result.get('signer') or '').split(',') if x.strip().startswith('CN=')), '')
    return f'{text} · {signer}' if signer and result.get('status') != 'NotSigned' else text


def shortcut(p):
    return (
        powershell(
            '$l=(New-Object -ComObject WScript.Shell).CreateShortcut($env:SSEUK_PREVIEW_PATH);'
            '@{TargetPath=$l.TargetPath;Arguments=$l.Arguments}',
            p,
        )
        or {}
    )


def head(p, n):
    with p.open('rb') as f:
        return f.read(n)


def text_head(p):
    raw = head(p, 4096)
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        text = raw.decode('utf-16', 'replace')
    else:
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = raw.decode('mbcs' if os.name == 'nt' else 'latin-1', 'replace')
    lines = [line[:160] for line in text.splitlines()[:TEXT_LINES]]
    return '\n'.join(lines) or '(빈 파일)'
