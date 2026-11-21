"""Vietnamese-only voice policy, NLU normalization, small talk, sensor/status queries, and concise replies."""

from __future__ import annotations

from difflib import SequenceMatcher
import re
import unicodedata
from typing import Any

from simulator.engine.constants_and_time import DEFAULT_DEVICES

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
    "cap", "thanh", "vien", "chu", "nguoi", "tat", "ca", "hai", "het", "mot",
    "lan", "hang", "ngay", "phut", "giay", "sau", "nua", "luc", "sang", "trua",
    "chieu", "toi", "dem", "chua", "nghe", "ro", "noi", "lai", "hon", "nhe",
    "thiet", "bi", "he", "thong", "trang", "thai", "tu", "dong", "vuon", "kho",
    "uot", "vui", "long", "bang", "cam", "on", "tam", "biet", "gap", "ngon",
    "ai", "ten", "la", "lam", "xong", "khoa", "chot", "khep", "gai", "ngat",
    "muc", "bao", "nhieu", "nao", "the", "hay", "va", "cung", "voi", "cua",
    "minh", "em", "anh", "chi", "me", "bo", "con", "ong", "ba", "a", "nha",
    "nhung", "cac", "moi", "trong", "ngoai", "buong", "bong", "cong", "hu",
    "chong", "trom", "vo", "tay", "dat", "lai", "goc", "cai", "xac", "nhan",
    "y", "vang", "u", "thoi", "bo", "ke", "xem", "danh", "sach", "hien", "tai",
    "phan", "tram", "do", "c", "giu", "tat", "tay", "nguoc", "tri", "thuc",
    "giong", "ao", "nguyen", "tuan", "cu", "the", "vua", "se", "nhap", "phien",
    "can", "goi", "rat", "tot", "gioi", "qua", "tuyet", "voi", "chuc", "muon",
})

_PURE_FILLERS: frozenset[str] = frozenset({
    "o", "a", "um", "uh", "uhm", "erm", "hmm", "hm", "eh", "oh", "ah",
    "nay", "e", "oi", "ha", "ho", "ne", "a", "da", "u", "ua", "i",
})

_UNSUPPORTED_DEVICE_RE = re.compile(
    r"(?:^|\s)(?:"
    r"quat(?:\s+tran|\s+dung|\s+ban|\s+may)?|"
    r"dieu\s+hoa|may\s+lanh|aircon|"
    r"tivi|ti\s+vi|\btv\b|"
    r"may\s+giat|tu\s+lanh|"
    r"rem(?:\s+cua)?|(?:dem|giem|ren)\s+cua|"
    r"cua\s+(?:cuon|so|ban\s+cong|phong\s+ngu|nha\s+ve\s+sinh|gara|tu|kinh)|"
    r"den\s+(?:bep|nha\s+ve\s+sinh|nha\s+tam|ban\s+cong|cau\s+thang|ban\s+hoc)|"
    r"loa\s+(?:bluetooth|tivi|tv)|bom\s+tang\s+ap|"
    r"(?:binh\s+)?nong\s+lanh|"
    r"lo\s+vi\s+song|robot\s+hut\s+bui|"
    r"hoc\s+lenh|hong\s+ngoai|remote|vs1838b?"
    r")(?:\s|$)"
)

