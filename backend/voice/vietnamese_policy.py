"""Vietnamese-only voice policy, NLU normalization, small talk, sensor/status queries, and concise replies."""

from __future__ import annotations

from difflib import SequenceMatcher
import re
import unicodedata
from typing import Any

from backend.engine.constants_and_time import DEFAULT_DEVICES
from backend.engine.offline_contract import (
    format_device_offline_reply_vi,
    format_devices_offline_reply_vi,
)

try:
    from rapidfuzz import fuzz as _rapidfuzz_fuzz
except Exception:  # pragma: no cover - optional dependency
    _rapidfuzz_fuzz = None  # type: ignore[assignment]

try:
    from langdetect import DetectorFactory as _LDDetectorFactory
    from langdetect import detect as _langdetect_detect

    _LDDetectorFactory.seed = 0
except Exception:  # pragma: no cover - optional dependency
    _langdetect_detect = None  # type: ignore[assignment]


def _fuzzy_ratio(a: str, b: str) -> float:
    if _rapidfuzz_fuzz is not None:
        return float(_rapidfuzz_fuzz.ratio(a, b))
    return float(SequenceMatcher(None, a, b).ratio() * 100.0)


DEFAULT_VI_FALLBACK = "Xin lỗi, tôi chỉ hỗ trợ tiếng Việt."
FOREIGN_INPUT_REPLY_VI = "Tôi chỉ hỗ trợ tiếng Việt, bạn vui lòng nói lệnh bằng tiếng Việt nhé."
NONSENSE_INPUT_REPLY_VI = "Tôi chưa nghe rõ lệnh, bạn nói lại rõ hơn nhé."
UNSUPPORTED_DEVICE_REPLY_VI = "Thiết bị này chưa được hỗ trợ trong hệ thống."

_NON_VI_SCRIPT_RE = re.compile(
    r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af"  # Hangul
    r"\u3040-\u30ff\u31f0-\u31ff"                # Kana
    r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"   # CJK
    r"\u0400-\u04ff\u0500-\u052f"                # Cyrillic
    r"\u0e00-\u0e7f"                             # Thai
    r"\u0600-\u06ff\u0750-\u077f"                # Arabic
    r"\u0590-\u05ff"                             # Hebrew
    r"\u0900-\u097f"                             # Devanagari
    r"\u0370-\u03ff]"                            # Greek
)

_FOREIGN_LATIN_DIACRITIC_RE = re.compile(r"[ñÑçÇüÜöÖäÄßłŁžŽšŠčČåÅøØæÆ¿¡îÎëËïÏûÛ]")

_VI_DIACRITIC_RE = re.compile(
    r"[ăâđêôơưĂÂĐÊÔƠƯáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
    r"ÁÀẢÃẠẤẦẨẪẬẮẰẲẴẶÉÈẺẼẸẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌỐỒỔỖỘỚỜỞỠỢÚÙỦŨỤỨỪỬỮỰÝỲỶỸỴ]"
)

_ALLOWED_TECH_TOKENS: frozenset[str] = frozenset({
    "dht11", "ky-037", "ky037", "ky-038", "ky038", "pam8403", "esp8266", "nodemcu",
    "sg90", "yl-69", "yl69", "lm393", "wi-fi", "wifi", "gpio", "gpio0", "gpio2",
    "gpio4", "gpio5", "gpio12", "gpio13", "gpio14", "gpio15", "gpio16", "adc0",
    "d0", "d1", "d2", "d3", "d4", "d5", "d6", "d7", "d8", "a0", "pwm", "mqtt",
    "sqlite", "aoede", "gemini", "live", "am", "pm", "ok", "oke", "okay", "okie",
    "iot", "custom", "reset", "if", "else", "then", "if-else", "rbac", "admin",
    "qr", "app", "web", "ip", "led", "relay", "pin", "auto", "scene", "ir",
    "tivi", "tv", "alo", "video", "servo", "on", "off", "open", "closed", "dry",
    "wet", "loud", "quiet", "speaker", "amp", "do",
})

_FOREIGN_WORDS: frozenset[str] = frozenset({
    # English
    "the", "is", "are", "was", "were", "have", "has", "had", "this", "that",
    "these", "those", "with", "from", "your", "you", "my", "our", "their",
    "please", "sorry", "hello", "hi", "hey", "world", "morning", "evening",
    "night", "good", "bye", "goodbye", "thanks", "thank", "welcome", "turn",
    "light", "lights", "lamp", "door", "open", "close", "switch", "pump",
    "alarm", "siren", "what", "where", "when", "how", "why", "who", "which",
    "would", "could", "should", "will", "can", "cannot", "cant", "dont", "does",
    "did", "sure", "certainly", "assistant", "smart", "home", "device", "devices",
    "sensor", "sensors", "temperature", "humidity", "moisture", "sound", "status",
    "currently", "already", "turned", "opened", "closed", "done", "here", "there",
    "help", "need", "want", "today", "now", "about", "only", "support", "vietnamese",
    "english", "language", "speak", "understand", "command", "please", "schedule",
    "timer", "rule", "minutes", "seconds", "hours", "yes", "no", "not", "all",
    # French
    "bonjour", "bonsoir", "salut", "merci", "comment", "allez", "vous", "suis",
    "lumiere", "porte", "ouvrir", "fermer", "allumer", "eteindre", "tres", "avec",
    "pour", "dans", "plait", "maison", "desole", "pardon", "oui", "non",
    # Spanish
    "hola", "gracias", "favor", "puerta", "luz", "encender", "apagar", "abrir",
    "cerrar", "como", "estas", "temperatura", "humedad", "buenos", "dias", "noches",
    "adios", "si", "casa", "ayuda",
    # German
    "hallo", "danke", "bitte", "licht", "tur", "offnen", "schliessen",
    "einschalten", "ausschalten", "wie", "ist", "das", "und", "ich", "nicht",
    "kann", "guten", "morgen", "abend", "tschuss",
})

_COMMON_VI_WORDS: frozenset[str] = frozenset({
    "da", "dang", "bat", "tat", "mo", "dong", "cua", "chinh", "den", "phong",
    "khach", "ngu", "may", "bom", "tuoi", "cay", "coi", "bao", "nguon", "mach",
    "loa", "nhiet", "do", "am", "dat", "thanh", "cam", "bien", "yen", "tinh",
    "tieng", "lon", "xin", "loi", "toi", "ban", "khong", "co", "quyen", "thuc",
    "hien", "lenh", "nay", "chi", "ho", "tro", "viet", "chao", "giup", "gi",
    "cho", "nha", "thong", "minh", "hen", "gio", "lich", "luat", "lien", "ket",
    "khi", "thi", "roi", "duoc", "dung", "huy", "xoa", "tao", "sua", "doi",
    "cap", "vien", "chu", "nguoi", "ca", "hai", "het", "mot", "ba", "bon",
    "nam", "sau", "bay", "tam", "chin", "muoi", "lan", "hang", "ngay", "phut",
    "giay", "nua", "luc", "sang", "trua", "chieu", "dem", "chua", "nghe", "ro",
    "noi", "lai", "hon", "nhe", "thiet", "bi", "he", "trang", "thai", "tu",
    "vuon", "kho", "uot", "vui", "long", "bang", "on", "tam", "biet", "gap",
    "ngon", "ai", "ten", "la", "lam", "xong", "khoa", "chot", "khep", "gai",
    "ngat", "muc", "nhieu", "nao", "the", "hay", "va", "cung", "voi", "em",
    "anh", "me", "bo", "con", "ong", "a", "nhung", "cac", "moi", "trong",
    "ngoai", "buong", "bong", "cong", "hu", "chong", "trom", "vo", "tay",
    "goc", "cai", "xac", "nhan", "y", "vang", "u", "thoi", "ke", "xem",
    "danh", "sach", "tai", "phan", "tram", "c", "giu", "nguoc", "tri", "giong",
    "ao", "nguyen", "tuan", "cu", "vua", "se", "nhap", "phien", "can", "goi",
    "rat", "tot", "gioi", "qua", "tuyet", "chuc", "muon", "len", "xuong", "ra",
    "vao", "gium", "dum", "kich", "hoat", "ngung", "cup", "dap", "keu", "san",
    "rau", "heo", "nong", "lanh", "toan", "nhanh", "luon", "khoi", "chay",
    "phu", "nuoc", "kiem", "tra", "doc", "hoi", "tuy", "phim", "ghi", "nho",
    "rieng", "tuan", "thu", "nhat", "cuoi", "truoc", "neu", "khac", "them",
    "it", "cao", "thap", "vuot", "duoi", "tren", "nha", "ma", "vi", "nen",
    "de", "van", "hom", "mai", "khuya", "dien", "mat", "don", "ve", "di",
    "an", "viec", "hoc", "nhac", "luong", "khoan", "chut", "xiu", "lat",
    "tru", "troi", "sap", "phai", "hoac", "ben", "phia", "khu", "nhung", "lan",
    "dieu", "khien", "ngoai", "tuyen", "luu", "y",
})

_PURE_FILLERS: frozenset[str] = frozenset({
    "o", "a", "um", "uh", "uhm", "erm", "hmm", "hm", "eh", "oh", "ah",
    "nay", "e", "oi", "ha", "ho", "ne", "a", "da", "u", "ua", "i",
})

_UNSUPPORTED_DEVICE_RE = re.compile(
    r"(?:^|\s)(?:"
    r"quat(?:\s+tran|\s+dung|\s+ban|\s+may|\s+hut)?|"
    r"dieu\s+hoa|may\s+lanh|aircon|"
    r"tivi|ti\s+vi|\btv\b|"
    r"may\s+giat|tu\s+lanh|may\s+loc(?:\s+khong\s+khi|\s+nuoc)?|"
    r"rem(?:\s+cua)?|(?:dem|giem|ren)\s+cua|"
    r"cua\s+(?:cuon|so|ban\s+cong|phong\s+ngu|phong\s+khach|nha\s+ve\s+sinh|nha\s+tam|bep|gara|tu|kinh|hau|sau|phu)|"
    r"(?:bong\s+)?den\s+(?:(?:ngoai|o|trong|tren|duoi|ben|phia|tai|khu)\s+)?(?:(?:nha|phong)\s+)?(?:"
    r"bep|ve\s+sinh|tam|wc|toilet|an|tho|lam\s+viec|kho|gara|xe|"
    r"ban\s+cong|hanh\s+lang|cau\s+thang|san(?:\s+thuong)?|gac(?:\s+xep)?|"
    r"ban\s+hoc|ban\s+an|mai|hien|ngo|lau|tang(?:\s+ham)?|vuon|cong)|"
    r"loa\s+(?:bluetooth|tivi|tv)|bom\s+tang\s+ap|"
    r"(?:binh\s+)?nong\s+lanh|"
    r"lo\s+vi\s+song|robot\s+hut\s+bui|"
    r"hoc\s+lenh|hong\s+ngoai|remote|vs1838b?"
    r")(?:\s|$)"
)

_NEGATED_OR_RHETORICAL_DIRECT_RE = re.compile(
    r"(?:^|\s)(?:"
    r"(?:không(?:\s+(?:cần|muốn|được|nên|phải|đụng))?|khong(?:\s+(?:can|muon|duoc|nen|phai|dung))?|"
    r"đừng(?:\s+(?:có|vội|bao\s+giờ|đụng))?|chớ|"
    r"chưa\s+(?:cần|muốn|vội|đâu)|chua\s+(?:can|muon|voi|dau)|"
    r"khỏi\s+cần|khoi\s+can|thôi\s+không|thoi\s+khong)\s+"
    r"(?:mở|mo|đóng|dong|bật|bat|tắt|tat|khóa|khoa|chốt|chot|khép|khep|ngắt|ngat|dừng|dung|ngừng|ngung|cúp|cup|dập|dap|chạy|chay|kích\s+hoạt|kich\s+hoat|khởi\s+động|khoi\s+dong|cấp\s+nguồn|cap\s+nguon)\b|"
    r"(?:khoan(?:\s+(?:đã|hẵng|hãy|vội))?|chờ\s+(?:chút|đã|xíu|một\s+(?:chút|lát|xíu)|tý|tí)|cho\s+(?:chut|da|xiu|mot\s+(?:chut|lat))|"
    r"đợi\s+(?:chút|đã|xíu|một\s+(?:chút|lát|xíu)|tý|tí)|doi\s+(?:chut|da|xiu|mot\s+(?:chut|lat))|"
    r"từ\s+từ|tu\s+tu|để\s+sau|de\s+sau|lát\s+nữa|lat\s+nua|đừng\s+vội|chưa\s+cần|chưa\s+muốn|chua\s+can|chua\s+muon)\b|"
    r"đúng\s+(?:rồi|không|chưa|nhỉ|nhé|ạ)\b"
    r")",
    re.IGNORECASE,
)

_DEVICE_LABELS_SHORT_VI: dict[str, str] = {
    "main_door": "cửa chính",
    "living_room_light": "đèn phòng khách",
    "bedroom_light": "đèn phòng ngủ",
    "garden_pump": "máy bơm tưới cây",
    "alarm_siren": "còi báo động",
    "speaker_amp": "nguồn mạch loa",
}

_BAD_VI_CLUSTER_RE = re.compile(
    r"(?:[bcdfghjklmnpqrstvwxz]{4,}|"
    r"(?:bl|br|cl|cr|dr|fl|fr|gl|gr|pl|pr|sc|sk|sl|sm|sn|sp|st|sw|wr|df|fg|ghj|sdf|qwe|zxc|asd|jkl|xyz))",
    re.IGNORECASE,
)


def strip_vi_accents(text: str) -> str:
    if not text:
        return ""
    s = str(text).replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in nfkd if unicodedata.category(ch) != "Mn")


def has_vi_diacritics(text: str) -> bool:
    return bool(_VI_DIACRITIC_RE.search(str(text or "")))


def _has_wrong_diacritic_token(text: str, ascii_root: str, valid_accented: tuple[str, ...]) -> bool:
    """True when accented Vietnamese contains a word stripping to ascii_root that is NOT in valid_accented."""
    raw = str(text or "").strip().lower()
    if not raw or not has_vi_diacritics(raw):
        return False
    for tok in re.findall(r"[a-zA-ZÀ-ỹ]+", raw):
        if strip_vi_accents(tok) == ascii_root and tok not in valid_accented:
            return True
    return False


_DEVICE_HEAD_NOUN_DIACRITICS: dict[str, tuple[str, ...]] = {
    "den": ("đèn",),
    "coi": ("còi",),
    "cua": ("cửa", "cữa"),
    "bom": ("bơm",),
    "loa": ("loa",),
    "phong": ("phòng",),
}


def _has_wrong_diacritic_device_head(text: str, ascii_root: str) -> bool:
    """Uniform positional wrong-diacritic guard across all 6 device head nouns (đèn, còi, cửa, bơm, loa, phòng)."""
    raw = str(text or "").strip().lower()
    if not raw or not has_vi_diacritics(raw):
        return False
    valid = _DEVICE_HEAD_NOUN_DIACRITICS.get(ascii_root)
    if not valid:
        return False
    toks = re.findall(r"[a-zA-ZÀ-ỹ]+", raw)
    # If the exact properly-spelled head noun is already present, unrelated words elsewhere must not poison it.
    if any(t in valid for t in toks):
        return False
    if ascii_root == "den":
        light_verbs = {
            "bật", "tắt", "mở", "ngắt", "cúp", "dập", "rọi", "kích", "hoạt",
            "dừng", "ngừng", "ngưng", "cái", "bóng", "hai", "cả", "hết", "tất",
        }
        light_quals = {"phòng", "khách", "ngủ", "buồng", "hết", "tất", "toàn"}
        for idx, tok in enumerate(toks):
            if strip_vi_accents(tok) == "den" and tok not in valid:
                prev_t = toks[idx - 1] if idx > 0 else ""
                next_t = toks[idx + 1] if idx + 1 < len(toks) else ""
                # 'đến' is a normal Vietnamese preposition ('từ ... đến ...', 'có người đến'); only flag in light-command position
                if tok == "đến":
                    if prev_t in light_verbs or next_t in light_quals:
                        return True
                    continue
                if prev_t in ("màu", "tối") and next_t not in light_quals:
                    continue
                return True
        return False
    if ascii_root == "cua":
        # 'của' is a normal Vietnamese possessive preposition ("của tôi"); only flag wrong-diacritic 'cua'/'của'
        # when used in a door-command position (after open/close verb or before door qualifier).
        door_verbs = {"mở", "đóng", "khóa", "khoá", "chốt", "khép", "gài", "kín", "hé"}
        door_quals = {"chính", "chánh", "lớn", "nhà", "ra", "đi", "lại"}
        for idx, tok in enumerate(toks):
            if strip_vi_accents(tok) == "cua" and tok not in valid:
                prev_t = toks[idx - 1] if idx > 0 else ""
                next_t = toks[idx + 1] if idx + 1 < len(toks) else ""
                if prev_t in door_verbs or next_t in door_quals or tok != "của":
                    return True
        return False
    if ascii_root == "coi":
        # Southern/colloquial particle 'coi' ("mở loa lên coi") is NOT a wrong-diacritic siren unless paired with siren words or after a siren verb.
        siren_quals = {"báo", "hú", "chống"}
        siren_verbs = {"bật", "tắt", "mở", "ngắt", "dừng", "ngừng", "ngưng", "cúp", "dập", "hoạt", "động", "cho"}
        for idx, tok in enumerate(toks):
            if strip_vi_accents(tok) == "coi" and tok not in valid:
                prev_t = toks[idx - 1] if idx > 0 else ""
                next_t = toks[idx + 1] if idx + 1 < len(toks) else ""
                if next_t in siren_quals or prev_t in siren_verbs or tok != "coi":
                    return True
        return False
    if ascii_root == "phong":
        room_quals = {"khách", "ngủ", "buồng"}
        for idx, tok in enumerate(toks):
            if strip_vi_accents(tok) == "phong" and tok not in valid:
                next_t = toks[idx + 1] if idx + 1 < len(toks) else ""
                if next_t in room_quals:
                    return True
        return False
    if ascii_root == "bom":
        pump_verbs = {"bật", "tắt", "mở", "ngắt", "dừng", "ngừng", "ngưng", "cúp", "dập", "hoạt", "động", "cho", "chạy", "máy"}
        pump_quals = {"tưới", "nước", "vườn", "cây", "ngoài"}
        for idx, tok in enumerate(toks):
            if strip_vi_accents(tok) == "bom" and tok not in valid:
                prev_t = toks[idx - 1] if idx > 0 else ""
                next_t = toks[idx + 1] if idx + 1 < len(toks) else ""
                if prev_t in pump_verbs or next_t in pump_quals:
                    return True
        return False
    if ascii_root == "loa":
        amp_verbs = {"bật", "tắt", "mở", "ngắt", "dừng", "ngừng", "ngưng", "cúp", "dập", "hoạt", "động", "cho", "mạch", "nguồn"}
        amp_quals = {"chuông", "kêu", "lên", "đi"}
        for idx, tok in enumerate(toks):
            if strip_vi_accents(tok) == "loa" and tok not in valid:
                prev_t = toks[idx - 1] if idx > 0 else ""
                next_t = toks[idx + 1] if idx + 1 < len(toks) else ""
                if prev_t in amp_verbs or next_t in amp_quals:
                    return True
        return False
    return _has_wrong_diacritic_token(raw, ascii_root, valid)


