"""Recycle one item and require a positive per-item Windows Shell receipt."""

import ctypes as c
import uuid


def recycle(path):
    P, HR, U = c.c_void_p, c.c_int32, c.c_uint32
    proto = c.WINFUNCTYPE

    def guid(value):
        return (c.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le)

    def check(hr):
        if hr < 0:
            raise OSError(f"Windows 오류 0x{hr & 0xFFFFFFFF:08X}. 파일을 닫고 권한을 확인한 뒤 다시 시도하세요.")

    def method(obj, slot, *args):
        table = c.cast(obj, c.POINTER(c.POINTER(P))).contents
        return proto(HR, P, *args)(table[slot])

    if c.windll.kernel32.GetDriveTypeW(str(path.anchor)) != 3:
        raise ValueError("로컬 드라이브에서만 휴지통을 사용할 수 있어요.")
    ole = c.OleDLL("ole32")
    shell = c.WinDLL("shell32")
    sink_id = "04b0f1a7-9490-44bc-96e1-4296a31252e2"
    receipt = []

    def query(this, iid, out):
        allowed = (uuid.UUID(sink_id).bytes_le, uuid.UUID("00000000-0000-0000-c000-000000000046").bytes_le)
        target = c.cast(out, c.POINTER(P))
        target[0] = this if c.string_at(iid, 16) in allowed else None
        return 0 if target[0] else -2147467262

    def before(this, flags, item):
        return 0 if flags & 0x80 else -2147467260

    def after(this, flags, item, hr, recycled):
        receipt.append((hr, bool(recycled)))
        return 0

    callbacks = []
    for slot, n in enumerate((2, 0, 0, 0, 1, 3, 5, 4, 6, 4, 6, 2, 4, 3, 7, 2, 0, 0, 0)):
        fn = {0: query, 1: lambda *_: 2, 2: lambda *_: 1, 11: before, 12: after}.get(slot, lambda *_: 0)
        types = [P] * n
        if slot == 11:
            types = [U, P]
        if slot == 12:
            types = [U, P, HR, P]
        callbacks.append(proto(HR, P, *types)(fn))
    table = (P * len(callbacks))(*(c.cast(fn, P) for fn in callbacks))
    sink = c.pointer(c.cast(table, P))
    op, item = P(), P()
    ole.CoInitializeEx(None, 2)
    try:
        ole.CoCreateInstance(
            guid("3ad05575-8857-4850-9277-11b85bdb8e09"),
            None,
            1,
            guid("947aab5f-0a5c-4c13-b4d6-4bf7836fc9f8"),
            c.byref(op),
        )
        check(
            shell.SHCreateItemFromParsingName(
                c.c_wchar_p(str(path)), None, guid("43826d1e-e718-42ee-bc55-a1e261c37bfe"), c.byref(item)
            )
        )
        check(method(op, 5, U)(op, 0x80000 | 0x00100000 | 0x0614))
        check(method(op, 18, P, P)(op, item, sink))
        result = method(op, 21)(op)
        if receipt and receipt[-1][0] >= 0 and receipt[-1][1]:
            return
        if receipt:
            check(receipt[-1][0])
        check(result)
        raise OSError("휴지통 이동을 확인하지 못했어요. 파일 위치를 확인하고 다시 찾아 주세요.")
    finally:
        for obj in (item, op):
            if obj:
                method(obj, 2)(obj)
        ole.CoUninitialize()


def empty_recycle_bin(confirmed=False):
    if confirmed is not True:
        raise ValueError('휴지통 영구 삭제를 먼저 확인해 주세요.')
    shell = c.WinDLL('shell32')
    call = shell.SHEmptyRecycleBinW
    call.argtypes = [c.c_void_p, c.c_wchar_p, c.c_uint32]
    call.restype = c.c_int32
    SHERB_NOCONFIRMATION = 0x1  # 앱에서 이미 확인함. 진행률 창(0x2)·소리(0x4)는 유지
    hr = call(None, None, SHERB_NOCONFIRMATION)  # 모든 드라이브, 현재 사용자
    if hr != 0:
        raise OSError(
            f'휴지통 비우기가 취소되었거나 완료되지 않았어요 (0x{hr & 0xFFFFFFFF:08X}). 휴지통에서 남은 파일을 확인해 주세요.'
        )