_NEGATED_OR_RHETORICAL_DIRECT_RE = re.compile(
    r"(?:^|\s)(?:"
    r"(?:không(?:\s+(?:cần|muốn|được|nên|phải))?|khong(?:\s+(?:can|muon|duoc|nen|phai))?|"
    r"đừng(?:\s+(?:có|vội|bao\s+giờ))?|chớ|"
    r"chưa\s+cần|chua\s+can|khỏi\s+cần|khoi\s+can|thôi\s+không|thoi\s+khong)\s+"
    r"(?:mở|mo|đóng|dong|bật|bat|tắt|tat|khóa|khoa|chốt|chot|khép|khep|ngắt|ngat|dừng|dung|chạy|chay)\b|"
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
    norm = f" {strip_vi_accents(str(text or '').lower())} "
    norm = re.sub(r"[^a-z0-9\s]+", " ", norm)
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
        " tieng dong ", " vo tay ", " trang thai ", " bom tu dong ",
    )
    automation_cues = (
        " hen gio ", " dat lich ", " lich ", " sau ", " nua ", " tao lenh ",
        " sua lenh ", " xoa lenh ", " huy ", " lien ket ", " tao luat ", " reset ",
        " dat lai ", " thanh vien ", " cap quyen ", " thu hoi ", " khi ", " neu ",
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

    # Help / capabilities
    if any(
        p in norm
        for p in (
            "giup toi",
            "giup minh",
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
    ):
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
            "reply": "Không có gì! Cần điều khiển gì bạn cứ nói nhé.",
        }

    # Goodbye
    if norm in ("tam biet", "tam biet ban", "tam biet nhe", "gap lai sau", "hen gap lai", "ket thuc", "ngu ngon", "chuc ngu ngon") or any(
        p in norm for p in ("tam biet", "gap lai sau", "hen gap lai", "chuc ngu ngon")
    ):
        reply = "Chúc bạn ngủ ngon!" if "ngu ngon" in norm else "Tạm biệt bạn! Hẹn gặp lại."
        return {
            "kind": "small_talk",
            "subkind": "goodbye",
            "reply": reply,
        }

    # Greetings
    if any(p in norm for p in ("chao buoi sang",)) or norm in ("vao buoi sang", "trong buoi sang"):
        return {
            "kind": "small_talk",
            "subkind": "greeting",
            "reply": "Chào buổi sáng! Tôi có thể giúp gì cho bạn?",
        }
    if any(p in norm for p in ("chao buoi trua",)):
        return {
            "kind": "small_talk",
            "subkind": "greeting",
            "reply": "Chào buổi trưa! Tôi có thể giúp gì cho bạn?",
        }
    if any(p in norm for p in ("chao buoi chieu",)):
        return {
            "kind": "small_talk",
            "subkind": "greeting",
            "reply": "Chào buổi chiều! Tôi có thể giúp gì cho bạn?",
        }
    if any(p in norm for p in ("chao buoi toi",)):
        return {
            "kind": "small_talk",
            "subkind": "greeting",
            "reply": "Chào buổi tối! Tôi có thể giúp gì cho bạn?",
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
            "reply": "Xin chào! Tôi có thể giúp gì cho bạn?",
        }

    return None


def normalize_vietnamese_utterance(text: str) -> str:
    """Strip conversational fillers and normalize Bac/Trung/Nam regional & STT variants for direct commands."""
    s = _clean_space(text).lower()
    if not s:
        return ""

    # Strip leading greeting/attention prefixes when followed by a command (e.g. "chào bạn, mở cửa đi")
    s = re.sub(
        r"^(?:(?:xin\s+)?chào(?:\s+(?:bạn|em|anh|chị|trợ\s+lý|nhà\s+thông\s+minh))?|"
        r"(?:xin\s+)?chao(?:\s+(?:ban|em|anh|chi|tro\s+ly|nha\s+thong\s+minh))?|"
        r"ê\s+trợ\s+lý|e\s+tro\s+ly|al[ôo]\s+trợ\s+lý|al[ôo]\s+tro\s+ly|"
        r"trợ\s+lý\s+ơi|tro\s+ly\s+oi|bạn\s+ơi|ban\s+oi|em\s+ơi|em\s+oi)\s*[,;:.!?-]*\s+",
        "",
        s,
        flags=re.IGNORECASE,
    )

    # Strip leading filler words repeatedly
    for _ in range(4):
        updated = re.sub(
            r"^(?:ờ|à|ừm|ừ|ơ|này|ê|ơi|nè|alô|alo|o|a|um|nay|e|oi|làm\s+ơn|lam\s+on|hãy|hay)\b[\s,;:]*",
            "",
            s,
            flags=re.IGNORECASE,
        ).strip()
        if updated == s:
            break
        s = updated

    # Normalize common STT clipped/mumbled & regional forms BEFORE filler stripping
    # Door variants
    s = re.sub(r"\b(?:mở\s+cữa|mơ\s+cửa|mở\s+củ|mo\s+cu|mo\s+cua\s+di|mở\s+cổng|mo\s+cong)\b", "mở cửa chính", s)
    s = re.sub(r"\b(?:khóa|khoá|hóa|hoá|chốt|khép|gài)\s+(?:cửa\s+chính|cửa|cữa|cổng)\b", "đóng cửa chính", s)
    s = re.sub(r"\b(?:khoa|hoa|chot|khep|gai)\s+(?:cua\s+chinh|cua|cong)\b", "đóng cửa chính", s)
    s = re.sub(r"\b(?:đóng|dong)\s+(?:cữa|cổng|cong)\b", "đóng cửa chính", s)

    # Lights regional & colloquial variants
    s = re.sub(r"\b(?:hát|hat)\s+(?:đèn|den)\b", "tắt đèn", s)
    s = re.sub(r"\bđền\s+phòng\s+khách\b", "đèn phòng khách", s)
    s = re.sub(r"\bđền\s+phòng\s+ngủ\b", "đèn phòng ngủ", s)
    s = re.sub(r"\bđèn\s+(?:ngồi|vừa)\s+ngủ\b|\bden\s+(?:ngoi|vua)\s+ngu\b", "đèn phòng ngủ", s)
    s = re.sub(r"\bđèn\s+(?:hò\s+khách|vòm\s+hết|vòm\s+khách)\b|\bden\s+(?:ho\s+khach|vom\s+het|vom\s+khach)\b", "đèn phòng khách", s)
    s = re.sub(r"\btất\s+cả\s+đền\b", "tất cả đèn", s)
    s = re.sub(r"\bhết\s+đền\b", "hết đèn", s)
    s = re.sub(r"\b(?:tắt\s+tắt\s+đèn|tat\s+tat\s+den)\b", "tắt tất cả đèn", s)
    s = re.sub(r"\b(?:bật\s+bật\s+đèn|bat\s+bat\s+den)\b", "bật tất cả đèn", s)
    s = re.sub(r"\b(?:bật|mở|bat|mo)\s+(?:thiết\s+đèn|thiet\s+den)\b", "bật tất cả đèn", s)
    s = re.sub(r"\b(?:tắt|tat)\s+(?:thiết\s+đèn|thiet\s+den)\b", "tắt tất cả đèn", s)
    s = re.sub(r"\b(bật|tắt|mở|đóng|bat|tat|mo|dong)\s+(?:đèn\s+khác|den\s+khac)\b", r"\1 đèn phòng khách", s)
    s = re.sub(r"\b(?:vận\s+hành|van\s+hanh)\s+(?:phòng\s+khách|phong\s+khach)\b", "bật đèn phòng khách", s)
    s = re.sub(r"\bbóng\s+đèn\s+phòng\s+khách\b|\bbóng\s+đèn\s+khách\b|\bđèn\s+khách\b|\bđèn\s+ngoài\b|\bđèn\s+chính\b", "đèn phòng khách", s)
    s = re.sub(r"\bbong\s+den\s+phong\s+khach\b|\bbong\s+den\s+khach\b|\bden\s+khach\b|\bden\s+ngoai\b|\bden\s+chinh\b", "đèn phòng khách", s)
    s = re.sub(r"\bbóng\s+đèn\s+phòng\s+ngủ\b|\bđèn\s+ngủ\b|\bđèn\s+buồng\b|\bđèn\s+buồn\b|\bđèn\s+trong\s+phòng\b", "đèn phòng ngủ", s)
    s = re.sub(r"\bbong\s+den\s+phong\s+ngu\b|\bden\s+ngu\b|\bden\s+buong\b|\bden\s+buon\b|\bden\s+trong\s+phong\b", "đèn phòng ngủ", s)
    s = re.sub(r"\b(?:hết|toàn\s+bộ|cả\s+hai|hai|cả\s+2|2|các|mọi)\s+đèn(?!\s+(?:phòng|khách|ngủ|buồng))\b", "tất cả đèn", s)
    s = re.sub(r"\b(?:het|toan\s+bo|ca\s+hai|hai|ca\s+2|2|cac|moi)\s+den(?!\s+(?:phong|khach|ngu|buong))\b", "tất cả đèn", s)

    # Pump variants
    s = re.sub(
        r"\b(?:ngừng|dừng|rừng|tắt|ngắt|ngung|dung|rung|tat|ngat)\s+"
        r"(?:tưới\s+cây|tưới\s+vườn|tưới\s+vừa|dưới\s+cây|dưới\s+vườn|dưới\s+vừa|dưới\s+vần|tưới\s+vần|"
        r"tuoi\s+cay|tuoi\s+vuon|tuoi\s+vua|duoi\s+cay|duoi\s+vuon|duoi\s+vua|duoi\s+van|tuoi\s+van)\b",
        "tắt máy bơm tưới cây",
        s,
    )
    s = re.sub(
        r"\b(?:bật|mở|bat|mo)\s+(?:máy\s+bơm|máy\s+ôm|may\s+bom|may\s+om|bơm|bom)"
        r"(?:\s+(?:tưới\s+cây|dưới\s+cây|tưới\s+vườn|dưới\s+vườn|tuoi\s+cay|duoi\s+cay|tuoi\s+vuon|duoi\s+vuon))?"
        r"(?!\s+(?:nước|vườn|nuoc|vuon))\b",
        "bật máy bơm tưới cây",
        s,
    )
    s = re.sub(
        r"\b(?:tắt|ngắt|dừng|ngừng|tat|ngat|dung|ngung)\s+(?:máy\s+ôm|may\s+om|bơm|bom)"
        r"(?:\s+(?:tưới\s+cây|dưới\s+cây|tưới\s+vườn|dưới\s+vườn|tuoi\s+cay|duoi\s+cay|tuoi\s+vuon|duoi\s+vuon))?"
        r"(?!\s+(?:nước|vườn|nuoc|vuon))\b",
        "tắt máy bơm tưới cây",
        s,
    )
    s = re.sub(r"\b(?:bơm\s+nước|bơm\s+vườn|bom\s+nuoc|bom\s+vuon)\b", "máy bơm tưới cây", s)

    # Siren variants
    s = re.sub(r"\b(?:bật|mở|bat|mo)\s+(?:ngòi\s+hú|ngoi\s+hu)\b", "bật còi báo động", s)
    s = re.sub(r"\b(?:tắt|ngắt|dừng|ngừng|tat|ngat|dung|ngung)\s+(?:ngòi\s+hú|ngoi\s+hu)\b", "tắt còi báo động", s)
    s = re.sub(r"\b(?:bật|mở|bat|mo)\s+(?:còi|coi)(?!\s+(?:báo\s+động|bao\s+dong|hú|hu))\b", "bật còi báo động", s)
    s = re.sub(r"\b(?:tắt|ngắt|dừng|tat|ngat|dung)\s+(?:còi|coi|báo\s+động|bao\s+dong)(?!\s+(?:báo\s+động|bao\s+dong|hú|hu))\b", "tắt còi báo động", s)
    s = re.sub(r"\b(?:còi\s+hú|coi\s+hu|chống\s+trộm|chong\s+trom)\b", "còi báo động", s)

    # Speaker amp variants
    s = re.sub(r"^(?:bật|mở|bạch|bat|mo|bach)\s+(?:hoa|loa)(?:\s*[.!?]*)$", "bật nguồn mạch loa", s)
    s = re.sub(r"^(?:tắt|ngắt|tat|ngat)\s+hoa(?:\s*[.!?]*)$", "tắt nguồn mạch loa", s)
    s = re.sub(r"\b(?:bạn|ban)\s+nguồn\s+(?:mạch|mệt|mạt|vài|bài)\s+loa\b", "bật nguồn mạch loa", s)
    s = re.sub(r"\b(bật|tắt|mở|đóng|bat|tat|mo|dong)\s+(?:nguồn|ngùng|nguon|ngung)\s+(?:mạch|mặt|mệt|mạt|vài|bài|mach|mat|met|vai|bai)\s+loa\b", r"\1 nguồn mạch loa", s)
    s = re.sub(r"\b(?:bật|mở|bat|mo)\s+(?:loa|âm\s+ly|ấm\s+lý|âm\s+li|am\s+ly|am\s+li|mạch\s+loa|mach\s+loa|nguồn\s+loa|nguon\s+loa|nguồn\s+(?:vài|bài)\s+loa|nguon\s+(?:vai|bai)\s+loa|pam8403)\b", "bật nguồn mạch loa", s)
    s = re.sub(r"\b(?:tắt|ngắt|dừng|tat|ngat|dung)\s+(?:loa|âm\s+ly|ấm\s+lý|âm\s+li|am\s+ly|am\s+li|mạch\s+loa|mach\s+loa|nguồn\s+loa|nguon\s+loa|nguồn\s+(?:vài|bài)\s+loa|nguon\s+(?:vai|bai)\s+loa|pam8403)\b", "tắt nguồn mạch loa", s)
    s = re.sub(r"\b(?:âm\s+ly|ấm\s+lý|âm\s+li|am\s+ly|am\s+li|(?<!nguồn\s)mạch\s+loa|(?<!nguon\s)mach\s+loa|nguồn\s+loa|nguon\s+loa|nguồn\s+(?:vài|bài)\s+loa|nguon\s+(?:vai|bai)\s+loa|pam8403)\b", "nguồn mạch loa", s)

    # Strip polite fillers inside / at end without breaking clause conjunctions
    s = re.sub(
        r"\b(?:giúp\s+mình|giúp\s+tôi|hộ\s+mình|hộ\s+tôi|giùm\s+tôi|giùm\s+mình|"
        r"cho\s+tôi|cho\s+mình|làm\s+ơn|giup\s+minh|giup\s+toi|ho\s+minh|ho\s+toi|"
        r"gium\s+toi|gium\s+minh|cho\s+toi|cho\s+minh|lam\s+on)\b",
        " ",
        s,
    )
    # Strip trailing softeners
    for _ in range(3):
        updated = re.sub(
            r"(?:\s+(?:nhé|nha|nhá|ạ|đi|với|luôn|ngay|nhanh|cái|hộ|giùm|nhe|nha|a|di|voi|luon|ngay|nhanh|cai))+\s*[.!?]*$",
            "",
            s.strip(),
        ).strip()
        if updated == s:
            break
        s = updated

    # Strip inline fillers "luôn", "ngay", "nhanh", "đi" right after verbs/devices
    s = re.sub(r"\b(?:luôn|ngay|nhanh|nhé|nha|nhá|ạ)\b", " ", s)
    return _clean_space(s)


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
    ("cua lon", "main_door"),
    ("cua nha", "main_door"),
    ("cua ra vao", "main_door"),
    ("may bom tuoi cay", "garden_pump"),
    ("may bom", "garden_pump"),
    ("bom nuoc", "garden_pump"),
    ("bom vuon", "garden_pump"),
    ("tuoi cay", "garden_pump"),
    ("tuoi vuon", "garden_pump"),
    ("coi bao dong", "alarm_siren"),
    ("bao dong", "alarm_siren"),
    ("coi hu", "alarm_siren"),
    ("nguon mach loa", "speaker_amp"),
    ("mach loa", "speaker_amp"),
    ("nguon loa", "speaker_amp"),
    ("pam8403", "speaker_amp"),
)