def _has_wrong_diacritic_light_word(text: str) -> bool:
    """True when accented Vietnamese contains a wrong-diacritic light head word."""
    return _has_wrong_diacritic_device_head(text, "den")


def _detect_wrong_diacritic_near_miss_clarification(raw_text: str) -> str | None:
    """For accented input with an action verb + wrong-diacritic device head noun across all 6 devices, ask clarification."""
    raw = _clean_space(raw_text).lower()
    if not raw or not has_vi_diacritics(raw):
        return None
    bad_den = _has_wrong_diacritic_device_head(raw, "den") or _has_wrong_diacritic_device_head(raw, "phong")
    bad_coi = _has_wrong_diacritic_device_head(raw, "coi")
    bad_cua = _has_wrong_diacritic_device_head(raw, "cua")
    bad_bom = _has_wrong_diacritic_device_head(raw, "bom")
    bad_loa = _has_wrong_diacritic_device_head(raw, "loa")
    if not (bad_den or bad_coi or bad_cua or bad_bom or bad_loa):
        return None
    norm = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(raw)).split())
    act = _extract_clause_action(norm, None, raw_clause=raw, input_has_diacritics=True)
    if act is None:
        return None
    act_vi = "tắt" if act in ("turn_off", "close") else "bật"
    door_vi = "đóng" if act in ("turn_off", "close") else "mở"
    padded = f" {norm} "
    if bad_den:
        if " phong ngu " in padded or " ngu " in padded or " buong " in padded:
            return f"Bạn muốn {act_vi} đèn phòng ngủ phải không?"
        if any(k in padded for k in (" tat ca ", " toan bo ", " ca hai ", " hai ", " het ")):
            return f"Bạn muốn {act_vi} tất cả đèn phải không?"
        if " phong khach " in padded or " khach " in padded:
            return f"Bạn muốn {act_vi} đèn phòng khách phải không?"
        return f"Bạn muốn {act_vi} đèn phòng khách hay đèn phòng ngủ?"
    if bad_coi:
        return f"Bạn muốn {act_vi} còi báo động phải không?"
    if bad_cua:
        return f"Bạn muốn {door_vi} cửa chính phải không?"
    if bad_bom:
        return f"Bạn muốn {act_vi} máy bơm tưới cây phải không?"
    if bad_loa:
        return f"Bạn muốn {act_vi} nguồn mạch loa phải không?"
    return None


def _clean_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _tokenize_alpha(text: str) -> list[str]:
    norm = strip_vi_accents(str(text or "").lower())
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", norm)


def _is_allowlisted_token(tok: str) -> bool:
    if tok in _ALLOWED_TECH_TOKENS:
        return True
    if tok.isdigit():
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?[a-z%]?", tok):
        return True
    if re.fullmatch(r"(?:gpio\d+|d[0-8]|a0|ky-?03[78]|dht11|pam8403|esp8266|sg90|yl-?69|lm393)", tok):
        return True
    return False


def _is_plausible_vi_word(tok: str) -> bool:
    if _is_allowlisted_token(tok) or tok in _COMMON_VI_WORDS:
        return True
    if not tok.isalpha():
        return True
    if len(tok) <= 1:
        return tok in ("a", "o", "u", "e", "i", "y")
    if any(ch in tok for ch in ("f", "j", "w", "z")):
        return False
    if not re.search(r"[aeiouy]", tok):
        return False
    if _BAD_VI_CLUSTER_RE.search(tok):
        return False
    if len(tok) >= 8:
        return False
    return True


def _detect_foreign_latin(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    if _FOREIGN_LATIN_DIACRITIC_RE.search(raw):
        return True

    tokens = _tokenize_alpha(raw)
    alpha_tokens = [t for t in tokens if any(c.isalpha() for c in t) and not _is_allowlisted_token(t)]
    if not alpha_tokens:
        return False

    has_vi_diacritics = bool(_VI_DIACRITIC_RE.search(raw))
    foreign_hits = sum(1 for t in alpha_tokens if t in _FOREIGN_WORDS and t not in _COMMON_VI_WORDS)
    vi_hits = sum(1 for t in alpha_tokens if t in _COMMON_VI_WORDS)

    if len(alpha_tokens) == 1:
        t0 = alpha_tokens[0]
        if t0 in _FOREIGN_WORDS and t0 not in _COMMON_VI_WORDS and not has_vi_diacritics:
            return True
        return False

    if foreign_hits >= 2 and (not has_vi_diacritics or foreign_hits >= max(2, vi_hits)):
        return True
    if foreign_hits >= 1 and vi_hits == 0 and not has_vi_diacritics:
        return True

    # Never let langdetect misclassify clean unaccented Vietnamese commands as foreign
    if (
        not has_vi_diacritics
        and foreign_hits == 0
        and all(_is_plausible_vi_word(t) for t in alpha_tokens)
        and (vi_hits >= 2 or _contains_command_or_query_intent(raw))
    ):
        return False

    if not has_vi_diacritics and len(alpha_tokens) >= 3 and _langdetect_detect is not None:
        filtered_str = " ".join(alpha_tokens)
        try:
            lang = str(_langdetect_detect(filtered_str) or "").lower()
            if lang and lang != "vi" and vi_hits < max(2, len(alpha_tokens) // 2):
                return True
        except Exception:
            pass

    return False


def ensure_vietnamese_reply(
    text: str,
    *,
    fallback: str = DEFAULT_VI_FALLBACK,
) -> str:
    """Guarantee 100% Vietnamese output; replace foreign/corrupted replies with a clean Vietnamese fallback."""
    cleaned = _clean_space(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\u200b-\u200f\ufeff]", "", str(text or "")))
    if not cleaned:
        return fallback
    if _NON_VI_SCRIPT_RE.search(cleaned):
        return fallback
    if _detect_foreign_latin(cleaned):
        return fallback
    return cleaned


def is_foreign_or_nonsense_input(text: str) -> tuple[bool, str]:
    """Detect clearly foreign-language input or meaningless fillers/gibberish."""
    raw = _clean_space(text)
    if not raw:
        return True, "nonsense"
    if _NON_VI_SCRIPT_RE.search(raw):
        return True, "foreign"
    if _FOREIGN_LATIN_DIACRITIC_RE.search(raw):
        return True, "foreign"

    tokens = _tokenize_alpha(raw)
    if not tokens:
        return True, "nonsense"

    # Digits/punctuation only (e.g. "12345", "999")
    if all(t.isdigit() for t in tokens):
        return True, "nonsense"

    if _detect_foreign_latin(raw):
        return True, "foreign"

    # Pure fillers only ("ờ", "à", "ừm", "này", "ờ à ừm")
    if all(t in _PURE_FILLERS for t in tokens):
        return True, "nonsense"

    # Gibberish / keyboard mash check (e.g., "asdfgh", "blabla", "qwerty")
    has_vi_diacritics = bool(_VI_DIACRITIC_RE.search(raw))
    if not has_vi_diacritics:
        alpha_tokens = [t for t in tokens if any(c.isalpha() for c in t) and not _is_allowlisted_token(t)]
        if alpha_tokens:
            bad_count = sum(1 for t in alpha_tokens if not _is_plausible_vi_word(t))
            if bad_count == len(alpha_tokens) or (bad_count >= 1 and len(alpha_tokens) <= 2 and all(t not in _COMMON_VI_WORDS for t in alpha_tokens)):
                return True, "nonsense"

    return False, ""


def _contains_command_or_query_intent(text: str) -> bool:
    """Return True if the utterance contains a real device control, sensor query, or automation command."""
    raw_low = str(text or "").lower()
    # Preserve 'không khí' (air) so it never collapses into 'khi' (when)
    raw_no_air = re.sub(r"\b(?:không\s+khí|khong\s+khi)\b", " khong_khi ", raw_low)
    norm = f" {strip_vi_accents(raw_no_air)} "
    norm = re.sub(r"[^a-z0-9_\s]+", " ", norm)
    norm = f" {' '.join(norm.split())} "

    device_cues = (
        " cua ", " cua chinh ", " cong ", " den ", " may bom ", " bom ", " tuoi cay ",
        " tuoi vuon ", " coi ", " bao dong ", " loa ", " pam8403 ", " am ly ",
        " thiet bi ", " quat ", " dieu hoa ", " may lanh ", " tivi ", " rem ",
    )
    action_cues = (
        " mo ", " dong ", " khoa ", " chot ", " khep ", " gai ", " bat ", " tat ",
        " ngat ", " dung ", " ngung ", " khoi dong ", " chay ",
    )
    sensor_cues = (
        " nhiet do ", " do am ", " cam bien ", " am thanh ", " ky037 ", " ky 037 ",
        " tieng dong ", " vo tay ", " trang thai ", " bom tu dong ", " bao nhieu do ",
        " khong_khi ", " dht11 ",
    )
    automation_cues = (
        " hen gio ", " dat lich ", " lich ", " sau ", " nua ", " tao lenh ", " luu lenh ",
        " them lenh ", " luu cau ", " dat cau ", " gan cau ", " tao cau ",
        " sua lenh ", " xoa lenh ", " huy ", " lien ket ", " tao luat ", " quy tac ",
        " reset ", " dat lai ", " khoi dong lai ", " bo dieu khien ", " cau hinh ",
        " mac dinh ", " thanh vien ", " cap quyen ", " thu hoi ", " khi ", " neu ",
    )
    if any(k in norm for k in sensor_cues):
        return True
    if any(k in norm for k in automation_cues):
        if " gap lai sau " in norm and not any(k in norm for k in automation_cues if k != " sau "):
            pass
        else:
            return True
    if any(d in norm for d in device_cues) and any(a in norm for a in action_cues):
        return True
    if " tuoi cay " in norm or " tuoi vuon " in norm:
        return True
    return False


def classify_small_talk_vi(
    text: str,
    user_name: str = "",
) -> dict[str, Any] | None:
    """Classify Vietnamese greetings, identity, help, thanks, and goodbye without ever blocking RBAC."""
    raw = _clean_space(text)
    if not raw:
        return None
    if _contains_command_or_query_intent(raw):
        return None

    norm = re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(raw.lower()))
    norm = " ".join(norm.split())
    if not norm:
        return None

    # Identity questions
    if any(
        p in norm
        for p in (
            "ban la ai",
            "em la ai",
            "may la ai",
            "ban ten gi",
            "ten cua ban la gi",
            "ban ten la gi",
            "ai tao ra ban",
            "ban duoc ai tao ra",
            "ai lam ra ban",
            "ai lap trinh ban",
            "gioi thieu ban than",
            "gioi thieu ve ban",
        )
    ):
        return {
            "kind": "small_talk",
            "subkind": "identity",
            "reply": "Tôi là trợ lý ảo điều khiển nhà thông minh do Nguyễn Tuấn Anh tạo ra.",
        }

    # Help / capabilities (standalone help ONLY: never hijack commands carrying polite tail "giúp mình"/"giúp tôi")
    help_explicit = (
        "huong dan",
        "ban lam duoc gi",
        "ban co the lam gi",
        "ban co the lam nhung gi",
        "ban duoc lam nhung gi",
        "co nhung lenh gi",
        "tro giup",
        "ho tro gi",
        "chuc nang cua ban",
    )
    is_standalone_help = (
        any(p in norm for p in help_explicit)
        or (
            len(norm.split()) <= 5
            and any(p in norm for p in ("giup toi", "giup minh"))
            and re.fullmatch(
                r"(?:ban|em|tro\s+ly|hay|xin|vui\s+long)?\s*(?:co\s+the\s+)?giup\s+(?:toi|minh)(?:\s+(?:voi|nhe|nha|duoc\s+khong|nhe|a))?",
                norm,
            )
            is not None
        )
    )
    if is_standalone_help:
        return {
            "kind": "small_talk",
            "subkind": "help",
            "reply": (
                "Tôi có thể bật tắt đèn, mở đóng cửa chính, điều khiển máy bơm, còi báo động, "
                "nguồn mạch loa, đọc cảm biến, hẹn giờ và tạo lệnh tự động bằng tiếng Việt."
            ),
        }

    # Thanks / praise
    if any(
        p in norm
        for p in (
            "cam on",
            "tot lam",
            "gioi qua",
            "hay qua",
            "tuyet voi",
            "cam on ban",
            "cam on nhe",
            "cam on em",
            "cam on nhieu",
        )
    ):
        return {
            "kind": "small_talk",
            "subkind": "thanks",
            "reply": "Dạ không có gì ạ.",
        }

    # Goodbye
    if norm in ("tam biet", "tam biet ban", "tam biet nhe", "gap lai sau", "hen gap lai", "ket thuc", "ngu ngon", "chuc ngu ngon") or any(
        p in norm for p in ("tam biet", "gap lai sau", "hen gap lai", "chuc ngu ngon")
    ):
        reply = "Chúc bạn ngủ ngon ạ." if "ngu ngon" in norm else "Dạ chào tạm biệt, hẹn gặp lại ạ."
        return {
            "kind": "small_talk",
            "subkind": "goodbye",
            "reply": reply,
        }

    # Greetings
    if any(p in norm for p in ("chao buoi sang",)):
        return {
            "kind": "small_talk",
            "subkind": "greeting",
            "reply": "Dạ chào buổi sáng ạ.",
        }
    if any(p in norm for p in ("chao buoi trua",)):
        return {
            "kind": "small_talk",
            "subkind": "greeting",
            "reply": "Dạ chào buổi trưa ạ.",
        }
    if any(p in norm for p in ("chao buoi chieu",)):
        return {
            "kind": "small_talk",
            "subkind": "greeting",
            "reply": "Dạ chào buổi chiều ạ.",
        }
    if any(p in norm for p in ("chao buoi toi",)):
        return {
            "kind": "small_talk",
            "subkind": "greeting",
            "reply": "Dạ chào buổi tối ạ.",
        }

    greeting_exact = {
        "chao", "chao ban", "xin chao", "xin chao ban", "chao em", "chao anh",
        "chao chi", "chao tro ly", "e tro ly", "alo tro ly", "chao nha thong minh",
        "xin chao tro ly", "xin chao nha thong minh", "alo", "tro ly oi", "ban oi",
    }
    if norm in greeting_exact or re.match(
        r"^(?:xin\s+chao|chao\s+ban|chao\s+tro\s+ly|chao\s+nha\s+thong\s+minh|e\s+tro\s+ly|alo\s+tro\s+ly)(?:\s+(?:nha|nhe|a|oi|em|ban))?$",
        norm,
    ):
        return {
            "kind": "small_talk",
            "subkind": "greeting",
            "reply": "Dạ chào bạn ạ.",
        }

    return None


def normalize_vietnamese_utterance(text: str) -> str:
    """Strip conversational fillers and normalize natural Vietnamese regional variants for direct commands."""
    s = _clean_space(text).lower()
    if not s:
        return ""
    input_has_diac = has_vi_diacritics(s)

    # Strip leading greeting/attention/vocative prefixes ("trợ lý ơi, ...", "<1-2 words> ơi, ...") when followed by a command
    s = re.sub(
        r"^(?:(?:xin\s+)?chào(?:\s+(?:bạn|em|anh|chị|trợ\s+lý|nhà\s+thông\s+minh))?|"
        r"(?:xin\s+)?chao(?:\s+(?:ban|em|anh|chi|tro\s+ly|nha\s+thong\s+minh))?|"
        r"ê\s+trợ\s+lý|e\s+tro\s+ly|al[ôo]\s+trợ\s+lý|al[ôo]\s+tro\s+ly|"
        r"[a-zA-ZÀ-ỹ]+(?:\s+[a-zA-ZÀ-ỹ]+){0,2}\s+(?:ơi|oi))\s*[,;:.!?…-]*\s+",
        "",
        s,
        flags=re.IGNORECASE,
    )

    # Strip leading discourse filler "ờ thì..." / "à thì..." / "ừm thì..."
    s = re.sub(r"^(?:ờ|à|ừm|ừ|ơ)\s+thì\b[\s,;:.…-]*", "", s, flags=re.IGNORECASE).strip()

    # Strip leading filler words repeatedly
    for _ in range(4):
        updated = re.sub(
            r"^(?:ờ|à|ừm|ừ|ơ|này|ê|ơi|nè|alô|alo|o|a|um|nay|e|oi|làm\s+ơn|lam\s+on|hãy|hay)\b[\s,;:.…-]*",
            "",
            s,
            flags=re.IGNORECASE,
        ).strip()
        if updated == s:
            break
        s = updated

    # Collapse stuttered word repetition across ellipsis or discourse fillers
    s = re.sub(
        r"\b(phòng|cửa|bơm|còi|đèn|loa|bật|tắt|mở|đóng|cái)\b(?:\s*[,;:.…-]+\s*(?:(?:à|ờ|ừm|ơ)\s+)?|\s+(?:à|ờ|ừm|ơ)\s+)\1\b",
        r"\1",
        s,
        flags=re.IGNORECASE,
    )
    if not input_has_diac:
        s = re.sub(
            r"\b(phong|cua|bom|coi|den|loa|bat|tat|mo|dong|cai)\b(?:\s*[,;:.…-]+\s*(?:(?:a|o|um)\s+)?|\s+(?:a|o|um)\s+)\1\b",
            r"\1",
            s,
            flags=re.IGNORECASE,
        )
    s = re.sub(r"[…]+|\.{2,}", " ", s)

    # Normalize natural Vietnamese regional/colloquial device synonyms (strictly preserving diacritic safety)
    # Door variants
    s = re.sub(r"\bcửa\s+chánh\b", "cửa chính", s)
    s = re.sub(r"\bmở\s+cổng\b", "mở cửa chính", s)
    s = re.sub(r"\b(?:khóa|khoá|chốt|khép|gài)\s+(?:cửa\s+chính|cửa|cổng)\b", "đóng cửa chính", s)
    s = re.sub(r"\bđóng\s+cổng\b", "đóng cửa chính", s)
    if not input_has_diac:
        s = re.sub(r"\bmo\s+cong\b", "mo cua chinh", s)
        s = re.sub(r"\b(?:khoa|chot|khep|gai)\s+(?:cua\s+chinh|cua|cong)\b", "dong cua chinh", s)
        s = re.sub(r"\bdong\s+cong\b", "dong cua chinh", s)

    # Lights natural regional/colloquial variants (NEVER default bare 'đèn' or coerce wrong-diacritic tokens!)
    s = re.sub(r"\brọi\s+(?:cái\s+)?((?:bóng\s+)?đèn)\b", r"bật \1", s)
    s = re.sub(
        r"\bbóng\s+đèn\s+phòng\s+khách\b|\bbóng\s+đèn\s+khách\b|\bđèn\s+khách\b|"
        r"\bđèn\s+ngoài(?!\s+(?:ban\s+công|sân|hiên|cổng|vườn|hành\s+lang|ngõ|nhà|kho|gara|bếp|tắm|vệ\s+sinh))\b|\bđèn\s+chính\b",
        "đèn phòng khách",
        s,
    )
    s = re.sub(r"\bbóng\s+đèn\s+phòng\s+ngủ\b|\bđèn\s+ngủ\b|\bđèn\s+buồng\b|\bđèn\s+trong\s+phòng\b", "đèn phòng ngủ", s)
    s = re.sub(
        r"\b(?:(?:hết|toàn\s+bộ|tất\s+cả)(?:\s+các)?|cả\s+hai|hai|cả\s+2|2|các|mọi)\s+(?:bóng\s+)?đèn(?!\s+(?:phòng|khách|ngủ|buồng))\b",
        "tất cả đèn",
        s,
    )
    s = re.sub(r"\bđèn\s+(?:cả\s+)?(?:hai|2)\s+phòng\b", "tất cả đèn", s)
    s = re.sub(
        r"\b(?:(?:toàn\s+bộ|tất\s+cả|hết|cả|mọi)\s+)+(?:(?:các|sáu|6)\s+)*thiết\s+bị\b",
        "tất cả thiết bị",
        s,
    )
    s = re.sub(r"\bcho\s+(?:cái\s+)?(đèn\s+phòng\s+(?:khách|ngủ)|tất\s+cả\s+đèn)\s+sáng(?:\s+lên)?\b", r"bật \1", s)
    if not input_has_diac:
        s = re.sub(r"\broi\s+(?:cai\s+)?((?:bong\s+)?den)\b", r"bat \1", s)
        s = re.sub(
            r"\bbong\s+den\s+phong\s+khach\b|\bbong\s+den\s+khach\b|\bden\s+khach\b|"
            r"\bden\s+ngoai(?!\s+(?:ban\s+cong|san|hien|cong|vuon|hanh\s+lang|ngo|nha|kho|gara|bep|tam|ve\s+sinh))\b|\bden\s+chinh\b",
            "den phong khach",
            s,
        )
        s = re.sub(r"\bbong\s+den\s+phong\s+ngu\b|\bden\s+ngu\b|\bden\s+buong\b|\bden\s+trong\s+phong\b", "den phong ngu", s)
        s = re.sub(
            r"\b(?:(?:het|toan\s+bo|tat\s+ca)(?:\s+cac)?|ca\s+hai|hai|ca\s+2|2|cac|moi)\s+(?:bong\s+)?den(?!\s+(?:phong|khach|ngu|buong))\b",
            "tat ca den",
            s,
        )
        s = re.sub(r"\bden\s+(?:ca\s+)?(?:hai|2)\s+phong\b", "tat ca den", s)
        s = re.sub(
            r"\b(?:(?:toan\s+bo|tat\s+ca|het|ca|moi)\s+)+(?:(?:cac|sau|6)\s+)*thiet\s+bi\b",
            "tat ca thiet bi",
            s,
        )
        s = re.sub(r"\bcho\s+(?:cai\s+)?(den\s+phong\s+(?:khach|ngu)|tat\s+ca\s+den)\s+sang(?:\s+len)?\b", r"bat \1", s)

    # Pump natural variants
    s = re.sub(
        r"\b(?:nghỉ|ngừng|ngưng|dừng|thôi|tắt|ngắt|cúp|dập)\s+(?:chạy\s+)?(?:tưới\s+cây|tưới\s+vườn|tưới\s+nước|bơm(?:\s+(?:nước|vườn|tưới\s+(?:cây|vườn)))?)\b",
        "tắt máy bơm tưới cây",
        s,
    )
    s = re.sub(
        r"\b(?:hệ\s+thống\s+tưới(?:\s+(?:nước|cây|vườn))?(?:\s+ngoài\s+vườn)?|"
        r"tưới\s+nước(?:\s+ngoài\s+vườn)?|"
        r"máy\s+bơm\s+ngoài\s+vườn|bơm\s+ngoài\s+vườn|"
        r"bơm\s+nước(?:\s+tưới\s+(?:cây|vườn))?|bơm\s+tưới\s+(?:cây|vườn)|bơm\s+vườn)\b",
        "máy bơm tưới cây",
        s,
    )
    if not input_has_diac:
        s = re.sub(
            r"\b(?:nghi|ngung|dung|thoi|tat|ngat|cup|dap)\s+(?:chay\s+)?(?:tuoi\s+cay|tuoi\s+vuon|tuoi\s+nuoc|bom(?:\s+(?:nuoc|vuon|tuoi\s+(?:cay|vuon)))?)\b",
            "tat may bom tuoi cay",
            s,
        )
        s = re.sub(
            r"\b(?:he\s+thong\s+tuoi(?:\s+(?:nuoc|cay|vuon))?(?:\s+ngoai\s+vuon)?|"
            r"tuoi\s+nuoc(?:\s+ngoai\s+vuon)?|"
            r"may\s+bom\s+ngoai\s+vuon|bom\s+ngoai\s+vuon|"
            r"bom\s+nuoc(?:\s+tuoi\s+(?:cay|vuon))?|bom\s+tuoi\s+(?:cay|vuon)|bom\s+vuon)\b",
            "may bom tuoi cay",
            s,
        )

    # General causative activation: "cho <device> hoạt động / chạy / hú / kêu" -> "bật <device>"
    s = re.sub(
        r"\bcho\s+(?:cái\s+)?(máy\s+bơm(?:\s+tưới\s+cây)?|bơm|đèn\s+phòng\s+(?:khách|ngủ)|tất\s+cả\s+đèn|còi\s+báo\s+động|còi\s+hú|còi|nguồn\s+mạch\s+loa|mạch\s+loa|loa\s+chuông)\s+(?:hoạt\s+động|chạy|hú|kêu)\b",
        r"bật \1",
        s,
    )
    if not input_has_diac:
        s = re.sub(
            r"\bcho\s+(?:cai\s+)?(may\s+bom(?:\s+tuoi\s+cay)?|bom|den\s+phong\s+(?:khach|ngu)|tat\s+ca\s+den|coi\s+bao\s+dong|coi\s+hu|coi|nguon\s+mach\s+loa|mach\s+loa|loa\s+chuong)\s+(?:hoat\s+dong|chay|hu|keu)\b",
            r"bat \1",
            s,
        )

    # Siren natural variants (never coerce unaccented particle 'coi' in accented text!)
    s = re.sub(r"\b(?:còi\s+hú|chống\s+trộm)\b", "còi báo động", s)
    if not input_has_diac:
        s = re.sub(r"\b(?:coi\s+hu|chong\s+trom)\b", "coi bao dong", s)

    # Speaker amp natural variants
    if input_has_diac:
        s = re.sub(r"\bcho\s+(?:cái\s+)?(?:loa\s+chuông|nguồn\s+mạch\s+loa|mạch\s+loa|loa)\s+kêu\b", "bật nguồn mạch loa", s)
        s = re.sub(r"\b(?:loa\s+chuông|âm\s+ly|âm\s+li|(?<!nguồn\s)mạch\s+loa|nguồn\s+loa|pam8403)\b", "nguồn mạch loa", s)
    else:
        s = re.sub(r"\bcho\s+(?:cai\s+)?(?:loa\s+chuong|nguon\s+mach\s+loa|mach\s+loa|loa)\s+keu\b", "bat nguon mach loa", s)
        s = re.sub(r"\b(?:loa\s+chuong|am\s+ly|am\s+li|(?<!nguon\s)mach\s+loa|nguon\s+loa|pam8403)\b", "nguon mach loa", s)

    # Strip polite fillers inside / at end without breaking clause conjunctions
    s = re.sub(
        r"\b(?:giúp\s+(?:mình|tôi|tớ|bà|ông|bé|con|anh|chị|em)|hộ\s+(?:mình|tôi|ông|bà|anh|chị|em)|"
        r"(?:giùm|dùm)\s+(?:tôi|mình|tui|cái|tau|anh|chị|em)|"
        r"cho\s+(?:tôi|mình|bà|ông|bé|con|anh|chị|em)|làm\s+ơn|"
        r"giup\s+(?:minh|toi|to|ba|ong|be|con|anh|chi|em)|ho\s+(?:minh|toi|ong|ba|anh|chi|em)|"
        r"(?:gium|dum)\s+(?:toi|minh|tui|cai|tau|anh|chi|em)|"
        r"cho\s+(?:toi|minh|ba|ong|be|con|anh|chi|em)|lam\s+on)\b",
        " ",
        s,
    )
    # Strip trailing softeners & regional particles
    if input_has_diac:
        s = re.sub(r"\b(?:phát|cái|lên|đi)\s+coi\b", " ", s)
        # Polite imperative ending "đi ạ" is sometimes heard as "đi à" without question mark
        s = re.sub(r"\s+đi\s+à\s*[.!]*$", "", s.strip()).strip()
    for _ in range(3):
        updated = re.sub(
            r"(?:\s+(?:nhé|nha|nhá|nghen|hen|hỉ|hè|nghe|cơ|đê|nào|ấy|ạ|đi|với|luôn|ngay|nhanh|lẹ|cái|hộ|giùm|dùm|nhe|nha|a|di|voi|luon|ngay|nhanh|cai|ma))+\s*[.!?]*$",
            "",
            s.strip(),
        ).strip()
        if updated == s:
            break
        s = updated

    # Strip inline fillers
    s = re.sub(r"\b(?:luôn|ngay|nhanh|lẹ|nhé|nha|nhá|nghen|hen|hỉ|hè|ạ)\b", " ", s)
    return _clean_space(s)


_DIRECT_DEVICE_PATTERNS_ACCENTED: tuple[tuple[str, str], ...] = (
    ("tất cả thiết bị", "all_devices"),
    ("toàn bộ thiết bị", "all_devices"),
    ("hết thiết bị", "all_devices"),
    ("mọi thiết bị", "all_devices"),
    ("tất cả đèn", "all_lights"),
    ("toàn bộ đèn", "all_lights"),
    ("hết đèn", "all_lights"),
    ("cả hai đèn", "all_lights"),
    ("hai đèn", "all_lights"),
    ("cả 2 đèn", "all_lights"),
    ("các đèn", "all_lights"),
    ("mọi đèn", "all_lights"),
    ("đèn phòng khách", "living_room_light"),
    ("đèn khách", "living_room_light"),
    ("đèn phòng ngủ", "bedroom_light"),
    ("đèn ngủ", "bedroom_light"),
    ("đèn buồng", "bedroom_light"),
    ("cửa chính", "main_door"),
    ("cửa chánh", "main_door"),
    ("cửa lớn", "main_door"),
    ("cửa nhà", "main_door"),
    ("cửa ra vào", "main_door"),
    ("máy bơm tưới cây", "garden_pump"),
    ("máy bơm", "garden_pump"),
    ("bơm nước", "garden_pump"),
    ("bơm vườn", "garden_pump"),
    ("bơm ngoài vườn", "garden_pump"),
    ("tưới cây", "garden_pump"),
    ("tưới vườn", "garden_pump"),
    ("còi báo động", "alarm_siren"),
    ("báo động", "alarm_siren"),
    ("còi hú", "alarm_siren"),
    ("nguồn mạch loa", "speaker_amp"),
    ("mạch loa", "speaker_amp"),
    ("nguồn loa", "speaker_amp"),
    ("loa chuông", "speaker_amp"),
    ("pam8403", "speaker_amp"),
)

_DIRECT_DEVICE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("tat ca thiet bi", "all_devices"),
    ("toan bo thiet bi", "all_devices"),
    ("het thiet bi", "all_devices"),
    ("moi thiet bi", "all_devices"),
    ("tat ca den", "all_lights"),
    ("toan bo den", "all_lights"),
    ("het den", "all_lights"),
    ("ca hai den", "all_lights"),
    ("hai den", "all_lights"),
    ("ca 2 den", "all_lights"),
    ("cac den", "all_lights"),
    ("moi den", "all_lights"),
    ("den phong khach", "living_room_light"),
    ("den khach", "living_room_light"),
    ("den phong ngu", "bedroom_light"),
    ("den ngu", "bedroom_light"),
    ("cua chinh", "main_door"),
    ("cua chanh", "main_door"),
    ("cua lon", "main_door"),
    ("cua nha", "main_door"),
    ("cua ra vao", "main_door"),
    ("may bom tuoi cay", "garden_pump"),
    ("may bom", "garden_pump"),
    ("bom nuoc", "garden_pump"),
    ("bom vuon", "garden_pump"),
    ("bom ngoai vuon", "garden_pump"),
    ("tuoi cay", "garden_pump"),
    ("tuoi vuon", "garden_pump"),
    ("coi bao dong", "alarm_siren"),
    ("bao dong", "alarm_siren"),
    ("coi hu", "alarm_siren"),
    ("nguon mach loa", "speaker_amp"),
    ("mach loa", "speaker_amp"),
    ("nguon loa", "speaker_amp"),
    ("loa chuong", "speaker_amp"),
    ("pam8403", "speaker_amp"),
)


def _extract_clause_device(
    norm_clause: str,
    *,
    raw_clause: str | None = None,
    input_has_diacritics: bool | None = None,
    allow_unaccented_bare_den: bool = False,
) -> str | None:
    """Match device targets on accented Vietnamese first; enforce uniform wrong-diacritic guard and never default bare 'đèn'."""
    _ = allow_unaccented_bare_den  # Bare 'đèn' must always clarify when >1 light exists in registry.
    if raw_clause is not None:
        raw_clean = " ".join(re.sub(r"[^a-zA-ZÀ-ỹ0-9\s]+", " ", raw_clause.lower()).split())
        has_diac = has_vi_diacritics(raw_clean) if input_has_diacritics is None else bool(input_has_diacritics)
        if has_diac:
            raw_padded = f" {raw_clean} "
            bad_den = _has_wrong_diacritic_device_head(raw_clean, "den")
            bad_coi = _has_wrong_diacritic_device_head(raw_clean, "coi")
            bad_cua = _has_wrong_diacritic_device_head(raw_clean, "cua")
            bad_bom = _has_wrong_diacritic_device_head(raw_clean, "bom")
            bad_loa = _has_wrong_diacritic_device_head(raw_clean, "loa")
            bad_phong = _has_wrong_diacritic_device_head(raw_clean, "phong")
            for kw, dev_id in _DIRECT_DEVICE_PATTERNS_ACCENTED:
                if f" {kw} " in raw_padded:
                    if dev_id in ("living_room_light", "bedroom_light", "all_lights") and (bad_den or bad_phong):
                        return None
                    if dev_id == "alarm_siren" and bad_coi:
                        return None
                    if dev_id == "main_door" and bad_cua:
                        return None
                    if dev_id == "garden_pump" and bad_bom:
                        return None
                    if dev_id == "speaker_amp" and bad_loa:
                        return None
                    return dev_id
            # Never default bare 'đèn' to living_room_light when multiple lights exist in DEFAULT_DEVICES.
            if (
                not bad_cua
                and (
                    (
                        " cửa " in raw_padded
                        and not any(
                            bad_c in raw_padded
                            for bad_c in (
                                " cửa hàng ", " cửa tiệm ", " cửa hiệu ", " cửa sổ ",
                                " cửa miệng ", " cửa sông ", " cửa biển ",
                            )
                        )
                    )
                    or " cổng " in raw_padded
                )
            ):
                return "main_door"
            if not bad_bom and " bơm " in raw_padded:
                return "garden_pump"
            if not bad_coi and " còi " in raw_padded:
                return "alarm_siren"
            if not bad_loa and " loa " in raw_padded:
                return "speaker_amp"
            return None

    padded = f" {norm_clause} "
    for kw, dev_id in _DIRECT_DEVICE_PATTERNS:
        if f" {kw} " in padded:
            return dev_id
    if (
        " cua " in padded
        and not any(
            bad_c in padded
            for bad_c in (
                " cua hang ", " cua tiem ", " cua hieu ", " cua so ",
                " cua mieng ", " cua song ", " cua bien ",
            )
        )
    ) or " cong " in padded:
        return "main_door"
    if " bom " in padded:
        return "garden_pump"
    if " loa " in padded:
        return "speaker_amp"
    if " coi " in padded and not re.search(r"\b(?:len|cai|di|phat|chau|ba|ong|xem)\s+coi\b", norm_clause):
        return "alarm_siren"
    return None


_NON_VERB_NOUN_PHRASES: tuple[str, ...] = (
    "bao dong",
    "tu dong",
    "tieng dong",
    "chuyen dong",
    "hoat dong",
    "cong tac",
    "dong y",
    "dong thoi",
    "dong bo",
)

_DESCRIPTIVE_STATE_RE = re.compile(
    r"(?:"
    r"\b(?:đang|dang)\s+(?:chạy|chay|bật|bat|mở|mo|tắt|tat|đóng|dong|kêu|keu|sáng|sang|hoạt\s+động|hoat\s+dong)\b|"
    r"\b(?:kêu|keu|sáng|sang|chạy|chay)\s+(?:inh\s+ỏi|inh\s+oi|ầm\s+ĩ|am\s+i|mãi|mai|hoài|hoai|rồi|roi|quá|qua|lớn\s+quá|lon\s+qua|to\s+quá|to\s+qua)\b|"
    r"\b(?:đủ\s+nước|du\s+nuoc|tối\s+om|toi\s+om|tối\s+quá|toi\s+qua|sáng\s+quá|sang\s+qua|có\s+người\s+tới|co\s+nguoi\s+toi|có\s+khách|co\s+khach)\b"
    r")",
    re.IGNORECASE,
)


def _strip_non_verb_phrases(
    norm_clause: str,
    *,
    raw_clause: str | None = None,
    input_has_diacritics: bool | None = None,
) -> str:
    has_diac = (
        has_vi_diacritics(raw_clause)
        if (input_has_diacritics is None and raw_clause is not None)
        else bool(input_has_diacritics)
    )
    # Strip descriptive state clauses except inside alternative status questions
    padded_pre = f" {' '.join(norm_clause.split())} "
    if " hay " in padded_pre or " hoac " in padded_pre:
        cleaned = norm_clause
    else:
        cleaned = _DESCRIPTIVE_STATE_RE.sub(" ", norm_clause)
    padded = f" {' '.join(cleaned.split())} "
    for phrase in _NON_VERB_NOUN_PHRASES:
        padded = padded.replace(f" {phrase} ", " ")
    # Collapse compound stop-phrases (cease verb + activity verb) -> single OFF verb "ngung"
    _stop_act = r"(?:chay|hoat\s+dong|kich\s+hoat|bom|tuoi|keu|hu|phat|sang)"
    padded = re.sub(
        rf"\b(?:ngung|dung|tat|ngat|cup)\s+{_stop_act}\b",
        "ngung",
        padded,
    )
    if not has_diac or (raw_clause is not None and re.search(r"\bnghỉ\b", raw_clause.lower())):
        padded = re.sub(rf"\bnghi\s+{_stop_act}\b", "ngung", padded)
    if not has_diac or (raw_clause is not None and re.search(r"\bthôi\b", raw_clause.lower())):
        padded = re.sub(rf"\bthoi\s+{_stop_act}\b", "ngung", padded)
    # Only strip "tất cả" (all), NEVER "tắt cả" (turn off both)!
    if raw_clause is not None and has_diac:
        if "tất cả" in raw_clause.lower():
            padded = padded.replace(" tat ca ", " ")
    elif " tat ca " in padded and not re.search(r"\btat\s+ca\s+(?:hai|2)\b", padded):
        padded = padded.replace(" tat ca ", " ")
    # Only strip "đồng hồ" (clock), NEVER "đóng hộ" (close for me)!
    if raw_clause is not None and has_diac:
        if "đồng hồ" in raw_clause.lower():
            padded = padded.replace(" dong ho ", " ")
    elif " dong ho " in padded and not re.search(r"\bdong\s+ho\s+(?:cai\s+)?(?:cua|cong|toi|minh|ong|ba)\b", padded):
        padded = padded.replace(" dong ho ", " ")
    return " ".join(padded.split())