def _extract_clause_device(norm_clause: str) -> str | None:
    padded = f" {norm_clause} "
    for kw, dev_id in _DIRECT_DEVICE_PATTERNS:
        if f" {kw} " in padded:
            return dev_id
    if " den " in padded and " den phong " not in padded:
        return "living_room_light"
    if " cua " in padded or " cong " in padded:
        return "main_door"
    if " bom " in padded:
        return "garden_pump"
    if " coi " in padded:
        return "alarm_siren"
    if " loa " in padded:
        return "speaker_amp"
    return None


_NON_VERB_NOUN_PHRASES: tuple[str, ...] = (
    "bao dong",
    "tu dong",
    "tat ca",
    "tieng dong",
    "chuyen dong",
    "hoat dong",
    "dong ho",
    "cong tac",
    "dong y",
)


def _strip_non_verb_phrases(norm_clause: str) -> str:
    padded = f" {norm_clause} "
    for phrase in _NON_VERB_NOUN_PHRASES:
        padded = padded.replace(f" {phrase} ", " ")
    return " ".join(padded.split())


def _extract_clause_action(norm_clause: str, dev_id: str | None) -> str | None:
    action_clause = _strip_non_verb_phrases(norm_clause)
    padded = f" {action_clause} "
    off_verb: str | None = None
    on_verb: str | None = None
    for w in ("tat", "dong", "khoa", "chot", "khep", "gai", "ngat", "dung", "ngung"):
        if f" {w} " in padded:
            off_verb = w
            break
    for w in ("bat", "mo", "khoi dong", "chay"):
        if f" {w} " in padded:
            on_verb = w
            break
    # Conflicting ON and OFF verbs in a single clause -> ambiguous (never silently flip polarity!).
    if off_verb is not None and on_verb is not None:
        return None
    if off_verb is not None:
        return "close" if (dev_id == "main_door" or off_verb in ("dong", "khoa", "chot", "khep", "gai")) else "turn_off"
    if on_verb is not None:
        return "open" if (dev_id == "main_door" or on_verb == "mo") else "turn_on"
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
                {"device_id": "speaker_amp", "action": "turn_on"},
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
    " dang mo hay dong ", " dang bat hay tat ", " co dang bat ", " co dang mo ",
    " co dang tat ", " co dang dong ", " trang thai ", " hen gio ", " dat lich ", " dac lich ",
    " hen lich ", " sua lich ", " doi lich ", " xoa lich ", " huy lich ", " lich hen ",
    " hang ngay ", " moi ngay ", " ngay nao cung ", " lap lai ",
    " gio sang ", " gio trua ", " gio chieu ", " gio toi ", " gio dem ",
    " tao lenh ", " sua lenh ", " doi lenh ", " xoa lenh ", " huy lenh ",
    " tao viec ", " ra lenh ", " dau lenh ", " doc lenh ", " tao ra ",
    " thanh bat ", " thanh tat ", " thanh mo ", " thanh dong ",
    " lenh custom ", " lenh tuy chinh ", " tao luat ", " lien ket ",
    " xoa lien ket ", " huy lien ket ", " phut nua ", " giay nua ", " gio nua ",
    " reset ", " ri set ", " rex ", " rexit ", " rep trang thai ", " rep lien ket ",
    " virus lien ket ", " khoi phuc ", " hoi phuc ", " cai dat goc ", " thiet lap ",
    " dat lai ", " thiet lap trang thai ", " save trang thai ", " ve sinh sach thiet bi ",
    " khi ", " neu ", " dat kho ", " tieng dong lon ", " chuyen dong lon ", " bien dong lon ",
)

_CUSTOM_COMMAND_DIRECT_GUARD_RE = re.compile(
    r"(?:\b(?:che\s+do|lenh|tao\s+lich|vi\s*ec|viec|kich\s+ban|ngu\s+canh)\b.+\b(?:la|lam|thanh)\b|"
    r"\b(?:la|lam|thanh)\s+(?:bat|tat|mo|dong|khoa|ngat|dung|ngung)\b|"
    r"\bmo\s+(?:tat|dong|khoa|ngat)\b)"
)

_COUNTDOWN_OR_CLOCK_GUARD_RE = re.compile(
    r"(?:\bsau\s+(?:\d+|(?:mot|hai|ba|bon|nam|sau|bay|bai|tam|chin|muoi|nua)\s+(?:giay|phut|gio|tieng))\b|"
    r"\b(?:giay|phut|tieng)\s+nua\b|"
    r"\b\d+\s*(?:giay|phut|tieng)\b|"
    r"\b(?:luc|vao\s+luc)\s+(?:\d+|mot|hai|ba|bon|nam|sau|bay|bai|tam|chin|muoi)\s*(?:gio|h)\b|"
    r"\b\d{1,2}\s*(?:gio|h)\s*\d{0,2}\b|\b\d{1,2}:\d{2}\b)"
)