def _extract_clause_action(
    norm_clause: str,
    dev_id: str | None,
    *,
    raw_clause: str | None = None,
    input_has_diacritics: bool | None = None,
) -> str | None:
    action_clause = _strip_non_verb_phrases(
        norm_clause,
        raw_clause=raw_clause,
        input_has_diacritics=input_has_diacritics,
    )
    padded = f" {action_clause} "
    has_diac = (
        has_vi_diacritics(raw_clause)
        if (input_has_diacritics is None and raw_clause is not None)
        else bool(input_has_diacritics)
    )
    raw_low_act = (raw_clause or "").lower()
    # Protect 'khoi dong' (start up) so its second token 'dong' never collides with OFF verb 'dong' (close)
    padded = padded.replace(" khoi dong ", " __khoi_dong__ ")
    off_verb: str | None = None
    on_verb: str | None = None
    _ACCENTED_OFF_GUARD: dict[str, str] = {
        "tat": r"\btắt\b",
        "dong": r"\bđóng\b",
        "khoa": r"\b(?:khóa|khoá)\b",
        "chot": r"\bchốt\b",
        "khep": r"\bkhép\b",
        "gai": r"\bgài\b",
        "ngat": r"\bngắt\b",
        "dung": r"\bdừng\b",
        "cup": r"\bcúp\b",
        "dap": r"\bdập\b",
    }
    _ACCENTED_ON_GUARD: dict[str, str] = {
        "bat": r"\bbật\b",
        "mo": r"\bmở\b",
        "he mo": r"\bhé\s+mở\b",
        "chay": r"\bchạy\b",
    }
    for w in ("tat nguon", "ngat nguon", "cup nguon", "tat han", "dong kin", "tat", "dong", "khoa", "chot", "khep", "gai", "ngat", "dung", "ngung", "cup", "dap"):
        if f" {w} " in padded:
            guard_pat = _ACCENTED_OFF_GUARD.get(w)
            if guard_pat and has_diac and not re.search(guard_pat, raw_low_act):
                continue
            off_verb = w
            break
    for w in ("he mo", "kich hoat", "__khoi_dong__", "cap nguon", "mo nguon", "bat nguon", "cho chay", "cho sang", "lam sang", "cho hoat dong", "cho keu", "cho hu", "bat", "mo", "chay"):
        if f" {w} " in padded:
            guard_pat = _ACCENTED_ON_GUARD.get(w)
            if guard_pat and has_diac and not re.search(guard_pat, raw_low_act):
                continue
            on_verb = w
            break
    if on_verb is None and dev_id == "main_door":
        if has_diac and re.search(r"\bhé\b", raw_low_act):
            on_verb = "he mo"
        elif not has_diac and re.search(r"\bhe\s+(?:cua|cong)\b", padded):
            on_verb = "he mo"
    if on_verb is None and dev_id in ("speaker_amp", "alarm_siren") and " keu " in padded:
        on_verb = "keu"
    if on_verb is None and dev_id == "alarm_siren" and " hu " in padded and (not has_diac or re.search(r"\bhú\b", raw_low_act)):
        on_verb = "hu"
    # Conflicting ON and OFF verbs in a single clause -> ambiguous (never silently flip polarity!).
    if off_verb is not None and on_verb is not None:
        return None
    if off_verb is not None:
        return "close" if (dev_id == "main_door" or off_verb in ("dong", "dong kin", "khoa", "chot", "khep", "gai")) else "turn_off"
    if on_verb is not None:
        return "open" if (dev_id == "main_door" or on_verb in ("mo", "he mo")) else "turn_on"
    if (" tuoi cay " in padded or " tuoi vuon " in padded) and " may bom " not in padded and " bom " not in padded:
        return "turn_on"
    return None


def _canonicalize_device_action(dev_id: str, action: str) -> str:
    act = str(action or "").strip().lower()
    is_on = act in ("open", "turn_on")
    if dev_id == "main_door":
        return "open" if is_on else "close"
    return "turn_on" if is_on else "turn_off"


def _expand_direct_target(dev_id: str, action: str) -> list[dict[str, str]]:
    is_on = action in ("open", "turn_on")
    if dev_id == "all_lights":
        act = "turn_on" if is_on else "turn_off"
        return [
            {"device_id": "living_room_light", "action": act},
            {"device_id": "bedroom_light", "action": act},
        ]
    if dev_id == "all_devices":
        if is_on:
            return [
                {"device_id": "living_room_light", "action": "turn_on"},
                {"device_id": "bedroom_light", "action": "turn_on"},
                {"device_id": "garden_pump", "action": "turn_on"},
                {"device_id": "alarm_siren", "action": "turn_on"},
                {"device_id": "speaker_amp", "action": "turn_on"},
                {"device_id": "main_door", "action": "open"},
            ]
        return [
            {"device_id": "living_room_light", "action": "turn_off"},
            {"device_id": "bedroom_light", "action": "turn_off"},
            {"device_id": "garden_pump", "action": "turn_off"},
            {"device_id": "alarm_siren", "action": "turn_off"},
            {"device_id": "speaker_amp", "action": "turn_off"},
            {"device_id": "main_door", "action": "close"},
        ]
    return [{"device_id": dev_id, "action": _canonicalize_device_action(dev_id, action)}]


_NON_DIRECT_INTENT_CUES: tuple[str, ...] = (
    " dang mo hay dong ", " dang dong hay mo ", " dang mo hay da dong ", " dang mo hoac dong ", " dang dong hoac mo ",
    " dang bat hay tat ", " dang tat hay bat ", " dang bat hay da tat ", " dang bat hoac tat ", " dang tat hoac bat ",
    " co dang bat ", " co dang mo ",
    " co dang tat ", " co dang dong ", " trang thai ", " hen gio ", " dat hen gio ",
    " dat lich ", " dac lich ", " len lich ", " tao lich ", " lap lich ", " hen lich ",
    " sua lich ", " doi lich ", " xoa lich ", " huy lich ", " lich hen ", " lich trinh ", " lich tu dong ", " dinh ky ",
    " hang ngay ", " hang sang ", " hang chieu ", " hang toi ", " hang dem ", " hang tuan ",
    " ngay nao cung ", " lap lai ",
    " gio sang ", " gio trua ", " gio chieu ", " gio toi ", " gio dem ",
    " tao lenh ", " them lenh ", " luu lenh ", " dat lenh ", " dang ky lenh ", " cai lenh ", " thiet lap lenh ",
    " sua lenh ", " chinh sua lenh ", " doi lenh ", " cap nhat lenh ", " xoa lenh ", " huy lenh ", " go lenh ", " go bo lenh ",
    " tao khau lenh ", " them khau lenh ", " thiet lap khau lenh ", " cau lenh ", " tao ngu canh ", " them ngu canh ",
    " tao kich ban ", " them kich ban ", " tao bi danh ", " dat bi danh ",
    " luu cau ", " dat cau ", " gan cau ", " tao cau ", " noi dung la ", " cho thao tac ",
    " thanh bat ", " thanh tat ", " thanh mo ", " thanh dong ", " thanh lenh ",
    " lenh custom ", " lenh tuy chinh ", " tao luat ", " dat luat ", " them luat ",
    " dat quy tac ", " tao quy tac ", " quy tac ", " lien ket ",
    " xoa lien ket ", " huy lien ket ", " phut nua ", " giay nua ", " gio nua ",
    " reset ", " ri set ", " ri xet ", " re set ", " rexit ", " ri xep ", " khoi phuc ", " hoi phuc ", " cai dat goc ", " thiet lap lai ",
    " dat lai ", " khoi dong lai ", " ve mac dinh ", " mac dinh goc ", " xuat xuong ", " tinh trang ",
    " cau hinh ", " moi cai dat ", " tat ca cai dat ", " toan he thong ",
    " khi ", " neu ", " bat cu luc nao ", " moi luc ", " dat kho ", " tieng dong lon ",
    " tu bat ", " tu tat ", " bat theo ", " tat theo ", " phim tat ", " lenh rieng ", " lenh tat ",
    " lenh giong noi ", " ghi nho ",
)

_RECURRING_MOI_ACCENTED_RE = re.compile(r"\bmỗi\s+(?:ngày|sáng|trưa|chiều|tối|đêm|tuần)\b", re.IGNORECASE)
_RECURRING_MOI_UNACCENTED_RE = re.compile(r"\bmoi\s+(?:ngay|sang|trua|chieu|toi|dem|tuan)\b", re.IGNORECASE)

_MACRO_LIFECYCLE_GUARD_RE = re.compile(
    r"(?:^|\s)(?:tao|them|cai|dat|luu|thiet\s+lap|dang\s+ky|gan|ghi\s+nho|nho|"
    r"sua|chinh\s+sua|chinh|cap\s+nhat|doi|xoa(?:\s+(?:bo|di))?|go(?:\s+bo)?|dep(?:\s+bo)?|loai\s+bo|huy(?:\s+bo)?)\s+"
    r"(?:(?:giup|gium|dum|ho|cho)\s+(?:toi|minh|anh|chi|em|ban)\s+)?"
    r"(?:(?:mot|cai)\s+)?(?:khau\s+lenh|cau\s+lenh|lenh(?:\s+(?:moi|rieng|tat|tuy\s+chinh|custom|giong\s+noi|da\s+luu|cu))?|"
    r"kich\s+ban|bi\s+danh|phim\s+tat(?:\s+giong\s+noi)?|ngu\s+canh|scene|che\s+do)\b"
)

_CUSTOM_COMMAND_DIRECT_GUARD_RE = re.compile(
    r"(?:\b(?:che\s+do|lenh|khau\s+lenh|cau\s+lenh|cau|kich\s+ban|ngu\s+canh|bi\s+danh|phim\s+tat)\b.+\b(?:la|lam|thanh|de|gom|se|cho\s+thao\s+tac|noi\s+dung\s+la)\b|"
    r"\b(?:tao|them|luu|dat|gan|cai|thiet\s+lap|dang\s+ky|ghi\s+nho|nho)\b.+\b(?:de|gom|se)\s+(?:bat|tat|mo|dong|khoa|ngat|dung|ngung|doc|xem|kich\s+hoat|khoi\s+dong)\b|"
    r"\b(?:chinh\s+sua|go(?:\s+bo)?|dep(?:\s+bo)?|thiet\s+lap|ghi\s+nho)\s+(?:(?:giup|gium|dum|ho|cho)\s+(?:toi|minh|anh|chi|em|ban)\s+)?(?:(?:mot|cai)\s+)?(?:khau\s+lenh|cau\s+lenh|lenh|kich\s+ban|ngu\s+canh|bi\s+danh|phim\s+tat)\b|"
    r"\b(?:dua|dat|tra)\b.+\bve\s+(?:trang\s+thai\s+)?(?:mac\s+dinh|ban\s+dau|xuat\s+xuong|goc)\b|"
    r"\b(?:la|thanh)\s+(?:bat|tat|mo|dong|khoa|ngat|dung|ngung)\b|"
    r"\bcu\s+(?:mo|dong|bat|tat)\b.+\bla\b)"
)

_META_LINGUISTIC_NO_ACTION_RE = re.compile(
    r"(?:"
    # Quotation / metalinguistic mention / linguistic question frames
    r"\b(?:đang\s+|chỉ\s+(?:đang\s+)?)?(?:nói|đọc|nhắc|viết|gõ|lặp\s+lại|ví\s+dụ|thử\s+nói)\s+(?:lại\s+)?(?:từ|câu|chữ|cụm|lệnh)\b|"
    r"\b(?:dang\s+|chi\s+(?:dang\s+)?)?(?:noi|doc|nhac|viet|go|lap\s+lai|vi\s+du|thu\s+noi)\s+(?:lai\s+)?(?:tu|cau|chu|cum|lenh)\b|"
    r"\b(?:từ|câu|chữ|tu|cau|chu)\b.{1,40}\b(?:có\s+mấy|co\s+may|mấy\s+chữ|may\s+chu|nghĩa\s+là|nghia\s+la|viết\s+thế\s+nào|viet\s+the\s+nao)\b|"
    # Explicit disclaimer ("chưa nhờ", "không bảo", "không yêu cầu", "chưa kêu")
    r"\b(?:chưa|không|chua|khong)\s+(?:nhờ|bảo|yêu\s+cầu|kêu|ra\s+lệnh|nho|bao|yeu\s+cau|keu|ra\s+lenh)\b|"
    # Tag / confirmation questions
    r"\b(?:hay\s+gì|hay\s+gi|đúng\s+(?:không|chưa|rồi)|dung\s+(?:khong|chua|roi))\b|"
    r"^(?!.*\bđi\s+à\s*[.!]*$)(?:(?!(?:.*,|\b(?:làm\s+ơn|lam\s+on|giúp|giup|giùm|gium|dùm|dum|hộ|ho)\b)).)+\s(?:à|hả|ha|sao)\s*[.!?]*$"
    r")",
    re.IGNORECASE,
)

_PAST_TEMPORAL_MARKER_RE = re.compile(
    r"\b(?:hồi\s+(?:sáng|trưa|chiều|tối|nãy)|hoi\s+(?:sang|trua|chieu|toi|nay)|"
    r"lúc\s+(?:sáng|trưa|chiều|tối|nãy)|luc\s+(?:sang|trua|chieu|toi)|"
    r"ban\s+nãy|ban\s+nay|nãy\s+giờ|nay\s+gio|từ\s+(?:sáng|trưa|chiều|tối|hôm\s+qua|tối\s+qua)|"
    r"hôm\s+(?:qua|trước)|hom\s+(?:qua|truoc)|tuần\s+trước|tuan\s+truoc|tối\s+qua|toi\s+qua|"
    r"vừa\s+nãy|vua\s+nay|vừa\s+rồi(?:\s+đã)?|vua\s+roi(?:\s+da)?|"
    r"sáng\s+nay\s+đã|sang\s+nay\s+da|(?:tôi|mình|toi|minh|đã|da)\s+(?:quên|quen))\b",
    re.IGNORECASE,
)

_PAST_TENSE_ACTION_RE = re.compile(
    r"\b(?:đã|vừa(?:\s+mới)?|mới)\s+"
    r"(?:bật|tắt|mở|đóng|khóa|khoá|ngắt|cúp|dừng|ngừng|ngưng|dập|khép|kích\s+hoạt|khởi\s+động)\b",
    re.IGNORECASE,
)

_PAST_TENSE_ACTION_UNACCENTED_RE = re.compile(
    r"\b(?:da|vua(?:\s+moi)?|moi)\s+"
    r"(?:bat|tat|mo|dong|khoa|ngat|cup|dung|ngung|dap|khep|kich\s+hoat|khoi\s+dong)\b",
    re.IGNORECASE,
)

_LEADING_DEFERRAL_RE = re.compile(
    r"^(?:(?:ờ|à|ừ|ừm|thôi|này|ơi|o|a|u|um|thoi|nay|oi)\s*[,;:.!?…-]*\s*)*"
    r"(?:khoan(?:\s+(?:đã|hẵng|hãy|vội|da|hang|hay|voi))?|"
    r"(?:chờ|đợi|cho|doi)\s+(?:chút|đã|xíu|tý|tí|một\s+(?:chút|lát|xíu)|chut|da|xiu|ty|ti|mot\s+(?:chut|lat|xiu))|"
    r"từ\s+từ|tu\s+tu|để\s+sau|de\s+sau|lát\s+nữa|lat\s+nua|"
    r"đừng\s+vội|chưa\s+(?:cần|muốn)|chua\s+(?:can|muon))\b",
    re.IGNORECASE,
)

_KEEP_UNCHANGED_PHRASE_RE = re.compile(
    r"\b(?:cứ\s+để\s+nguyên|để\s+nguyên|giữ\s+nguyên|cứ\s+giữ\s+nguyên|"
    r"không\s+cần\s+đụng|đừng\s+đụng(?:\s+tới|\s+vào)?|không\s+đụng(?:\s+tới|\s+vào)?|"
    r"cu\s+de\s+nguyen|de\s+nguyen|giu\s+nguyen|cu\s+giu\s+nguyen|"
    r"khong\s+can\s+dung|dung\s+dung(?:\s+toi|\s+vao)?|khong\s+dung(?:\s+toi|\s+vao)?)\b",
    re.IGNORECASE,
)


def _is_status_question_vi(raw_text: str) -> bool:
    """True when the utterance is asking about device/sensor status rather than narrating a past event."""
    raw = _clean_space(raw_text).lower()
    if not raw:
        return False
    if "?" in raw:
        return True
    if re.search(r"\b(?:chưa|chua)\s*[.!?]*$", raw):
        return True
    if re.search(r"\b(?:bao\s+nhiêu|bao\s+nhieu|mấy\s+độ|may\s+do|thế\s+nào|the\s+nao|ra\s+sao|thì\s+sao|thi\s+sao)\b", raw):
        return True
    if re.search(r"\b(?:đang|dang)\b.+\b(?:hay|hoặc|hoac)\b", raw):
        return True
    if re.search(r"\b(?:có|co)\s+(?:đang|còn|bị|dang|con|bi)?\b.+\b(?:không|khong)\s*[.!?]*$", raw):
        return True
    return False


def _is_past_clause_vi(clause_raw: str, *, has_diac: bool) -> bool:
    """True if a single clause expresses a past-tense event or past temporal narration."""
    cl = _clean_space(clause_raw).lower()
    if not cl:
        return False
    if _PAST_TEMPORAL_MARKER_RE.search(cl):
        return True
    return bool(_PAST_TENSE_ACTION_RE.search(cl) if has_diac else _PAST_TENSE_ACTION_UNACCENTED_RE.search(cl))


def _is_past_tense_narration_without_imperative(raw_text: str) -> bool:
    """True for past-tense narration without a separate present imperative targeting a device (never blocks status questions)."""
    raw = _clean_space(raw_text).lower()
    if not raw or _is_status_question_vi(raw):
        return False
    has_diac = has_vi_diacritics(raw)
    has_past_act = bool(_PAST_TENSE_ACTION_RE.search(raw) if has_diac else _PAST_TENSE_ACTION_UNACCENTED_RE.search(raw))
    has_past_temp = bool(_PAST_TEMPORAL_MARKER_RE.search(raw))
    if not (has_past_act or has_past_temp):
        return False
    # Split into clauses and check whether ANY distinct clause is a present imperative targeting a device
    clauses = re.split(r"\s*(?:,|;|\.(?=\s|$)|\bnhưng\b|\bnhung\b|\bnên\b|\bnen\b|\bvậy\s+nên\b|\bthế\s+nên\b)\s*", raw)
    if len(clauses) >= 2:
        for cl in clauses:
            cl_s = cl.strip(" .!?…")
            if not cl_s:
                continue
            if _is_past_clause_vi(cl_s, has_diac=has_diac):
                continue
            if (
                _CLAUSE_NEGATED_OR_KEEP_RE.search(cl_s)
                or _NEGATED_OR_RHETORICAL_DIRECT_RE.search(cl_s)
                or _LEADING_DEFERRAL_RE.match(cl_s)
            ):
                continue
            cl_norm = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(cl_s)).split())
            dev_c = _extract_clause_device(cl_norm, raw_clause=cl_s, input_has_diacritics=has_diac)
            act_c = _extract_clause_action(cl_norm, dev_c, raw_clause=cl_s, input_has_diacritics=has_diac)
            if dev_c is not None and act_c is not None:
                return False
    return True