_CONDITIONAL_THI_GUARD_RE = re.compile(r"(?<!\broi)\s+thi\s+")

_EXPLICIT_OFF_VERBS: frozenset[str] = frozenset({
    "tat", "dong", "khoa", "chot", "khep", "gai", "ngung", "dung", "ngat",
})
_EXPLICIT_ON_VERBS: frozenset[str] = frozenset({
    "bat", "mo", "khoi",
})

_FUZZY_BLOCKED_QUERY_CUES: tuple[str, ...] = (
    " bao nhieu ", " the nao ", " la gi ", " cam bien ", " nhiet do ",
    " do am ", " thanh vien ", " tai khoan ", " quyen ", " lich ", " hen ",
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


_CANONICAL_DIRECT_COMMANDS: tuple[tuple[str, str, str, str, str, int], ...] = tuple(
    (phrase, pol, dev, act, _vi_phonetic_skeleton(phrase), len(phrase.split()))
    for phrase, pol, dev, act in (
        ("mo cua chinh", "on", "main_door", "open"),
        ("mo cua", "on", "main_door", "open"),
        ("dong cua chinh", "off", "main_door", "close"),
        ("dong cua", "off", "main_door", "close"),
        ("khoa cua chinh", "off", "main_door", "close"),
        ("khoa cua", "off", "main_door", "close"),
        ("bat den phong khach", "on", "living_room_light", "turn_on"),
        ("tat den phong khach", "off", "living_room_light", "turn_off"),
        ("bat den phong ngu", "on", "bedroom_light", "turn_on"),
        ("tat den phong ngu", "off", "bedroom_light", "turn_off"),
        ("bat tat ca den", "on", "all_lights", "turn_on"),
        ("tat tat ca den", "off", "all_lights", "turn_off"),
        ("bat may bom tuoi cay", "on", "garden_pump", "turn_on"),
        ("bat may bom", "on", "garden_pump", "turn_on"),
        ("tat may bom tuoi cay", "off", "garden_pump", "turn_off"),
        ("tat may bom", "off", "garden_pump", "turn_off"),
        ("bat coi bao dong", "on", "alarm_siren", "turn_on"),
        ("tat coi bao dong", "off", "alarm_siren", "turn_off"),
        ("bat nguon mach loa", "on", "speaker_amp", "turn_on"),
        ("tat nguon mach loa", "off", "speaker_amp", "turn_off"),
        ("tat tat ca thiet bi", "off", "all_devices", "turn_off"),
    )
)


def _match_constrained_direct_command_vi(norm_text: str) -> list[dict[str, str]]:
    """High-precision phonetic + edit-distance matcher over the closed 6-device Vietnamese command grammar.

    Safety invariants:
    - Never runs on foreign/nonsense, unsupported devices, questions, or automation cues.
    - Requires an explicit ON or OFF verb token and strictly locks polarity (never flips ON<->OFF, never guesses bare nouns).
    - Requires score >= 85, token-count compatibility (|diff| <= 1), and margin >= 6 over the runner-up target.
    """
    if not norm_text or "?" in norm_text:
        return []
    clean = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(norm_text.lower())).split())
    if not clean:
        return []
    padded = f" {clean} "
    if _UNSUPPORTED_DEVICE_RE.search(padded):
        return []
    if any(k in padded for k in _FUZZY_BLOCKED_QUERY_CUES):
        return []

    tokens = clean.split()
    if len(tokens) < 2 or len(tokens) > 7:
        return []

    verb_tokens = set(_strip_non_verb_phrases(clean).split())
    has_off = bool(verb_tokens & _EXPLICIT_OFF_VERBS)
    has_on = bool(verb_tokens & _EXPLICIT_ON_VERBS)
    if has_off == has_on:
        # Either no explicit verb (ambiguous bare noun) or conflicting polarities: never guess.
        return []
    required_polarity = "off" if has_off else "on"

    phon_in = _vi_phonetic_skeleton(clean)
    best_by_target: dict[tuple[str, str], float] = {}
    for phrase, pol, dev, act, cand_phon, cand_tok_n in _CANONICAL_DIRECT_COMMANDS:
        if pol != required_polarity:
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
    if best_score < 85.0 or (best_score - second_score) < 6.0:
        return []
    return _expand_direct_target(best_dev, best_act)


def parse_direct_device_intents_vi(
    text: str,
    *,
    word_mappings: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """Parse single or multi-device direct Vietnamese commands; never guess on ambiguous/foreign input."""
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

    norm_raw = f" {' '.join(re.sub(r'[^a-z0-9\s]+', ' ', strip_vi_accents(mapped)).split())} "
    # Never guess a supported device when an unsupported appliance is mentioned (e.g. "đóng rèm cửa")
    if _UNSUPPORTED_DEVICE_RE.search(norm_raw):
        return []
    # Never execute negated commands ("đừng bật đèn", "không mở cửa") or rhetorical checks ("cửa chính đúng không")
    if _NEGATED_OR_RHETORICAL_DIRECT_RE.search(mapped):
        return []
    # Never treat status questions, timers/schedules, custom CRUD, resets, or conditional rules as immediate toggles
    if (
        any(k in norm_raw for k in _NON_DIRECT_INTENT_CUES)
        or _COUNTDOWN_OR_CLOCK_GUARD_RE.search(norm_raw)
        or _CONDITIONAL_THI_GUARD_RE.search(norm_raw)
        or _CUSTOM_COMMAND_DIRECT_GUARD_RE.search(norm_raw)
        or (" ky " in norm_raw and " thi " in norm_raw)
    ):
        return []

    normalized = normalize_vietnamese_utterance(mapped)
    if not normalized:
        return []

    # Split multi-device sentences on conjunctions / punctuation, and also between adjacent
    # verb-device clauses when ASR drops a comma (e.g. 'tắt đèn phòng khách tắt đèn phòng ngủ').
    split_prep = re.sub(
        r"\b(khách|khach|ngủ|ngu|chính|chinh|cửa|cua|cổng|cong|bơm|bom|cây|cay|vườn|vuon|còi|coi|động|dong|loa|đèn|den)\s+"
        r"(?=(?:bật|tắt|mở|đóng|bat|tat|mo|dong)\s+(?:đèn|den|cửa|cua|cổng|cong|máy\s+bơm|may\s+bom|bơm|bom|còi|coi|nguồn|nguon|loa|tất\s+cả|tat\s+ca|hết|het)\b)",
        r"\1 , ",
        normalized,
        flags=re.IGNORECASE,
    )
    clauses = re.split(
        r"\s*(?:,|;|\bvà\b|\bva\b|\brồi\s+thì\b|\broi\s+thi\b|\brồi\b|\broi\b|\bcùng\s+với\b|\bcung\s+voi\b|\bxong\b|\bvới\b|\bvoi\b)\s*",
        split_prep,
        flags=re.IGNORECASE,
    )

    intents: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    last_action: str | None = None

    first_nonempty_seen = False
    for cl in clauses:
        cl_norm = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(cl.lower())).split())
        if not cl_norm:
            continue
        dev = _extract_clause_device(cl_norm)
        act = _extract_clause_action(cl_norm, dev)

        if not first_nonempty_seen:
            first_nonempty_seen = True
            # Multi-clause utterance with a long garbled/unrecognized prefix before 'và <device>'
            # (e.g. ASR-corrupted 'tạo lệnh đi làm ... và đóng cửa chính') must clarify, never act.
            if len(clauses) >= 2 and dev is None and act is None and len(cl_norm.split()) >= 4:
                return []

        if act is not None:
            last_action = act
        elif dev is not None and last_action is not None:
            act = last_action

        if dev is None:
            continue
        if act is None:
            # Ambiguous/garbled device clause without action: abort the whole utterance rather than executing a trailing clause.
            return []

        for item in _expand_direct_target(dev, act):
            key = (item["device_id"], item["action"])
            if key not in seen:
                seen.add(key)
                intents.append(item)

    if not intents:
        intents = _match_constrained_direct_command_vi(normalized)

    return intents