def is_no_action_safety_blocked_vi(raw_text: str) -> bool:
    """Single source of truth for deferral, hesitation, negation, keep-unchanged, and past-tense safety blocks."""
    raw = _clean_space(raw_text).lower()
    if not raw:
        return False
    resolved = _resolve_self_correction_vi(raw)
    if _META_LINGUISTIC_NO_ACTION_RE.search(resolved):
        return True
    if _is_past_tense_narration_without_imperative(resolved):
        return True
    if _LEADING_DEFERRAL_RE.match(resolved):
        return True
    if _KEEP_UNCHANGED_PHRASE_RE.search(resolved) and not re.search(r"(?:,|;|\bnhưng\b|\bcòn\b|\bnhung\b|\bcon\b)", resolved):
        return True
    if _NEGATED_OR_RHETORICAL_DIRECT_RE.search(resolved) and not re.search(r"(?:,|;|\bnhưng\b|\bcòn\b|\bnhung\b|\bcon\b)", resolved):
        return True
    return False

_SELF_CORRECTION_RE = re.compile(
    r"^(?P<before>.+?)\s*(?:(?:\.{2,}|…)\s*(?:à|ờ)\s+(?=(?:bật|tắt|mở|đóng|bat|tat|mo|dong)\b)|"
    r"(?:[.,…;!?-]+\s*|\s+)(?:à\s+không|a\s+khong|à\s+thôi|a\s+thoi|ờ\s+thôi|o\s+thoi|"
    r"thôi\s+(?:đổi|chuyển)\s+(?:sang|thành)|thoi\s+(?:doi|chuyen)\s+(?:sang|thanh)|"
    r"à\s+nhầm|a\s+nham|nhầm\s+rồi|nham\s+roi|nhầm|nham|ý\s+mình\s+là|ý\s+tôi\s+là)\s*[,;:.!?…-]*\s*)(?P<after>.+)$",
    re.IGNORECASE,
)

_CLAUSE_NEGATED_OR_KEEP_RE = re.compile(
    r"(?:(?:^|\s)(?:"
    r"đừng(?:\s+(?:có|vội|bao\s+giờ|đụng|chạm|tắt|bật|mở|đóng))?|"
    r"chớ\b|"
    r"không(?:\s+(?:phải|cần|muốn|được|nên|bảo|nhờ|đụng|bật|tắt|mở|đóng|khóa|ngắt|dừng|ngừng|ngưng|cúp|dập|chạy|kích\s+hoạt|khởi\s+động))|"
    r"khong(?:\s+(?:phai|can|muon|duoc|nen|bao|nho|dung|bat|tat|mo|dong|khoa|ngat|ngung|cup|dap|chay|kich\s+hoat|khoi\s+dong))|"
    r"chưa\s+(?:cần|muốn|vội|đâu)|chua\s+(?:can|muon|voi|dau)|"
    r"khoan(?:\s+(?:đã|hẵng|hãy|vội|da|hang|hay|voi))?\b|"
    r"(?:chờ|đợi|cho|doi)\s+(?:chút|đã|xíu|một\s+(?:chút|lát|xíu)|tý|tí|chut|da|xiu|mot\s+(?:chut|lat|xiu))\b|"
    r"từ\s+từ\b|tu\s+tu\b|để\s+sau\b|de\s+sau\b|lát\s+nữa\b|lat\s+nua\b|"
    r"khỏi\s+cần|khoi\s+can|"
    r"thôi\s+(?:không|khỏi|bỏ|hủy|huỷ|đừng)\b|thoi\s+(?:khong|khoi|bo|huy|dung)\b|"
    r"hủy(?:\s+bỏ)?\b|huỷ(?:\s+bỏ)?\b|bỏ\s+đi\b|"
    r"cứ\s+để\s+nguyên|để\s+nguyên|giữ\s+nguyên|cứ\s+giữ\s+nguyên|cu\s+de\s+nguyen|de\s+nguyen|giu\s+nguyen|cu\s+giu\s+nguyen|"
    r"đừng\s+đụng(?:\s+tới|\s+vào)?|không\s+cần\s+đụng|không\s+đụng(?:\s+tới|\s+vào)?|dung\s+dung(?:\s+toi|\s+vao)?|khong\s+can\s+dung|"
    r"đúng\s+(?:rồi|không|chưa|nhỉ|nhé|ạ)\b"
    r")|^\s*(?:(?:ờ|à|ừ|thế|vậy|o|a|u|the|vay)\s+)?(?:thôi|thoi)\b(?!\s+(?:chạy|chay|hoạt\s+động|hoat\s+dong|bơm|bom|tưới|tuoi|kêu|keu|hú|hu|phát|phat|sáng|sang)\b))",
    re.IGNORECASE,
)

_COUNTDOWN_OR_CLOCK_GUARD_RE = re.compile(
    r"(?:\bsau\s+(?:\d+|(?:mot|hai|ba|bon|nam|sau|bay|bai|tam|chin|muoi|nua)\s+(?:giay|phut|gio|tieng))\b|"
    r"\b(?:giay|phut|tieng)\s+nua\b|"
    r"\b\d+\s*(?:giay|phut|tieng)\b|"
    r"\b(?:luc|vao\s+luc)\s+(?:\d+|mot|hai|ba|bon|nam|sau|bay|bai|tam|chin|muoi)\s*(?:gio|h)\b|"
    r"\b\d{1,2}\s*(?:gio|h)\s*\d{0,2}\b|\b\d{1,2}:\d{2}\b)"
)

_CONDITIONAL_THI_GUARD_RE = re.compile(r"(?<!\broi)(?<!\bo)(?<!\ba)(?<!\bum)\s+thi\s+")

_EXPLICIT_OFF_VERBS: frozenset[str] = frozenset({
    "tat", "dong", "khoa", "chot", "khep", "gai", "ngung", "dung", "ngat", "cup",
})
_EXPLICIT_ON_VERBS: frozenset[str] = frozenset({
    "bat", "mo", "khoi", "kich", "cap",
})

_FUZZY_BLOCKED_QUERY_CUES: tuple[str, ...] = (
    " bao nhieu ", " the nao ", " la gi ", " cam bien ", " nhiet do ",
    " do am ", " thanh vien ", " tai khoan ", " quyen ", " lich ", " hen ",
    " reset ", " khoi phuc ", " xoa ", " huy ", " dat lai ", " thiet lap ",
)


def _vi_phonetic_skeleton(text: str) -> str:
    """Fold Vietnamese regional consonant mergers (d/gi/r/v, tr/ch, s/x, kh/h) for phonetic matching."""
    norm = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(str(text or "").lower())).split())
    if not norm:
        return ""
    folded: list[str] = []
    for tok in norm.split():
        if tok.startswith("ngh"):
            tok = "ng" + tok[3:]
        elif tok.startswith("gh"):
            tok = "g" + tok[2:]
        elif tok.startswith("kh"):
            tok = "h" + tok[2:]
        elif tok.startswith("tr") or tok.startswith("ch"):
            tok = "c" + tok[2:]
        elif tok.startswith("gi"):
            tok = "z" + tok[2:]
        elif tok.startswith(("d", "r", "v")):
            tok = "z" + tok[1:]
        elif tok.startswith("x"):
            tok = "s" + tok[1:]
        elif tok.startswith(("k", "q", "c")):
            tok = "k" + tok[1:]
        folded.append(tok)
    return " ".join(folded)


def _build_registry_canonical_commands() -> tuple[tuple[str, str, str, str, str, int], ...]:
    """Derive canonical direct command vocabulary dynamically from DEFAULT_DEVICES registry."""
    extra_aliases: dict[str, tuple[str, ...]] = {
        "main_door": ("cua chinh", "cua"),
        "garden_pump": ("may bom tuoi cay", "may bom"),
        "alarm_siren": ("coi bao dong",),
        "speaker_amp": ("nguon mach loa", "mach loa"),
        "living_room_light": ("den phong khach",),
        "bedroom_light": ("den phong ngu",),
    }
    rows: list[tuple[str, str, str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for dev_id, info in DEFAULT_DEVICES.items():
        raw_name = str(info.get("name") or dev_id)
        clean_name = " ".join(
            re.sub(r"\([^)]*\)", " ", strip_vi_accents(raw_name.lower())).split()
        )
        clean_name = re.sub(r"[^a-z0-9\s]+", " ", clean_name).strip()
        names = [clean_name] if clean_name else []
        for al in extra_aliases.get(dev_id, ()):
            if al not in names:
                names.append(al)
        if dev_id == "main_door":
            verb_specs = (("mo", "on", "open"), ("dong", "off", "close"), ("khoa", "off", "close"))
        else:
            verb_specs = (("bat", "on", "turn_on"), ("tat", "off", "turn_off"))
        for nm in names:
            for v, pol, act in verb_specs:
                ph = f"{v} {nm}".strip()
                if (ph, dev_id) not in seen_pairs:
                    seen_pairs.add((ph, dev_id))
                    rows.append((ph, pol, dev_id, act))
    # Registry group quantifiers (derived when >1 light / >1 device exist)
    light_ids = [d for d in DEFAULT_DEVICES if "light" in d]
    if len(light_ids) > 1:
        rows.append(("bat tat ca den", "on", "all_lights", "turn_on"))
        rows.append(("tat tat ca den", "off", "all_lights", "turn_off"))
    if len(DEFAULT_DEVICES) > 1:
        rows.append(("tat tat ca thiet bi", "off", "all_devices", "turn_off"))
    return tuple(
        (phrase, pol, dev, act, _vi_phonetic_skeleton(phrase), len(phrase.split()))
        for phrase, pol, dev, act in rows
    )


_CANONICAL_DIRECT_COMMANDS: tuple[tuple[str, str, str, str, str, int], ...] = _build_registry_canonical_commands()


def _match_constrained_direct_command_vi(norm_text: str, *, raw_text: str = "") -> list[dict[str, str]]:
    """High-precision registry-derived phonetic + edit-distance matcher over canonical Vietnamese device commands.

    Safety invariants:
    - Never runs on foreign/nonsense, unsupported devices, questions, wrong-diacritic near-misses, or destructive/automation cues.
    - Requires an explicit ON or OFF verb token and strictly locks polarity (never flips ON<->OFF, never guesses bare nouns).
    - Requires score >= 86, token-count compatibility (|diff| <= 1), and margin >= 6 over the runner-up target.
    """
    if not norm_text or "?" in norm_text:
        return []
    src = raw_text or norm_text
    if _has_wrong_diacritic_light_word(src):
        return []
    clean = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(norm_text.lower())).split())
    if not clean:
        return []
    padded = f" {clean} "
    # Never fuzzy-match bare 'den' without an explicit room or multi-light quantifier (accented or unaccented)
    if " den " in padded and not any(
        k in padded for k in (" phong khach ", " khach ", " phong ngu ", " ngu ", " buong ", " tat ca ", " toan bo ", " het ", " ca hai ", " hai ")
    ):
        return []
    if _UNSUPPORTED_DEVICE_RE.search(padded):
        return []
    if any(k in padded for k in _FUZZY_BLOCKED_QUERY_CUES):
        return []

    tokens = clean.split()
    if len(tokens) < 2 or len(tokens) > 7:
        return []

    verb_tokens = set(_strip_non_verb_phrases(clean, raw_clause=src, input_has_diacritics=has_vi_diacritics(src)).split())
    has_off = bool(verb_tokens & _EXPLICIT_OFF_VERBS)
    has_on = bool(verb_tokens & _EXPLICIT_ON_VERBS)
    if has_off == has_on:
        # Either no explicit verb (ambiguous bare noun) or conflicting polarities: never guess.
        return []
    required_polarity = "off" if has_off else "on"

    phon_in = _vi_phonetic_skeleton(clean)
    bad_den = _has_wrong_diacritic_device_head(src, "den") or _has_wrong_diacritic_device_head(src, "phong")
    bad_cua = _has_wrong_diacritic_device_head(src, "cua")
    bad_coi = _has_wrong_diacritic_device_head(src, "coi")
    bad_bom = _has_wrong_diacritic_device_head(src, "bom")
    bad_loa = _has_wrong_diacritic_device_head(src, "loa")

    best_by_target: dict[tuple[str, str], float] = {}
    for phrase, pol, dev, act, cand_phon, cand_tok_n in _CANONICAL_DIRECT_COMMANDS:
        if pol != required_polarity:
            continue
        if dev in ("living_room_light", "bedroom_light", "all_lights") and bad_den:
            continue
        if dev == "main_door" and bad_cua:
            continue
        if dev == "alarm_siren" and bad_coi:
            continue
        if dev == "garden_pump" and bad_bom:
            continue
        if dev == "speaker_amp" and bad_loa:
            continue
        if abs(len(tokens) - cand_tok_n) > 1:
            continue
        score = max(_fuzzy_ratio(clean, phrase), _fuzzy_ratio(phon_in, cand_phon))
        key = (dev, act)
        prev = best_by_target.get(key)
        if prev is None or score > prev:
            best_by_target[key] = score

    if not best_by_target:
        return []

    ranked = sorted(best_by_target.items(), key=lambda kv: kv[1], reverse=True)
    (best_dev, best_act), best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    if best_score < 86.0 or (best_score - second_score) < 6.0:
        return []
    return _expand_direct_target(best_dev, best_act)


def _resolve_self_correction_vi(text: str) -> str:
    """Resolve spoken self-corrections (<initial clause> <correction cue> <replacement clause>)."""
    m = _SELF_CORRECTION_RE.match(text.strip())
    if not m:
        return text
    before = m.group("before").strip()
    after = m.group("after").strip()
    if not after:
        return text
    # If correction already contains its own verb, replace entirely with the correction
    after_norm = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(after.lower())).split())
    after_has_diac = has_vi_diacritics(after)
    if _extract_clause_action(after_norm, None, raw_clause=after, input_has_diacritics=after_has_diac) is not None:
        return after
    # If correction is a replacement room ("phòng khách" / "phòng ngủ"), substitute room in light command
    if re.search(r"\b(?:phòng\s+khách|phòng\s+ngủ|phong\s+khach|phong\s+ngu)\b", after, flags=re.IGNORECASE):
        replaced = re.sub(
            r"\b(?:phòng\s+khách|phòng\s+ngủ|phong\s+khach|phong\s+ngu)\b",
            after.strip(" .,!?"),
            before,
            flags=re.IGNORECASE,
        )
        if replaced != before:
            return replaced
    return after


def parse_direct_device_intents_vi(
    text: str,
    *,
    word_mappings: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """Parse single or multi-device direct Vietnamese commands; never guess on ambiguous/wrong-diacritic/foreign input."""
    raw = _clean_space(text)
    if not raw:
        return []

    is_bad, _ = is_foreign_or_nonsense_input(raw)
    if is_bad:
        return []

    mapped = raw.lower()
    if word_mappings:
        for custom_word, target_val in word_mappings.items():
            cw = str(custom_word or "").lower().strip()
            tv = str(target_val or "").lower().strip()
            if cw and cw in mapped:
                mapped = mapped.replace(cw, f" {tv} ")

    # Never execute meta-linguistic mentions, quotes, past-tense narrations, or word-count questions
    if _META_LINGUISTIC_NO_ACTION_RE.search(mapped):
        return []
    if _is_past_tense_narration_without_imperative(mapped):
        return []
    # Never execute rhetorical/meta/status questions (device commands are imperatives)
    if "?" in mapped or _is_status_question_vi(mapped):
        return []

    # Resolve spoken self-corrections BEFORE custom-command and negation guards
    resolved_text = _resolve_self_correction_vi(mapped)

    # Leading deferral / hesitation governs the utterance -> block immediate execution
    if _LEADING_DEFERRAL_RE.match(resolved_text):
        return []

    # Preserve ambient-air phrase before checking non-direct cues so it never collides with conditional cues
    mapped_no_air = re.sub(r"\b(?:không\s+khí|khong\s+khi)\b", " khong_khi ", resolved_text)
    norm_raw = f" {' '.join(re.sub(r'[^a-z0-9_\s]+', ' ', strip_vi_accents(mapped_no_air)).split())} "
    # Never guess a supported device when an unsupported appliance is mentioned (preserve clause punctuation boundaries!)
    norm_punct_safe = f" {' '.join(re.sub(r'([,;.])', r' \1 ', re.sub(r'[^a-z0-9_,;.\s]+', ' ', strip_vi_accents(resolved_text.lower()))).split())} "
    if _UNSUPPORTED_DEVICE_RE.search(norm_punct_safe):
        return []

    # Never execute direct device control on save/backup/macro-lifecycle/conditional utterances
    if _MACRO_LIFECYCLE_GUARD_RE.search(norm_raw):
        return []

    # Check non-direct cues (timers, schedules, custom CRUD, resets, conditional rules)
    # Allow contrastive topic-comment structures and leading discourse fillers
    has_contrastive_or_topic_thi = bool(
        re.search(r"\bcòn\b.+\bthì\b|\bcon\b.+\bthi\b", resolved_text)
        or re.search(
            r"(?:^|[,;.]|\bvà\b|\bva\b|\brồi\b|\broi\b|\bnhưng\b|\bnhung\b)\s*(?:phòng\s+(?:khách|ngủ)|phong\s+(?:khach|ngu)|"
            r"(?:ngoài\s+)?vườn|(?:ngoai\s+)?vuon|"
            r"đèn\s+phòng\s+(?:khách|ngủ)|den\s+phong\s+(?:khach|ngu)|"
            r"cửa\s+chính|cua\s+chinh|máy\s+bơm(?:\s+tưới\s+cây)?|may\s+bom(?:\s+tuoi\s+cay)?|bơm|bom|"
            r"còi\s+báo\s+động|coi\s+bao\s+dong|(?:nguồn\s+)?(?:mạch\s+)?loa(?:\s+chuông)?|(?:nguon\s+)?(?:mach\s+)?loa(?:\s+chuong)?)\s+"
            r"(?:thì|thi)\s+",
            resolved_text,
            flags=re.IGNORECASE,
        )
    )
    norm_for_thi = re.sub(r"^\s*(?:o|a|um|u)\s+thi\b", "", norm_raw.strip())
    norm_for_thi = f" {norm_for_thi} "
    input_has_diac = has_vi_diacritics(resolved_text)
    has_recurring_moi = bool(
        _RECURRING_MOI_ACCENTED_RE.search(resolved_text)
        if input_has_diac
        else _RECURRING_MOI_UNACCENTED_RE.search(norm_raw)
    )
    has_conditional_he = bool(
        re.search(r"\bhễ\b", resolved_text)
        if input_has_diac
        else (re.search(r"\bhe\s+(?!thong\b|mo\b|cua\b)\S+", norm_raw.strip()) and (" thi " in norm_raw or " la " in norm_raw))
    )
    if (
        any(k in norm_raw for k in _NON_DIRECT_INTENT_CUES)
        or has_recurring_moi
        or has_conditional_he
        or _COUNTDOWN_OR_CLOCK_GUARD_RE.search(norm_raw)
        or (not has_contrastive_or_topic_thi and _CONDITIONAL_THI_GUARD_RE.search(norm_for_thi))
        or _CUSTOM_COMMAND_DIRECT_GUARD_RE.search(norm_raw)
    ):
        return []

    # Extract explicit exclusions across ALL 6 registry devices (set-difference connectors)
    excluded_devs: set[str] = set()
    m_excl_re = re.compile(
        r"(?:,?\s*)?(?:chứ\s+)?(?:không\s+phải|khong\s+phai|ngoại\s+trừ|ngoai\s+tru|trừ|tru)\s+"
        r"([^,;.!?]+?)(?=(?:,|;|\.|!|\?|$|\bvà\b|\bva\b|\bcòn\b|\bcon\b))",
        flags=re.IGNORECASE,
    )

    def _collect_exclusion(m_ex: re.Match[str]) -> str:
        ex_raw = m_ex.group(1).strip()
        ex_norm = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(ex_raw.lower())).split())
        ex_dev = _extract_clause_device(ex_norm, raw_clause=ex_raw, input_has_diacritics=input_has_diac)
        if ex_dev is None:
            if ex_norm in ("phong khach", "khach"):
                ex_dev = "living_room_light"
            elif ex_norm in ("phong ngu", "ngu", "buong"):
                ex_dev = "bedroom_light"
        if ex_dev == "all_lights":
            excluded_devs.update(("living_room_light", "bedroom_light"))
        elif ex_dev is not None:
            excluded_devs.add(ex_dev)
        return ""

    resolved_text = m_excl_re.sub(_collect_exclusion, resolved_text).strip()

    # Insert clause breaks before trailing negated/keep-unchanged clauses when commas are absent
    seg_prep = re.sub(
        r"\b(chính|chinh|khách|khach|ngủ|ngu|động|dong|vườn|vuon|cây|cay|loa|chuông|chuong|đèn|den|cửa|cua|bơm|bom|còi|coi|thôi|thoi)\s+"
        r"(?=(?:(?:đừng|chớ)\s+(?:bật|tắt|mở|đóng|khóa|bat|tat|mo|dong|khoa)|"
        r"không\s+(?:bật|tắt|mở|đóng|phải|cần)|chứ\s+không|"
        r"(?:đèn|cửa|loa|còi|bơm|máy\s+bơm)[^,;.!?]{0,30}(?:đừng\s+đụng|cứ\s+để\s+nguyên|để\s+nguyên|giữ\s+nguyên)))",
        r"\1 , ",
        resolved_text,
        flags=re.IGNORECASE,
    )

    # Split into punctuation/sentence/contrast segments so negated/keep-unchanged clauses exclude only their target device;
    # a pure utterance-wide cancellation/deferral clause with no target device aborts the whole utterance.
    pre_segments = re.split(r"\s*(?:,|;|\.{2,}|…|\.(?=\s)|\bchứ\b|\bnhưng\b)\s*", seg_prep, flags=re.IGNORECASE)
    kept_segments: list[str] = []
    for seg in pre_segments:
        seg_s = seg.strip(" .!?…")
        if not seg_s:
            continue
        if _CLAUSE_NEGATED_OR_KEEP_RE.search(seg_s) or _NEGATED_OR_RHETORICAL_DIRECT_RE.search(seg_s):
            seg_norm = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(seg_s.lower())).split())
            neg_dev = _extract_clause_device(seg_norm, raw_clause=seg_s, input_has_diacritics=input_has_diac)
            if neg_dev == "all_lights":
                excluded_devs.update(("living_room_light", "bedroom_light"))
            elif neg_dev == "all_devices":
                return []
            elif neg_dev is not None:
                excluded_devs.add(neg_dev)
            elif re.fullmatch(
                r"(?:(?:a|o|um|u)\s+)?(?:khoan(?:\s+(?:da|hang|hay|voi))?|"
                r"(?:cho|doi)\s+(?:chut|da|xiu|mot\s+(?:chut|lat|xiu)|ty|ti)|"
                r"tu\s+tu(?:\s+da)?|de\s+sau|lat\s+nua|"
                r"dung\s+voi|chua\s+(?:can|muon)(?:\s+dau)?|"
                r"thoi(?:\s+(?:khong|khoi|bo|huy|dung|di|nhe|nha|lam))?|"
                r"huy(?:\s+bo)?(?:\s+(?:di|nhe|nha))?|bo\s+di|"
                r"(?:dung|khong)\s+(?:lam|thuc\s+hien|mo|dong|bat|tat|can)(?:\s+(?:nua|di|dau|nhe|nha|voi))?)"
                r"(?:\s+(?:da|nhe|nha|a|di|day|em|ban|anh|chi|toi|minh|lai))*",
                seg_norm,
            ):
                # Pure utterance-wide cancellation/deferral with no distinct object noun
                return []
            continue
        kept_segments.append(seg_s)

    if not kept_segments:
        return []

    filtered_text = " , ".join(kept_segments)
    # Strip trailing restrictive particle 'thôi' on already-validated positive clauses
    filtered_text = re.sub(r"\b(?:thôi|thoi)\b(?=\s*(?:,|;|$))", "", filtered_text, flags=re.IGNORECASE).strip()
    normalized = normalize_vietnamese_utterance(filtered_text)
    if not normalized:
        return []

    # Normalize multi-device 'cả ... lẫn ...' connector before splitting
    split_prep = re.sub(r"\bcả\s+(?=.+\blẫn\b)", "", normalized, flags=re.IGNORECASE)
    if not input_has_diac:
        split_prep = re.sub(r"\bca\s+(?=.+\blan\b)", "", split_prep, flags=re.IGNORECASE)

    # Split multi-device sentences on conjunctions / punctuation, and between adjacent verb-device clauses
    split_prep = re.sub(
        r"\b(khách|khach|ngủ|ngu|chính|chinh|cửa|cua|cổng|cong|bơm|bom|cây|cay|vườn|vuon|còi|coi|động|dong|loa|đèn|den|bị|bi)"
        r"(?:\s+(?:lại|lai|ra|lên|len|xuống|xuong|đi|di|thôi|thoi|kín|kin|chặt|chat|rộng|rong|sáng|sang|hẳn|han|hết|het)){0,2}\s+"
        r"(?=(?:bật|tắt|mở|đóng|khóa|khoá|khép|chốt|gài|hé(?:\s+mở)?|ngắt|ngưng|ngừng|dừng|cúp|dập|kích\s+hoạt|khởi\s+động|cấp\s+nguồn|"
        r"bat|tat|mo|dong|khoa|khep|chot|gai|he\s+mo|ngat|ngung|dung|cup|dap|kich\s+hoat|khoi\s+dong|cap\s+nguon)\s+"
        r"(?:(?:cái|cai)\s+)?(?:đèn|den|cửa|cua|cổng|cong|máy\s+bơm|may\s+bom|bơm|bom|còi|coi|nguồn|nguon|loa|tất\s+cả|tat\s+ca|toàn\s+bộ|toan\s+bo|hết|het)\b)",
        r"\1 , ",
        split_prep,
        flags=re.IGNORECASE,
    )
    # Mark contrastive clauses so a clipped contrastive clause never inherits opposite polarity
    split_prep = re.sub(r"\bcòn\b", " , __contrast__ ", split_prep, flags=re.IGNORECASE)
    clauses = re.split(
        r"\s*(?:,|;|\bvà\b|\bva\b|\blẫn\b|\blan\b|\bsau\s+đó\b|\bsau\s+do\b|\bđồng\s+thời\b|\bdong\s+thoi\b|"
        r"\bcùng\s+lúc\b|\bcung\s+luc\b|\btiếp\s+theo\b|\btiep\s+theo\b|\btiếp\s+đến\b|\btiep\s+den\b|"
        r"\bkế\s+tiếp\b|\bke\s+tiep\b|\bsau\s+cùng\b|\bsau\s+cung\b|\bcuối\s+cùng\b|\bcuoi\s+cung\b|"
        r"\bkèm(?:\s+theo)?\b|\bkem(?:\s+theo)?\b|\brồi\s+thì\b|\broi\s+thi\b|\brồi\b|\broi\b|\bnên\b|\bnen\b|"
        r"\bcùng\s+với\b|\bcung\s+voi\b|\bcùng\b|\bcung\b|\bxong\b|\bvới\b|\bvoi\b)\s*",
        split_prep,
        flags=re.IGNORECASE,
    )

    # Pre-parse clauses so topic-comment, past-context, and descriptive-context + imperative structures resolve cleanly
    _DESCRIPTIVE_CONTEXT_PREFIX_RE = re.compile(
        r"(?:\b(?:đủ\s+nước|du\s+nuoc|hết\s+nước|het\s+nuoc|tối\s+om|toi\s+om|tối\s+quá|toi\s+qua|"
        r"sáng\s+quá|sang\s+qua|nóng\s+quá|nong\s+qua|lạnh\s+quá|lanh\s+qua|"
        r"khô\s+quá|kho\s+qua|khô\s+rồi|kho\s+roi|khô\s+hết|kho\s+het|đất\s+khô|dat\s+kho|"
        r"héo|heo|mất\s+điện|mat\s+dien|có\s+lại|co\s+lai|tiếng\s+động|tieng\s+dong|"
        r"có\s+người|co\s+nguoi|có\s+khách|co\s+khach|ngoài\s+cổng|ngoai\s+cong|ngoài\s+sân|ngoai\s+san|"
        r"trời\s+tối|troi\s+toi|trời\s+sáng|troi\s+sang|đang\s+chạy|dang\s+chay|"
        r"đang\s+bật|dang\s+bat|đang\s+mở|dang\s+mo|kêu\s+inh|keu\s+inh|kêu\s+ầm|keu\s+am|"
        r"ồn\s+quá|on\s+qua|ồn\s+ào|on\s+ao)\b)",
        re.IGNORECASE,
    )
    # Expand any single clause that still contains multiple verb+device commands separated only by spaces/particles
    # Only split when the prefix before the second verb ALREADY names a device (preserves room topic-comment clauses)!
    expanded_clauses: list[str] = []
    _MULTI_VERB_SPLIT_RE = re.compile(
        r"\s+(?=(?:bật|tắt|mở|đóng|khóa|khoá|khép|chốt|gài|hé(?:\s+mở)?|ngắt|ngưng|ngừng|dừng|cúp|dập|kích\s+hoạt|khởi\s+động|cấp\s+nguồn|"
        r"bat|tat|mo|dong|khoa|khep|chot|gai|he\s+mo|ngat|ngung|dung|cup|dap|kich\s+hoat|khoi\s+dong|cap\s+nguon)\s+"
        r"(?:(?:cái|cai)\s+)?(?:đèn|den|cửa|cua|cổng|cong|máy\s+bơm|may\s+bom|bơm|bom|còi|coi|nguồn|nguon|loa|tất\s+cả|tat\s+ca|toàn\s+bộ|toan\s+bo|hết|het)\b)",
        flags=re.IGNORECASE,
    )
    for cl in clauses:
        parts_sub = _MULTI_VERB_SPLIT_RE.split(cl)
        if len(parts_sub) >= 2:
            p0_raw = parts_sub[0].replace("__contrast__", " ").strip(" .!?…")
            p0_norm = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(p0_raw.lower())).split())
            if p0_norm and _extract_clause_device(p0_norm, raw_clause=p0_raw, input_has_diacritics=input_has_diac) is not None:
                for ps in parts_sub:
                    if ps.strip():
                        expanded_clauses.append(ps)
                continue
        expanded_clauses.append(cl)
    clauses = expanded_clauses

    parsed_clauses: list[tuple[str, str, str | None, str | None, bool]] = []
    for cl in clauses:
        is_contrast = "__contrast__" in cl
        cl_raw = cl.replace("__contrast__", " ").strip(" .!?…")
        cl_norm = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(cl_raw.lower())).split())
        if not cl_norm:
            continue
        # Skip past-tense narration/context clauses (we already verified a separate present imperative exists)
        if _is_past_clause_vi(cl_raw, has_diac=input_has_diac):
            parsed_clauses.append((cl_raw, cl_norm, None, None, is_contrast))
            continue
        # Handle inline room/garden topic-comment: <room|garden> <topic marker> <action + device>
        m_room_topic = re.match(
            r"^(phòng\s+khách|phòng\s+ngủ|phong\s+khach|phong\s+ngu|(?:ngoài\s+)?vườn|(?:ngoai\s+)?vuon)\s+(?:thì|thi)\s+(.+)$",
            cl_raw,
            flags=re.IGNORECASE,
        )
        if m_room_topic:
            r_raw = m_room_topic.group(1).strip()
            r_norm = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(r_raw.lower())).split())
            body_raw = m_room_topic.group(2).strip()
            body_norm = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(body_raw.lower())).split())
            body_dev = _extract_clause_device(body_norm, raw_clause=body_raw, input_has_diacritics=input_has_diac)
            if body_dev is None and (" den " in f" {body_norm} " or " đèn " in f" {body_raw.lower()} "):
                if "khach" in r_norm:
                    body_dev = "living_room_light"
                elif "ngu" in r_norm:
                    body_dev = "bedroom_light"
            if body_dev is None and "vuon" in r_norm and (" bom " in f" {body_norm} " or " tuoi " in f" {body_norm} "):
                body_dev = "garden_pump"
            body_act = _extract_clause_action(body_norm, body_dev, raw_clause=body_raw, input_has_diacritics=input_has_diac)
            parsed_clauses.append((cl_raw, cl_norm, body_dev, body_act, is_contrast))
            continue

        # Strip pure descriptive/context clauses before device extraction so location nouns do not emit a verb-less device topic
        if _DESCRIPTIVE_CONTEXT_PREFIX_RE.search(cl_raw):
            cl_dev_chk = _extract_clause_device(cl_norm, raw_clause=cl_raw, input_has_diacritics=input_has_diac)
            cl_act_chk = _extract_clause_action(cl_norm, cl_dev_chk, raw_clause=cl_raw, input_has_diacritics=input_has_diac)
            if cl_act_chk is None and re.search(
                r"\b(?:có\s+người|co\s+nguoi|có\s+khách|co\s+khach|tối|toi|đủ\s+nước|du\s+nuoc|"
                r"ồn\s+quá|on\s+qua|ồn\s+ào|on\s+ao|khô\s+quá|kho\s+qua|khô\s+rồi|kho\s+roi|"
                r"héo|heo|tiếng\s+động|tieng\s+dong|mất\s+điện|mat\s+dien|ngoài\s+sân|ngoai\s+san)\b",
                cl_raw,
                flags=re.IGNORECASE,
            ):
                parsed_clauses.append((cl_raw, cl_norm, None, None, is_contrast))
                continue

        dev = _extract_clause_device(cl_norm, raw_clause=cl_raw, input_has_diacritics=input_has_diac)
        act = _extract_clause_action(cl_norm, dev, raw_clause=cl_raw, input_has_diacritics=input_has_diac)
        parsed_clauses.append((cl_raw, cl_norm, dev, act, is_contrast))

    if not parsed_clauses:
        return []

    intents: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    last_action: str | None = None
    last_dev: str | None = None
    pending_room_topic: str | None = None

    i = 0
    while i < len(parsed_clauses):
        cl_raw, cl_norm, dev, act, is_contrast = parsed_clauses[i]

        # Handle clause 0 when it has no device and no action (room topic, situational context/reason, or wrong-diacritic prefix)
        if i == 0 and len(parsed_clauses) >= 2 and dev is None and act is None:
            if re.fullmatch(r"(?:phong khach|phong ngu)", cl_norm):
                pending_room_topic = "living_room_light" if "khach" in cl_norm else "bedroom_light"
                i += 1
                continue
            if any(_has_wrong_diacritic_device_head(cl_raw, h) for h in ("den", "coi", "cua", "bom", "loa", "phong")):
                return []
            if _DESCRIPTIVE_CONTEXT_PREFIX_RE.search(cl_raw):
                i += 1
                continue
            # Allow clean Vietnamese situational context clauses (separated by ',', ';', 'rồi', 'nên' — NEVER coordinate 'và'!)
            cl0_toks = cl_norm.split()
            if len(cl0_toks) >= 2 and not cl_norm.endswith(" oi"):
                joined_by_va = bool(re.search(rf"{re.escape(cl_raw)}\s+(?:và|va)\b", split_prep, flags=re.IGNORECASE))
                vi_ok_ratio = sum(1 for t in cl0_toks if _is_plausible_vi_word(t)) / max(1, len(cl0_toks))
                has_later_imperative = any(p_dev is not None and p_act is not None for _, _, p_dev, p_act, _ in parsed_clauses[1:])
                if joined_by_va or not has_later_imperative or vi_ok_ratio < 0.85:
                    return []
                i += 1
                continue

        # Room-only continuation after an explicit light clause
        if dev is None and act is None and last_dev in ("living_room_light", "bedroom_light", "all_lights"):
            if cl_norm in ("phong ngu", "ngu"):
                dev = "bedroom_light"
            elif cl_norm in ("phong khach", "khach"):
                dev = "living_room_light"

        # Apply pending room topic to a following bare light clause
        if pending_room_topic is not None and dev is None and (" den " in f" {cl_norm} " or " đèn " in f" {cl_raw.lower()} "):
            dev = pending_room_topic
            pending_room_topic = None

        # Topic-comment binding: <device + descriptive state>, <verb-only imperative>
        if dev is not None and act is None and (i + 1) < len(parsed_clauses):
            _, _, next_dev, next_act, _ = parsed_clauses[i + 1]
            if next_dev is None and next_act is not None:
                act = next_act
                i += 1  # consume the trailing verb-only comment clause

        if act is not None:
            last_action = act
        elif dev is not None and last_action is not None and not is_contrast and not cl_norm.endswith(" thi"):
            act = last_action

        if dev is None:
            i += 1
            continue
        if act is None:
            # Ambiguous/garbled device clause without action: abort the whole utterance rather than executing a trailing clause.
            return []

        last_dev = dev
        for item in _expand_direct_target(dev, act):
            if item["device_id"] in excluded_devs:
                continue
            key = (item["device_id"], item["action"])
            if key not in seen:
                seen.add(key)
                intents.append(item)
        i += 1

    if not intents and not excluded_devs:
        # Only run fuzzy fallback when there was no wrong-diacritic light word and no garbled multi-clause prefix
        if not _has_wrong_diacritic_light_word(resolved_text) and len(parsed_clauses) == 1:
            intents = _match_constrained_direct_command_vi(normalized, raw_text=resolved_text)

    return intents