def classify_ambiguous_or_unsupported_vi(text: str) -> str | None:
    """Return a concise Vietnamese clarification/refusal for foreign, nonsense, unsupported, or ambiguous input."""
    raw = _clean_space(text)
    if not raw:
        return NONSENSE_INPUT_REPLY_VI

    is_bad, kind = is_foreign_or_nonsense_input(raw)
    if is_bad:
        return FOREIGN_INPUT_REPLY_VI if kind == "foreign" else NONSENSE_INPUT_REPLY_VI

    norm_raw = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(raw.lower())).split())
    if _UNSUPPORTED_DEVICE_RE.search(f" {norm_raw} "):
        return UNSUPPORTED_DEVICE_REPLY_VI

    normalized = normalize_vietnamese_utterance(raw)
    norm_clean = " ".join(re.sub(r"[^a-z0-9\s]+", " ", strip_vi_accents(normalized.lower())).split())

    dev = _extract_clause_device(norm_clean)
    act = _extract_clause_action(norm_clean, dev)

    if dev is not None and act is None:
        if dev == "main_door":
            return "Bạn muốn mở hay đóng cửa chính?"
        if dev == "all_lights":
            return "Bạn muốn bật hay tắt tất cả đèn?"
        if dev == "all_devices":
            return "Bạn muốn bật hay tắt tất cả thiết bị?"
        lbl = _DEVICE_LABELS_SHORT_VI.get(dev, "thiết bị này")
        return f"Bạn muốn bật hay tắt {lbl}?"

    if act is not None and dev is None:
        if act in ("open", "close"):
            return "Bạn muốn mở hay đóng thiết bị nào?"
        return "Bạn muốn bật hoặc tắt thiết bị nào?"

    return NONSENSE_INPUT_REPLY_VI


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
    if " thi " in padded or any(
        k in padded
        for k in (
            " tao luat ", " lien ket ", " khi ", " neu ", " hen gio ", " dat lich ",
            " reset ", " ri set ", " rex ", " rexit ", " reet ", " dat lai ", " khoi phuc ", " hoi phuc ",
            " truy van trang thai ", " truy suat trang thai ", " refresh trang thai ",
            " re trang thai ", " rep trang thai ", " xep trang thai ", " vi sep trang thai ",
            " vi sach trang thai ", " vi thich trang thai ",
            " viet trang thai ", " logic trang thai ", " re logic ",
            " thiet lap trang thai ", " save trang thai ",
        )
    ):
        return None
    if "," in raw and any(k in padded for k in (" dat kho ", " tieng dong lon ", " am thanh lon ", " chuyen dong lon ")) and any(
        v in padded for v in (" bat ", " tat ", " mo ", " dong ", " tuoi ")
    ):
        return None

    # Never hijack sensor SET mutations ("chỉnh nhiệt độ lên 30", "set độ ẩm đất 25")
    if any(w in padded for w in (" set ", " chinh ", " dat ", " thay doi ")) and re.search(r"\d", norm):
        return None
    if (" nhiet do " in padded or " do am " in padded) and any(w in padded for w in (" len ", " xuong ", " thanh ")) and re.search(r"\d", norm):
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

    # 2. Sensor queries
    ask_temp = " nhiet do " in padded
    ask_soil = any(k in padded for k in (" do am dat ", " cam bien dat ", " dat kho ", " dat uot ", " dat co kho "))
    ask_air_hum = (" do am " in padded) and not (ask_soil and " khong khi " not in padded)
    ask_sound = any(k in padded for k in (" am thanh ", " ky037 ", " ky 037 ", " tieng dong ", " vo tay "))
    ask_all_sensors = " cam bien " in padded and not (ask_temp or ask_air_hum or ask_soil or ask_sound)

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

    # 3. Device status queries
    is_status_query = bool(
        any(
            k in padded
            for k in (
                " trang thai ", " dang mo hay dong ", " dang dong hay mo ",
                " dang bat hay tat ", " dang tat hay bat ", " co dang bat ",
                " co dang tat ", " co dang mo ", " co dang dong ", " co mo khong ",
                " co bat khong ", " co dong khong ", " co tat khong ",
                " dang mo khong ", " dang bat khong ", " dang dong khong ",
                " dang tat khong ", " dang keu khong ", " co dang keu ",
                " dang the nao ", " thiet bi nao dang ", " nhung thiet bi nao ",
            )
        )
    )
    if not is_status_query:
        return None

    # All devices status query
    if any(k in padded for k in (" cac thiet bi ", " tat ca thiet bi ", " toan bo thiet bi ", " trong nha ", " thiet bi nao ")):
        if hasattr(engine, "list_accessible_devices"):
            devs = engine.list_accessible_devices(actor_tier=actor_tier)
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
        return {
            "ok": True,
            "kind": "device_status_query",
            "devices": devs,
            "reply": spoken,
            "exact_spoken_reply": spoken,
        }

    # Single device status query
    dev = _extract_clause_device(norm)
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
            rec = engine.get_device_state_record(td, actor_tier=actor_tier)
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
    return {
        "ok": True,
        "kind": "device_status_query",
        "devices": recs,
        "reply": spoken,
        "exact_spoken_reply": spoken,
    }