def classify_no_action_response_vi(text: str) -> tuple[str, str]:
    """Return (semantic_kind, reply_vi) for non-executing utterances: negation_no_action, unsupported_device, or clarify_no_action."""
    raw = _clean_space(text)
    if not raw:
        return "clarify_no_action", NONSENSE_INPUT_REPLY_VI

    is_bad, kind = is_foreign_or_nonsense_input(raw)
    if is_bad:
        return "clarify_no_action", (FOREIGN_INPUT_REPLY_VI if kind == "foreign" else NONSENSE_INPUT_REPLY_VI)

    norm_punct_safe = " ".join(re.sub(r"([,;.])", r" \1 ", re.sub(r"[^a-z0-9_,;.\s]+", " ", strip_vi_accents(raw.lower()))).split())
    if _UNSUPPORTED_DEVICE_RE.search(f" {norm_punct_safe} "):
        return "unsupported_device", UNSUPPORTED_DEVICE_REPLY_VI

    # Near-miss wrong-diacritic device command across all 6 devices -> clarify_no_action
    near_miss_msg = _detect_wrong_diacritic_near_miss_clarification(raw)
    if near_miss_msg is not None:
        return "clarify_no_action", near_miss_msg

    # Meta-linguistic, past-tense narration, keep-unchanged, or negated/hesitation/deferral phrases -> negation_no_action
    raw_low = raw.lower()
    if (
        _META_LINGUISTIC_NO_ACTION_RE.search(raw_low)
        or _is_past_tense_narration_without_imperative(raw_low)
        or _LEADING_DEFERRAL_RE.match(raw_low)
        or _KEEP_UNCHANGED_PHRASE_RE.search(raw_low)
        or _CLAUSE_NEGATED_OR_KEEP_RE.search(raw_low)
        or _NEGATED_OR_RHETORICAL_DIRECT_RE.search(raw_low)
    ):
        return "negation_no_action", "Vâng, tôi hiểu rồi, tôi sẽ không tác động tới thiết bị nào."

    input_has_diac = has_vi_diacritics(raw)
    normalized = normalize_vietnamese_utterance(raw)
    norm_clean = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(normalized.lower())).split())

    # Bare "đèn" / "den" without an explicit supported room or multi-light quantifier (BOTH accented and unaccented)
    # when >1 light exists in the device registry -> ALWAYS ask which light instead of defaulting to living_room_light!
    light_count = sum(1 for d in DEFAULT_DEVICES if "light" in d)
    has_bare_light_word = (
        (" đèn " in f" {normalized.lower()} " and not _has_wrong_diacritic_light_word(raw))
        if input_has_diac
        else (" den " in f" {norm_clean} ")
    )
    if light_count > 1 and has_bare_light_word and not any(
        k in f" {norm_clean} "
        for k in (" phong khach ", " khach ", " phong ngu ", " ngu ", " buong ", " tat ca ", " toan bo ", " het ", " ca hai ", " hai ")
    ):
        act_u = _extract_clause_action(norm_clean, None, raw_clause=normalized, input_has_diacritics=input_has_diac)
        if act_u is not None:
            act_vi = "tắt" if act_u in ("turn_off", "close") else "bật"
            return "clarify_no_action", f"Bạn muốn {act_vi} đèn phòng khách hay đèn phòng ngủ?"
        return "clarify_no_action", "Bạn muốn bật hay tắt đèn phòng khách hay đèn phòng ngủ?"

    dev = _extract_clause_device(norm_clean, raw_clause=normalized, input_has_diacritics=input_has_diac)
    act = _extract_clause_action(norm_clean, dev, raw_clause=normalized, input_has_diacritics=input_has_diac)

    if dev is not None and act is None:
        if dev == "main_door":
            return "clarify_no_action", "Bạn muốn mở hay đóng cửa chính?"
        if dev == "all_lights":
            return "clarify_no_action", "Bạn muốn bật hay tắt tất cả đèn?"
        if dev == "all_devices":
            return "clarify_no_action", "Bạn muốn bật hay tắt tất cả thiết bị?"
        lbl = _DEVICE_LABELS_SHORT_VI.get(dev, "thiết bị này")
        return "clarify_no_action", f"Bạn muốn bật hay tắt {lbl}?"

    if act is not None and dev is None:
        if act in ("open", "close"):
            return "clarify_no_action", "Bạn muốn mở hay đóng thiết bị nào?"
        return "clarify_no_action", "Bạn muốn bật hoặc tắt thiết bị nào?"

    return "clarify_no_action", NONSENSE_INPUT_REPLY_VI


def classify_ambiguous_or_unsupported_vi(text: str) -> str | None:
    """Return a concise Vietnamese clarification/refusal for foreign, nonsense, unsupported, wrong-diacritic, or ambiguous input."""
    _, reply = classify_no_action_response_vi(text)
    return reply


def format_short_action_reply_vi(
    results: list[dict[str, Any]],
    devices: dict[str, Any] | None = None,
) -> str:
    """Format ultra-concise Vietnamese post-action confirmation."""
    if not results:
        return "Đã thực hiện."

    normalized_items: list[dict[str, Any]] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        # Handle nested engine results list if passed directly
        if "device_id" not in r and isinstance(r.get("results"), list) and r["results"]:
            for sub in r["results"]:
                if isinstance(sub, dict) and sub.get("device_id"):
                    normalized_items.append(sub)
            continue
        if r.get("device_id"):
            normalized_items.append(r)

    if not normalized_items:
        return "Đã thực hiện."

    def _verb_and_state_for(dev_id: str, act: str, new_state: str) -> tuple[str, str]:
        st = str(new_state or "").upper()
        a = str(act or "").lower()
        if dev_id == "main_door":
            is_open = (st == "OPEN") if st in ("OPEN", "CLOSED") else (a in ("open", "turn_on"))
            return ("mở", "mở") if is_open else ("đóng", "đóng")
        is_on = (st == "ON") if st in ("ON", "OFF") else (a in ("open", "turn_on"))
        return ("bật", "bật") if is_on else ("tắt", "tắt")

    def _is_already(item: dict[str, Any]) -> bool:
        if item.get("already_in_state") is True:
            return True
        prev_st = str(item.get("previous_state") or item.get("old_state") or item.get("prev_state") or "").upper()
        new_st = str(item.get("state") or item.get("new_state") or "").upper()
        return bool(prev_st and new_st and prev_st == new_st)

    # Collapse living_room_light + bedroom_light with identical action into "tất cả đèn"
    dev_ids = [str(it.get("device_id") or "") for it in normalized_items]
    if len(normalized_items) == 2 and set(dev_ids) == {"living_room_light", "bedroom_light"}:
        v0, s0 = _verb_and_state_for(dev_ids[0], str(normalized_items[0].get("action") or ""), str(normalized_items[0].get("state") or normalized_items[0].get("new_state") or ""))
        v1, s1 = _verb_and_state_for(dev_ids[1], str(normalized_items[1].get("action") or ""), str(normalized_items[1].get("state") or normalized_items[1].get("new_state") or ""))
        if v0 == v1:
            if all(_is_already(it) for it in normalized_items):
                return f"Tất cả đèn đang {s0} rồi."
            return f"Đã {v0} tất cả đèn."

    if len(normalized_items) == 1:
        it = normalized_items[0]
        did = str(it.get("device_id") or "")
        lbl = _DEVICE_LABELS_SHORT_VI.get(did) or str((devices or {}).get(did, {}).get("name") or did).lower()
        verb, st_word = _verb_and_state_for(did, str(it.get("action") or ""), str(it.get("state") or it.get("new_state") or ""))
        if _is_already(it):
            cap_lbl = lbl[0].upper() + lbl[1:] if lbl else lbl
            return f"{cap_lbl} đang {st_word} rồi."
        return f"Đã {verb} {lbl}."

    parts: list[str] = []
    for it in normalized_items:
        did = str(it.get("device_id") or "")
        lbl = _DEVICE_LABELS_SHORT_VI.get(did) or str((devices or {}).get(did, {}).get("name") or did).lower()
        verb, _ = _verb_and_state_for(did, str(it.get("action") or ""), str(it.get("state") or it.get("new_state") or ""))
        parts.append(f"{verb} {lbl}")

    if len(parts) == 2:
        return f"Đã {parts[0]} và {parts[1]}."
    return f"Đã {', '.join(parts[:-1])} và {parts[-1]}."


def _state_vi_phrase(device_id: str, state: str) -> str:
    st = str(state or "").upper()
    if device_id == "main_door":
        return "đang mở" if st == "OPEN" else "đang đóng"
    return "đang bật" if st in ("ON", "OPEN") else "đang tắt"


def handle_sensor_or_status_query_vi(
    text: str,
    engine: Any,
    session: Any,
) -> dict[str, Any] | None:
    """Answer Vietnamese sensor readings, device status, and auto-pump mode queries immediately."""
    raw = _clean_space(text)
    if not raw:
        return None

    norm = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(raw.lower())).split())
    padded = f" {norm} "

    # Never hijack conditional rule creation or reset/schedule mutations
    # Preserve 'không khí' (air) so it never collides with 'khi' (when)
    raw_no_air = re.sub(r"\b(?:không\s+khí|khong\s+khi)\b", " khong_khi ", raw.lower())
    norm_no_air = " ".join(re.sub(r"[^a-z0-9_\s]+", " ", strip_vi_accents(raw_no_air)).split())
    padded_no_air = f" {norm_no_air} "

    has_cond_he_q = bool(
        re.search(r"\bhễ\b", raw.lower())
        if has_vi_diacritics(raw)
        else (re.search(r"\bhe\s+(?!thong\b|mo\b|cua\b)\S+", norm_no_air) and (" thi " in padded_no_air or " la " in padded_no_air))
    )
    has_reset_or_macro_q = bool(
        _MACRO_LIFECYCLE_GUARD_RE.search(padded_no_air)
        or re.search(
            r"\b(?:dua|dat|tra)\b.+\bve\s+(?:trang\s+thai\s+)?(?:mac\s+dinh|ban\s+dau|xuat\s+xuong|goc)\b|"
            r"\b(?:xuat\s+xuong|factory\s+reset)\b|"
            r"\b(?:xoa|don|huy)(?:\s+(?:bo|sach))?\s+(?:toan\s+bo|tat\s+ca|het|cac|moi)\s+(?:cac\s+)?(?:lien\s+ket|luat|quy\s+tac|cai\s+dat|cau\s+hinh|thiet\s+lap|hen\s+gio|lich)\b|"
            r"\b(?:thiet\s+lap|chinh\s+sua|go(?:\s+bo)?|dep(?:\s+bo)?|ghi\s+nho)\s+(?:(?:giup|gium|dum|ho|cho)\s+(?:toi|minh|anh|chi|em|ban)\s+)?(?:(?:mot|cai)\s+)?(?:khau\s+lenh|cau\s+lenh|lenh|kich\s+ban|ngu\s+canh|bi\s+danh|phim\s+tat)\b",
            norm_no_air,
        )
    )
    # Never hijack save/backup utterances or keep-unchanged / deferral / past-tense safety utterances into status/sensor queries
    if re.match(r"^(?:hay\s+|xin\s+|vui\s+long\s+)?(?:save|luu|sao\s+luu)\b", norm_no_air):
        return None
    if _LEADING_DEFERRAL_RE.match(raw.lower()):
        return None
    if not _is_status_question_vi(raw) and (
        _KEEP_UNCHANGED_PHRASE_RE.search(raw.lower())
        or _is_past_tense_narration_without_imperative(raw.lower())
    ):
        # Allow sensor questions that carry a negated device tail (e.g. 'đọc nhiệt độ, đừng bật đèn')
        has_explicit_sensor_read = bool(
            re.search(r"\b(?:nhiet\s+do|do\s+am|cam\s+bien|ky\s*037|dht\s*11|bao\s+nhieu|so\s+do|thong\s+so)\b", norm_no_air)
            and re.search(r"\b(?:doc|xem|kiem\s+tra|hoi|bao\s+nhieu|the\s+nao|ra\s+sao|bao\s+cao)\b", norm_no_air)
        )
        if not has_explicit_sensor_read:
            return None

    has_thi_conditional_q = bool(
        " thi " in padded_no_air
        and not re.search(r"\bthi\s+(?:sao|the\s+nao|ra\s+sao)\b", norm_no_air)
    )
    if (
        has_thi_conditional_q
        or has_cond_he_q
        or has_reset_or_macro_q
        or any(
            k in padded_no_air
            for k in (
                " tao luat ", " dat luat ", " them luat ", " lien ket ", " khi ", " neu ",
                " bat cu luc nao ", " moi luc ",
                " hen gio ", " dat hen gio ", " dat lich ", " len lich ", " tao lich ", " lap lich ", " hen lich ",
                " reset ", " ri set ", " ri xet ", " re set ", " rexit ", " ri xep ", " dat lai ", " thiet lap lai ",
                " khoi phuc ", " hoi phuc ", " khoi dong lai ", " cau hinh ",
                " tao lenh ", " them lenh ", " luu lenh ", " dat lenh ", " dang ky lenh ", " cai lenh ",
                " sua lenh ", " doi lenh ", " cap nhat lenh ", " cau lenh ", " phim tat ", " ghi nho ",
                " tao khau lenh ", " them khau lenh ", " tao ngu canh ", " them ngu canh ",
                " tao kich ban ", " them kich ban ", " tao che do ", " them che do ", " dat che do ", " luu che do ",
                " tao bi danh ", " dat bi danh ", " tao cau ", " dat cau ", " gan cau ", " luu cau ",
            )
        )
    ):
        return None
    if "," in raw and any(k in padded for k in (" dat kho ", " tieng dong lon ", " am thanh lon ")) and any(
        v in padded for v in (" bat ", " tat ", " mo ", " dong ", " tuoi ")
    ):
        return None

    # Never hijack an explicitly saved custom command whose phrase matches this utterance
    actor_tier_pre = int(getattr(session, "tier", 3) or 3)
    if actor_tier_pre < 3:
        try:
            from backend.automation_repo import list_custom_commands

            uid_pre = str(getattr(session, "user_id", "") or "").strip()
            if uid_pre:
                cmds_pre = list_custom_commands(include_disabled=False, owner_user_id=uid_pre)
                for _c in cmds_pre:
                    _pn = str(_c.get("phrase_norm") or "").strip()
                    if not _pn:
                        continue
                    if norm == _pn or norm in (
                        f"kich hoat {_pn}",
                        f"kich hoat lenh {_pn}",
                        f"chay lenh {_pn}",
                        f"chay khau lenh {_pn}",
                        f"chay phim tat {_pn}",
                        f"chay kich ban {_pn}",
                        f"chay {_pn}",
                        f"thuc hien {_pn}",
                        f"thuc hien lenh {_pn}",
                        f"dung {_pn}",
                    ):
                        return None
        except Exception:
            pass

    # Never hijack sensor SET mutations ("chỉnh nhiệt độ lên 30", "set độ ẩm đất 25")
    norm_no_models = re.sub(r"\b(?:dht\s*11|ky\s*03[78]|yl\s*69|pam\s*8403)\b", " ", norm)
    if any(w in padded for w in (" set ", " chinh ", " dat ", " thay doi ")) and re.search(r"\d", norm_no_models):
        return None
    if (" nhiet do " in padded or " do am " in padded) and any(w in padded for w in (" len ", " xuong ", " thanh ")) and re.search(r"\d", norm_no_models):
        return None

    if hasattr(engine, "sync_from_shared_store"):
        try:
            engine.sync_from_shared_store(force=False)
        except Exception:
            pass

    actor_tier = int(getattr(session, "tier", 3) or 3)

    # 1. Auto-pump mode query
    if any(k in padded for k in (" bom tu dong ", " che do bom ", " tuoi tu dong ", " che do tuoi ")):
        sensors = engine.read_all_sensors() if hasattr(engine, "read_all_sensors") else {}
        soil_pct = float(sensors.get("soil_moisture_pct", 55.0))
        pump_state = str((getattr(engine, "devices", {}) or {}).get("garden_pump", {}).get("state") or "OFF").upper()
        pump_lbl = "đang bật" if pump_state == "ON" else "đang tắt"
        override_off = bool(getattr(engine, "pump_manual_override_off", False))
        override_note = " Đang tạm giữ tắt do tắt thủ công." if override_off else ""
        spoken = (
            f"Chế độ bơm tự động hoạt động theo độ ẩm đất (dưới 40% tự bật, từ 70% tự tắt). "
            f"Hiện độ ẩm đất {soil_pct:.0f}%, máy bơm {pump_lbl}.{override_note}"
        )
        return {
            "ok": True,
            "kind": "auto_pump_status_query",
            "sensors": sensors,
            "reply": spoken,
            "exact_spoken_reply": spoken,
        }

    # 2. Compositional sensor queries (exclude explicitly negated or keep-unchanged clauses)
    pos_sensor_norm = re.sub(
        r"\b(?:khong\s+(?:hoi|xem|phai|bat|tat|mo|dong|can)|chu\s+khong(?:\s+phai)?|"
        r"dung\s+(?:bat|tat|mo|dong|chay|tuoi|dung\s+toi)|cu\s+de\s+nguyen|de\s+nguyen|giu\s+nguyen)\b[^,.;!?]*",
        " ",
        norm,
    )
    pos_padded = f" {' '.join(pos_sensor_norm.split())} "
    raw_low_q = raw.lower()
    raw_has_diac_q = has_vi_diacritics(raw)
    ask_temp = any(k in pos_padded for k in (" nhiet do ", " bao nhieu do ", " may do ", " do c "))
    has_soil_word = bool(re.search(r"\bđất\b", raw_low_q)) if raw_has_diac_q else (" dat " in pos_padded)
    has_humid_word = bool(re.search(r"\bẩm\b", raw_low_q)) if raw_has_diac_q else (" am " in pos_padded)
    has_dry_word = bool(re.search(r"\bkhô\b", raw_low_q)) if raw_has_diac_q else (" kho " in pos_padded)
    has_wet_word = bool(re.search(r"\bướt\b", raw_low_q)) if raw_has_diac_q else (" uot " in pos_padded)
    has_soil_prop = (
        has_humid_word
        or has_dry_word
        or has_wet_word
        or any(
            k in pos_padded
            for k in (
                " do am ", " bao nhieu ", " the nao ", " ra sao ",
                " can tuoi ", " cam bien ", " so do ", " thong so ", " gia tri ", " tinh trang ", " trang thai ", " chi so ",
            )
        )
        or (bool(re.search(r"\bmức\b", raw_low_q)) if raw_has_diac_q else (" muc " in pos_padded))
    )
    ask_soil = (" do am dat " in pos_padded or " cam bien dat " in pos_padded) or (
        has_soil_word and has_soil_prop
    )
    ask_air_hum = (
        (
            " do am " in pos_padded
            or (" khong khi " in pos_padded and has_humid_word)
        )
        and not (ask_soil and " khong khi " not in pos_padded and " phong " not in pos_padded and " trong nha " not in pos_padded)
    )
    ask_sound = any(
        k in pos_padded
        for k in (
            " am thanh ", " ky037 ", " ky 037 ", " tieng dong ", " tieng on ",
            " vo tay ", " phat hien tieng ", " co tieng ", " yen tinh ", " on ao ",
        )
    )
    ask_all_sensors = " cam bien " in pos_padded and not (ask_temp or ask_air_hum or ask_soil or ask_sound)

    # Require an explicit query/measurement cue (or concise standalone sensor noun lookup) and NEVER answer
    # sensor_query on casual non-query household statements (dusting/cleaning/wiping/arranging furniture).
    if ask_temp or ask_air_hum or ask_soil or ask_sound or ask_all_sensors:
        has_casual_chore = bool(
            re.search(
                r"\b(?:lau(?:\s+chùi|\s+bụi|\s+dọn)?|chùi|quét(?:\s+dọn)?|dọn(?:\s+dẹp)?|vệ\s+sinh|phủi(?:\s+bụi)?|bụi|sắp\s+xếp|rửa|giặt|nấu)\b",
                raw_low_q,
            )
            if raw_has_diac_q
            else re.search(r"\b(?:lau|chui|quet|don\s+dep|ve\s+sinh|phui|bui|sap\s+xep|rua|giat|nau)\b", pos_padded)
        )
        has_explicit_query_cue = bool(
            "?" in raw
            or any(
                q in pos_padded
                for q in (
                    " bao nhieu ", " bao nhiu ", " may do ", " the nao ", " ra sao ", " sao ",
                    " chua ", " co dang ", " co khong ", " hay ", " hoac ",
                    " xem ", " doc ", " kiem tra ", " check ",
                    " cho biet ", " cho xem ", " cho toi biet ", " cho minh biet ",
                    " liet ke ", " bao cao ", " thong bao ", " bao cho ", " hoi ",
                    " tinh trang ", " trang thai ", " chi so ", " so do ", " thong so ", " gia tri ",
                    " phan tram ", " can tuoi ", " co tieng ", " phat hien tieng ",
                    " hien tai ", " bay gio ",
                )
            )
            or re.search(r"\b(?:khong|chua|nhi|chu)\s*$", pos_sensor_norm.strip())
            or (
                raw_has_diac_q
                and bool(re.search(r"\b(?:mấy|đo|mức|độ\s*c|báo)\b", raw_low_q))
            )
            or (
                not raw_has_diac_q
                and any(q in pos_padded for q in (" may phan tram ", " muc ", " do c ", " nhiet do may "))
            )
        )
        # Concise standalone sensor noun phrase (e.g. "nhiệt độ phòng", "độ ẩm đất", "cảm biến DHT11")
        is_concise_sensor_lookup = (
            not has_casual_chore
            and len(pos_sensor_norm.split()) <= 8
            and not re.search(
                r"\b(?:vua|da|dang\s+lau|dang\s+don|dang\s+quet|bui)\b",
                pos_padded,
            )
            and any(
                k in pos_padded
                for k in (" nhiet do ", " do am ", " cam bien ", " dht11 ", " ky037 ", " ky 037 ", " am thanh ")
            )
        )
        if not has_explicit_query_cue and not is_concise_sensor_lookup:
            return None
        if has_casual_chore and "?" not in raw and not any(
            q in pos_padded
            for q in (
                " bao nhieu ", " may do ", " the nao ", " ra sao ",
                " xem ", " doc ", " kiem tra ", " check ", " cho biet ", " liet ke ", " bao cao ",
                " chi so ", " so do ", " thong so ", " gia tri ",
            )
        ):
            return None

    # Wrong-diacritic & imperative precedence over sensor_query:
    # An imperative control verb paired with a device or wrong-diacritic device head MUST NOT be hijacked into sensor_query
    # just because a context clause mentions 'tiếng động', 'đất khô', 'nóng', 'ẩm', or 'ồn'.
    if (ask_temp or ask_air_hum or ask_soil or ask_sound or ask_all_sensors) and "?" not in raw:
        if _detect_wrong_diacritic_near_miss_clarification(raw) is not None:
            return None
        has_explicit_sensor_question_cue = bool(
            any(
                q in pos_padded
                for q in (
                    " doc ", " hoi ", " bao nhieu ", " may do ", " the nao ",
                    " ra sao ", " so do ", " thong so ", " gia tri ", " cam bien ",
                    " ky037 ", " ky 037 ", " dht11 ", " co dang ", " phan tram ",
                )
            )
            or (raw_has_diac_q and re.search(r"\bmấy\b", raw_low_q))
        )
        if not has_explicit_sensor_question_cue and parse_direct_device_intents_vi(raw):
            return None
        # Also defer when a direct device imperative clearly governs a device even if trailing purpose says 'lên kiểm tra' / 'xem'
        if (
            not has_explicit_sensor_question_cue
            and re.search(
                r"\b(?:bat|tat|mo|dong|kich\s+hoat|ngat|cup|dung|ngung|dap|cho\s+chay|khoi\s+dong|cap\s+nguon)\b",
                pos_padded,
            )
            and any(
                d in pos_padded
                for d in (" den ", " coi ", " cua ", " bom ", " loa ", " thiet bi ")
            )
        ):
            return None

    if ask_temp or ask_air_hum or ask_soil or ask_sound or ask_all_sensors:
        sensors = (
            engine.read_all_sensors()
            if hasattr(engine, "read_all_sensors")
            else {
                "temperature_c": 28.5,
                "humidity_pct": 65.0,
                "soil_moisture_pct": 62.0,
                "soil_status": "Bình thường",
                "sound_detected": False,
                "sound_status": "Yên tĩnh",
            }
        )
        parts: list[str] = []
        if ask_all_sensors:
            sound_lbl = "phát hiện tiếng động lớn" if sensors.get("sound_detected") else "yên tĩnh"
            spoken = (
                f"Nhiệt độ phòng {float(sensors.get('temperature_c', 28.5)):.1f}°C, "
                f"độ ẩm không khí {float(sensors.get('humidity_pct', 65.0)):.0f}%, "
                f"độ ẩm đất {float(sensors.get('soil_moisture_pct', 55.0)):.0f}%, "
                f"cảm biến âm thanh KY-037 đang {sound_lbl}."
            )
        else:
            if ask_temp:
                parts.append(f"nhiệt độ phòng là {float(sensors.get('temperature_c', 28.5)):.1f}°C")
            if ask_air_hum:
                parts.append(f"độ ẩm không khí {float(sensors.get('humidity_pct', 65.0)):.0f}%")
            if ask_soil:
                soil_st = str(sensors.get("soil_status") or "").strip()
                soil_pct = float(sensors.get("soil_moisture_pct", 55.0))
                parts.append(f"độ ẩm đất {soil_pct:.0f}%" + (f" ({soil_st})" if soil_st else ""))
            if ask_sound:
                sound_lbl = "phát hiện tiếng động lớn" if sensors.get("sound_detected") else "yên tĩnh"
                parts.append(f"cảm biến âm thanh KY-037 đang {sound_lbl}")
            joined = ", ".join(parts)
            spoken = (joined[0].upper() + joined[1:] + ".") if joined else "Không đọc được cảm biến."
        return {
            "ok": True,
            "kind": "sensor_query",
            "sensors": sensors,
            "reply": spoken,
            "exact_spoken_reply": spoken,
        }

    # 3. Device status queries (compositional state-question markers)
    is_status_query = bool(
        any(
            k in padded
            for k in (
                " trang thai ", " tinh trang ",
                " dang mo hay dong ", " dang dong hay mo ",
                " dang mo hay da dong ", " dang mo hoac dong ", " dang dong hoac mo ",
                " dang bat hay tat ", " dang tat hay bat ", " dang sang hay tat ", " dang tat hay sang ",
                " dang bat hay da tat ", " dang bat hoac tat ", " dang tat hoac bat ",
                " co dang bat ",
                " co dang tat ", " co dang mo ", " co dang dong ", " co mo khong ",
                " co bat khong ", " co dong khong ", " co tat khong ",
                " dang mo khong ", " dang bat khong ", " dang dong khong ",
                " dang tat khong ", " dang keu khong ", " co dang keu ",
                " dang the nao ", " thi sao ", " the nao ", " ra sao ", " thiet bi nao dang ", " nhung thiet bi nao ",
                " dang bat gi ", " dang mo gi ", " co gi dang bat ", " co gi dang mo ",
                " nha minh dang bat ", " nha dang bat ",
            )
        )
        or re.search(
            r"\b(?:dang\s+)?(?:bat|sang|mo|keu|chay)\s+(?:hay|hoac)\s+(?:da\s+)?(?:tat|dong|ngung|dung)\b|"
            r"\b(?:dang\s+)?(?:tat|dong)\s+(?:hay|hoac)\s+(?:da\s+)?(?:bat|sang|mo)\b|"
            r"\b(?:da\s+)?(?:duoc\s+)?(?:khep|dong|mo|khoa|chot|bat|tat|sang|chay|keu|hu|ngung|dung)(?:\s+(?:lai|ra|len|kin|ky|chat|het|roi)){0,2}\s+chua\b|"
            r"\bco\s+(?:dang\s+|con\s+|bi\s+)?(?:mo|dong|khep|khoa|chot|bat|tat|sang|chay|keu|hu)(?:\s+(?:lai|ra|len|kin))?\s+khong\b|"
            r"\b(?:kiem\s+tra|xem)(?:\s+(?:giup|ho|gium|thu|lai))?\s+.+\s+(?:dang|da|co)\b",
            norm,
        )
    )
    if not is_status_query:
        return None

    actor_uid = str(getattr(session, "user_id", "") or "").strip() or None
    # All devices status query
    is_all_dev_status_cue = any(
        k in padded
        for k in (
            " cac thiet bi ", " tat ca thiet bi ", " tat ca cac thiet bi ",
            " toan bo thiet bi ", " toan bo cac thiet bi ", " sau thiet bi ", " 6 thiet bi ",
            " may thiet bi ", " moi thiet bi ", " trong nha ", " thiet bi nao ",
            " nha minh ", " ca nha ", " dang bat gi ", " dang mo gi ",
            " co gi dang bat ", " co gi dang mo ", " he thong ",
        )
    )
    single_dev_probe = _extract_clause_device(norm, raw_clause=raw)
    bare_status_fallthrough = False
    if single_dev_probe is None and not is_all_dev_status_cue:
        m_bare = re.search(r"\b(?:trang\s+thai|tinh\s+trang|thiet\s+bi)\b", norm)
        if m_bare is not None:
            prefix_tokens = norm[: m_bare.start()].split()
            allowed_prefix = {
                "xem", "kiem", "tra", "cho", "hoi", "doc", "bao", "cao", "thong",
                "hien", "thi", "cap", "nhat", "liet", "ke", "biet", "giup", "ho",
                "gium", "dum", "toi", "minh", "anh", "chi", "em", "ban", "nha",
                "ta", "oi", "nay", "xin", "vui", "long", "hay", "thu", "lai",
                "tai", "bay", "gio", "cac", "moi", "toan", "bo", "tat", "ca",
                "may", "cua", "ve", "la", "gi", "the", "nao", "nhu", "co", "dang",
                "con", "da", "he", "a", "o", "u", "um", "vang",
            }
            if all(tok in allowed_prefix for tok in prefix_tokens):
                bare_status_fallthrough = True
    if is_all_dev_status_cue or bare_status_fallthrough:
        if hasattr(engine, "list_accessible_devices"):
            devs = engine.list_accessible_devices(actor_tier=actor_tier, actor_user_id=actor_uid)
        else:
            devs = [
                {
                    "device_id": did,
                    "name": info.get("name", did),
                    "state": info.get("state", "OFF"),
                    "state_vi": _state_vi_phrase(did, str(info.get("state", "OFF"))),
                }
                for did, info in (getattr(engine, "devices", {}) or DEFAULT_DEVICES).items()
            ]
        summary = ", ".join(f"{d['name']} {d['state_vi']}" for d in devs)
        spoken = f"Trạng thái hiện tại: {summary}." if summary else "Không có thiết bị nào để hiển thị."
        bh = engine.get_board_health() if hasattr(engine, "get_board_health") else None
        if isinstance(bh, dict) and not bh.get("online", True):
            ls_vi = str(bh.get("last_seen_vi") or "").strip()
            st_vi = str(bh.get("status_vi") or "Mất kết nối").lower()
            note_off = f" Mạch hiện đang {st_vi}" + (f" (lần cuối: {ls_vi})." if ls_vi else ".")
            spoken = spoken + note_off
        return {
            "ok": True,
            "kind": "device_status_query",
            "devices": devs,
            **({"board_health": bh} if isinstance(bh, dict) else {}),
            "reply": spoken,
            "exact_spoken_reply": spoken,
        }

    # Single device status query (pass raw_clause so accented 'đèn' matches and 'của'/'coi' never false-match!)
    dev = single_dev_probe
    if dev is None:
        return None

    if dev == "all_lights":
        targets = ["living_room_light", "bedroom_light"]
    elif dev == "all_devices":
        targets = list((getattr(engine, "devices", {}) or DEFAULT_DEVICES).keys())
    else:
        targets = [dev]

    statuses: list[str] = []
    recs: list[dict[str, Any]] = []
    for td in targets:
        if hasattr(engine, "get_device_state_record"):
            rec = engine.get_device_state_record(td, actor_tier=actor_tier, actor_user_id=actor_uid)
            if not rec.get("ok"):
                if rec.get("rbac_blocked"):
                    deny = str(rec.get("exact_spoken_reply") or "Xin lỗi, bạn không có quyền thực hiện lệnh này.")
                    return {
                        "ok": False,
                        "rbac_blocked": True,
                        "status_code": 403,
                        "kind": "device_status_denied",
                        "error": deny,
                        "reply": deny,
                        "exact_spoken_reply": deny,
                    }
                continue
            recs.append(rec)
            statuses.append(f"{rec['name']} {rec['state_vi']}")
        else:
            info = (getattr(engine, "devices", {}) or {}).get(td)
            if info:
                st_vi = _state_vi_phrase(td, str(info.get("state") or "OFF"))
                statuses.append(f"{info.get('name', td)} {st_vi}")

    if not statuses:
        return None
    joined = ", ".join(statuses)
    spoken = f"{joined[0].upper() + joined[1:]}."
    bh = engine.get_board_health() if hasattr(engine, "get_board_health") else None
    if isinstance(bh, dict) and not bh.get("online", True):
        ls_vi = str(bh.get("last_seen_vi") or "").strip()
        st_vi = str(bh.get("status_vi") or "Mất kết nối").lower()
        spoken = spoken + f" Lưu ý: mạch hiện đang {st_vi}" + (f" (lần cuối: {ls_vi})." if ls_vi else ".")
    return {
        "ok": True,
        "kind": "device_status_query",
        "devices": recs,
        **({"board_health": bh} if isinstance(bh, dict) else {}),
        "reply": spoken,
        "exact_spoken_reply": spoken,
    }


def execute_custom_command_query_steps(
    query_steps: list[dict[str, Any]],
    engine: Any,
    actor_tier: int,
) -> tuple[bool, bool, str, str, dict[str, Any]]:
    """Read live sensor and/or device-state values for custom-command query steps without mutating any device.

    Returns (ok, rbac_blocked, error_msg, spoken_reply, data_payload).
    """
    from backend.automation_repo import SENSOR_QUERY_TARGETS

    if not query_steps:
        return True, False, "", "", {}

    if hasattr(engine, "sync_from_shared_store"):
        try:
            engine.sync_from_shared_store(force=False)
        except Exception:
            pass

    needs_sensors = any(str(s.get("device_id") or "") in SENSOR_QUERY_TARGETS for s in query_steps)
    sensors: dict[str, Any] | None = None
    if needs_sensors:
        sensors = (
            engine.read_all_sensors()
            if hasattr(engine, "read_all_sensors")
            else {
                "temperature_c": 28.5,
                "humidity_pct": 65.0,
                "soil_moisture_pct": 62.0,
                "soil_status": "Bình thường",
                "sound_detected": False,
                "sound_status": "Yên tĩnh",
            }
        )

    parts: list[str] = []
    seen_parts: set[str] = set()
    device_recs: list[dict[str, Any]] = []

    def _add_part(key: str, text_seg: str) -> None:
        if key not in seen_parts and text_seg:
            seen_parts.add(key)
            parts.append(text_seg)

    for step in query_steps:
        did = str(step.get("device_id") or "").strip()
        act = str(step.get("action") or "").strip().lower()
        if did in SENSOR_QUERY_TARGETS and sensors is not None:
            if did == "sensor_all":
                sound_lbl = "phát hiện tiếng động lớn" if sensors.get("sound_detected") else "yên tĩnh"
                soil_st = str(sensors.get("soil_status") or "").strip()
                soil_pct = float(sensors.get("soil_moisture_pct", 55.0))
                _add_part("sensor_temperature", f"nhiệt độ phòng {float(sensors.get('temperature_c', 28.5)):.1f}°C")
                _add_part("sensor_humidity", f"độ ẩm không khí {float(sensors.get('humidity_pct', 65.0)):.0f}%")
                _add_part("sensor_soil", f"độ ẩm đất {soil_pct:.0f}%" + (f" ({soil_st})" if soil_st else ""))
                _add_part("sensor_sound", f"cảm biến âm thanh KY-037 đang {sound_lbl}")
            elif did == "sensor_temperature":
                _add_part("sensor_temperature", f"nhiệt độ phòng {float(sensors.get('temperature_c', 28.5)):.1f}°C")
            elif did == "sensor_humidity":
                _add_part("sensor_humidity", f"độ ẩm không khí {float(sensors.get('humidity_pct', 65.0)):.0f}%")
            elif did == "sensor_soil":
                soil_st = str(sensors.get("soil_status") or "").strip()
                soil_pct = float(sensors.get("soil_moisture_pct", 55.0))
                _add_part("sensor_soil", f"độ ẩm đất {soil_pct:.0f}%" + (f" ({soil_st})" if soil_st else ""))
            elif did == "sensor_sound":
                sound_lbl = "phát hiện tiếng động lớn" if sensors.get("sound_detected") else "yên tĩnh"
                _add_part("sensor_sound", f"cảm biến âm thanh KY-037 đang {sound_lbl}")
            continue

        if act == "read_state":
            if did == "all_lights":
                targets = ["living_room_light", "bedroom_light"]
            elif did == "all_devices":
                targets = list((getattr(engine, "devices", {}) or DEFAULT_DEVICES).keys())
            else:
                targets = [did]
            for td in targets:
                if f"dev:{td}" in seen_parts:
                    continue
                if hasattr(engine, "get_device_state_record"):
                    rec = engine.get_device_state_record(td, actor_tier=actor_tier)
                    if not rec.get("ok"):
                        if rec.get("rbac_blocked"):
                            deny = str(rec.get("exact_spoken_reply") or "Xin lỗi, bạn không có quyền thực hiện lệnh này.")
                            return False, True, deny, deny, {}
                        continue
                    device_recs.append(rec)
                    _add_part(f"dev:{td}", f"{str(rec.get('name') or td).lower()} {rec['state_vi']}")
                else:
                    info = (getattr(engine, "devices", {}) or {}).get(td)
                    if info:
                        st_vi = _state_vi_phrase(td, str(info.get("state") or "OFF"))
                        device_recs.append({
                            "device_id": td,
                            "name": info.get("name", td),
                            "state": info.get("state", "OFF"),
                            "state_vi": st_vi,
                        })
                        _add_part(f"dev:{td}", f"{str(info.get('name') or td).lower()} {st_vi}")

    if not parts:
        return True, False, "", "", {}

    joined = ", ".join(parts)
    spoken = f"{joined[0].upper() + joined[1:]}."
    data: dict[str, Any] = {}
    if sensors is not None:
        data["sensors"] = sensors
    if device_recs:
        data["devices"] = device_recs
    return True, False, "", spoken, data
